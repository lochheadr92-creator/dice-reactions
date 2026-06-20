"""
Consequence Echoes v1 — schedule, mature, and fire delayed echoes.

Echoes require confirmed engine-owned source events with stable event IDs.
At most one echo fires per turn.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Tuple

ECHO_DIRECTIVE_MARKER = "[REPLAYABILITY_ECHO_V1]"
MAX_SCHEDULED = 16
MAX_FIRED_LOG = 24

# v1 supported echo kinds tied to confirmed structured sources only.
ECHO_KINDS = (
    "pressure_escalation",
    "delayed_consequence",
    "relationship_fracture",
    "resource_loss",
    "alliance_shift",
    "obligation_returns",
    "retaliation",
    "alliance_request",
    "defence_cost",
    "absence_consequence",
    "faction_shift_echo",
    "hidden_cost",
    "debt_or_loyalty_echo",
)

DEFAULT_MATURE_TURNS = 2

QUALIFYING_SOURCE_KINDS = frozenset({
    "pressure_threshold_crossed",
    "delayed_consequence_fired",
    "relationship_threshold_crossed",
    "destruction_confirmed",
    "faction_hostility_shift",
    "opening_unresolved_tension",
    "npc_world_move",
})


def echo_id_for_source(source_event_id: str, kind: str) -> str:
    digest = hashlib.sha256(f"{source_event_id}:{kind}".encode("utf-8")).hexdigest()
    return f"echo-{digest[:12]}"


def init_consequence_echoes() -> Dict[str, Any]:
    return {
        "scheduled": [],
        "pending": [],
        "fired": [],
        "last_fired_turn": None,
    }


def _normalize_source_event(event: Mapping[str, Any], turn_number: int) -> Optional[Dict[str, Any]]:
    source_kind = str(event.get("source_kind") or event.get("kind") or "").strip()
    if source_kind not in QUALIFYING_SOURCE_KINDS:
        return None
    source_event_id = str(event.get("source_event_id") or event.get("event_id") or "").strip()
    if not source_event_id:
        return None
    echo_kind = str(event.get("echo_kind") or "").strip()
    if echo_kind not in ECHO_KINDS:
        echo_kind = _default_echo_kind(source_kind)
    label = str(event.get("label") or echo_kind.replace("_", " ")).strip()[:80]
    mature_in = int(event.get("mature_in") or DEFAULT_MATURE_TURNS)
    mature_in = max(1, min(6, mature_in))
    entry: Dict[str, Any] = {
        "id": echo_id_for_source(source_event_id, echo_kind),
        "kind": echo_kind,
        "label": label,
        "source_event_id": source_event_id,
        "source_kind": source_kind,
        "scheduled_turn": turn_number,
        "mature_turn": turn_number + mature_in,
    }
    provenance = event.get("source_provenance")
    if isinstance(provenance, dict):
        entry["source_provenance"] = {
            k: str(provenance[k])
            for k in ("npc_id", "agenda_id", "move_kind", "target_type", "target_id")
            if provenance.get(k)
        }
    else:
        copied: Dict[str, str] = {}
        for field in ("npc_id", "agenda_id", "move_kind", "target_type", "target_id"):
            val = event.get(field)
            if val:
                copied[field] = str(val)
        if copied:
            entry["source_provenance"] = copied
    return entry


def _default_echo_kind(source_kind: str) -> str:
    mapping = {
        "pressure_threshold_crossed": "pressure_escalation",
        "delayed_consequence_fired": "delayed_consequence",
        "relationship_threshold_crossed": "relationship_fracture",
        "destruction_confirmed": "resource_loss",
        "faction_hostility_shift": "alliance_shift",
        "opening_unresolved_tension": "pressure_escalation",
        "npc_world_move": "obligation_returns",
    }
    return mapping.get(source_kind, "pressure_escalation")


def schedule_from_structured_events(
    echo_state: Dict[str, Any],
    events: List[Mapping[str, Any]],
    turn_number: int,
    *,
    processed_source_ids: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """Append echoes from confirmed structured source events only."""
    added: List[Dict[str, Any]] = []
    scheduled = echo_state.setdefault("scheduled", [])
    existing_ids = {e.get("id") for e in scheduled if isinstance(e, dict)}
    pending_ids = {e.get("id") for e in echo_state.get("pending") or [] if isinstance(e, dict)}
    fired_ids = {e.get("id") for e in echo_state.get("fired") or [] if isinstance(e, dict)}
    seen_sources = set(processed_source_ids or ())

    for raw in events or []:
        if not isinstance(raw, dict):
            continue
        entry = _normalize_source_event(raw, turn_number)
        if not entry:
            continue
        if entry["source_event_id"] in seen_sources:
            continue
        if entry["id"] in existing_ids or entry["id"] in pending_ids or entry["id"] in fired_ids:
            seen_sources.add(entry["source_event_id"])
            continue
        scheduled.append(entry)
        existing_ids.add(entry["id"])
        seen_sources.add(entry["source_event_id"])
        added.append(entry)

    if len(scheduled) > MAX_SCHEDULED:
        echo_state["scheduled"] = scheduled[-MAX_SCHEDULED:]
    return added


def mature_echoes(echo_state: Dict[str, Any], turn_number: int) -> List[Dict[str, Any]]:
    """Move scheduled echoes whose mature_turn <= turn_number into pending."""
    matured: List[Dict[str, Any]] = []
    scheduled = echo_state.get("scheduled") or []
    pending = echo_state.setdefault("pending", [])
    pending_ids = {e.get("id") for e in pending if isinstance(e, dict)}
    remain: List[Dict[str, Any]] = []

    for entry in scheduled:
        if not isinstance(entry, dict):
            continue
        if int(entry.get("mature_turn") or 0) <= turn_number:
            if entry.get("id") not in pending_ids:
                pending.append(entry)
                pending_ids.add(entry.get("id"))
                matured.append(entry)
        else:
            remain.append(entry)

    echo_state["scheduled"] = remain
    return matured


def fire_echo(
    echo_state: Dict[str, Any],
    turn_number: int,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Fire at most one pending echo for this turn."""
    if echo_state.get("last_fired_turn") == turn_number:
        return None, False

    pending = echo_state.get("pending") or []
    if not pending:
        return None, False

    pending.sort(key=lambda e: (int(e.get("mature_turn") or 0), str(e.get("id") or "")))
    fired_entry = pending.pop(0)
    echo_state["pending"] = pending

    fired_record = {
        **fired_entry,
        "fired_turn": turn_number,
    }
    fired_log = echo_state.setdefault("fired", [])
    fired_log.append(fired_record)
    if len(fired_log) > MAX_FIRED_LOG:
        echo_state["fired"] = fired_log[-MAX_FIRED_LOG:]

    echo_state["last_fired_turn"] = turn_number
    return fired_record, True


