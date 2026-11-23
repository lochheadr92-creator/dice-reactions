"""Standing instructions: "when Orin arrives, give him the data chip".

The engine owns what was asked, what the NPC understood, what she could observe, what she
decided and whether she had the means. The narrator only describes the result. State lives on
the save (``session["order_state"]``), never in narrator-written rolling state.

A deliberately small vocabulary, one implementation for every story. Nothing here names a
scenario's objects.

Conditions
  * ``gauge_reaches``: a gauge in ``rolling_state["gauges"]`` (label, mark, level, visible_from)
    reaches its named mark. The NPC must be standing somewhere the gauge is visible from.
  * ``person_arrives``: a named person is standing where the NPC is, having not been there when
    the instruction was given.

Action
  * ``deliver_item``: hand something the NPC carries to a named person. Any item, in any setting.
    It happens when the NPC carries that item and the two are in the same place. Until they
    are, she keeps waiting.

Decision: she refuses when she distrusts the player, is hostile, or is flagged
``refuses_orders``. A refusal and a missing item are final outcomes, not retries. An order fires
at most once: status moves off ``pending`` exactly once, inside the same transactional commit
as the turn, and a tick for a turn already processed is a no-op.

The engine owns the gauges once an order exists (the narrator cannot stop one rising). The
gauges a story starts with come from ``rolling_state``; the engine copies them on first sight
and projects its own values back after every merge. Gauges are story data: nothing here invents
one for a story that has none.
"""

from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

import claim_engine as ce
import relationships as rel

ORDER_VERSION = 1
MAX_ORDERS = 12
MAX_TEXT = 280
REFUSE_TRUST_BELOW = 25
DIRECTIVE_MARKER = "[ORDER_RESULT_V1]"
CONTEXT_MARKER = "[STANDING_ORDERS_V1]"
_NS = uuid.UUID("0c1d52a8-7b0e-4b7e-8a53-6e1f0d2b9c77")

OrderError = ce.ClaimError

_LEAD = r"(?:if|when|once|as soon as|the moment)"
_REACH = re.compile(r"\b(reach(?:es)?|hit(?:s)?|gets? to|rises? to|pass(?:es)?|cross(?:es)?|touch(?:es)?|tops?)\b", re.I)
_ARRIVE = re.compile(
    r"^(.+?)\s+(?:arrives?|shows? up|turns? up|gets? here|gets? in|docks?|comes? (?:in|here|back)|returns?)\b.*$", re.I
)
_GIVE_ACT = re.compile(r"\b(?:deliver|hand|give|bring|pass|take)\b\s+(.+)$", re.I)
_GIVE_TO = re.compile(r"\s+(?:over\s+)?to\s+(.+)$", re.I)
_GIVE_LEAD = re.compile(r"^(?:(?:over|him|her|them|it|the|a|an|my|your|his|their|this|that)\s+)+", re.I)
MAX_ITEM_TEXT = 60
LEGACY_ITEM = "parcel"   # orders saved before delivery covered any item
# Orders and results from the removed "cut the ferry loose" action can still sit in a save.
LEGACY_ACTIONS = frozenset({"cut_ferry_loose"})


def new_state() -> Dict[str, Any]:
    return {"version": ORDER_VERSION, "orders": [], "world": {}, "last_tick_turn": 0}


_n = ce._norm


def _inventory(row: Dict[str, Any]) -> List[str]:
    return [str(i) for i in (row.get("inventory") or []) if isinstance(i, str)]


def _parse_delivery(act_text: str) -> Optional[Tuple[str, Optional[str]]]:
    """("what to hand over", "to whom" or None) when the instruction is a handover, else None."""
    m = _GIVE_ACT.search(act_text or "")
    if not m:
        return None
    rest = m.group(1).strip()
    target = None
    to = _GIVE_TO.search(rest)
    if to:
        target, rest = to.group(1).strip(), rest[:to.start()].strip()
    item = _GIVE_LEAD.sub("", rest + " ").strip()
    item = re.sub(r"\s+over$", "", item, flags=re.I).strip()
    return item[:MAX_ITEM_TEXT], target


