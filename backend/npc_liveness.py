"""
Actor and target liveness checks for Living Cast v1.

Death and terminal registries override agenda status, tier, memory, and scene
membership. Canonical ID alone is insufficient for move eligibility.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Set, Tuple

import npc_agendas as agendas


def _deceased_names(rolling: Mapping[str, Any]) -> Set[str]:
    return {agendas.normalize_npc_name(str(d)) for d in (rolling.get("deceased") or [])}


def _destroyed_location_names(rolling: Mapping[str, Any]) -> Set[str]:
    destroyed: Set[str] = set()
    for row in rolling.get("object_locations") or []:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").lower()
        if status not in ("destroyed", "consumed"):
            continue
        for field in ("name", "display_name", "location", "room"):
            val = str(row.get(field) or "").strip()
            if val:
                destroyed.add(agendas.normalize_npc_name(val))
    return destroyed


def is_npc_alive(display_name: str, rolling: Mapping[str, Any]) -> bool:
    key = agendas.normalize_npc_name(display_name)
    if not key:
        return False
    if key in _deceased_names(rolling):
        return False
    for row in rolling.get("npcs") or []:
        if not isinstance(row, dict):
            continue
        if agendas.normalize_npc_name(str(row.get("name", ""))) != key:
            continue
        stance = str(row.get("stance") or "").lower()
        next_move = str(row.get("next_move") or "").lower()
        if stance == "dead" or "deceased" in next_move:
            return False
        if row.get("absent") is True or row.get("removed") is True:
            return False
    return True


def is_actor_eligible(
    npc_id: str,
    agenda: Mapping[str, Any],
    rolling: Mapping[str, Any],
) -> Tuple[bool, str]:
    """Return (eligible, reason)."""
    name = str(agenda.get("display_name") or "")
    if not is_npc_alive(name, rolling):
        return False, "actor_dead_or_absent"
    if agendas.normalize_npc_name(name) in _deceased_names(rolling):
        return False, "actor_deceased_registry"
    return True, ""


def is_faction_target_valid(faction_target_id: str, rolling: Mapping[str, Any]) -> bool:
    import hashlib

    for fac in rolling.get("faction_pressure") or []:
        if not isinstance(fac, dict) or not fac.get("name"):
            continue
        name = str(fac["name"])
        norm = agendas.normalize_npc_name(name)
        digest = hashlib.sha256(f"faction:{norm}".encode("utf-8")).hexdigest()
        canonical = f"faction-{digest[:12]}"
        if canonical == faction_target_id:
            if fac.get("removed") is True or fac.get("status") == "removed":
                return False
            return True
    return False


def is_location_target_valid(location_target_id: str, rolling: Mapping[str, Any]) -> bool:
    from npc_world_moves import _location_id

    loc = _location_id(rolling)
    if not loc or loc != location_target_id:
        return False
    scene_key = agendas.normalize_npc_name(
        str(rolling.get("scene") or rolling.get("location") or "")
    )
    if scene_key and scene_key in _destroyed_location_names(rolling):
        return False
    return True


def is_pressure_target_valid(
    pressure_target_id: str,
    replayability_state: Mapping[str, Any],
) -> bool:
    for node in (replayability_state.get("pressure_graph") or {}).get("nodes") or []:
        if isinstance(node, dict) and node.get("id") == pressure_target_id:
            return node.get("status") == "active"
    return False


def is_target_valid(
    target_type: str,
    target_id: str,
    *,
    actor_npc_id: str,
    rolling: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
) -> bool:
    if target_type == "player":
        return bool(str(rolling.get("scene") or rolling.get("location") or "").strip())
    if target_type == "npc":
        if target_id == actor_npc_id:
            return False
        for row in rolling.get("npcs") or []:
            if isinstance(row, dict) and row.get("npc_id") == target_id:
                return is_npc_alive(str(row.get("name") or ""), rolling)
        return False
    if target_type == "faction":
        return is_faction_target_valid(target_id, rolling)
    if target_type == "location":
        return is_location_target_valid(target_id, rolling)
    if target_type == "pressure":
        return is_pressure_target_valid(target_id, replayability_state)
    if target_type == "opening_fact":
        opening = replayability_state.get("opening") or {}
        fact_ids = opening.get("fact_ids") or {}
        return target_id in {str(v) for v in fact_ids.values() if v}
    return False