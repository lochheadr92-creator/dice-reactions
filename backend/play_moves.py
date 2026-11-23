"""Player moves: one envelope, one save field, one engine per move kind.

A move is something the player does that changes who knows what, who holds what, or how the world
treats them, beyond writing a sentence. It travels on the ordinary action request, so it takes the
ordinary turn: the same lease, credit, retry and persistence path as any other action.

``session["play_state"]`` is the only state these moves own. It is a plain dict keyed by move kind,
so a branch copies it with the save (and from then on the two saves are independent), and a save
made before moves existed simply has none.

Every engine is a module with the same small shape:

    apply(state, ctx, args, turn=, request_id=)   validate against the situation, record, return a result
    narrator_context(state, ctx, result)          directive lines for the narrator (engine decides, narrator words)
    player_view(state)                            what the player may see back
    options(ctx)                                  what the situation allows now, or why not
    tick(state, ctx, turn)                        optional: time moves on
    project(state, ctx, merged_rolling)           optional: write engine-owned world facts back

Nothing here is switched on by a genre or a scenario name.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator

import bargain_engine
import build_engine
import challenge_engine
import regard_engine
import route_engine
import signal_engine
import teach_engine
from play_facts import Context, MoveError

STATE_VERSION = 1
MAX_ARGS_BYTES = 6000

# Engines register here as they are built. A kind with no engine is refused, never faked.
ENGINES: Dict[str, Any] = {
    challenge_engine.KIND: challenge_engine,
    bargain_engine.KIND: bargain_engine,
    build_engine.KIND: build_engine,
    regard_engine.KIND: regard_engine,
    route_engine.KIND: route_engine,
    signal_engine.KIND: signal_engine,
    teach_engine.KIND: teach_engine,
}

MoveKind = Literal["challenge", "bargain", "route", "regard", "build", "signal", "teach"]


class MoveRequest(BaseModel):
    """One structured move. ``args`` is validated by the engine for its kind, against the real scene."""

    model_config = ConfigDict(extra="forbid")

    kind: MoveKind
    op: Optional[str] = Field(default=None, max_length=24)
    args: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("args")
    @classmethod
    def _bounded(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        if len(json.dumps(value, default=str)) > MAX_ARGS_BYTES:
            raise ValueError("this move is too large")
        return value

    def engine_args(self) -> Dict[str, Any]:
        out = dict(self.args)
        if self.op:
            out["op"] = self.op
        return out


_VERBS = {
    "challenge": "You challenge {who} with what you have",
    "bargain": "You make {who} an offer",
    "route": "You deal with a way through",
    "regard": "You work on how {who} sees someone",
    "build": "You set something up for others",
    "signal": "You settle a signal with {who}",
    "teach": "You teach {who}",
}


def action_text(move: MoveRequest) -> str:
    """Placeholder text for the request; the engine's result replaces it once the move is checked."""
    who = str(move.args.get("audience") or move.args.get("with") or move.args.get("person") or "someone here")[:60]
    return _VERBS[move.kind].format(who=who) + "."


def new_state() -> Dict[str, Any]:
    return {"version": STATE_VERSION}


def referenced_turns(move: Optional[MoveRequest]) -> List[int]:
    """Turn numbers a move names, so only those published turns need loading."""
    found: List[int] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "turn" and isinstance(value, int):
                    found.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    if move is not None:
        walk(move.args)
    return sorted(set(found))