def _find_named_item(row: Dict[str, Any], phrase: str) -> Optional[str]:
    """The item this person carries that the instruction named: the exact name, or the name as whole words."""
    want = _n(phrase)
    if not want:
        return None
    items = _inventory(row)
    for item in items:
        if _n(item) == want:
            return item
    whole = re.compile(r"\b" + re.escape(want) + r"\b")
    return next((item for item in items if whole.search(_n(item))), None)


def _willing(rolling: Dict[str, Any], row: Dict[str, Any]) -> bool:
    if rel.refuses_player(row):
        return False
    trust = rel.recorded_trust(rolling, row)
    return trust is None or trust >= REFUSE_TRUST_BELOW


def _ensure_world(state: Dict[str, Any], rolling: Dict[str, Any]) -> None:
    world = state.setdefault("world", {})
    if "gauges" not in world:
        gauges = {}
        for key, g in (rolling.get("gauges") or {}).items():
            if isinstance(g, dict) and isinstance(g.get("level"), (int, float)) and isinstance(g.get("mark"), (int, float)):
                gauges[str(key)] = {
                    "label": str(g.get("label") or key),
                    "mark_name": str(g.get("mark_name") or "mark"),
                    "level": g["level"],
                    "mark": g["mark"],
                    "rise_per_turn": g.get("rise_per_turn") if isinstance(g.get("rise_per_turn"), (int, float)) else 0,
                    "visible_from": [str(v) for v in g.get("visible_from") or []],
                }
        world["gauges"] = gauges