def build_echo_directive(
    echo_state: Mapping[str, Any],
    *,
    fired_this_turn: Optional[Mapping[str, Any]] = None,
) -> str:
    """Non-persisted guidance when an echo fires."""
    fired = fired_this_turn
    if not fired:
        return ""

    if not isinstance(fired, dict):
        return ""

    kind = str(fired.get("kind") or "consequence").replace("_", " ")
    label = str(fired.get("label") or kind).strip()
    lines = [
        ECHO_DIRECTIVE_MARKER,
        "INTERNAL — consequence echo (engine guidance; surface naturally):",
        f"- Let a prior choice echo back as '{label}' ({kind}).",
        "- Tie the echo to established state; do not invent unrelated backstory.",
        "- One echo this turn — do not stack multiple unrelated delayed payoffs.",
        "- This echo is due NOW — make the consequence legible in scene.",
    ]
    return "\n".join(lines)


def copy_echo_state(state: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    return copy.deepcopy(state) if isinstance(state, dict) else init_consequence_echoes()


def processed_source_event_ids(echo_state: Mapping[str, Any]) -> set:
    ids = set()
    for bucket in ("scheduled", "pending", "fired"):
        for entry in echo_state.get(bucket) or []:
            if isinstance(entry, dict) and entry.get("source_event_id"):
                ids.add(entry["source_event_id"])
    return ids