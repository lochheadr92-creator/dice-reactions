"""Planted claims: what the player said, who heard it, who believes it, what they do about it.

The engine owns what was said and who could observe it. The narrator only describes the result.
State lives on the save (``session["claim_state"]``), never in narrator-written rolling state.

Why a directed ledger and not the ambient information items: the generic information engine
spreads items to a settlement or faction as a side effect of time. A claim told in private must
go nowhere unless a credible route exists, so it travels only along explicit edges:

* an NPC row listing the other in ``contacts``, or
* two NPCs sharing the same non-empty ``faction``.

A holder passes the claim to each contact after ``RELAY_DELAY_TURNS`` turns. Someone with a
duty to act (guard, watch, harbourmaster, constable... or ``acts_on_claims: true``) who holds a
claim that names a place the world knows will go and search it. That search is an engine event;
the narrator is told to show it as something a bystander could notice, without saying why.

The true location of anything is never written here. A claim records what was said, not what is so.
"""

from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

CLAIM_VERSION = 1
MAX_CLAIMS = 24
MAX_CLAIM_TEXT = 280
RELAY_DELAY_TURNS = 2
ACT_DELAY_TURNS = 1
DIRECTIVE_MARKER = "[CLAIM_CONSEQUENCE_V1]"
BELIEF_MARKER = "[NPC_CONVERSATION_BELIEFS_V1]"
_NS = uuid.UUID("5f0b7d4e-9d2a-4a53-9a77-3c3c0f7a1e11")
_DUTY_RE = re.compile(r"\b(harbou?r\s*master|guard|watch|constable|captain|sheriff|marshal|warden|bailiff)\b", re.I)


class ClaimError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def new_state() -> Dict[str, Any]:
    return {"version": CLAIM_VERSION, "claims": [], "beliefs": [], "relays": [], "actions": [], "last_tick_turn": 0}


def _norm(text: Any) -> str:
    raw = re.sub(r"\s+", " ", str(text or "").strip().lower())
    return re.sub(r"^(?:the|a|an)\s+", "", raw)


def npc_name(row: Any) -> str:
    return str(row.get("name") or "").strip() if isinstance(row, dict) else ""


