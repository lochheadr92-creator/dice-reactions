"""Teach another character a skill.

A lesson is between a teacher who has been shown to know the skill and a willing learner, over
something real to practise on. It takes two lessons on different turns. The skill is recorded against
that one character; anyone else who was in the room only heard about it and gains nothing. A skill is a
small, general effect (not a scenario item) that changes what the narrator may let that character
notice: with it they can pick out a forgery, a gap in a record, or the marks of a passage; without it
they only see what is plain.

State (``play_state["teach"]``): ``skills`` (who has what, from whom) and ``lessons`` (in progress).
"""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional, Tuple

import notebook
import play_facts as pf
from play_facts import Context, MoveError

KIND = "teach"
RESULT_MARKER = "[TEACH_RESULT_V1]"
STANDING_MARKER = "[SKILL_STANDING_V1]"
_NS = uuid.UUID("5e8c1a40-9d37-4b2a-a6f1-2c7d0b93e854")
LESSONS_NEEDED = 2
MIN_LEARNER_TRUST = 20
MIN_TEACHER_TRUST = 40
MAX_SKILLS = 40

EFFECTS = {
    "verify": "tell a genuine thing from a forgery or a counterfeit",
    "audit": "notice what is missing or out of sequence in a record or a list",
    "trace": "read the marks left by someone or something that passed",
}


def new_state() -> Dict[str, Any]:
    return {"skills": [], "lessons": []}


def _part(state: Dict[str, Any]) -> Dict[str, Any]:
    part = state.setdefault(KIND, new_state())
    part.setdefault("skills", [])
    part.setdefault("lessons", [])
    return part


def has(part: Dict[str, Any], holder: str, effect: str) -> Optional[Dict[str, Any]]:
    return next((s for s in part.get("skills", []) if s["holder"]["id"] == holder and s["effect"] == effect), None)


def _tokens(label: str) -> List[str]:
    return [t[:4] for t in pf.norm(label).split() if len(t) >= 4]


def _passage(ctx: Context, raw: Any) -> Tuple[Dict[str, Any], str]:
    if not isinstance(raw, dict):
        raise MoveError(422, "Point to where you were shown it.")
    try:
        n, i = int(raw.get("turn")), int(raw.get("paragraph"))
    except (TypeError, ValueError):
        raise MoveError(422, "Point to where you were shown it.")
    row = ctx.row_for(n)
    if row is None:
        raise MoveError(404, "That is not in your story.")
    paras = pf.paragraphs_of(row)
    try:
        loc = notebook.resolve_quote(paras, i, raw.get("quote") or None)
    except notebook.NotebookError as exc:
        raise MoveError(exc.status, exc.detail)
    if not pf.was_shown(ctx.session, n, paras[i]):
        raise MoveError(422, "Your character was not there to see that.")
    return {"turn": n, "paragraph": i, "text": pf.clean(loc["text"], 240)}, paras[i]


def _practice(ctx: Context, raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict) and raw.get("item"):
        held = next((i for i in ctx.held() if pf.item_matches(i, str(raw["item"]))), None)
        if held is None:
            raise MoveError(422, f"You are not carrying {pf.clean(raw['item'], 60)}.")
        return {"kind": "item", "text": held}
    loc, _full = _passage(ctx, raw)
    return {"kind": "passage", "text": loc["text"]}


