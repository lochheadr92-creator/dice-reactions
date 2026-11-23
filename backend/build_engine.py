"""Leave something behind that others can use.

The player spends items they are carrying to put a lasting capability at the place they are standing:
a shelter, a place to rest, a hideout, or a cache. The cost is real and recorded, the capability stays
at that place, and whoever is later there and knows of it can use it. Choosing one improvement can make
another unaffordable. The builder's private note never reaches anyone else.

State (``play_state["build"]``): ``works`` and ``spent`` (items the build took, kept off the ledger).
"""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional, Tuple

import play_facts as pf
from play_facts import Context, MoveError
from route_engine import _same, here_label

KIND = "build"
RESULT_MARKER = "[BUILD_RESULT_V1]"
STANDING_MARKER = "[BUILD_STANDING_V1]"
_NS = uuid.UUID("3f6a9b14-d082-4e7c-a5b3-96c1e0d84f27")
MAX_WORKS = 30
MAX_ITEMS = 4
KEEP_SPENT_TURNS = 3

KINDS: Dict[str, Dict[str, Any]] = {
    "shelter": {"cost": 2, "visible": True, "stores": False, "label": "a shelter",
                "effect": "protection from weather and the elements for whoever is inside"},
    "rest": {"cost": 2, "visible": True, "stores": False, "label": "a place to rest",
             "effect": "somewhere safe and quiet to rest and recover"},
    "hideout": {"cost": 1, "visible": False, "stores": False, "label": "a hideout",
                "effect": "a concealed spot where someone can hide from anyone searching"},
    "cache": {"cost": 1, "visible": False, "stores": True, "label": "a cache",
              "effect": "stored supplies that those who know of it can take"},
}


def new_state() -> Dict[str, Any]:
    return {"works": [], "spent": [], "deliver": []}


def _part(state: Dict[str, Any]) -> Dict[str, Any]:
    part = state.setdefault(KIND, new_state())
    for k in ("works", "spent", "deliver"):
        part.setdefault(k, [])
    return part


def _knows(work: Dict[str, Any], key: str, here: bool) -> bool:
    if any(k["id"] == key for k in work["knowers"]):
        return True
    return bool(here and KINDS[work["kind"]]["visible"])


def _at(work: Dict[str, Any], ctx: Context) -> bool:
    return _same(work["place"], here_label(ctx))


def _find(part: Dict[str, Any], work_id: Any) -> Dict[str, Any]:
    for w in part["works"]:
        if w["id"] == str(work_id):
            return w
    raise MoveError(404, "There is nothing like that here.")


def _pick_items(ctx: Context, raw: Any) -> List[str]:
    if not isinstance(raw, list) or not raw or len(raw) > MAX_ITEMS:
        raise MoveError(422, f"Choose what to spend: 1 to {MAX_ITEMS} things you are carrying.")
    out: List[str] = []
    for v in raw:
        held = next((i for i in ctx.held() if pf.item_matches(i, str(v))), None)
        if held is None:
            raise MoveError(422, f"You are not carrying {pf.clean(v, 60)}.")
        if not any(pf.item_matches(held, o) for o in out):
            out.append(held)
    return out