def npc_key(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    return str(row.get("npc_id") or row.get("id") or "").strip().lower() or npc_name(row).lower()


def _alive(rolling: Dict[str, Any], row: Dict[str, Any]) -> bool:
    dead = {_norm(d) for d in rolling.get("deceased") or []}
    return _norm(npc_name(row)) not in dead and not row.get("removed") and not row.get("absent")


def _where(row: Dict[str, Any]) -> str:
    return _norm(row.get("location") or row.get("last_seen") or "")


def _scene(rolling: Dict[str, Any]) -> str:
    return _norm(rolling.get("scene") or rolling.get("location") or "")


def present_npcs(rolling: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Living NPCs standing in the player's scene (the people the player can speak to)."""
    scene = _scene(rolling)
    out = []
    for row in rolling.get("npcs") or []:
        if isinstance(row, dict) and npc_name(row) and _alive(rolling, row) and _where(row) == scene:
            out.append(row)
    return out


def find_npc(rolling: Dict[str, Any], ref: str) -> Optional[Dict[str, Any]]:
    want = _norm(ref)
    for row in rolling.get("npcs") or []:
        if isinstance(row, dict) and want and want in {_norm(npc_name(row)), npc_key(row)}:
            return row
    return None


def known_locations(rolling: Dict[str, Any]) -> List[str]:
    names: List[str] = []

    def add(value: Any) -> None:
        raw = value.get("name") if isinstance(value, dict) else value
        text = str(raw).strip() if isinstance(raw, str) else ""
        if text and _norm(text) not in {_norm(n) for n in names}:
            names.append(text)

    for key in ("known_rooms", "locations", "known_locations"):
        for value in rolling.get(key) or []:
            add(value)
    for row in rolling.get("npcs") or []:
        if isinstance(row, dict):
            add(row.get("location") or row.get("last_seen"))
    add(rolling.get("scene") or rolling.get("location"))
    return names


MAX_PLACES = 40


def _remember_places(st: Dict[str, Any], rolling: Dict[str, Any]) -> None:
    """The narrator may later prune ``known_rooms``; a place the world named stays groundable."""
    places = list(st.get("places") or [])
    for name in known_locations(rolling):
        if _norm(name) not in {_norm(p) for p in places}:
            places.append(name)
    st["places"] = places[-MAX_PLACES:]


def ground_location(text: str, rolling: Dict[str, Any], remembered: Optional[List[str]] = None) -> Optional[str]:
    """The place a claim names, if the world knows that place. Longest name wins."""
    hay = _norm(text)
    names = list(known_locations(rolling)) + [p for p in remembered or []]
    for name in sorted(names, key=lambda n: -len(n)):
        bare = _norm(name)
        if bare and re.search(rf"\b{re.escape(bare)}\b", hay):
            return name
    return None


def _contacts_of(rolling: Dict[str, Any], row: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    want = {_norm(c) for c in row.get("contacts") or []}
    faction = _norm(row.get("faction") or "")
    for other in rolling.get("npcs") or []:
        if not isinstance(other, dict) or npc_key(other) == npc_key(row) or not _alive(rolling, other):
            continue
        if _norm(npc_name(other)) in want or (faction and _norm(other.get("faction") or "") == faction):
            out.append(other)
    return out


def acts_on_claims(row: Dict[str, Any]) -> bool:
    if row.get("acts_on_claims") is False:
        return False
    return bool(row.get("acts_on_claims")) or bool(_DUTY_RE.search(f"{npc_name(row)} {row.get('role') or ''}"))


def _ref(row: Dict[str, Any]) -> Dict[str, str]:
    return {"id": npc_key(row), "name": npc_name(row)}


def record_disclosure(
    state: Optional[Dict[str, Any]], rolling: Dict[str, Any], *, turn: int, request_id: str,
    recipient_ref: str, text: str, speaker: str, aloud: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Record one telling. Idempotent on ``request_id`` so a retry never makes a second one."""
    st = copy.deepcopy(state) if isinstance(state, dict) else new_state()
    claim_id = str(uuid.uuid5(_NS, f"claim:{request_id}"))
    for existing in st["claims"]:
        if existing["id"] == claim_id:
            return st, existing
    claim_text = re.sub(r"\s+", " ", str(text or "")).strip()[:MAX_CLAIM_TEXT]
    if not claim_text:
        raise ClaimError(422, "Say what you want to tell them.")
    target = find_npc(rolling, recipient_ref)
    if target is None or not _alive(rolling, target) or _where(target) != _scene(rolling):
        raise ClaimError(422, "That person is not here to talk to.")
    _remember_places(st, rolling)
    witnesses = []
    for other in present_npcs(rolling):
        if npc_key(other) == npc_key(target):
            continue
        if aloud or other.get("within_earshot") is True:
            witnesses.append(_ref(other))
    claim = {
        "id": claim_id, "text": claim_text, "turn": turn, "request_id": request_id,
        "speaker": speaker, "recipient": _ref(target), "witnesses": witnesses,
        "aloud": bool(aloud), "location": ground_location(claim_text, rolling, st.get("places")),
    }
    st["claims"].append(claim)
    st["claims"] = st["claims"][-MAX_CLAIMS:]
    st["beliefs"].append({"claim_id": claim_id, "actor": _ref(target), "source": "told", "from": speaker, "turn": turn})
    for w in witnesses:
        st["beliefs"].append({"claim_id": claim_id, "actor": w, "source": "overheard", "from": speaker, "turn": turn})
    return st, claim


def _holds(st: Dict[str, Any], claim_id: str, actor_id: str) -> bool:
    return any(b["claim_id"] == claim_id and b["actor"]["id"] == actor_id for b in st["beliefs"])


def tick(state: Optional[Dict[str, Any]], rolling: Dict[str, Any], turn: int) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Advance relays and reactions to ``turn``. Re-running the same turn changes nothing."""
    if not isinstance(state, dict) or not state.get("claims"):
        return state, []
    st = copy.deepcopy(state)
    if int(st.get("last_tick_turn") or 0) >= turn:
        return state, []
    notes: List[str] = []
    claims = {c["id"]: c for c in st["claims"]}

    # 1. Schedule relays along credible routes for every belief that has none yet.
    scheduled = {(r["claim_id"], r["from"]["id"], r["to"]["id"]) for r in st["relays"]}
    for belief in list(st["beliefs"]):
        holder = find_npc(rolling, belief["actor"]["id"]) or find_npc(rolling, belief["actor"]["name"])
        if holder is None or not _alive(rolling, holder):
            continue
        for contact in _contacts_of(rolling, holder):
            edge = (belief["claim_id"], npc_key(holder), npc_key(contact))
            if edge in scheduled:
                continue
            scheduled.add(edge)
            st["relays"].append({
                "claim_id": belief["claim_id"], "from": _ref(holder), "to": _ref(contact),
                "due_turn": int(belief["turn"]) + RELAY_DELAY_TURNS, "status": "pending",
            })

    # 2. Deliver due relays. Both ends must still be alive; the hearer may already know it.
    for relay in st["relays"]:
        if relay["status"] != "pending" or relay["due_turn"] > turn:
            continue
        src = find_npc(rolling, relay["from"]["id"])
        dst = find_npc(rolling, relay["to"]["id"])
        if src is None or dst is None or not _alive(rolling, src) or not _alive(rolling, dst):
            relay["status"] = "dropped"
        elif _holds(st, relay["claim_id"], relay["to"]["id"]):
            relay["status"] = "already_known"
        else:
            relay["status"] = "delivered"
            relay["delivered_turn"] = turn
            st["beliefs"].append({
                "claim_id": relay["claim_id"], "actor": relay["to"], "source": "relayed",
                "from": relay["from"]["name"], "turn": turn,
            })
            notes.append(f"claim_relayed:{relay['from']['name']}>{relay['to']['name']}")

    # 3. Someone with a duty to act on a place they now believe in goes there.
    done = {(a["claim_id"], a["actor"]["id"]) for a in st["actions"]}
    for belief in st["beliefs"]:
        claim = claims.get(belief["claim_id"])
        if not claim or not claim.get("location") or (belief["claim_id"], belief["actor"]["id"]) in done:
            continue
        actor = find_npc(rolling, belief["actor"]["id"])
        if actor is None or not _alive(rolling, actor) or not acts_on_claims(actor):
            continue
        if turn < int(belief["turn"]) + ACT_DELAY_TURNS:
            continue
        done.add((belief["claim_id"], belief["actor"]["id"]))
        st["actions"].append({
            "id": str(uuid.uuid5(_NS, f"act:{belief['claim_id']}:{belief['actor']['id']}")),
            "claim_id": belief["claim_id"], "kind": "search_location", "actor": belief["actor"],
            "location": claim["location"], "turn": turn, "observed_turn": None,
        })
        notes.append(f"claim_action:{belief['actor']['name']}:search:{claim['location']}")
    st["last_tick_turn"] = turn
    return st, notes


def narrator_context(state: Optional[Dict[str, Any]], rolling: Dict[str, Any]) -> str:
    """What the people in this scene were told. Claims, not facts."""
    if not isinstance(state, dict) or not state.get("beliefs"):
        return ""
    claims = {c["id"]: c for c in state["claims"]}
    here = {npc_key(r) for r in present_npcs(rolling)}
    lines = []
    for b in state["beliefs"]:
        c = claims.get(b["claim_id"])
        if not c or b["actor"]["id"] not in here:
            continue
        how = {"told": "was told", "overheard": "overheard", "relayed": f"heard from {b['from']}"}[b["source"]]
        lines.append(f'- {b["actor"]["name"]} {how}: "{c["text"]}"')
    if not lines:
        return ""
    return (
        f"{BELIEF_MARKER}\nWhat people here have been told. These are claims, not facts. "
        "Do not confirm or deny them, and do not let anyone know more than this.\n" + "\n".join(lines)
    )


def pending_observations(state: Optional[Dict[str, Any]], turn: int) -> Tuple[str, List[str]]:
    """Directive for events the player has not yet been shown, plus their ids."""
    if not isinstance(state, dict):
        return "", []
    todo = [a for a in state.get("actions") or [] if a.get("observed_turn") is None and a["turn"] <= turn]
    if not todo:
        return "", []
    lines = [
        f"- {a['actor']['name']} and their people are searching {a['location']}. "
        "Show it as something anyone nearby could see or hear. Do not say why, and do not say who sent them."
        for a in todo
    ]
    return DIRECTIVE_MARKER + "\nThe world has moved this way:\n" + "\n".join(lines), [a["id"] for a in todo]


def mark_observed(state: Optional[Dict[str, Any]], action_ids: List[str], turn: int) -> Optional[Dict[str, Any]]:
    if not isinstance(state, dict) or not action_ids:
        return state
    st = copy.deepcopy(state)
    for a in st["actions"]:
        if a["id"] in action_ids and a.get("observed_turn") is None:
            a["observed_turn"] = turn
    return st


def player_view(state: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Only what the player said. Who believes it, who overheard it and who acted stay hidden."""
    if not isinstance(state, dict):
        return []
    return [
        {"id": c["id"], "turn": c["turn"], "to": c["recipient"]["name"], "text": c["text"]}
        for c in state.get("claims") or []
    ]
