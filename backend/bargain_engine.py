"""Strike a bargain with something at stake.

The player proposes terms to someone present who can offer something. The engine, not the narrator,
decides whether they accept, decline or counter, moves the items, and keeps the obligation. A pledge
is held by the other person until the terms that settle it are met. Nothing here reads a genre.

State (``play_state["bargain"]``):
  records  one per proposal: terms, status, who proposed, what settles it
  custody  items an engine moved: who gave it, who holds it now, whether the cast and ledger caught up
"""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional, Tuple

import claim_engine as ce
import play_facts as pf
from play_facts import Context, MoveError

KIND = "bargain"
RESULT_MARKER = "[BARGAIN_RESULT_V1]"
STANDING_MARKER = "[BARGAIN_STANDING_V1]"
_NS = uuid.UUID("0d9c6a2e-51b7-4c3e-9b0a-7f1d3e8a2c64")

REFUSE_BELOW = 15
FAVOUR_FROM = 70
FIRM_BELOW = 25
MAX_ITEMS = 4
MAX_RECORDS = 30
MAX_CUSTODY = 60


def new_state() -> Dict[str, Any]:
    return {"records": [], "custody": []}


def _part(state: Dict[str, Any]) -> Dict[str, Any]:
    part = state.setdefault(KIND, new_state())
    part.setdefault("records", [])
    part.setdefault("custody", [])
    return part