def apply(state: Dict[str, Any], ctx: Context, args: Dict[str, Any], *, turn: int, request_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    st = copy.deepcopy(state)
    part = _part(st)
    rid = str(uuid.uuid5(_NS, f"teach:{request_id}"))
    for les in part["lessons"]:
        if rid in les["request_ids"]:
            return st, _result(les, "replay", replay=True)
    for sk in part["skills"]:
        if rid in sk.get("request_ids", []):
            return st, _result({"learner": sk["holder"], "teacher": sk["from"], "label": sk["label"], "effect": sk["effect"], "turns": [], "status": "learned"}, "replay", replay=True)
    op = str(args.get("op") or "teach")
    me = ctx.me
    effect = str(args.get("effect") or "")
    if effect not in EFFECTS:
        raise MoveError(422, "Choose what it lets them do: " + ", ".join(EFFECTS) + ".")
    if op == "use":
        mine = has(part, me, effect)
        if not mine:
            raise MoveError(422, "You do not know how to do that.")
        target = args.get("target")
        if isinstance(target, dict) and target.get("item"):
            held = next((i for i in ctx.held() if pf.item_matches(i, str(target["item"]))), None)
            if held is None:
                raise MoveError(422, f"You are not carrying {pf.clean(target['item'], 60)}.")
            what = held
        else:
            loc, _ = _passage(ctx, target)
            what = loc["text"]
        mine["uses"] = mine.get("uses", 0) + 1
        mine.setdefault("request_ids", []).append(rid)
        return st, {"kind": KIND, "op": "use", "replayed": False, "id": rid, "terms": [],
                    "directive": (f"{RESULT_MARKER}\n- The player examines {what!r} using what they learned: they can {EFFECTS[effect]}. "
                                  f"Tell them plainly what that skill reveals, only if it is really there. If nothing is wrong, say it checks out. Do not invent a flaw."),
                    "action_text": "You look closely, using what you were taught."}
    if op != "teach":
        raise MoveError(422, "Teach a skill or use one.")
    label = pf.clean(args.get("skill"), 60)
    if not label:
        raise MoveError(422, "Name the skill.")
    teacher_ref, learner_ref = str(args.get("teacher") or "me"), str(args.get("learner") or "")
    if (teacher_ref == "me") == (learner_ref in ("", "me")):
        raise MoveError(422, "Teach someone else, or be taught by someone else.")
    def person(name: str) -> Dict[str, Any]:
        p = pf.find_person(ctx.rolling, name, ctx.scene_text())
        if p is None or not p["present"]:
            raise MoveError(422, f"{pf.clean(name, 60)} is not here.")
        return p
    if teacher_ref == "me":
        learner_p = person(learner_ref)
        if pf.hostile(learner_p["row"]) or pf.trust_of(ctx.rolling, learner_p["row"]) < MIN_LEARNER_TRUST:
            raise MoveError(422, f"{learner_p['name']} will not take instruction from you.")
        teacher = {"id": me, "name": ctx.my_name}
        learner = pf.ref(learner_p)
        known = has(part, me, effect)
        if not known:
            # No record of it yet: you must be able to point to being shown that you can do it.
            _loc, full = _passage(ctx, args.get("demonstrated"))
            if not any(t in pf.norm(full) for t in _tokens(label)):
                raise MoveError(422, "That passage does not show you doing it.")
    else:
        teacher_p = person(teacher_ref)
        if pf.hostile(teacher_p["row"]) or pf.trust_of(ctx.rolling, teacher_p["row"]) < MIN_TEACHER_TRUST:
            raise MoveError(422, f"{teacher_p['name']} will not teach you.")
        loc, full = _passage(ctx, args.get("demonstrated"))
        if not pf.named_in(full, teacher_p["row"], ctx.rolling):
            raise MoveError(422, f"{teacher_p['name']} is not part of what you point to.")
        if not any(t in pf.norm(full) for t in _tokens(label)):
            raise MoveError(422, "That passage does not show it being done.")
        teacher, learner = pf.ref(teacher_p), {"id": me, "name": ctx.my_name}
    if has(part, learner["id"], effect):
        raise MoveError(409, f"{learner['name']} already knows how.")
    practice = _practice(ctx, args.get("practise_on"))
    les = next((l for l in part["lessons"] if l["learner"]["id"] == learner["id"] and l["effect"] == effect and l["status"] == "learning"), None)
    if les is None:
        les = {"id": rid, "request_ids": [], "learner": learner, "teacher": teacher, "label": label, "effect": effect, "turns": [],
               "practised_on": [], "status": "learning", "heard": []}
        part["lessons"].append(les)
    if turn in les["turns"]:
        raise MoveError(409, "One lesson a turn. Let it sink in.")
    les["turns"].append(turn)
    les["practised_on"].append(practice["text"])
    les["request_ids"].append(rid)
    les["heard"] = [pf.ref(p) for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"] and p["key"] not in (learner["id"], teacher["id"])]
    if len(les["turns"]) >= LESSONS_NEEDED:
        les["status"] = "learned"
        part["skills"].append({"holder": learner, "effect": effect, "label": label, "from": teacher, "learned_turn": turn, "request_ids": []})
        part["skills"] = part["skills"][-MAX_SKILLS:]
    return st, _result(les, "teach", replay=False)


def _result(les: Dict[str, Any], op: str, *, replay: bool) -> Dict[str, Any]:
    t, l = les["teacher"]["name"], les["learner"]["name"]
    if op == "replay":
        line = ["Already done."]
    elif les["status"] == "learned":
        line = [f"{t} gives {l} the second lesson in {les['label']}, practising on {les['practised_on'][-1]!r}. {l} has now got it: they can {EFFECTS[les['effect']]}. "
                f"Nobody else in the room learned it; anyone who watched only knows a lesson happened."]
    else:
        line = [f"{t} begins teaching {l} {les['label']}, practising on {les['practised_on'][-1]!r}. {l} is not there yet and cannot do it. One more lesson, on another day."]
    return {"kind": KIND, "op": op, "replayed": replay, "directive": f"{RESULT_MARKER}\n" + "\n".join(f"- {x}" for x in line), "terms": line,
            "id": les.get("id", ""), "action_text": f"You work through {les['label']} together."}


def narrator_context(state: Dict[str, Any], ctx: Context, result: Optional[Dict[str, Any]]) -> str:
    part = (state or {}).get(KIND) or {}
    parts: List[str] = []
    if result and result.get("kind") == KIND:
        parts.append(result["directive"])
    if not part.get("skills") and not part.get("lessons"):
        return "\n\n".join(parts)
    here = {p["key"]: p["name"] for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"]}
    lines: List[str] = []
    mine = [s for s in part.get("skills", []) if s["holder"]["id"] == ctx.me]
    for s in mine:
        lines.append(f"The player's character has learned {s['label']}: they can {EFFECTS[s['effect']]}.")
    missing = [f"{EFFECTS[e]}" for e in EFFECTS if not has(part, ctx.me, e)]
    if missing:
        lines.append("The player's character cannot, unless it is plain to anyone: " + "; ".join(missing) + ". Do not let them pick out those subtle details.")
    for s in part.get("skills", []):
        if s["holder"]["id"] in here and s["holder"]["id"] != ctx.me:
            lines.append(f"{s['holder']['name']} learned {s['label']} from {s['from']['name']}: they can {EFFECTS[s['effect']]}, and may point it out on their own, briefly, if it is really there. Others here cannot.")
    if lines:
        parts.append(f"{STANDING_MARKER}\n" + "\n".join(f"- {l}" for l in lines))
    return "\n\n".join(parts)


def player_view(state: Dict[str, Any]) -> Dict[str, Any]:
    part = (state or {}).get(KIND) or {}
    return {
        "skills": [{"who": s["holder"]["name"], "label": s["label"], "effect": s["effect"], "from": s["from"]["name"], "turn": s["learned_turn"]} for s in part.get("skills", [])],
        "lessons": [{"learner": l["learner"]["name"], "teacher": l["teacher"]["name"], "label": l["label"], "given": len(l["turns"]), "needed": LESSONS_NEEDED}
                    for l in part.get("lessons", []) if l["status"] == "learning"],
    } if (part.get("skills") or part.get("lessons")) else {}


def options(ctx: Context) -> Dict[str, Any]:
    part = (ctx.play or {}).get(KIND) or {}
    here = [p for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"]]
    learners = [{"name": p["name"]} for p in here if not pf.hostile(p["row"]) and pf.trust_of(ctx.rolling, p["row"]) >= MIN_LEARNER_TRUST]
    teachers = [{"name": p["name"]} for p in here if not pf.hostile(p["row"]) and pf.trust_of(ctx.rolling, p["row"]) >= MIN_TEACHER_TRUST]
    own = [{"label": s["label"], "effect": s["effect"]} for s in part.get("skills", []) if s["holder"]["id"] == ctx.me]
    reason = None if (learners or teachers) and (ctx.held() or ctx.rows) else "Nobody here is willing to teach or learn from you."
    passages = []
    for row in sorted(ctx.rows, key=lambda x: int(x.get("turn_number") or 0), reverse=True)[:6]:
        n = int(row.get("turn_number") or 0)
        for i, t in enumerate(pf.paragraphs_of(row)):
            if pf.was_shown(ctx.session, n, t):
                passages.append({"turn": n, "paragraph": i, "text": pf.clean(t, 240)})
    return {"kind": KIND, "available": reason is None, "reason": reason, "passages": passages[:12], "learners": learners, "teachers": teachers, "effects": EFFECTS, "own": own,
            "items": ctx.held(), "lessons_needed": LESSONS_NEEDED}
