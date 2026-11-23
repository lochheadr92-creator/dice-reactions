"""Challenge a claim with evidence.

The player brings up something a person said, picks which evidence to show, and picks who hears
it. The engine decides the answer (explanation, denial, concession or refusal) from how much the
listener trusts the player, whether the listener is the one being challenged, and how much was
actually shown. The narrator only describes it.

What is evidence is limited to what the current character really has:

* a statement: an exact published passage in which a named person speaks,
* an observation: any other published passage the character was shown (tracks, a smell, a room),
* an item the character carries now.

A notebook pin is only a pointer to a published passage. It carries no authority of its own, so a
pin made from the former protagonist's chapter cannot make evidence for a successor who was not
there.

A challenge records what was shown and to whom. It never writes anything into the world: the
player's suspicion is a claim, so the listener's answer is that person's account and not a fact.
Whatever evidence the player held back stays unknown to everyone.
"""

from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

import notebook
import play_facts as pf
from play_facts import Context, MoveError

KIND = "challenge"
RESULT_MARKER = "[CHALLENGE_RESULT_V1]"
SHOWN_MARKER = "[SHOWN_EVIDENCE_V1]"
_NS = uuid.UUID("6a1b7c52-93d4-4f0e-8a1d-0c5e2d7f4b19")

REFUSE_BELOW = 15
OPEN_FROM = 40
MAX_EVIDENCE = 4
MAX_RECORDS = 30
MAX_TEXT = 400
_SPEECH = re.compile(r"[\"“”]")


def new_state() -> Dict[str, Any]:
    return {"records": [], "knowledge": []}


def _part(state: Dict[str, Any]) -> Dict[str, Any]:
    return state.setdefault(KIND, new_state())


def _is_speech(text: str, full: str = "", start: int = 0) -> bool:
    """Spoken words: the slice carries quote marks, or sits between an opened and closed pair in its paragraph."""
    if _SPEECH.search(text or ""):
        return True
    return bool(full) and len(_SPEECH.findall(full[:start])) % 2 == 1 and bool(_SPEECH.search(full[start + len(text):]))


def _passage(ctx: Context, turn: Any, paragraph: Any, quote: Any) -> Dict[str, Any]:
    """One published passage, exactly as the current character was shown it."""
    try:
        turn_number, index = int(turn), int(paragraph)
    except (TypeError, ValueError):
        raise MoveError(422, "Pick a passage from your story.")
    row = ctx.row_for(turn_number)
    if row is None:
        raise MoveError(404, "That passage is not in your story.")
    paragraphs = pf.paragraphs_of(row)
    try:
        located = notebook.resolve_quote(paragraphs, index, quote if quote else None)
    except notebook.NotebookError as exc:
        raise MoveError(exc.status, exc.detail)
    if not pf.was_shown(ctx.session, turn_number, paragraphs[index]):
        raise MoveError(422, "Your character was not there to see that.")
    return {"turn": turn_number, "paragraph": index, "text": pf.clean(located["text"], MAX_TEXT), "full": paragraphs[index], "start": located["start"]}


def _speaker(ctx: Context, passage: Dict[str, Any], who: Any) -> Optional[Dict[str, str]]:
    """The person a statement belongs to: someone named in that very passage."""
    ref_text = str(who or "").strip()
    if not ref_text:
        return None
    for person in pf.people(ctx.rolling):
        if pf.norm(ref_text) in {pf.norm(person["name"]), person["key"]} and pf.named_in(passage["full"], person["row"], ctx.rolling):
            return pf.ref(person)
    raise MoveError(422, f"{ref_text} is not named in that passage.")