def _names(value: Any, label: str) -> List[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or len(value) > MAX_ITEMS:
        raise MoveError(422, f"{label}: name up to {MAX_ITEMS} things.")
    out: List[str] = []
    for v in value:
        text = pf.clean(v, 80)
        if text and not any(pf.item_matches(text, o) for o in out):
            out.append(text)
    return out


def _held_match(ctx: Context, wanted: str) -> str:
    held = next((i for i in ctx.held() if pf.item_matches(i, wanted)), None)
    if held is None:
        raise MoveError(422, f"You are not carrying {wanted}.")
    return held


def _say(terms: Dict[str, Any], who: str) -> List[str]:
    """The terms in plain words, so they are understood before anyone agrees."""
    lines: List[str] = []
    if terms["give"]:
        lines.append(f"You give {who}: {', '.join(terms['give'])}. You will not have {'it' if len(terms['give']) == 1 else 'them'} afterwards.")
    if terms["pledge"]:
        lines.append(f"{who} holds {', '.join(terms['pledge'])} as security. You cannot use {'it' if len(terms['pledge']) == 1 else 'them'} while they do.")
    if terms["get"]:
        lines.append(f"You get from {who}: {', '.join(terms['get'])}.")
    if terms["service"]:
        lines.append(f"{who} agrees to: {terms['service']}.")
    if terms["settle"]:
        lines.append(f"To settle it, you bring {who}: {', '.join(terms['settle'])}." + (" Then you get your security back." if terms["pledge"] else ""))
    return lines


def _row_by_key(rolling: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    for r in rolling.get("npcs") or []:
        if isinstance(r, dict) and ce.npc_name(r) and ce.npc_key(r) == key:
            return r
    return None


def _present(ctx: Context, name: Any) -> Dict[str, Any]:
    person = pf.find_person(ctx.rolling, str(name or ""), ctx.scene_text())
    if person is None or not person["present"]:
        raise MoveError(422, "That person is not here to deal with.")
    return person


def _respond(ctx: Context, person: Dict[str, Any], terms: Dict[str, Any]) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """(status, reason, counter terms). Decided from regard and from what is on the table."""
    row = person["row"]
    trust = pf.trust_of(ctx.rolling, row)
    if pf.hostile(row) or trust < REFUSE_BELOW:
        return "declined", "will not deal with the player", None
    asked = len(terms["get"]) + (1 if terms["service"] else 0)
    offered = len(terms["give"]) + len(terms["pledge"]) + len(terms["settle"])
    if offered == 0 and trust >= FAVOUR_FROM:
        return "accepted", "does it as a favour", None
    if offered >= asked and offered > 0:
        if trust < FIRM_BELOW and not terms["pledge"]:
            spare = next((i for i in ctx.held() if not any(pf.item_matches(i, t) for t in terms["give"] + terms["pledge"])), None)
            if spare:
                counter = copy.deepcopy(terms)
                counter["pledge"] = counter["pledge"] + [spare]
                if not counter["settle"]:
                    counter["settle"] = list(terms["give"]) or [spare]
                return "countered", "wants something held as security", counter
            return "declined", "does not trust the player to keep the deal", None
        return "accepted", "agrees", None
    spare = next((i for i in ctx.held() if not any(pf.item_matches(i, t) for t in terms["give"] + terms["pledge"])), None)
    if spare and trust >= FIRM_BELOW:
        counter = copy.deepcopy(terms)
        counter["pledge"] = counter["pledge"] + [spare]
        counter["settle"] = counter["settle"] or [spare]
        return "countered", "wants more than was offered", counter
    return "declined", "does not think it is worth it", None


def _terms_from(ctx: Context, person: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    give = [_held_match(ctx, g) for g in _names(args.get("give"), "give")]
    pledge = [_held_match(ctx, g) for g in _names(args.get("pledge"), "pledge")]
    if set(map(pf.norm, give)) & set(map(pf.norm, pledge)):
        raise MoveError(422, "An item cannot be both given and pledged.")
    known = pf.npc_known_items(ctx.npc_ledger, person["row"])
    get = []
    for g in _names(args.get("get"), "get"):
        match = next((k for k in known if pf.item_matches(k, g)), None)
        if match is None:
            raise MoveError(422, f"You do not know that {person['name']} has {g}. Ask what they are carrying first.")
        get.append(match)
    service = pf.clean(args.get("service"), 120)
    row = person["row"]
    if service and not (row.get("role") or pf.npc_inventory(ctx.npc_ledger, row)):
        raise MoveError(422, f"{person['name']} has nothing to offer you that way.")
    settle = _names(args.get("settle"), "settle")
    if not (get or service):
        raise MoveError(422, "Say what you want from them.")
    if not (give or pledge or settle) and pf.trust_of(ctx.rolling, row) < FAVOUR_FROM:
        raise MoveError(422, "Offer them something for it.")
    if pledge and not settle:
        raise MoveError(422, "Say what settles it, so you can get your security back.")
    return {"give": give, "get": get, "service": service, "pledge": pledge, "settle": settle}


def _find(part: Dict[str, Any], bargain_id: Any) -> Dict[str, Any]:
    for rec in part["records"]:
        if rec["id"] == str(bargain_id):
            return rec
    raise MoveError(404, "That bargain is not in your story.")


def _move(part: Dict[str, Any], rec: Dict[str, Any], me: str, cp: str, terms: Dict[str, Any]) -> None:
    mine, theirs = f"player:{me}", f"npc:{cp}"

    def add(item: str, origin: str, holder: str, kind: str) -> None:
        part["custody"].append({"item": item, "origin": origin, "holder": holder, "kind": kind,
                                "bargain": rec["id"], "synced": False, "delivered": False})

    for item in terms["give"]:
        add(item, mine, theirs, "paid")
    for item in terms["pledge"]:
        add(item, mine, theirs, "pledge")
    for item in terms["get"]:
        add(item, theirs, mine, "goods")
    part["custody"] = part["custody"][-MAX_CUSTODY:]


def apply(state: Dict[str, Any], ctx: Context, args: Dict[str, Any], *, turn: int, request_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    st = copy.deepcopy(state)
    part = _part(st)
    rid = str(uuid.uuid5(_NS, f"bargain:{request_id}"))
    for rec in part["records"]:
        if rid in rec["request_ids"]:
            return st, _result(rec, replay=True)
    op = str(args.get("op") or "propose")
    me = ctx.me
    if op == "propose":
        person = _present(ctx, args.get("with"))
        terms = _terms_from(ctx, person, args)
        status, reason, counter = _respond(ctx, person, terms)
        rec = {"id": rid, "request_ids": [rid], "turn": turn, "by": me, "by_name": ctx.my_name,
               "with": pf.ref(person), "terms": terms, "status": status, "reason": reason, "counter": counter}
        part["records"].append(rec)
        part["records"] = part["records"][-MAX_RECORDS:]
        if status == "accepted":
            _move(part, rec, me, person["key"], terms)
            rec["accepted_turn"] = turn
        return st, _result(rec, replay=False)
    rec = _find(part, args.get("bargain_id"))
    if rec["by"] != me:
        raise MoveError(422, "That is not your bargain to deal with.")
    person = _present(ctx, rec["with"]["name"])
    if op == "accept":
        if rec["status"] != "countered" or not rec.get("counter"):
            raise MoveError(409, "There is no counter-offer to accept.")
        terms = rec["counter"]
        for item in terms["give"] + terms["pledge"]:
            _held_match(ctx, item)
        rec.update(status="accepted", terms=terms, counter=None, reason="agrees", accepted_turn=turn)
        _move(part, rec, me, person["key"], terms)
    elif op == "decline":
        if rec["status"] not in ("countered", "open"):
            raise MoveError(409, "That bargain is already settled one way or the other.")
        rec.update(status="declined", reason="the player turned it down", counter=None)
    elif op == "settle":
        if rec["status"] != "accepted" or not rec["terms"]["settle"]:
            raise MoveError(409, "There is nothing left to settle.")
        for item in rec["terms"]["settle"]:
            _held_match(ctx, item)
        for item in rec["terms"]["settle"]:
            part["custody"].append({"item": item, "origin": f"player:{me}", "holder": f"npc:{person['key']}", "kind": "paid",
                                    "bargain": rec["id"], "synced": False, "delivered": False})
        for e in part["custody"]:
            if e["bargain"] == rec["id"] and e["kind"] == "pledge" and e["holder"].startswith("npc:"):
                e.update(holder=f"player:{me}", kind="returned", synced=False, delivered=False)
        rec.update(status="settled", settled_turn=turn, reason="the terms were met")
    else:
        raise MoveError(422, "That is not something you can do with a bargain.")
    rec["request_ids"].append(rid)
    return st, _result(rec, replay=False)


def _result(rec: Dict[str, Any], *, replay: bool) -> Dict[str, Any]:
    who = rec["with"]["name"]
    terms = rec["counter"] if rec["status"] == "countered" and rec.get("counter") else rec["terms"]
    lines = _say(terms, who)
    head = {
        "accepted": f"{who} accepts. The exchange below has already happened; narrate it, do not change it.",
        "declined": f"{who} declines ({rec['reason']}). Nothing changes hands and nothing is owed.",
        "countered": f"{who} will not take it as offered and asks for the terms below instead. Nothing has changed hands. The player has not agreed.",
        "settled": f"The obligation is met. {who} returns what was held and takes what was brought.",
    }[rec["status"]]
    directive = f"{RESULT_MARKER}\n- {head}\n" + "\n".join(f"- {l}" for l in lines)
    return {"kind": KIND, "status": rec["status"], "with": who, "replayed": replay, "directive": directive,
            "terms": lines, "id": rec["id"], "action_text": f"You settle terms with {who}."}


def _mine(part: Dict[str, Any], me: str, *, standing_only: bool = True) -> List[Dict[str, Any]]:
    return [r for r in part["records"] if r["by"] == me]


def narrator_context(state: Dict[str, Any], ctx: Context, result: Optional[Dict[str, Any]]) -> str:
    part = (state or {}).get(KIND) or {}
    parts: List[str] = []
    if result and result.get("kind") == KIND:
        parts.append(result["directive"])
    me = ctx.me
    here = {p["key"] for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"]}
    lines: List[str] = []
    for rec in part.get("records") or []:
        if rec["by"] != me or rec["status"] != "accepted" or not rec["terms"]["settle"]:
            continue
        who = rec["with"]["name"]
        terms = rec["terms"]
        owed = f"The player still owes {who}: {', '.join(terms['settle'])}."
        if terms["pledge"]:
            owed += f" {who} holds {', '.join(terms['pledge'])} until then. The player cannot use or show it."
        lines.append(("(here now) " if rec["with"]["id"] in here else "") + owed)
    gone = [e["item"] for e in part.get("custody") or [] if e["origin"] == f"player:{me}" and e["holder"].startswith("npc:")]
    if gone:
        lines.append(f"The player no longer has: {', '.join(gone)}. They cannot use, drop or show these.")
    if lines:
        parts.append(f"{STANDING_MARKER}\n" + "\n".join(f"- {l}" for l in lines))
    return "\n\n".join(parts)


def project(state: Dict[str, Any], ctx: Context, rolling: Dict[str, Any], npc_ledger: Dict[str, Any], turn: int) -> List[str]:
    notes: List[str] = []
    for e in _part(state)["custody"]:
        if e["synced"]:
            continue
        if e["holder"].startswith("npc:"):
            row = _row_by_key(rolling, e["holder"][4:])
            if row:
                pf.npc_take(npc_ledger, rolling, row, e["item"], turn, reveal=True)
                e["synced"] = True
        elif e["origin"].startswith("npc:"):
            row = _row_by_key(rolling, e["origin"][4:])
            if row:
                pf.npc_lose(npc_ledger, rolling, row, e["item"], turn)
                e["synced"] = True
        else:
            e["synced"] = True
    return notes


def project_ledger(state: Dict[str, Any], ctx: Context, ledger: Dict[str, Any]) -> Dict[str, Any]:
    part = _part(state)
    me = f"player:{ctx.me}"
    keep: List[Dict[str, Any]] = []
    for e in part["custody"]:
        if e["holder"].startswith("npc:") and e["origin"].startswith("player:"):
            ledger = pf.ledger_remove(ledger, e["item"])
            keep.append(e)
        elif e["holder"] == me and not e["delivered"]:
            ledger = pf.ledger_add(ledger, e["item"])
            e["delivered"] = True
        elif e["holder"] == me:
            pass
        else:
            keep.append(e)
    part["custody"] = keep
    return ledger


def player_view(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for r in ((state or {}).get(KIND) or {}).get("records") or []:
        terms = r["counter"] if r["status"] == "countered" and r.get("counter") else r["terms"]
        out.append({"id": r["id"], "turn": r["turn"], "with": r["with"]["name"], "status": r["status"],
                    "terms": _say(terms, r["with"]["name"]), "by": r["by_name"]})
    return out


def options(ctx: Context) -> Dict[str, Any]:
    here = [p for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"] and not pf.hostile(p["row"])]
    partners = []
    for p in here:
        known = pf.npc_known_items(ctx.npc_ledger, p["row"])
        partners.append({"name": p["name"], "offers": known, "service": bool(p["row"].get("role") or pf.npc_inventory(ctx.npc_ledger, p["row"]))})
    part = (ctx.play or {}).get(KIND) or {}
    open_ = []
    for r in part.get("records") or []:
        if r["by"] != ctx.me:
            continue
        if r["status"] == "countered":
            open_.append({"id": r["id"], "with": r["with"]["name"], "status": "countered", "terms": _say(r["counter"], r["with"]["name"]), "can": ["accept", "decline"]})
        elif r["status"] == "accepted" and r["terms"]["settle"]:
            near = any(p["name"] == r["with"]["name"] for p in here)
            open_.append({"id": r["id"], "with": r["with"]["name"], "status": "accepted", "terms": _say(r["terms"], r["with"]["name"]), "can": ["settle"] if near else []})
    reason = None
    if not here:
        reason = "Nobody here can deal with you."
    elif not partners or not (ctx.held() or any(x["offers"] for x in partners)):
        reason = "You have nothing to trade."
    return {"kind": KIND, "available": reason is None or bool(open_), "reason": reason, "partners": partners, "items": ctx.held(), "open": open_}