def apply(state: Dict[str, Any], ctx: Context, args: Dict[str, Any], *, turn: int, request_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    st = copy.deepcopy(state)
    part = _part(st)
    rid = str(uuid.uuid5(_NS, f"build:{request_id}"))
    for w in part["works"]:
        if rid in w["request_ids"]:
            return st, _result(w, "replay", replay=True)
    op = str(args.get("op") or "build")
    me = ctx.me
    place = here_label(ctx)
    if op == "build":
        if not place:
            raise MoveError(422, "You cannot say where you are yet.")
        kind = str(args.get("kind") or "")
        spec = KINDS.get(kind)
        if spec is None:
            raise MoveError(422, "Choose what to leave: " + ", ".join(KINDS) + ".")
        items = _pick_items(ctx, args.get("items"))
        if len(items) < spec["cost"]:
            raise MoveError(422, f"{spec['label'].capitalize()} takes {spec['cost']} things. You chose {len(items)}.")
        if any(_same(w["place"], place) and w["kind"] == kind for w in part["works"]):
            raise MoveError(409, f"There is already {spec['label']} here.")
        work = {"id": rid, "request_ids": [rid], "kind": kind, "place": place, "cost": items, "turn": turn, "by": me, "by_name": ctx.my_name,
                "note": pf.clean(args.get("note"), 200), "knowers": [{"id": me, "name": ctx.my_name, "how": "built it"}],
                "stock": list(items) if spec["stores"] else []}
        part["works"].append(work)
        part["works"] = part["works"][-MAX_WORKS:]
        for item in items:
            part["spent"].append({"item": item, "by": me, "turn": turn})
        return st, _result(work, "build", replay=False)
    work = _find(part, args.get("work_id"))
    here = _at(work, ctx)
    if not here:
        raise MoveError(422, "You are not there.")
    if not _knows(work, me, here):
        raise MoveError(422, "You do not know of that.")
    if op == "share":
        person = pf.find_person(ctx.rolling, str(args.get("with") or ""), ctx.scene_text())
        if person is None or not person["present"]:
            raise MoveError(422, "That person is not here.")
        if any(k["id"] == person["key"] for k in work["knowers"]):
            raise MoveError(409, f"{person['name']} already knows.")
        work["knowers"].append({"id": person["key"], "name": person["name"], "how": "was told", "from": me})
        extra = person["name"]
    elif op == "use":
        if KINDS[work["kind"]]["stores"]:
            wanted = [pf.clean(v, 60) for v in (args.get("items") or [])]
            if not wanted:
                raise MoveError(422, "Choose what to take.")
            taken: List[str] = []
            for v in wanted:
                match = next((s for s in work["stock"] if pf.item_matches(s, v)), None)
                if match is None:
                    raise MoveError(422, f"There is no {v} stored there.")
                work["stock"].remove(match)
                taken.append(match)
                part["deliver"].append({"item": match, "to": me, "turn": turn})
            extra = ", ".join(taken)
        else:
            work["uses"] = work.get("uses", []) + [{"by": me, "name": ctx.my_name, "turn": turn}]
            extra = ""
    else:
        raise MoveError(422, "That is not something you can do with this.")
    work["request_ids"].append(rid)
    return st, _result(work, op, replay=False, extra=extra)


def _result(work: Dict[str, Any], op: str, *, replay: bool, extra: str = "") -> Dict[str, Any]:
    spec = KINDS[work["kind"]]
    line = {
        "build": f"The player spends {', '.join(work['cost'])} and leaves {spec['label']} at {work['place']}: {spec['effect']}. It is real and stays there. The items are gone.",
        "share": f"The player shows {extra} {spec['label']} at {work['place']}. {extra} now knows of it.",
        "use": (f"The player takes {extra} from the cache at {work['place']}." if spec["stores"] else f"The player makes use of {spec['label']} at {work['place']}: {spec['effect']}."),
        "replay": "Already done.",
    }[op]
    action = {"build": f"You set up {spec['label']} here.", "share": f"You show {extra} what you left here.",
              "use": "You use what was left here.", "replay": "You carry on."}[op]
    return {"kind": KIND, "op": op, "replayed": replay, "directive": f"{RESULT_MARKER}\n- {line}", "terms": [line], "id": work["id"], "action_text": action}


def narrator_context(state: Dict[str, Any], ctx: Context, result: Optional[Dict[str, Any]]) -> str:
    part = (state or {}).get(KIND) or {}
    parts: List[str] = []
    if result and result.get("kind") == KIND:
        parts.append(result["directive"])
    here_people = [p for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"]]
    lines: List[str] = []
    for w in part.get("works") or []:
        if not _at(w, ctx):
            continue
        spec = KINDS[w["kind"]]
        users = [p["name"] for p in here_people if _knows(w, p["key"], True)]
        if _knows(w, ctx.me, True):
            users.insert(0, "the player")
        if not users:
            continue
        extra = f" It holds: {', '.join(w['stock'])}." if spec["stores"] and w["stock"] else ""
        lines.append(f"At {w['place']} there is {spec['label']}: {spec['effect']}.{extra} Those here who may use it: {', '.join(users)}. "
                     f"{'It is out of sight; nobody else knows of it.' if not spec['visible'] else 'It is visible to anyone here.'}")
    if lines:
        parts.append(f"{STANDING_MARKER}\n" + "\n".join(f"- {l}" for l in lines))
    return "\n\n".join(parts)


def project_ledger(state: Dict[str, Any], ctx: Context, ledger: Dict[str, Any]) -> Dict[str, Any]:
    part = _part(state)
    now = ctx.turn
    keep_spent = []
    for s in part["spent"]:
        if s["by"] == ctx.me:
            ledger = pf.ledger_remove(ledger, s["item"])
        if now - s["turn"] < KEEP_SPENT_TURNS:
            keep_spent.append(s)
    part["spent"] = keep_spent
    left = []
    for d in part["deliver"]:
        if d["to"] == ctx.me:
            ledger = pf.ledger_add(ledger, d["item"])
        else:
            left.append(d)
    part["deliver"] = left
    return ledger


def player_view(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for w in ((state or {}).get(KIND) or {}).get("works") or []:
        spec = KINDS[w["kind"]]
        out.append({"id": w["id"], "kind": w["kind"], "label": spec["label"], "effect": spec["effect"], "place": w["place"],
                    "cost": w["cost"], "turn": w["turn"], "by": w["by_name"], "stock": w["stock"] if spec["stores"] else []})
    return out


def options(ctx: Context) -> Dict[str, Any]:
    part = (ctx.play or {}).get(KIND) or {}
    here = here_label(ctx)
    held = ctx.held()
    kinds = []
    for k, spec in KINDS.items():
        built = any(_same(w["place"], here) and w["kind"] == k for w in part.get("works") or [])
        kinds.append({"kind": k, "label": spec["label"], "effect": spec["effect"], "cost": spec["cost"], "stores": spec["stores"],
                      "can_afford": len(held) >= spec["cost"], "built_here": built})
    here_ppl = [p for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"]]
    works = []
    for w in part.get("works") or []:
        if not _at(w, ctx) or not _knows(w, ctx.me, True):
            continue
        works.append({"id": w["id"], "kind": w["kind"], "label": KINDS[w["kind"]]["label"], "stock": w["stock"] if KINDS[w["kind"]]["stores"] else [],
                      "built_by_me": w["by"] == ctx.me, "note": w["note"] if w["by"] == ctx.me else ""})
    reason = None if (here and held) or works else ("You have nothing to spend." if here else "You cannot say where you are yet.")
    return {"kind": KIND, "available": reason is None, "reason": reason, "here": here, "items": held, "kinds": kinds, "works": works,
            "people": [{"name": p["name"]} for p in here_ppl]}
