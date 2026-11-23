"""Change how two other people see each other.

Regard is directional: what Y thinks of X is not what X thinks of Y. The player can introduce two
people, vouch for one to the other, mediate between them, or expose one to the other. How far the
other person is moved depends on how much they trust the player. The result is used later: an errand
one asks of the other is decided from that regard, with or without the player in the room.

State (``play_state["regard"]``): ``edges`` (holder, toward, value), ``acts`` (what the player did),
``errands`` (a request between two people and how it was decided).
"""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional, Tuple

import claim_engine as ce
import play_facts as pf
from play_facts import Context, MoveError

KIND = "regard"
RESULT_MARKER = "[REGARD_RESULT_V1]"
STANDING_MARKER = "[REGARD_STANDING_V1]"
ERRAND_MARKER = "[BETWEEN_THEM_V1]"
_NS = uuid.UUID("8b3e5d17-6a42-4f90-bd21-0e7c9a4f1d58")

DEFAULT = 30
WILL_HELP = 50
MET = 40
LISTENS_FROM = 20
MAX_ACTS = 40


def new_state() -> Dict[str, Any]:
    return {"edges": [], "acts": [], "errands": []}


def _part(state: Dict[str, Any]) -> Dict[str, Any]:
    part = state.setdefault(KIND, new_state())
    for k in ("edges", "acts", "errands"):
        part.setdefault(k, [])
    return part


def regard(part: Dict[str, Any], holder: str, toward: str) -> int:
    for e in part.get("edges") or []:
        if e["holder"] == holder and e["toward"] == toward:
            return int(e["value"])
    return DEFAULT


def _set(part: Dict[str, Any], holder: Dict[str, str], toward: Dict[str, str], value: int) -> None:
    value = max(0, min(100, int(value)))
    for e in part["edges"]:
        if e["holder"] == holder["id"] and e["toward"] == toward["id"]:
            e["value"] = value
            return
    part["edges"].append({"holder": holder["id"], "holder_name": holder["name"], "toward": toward["id"], "toward_name": toward["name"], "value": value})


def word(value: int) -> str:
    if value >= WILL_HELP:
        return "warm toward"
    if value >= MET:
        return "civil but unsure of"
    if value >= 20:
        return "wary of"
    return "cold toward"


def _person(ctx: Context, name: Any) -> Dict[str, Any]:
    p = pf.find_person(ctx.rolling, str(name or ""), ctx.scene_text())
    if p is None or not p["present"]:
        raise MoveError(422, f"{pf.clean(name, 60) or 'That person'} is not here.")
    return p


