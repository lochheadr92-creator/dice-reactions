"""
Living Cast provenance — allowlisted engine-confirmed causal sources only.

Events that evolve agendas, fire breaking points, create arc beats, or schedule
echoes must carry structured provenance. Raw narrative, player text, and
inferred prose are rejected.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional, Set

ALLOWLISTED_SOURCE_KINDS: Set[str] = frozenset({
    "npc_world_move",
    "npc_move_receipt",
    "pressure_threshold_crossed",
    "relationship_threshold_crossed",
    "living_cast_relationship_threshold",
    "delayed_consequence_fired",
    "destruction_confirmed",
    "faction_hostility_shift",
    "opening_unresolved_tension",
    "deterministic_faction_effect",
})

_REJECTED_TEXT_KEYS = frozenset({
    "narrative",
    "player_action",
    "action_text",
    "choices",
    "prose",
    "description",
    "debug",
    "raw_text",
})

_NARRATIVE_MARKERS = re.compile(
    r"\b(player said|you chose|the narrative|story text)\b",
    re.IGNORECASE,
)


def validate_provenance(source: Mapping[str, Any]) -> bool:
    """Return True when source has allowlisted kind and stable source ID."""
    if not isinstance(source, dict):
        return False
    kind = str(source.get("source_kind") or source.get("kind") or "").strip()
    if kind not in ALLOWLISTED_SOURCE_KINDS:
        return False
    source_id = str(source.get("source_event_id") or source.get("source_id") or "").strip()
    if not source_id:
        return False
    for key in _REJECTED_TEXT_KEYS:
        val = source.get(key)
        if isinstance(val, str) and val.strip():
            return False
    label = str(source.get("label") or "")
    if label and _NARRATIVE_MARKERS.search(label):
        return False
    return True


def normalize_provenance(
    source: Mapping[str, Any],
    turn_number: int,
    *,
    engine_confirmed: bool = True,
) -> Optional[Dict[str, Any]]:
    """Normalize provenance or return None when invalid."""
    if not validate_provenance(source):
        return None
    kind = str(source.get("source_kind") or source.get("kind") or "").strip()
    source_id = str(source.get("source_event_id") or source.get("source_id") or "").strip()
    out: Dict[str, Any] = {
        "source_system": "living_cast",
        "source_kind": kind,
        "source_id": source_id,
        "source_event_id": source_id,
        "source_turn": int(source.get("source_turn") or turn_number),
        "engine_confirmed": bool(engine_confirmed),
    }
    for field in ("actor_id", "target_id", "npc_id", "agenda_id"):
        val = source.get(field)
        if val:
            out[field] = str(val)
    echo_kind = source.get("echo_kind")
    if echo_kind:
        out["echo_kind"] = str(echo_kind)
    label = str(source.get("label") or "").strip()
    if label and not _NARRATIVE_MARKERS.search(label):
        out["label"] = label[:80]
    return out


def filter_provenance_sources(
    sources: list,
    turn_number: int,
) -> list:
    """Return only normalized, allowlisted sources."""
    out = []
    for raw in sources or []:
        entry = normalize_provenance(raw, turn_number)
        if entry:
            out.append(entry)
    return out