def pin_ids(move: Optional[MoveRequest]) -> List[str]:
    out: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("pin_id"), str):
                out.append(node["pin_id"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    if move is not None:
        walk(move.args)
    return out[:20]


def _engine(kind: str) -> Any:
    engine = ENGINES.get(kind)
    if engine is None:
        raise MoveError(422, "That cannot be done yet.")
    return engine


def apply_move(
    state: Optional[Dict[str, Any]], ctx: Context, move: MoveRequest, *, turn: int, request_id: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    st = copy.deepcopy(state) if isinstance(state, dict) else new_state()
    st.setdefault("version", STATE_VERSION)
    return _engine(move.kind).apply(st, ctx, move.engine_args(), turn=turn, request_id=request_id)


def preview(state: Optional[Dict[str, Any]], ctx: Context, move: MoveRequest) -> Dict[str, Any]:
    """What this move would do, as far as the player may know. Reads only: nothing is kept."""
    try:
        _st, result = apply_move(state, ctx, move, turn=ctx.turn, request_id="preview")
    except MoveError as exc:
        return {"kind": move.kind, "can_commit": False, "issues": [exc.detail]}
    return {"kind": move.kind, "can_commit": True, "issues": [], **{k: v for k, v in result.items() if k in ("audience", "shown", "terms", "notes")}}


def run_tick(state: Optional[Dict[str, Any]], ctx: Context, turn: int) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    if not isinstance(state, dict):
        return state, []
    st = copy.deepcopy(state)
    notes: List[str] = []
    for engine in ENGINES.values():
        fn = getattr(engine, "tick", None)
        if fn:
            st, more = fn(st, ctx, turn)
            notes.extend(more)
    return st, notes


def narrator_context(state: Optional[Dict[str, Any]], ctx: Context, result: Optional[Dict[str, Any]]) -> str:
    if not isinstance(state, dict) and not result:
        return ""
    st = state if isinstance(state, dict) else new_state()
    parts = [engine.narrator_context(st, ctx, result) for engine in ENGINES.values()]
    return "\n\n".join(p for p in parts if p)


def relationship_events(result: Optional[Dict[str, Any]], turn: int) -> List[Dict[str, Any]]:
    """Relationship events this turn's move raised, in the relationship system's own shape.

    An engine names what happened ("a promise was kept toward Maren"). The relationship system
    owns what that is worth and is the only writer of the vectors. A replayed move raises nothing.
    """
    import relationship_provenance as rp

    if not result or result.get("replayed"):
        return []
    return [
        rp.engine_event(ev["kind"], ev["target_name"], source_kind=ev["source_kind"], source_id=ev["source_id"], turn=turn)
        for ev in result.get("relationship_events") or []
    ]


def project(state: Optional[Dict[str, Any]], ctx: Context, merged_rolling: Dict[str, Any], npc_ledger: Dict[str, Any], turn: int) -> List[str]:
    """Write what the engines own back over the narrator's cast and the NPC ledger."""
    notes: List[str] = []
    if not isinstance(state, dict):
        return notes
    for engine in ENGINES.values():
        fn = getattr(engine, "project", None)
        if fn:
            notes.extend(fn(state, ctx, merged_rolling, npc_ledger, turn))
    return notes


def project_ledger(state: Optional[Dict[str, Any]], ctx: Context, ledger: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The player's own inventory: what an engine took stays gone, what it handed over is there."""
    if not isinstance(state, dict) or not isinstance(ledger, dict):
        return ledger
    out = copy.deepcopy(ledger)
    for engine in ENGINES.values():
        fn = getattr(engine, "project_ledger", None)
        if fn:
            out = fn(state, ctx, out)
    return out


def player_view(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    out: Dict[str, Any] = {}
    for kind, engine in ENGINES.items():
        view = engine.player_view(state)
        if view:
            out[kind] = view
    return out


def all_options(ctx: Context) -> Dict[str, Any]:
    return {kind: engine.options(ctx) for kind, engine in ENGINES.items()}


MAX_OFFERS = 3


def offers(options: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Moves the scene itself suggests, shown next to the narrator's choices.

    Built only from what the player was shown and holds (the same options a player can open
    from the icons), so an offer never reveals more than the panel would. Each offer names a
    move kind and what to pre-select; the player still completes and sends it.
    """
    found: List[Dict[str, Any]] = []

    def have(kind: str) -> Dict[str, Any]:
        o = options.get(kind) or {}
        return o if o.get("available") else {}

    o = have("challenge")
    if o and o.get("statements") and (o.get("items") or len(o.get("passages") or []) >= 2):
        audience = {a["name"] for a in o.get("audiences") or []}
        for st in o["statements"]:
            who = next((n for n in st.get("speakers") or [] if n in audience), None)
            if who:
                found.append({"kind": "challenge", "label": f"Challenge what {who} said",
                              "prefill": {"audience": [who], "subject": [f"{st['turn']}:{st['paragraph']}"]}})
                break
    o = have("route")
    if o and not o.get("routes"):
        for passage in o.get("passages") or []:
            text = str(passage.get("text") or "").lower()
            place = next((pl for pl in o.get("places") or [] if pl.lower() in text), None)
            if place:
                found.append({"kind": "route", "label": f"Mark the way toward {place}",
                              "prefill": {"via": [f"{passage['turn']}:{passage['paragraph']}"], "to": [place]}})
                break
    o = have("bargain")
    if o and o.get("items"):
        partner = next((x for x in o.get("partners") or [] if x.get("offers")), None)
        if partner:
            found.append({"kind": "bargain", "label": f"Make {partner['name']} an offer", "prefill": {"with": [partner["name"]]}})
    o = have("signal")
    if o and o.get("partners") and not o.get("signals"):
        found.append({"kind": "signal", "label": f"Agree a signal with {o['partners'][0]['name']}", "prefill": {"with": [o["partners"][0]["name"]]}})
    o = have("teach")
    if o and o.get("learners") and o.get("passages"):
        found.append({"kind": "teach", "label": f"Teach {o['learners'][0]['name']} something", "prefill": {"mode": ["teach"], "learner": [o["learners"][0]["name"]]}})
    return found[:MAX_OFFERS]
