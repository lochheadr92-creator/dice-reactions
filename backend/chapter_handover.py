"""
Chapter handover: continue the same save as another established character.

The engine has no chapter-end event and no protagonist identity, so this module adds both,
as small, compatible session fields:

  character_timeline  [{from_turn, name, role, actor_id}] who the player controlled from which
                      turn. Absent on older saves; the first segment is then implied with the
                      name left unknown (an unknown fact stays unknown, it is never invented).
  controlled_character {actor_id, name, role, knows, relation, ...} the current character.
  handover            {count, boundary_turn, history[...]} one record per handover.

What a handover does, in one transaction through ``turn_commit.commit_action_turn``:
  * appends ONE engine-written turn (turn_kind "handover") that says who you are now, where you
    are, what you carry and what you know. It uses only recorded engine state and text the
    player was shown. It makes no narrator call and takes no game time.
  * re-homes the player-centric state: the former protagonist becomes an autonomous NPC row
    (exactly once, controller "engine") holding their own items, condition and position; the
    successor leaves the NPC cast, stops being driven (agenda status "player_controlled") and
    their own items, condition and injuries become the player's.
  * records, as hashes, the knowledge items the successor is not evidenced to share. From then
    on ``narrator_view`` removes them from every narrator request. The stored state keeps them.

Knowledge rule (default deny): an item the former protagonist learned stays out of the
successor's context unless the item names the successor in an explicit field (known_by,
witnesses, shared_with, told_to, learned_by) or is marked public. Prose before the handover is
never replayed to the narrator (``replay_floor``).

What the engine does not record for NPCs (items, condition, knowledge) is "unknown", never guessed.
"""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from memory import _key_for
from player_api import build_player_paragraphs

HANDOVER_TURN_KIND = "handover"
MIN_APPEARANCES = 2
MAX_KNOWS = 6
MAX_ITEMS = 12

# Narrator-maintained keys the model prunes freely and that carry the old protagonist's session.
CLEARED_ON_HANDOVER = ("objectives", "topic_ledger", "recent_beats", "recent_choice_signatures")
# Keys that hold what the protagonist learned. Items are withheld from the successor by default.
KNOWLEDGE_KEYS = (
    "clues",
    "unresolved",
    "promises",
    "relationship_threads",
    "known_rooms",
    "route_continuity",
)
# Creation surfaces that describe the former protagonist; never shown to a successor's narrator.
FORMER_CHARACTER_KEYS = ("character_hooks",)
EVIDENCE_FIELDS = ("known_by", "witnesses", "shared_with", "told_to", "learned_by")
PUBLIC_SCOPES = frozenset({"public", "common", "settlement", "faction"})
_CARRIED_RE = re.compile(
    r"\b(carried|carrying|worn|wearing|inventory|on (your |his |her |their )?person|"
    r"(in|on) (your |his |her |their )?(pack|pocket|pockets|belt|hand|hands|bag|satchel))\b",
    re.IGNORECASE,
)
_HELD_BY_RE = re.compile(r"\b(?:carried|held|worn|kept|owned)\s+by\s+(.+)$", re.IGNORECASE)


class HandoverError(Exception):
    """A handover the engine refuses. ``status`` maps to the HTTP answer."""

    def __init__(self, status: int, detail: str, code: str = "handover_refused"):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.code = code


def _norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def candidate_id(row: Mapping[str, Any]) -> str:
    """Stable id for an NPC row: its own ``npc_id`` when it has one, else a hash of the name."""
    explicit = str(row.get("npc_id") or row.get("actor_id") or "").strip()
    if explicit.startswith("npc-"):
        return explicit
    return "npc-" + hashlib.sha1(_norm(row.get("name")).encode("utf-8")).hexdigest()[:12]


