"""Discover a route and choose who learns it.

A route joins two places the story has already established. It is found from something the player was
actually shown, it is known to the people who found it or were told or guided, and it is passable
only while it is open and the player has whatever its gate asks for. Knowing where it leads is not the
same as being able to go through.

State (``play_state["route"]``): ``routes`` with endpoints, label, status, gate, and ``knowers``.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional, Tuple

import notebook
import play_facts as pf
from play_facts import Context, MoveError

KIND = "route"
RESULT_MARKER = "[ROUTE_RESULT_V1]"
STANDING_MARKER = "[ROUTE_STANDING_V1]"
_NS = uuid.UUID("c4a1f0e8-27d3-4b69-8e55-1a9c3d0b7e42")
MAX_ROUTES = 40


def new_state() -> Dict[str, Any]:
    return {"routes": []}


def _part(state: Dict[str, Any]) -> Dict[str, Any]:
    part = state.setdefault(KIND, new_state())
    part.setdefault("routes", [])
    return part


def _same(a: Any, b: Any) -> bool:
    x, y = pf.norm(a), pf.norm(b)
    return bool(x) and bool(y) and (x == y or pf.has_phrase(x, y) or pf.has_phrase(y, x))


def here_label(ctx: Context) -> str:
    r = ctx.rolling
    return pf.clean(r.get("location") or r.get("scene") or "", 120)


def _places(ctx: Context) -> List[str]:
    r = ctx.rolling
    out: List[str] = []
    for key in ("known_rooms", "locations"):
        for v in r.get(key) or []:
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
    out.append(here_label(ctx))
    return [p for p in out if p]


def _established(ctx: Context, place: str) -> bool:
    """A place counts only when the engine lists it. A name that merely appears in prose is not a place yet."""
    return any(_same(place, p) for p in _places(ctx))


def _find(part: Dict[str, Any], route_id: Any) -> Dict[str, Any]:
    for r in part["routes"]:
        if r["id"] == str(route_id):
            return r
    raise MoveError(404, "You do not know of that route.")


def _knows(route: Dict[str, Any], key: str) -> bool:
    return any(k["id"] == key for k in route["knowers"])


def _passable(route: Dict[str, Any], ctx: Context) -> Tuple[bool, str]:
    if route["status"] != "open":
        return False, route.get("note") or "It is blocked."
    gate = route.get("gate")
    if gate and not any(pf.item_matches(i, gate) for i in ctx.held()):
        return False, f"You know where it leads, but you have no {gate}."
    return True, ""


def apply(state: Dict[str, Any], ctx: Context, args: Dict[str, Any], *, turn: int, request_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    st = copy.deepcopy(state)
    part = _part(st)
    rid = str(uuid.uuid5(_NS, f"route:{request_id}"))
    for r in part["routes"]:
        if rid in r["request_ids"]:
            return st, _result(r, "replay", replay=True)
    op = str(args.get("op") or "discover")
    me = ctx.me
    if op == "discover":
        via = args.get("via")
        if not isinstance(via, dict):
            raise MoveError(422, "Point to what you found.")
        try:
            turn_no, idx = int(via.get("turn")), int(via.get("paragraph"))
        except (TypeError, ValueError):
            raise MoveError(422, "Point to what you found.")
        row = ctx.row_for(turn_no)
        if row is None:
            raise MoveError(404, "That is not in your story.")
        paras = pf.paragraphs_of(row)
        try:
            located = notebook.resolve_quote(paras, idx, via.get("quote") or None)
        except notebook.NotebookError as exc:
            raise MoveError(exc.status, exc.detail)
        if not pf.was_shown(ctx.session, turn_no, paras[idx]):
            raise MoveError(422, "Your character was not there to see that.")
        origin = here_label(ctx)
        dest = pf.clean(args.get("to"), 120)
        if not origin:
            raise MoveError(422, "You cannot say where you are yet.")
        if not dest or _same(dest, origin):
            raise MoveError(422, "Say where it leads.")
        if not _established(ctx, dest):
            raise MoveError(422, "That is not a place the story has established yet.")
        gate = pf.clean(args.get("gate"), 60) or None
        if gate and not pf.has_phrase(paras[idx], gate):
            raise MoveError(422, f"Nothing you were shown says {gate} is part of it.")
        for r in part["routes"]:
            if _same(r["a"], origin) and _same(r["b"], dest) or _same(r["a"], dest) and _same(r["b"], origin):
                raise MoveError(409, "You already know a way between those places.")
        route = {"id": rid, "request_ids": [rid], "a": origin, "b": dest, "label": pf.clean(args.get("label") or located["text"], 90),
                 "via": {"turn": turn_no, "text": located["text"]}, "gate": gate, "status": "open", "note": "",
                 "found_by": me, "found_turn": turn, "knowers": [{"id": me, "name": ctx.my_name, "how": "found", "turn": turn}]}
        part["routes"].append(route)
        part["routes"] = part["routes"][-MAX_ROUTES:]
        return st, _result(route, "discover", replay=False)
    route = _find(part, args.get("route_id"))
    if not _knows(route, me):
        raise MoveError(422, "You do not know of that route.")
    if op in ("guide", "teach"):
        person = pf.find_person(ctx.rolling, str(args.get("with") or ""), ctx.scene_text())
        if person is None or not person["present"]:
            raise MoveError(422, "That person is not here.")
        if not (_same(route["a"], here_label(ctx)) or _same(route["b"], here_label(ctx))) and op == "guide":
            raise MoveError(422, "You can only lead someone to it from where it starts.")
        if _knows(route, person["key"]):
            raise MoveError(409, f"{person['name']} already knows it.")
        route["knowers"].append({"id": person["key"], "name": person["name"], "how": "guided" if op == "guide" else "told", "turn": turn, "from": me})
        route["told"] = route.get("told", []) + [person["name"]]
        extra = person["name"]
    elif op == "travel":
        if not (_same(route["a"], here_label(ctx)) or _same(route["b"], here_label(ctx))):
            raise MoveError(422, "You are not at either end of it.")
        ok, why = _passable(route, ctx)
        if not ok:
            raise MoveError(422, why)
        dest = route["b"] if _same(route["a"], here_label(ctx)) else route["a"]
        route["last_used"] = {"by": me, "to": dest, "turn": turn}
        extra = dest
    elif op in ("block", "reopen"):
        if not (_same(route["a"], here_label(ctx)) or _same(route["b"], here_label(ctx))):
            raise MoveError(422, "You are not at either end of it.")
        if op == "block":
            if route["status"] == "blocked":
                raise MoveError(409, "It is already blocked.")
            route.update(status="blocked", note=pf.clean(args.get("note"), 120) or "It is blocked.")
        else:
            if route["status"] == "open":
                raise MoveError(409, "It is already open.")
            route.update(status="open", note="")
        extra = ""
    else:
        raise MoveError(422, "That is not something you can do with a route.")
    route["request_ids"].append(rid)
    route["last_op"] = {"op": op, "turn": turn, "with": extra}
    return st, _result(route, op, replay=False, extra=extra)


def _result(route: Dict[str, Any], op: str, *, replay: bool, extra: str = "") -> Dict[str, Any]:
    a, b = route["a"], route["b"]
    line = {
        "discover": f"The player finds a way between {a} and {b}: {route['label']}." + (f" It needs {route['gate']}; the player does not have it unless already listed as carried." if route.get("gate") else ""),
        "guide": f"The player leads {extra} to the way between {a} and {b} and shows them. {extra} now knows it. No one else does.",
        "teach": f"The player explains the way between {a} and {b} to {extra}. {extra} now knows it. No one else does.",
        "travel": f"The player takes the route and arrives at {extra}. Narrate the trip and the arrival; the route is real and open.",
        "block": f"The way between {a} and {b} is now blocked: {route['note']}. Nobody can pass until it is cleared.",
        "reopen": f"The way between {a} and {b} is clear again.",
        "replay": "Already done.",
    }[op]
    directive = f"{RESULT_MARKER}\n- {line}"
    return {"kind": KIND, "op": op, "replayed": replay, "directive": directive, "id": route["id"], "action_text": {
        "discover": f"You work out a way between {a} and {b}.", "guide": f"You lead {extra} to the way through.", "teach": f"You tell {extra} the way through.",
        "travel": f"You take the way through to {extra}.", "block": "You block the way through.", "reopen": "You clear the way through.", "replay": "You carry on.",
    }[op], "terms": [line]}


def narrator_context(state: Dict[str, Any], ctx: Context, result: Optional[Dict[str, Any]]) -> str:
    part = (state or {}).get(KIND) or {}
    parts: List[str] = []
    if result and result.get("kind") == KIND:
        parts.append(result["directive"])
    here = {p["key"]: p["name"] for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"]}
    lines: List[str] = []
    for r in part.get("routes") or []:
        who = [k["name"] for k in r["knowers"] if k["id"] in here or k["id"] == ctx.me]
        if not who:
            continue
        status = "open" if r["status"] == "open" else f"blocked ({r.get('note') or 'blocked'})"
        gate = f", needs {r['gate']}" if r.get("gate") else ""
        lines.append(f"A way between {r['a']} and {r['b']} ({status}{gate}) is known to: {', '.join(who)}. Nobody else here knows it.")
    if lines:
        parts.append(f"{STANDING_MARKER}\n" + "\n".join(f"- {l}" for l in lines))
    return "\n\n".join(parts)


def player_view(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for r in ((state or {}).get(KIND) or {}).get("routes") or []:
        out.append({"id": r["id"], "a": r["a"], "b": r["b"], "label": r["label"], "status": r["status"], "note": r.get("note", ""),
                    "gate": r.get("gate"), "found_by": r["knowers"][0]["name"], "told": r.get("told", [])})
    return out


def options(ctx: Context) -> Dict[str, Any]:
    part = (ctx.play or {}).get(KIND) or {}
    here = here_label(ctx)
    mine = []
    for r in part.get("routes") or []:
        if not _knows(r, ctx.me):
            continue
        at_end = _same(r["a"], here) or _same(r["b"], here)
        ok, why = _passable(r, ctx)
        mine.append({"id": r["id"], "a": r["a"], "b": r["b"], "label": r["label"], "status": r["status"], "at_end": at_end,
                     "can_travel": at_end and ok, "why_not": "" if ok else why,
                     "told": r.get("told", [])})
    people = [{"name": p["name"]} for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"]]
    passages = []
    for row in sorted(ctx.rows, key=lambda x: int(x.get("turn_number") or 0), reverse=True)[:6]:
        n = int(row.get("turn_number") or 0)
        for i, t in enumerate(pf.paragraphs_of(row)):
            if pf.was_shown(ctx.session, n, t):
                passages.append({"turn": n, "paragraph": i, "text": pf.clean(t, 240)})
    reason = None if (mine or (here and passages)) else "You have not seen anything that could lead anywhere yet."
    return {"kind": KIND, "available": reason is None, "reason": reason, "here": here, "routes": mine, "people": people,
            "places": sorted({p for p in _places(ctx) if not _same(p, here)}), "passages": passages[:12]}


def project(state: Dict[str, Any], ctx: Context, rolling: Dict[str, Any], npc_ledger: Dict[str, Any], turn: int) -> List[str]:
    """A route taken this turn puts the player where it leads, over whatever the narrator wrote."""
    for r in _part(state)["routes"]:
        used = r.get("last_used")
        if used and used.get("turn") == turn and used.get("by") == ctx.me:
            rolling["location"] = used["to"]
            return [f"route_travel:{used['to']}"]
    return []