def _evidence_item(ctx: Context, raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise MoveError(422, "That evidence is not usable.")
    if raw.get("item"):
        wanted = pf.clean(raw["item"], 80)
        held = next((i for i in ctx.held() if pf.item_matches(i, wanted)), None)
        if held is None:
            raise MoveError(422, f"You are not carrying {wanted}.")
        return {"kind": "item", "item": held, "text": held, "weight": 1}
    turn, paragraph, quote = raw.get("turn"), raw.get("paragraph"), raw.get("quote")
    if raw.get("pin_id"):
        pin = ctx.pins.get(str(raw["pin_id"]))
        if not pin:
            raise MoveError(404, "That pin is not in your notebook.")
        turn, paragraph, quote = pin.get("turn_number"), pin.get("paragraph_index"), pin.get("text")
    passage = _passage(ctx, turn, paragraph, quote)
    who = _speaker(ctx, passage, raw.get("speaker")) if raw.get("speaker") else None
    if who and not _is_speech(passage["text"], passage["full"], passage["start"]):
        raise MoveError(422, "That is not something anyone said.")
    kind = "statement" if who and _is_speech(passage["text"], passage["full"], passage["start"]) else "observation"
    return {"kind": kind, "turn": passage["turn"], "paragraph": passage["paragraph"], "text": passage["text"],
            "speaker": who, "weight": 1}


def _decide(trust: int, hostile: bool, is_speaker: bool, strength: int) -> Tuple[str, str]:
    if hostile or trust < REFUSE_BELOW:
        return "refusal", "does not trust the player enough to discuss it"
    if is_speaker:
        if strength >= 3:
            return "concession", "faced with more than one thing that does not fit"
        if strength == 2:
            return ("explanation", "trusts the player enough to explain") if trust >= OPEN_FROM else ("denial", "does not trust the player enough to explain")
        return ("explanation", "trusts the player enough to explain") if trust >= OPEN_FROM else ("denial", "is not moved by one thing")
    return ("explanation", "will say what they know") if trust >= OPEN_FROM else ("refusal", "will not speak for someone else")


_RESULT_LINE = {
    "explanation": (
        "{who} gives an account that makes sense of what was shown. It is {who}'s own account, not established truth: "
        "do not say whether it is true, and do not settle the matter for the player."
    ),
    "denial": "{who} denies it and holds to what they said. Do not reveal whether they are lying.",
    "concession": "{who} concedes what the evidence shows and no more than it shows. Do not volunteer anything else.",
    "refusal": "{who} refuses to discuss it and tells the player nothing about it.",
}


def apply(state: Dict[str, Any], ctx: Context, args: Dict[str, Any], *, turn: int, request_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Record one confrontation. Idempotent on ``request_id``: a retry is the same challenge."""
    st = copy.deepcopy(state)
    part = _part(st)
    cid = str(uuid.uuid5(_NS, f"challenge:{request_id}"))
    for rec in part["records"]:
        if rec["id"] == cid:
            return st, _result(rec, replay=True)

    scene_text = ctx.scene_text()
    audience = pf.find_person(ctx.rolling, str(args.get("audience") or ""), scene_text)
    if audience is None or not audience["present"]:
        raise MoveError(422, "That person is not here to talk to.")
    sub = args.get("subject")
    if not isinstance(sub, dict):
        raise MoveError(422, "Pick what they said.")
    passage = _passage(ctx, sub.get("turn"), sub.get("paragraph"), sub.get("quote"))
    if not _is_speech(passage["text"], passage["full"], passage["start"]):
        raise MoveError(422, "That is not something anyone said.")
    speaker = _speaker(ctx, passage, sub.get("speaker"))
    if speaker is None:
        raise MoveError(422, "Say who said it.")

    raw_evidence = args.get("evidence")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise MoveError(422, "Choose something to show them.")
    if len(raw_evidence) > MAX_EVIDENCE:
        raise MoveError(422, f"Show them at most {MAX_EVIDENCE} things at once.")
    evidence: List[Dict[str, Any]] = []
    seen = {(passage["turn"], passage["paragraph"], pf.norm(passage["text"]))}
    for raw in raw_evidence:
        item = _evidence_item(ctx, raw)
        key = ("item", pf.norm(item["item"])) if item["kind"] == "item" else (item["turn"], item["paragraph"], pf.norm(item["text"]))
        if key in seen:
            continue
        seen.add(key)
        evidence.append(item)
    if not evidence:
        raise MoveError(422, "That is the very thing you are challenging. Show them something else.")

    is_speaker = speaker["id"] == audience["key"]
    for e in evidence:
        e["weight"] = 2 if e["kind"] == "statement" else 1  # an account that conflicts weighs more than a thing seen
    strength = sum(e["weight"] for e in evidence)
    trust = pf.trust_of(ctx.rolling, audience["row"])
    outcome, reason = _decide(trust, pf.hostile(audience["row"]), is_speaker, strength)

    aloud = bool(args.get("aloud"))
    witnesses = [
        pf.ref(p) for p in pf.people(ctx.rolling, scene_text)
        if p["present"] and p["key"] != audience["key"] and (aloud or p["row"].get("within_earshot") is True)
    ]
    shown = [{"kind": e["kind"], "text": e["text"], **({"speaker": e["speaker"]["name"]} if e.get("speaker") else {})} for e in evidence]
    rec = {
        "id": cid, "turn": turn, "request_id": request_id, "by": ctx.me,
        "audience": pf.ref(audience), "witnesses": witnesses, "aloud": aloud,
        "subject": {"text": passage["text"], "speaker": speaker, "turn": passage["turn"], "paragraph": passage["paragraph"]},
        "evidence": shown, "outcome": outcome, "reason": reason, "strength": strength,
    }
    part["records"].append(rec)
    part["records"] = part["records"][-MAX_RECORDS:]
    holders = [pf.ref(audience)] + witnesses
    facts = [f'The player said {speaker["name"]} said: "{passage["text"]}"'] + [
        (f'The player showed {e["text"]}' if e["kind"] == "item" else f'The player pointed to: "{e["text"]}"') for e in shown
    ]
    for holder in holders:
        for fact in facts:
            part["knowledge"].append({"holder": holder, "fact": fact, "challenge_id": cid, "turn": turn})
    part["knowledge"] = part["knowledge"][-120:]
    return st, _result(rec, replay=False)


def _result(rec: Dict[str, Any], *, replay: bool) -> Dict[str, Any]:
    who = rec["audience"]["name"]
    shown = "\n".join(f'  - {e["text"]}' for e in rec["evidence"])
    directive = (
        f"{RESULT_MARKER}\n- {_RESULT_LINE[rec['outcome']].format(who=who)}\n"
        f"- The player showed {who}:\n{shown}\n"
        f"- {who} knows only what is listed above from this. Nobody who was not there heard it."
    )
    return {
        "kind": KIND, "outcome": rec["outcome"], "audience": who, "replayed": replay, "directive": directive,
        "shown": rec["evidence"],
        "action_text": f'You confront {who} about what {rec["subject"]["speaker"]["name"]} said, and show them what you have.',
    }


def narrator_context(state: Dict[str, Any], ctx: Context, result: Optional[Dict[str, Any]]) -> str:
    part = (state or {}).get(KIND) or {}
    parts: List[str] = []
    if result and result.get("kind") == KIND:
        parts.append(result["directive"])
    here = {p["key"] for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"]}
    lines = [f'- {k["holder"]["name"]} was shown: {k["fact"]}' for k in part.get("knowledge") or [] if k["holder"]["id"] in here]
    if lines:
        parts.append(
            f"{SHOWN_MARKER}\nWhat people here were shown by the player. They know this and nothing more from it. "
            "It is what was shown, not what is true.\n" + "\n".join(lines[-12:])
        )
    return "\n\n".join(parts)


def player_view(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """What the player did and was told back. Who else heard stays engine side."""
    return [
        {
            "id": r["id"], "turn": r["turn"], "audience": r["audience"]["name"],
            "subject": {"speaker": r["subject"]["speaker"]["name"], "text": r["subject"]["text"]},
            "evidence": r["evidence"], "outcome": r["outcome"],
        }
        for r in ((state or {}).get(KIND) or {}).get("records") or []
    ]


def options(ctx: Context) -> Dict[str, Any]:
    """What the situation lets the player challenge now, and what is missing when it does not."""
    scene_text = ctx.scene_text()
    here = [p for p in pf.people(ctx.rolling, scene_text) if p["present"]]
    statements, observations = [], []
    for row in sorted(ctx.rows, key=lambda r: int(r.get("turn_number") or 0), reverse=True)[:12]:
        turn_number = int(row.get("turn_number") or 0)
        for index, text in enumerate(pf.paragraphs_of(row)):
            if not pf.was_shown(ctx.session, turn_number, text):
                continue
            named = [p for p in pf.people(ctx.rolling) if pf.named_in(text, p["row"], ctx.rolling)]
            entry = {"turn": turn_number, "paragraph": index, "text": pf.clean(text, 280)}
            if _is_speech(text) and named:
                statements.append({**entry, "speakers": [p["name"] for p in named]})
            observations.append(entry)
    items = ctx.held()
    reason = None
    if not here:
        reason = "Nobody is here to put it to."
    elif not statements:
        reason = "Nobody has said anything you could bring up yet."
    elif len(observations) < 2 and not items:
        reason = "You have nothing else to show them."
    return {
        "kind": KIND, "available": reason is None, "reason": reason,
        "audiences": [{"name": p["name"]} for p in here],
        "statements": statements[:20], "passages": observations[:30], "items": items,
    }