def _texts(value: Any) -> List[str]:
    """Plain strings from a list of strings or dicts (text/name/event/object/item)."""
    out: List[str] = []
    for item in value if isinstance(value, list) else ([value] if value else []):
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, Mapping):
            text = ""
            for key in ("text", "event", "name", "object", "item", "label", "description"):
                if item.get(key):
                    text = str(item[key]).strip()
                    break
        else:
            text = ""
        if text:
            out.append(text)
    return out


def _fingerprint(item: Any) -> str:
    return hashlib.sha1(_key_for(item).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Who the player controls
# ---------------------------------------------------------------------------
def current_character(session: Mapping[str, Any]) -> Dict[str, Any]:
    controlled = session.get("controlled_character")
    if isinstance(controlled, Mapping) and controlled.get("name"):
        return dict(controlled)
    return {"actor_id": None, "name": None, "role": session.get("role")}


def timeline(session: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows = session.get("character_timeline")
    if isinstance(rows, list) and rows:
        return [dict(r) for r in rows if isinstance(r, Mapping)]
    return [{"from_turn": 1, "name": None, "role": session.get("role"), "actor_id": None}]


def character_for_turn(session: Mapping[str, Any], turn_number: int) -> Dict[str, Any]:
    """Who the player controlled on a turn: the last segment that began at or before it."""
    chosen = timeline(session)[0]
    for segment in timeline(session):
        if int(segment.get("from_turn") or 1) <= int(turn_number):
            chosen = segment
    return {"name": chosen.get("name"), "role": chosen.get("role"), "actor_id": chosen.get("actor_id")}


def is_handed_over(session: Mapping[str, Any]) -> bool:
    handover = session.get("handover")
    return isinstance(handover, Mapping) and int(handover.get("count") or 0) > 0


def replay_floor(session: Mapping[str, Any]) -> int:
    """First turn number whose prose may be replayed to the narrator (0 = no limit)."""
    handover = session.get("handover")
    if isinstance(handover, Mapping) and int(handover.get("count") or 0) > 0:
        return int(handover.get("boundary_turn") or 0)
    return 0


# ---------------------------------------------------------------------------
# Who can take over: only characters the player has actually met
# ---------------------------------------------------------------------------
def published_text(turn: Mapping[str, Any]) -> str:
    """The prose the player was shown for a turn (the same sanitised view the play screen gets)."""
    return " ".join(build_player_paragraphs(turn.get("paragraphs")))


def appearances(name: str, turns: Sequence[Mapping[str, Any]]) -> int:
    """In how many published turns does this name appear (whole words, case-insensitive)."""
    key = _norm(name)
    if not key:
        return 0
    pattern = re.compile(r"(?<![a-z0-9])" + re.escape(key).replace(r"\ ", r"\s+") + r"(?![a-z0-9])")
    return sum(1 for t in turns if pattern.search(_norm(published_text(t))))


def _stance_label(row: Mapping[str, Any]) -> str:
    stance = str(row.get("stance") or "").strip().lower()
    return {"ally": "an ally", "friend": "a friend", "hostile": "an enemy", "enemy": "an enemy"}.get(
        stance, "someone you have met"
    )


def _row_location(row: Mapping[str, Any], rolling: Mapping[str, Any]) -> str:
    return str(row.get("last_seen") or rolling.get("scene") or rolling.get("location") or "").strip()


def _deceased(rolling: Mapping[str, Any]) -> set:
    return {_norm(d) for d in (rolling.get("deceased") or [])}


def _is_living(row: Mapping[str, Any], rolling: Mapping[str, Any]) -> bool:
    if _norm(row.get("name")) in _deceased(rolling):
        return False
    if str(row.get("stance") or "").lower() == "dead":
        return False
    if "deceased" in str(row.get("next_move") or "").lower():
        return False
    return not (row.get("absent") is True or row.get("removed") is True)


def candidates(session: Mapping[str, Any], turns: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Successors the player may choose, plus whether the chapter can be closed at all."""
    if is_handed_over(session):
        return {"can_end_chapter": False, "reason": "already_done", "candidates": []}
    if int(session.get("turn_count") or 0) < 1:
        return {"can_end_chapter": False, "reason": "no_turns", "candidates": []}
    rolling = session.get("rolling_state") if isinstance(session.get("rolling_state"), Mapping) else {}
    current = current_character(session)
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in rolling.get("npcs") or []:
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or "").strip()
        if not name or _norm(name) in seen or _norm(name) == _norm(current.get("name")):
            continue
        seen.add(_norm(name))
        if not _is_living(row, rolling):
            continue
        count = appearances(name, turns)
        if count < MIN_APPEARANCES:
            continue
        out.append(
            {
                "id": candidate_id(row),
                "name": name,
                "relation": _stance_label(row),
                "last_seen": _row_location(row, rolling),
                "appearances": count,
            }
        )
    out.sort(key=lambda c: (-c["appearances"], c["name"]))
    reason = None if out else "nobody_qualifies"
    return {"can_end_chapter": bool(out), "reason": reason, "candidates": out}


def find_row(rolling: Mapping[str, Any], successor_id: str) -> Optional[Dict[str, Any]]:
    for row in rolling.get("npcs") or []:
        if isinstance(row, Mapping) and candidate_id(row) == successor_id:
            return dict(row)
    return None


# ---------------------------------------------------------------------------
# What the successor knows and carries (only what the engine recorded)
# ---------------------------------------------------------------------------
def _memory_row(rolling: Mapping[str, Any], name: str) -> Optional[Mapping[str, Any]]:
    for row in rolling.get("npc_memory") or []:
        if isinstance(row, Mapping) and _norm(row.get("name")) == _norm(name):
            return row
    return None


def successor_profile(rolling: Mapping[str, Any], row: Mapping[str, Any]) -> Dict[str, Any]:
    """Own identity, possessions, condition and knowledge. Missing facts stay ``None``/empty."""
    name = str(row.get("name") or "").strip()
    memory = _memory_row(rolling, name) or {}
    knows = _texts(row.get("knows")) + _texts(memory.get("remembers"))
    items = _texts(row.get("inventory"))
    return {
        "name": name,
        "actor_id": candidate_id(row),
        "role": str(row.get("role") or "").strip() or None,
        "relation": _stance_label(row),
        "location": _row_location(row, rolling) or None,
        "items": items[:MAX_ITEMS],
        "items_recorded": "inventory" in row,
        "condition": str(row.get("condition") or "").strip() or None,
        "injuries": _texts(row.get("injuries")),
        "knows": knows[:MAX_KNOWS],
        "goal": str(memory.get("goal") or "").strip() or None,
    }


def _evidenced(item: Any, name: str) -> bool:
    """True only when the item itself says the successor learned it, or it is public."""
    if not isinstance(item, Mapping):
        return False
    if item.get("public") is True or str(item.get("scope") or "").lower() in PUBLIC_SCOPES:
        return True
    key = _norm(name)
    for field in EVIDENCE_FIELDS:
        value = item.get(field)
        values = value if isinstance(value, list) else [value]
        if any(_norm(v) == key for v in values if v):
            return True
    return False


def compute_withheld(rolling: Mapping[str, Any], successor_name: str) -> List[Dict[str, str]]:
    """Hashes of knowledge items present now that the successor is not evidenced to share."""
    out: List[Dict[str, str]] = []
    for key in KNOWLEDGE_KEYS:
        value = rolling.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if not _evidenced(item, successor_name):
                out.append({"key": key, "fp": _fingerprint(item)})
    return out


def narrator_view(session: Mapping[str, Any], rolling: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """The rolling state the narrator is allowed to see. Stored state is never changed."""
    view = copy.deepcopy(dict(rolling)) if isinstance(rolling, Mapping) else {}
    handover = session.get("handover")
    if not is_handed_over(session) or not isinstance(handover, Mapping):
        return view
    for key in FORMER_CHARACTER_KEYS + ("knowledge_scope",):
        view.pop(key, None)
    blocked: Dict[str, set] = {}
    for rec in handover.get("withheld") or []:
        blocked.setdefault(str(rec.get("key")), set()).add(str(rec.get("fp")))
    for key, fingerprints in blocked.items():
        value = view.get(key)
        if isinstance(value, list):
            view[key] = [i for i in value if _fingerprint(i) not in fingerprints]
    for row in view.get("npcs") or []:
        if isinstance(row, dict):
            row.pop("knows", None)
    return view


def narrator_session(session: Mapping[str, Any]) -> Dict[str, Any]:
    """Session copy for building the narrator request: no trace of the former protagonist's setup."""
    copy_ = dict(session)
    if not is_handed_over(session):
        return copy_
    current = current_character(session)
    copy_["role"] = current.get("role") or ""
    setup = copy_.get("custom_world_setup")
    if isinstance(setup, Mapping):
        copy_["custom_world_setup"] = {
            k: v for k, v in setup.items() if k not in PROTAGONIST_SETUP_KEYS
        }
    return copy_


PROTAGONIST_SETUP_KEYS = (
    "want", "desire", "fear", "ghost", "talent", "flaw", "line", "characterKnowledge",
    "whoMatters", "role", "archetype", "startingRole", "starting_role", "name", "characterName",
)


def controlled_character_message(session: Mapping[str, Any]) -> str:
    """Authoritative identity block for the narrator, built only from the successor's own record."""
    handover = session.get("handover")
    if not is_handed_over(session) or not isinstance(handover, Mapping):
        return ""
    who = current_character(session)
    known = handover.get("baseline") or {}
    items = known.get("items") or []
    knows = known.get("knows") or []
    former = handover.get("former") or {}
    lines = [
        "[CONTROLLED_CHARACTER] From this turn the player controls "
        f"{who.get('name')}"
        + (f", {who.get('role')}" if who.get("role") else "")
        + ". Narrate only through this character's senses and knowledge.",
        "Carried: "
        + ("; ".join(items) if items else "nothing recorded. Do not assume any item beyond what the story state lists."),
    ]
    if known.get("condition"):
        lines.append(f"Condition: {known['condition']}")
    if known.get("location"):
        lines.append(f"Location: {known['location']}")
    if knows:
        lines.append("Knows: " + "; ".join(knows))
    else:
        lines.append("Knows nothing recorded beyond what has happened on screen since the handover.")
    if former.get("name"):
        lines.append(
            f"{former['name']} is now an independent character who acts on their own. "
            "Do not reveal what they learned unless this character has seen or been told it. "
            f"Story records that say 'the player' before this point mean {former['name']}, not this character."
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The handover itself (pure planning; the route commits it under the action lease)
# ---------------------------------------------------------------------------
@dataclass
class HandoverPlan:
    turn_fields: Dict[str, Any]
    update_set: Dict[str, Any]
    successor: Dict[str, Any]
    former: Dict[str, Any]


def _former_identity(session: Mapping[str, Any]) -> Dict[str, Any]:
    cur = current_character(session)
    role = str(cur.get("role") or session.get("role") or "").strip() or None
    name = str(cur.get("name") or "").strip() or None
    label = name or (f"The {role}" if role else "The earlier protagonist")
    actor_id = cur.get("actor_id") or (
        "npc-" + hashlib.sha1(f"former:{session.get('id')}:{_norm(label)}".encode("utf-8")).hexdigest()[:12]
    )
    return {"name": name, "label": label, "role": role, "actor_id": actor_id}


def _object_rows(names: Sequence[str], status: str, where: str) -> List[Dict[str, str]]:
    return [{"object": n, "status": status, "where": where} for n in names]


def _rehome_objects(rolling: Dict[str, Any], former_items: List[str], former_label: str,
                    successor_items: List[str], successor_name: str) -> None:
    from memory import _normalize_object_name

    moved = {_normalize_object_name(n) for n in former_items}
    gained = {_normalize_object_name(n) for n in successor_items}
    locations = [
        r for r in (rolling.get("object_locations") or [])
        if isinstance(r, dict) and _normalize_object_name(r.get("object")) not in moved | gained
    ]
    locations += _object_rows(former_items, "stored", f"with {former_label}")
    locations += _object_rows(successor_items, "carried", f"with {successor_name}")
    rolling["object_locations"] = locations
    rolling["inventory_objects"] = [
        {"object": n, "location_state": "carried", "where": f"with {successor_name}"}
        for n in successor_items
    ]


def _handover_paragraphs(profile: Mapping[str, Any], former: Mapping[str, Any]) -> List[str]:
    name = profile["name"]
    who = name + (f", {profile['role']}" if profile.get("role") else "")
    paras = [f"The chapter closes. From here, you are {who}."]
    paras.append(
        f"You are at {profile['location']}." if profile.get("location")
        else "You have not yet taken stock of where you stand."
    )
    paras.append(
        "You are carrying " + ", ".join(profile["items"]) + "."
        if profile.get("items")
        else "You have not yet checked what you are carrying."
    )
    if profile.get("condition"):
        paras.append(f"You are {profile['condition']}.")
    paras.append(
        "What you know: " + "; ".join(profile["knows"]) + "."
        if profile.get("knows")
        else "You know only what you have lived through yourself."
    )
    paras.append(f"{former['label']} is no longer in your hands. They act on their own now.")
    return paras


def _handover_choices(profile: Mapping[str, Any], former: Mapping[str, Any]) -> List[Dict[str, str]]:
    return [
        {"label": "A", "text": "Take stock of what you are carrying"},
        {"label": "B", "text": "Look around and take in where you are"},
        {"label": "C", "text": f"Speak with {former['label']}"},
        {"label": "D", "text": "Think through what you know and what you still need to find out"},
    ]


def plan_handover(
    session: Mapping[str, Any],
    turns: Sequence[Mapping[str, Any]],
    *,
    successor_id: str,
    request_id: str,
    now: Optional[datetime] = None,
) -> HandoverPlan:
    """Validate and build one handover. Raises HandoverError; touches nothing."""
    if is_handed_over(session):
        raise HandoverError(409, "This story already changed hands once.", "already_done")
    listing = candidates(session, turns)
    if not listing["can_end_chapter"]:
        raise HandoverError(422, "Nobody you have met can take over yet.", "nobody_qualifies")
    if successor_id not in {c["id"] for c in listing["candidates"]}:
        raise HandoverError(422, "That character cannot take over.", "ineligible_successor")
    now = now or datetime.now(timezone.utc)
    rolling = copy.deepcopy(dict(session.get("rolling_state") or {}))
    row = find_row(rolling, successor_id)
    if row is None:
        raise HandoverError(422, "That character cannot take over.", "ineligible_successor")

    profile = successor_profile(rolling, row)
    former = _former_identity(session)
    turn_number = int(session.get("turn_count") or 0) + 1
    scene = str(rolling.get("scene") or rolling.get("location") or "").strip()

    former_items = _texts(rolling.get("inventory_objects"))
    former_row: Dict[str, Any] = {
        "name": former["label"],
        "npc_id": former["actor_id"],
        "stance": "neutral",
        "last_seen": scene,
        "controller": "engine",
        "former_protagonist": True,
        "inventory": former_items,
        "condition": str(rolling.get("character") or "").strip() or None,
        "injuries": _texts(rolling.get("injuries")),
    }
    withheld = compute_withheld(rolling, profile["name"])
    former_vectors = copy.deepcopy(rolling.get("relationship_vectors") or [])

    rolling["npcs"] = [
        r for r in (rolling.get("npcs") or [])
        if not (isinstance(r, dict) and candidate_id(r) == successor_id)
    ] + [former_row]
    _rehome_objects(rolling, former_items, former["label"], profile["items"], profile["name"])
    rolling["injuries"] = list(profile["injuries"])
    rolling["character"] = profile["condition"] or "unknown"
    rolling["relationship_vectors"] = []
    for key in CLEARED_ON_HANDOVER:
        rolling[key] = []
    if profile.get("location"):
        rolling["scene"] = profile["location"]

    paragraphs = _handover_paragraphs(profile, former)
    state = {
        "Position": profile.get("location") or "Unknown",
        "Inventory Summary": ", ".join(profile["items"]) if profile["items"] else "Not yet checked",
        "Health": profile["condition"] or "Unknown",
    }
    timeline_rows = timeline(session)
    if not session.get("character_timeline"):
        timeline_rows[0].update({"name": former["name"], "role": former["role"], "actor_id": former["actor_id"]})
    timeline_rows.append(
        {"from_turn": turn_number, "name": profile["name"], "role": profile["role"], "actor_id": profile["actor_id"]}
    )
    baseline = {
        "items": profile["items"],
        "knows": profile["knows"],
        "condition": profile["condition"],
        "location": profile["location"],
    }
    handover = {
        "count": 1,
        "boundary_turn": turn_number,
        "successor_id": profile["actor_id"],
        "request_id": request_id,
        "at": now.isoformat(),
        "withheld": withheld,
        "baseline": baseline,
        "former": {"name": former["label"], "role": former["role"], "actor_id": former["actor_id"],
                   "vectors": former_vectors},
    }
    update_set: Dict[str, Any] = {
        "turn_count": turn_number,
        "last_narrative_snippet": (paragraphs[0][:180]),
        "last_state": state,
        "rolling_state": rolling,
        "rolling_state_updated_at": now,
        "updated_at": now,
        "controlled_character": {
            "actor_id": profile["actor_id"], "name": profile["name"], "role": profile["role"],
        },
        "character_timeline": timeline_rows,
        "handover": handover,
    }
    replay = copy.deepcopy(session.get("replayability_state"))
    if isinstance(replay, dict) and isinstance(replay.get("npc_agendas"), dict):
        _rehome_agendas(replay, session, profile, former)
        update_set["replayability_state"] = replay
    narrative = "\n\n".join(paragraphs)
    turn_fields = {
        "session_id": session["id"],
        "turn_number": turn_number,
        "player_action": f"End the chapter and continue as {profile['name']}",
        "narrative": narrative,
        "canonical_narrative": narrative,
        "paragraphs": paragraphs,
        "choices": _handover_choices(profile, former),
        "state": state,
        "ledger": {},
        "rolling_state": rolling,
        "turn_kind": HANDOVER_TURN_KIND,
    }
    return HandoverPlan(turn_fields, update_set, profile, former)


def _rehome_agendas(replay: Dict[str, Any], session: Mapping[str, Any],
                    profile: Mapping[str, Any], former: Mapping[str, Any]) -> None:
    """The successor stops being driven; the former protagonist gets one agenda, once."""
    import npc_agendas as agendas

    state = replay["npc_agendas"]
    active = state.setdefault("active", [])
    for agenda in active:
        if isinstance(agenda, dict) and agenda.get("npc_id") == profile["actor_id"]:
            agenda["status"] = "player_controlled"
    if not any(isinstance(a, dict) and a.get("npc_id") == former["actor_id"] for a in active):
        run_seed = str(replay.get("run_seed") or session.get("id") or "")
        active.append(
            agendas._new_agenda(
                run_seed, former["actor_id"], display_name=former["label"], role_hint=former.get("role") or ""
            )
        )
        state["active"] = active[: agendas.MAX_ACTIVE_AGENDAS]