def _pull(ctx: Context, p: Dict[str, Any]) -> int:
    """How far this person lets the player move them: nothing below a floor, more with trust."""
    trust = pf.trust_of(ctx.rolling, p["row"])
    if pf.hostile(p["row"]) or trust < LISTENS_FROM:
        return 0
    return max(5, (trust - LISTENS_FROM) // 2)


def _evidence(ctx: Context, ev: Any, about: Dict[str, Any]) -> str:
    if not isinstance(ev, dict):
        raise MoveError(422, "Show them something that happened.")
    if ev.get("item"):
        held = next((i for i in ctx.held() if pf.item_matches(i, str(ev["item"]))), None)
        if held is None:
            raise MoveError(422, f"You are not carrying {ev['item']}.")
        return held
    import notebook

    try:
        n, i = int(ev.get("turn")), int(ev.get("paragraph"))
    except (TypeError, ValueError):
        raise MoveError(422, "Show them something that happened.")
    row = ctx.row_for(n)
    if row is None:
        raise MoveError(404, "That is not in your story.")
    paras = pf.paragraphs_of(row)
    try:
        loc = notebook.resolve_quote(paras, i, ev.get("quote") or None)
    except notebook.NotebookError as exc:
        raise MoveError(exc.status, exc.detail)
    if not pf.was_shown(ctx.session, n, paras[i]):
        raise MoveError(422, "Your character was not there to see that.")
    if not pf.named_in(paras[i], about["row"], ctx.rolling):
        raise MoveError(422, f"{about['name']} is not part of what you point to.")
    return pf.clean(loc["text"], 240)


def apply(state: Dict[str, Any], ctx: Context, args: Dict[str, Any], *, turn: int, request_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    st = copy.deepcopy(state)
    part = _part(st)
    rid = str(uuid.uuid5(_NS, f"regard:{request_id}"))
    for a in part["acts"]:
        if a["id"] == rid:
            return st, _result(a, replay=True)
    op = str(args.get("op") or "")
    if op not in ("introduce", "vouch", "mediate", "expose"):
        raise MoveError(422, "Introduce them, vouch for one, mediate, or expose one.")
    x = _person(ctx, args.get("a"))
    y = _person(ctx, args.get("b"))
    if x["key"] == y["key"]:
        raise MoveError(422, "Pick two different people.")
    rx, ry = pf.ref(x), pf.ref(y)
    changes: List[Dict[str, Any]] = []
    detail = ""
    if op == "introduce":
        for h, t, hp in ((rx, ry, x), (ry, rx, y)):
            if any(e["holder"] == h["id"] and e["toward"] == t["id"] for e in part["edges"]):
                continue
            _set(part, h, t, MET)
            changes.append({"holder": h["name"], "toward": t["name"], "to": MET})
        if not changes:
            raise MoveError(409, "They already know each other.")
    elif op == "vouch":
        # a is vouched for to b: b's regard for a moves, a's regard for b does not.
        pull = _pull(ctx, y)
        before = regard(part, y["key"], x["key"])
        after = before + pull
        if pull == 0:
            detail = f"{y['name']} does not take the player's word for it."
        else:
            _set(part, ry, rx, after)
            changes.append({"holder": y["name"], "toward": x["name"], "from": before, "to": after})
    elif op == "mediate":
        for h, t, hp in ((rx, ry, x), (ry, rx, y)):
            pull = _pull(ctx, hp) // 2
            before = regard(part, h["id"], t["id"])
            if pull:
                _set(part, h, t, before + pull)
                changes.append({"holder": h["name"], "toward": t["name"], "from": before, "to": before + pull})
        if not changes:
            detail = "Neither of them will hear the player out."
    else:  # expose: tell b what a did
        shown = _evidence(ctx, args.get("evidence"), x)
        pull = _pull(ctx, y)
        before = regard(part, y["key"], x["key"])
        if pull == 0:
            detail = f"{y['name']} does not believe the player."
        else:
            after = before - (10 + pull)
            _set(part, ry, rx, after)
            changes.append({"holder": y["name"], "toward": x["name"], "from": before, "to": after})
        detail = detail or f"The player showed {y['name']}: {shown}. It is what the player showed, not what is proven."
    errand = args.get("errand")
    if isinstance(errand, dict) and errand.get("what"):
        asker, giver = _person(ctx, errand.get("asker")), _person(ctx, errand.get("giver"))
        if {asker["key"], giver["key"]} != {x["key"], y["key"]}:
            raise MoveError(422, "The errand has to be between the two people you are working with.")
        part["errands"].append({"id": rid, "asker": pf.ref(asker), "giver": pf.ref(giver), "what": pf.clean(errand["what"], 120),
                                "turn": turn, "by": ctx.me, "status": "waiting"})
    act = {"id": rid, "turn": turn, "op": op, "a": rx, "b": ry, "by": ctx.me, "detail": detail, "changes": changes,
           "errand": bool(isinstance(errand, dict) and errand.get("what"))}
    part["acts"].append(act)
    part["acts"] = part["acts"][-MAX_ACTS:]
    return st, _result(act, replay=False)


_LINE = {
    "introduce": "The player introduces {a} and {b}. They now know of each other and are civil, nothing more.",
    "vouch": "The player speaks up for {a} to {b}.",
    "mediate": "The player sits {a} and {b} down and gets them talking.",
    "expose": "The player tells {b} what {a} did.",
}


def _result(act: Dict[str, Any], *, replay: bool) -> Dict[str, Any]:
    a, b = act["a"]["name"], act["b"]["name"]
    lines = [_LINE[act["op"]].format(a=a, b=b)]
    if act["detail"]:
        lines.append(act["detail"])
    for c in act["changes"]:
        w = word(c["to"])
        lines.append(f"{c['holder']} is now {w} {c['toward']}." + (" (Not the other way round.)" if act["op"] in ("vouch", "expose") else ""))
    if act["errand"]:
        lines.append("Something has been asked between them for later. Do not decide it now.")
    directive = f"{RESULT_MARKER}\n" + "\n".join(f"- {l}" for l in lines)
    return {"kind": KIND, "op": act["op"], "replayed": replay, "directive": directive, "terms": lines, "id": act["id"],
            "action_text": f"You bring {a} and {b} together."}


def _here(ctx: Context) -> Dict[str, str]:
    return {p["key"]: p["name"] for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"]}


def _row(rolling: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    for r in rolling.get("npcs") or []:
        if isinstance(r, dict) and ce.npc_name(r) and ce.npc_key(r) == key:
            return r
    return None


def _place(row: Dict[str, Any]) -> str:
    return pf.norm(row.get("location") or row.get("last_seen") or "")


def tick(state: Dict[str, Any], ctx: Context, turn: int) -> Tuple[Dict[str, Any], List[str]]:
    """An errand is decided when its two people are in the same place, whether or not the player is."""
    part = _part(state)
    notes: List[str] = []
    for e in part["errands"]:
        if e["status"] != "waiting" or turn <= e["turn"]:
            continue
        a, g = _row(ctx.rolling, e["asker"]["id"]), _row(ctx.rolling, e["giver"]["id"])
        if not a or not g or not pf.alive(ctx.rolling, a) or not pf.alive(ctx.rolling, g):
            continue
        if not _place(a) or _place(a) != _place(g):
            continue
        value = regard(part, e["giver"]["id"], e["asker"]["id"])
        e.update(status="agreed" if value >= WILL_HELP else "refused", decided_turn=turn, seen=False, regard=value)
        notes.append(f"errand:{e['status']}")
    return state, notes


def narrator_context(state: Dict[str, Any], ctx: Context, result: Optional[Dict[str, Any]]) -> str:
    part = (state or {}).get(KIND) or {}
    parts: List[str] = []
    if result and result.get("kind") == KIND:
        parts.append(result["directive"])
    here = _here(ctx)
    lines: List[str] = []
    for e in part.get("edges") or []:
        if e["holder"] in here and e["toward"] in here:
            lines.append(f"{e['holder_name']} is {word(e['value'])} {e['toward_name']}. Let it show in how they treat each other.")
    done: List[str] = []
    for er in part.get("errands") or []:
        if er["status"] in ("agreed", "refused") and not er.get("seen") and (er["asker"]["id"] in here or er["giver"]["id"] in here):
            verb = "agrees to" if er["status"] == "agreed" else "refuses"
            done.append(f"{er['asker']['name']} asked {er['giver']['name']} for this: {er['what']}. {er['giver']['name']} {verb} it. This is already settled; narrate it as news the player now notices.")
    if lines:
        parts.append(f"{STANDING_MARKER}\n" + "\n".join(f"- {l}" for l in lines))
    if done:
        parts.append(f"{ERRAND_MARKER}\n" + "\n".join(f"- {l}" for l in done))
    return "\n\n".join(parts)


def project(state: Dict[str, Any], ctx: Context, rolling: Dict[str, Any], npc_ledger: Dict[str, Any], turn: int) -> List[str]:
    here = _here(ctx)
    for er in _part(state)["errands"]:
        if er["status"] in ("agreed", "refused") and not er.get("seen") and (er["asker"]["id"] in here or er["giver"]["id"] in here):
            er["seen"] = True
    return []


def player_view(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    part = (state or {}).get(KIND) or {}
    out: List[Dict[str, Any]] = []
    for a in part.get("acts") or []:
        out.append({"id": a["id"], "turn": a["turn"], "op": a["op"], "a": a["a"]["name"], "b": a["b"]["name"],
                    "effects": [f"{c['holder']} is now {word(c['to'])} {c['toward']}" for c in a["changes"]] or ([a["detail"]] if a["detail"] else [])})
    for er in part.get("errands") or []:
        if er["status"] in ("agreed", "refused") and er.get("seen"):
            out.append({"id": er["id"], "turn": er["decided_turn"], "op": "errand", "a": er["asker"]["name"], "b": er["giver"]["name"],
                        "effects": [f"{er['giver']['name']} {'agreed to' if er['status'] == 'agreed' else 'refused'}: {er['what']}"]})
    return out


def options(ctx: Context) -> Dict[str, Any]:
    here = [p for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"]]
    reason = None if len(here) >= 2 else "You need two other people here to work on."
    return {"kind": KIND, "available": reason is None, "reason": reason, "people": [{"name": p["name"]} for p in here],
            "ops": ["introduce", "vouch", "mediate", "expose"], "items": ctx.held()}