def _resolve_person(rolling: Dict[str, Any], phrase: str, exclude: Optional[Dict[str, Any]] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    want = _n(phrase)
    if not want:
        return None, "I don't know who you mean."
    rows = [r for r in rolling.get("npcs") or [] if isinstance(r, dict) and ce.npc_name(r) and r is not exclude]
    exact = [r for r in rows if _n(ce.npc_name(r)) == want]
    if exact:
        return exact[0], None
    partial = [r for r in rows if want in _n(ce.npc_name(r)).split() or want in _n(ce.npc_name(r))]
    if len(partial) == 1:
        return partial[0], None
    if len(partial) > 1:
        return None, f'"{phrase.strip()}" could be {" or ".join(ce.npc_name(r) for r in partial)}.'
    return None, f"I don't know anyone called {phrase.strip()}."


def _split(text: str) -> Tuple[Optional[str], str]:
    t = text.strip().rstrip(".!")
    m = re.match(rf"^{_LEAD}\s+(.+?)\s*,\s*(?:then\s+)?(.+)$", t, re.I)
    if m:
        return m.group(1), m.group(2)
    m = re.match(rf"^(.+?)\s+{_LEAD}\s+(.+)$", t, re.I)
    if m:
        return m.group(2), m.group(1)
    return None, t


def parse(text: str, rolling: Dict[str, Any], state: Optional[Dict[str, Any]], recipient: Dict[str, Any]) -> Dict[str, Any]:
    """What the recipient understood. Deterministic, free, and the same code the commit uses."""
    st = copy.deepcopy(state) if state else new_state()
    _ensure_world(st, rolling)
    world = st["world"]
    issues: List[str] = []
    notes: List[str] = []
    name = ce.npc_name(recipient)
    cond_text, act_text = _split(text)
    condition: Optional[Dict[str, Any]] = None
    action: Optional[Dict[str, Any]] = None
    arriving: Optional[Dict[str, Any]] = None

    if cond_text is None:
        issues.append("Say when she should act, for example: when someone arrives, ...")
    else:
        cl = cond_text.lower()
        matched = [(k, g) for k, g in world.get("gauges", {}).items() if g["mark_name"].lower() in cl and g["label"].lower() in cl]
        if matched and _REACH.search(cl):
            key, g = matched[0]
            condition = {"kind": "gauge_reaches", "gauge": key, "summary": f"the {g['label']} reaches the {g['mark_name']}"}
            if g["level"] >= g["mark"]:
                issues.append(f"The {g['label']} is already at the {g['mark_name']}; there is nothing to wait for.")
        elif any(g["label"].lower() in cl for g in world.get("gauges", {}).values()):
            marks = ", ".join(f"the {g['mark_name']}" for g in world.get("gauges", {}).values())
            issues.append(f"I can only watch for it reaching a mark I can see ({marks}). Which mark do you mean?")
        else:
            m = _ARRIVE.match(cond_text.strip())
            if m:
                person, why = _resolve_person(rolling, re.sub(r"^(?:the)\s+", "", m.group(1).strip(), flags=re.I), exclude=recipient)
                if person is None:
                    issues.append(why or "I don't know who you mean.")
                else:
                    arriving = person
                    condition = {"kind": "person_arrives", "person": {"id": ce.npc_key(person), "name": ce.npc_name(person)},
                                 "summary": f"{ce.npc_name(person)} arrives"}
                    if ce._where(person) == ce._where(recipient):
                        issues.append(f"{ce.npc_name(person)} is already here; there is nothing to wait for.")
            else:
                issues.append("She can only act on something reaching a mark she can see, or on a named person arriving.")

    handover = _parse_delivery(act_text)
    if handover:
        item_text, to_whom = handover
        target = arriving
        if not item_text:
            issues.append("Say what should be handed over.")
        elif to_whom:
            target, why = _resolve_person(rolling, re.sub(r"^(?:the)\s+", "", to_whom, flags=re.I), exclude=recipient)
            if target is None:
                issues.append(why or f"I don't know who the {item_text} is for.")
        elif target is None:
            issues.append(f"Who should get the {item_text}?")
        if item_text and target is not None:
            action = {"kind": "deliver_item", "item": item_text,
                      "target": {"id": ce.npc_key(target), "name": ce.npc_name(target)},
                      "summary": f"hand the {item_text} to {ce.npc_name(target)}"}
    else:
        issues.append("She can only hand something she carries to someone.")

    if condition and action:
        # Never say here whether she has it: what someone carries is not the player's to learn from a preview.
        notes.append(f"{name} can hand over the {action['item']} only if she is carrying it when the time comes.")
        if condition["kind"] == "gauge_reaches":
            g = world["gauges"][condition["gauge"]]
            where = ce._where(recipient)
            if where in {_n(v) for v in g["visible_from"]}:
                notes.append(f"{name} can see the {g['mark_name']} from where she is.")
            else:
                notes.append(f"{name} cannot see the {g['mark_name']} from where she is, so she will not notice it.")
        notes.append(f"{name} seems willing to take your word." if _willing(rolling, recipient) else f"{name} seems reluctant to take orders from you.")

    return {
        "recipient": name,
        "understood": None if issues or not (condition and action) else {
            "condition": condition["summary"], "action": action["summary"],
        },
        "issues": issues,
        "notes": notes,
        "can_commit": not issues and bool(condition and action),
        "_condition": condition, "_action": action,
    }


def preview(state: Optional[Dict[str, Any]], rolling: Dict[str, Any], recipient_ref: str, text: str) -> Dict[str, Any]:
    row = _present_recipient(rolling, recipient_ref)
    out = parse(text, rolling, state, row)
    return {k: v for k, v in out.items() if not k.startswith("_")}


def _present_recipient(rolling: Dict[str, Any], ref: str) -> Dict[str, Any]:
    row = ce.find_npc(rolling, ref)
    if row is None or row not in ce.present_npcs(rolling):
        raise OrderError(422, f"{ref.strip() or 'That person'} is not here to leave instructions with.")
    return row


def record_order(state: Optional[Dict[str, Any]], rolling: Dict[str, Any], *, turn: int, request_id: str,
                 recipient_ref: str, text: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Add one order. Same request id, same order: a retry adds nothing."""
    row = _present_recipient(rolling, recipient_ref)
    st = copy.deepcopy(state) if state else new_state()
    oid = str(uuid.uuid5(_NS, f"order:{request_id}"))
    for existing in st["orders"]:
        if existing["id"] == oid:
            return st, existing
    parsed = parse(text, rolling, st, row)
    if not parsed["can_commit"]:
        raise OrderError(422, " ".join(parsed["issues"]) or "I could not make sense of that instruction.")
    if sum(1 for o in st["orders"] if o["status"] == "pending") >= MAX_ORDERS:
        raise OrderError(422, "She is already holding as many instructions as she can keep in her head.")
    _ensure_world(st, rolling)
    if not st["orders"]:
        # The gauges start moving from the turn the first instruction is given.
        st["last_tick_turn"] = turn - 1
    order = {
        "id": oid, "turn": turn, "recipient": {"id": ce.npc_key(row), "name": ce.npc_name(row)},
        "text": text.strip()[:MAX_TEXT], "condition": parsed["_condition"], "action": parsed["_action"],
        "status": "pending", "shown": False,
    }
    st["orders"].append(order)
    return st, order


def _decide(order: Dict[str, Any], rolling: Dict[str, Any], row: Dict[str, Any], turn: int) -> Optional[Dict[str, Any]]:
    """Resolve one triggered order. None means she holds off for now."""
    out = {"fired_turn": turn, "at": ce._where(row)}
    if order["action"]["kind"] in LEGACY_ACTIONS:
        return {**out, "status": "void"}
    target = ce.find_npc(rolling, order["action"]["target"]["id"])
    if target is None or not ce._alive(rolling, target):
        return {**out, "status": "void"}
    if ce._where(target) != ce._where(row):
        return None                          # nothing changes hands until the two are in the same place
    if not _willing(rolling, row):
        return {**out, "status": "refused"}
    item = _find_named_item(row, order["action"].get("item") or LEGACY_ITEM)
    if not item:
        return {**out, "status": "no_means"}
    return {**out, "status": "done", "effect": {"kind": "item_given", "item": item, "from": ce.npc_key(row),
                                                  "to": order["action"]["target"]["id"]}}


def tick(state: Optional[Dict[str, Any]], rolling: Dict[str, Any], turn: int) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Advance the world's gauges and let each pending order observe, decide and act, once."""
    if not state or not state.get("orders") and not state.get("world", {}).get("gauges"):
        return state, []
    st = copy.deepcopy(state)
    if turn <= int(st.get("last_tick_turn") or 0):
        return state, []
    _ensure_world(st, rolling)
    world = st["world"]
    steps = max(0, turn - int(st.get("last_tick_turn") or 0))
    for g in world.get("gauges", {}).values():
        g["level"] = g["level"] + g.get("rise_per_turn", 0) * steps
    notes: List[str] = []
    for order in st["orders"]:
        if order["status"] != "pending":
            continue
        row = ce.find_npc(rolling, order["recipient"]["id"]) or ce.find_npc(rolling, order["recipient"]["name"])
        if row is None or not ce._alive(rolling, row):
            order["status"] = "void"
            continue
        if _n(row.get("controller")) == "player":
            continue
        cond = order["condition"]
        if cond["kind"] == "gauge_reaches":
            g = world["gauges"].get(cond["gauge"])
            if not g or g["level"] < g["mark"] or ce._where(row) not in {_n(v) for v in g["visible_from"]}:
                continue
        else:
            person = ce.find_npc(rolling, cond["person"]["id"])
            if person is None or not ce._alive(rolling, person) or ce._where(person) != ce._where(row):
                continue
        result = _decide(order, rolling, row, turn)
        if result is None:
            continue
        order.update(result)
        notes.append(f"order {order['id'][:8]} {order['status']}")
    st["last_tick_turn"] = turn
    return st, notes


def project(state: Optional[Dict[str, Any]], rolling: Dict[str, Any]) -> List[str]:
    """Write the engine's world back over whatever the narrator left, every turn."""
    if not state:
        return []
    world = state.get("world") or {}
    notes: List[str] = []
    if world.get("gauges"):
        rolling["gauges"] = copy.deepcopy(world["gauges"])
    for order in state.get("orders") or []:
        eff = order.get("effect")
        if order.get("status") != "done" or not eff or eff["kind"] not in ("item_given", "parcel_given"):
            continue
        giver, taker = ce.find_npc(rolling, eff["from"]), ce.find_npc(rolling, eff["to"])
        if giver is not None and eff["item"] in _inventory(giver):
            giver["inventory"] = [i for i in giver["inventory"] if i != eff["item"]]
        if taker is not None and eff["item"] not in _inventory(taker):
            taker["inventory"] = _inventory(taker) + [eff["item"]]
    return notes


def narrator_context(state: Optional[Dict[str, Any]], rolling: Dict[str, Any]) -> str:
    if not state:
        return ""
    here = {ce.npc_key(r) for r in ce.present_npcs(rolling)}
    lines = []
    for o in state.get("orders") or []:
        if o["status"] == "pending" and o["recipient"]["id"] in here:
            lines.append(
                f'- {o["recipient"]["name"]} was told: "{o["text"]}" She understood it as: when {o["condition"]["summary"]}, '
                f'{o["action"]["summary"]}. She is waiting for that and has not acted yet.'
            )
    if not lines:
        return ""
    return f"{CONTEXT_MARKER}\n" + "\n".join(lines) + "\nShow her waiting or watching in character. Do not make the condition happen yourself."


_RESULT = {
    "done_ferry_adrift": "{n} cut the ferry loose with {tool}. The ferry is now adrift.",   # a result saved before that action was removed
    "done_item_given": "{n} handed the {item} to {to}.",
    "done_parcel_given": "{n} handed the parcel to {to}.",
    "refused": "{n} saw it was time, but chose not to {act}. Show the hesitation or refusal in character. Nothing changed.",
    "no_means": "{n} wanted to {act}, but had nothing to do it with. Nothing changed.",
}


def _result_line(order: Dict[str, Any]) -> str:
    n, act = order["recipient"]["name"], order["action"]["summary"]
    eff = order.get("effect") or {}
    if order["status"] == "done":
        return _RESULT["done_" + eff["kind"]].format(n=n, tool=eff.get("tool", ""), item=order["action"].get("item") or LEGACY_ITEM,
                                                     to=order["action"].get("target", {}).get("name", ""))
    return _RESULT[order["status"]].format(n=n, act=act)


def pending_observations(state: Optional[Dict[str, Any]], rolling: Dict[str, Any], turn: int) -> Tuple[str, List[str]]:
    """Results the player is now standing close enough to see. Elsewhere they wait for the player."""
    if not state:
        return "", []
    scene = ce._scene(rolling)
    lines, ids = [], []
    for o in state.get("orders") or []:
        if o["status"] in {"done", "refused", "no_means"} and not o.get("shown") and o.get("at") == scene:
            when = "just now" if o.get("fired_turn") == turn else f"on turn {o.get('fired_turn')}, while the player was away"
            lines.append(f"- ({when}) {_result_line(o)}")
            ids.append(o["id"])
    if not lines:
        return "", []
    return (
        f"{DIRECTIVE_MARKER}\nThe player can see these results. Show what is now visible. If it happened while they were away, "
        "show the changed scene and let the people here say what happened, without a flashback.\n" + "\n".join(lines),
        ids,
    )


def mark_observed(state: Optional[Dict[str, Any]], ids: List[str], turn: int) -> Optional[Dict[str, Any]]:
    if not state or not ids:
        return state
    st = copy.deepcopy(state)
    for o in st["orders"]:
        if o["id"] in ids:
            o["shown"] = True
            o["shown_turn"] = turn
    return st


def player_view(state: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What the player may see: their words, what she understood, and a result only once seen."""
    out = []
    for o in (state or {}).get("orders") or []:
        row = {"id": o["id"], "turn": o["turn"], "to": o["recipient"]["name"], "text": o["text"],
               "understood": f"When {o['condition']['summary']}, {o['action']['summary']}."}
        if o.get("shown"):
            row["result"] = _result_line(o).split(" Show ")[0].split(" Nothing")[0]
        out.append(row)
    return out
