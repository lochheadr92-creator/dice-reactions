"""
Deterministic World Event Engine.

World events are canonical engine-owned state derived from existing
simulation state. They are not random prompts and are not LLM-authored.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

WORLD_EVENT_ENGINE_VERSION = 1

MAX_WORLD_EVENTS = 12
MAX_ACTIVE_WORLD_EVENTS = 6
MAX_WORLD_EVENT_INPUTS_PER_TICK = 8
MAX_WORLD_EVENT_CHANGES_PER_TICK = 5
MAX_WORLD_EVENT_RECEIPTS = 4
MAX_WORLD_EVENT_REFS = 8
MAX_WORLD_EVENT_EVIDENCE_REFS = 8
MAX_PROJECTED_WORLD_EVENTS = 6
MAX_PROMPT_WORLD_EVENTS = 4
MAX_CONTEXT_WORLD_EVENTS = 4

CREATION_PRESSURE_THRESHOLD = 60
CREATION_SITUATION_SEVERITY = 6
CREATION_GOAL_PRIORITY = 8
DEFAULT_EXPIRY_TURNS = 18
DECAY_AFTER_INACTIVE_TURNS = 2
ARCHIVE_AFTER_TERMINAL_TURNS = 8

WORLD_EVENT_STATUSES = ("forming", "active", "resolving", "resolved", "failed", "archived")
TERMINAL_STATUSES = frozenset({"resolved", "failed", "archived"})

WORLD_EVENT_RECEIPT_TYPES = (
    "world_event_created",
    "world_event_reinforced",
    "world_event_merged",
    "world_event_progressed",
    "world_event_resolved",
    "world_event_failed",
    "world_event_archived",
)

WORLD_EVENT_TYPES = frozenset(
    {
        "resource_shortage",
        "trade_disruption",
        "investigation",
        "search_operation",
        "disease_outbreak",
        "infrastructure_failure",
        "settlement_recovery",
        "bandit_activity",
        "political_unrest",
        "migration",
        "military_mobilisation",
        "construction",
        "fire",
        "flood",
        "crop_failure",
        "guard_patrol",
        "refugee_movement",
        "wildlife_migration",
        "environmental_hazard",
    }
)

EVENT_TITLES = {
    "resource_shortage": "Resource Shortage",
    "trade_disruption": "Trade Disruption",
    "investigation": "Investigation",
    "search_operation": "Search Operation",
    "disease_outbreak": "Disease Outbreak",
    "infrastructure_failure": "Infrastructure Failure",
    "settlement_recovery": "Settlement Recovery",
    "bandit_activity": "Bandit Activity",
    "political_unrest": "Political Unrest",
    "migration": "Migration",
    "military_mobilisation": "Military Mobilisation",
    "construction": "Construction",
    "fire": "Fire",
    "flood": "Flood",
    "crop_failure": "Crop Failure",
    "guard_patrol": "Guard Patrol",
    "refugee_movement": "Refugee Movement",
    "wildlife_migration": "Wildlife Migration",
    "environmental_hazard": "Environmental Hazard",
}

PRESSURE_KIND_GROUPS = {
    "danger": "danger",
    "environmental": "environmental",
    "environmental_threat": "environmental",
    "pursuit": "danger",
    "injury_or_fatigue": "danger",
    "resource": "scarcity",
    "resource_pressure": "scarcity",
    "scarcity": "scarcity",
    "social": "conflict",
    "social_tension": "conflict",
    "conflict": "conflict",
    "suspicion": "unknown",
    "opportunity": "opportunity",
    "unresolved_thread": "unknown",
    "unknown": "unknown",
}

PRESSURE_GROUP_TO_EVENT_TYPE = {
    "danger": "bandit_activity",
    "environmental": "environmental_hazard",
    "scarcity": "resource_shortage",
    "conflict": "political_unrest",
    "opportunity": "trade_disruption",
    "unknown": "investigation",
}

SITUATION_TYPE_TO_EVENT_TYPE = {
    "murder_investigation": "investigation",
    "food_shortage": "resource_shortage",
    "gang_turf_war": "bandit_activity",
    "disease_outbreak": "disease_outbreak",
    "political_unrest": "political_unrest",
    "search_party": "search_operation",
    "flood_recovery": "settlement_recovery",
    "missing_child": "search_operation",
    "trade_opportunity": "trade_disruption",
}

GOAL_TYPE_TO_EVENT_TYPE = {
    "secure_food": "resource_shortage",
    "rescue_missing_person": "search_operation",
    "investigate_murder": "investigation",
    "stabilize_settlement": "settlement_recovery",
    "repair_route": "infrastructure_failure",
    "negotiate_peace": "political_unrest",
    "defend_area": "guard_patrol",
    "reduce_threat": "bandit_activity",
}

ACTION_TYPE_TO_EVENT_TYPE = {
    "gather": "resource_shortage",
    "search": "search_operation",
    "investigate": "investigation",
    "repair": "infrastructure_failure",
    "warn": "guard_patrol",
    "defend": "guard_patrol",
    "negotiate": "political_unrest",
    "travel": "migration",
    "retreat": "refugee_movement",
}

EVENT_TYPE_TO_ENGINE_KIND = {
    "resource_shortage": "supplies_exhausted",
    "trade_disruption": "price_increase",
    "investigation": "strange_evidence",
    "search_operation": "unexplained_disappearance",
    "disease_outbreak": "disease",
    "infrastructure_failure": "collapse",
    "settlement_recovery": "trader_arrival",
    "bandit_activity": "raid",
    "political_unrest": "protest",
    "migration": "evacuation",
    "military_mobilisation": "retaliation",
    "construction": "resource_discovery",
    "fire": "fire",
    "flood": "collapse",
    "crop_failure": "supplies_exhausted",
    "guard_patrol": "npc_warned_settlement",
    "refugee_movement": "evacuation",
    "wildlife_migration": "accident",
    "environmental_hazard": "accident",
}


def _stable_id(prefix: str, *parts: Any) -> str:
    material = ":".join(str(part or "") for part in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:12]}"


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp_int(value: Any, low: int, high: int, default: int = 0) -> int:
    return max(low, min(high, _coerce_int(value, default)))


def _bounded_str(value: Any, limit: int = 120) -> str:
    return str(value or "").strip()[:limit]


def _bounded_str_list(values: Any, limit: int = MAX_WORLD_EVENT_REFS) -> List[str]:
    out: List[str] = []
    raw = values if isinstance(values, (list, tuple, set)) else [values]
    for value in raw or []:
        text = _bounded_str(value)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _merge_unique(existing: Dict[str, Any], incoming: Mapping[str, Any], key: str, limit: int) -> bool:
    before = list(existing.get(key) or [])
    merged = _bounded_str_list(before + list(incoming.get(key) or []), limit)
    existing[key] = merged
    return merged != before


def _normalise_event_type(value: Any) -> str:
    event_type = _bounded_str(value, 80).lower()
    return event_type if event_type in WORLD_EVENT_TYPES else "investigation"


def _normalise_status(value: Any, severity: int = 0) -> str:
    status = _bounded_str(value, 40).lower()
    if status in WORLD_EVENT_STATUSES:
        return status
    return "active" if severity >= 4 else "forming"


def _world_event_id(run_seed: str, dedupe_key: str) -> str:
    return _stable_id("world-event", run_seed, dedupe_key)


def _world_event_id_for_generation(run_seed: str, dedupe_key: str, generation: int) -> str:
    if generation <= 0:
        return _world_event_id(run_seed, dedupe_key)
    return _stable_id("world-event", run_seed, dedupe_key, "recreated", generation)


def _assign_unique_world_event_id(
    candidate: Dict[str, Any],
    world_events: Sequence[Mapping[str, Any]],
    run_seed: str,
) -> int:
    dedupe = _bounded_str(candidate.get("dedupe_key"), 180)
    if not dedupe:
        return 0
    existing_ids = {
        str(row.get("world_event_id") or "")
        for row in world_events
        if isinstance(row, Mapping) and row.get("world_event_id")
    }
    generation = 0
    while True:
        event_id = _world_event_id_for_generation(run_seed, dedupe, generation)
        if event_id not in existing_ids:
            candidate["world_event_id"] = event_id
            return generation
        generation += 1


def _default_title(event_type: str) -> str:
    return EVENT_TITLES.get(event_type, event_type.replace("_", " ").title())


def _scope_key(
    *,
    event_type: str,
    locations: Sequence[str],
    regions: Sequence[str],
    factions: Sequence[str],
    actors: Sequence[str],
    fallback: str,
) -> str:
    if locations:
        return f"{event_type}:location:{locations[0]}"
    if regions:
        return f"{event_type}:region:{regions[0]}"
    if factions:
        return f"{event_type}:faction:{factions[0]}"
    if actors:
        return f"{event_type}:actor:{actors[0]}"
    return f"{event_type}:global:{fallback}"


def _normalise_world_event(row: Mapping[str, Any], *, run_seed: str = "") -> Dict[str, Any]:
    event_type = _normalise_event_type(row.get("event_type"))
    locations = _bounded_str_list(row.get("affected_locations"), MAX_WORLD_EVENT_REFS)
    regions = _bounded_str_list(row.get("affected_regions"), MAX_WORLD_EVENT_REFS)
    factions = _bounded_str_list(row.get("affected_factions"), MAX_WORLD_EVENT_REFS)
    actors = _bounded_str_list(row.get("affected_actor_ids"), MAX_WORLD_EVENT_REFS)
    dedupe_key = _bounded_str(
        row.get("dedupe_key")
        or _scope_key(
            event_type=event_type,
            locations=locations,
            regions=regions,
            factions=factions,
            actors=actors,
            fallback=event_type,
        ),
        180,
    )
    created_turn = max(0, _coerce_int(row.get("created_turn"), 0))
    updated_turn = max(created_turn, _coerce_int(row.get("updated_turn"), created_turn))
    severity = _clamp_int(row.get("severity"), 0, 10, default=1)
    out = {
        "world_event_id": _bounded_str(
            row.get("world_event_id") or _world_event_id(run_seed or "world-event", dedupe_key),
            160,
        ),
        "event_type": event_type,
        "title": _bounded_str(row.get("title") or _default_title(event_type), 120),
        "severity": severity,
        "status": _normalise_status(row.get("status"), severity),
        "progress": _clamp_int(row.get("progress"), 0, 100, default=0),
        "created_turn": created_turn,
        "updated_turn": updated_turn,
        "originating_pressure_ids": _bounded_str_list(row.get("originating_pressure_ids"), MAX_WORLD_EVENT_REFS),
        "originating_situation_ids": _bounded_str_list(row.get("originating_situation_ids"), MAX_WORLD_EVENT_REFS),
        "originating_goal_ids": _bounded_str_list(row.get("originating_goal_ids"), MAX_WORLD_EVENT_REFS),
        "originating_action_ids": _bounded_str_list(row.get("originating_action_ids"), MAX_WORLD_EVENT_REFS),
        "affected_locations": locations,
        "affected_regions": regions,
        "affected_factions": factions,
        "affected_actor_ids": actors,
        "evidence_refs": _bounded_str_list(row.get("evidence_refs"), MAX_WORLD_EVENT_EVIDENCE_REFS),
        "expiry": max(updated_turn, _coerce_int(row.get("expiry"), created_turn + DEFAULT_EXPIRY_TURNS)),
        "source_event_ids": _bounded_str_list(row.get("source_event_ids"), MAX_WORLD_EVENT_REFS),
        "dedupe_key": dedupe_key,
        "last_reinforced_turn": _coerce_int(row.get("last_reinforced_turn"), updated_turn),
        "last_evolved_turn": row.get("last_evolved_turn"),
        "inactive_turns": max(0, _coerce_int(row.get("inactive_turns"), 0)),
        "archived_turn": row.get("archived_turn"),
    }
    if out["status"] in TERMINAL_STATUSES:
        out["severity"] = min(out["severity"], 3)
    return out


def _world_event_summary(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key: row.get(key)
        for key in ("status", "severity", "progress")
        if row.get(key) is not None
    }


def _summary_change(before: Mapping[str, Any], after: Mapping[str, Any]) -> Dict[str, List[Any]]:
    change: Dict[str, List[Any]] = {}
    for key in sorted(set(before) | set(after)):
        before_value = before.get(key)
        after_value = after.get(key)
        if before_value != after_value:
            change[key] = [before_value, after_value]
    return change


def _receipt_id(
    receipt_type: str,
    *,
    turn_number: int,
    world_event_id: str,
    detail: str = "",
    source_event_ids: Optional[Sequence[str]] = None,
) -> str:
    sources = ",".join(sorted(_bounded_str_list(source_event_ids or [], MAX_WORLD_EVENT_REFS)))
    return _stable_id("world-event-receipt", receipt_type, turn_number, world_event_id, detail, sources)


def _append_receipt(
    replayability_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    receipt_type: str,
    turn_number: int,
    world_event: Mapping[str, Any],
    before: Optional[Mapping[str, Any]] = None,
    after: Optional[Mapping[str, Any]] = None,
    detail: str = "",
    source_event_ids: Optional[Sequence[str]] = None,
) -> bool:
    if receipt_type not in WORLD_EVENT_RECEIPT_TYPES:
        return False
    world_event_id = _bounded_str(world_event.get("world_event_id"), 160)
    if not world_event_id:
        return False
    rid = _receipt_id(
        receipt_type,
        turn_number=turn_number,
        world_event_id=world_event_id,
        detail=detail,
        source_event_ids=source_event_ids,
    )
    receipts = replayability_state.setdefault("world_event_receipts", [])
    if any(isinstance(row, Mapping) and row.get("receipt_id") == rid for row in receipts):
        return False
    receipt: Dict[str, Any] = {
        "version": WORLD_EVENT_ENGINE_VERSION,
        "receipt_id": rid,
        "receipt_type": receipt_type,
        "turn": turn_number,
        "world_event_id": world_event_id,
        "event_type": world_event.get("event_type"),
        "status": world_event.get("status"),
        "detail": _bounded_str(detail, 160),
        "change": _summary_change(
            _world_event_summary(before or {}),
            _world_event_summary(after or world_event),
        ),
    }
    source_ids = _bounded_str_list(source_event_ids or world_event.get("source_event_ids"), MAX_WORLD_EVENT_REFS)
    if source_ids:
        receipt["source_event_ids"] = source_ids
    receipts.append(receipt)
    if len(receipts) > MAX_WORLD_EVENT_RECEIPTS:
        replayability_state["world_event_receipts"] = receipts[-MAX_WORLD_EVENT_RECEIPTS:]
    local_receipts.append(receipt)
    return True


def _engine_event_id(run_seed: str, world_event: Mapping[str, Any], receipt_type: str, turn_number: int) -> str:
    return _stable_id(
        "evt-world",
        run_seed,
        world_event.get("world_event_id"),
        world_event.get("event_type"),
        receipt_type,
        turn_number,
    )


def _engine_event_from_world_event(
    world_event: Mapping[str, Any],
    *,
    run_seed: str,
    turn_number: int,
    receipt_type: str,
) -> Dict[str, Any]:
    event_type = _normalise_event_type(world_event.get("event_type"))
    event_kind = EVENT_TYPE_TO_ENGINE_KIND.get(event_type, "strange_evidence")
    return {
        "event_id": _engine_event_id(run_seed, world_event, receipt_type, turn_number),
        "event_type": "world_event",
        "event_kind": event_kind,
        "pressure_event_kind": event_kind,
        "world_event_id": _bounded_str(world_event.get("world_event_id"), 160),
        "world_event_type": event_type,
        "world_event_status": _bounded_str(world_event.get("status"), 40),
        "turn": turn_number,
        "magnitude": _clamp_int(world_event.get("severity"), 0, 10) * 10,
        "actor_ids": _bounded_str_list(world_event.get("affected_actor_ids"), MAX_WORLD_EVENT_REFS),
        "location_ids": _bounded_str_list(world_event.get("affected_locations"), MAX_WORLD_EVENT_REFS),
        "region_ids": _bounded_str_list(world_event.get("affected_regions"), MAX_WORLD_EVENT_REFS),
        "faction_ids": _bounded_str_list(world_event.get("affected_factions"), MAX_WORLD_EVENT_REFS),
        "tags": _bounded_str_list(["world_event", event_type, receipt_type], 8),
        "source_event_ids": _bounded_str_list(world_event.get("source_event_ids"), MAX_WORLD_EVENT_REFS),
        "originating_pressure_ids": _bounded_str_list(world_event.get("originating_pressure_ids"), MAX_WORLD_EVENT_REFS),
        "originating_situation_ids": _bounded_str_list(world_event.get("originating_situation_ids"), MAX_WORLD_EVENT_REFS),
        "originating_goal_ids": _bounded_str_list(world_event.get("originating_goal_ids"), MAX_WORLD_EVENT_REFS),
        "originating_action_ids": _bounded_str_list(world_event.get("originating_action_ids"), MAX_WORLD_EVENT_REFS),
    }


def _pressure_group(kind: Any) -> str:
    return PRESSURE_KIND_GROUPS.get(str(kind or "").strip().lower(), "unknown")


def _refs_from_pressure(node: Mapping[str, Any]) -> Tuple[List[str], List[str], List[str], List[str]]:
    return (
        _bounded_str_list(node.get("actor_ids") or node.get("linked_actor_ids"), MAX_WORLD_EVENT_REFS),
        _bounded_str_list(
            list(node.get("location_ids") or [])
            + list(node.get("linked_location_ids") or []),
            MAX_WORLD_EVENT_REFS,
        ),
        _bounded_str_list(
            list(node.get("region_ids") or [])
            + list(node.get("linked_region_ids") or []),
            MAX_WORLD_EVENT_REFS,
        ),
        _bounded_str_list(node.get("faction_ids") or node.get("linked_faction_ids"), MAX_WORLD_EVENT_REFS),
    )


def _candidate_from_pressure(node: Mapping[str, Any], *, turn_number: int, run_seed: str) -> Optional[Dict[str, Any]]:
    if str(node.get("origin_type") or "") == "world_event":
        return None
    if str(node.get("status") or "") != "active":
        return None
    magnitude = _clamp_int(node.get("magnitude"), 0, 100)
    trend = _coerce_int(node.get("trend"), 0)
    if magnitude < CREATION_PRESSURE_THRESHOLD and trend <= 0:
        return None
    pressure_id = _bounded_str(node.get("id"), 160)
    if not pressure_id:
        return None
    event_type = PRESSURE_GROUP_TO_EVENT_TYPE.get(_pressure_group(node.get("kind")), "investigation")
    actors, locations, regions, factions = _refs_from_pressure(node)
    dedupe_key = _scope_key(
        event_type=event_type,
        locations=locations,
        regions=regions,
        factions=factions,
        actors=actors,
        fallback=_pressure_group(node.get("kind")) or pressure_id,
    )
    severity = max(3, min(10, round(magnitude / 10)))
    return _normalise_world_event(
        {
            "world_event_id": _world_event_id(run_seed, dedupe_key),
            "event_type": event_type,
            "title": _default_title(event_type),
            "severity": severity,
            "status": "active" if severity >= 4 else "forming",
            "progress": 0,
            "created_turn": turn_number,
            "updated_turn": turn_number,
            "originating_pressure_ids": [pressure_id],
            "affected_locations": locations,
            "affected_regions": regions,
            "affected_factions": factions,
            "affected_actor_ids": actors,
            "evidence_refs": list(node.get("evidence_refs") or []) + [f"pressure:{pressure_id}"],
            "expiry": turn_number + DEFAULT_EXPIRY_TURNS,
            "source_event_ids": [pressure_id],
            "dedupe_key": dedupe_key,
            "last_reinforced_turn": turn_number,
            "inactive_turns": 0,
        },
        run_seed=run_seed,
    )


def _candidate_from_situation(situation: Mapping[str, Any], *, turn_number: int, run_seed: str) -> Optional[Dict[str, Any]]:
    if str(situation.get("status") or "") in TERMINAL_STATUSES:
        return None
    if _bounded_str_list(situation.get("originating_world_event_ids"), MAX_WORLD_EVENT_REFS):
        return None
    if any(str(source).startswith("evt-world") for source in situation.get("source_event_ids") or []):
        return None
    severity = _clamp_int(situation.get("severity"), 0, 10)
    if severity < CREATION_SITUATION_SEVERITY:
        return None
    situation_id = _bounded_str(situation.get("situation_id"), 160)
    if not situation_id:
        return None
    event_type = SITUATION_TYPE_TO_EVENT_TYPE.get(str(situation.get("type") or ""), "investigation")
    locations = _bounded_str_list(situation.get("involved_locations"), MAX_WORLD_EVENT_REFS)
    factions = _bounded_str_list(situation.get("involved_factions"), MAX_WORLD_EVENT_REFS)
    actors = _bounded_str_list(situation.get("involved_actor_ids"), MAX_WORLD_EVENT_REFS)
    if not (locations or factions or actors):
        return None
    dedupe_key = _scope_key(
        event_type=event_type,
        locations=locations,
        regions=[],
        factions=factions,
        actors=actors,
        fallback=situation_id,
    )
    return _normalise_world_event(
        {
            "world_event_id": _world_event_id(run_seed, dedupe_key),
            "event_type": event_type,
            "title": _default_title(event_type),
            "severity": severity,
            "status": "active",
            "progress": max(0, min(40, _clamp_int(situation.get("progress"), 0, 100) // 3)),
            "created_turn": turn_number,
            "updated_turn": turn_number,
            "originating_pressure_ids": list(situation.get("originating_pressure_ids") or []),
            "originating_situation_ids": [situation_id],
            "affected_locations": locations,
            "affected_factions": factions,
            "affected_actor_ids": actors,
            "evidence_refs": list(situation.get("evidence_refs") or []) + [f"situation:{situation_id}"],
            "expiry": turn_number + DEFAULT_EXPIRY_TURNS,
            "source_event_ids": [situation_id],
            "dedupe_key": dedupe_key,
            "last_reinforced_turn": turn_number,
            "inactive_turns": 0,
        },
        run_seed=run_seed,
    )


def _candidate_from_goal(goal: Mapping[str, Any], *, turn_number: int, run_seed: str) -> Optional[Dict[str, Any]]:
    if str(goal.get("status") or "") in {"completed", "failed", "abandoned"}:
        return None
    priority = _clamp_int(goal.get("priority"), 0, 10)
    status = str(goal.get("status") or "")
    if priority < CREATION_GOAL_PRIORITY and status != "blocked":
        return None
    goal_id = _bounded_str(goal.get("goal_id"), 160)
    if not goal_id:
        return None
    goal_type = str(goal.get("goal_type") or "")
    event_type = GOAL_TYPE_TO_EVENT_TYPE.get(goal_type, "search_operation")
    if status == "blocked" and goal.get("required_resources"):
        event_type = "resource_shortage"
    locations = _bounded_str_list(goal.get("target_location_ids"), MAX_WORLD_EVENT_REFS)
    factions = _bounded_str_list([goal.get("owner_id")] if goal.get("owner_type") == "faction" else [], MAX_WORLD_EVENT_REFS)
    actors = _bounded_str_list(goal.get("target_actor_ids"), MAX_WORLD_EVENT_REFS)
    dedupe_key = _scope_key(
        event_type=event_type,
        locations=locations,
        regions=[],
        factions=factions,
        actors=actors,
        fallback=goal_id,
    )
    return _normalise_world_event(
        {
            "world_event_id": _world_event_id(run_seed, dedupe_key),
            "event_type": event_type,
            "title": _default_title(event_type),
            "severity": max(3, priority),
            "status": "active",
            "progress": 0,
            "created_turn": turn_number,
            "updated_turn": turn_number,
            "originating_pressure_ids": list(goal.get("supporting_pressure_ids") or []),
            "originating_situation_ids": list(goal.get("parent_situation_ids") or []),
            "originating_goal_ids": [goal_id],
            "affected_locations": locations,
            "affected_factions": factions,
            "affected_actor_ids": actors,
            "evidence_refs": list(goal.get("evidence_refs") or []) + [f"goal:{goal_id}"],
            "expiry": turn_number + DEFAULT_EXPIRY_TURNS,
            "source_event_ids": [goal_id],
            "dedupe_key": dedupe_key,
            "last_reinforced_turn": turn_number,
            "inactive_turns": 0,
        },
        run_seed=run_seed,
    )


def _candidate_from_action(action: Mapping[str, Any], *, turn_number: int, run_seed: str) -> Optional[Dict[str, Any]]:
    if str(action.get("status") or "") not in {"resolved", "completed", "failed"}:
        return None
    action_id = _bounded_str(action.get("action_id"), 160)
    if not action_id:
        return None
    action_type = str(action.get("action_type") or "")
    event_type = ACTION_TYPE_TO_EVENT_TYPE.get(action_type)
    if not event_type:
        return None
    priority = _clamp_int(action.get("priority"), 0, 10, default=5)
    locations = _bounded_str_list([action.get("target_location"), action.get("destination")], MAX_WORLD_EVENT_REFS)
    actors = _bounded_str_list([action.get("actor_id")], MAX_WORLD_EVENT_REFS)
    dedupe_key = _scope_key(
        event_type=event_type,
        locations=locations,
        regions=[],
        factions=[],
        actors=actors,
        fallback=action_id,
    )
    return _normalise_world_event(
        {
            "world_event_id": _world_event_id(run_seed, dedupe_key),
            "event_type": event_type,
            "title": _default_title(event_type),
            "severity": max(3, priority),
            "status": "active",
            "progress": 0,
            "created_turn": turn_number,
            "updated_turn": turn_number,
            "originating_situation_ids": [action.get("situation_id")] if action.get("situation_id") else [],
            "originating_goal_ids": [action.get("goal_id")] if action.get("goal_id") else [],
            "originating_action_ids": [action_id],
            "affected_locations": locations,
            "affected_actor_ids": actors,
            "evidence_refs": [f"npc_action:{action_id}"],
            "expiry": turn_number + DEFAULT_EXPIRY_TURNS,
            "source_event_ids": [action_id],
            "dedupe_key": dedupe_key,
            "last_reinforced_turn": turn_number,
            "inactive_turns": 0,
        },
        run_seed=run_seed,
    )


def _rolling_candidates(rolling_state: Mapping[str, Any], *, turn_number: int, run_seed: str) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    def conditions_from(row: Mapping[str, Any]) -> set:
        return {str(value).lower() for value in _bounded_str_list(row.get("conditions"), 12)}

    def row_from_world_event(row: Mapping[str, Any]) -> bool:
        return any(str(source).startswith("evt-world") for source in row.get("source_event_ids") or [])

    def add(event_type: str, row_id: str, *, location: str = "", faction: str = "", actor: str = "", severity: int = 4, evidence: str = "") -> None:
        if not row_id:
            return
        locations = [location] if location else []
        factions = [faction] if faction else []
        actors = [actor] if actor else []
        dedupe = _scope_key(
            event_type=event_type,
            locations=locations,
            regions=[],
            factions=factions,
            actors=actors,
            fallback=row_id,
        )
        candidates.append(
            _normalise_world_event(
                {
                    "world_event_id": _world_event_id(run_seed, dedupe),
                    "event_type": event_type,
                    "title": _default_title(event_type),
                    "severity": severity,
                    "status": "active",
                    "progress": 0,
                    "created_turn": turn_number,
                    "updated_turn": turn_number,
                    "affected_locations": locations,
                    "affected_factions": factions,
                    "affected_actor_ids": actors,
                    "evidence_refs": [evidence or f"world_state:{row_id}"],
                    "expiry": turn_number + DEFAULT_EXPIRY_TURNS,
                    "source_event_ids": [row_id],
                    "dedupe_key": dedupe,
                    "last_reinforced_turn": turn_number,
                    "inactive_turns": 0,
                },
                run_seed=run_seed,
            )
        )

    for row in rolling_state.get("world_resources") or []:
        if not isinstance(row, Mapping):
            continue
        if row_from_world_event(row):
            continue
        status = str(row.get("status") or "").lower()
        trend = str(row.get("trend") or "").lower()
        delta = _coerce_int(row.get("quantity_delta"), 0)
        if status in {"shortage", "reduced", "exhausted"} or trend == "decreasing" or delta < 0:
            add(
                "resource_shortage",
                _bounded_str(row.get("id") or row.get("name")),
                location=_bounded_str(row.get("location_id")),
                severity=max(4, min(8, 4 + abs(delta))),
            )

    for row in rolling_state.get("market_state") or []:
        if not isinstance(row, Mapping):
            continue
        if row_from_world_event(row):
            continue
        conditions = conditions_from(row)
        if str(row.get("status") or "").lower() in {"strained", "blocked"} or "prices_rising" in conditions:
            add("trade_disruption", _bounded_str(row.get("id")), location=_bounded_str(row.get("location_id")), severity=5)

    for row in rolling_state.get("infrastructure_state") or []:
        if not isinstance(row, Mapping):
            continue
        if row_from_world_event(row):
            continue
        conditions = conditions_from(row)
        if str(row.get("status") or "").lower() in {"damaged", "blocked", "collapsed"} or conditions.intersection({"damaged", "blocked", "collapse"}):
            add("infrastructure_failure", _bounded_str(row.get("id")), location=_bounded_str(row.get("location_id")), severity=6)

    for row in rolling_state.get("travel_routes") or []:
        if not isinstance(row, Mapping):
            continue
        if row_from_world_event(row):
            continue
        conditions = conditions_from(row)
        if str(row.get("status") or "").lower() in {"blocked", "unsafe"} or conditions.intersection({"blocked", "unsafe", "damaged"}):
            add("trade_disruption", _bounded_str(row.get("id")), location=_bounded_str(row.get("location_id")), severity=5)

    for row in rolling_state.get("settlement_conditions") or []:
        if not isinstance(row, Mapping):
            continue
        if row_from_world_event(row):
            continue
        status = str(row.get("status") or "").lower()
        conditions = conditions_from(row)
        if status in {"recovering", "improving"}:
            add("settlement_recovery", _bounded_str(row.get("id")), location=_bounded_str(row.get("location_id")), severity=4)
        elif status in {"unstable", "strained"} or conditions.intersection({"protest", "argument", "alliance_fracture"}):
            add("political_unrest", _bounded_str(row.get("id")), location=_bounded_str(row.get("location_id")), severity=5)
        elif "disease" in conditions:
            add("disease_outbreak", _bounded_str(row.get("id")), location=_bounded_str(row.get("location_id")), severity=6)

    for row in rolling_state.get("actor_location_registry") or []:
        if not isinstance(row, Mapping):
            continue
        if row_from_world_event(row):
            continue
        status = str(row.get("status") or "").lower()
        if status == "missing":
            add("search_operation", _bounded_str(row.get("id")), location=_bounded_str(row.get("location_id")), actor=_bounded_str(row.get("id")), severity=5)
        elif status == "relocated":
            add("refugee_movement", _bounded_str(row.get("id")), location=_bounded_str(row.get("location_id")), actor=_bounded_str(row.get("id")), severity=4)

    for row in rolling_state.get("faction_pressure") or []:
        if not isinstance(row, Mapping):
            continue
        if row_from_world_event(row):
            continue
        ticks = row.get("ticks") if isinstance(row.get("ticks"), Mapping) else {}
        total = sum(abs(_coerce_int(v, 0)) for v in ticks.values()) if isinstance(ticks, Mapping) else 0
        if total >= 3:
            add("political_unrest", _bounded_str(row.get("id") or row.get("name")), faction=_bounded_str(row.get("id") or row.get("name")), severity=min(8, 3 + total))

    return candidates


def _collect_candidates(
    replayability_state: Mapping[str, Any],
    rolling_state: Mapping[str, Any],
    *,
    turn_number: int,
    run_seed: str,
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    graph = replayability_state.get("pressure_graph") if isinstance(replayability_state.get("pressure_graph"), Mapping) else {}
    pressure_nodes = [node for node in graph.get("nodes") or [] if isinstance(node, Mapping)]
    pressure_nodes.sort(key=lambda node: (-_clamp_int(node.get("magnitude"), 0, 100), str(node.get("id") or "")))
    for node in pressure_nodes:
        candidate = _candidate_from_pressure(node, turn_number=turn_number, run_seed=run_seed)
        if candidate:
            candidates.append(candidate)
        if len(candidates) >= MAX_WORLD_EVENT_INPUTS_PER_TICK:
            return candidates

    situations = [row for row in replayability_state.get("situations") or [] if isinstance(row, Mapping)]
    situations.sort(key=lambda row: (-_clamp_int(row.get("severity"), 0, 10), str(row.get("situation_id") or "")))
    for situation in situations:
        candidate = _candidate_from_situation(situation, turn_number=turn_number, run_seed=run_seed)
        if candidate:
            candidates.append(candidate)
        if len(candidates) >= MAX_WORLD_EVENT_INPUTS_PER_TICK:
            return candidates

    situations_by_id = {
        str(row.get("situation_id") or ""): row
        for row in replayability_state.get("situations") or []
        if isinstance(row, Mapping) and row.get("situation_id")
    }
    goals = [row for row in replayability_state.get("goals") or [] if isinstance(row, Mapping)]
    goals.sort(key=lambda row: (-_clamp_int(row.get("priority"), 0, 10), str(row.get("goal_id") or "")))
    for goal in goals:
        parent_ids = _bounded_str_list(goal.get("parent_situation_ids"), MAX_WORLD_EVENT_REFS)
        if any(
            _bounded_str_list((situations_by_id.get(parent_id) or {}).get("originating_world_event_ids"), MAX_WORLD_EVENT_REFS)
            for parent_id in parent_ids
        ):
            continue
        candidate = _candidate_from_goal(goal, turn_number=turn_number, run_seed=run_seed)
        if candidate:
            candidates.append(candidate)
        if len(candidates) >= MAX_WORLD_EVENT_INPUTS_PER_TICK:
            return candidates

    actions = [row for row in replayability_state.get("npc_actions") or [] if isinstance(row, Mapping)]
    actions.sort(key=lambda row: (-_coerce_int(row.get("resolved_turn"), 0), str(row.get("action_id") or "")))
    for action in actions:
        candidate = _candidate_from_action(action, turn_number=turn_number, run_seed=run_seed)
        if candidate:
            candidates.append(candidate)
        if len(candidates) >= MAX_WORLD_EVENT_INPUTS_PER_TICK:
            return candidates

    for candidate in _rolling_candidates(rolling_state, turn_number=turn_number, run_seed=run_seed):
        candidates.append(candidate)
        if len(candidates) >= MAX_WORLD_EVENT_INPUTS_PER_TICK:
            return candidates
    return candidates


def _find_existing(world_events: Sequence[Dict[str, Any]], candidate: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    wanted_id = _bounded_str(candidate.get("world_event_id"), 160)
    wanted_key = _bounded_str(candidate.get("dedupe_key"), 180)
    for row in world_events:
        if row.get("status") in TERMINAL_STATUSES:
            continue
        if wanted_id and row.get("world_event_id") == wanted_id:
            return row
        if wanted_key and row.get("dedupe_key") == wanted_key:
            return row
    return None


def _reinforce_event(existing: Dict[str, Any], candidate: Mapping[str, Any], turn_number: int) -> bool:
    changed = False
    for key, limit in (
        ("originating_pressure_ids", MAX_WORLD_EVENT_REFS),
        ("originating_situation_ids", MAX_WORLD_EVENT_REFS),
        ("originating_goal_ids", MAX_WORLD_EVENT_REFS),
        ("originating_action_ids", MAX_WORLD_EVENT_REFS),
        ("affected_locations", MAX_WORLD_EVENT_REFS),
        ("affected_regions", MAX_WORLD_EVENT_REFS),
        ("affected_factions", MAX_WORLD_EVENT_REFS),
        ("affected_actor_ids", MAX_WORLD_EVENT_REFS),
        ("evidence_refs", MAX_WORLD_EVENT_EVIDENCE_REFS),
        ("source_event_ids", MAX_WORLD_EVENT_REFS),
    ):
        changed = _merge_unique(existing, candidate, key, limit) or changed
    severity = max(_clamp_int(existing.get("severity"), 0, 10), _clamp_int(candidate.get("severity"), 0, 10))
    if severity != existing.get("severity"):
        existing["severity"] = severity
        changed = True
    if existing.get("status") == "forming" and severity >= 4:
        existing["status"] = "active"
        changed = True
    if _coerce_int(candidate.get("expiry"), 0) > _coerce_int(existing.get("expiry"), 0):
        existing["expiry"] = _coerce_int(candidate.get("expiry"), existing.get("expiry"))
        changed = True
    if changed:
        existing["updated_turn"] = turn_number
    existing["last_reinforced_turn"] = turn_number
    existing["inactive_turns"] = 0
    return changed


def _pressure_statuses(replayability_state: Mapping[str, Any]) -> Dict[str, str]:
    graph = replayability_state.get("pressure_graph") if isinstance(replayability_state, Mapping) else {}
    return {
        str(node.get("id")): str(node.get("status") or "")
        for node in (graph or {}).get("nodes") or []
        if isinstance(node, Mapping) and node.get("id")
    }


def _row_statuses(replayability_state: Mapping[str, Any], key: str, id_key: str) -> Dict[str, str]:
    return {
        str(row.get(id_key)): str(row.get("status") or "")
        for row in replayability_state.get(key) or []
        if isinstance(row, Mapping) and row.get(id_key)
    }


def _advance_existing_event(
    event: Dict[str, Any],
    *,
    replayability_state: Mapping[str, Any],
    turn_number: int,
) -> Optional[Tuple[str, str, Dict[str, Any], Dict[str, Any]]]:
    if event.get("status") == "archived":
        return None
    if event.get("last_evolved_turn") == turn_number:
        return None
    before = copy.deepcopy(event)
    status = str(event.get("status") or "")
    if status in {"resolved", "failed"}:
        if turn_number - _coerce_int(event.get("updated_turn"), turn_number) >= ARCHIVE_AFTER_TERMINAL_TURNS:
            event["status"] = "archived"
            event["archived_turn"] = turn_number
            event["updated_turn"] = turn_number
            event["last_evolved_turn"] = turn_number
            return "world_event_archived", "terminal_archive", before, copy.deepcopy(event)
        event["last_evolved_turn"] = turn_number
        return None

    pressure_status = _pressure_statuses(replayability_state)
    situation_status = _row_statuses(replayability_state, "situations", "situation_id")
    goal_status = _row_statuses(replayability_state, "goals", "goal_id")

    pressure_ids = _bounded_str_list(event.get("originating_pressure_ids"), MAX_WORLD_EVENT_REFS)
    situation_ids = _bounded_str_list(event.get("originating_situation_ids"), MAX_WORLD_EVENT_REFS)
    goal_ids = _bounded_str_list(event.get("originating_goal_ids"), MAX_WORLD_EVENT_REFS)

    pressure_active = any(pressure_status.get(pid) == "active" for pid in pressure_ids)
    situation_active = any(situation_status.get(sid) not in {"", "resolved", "failed", "archived"} for sid in situation_ids)
    goal_active = any(goal_status.get(gid) not in {"", "completed", "failed", "abandoned"} for gid in goal_ids)
    has_tracked_sources = bool(pressure_ids or situation_ids or goal_ids)
    any_source_active = pressure_active or situation_active or goal_active

    receipt_type = ""
    detail = ""
    if has_tracked_sources and not any_source_active:
        event["progress"] = min(100, _clamp_int(event.get("progress"), 0, 100) + 35)
        event["severity"] = max(0, _clamp_int(event.get("severity"), 0, 10) - 2)
        event["status"] = "resolved" if event["progress"] >= 100 or event["severity"] <= 1 else "resolving"
        event["updated_turn"] = turn_number
        event["inactive_turns"] = 0
        receipt_type = "world_event_resolved" if event["status"] == "resolved" else "world_event_progressed"
        detail = "origin_sources_quiet"
    else:
        inactive = max(0, _coerce_int(event.get("inactive_turns"), 0)) + 1
        event["inactive_turns"] = inactive
        if inactive >= DECAY_AFTER_INACTIVE_TURNS and _clamp_int(event.get("severity"), 0, 10) <= 4:
            event["progress"] = min(100, _clamp_int(event.get("progress"), 0, 100) + 10)
            event["severity"] = max(0, _clamp_int(event.get("severity"), 0, 10) - 1)
            event["status"] = "resolved" if event["severity"] <= 0 and event["progress"] >= 50 else "resolving"
            event["updated_turn"] = turn_number
            receipt_type = "world_event_resolved" if event["status"] == "resolved" else "world_event_progressed"
            detail = "inactive_decay"
        elif turn_number >= _coerce_int(event.get("expiry"), turn_number + 1):
            event["status"] = "failed"
            event["severity"] = min(_clamp_int(event.get("severity"), 0, 10), 3)
            event["updated_turn"] = turn_number
            receipt_type = "world_event_failed"
            detail = "expired"

    event["last_evolved_turn"] = turn_number
    if receipt_type and before != event:
        return receipt_type, detail, before, copy.deepcopy(event)
    return None


def _merge_duplicate_events(
    replayability_state: Dict[str, Any],
    world_events: List[Dict[str, Any]],
    local_receipts: List[Dict[str, Any]],
    turn_number: int,
    remaining_changes: int,
) -> int:
    by_key: Dict[str, Dict[str, Any]] = {}
    for event in sorted(world_events, key=lambda row: (_coerce_int(row.get("created_turn"), 0), str(row.get("world_event_id") or ""))):
        if event.get("status") in TERMINAL_STATUSES:
            continue
        key = _bounded_str(event.get("dedupe_key"), 180)
        if not key:
            continue
        primary = by_key.get(key)
        if primary is None:
            by_key[key] = event
            continue
        if remaining_changes <= 0:
            break
        before = copy.deepcopy(primary)
        _reinforce_event(primary, event, turn_number)
        duplicate_before = copy.deepcopy(event)
        event["status"] = "resolved"
        event["progress"] = 100
        event["severity"] = min(_clamp_int(event.get("severity"), 0, 10), 1)
        event["updated_turn"] = turn_number
        event["merged_into"] = primary.get("world_event_id")
        _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type="world_event_merged",
            turn_number=turn_number,
            world_event=primary,
            before=before,
            after=primary,
            detail=f"merged:{event.get('world_event_id')}",
            source_event_ids=list(primary.get("source_event_ids") or []) + list(event.get("source_event_ids") or []),
        )
        _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type="world_event_resolved",
            turn_number=turn_number,
            world_event=event,
            before=duplicate_before,
            after=event,
            detail="merged_duplicate",
            source_event_ids=event.get("source_event_ids") or [],
        )
        remaining_changes -= 1
    return remaining_changes


def _compact_terminal_event(event: Dict[str, Any]) -> Dict[str, Any]:
    if event.get("status") not in TERMINAL_STATUSES:
        return event
    keep = (
        "world_event_id",
        "event_type",
        "title",
        "severity",
        "status",
        "progress",
        "created_turn",
        "updated_turn",
        "affected_locations",
        "affected_regions",
        "affected_factions",
        "affected_actor_ids",
        "source_event_ids",
        "dedupe_key",
        "archived_turn",
    )
    return {key: copy.deepcopy(event.get(key)) for key in keep if event.get(key) not in (None, "", [])}


def _cap_world_events(world_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    active = [row for row in world_events if row.get("status") not in TERMINAL_STATUSES]
    if len(active) > MAX_ACTIVE_WORLD_EVENTS:
        overflow_ids = {
            row.get("world_event_id")
            for row in sorted(
                active,
                key=lambda row: (
                    _clamp_int(row.get("severity"), 0, 10),
                    _coerce_int(row.get("updated_turn"), 0),
                    str(row.get("world_event_id") or ""),
                ),
            )[: len(active) - MAX_ACTIVE_WORLD_EVENTS]
        }
        for row in world_events:
            if row.get("world_event_id") in overflow_ids:
                row["status"] = "archived"
                row["updated_turn"] = max(_coerce_int(row.get("updated_turn"), 0), _coerce_int(row.get("created_turn"), 0))
                row["archived_turn"] = row.get("archived_turn") or row.get("updated_turn")
    world_events = [_compact_terminal_event(row) for row in world_events]
    if len(world_events) > MAX_WORLD_EVENTS:
        world_events = sorted(
            world_events,
            key=lambda row: (
                0 if row.get("status") not in TERMINAL_STATUSES else 1,
                -_clamp_int(row.get("severity"), 0, 10),
                -_coerce_int(row.get("updated_turn"), 0),
                str(row.get("world_event_id") or ""),
            ),
        )[:MAX_WORLD_EVENTS]
    return sorted(world_events, key=lambda row: (_coerce_int(row.get("created_turn"), 0), str(row.get("world_event_id") or "")))


def evolve_world_events(
    replayability_state: Dict[str, Any],
    rolling_state: Mapping[str, Any],
    turn_number: int,
    *,
    run_seed: str = "",
) -> Dict[str, Any]:
    """Evaluate engine state into bounded canonical world events."""
    diagnostics = {
        "world_event_engine_executed": False,
        "world_event_candidates_evaluated": 0,
        "world_event_created": 0,
        "world_event_reinforced": 0,
        "world_event_merged": 0,
        "world_event_progressed": 0,
        "world_event_resolved": 0,
        "world_event_failed": 0,
        "world_event_archived": 0,
        "world_event_duplicate_suppressed": 0,
        "world_event_recreated": 0,
        "world_event_engine_events": 0,
    }
    if not isinstance(replayability_state, dict):
        return {"events": [], "receipts": [], "diagnostics": diagnostics}

    seed = run_seed or str(replayability_state.get("run_seed") or "world-event-engine")
    world_events = [
        _normalise_world_event(row, run_seed=seed)
        for row in replayability_state.get("world_events") or []
        if isinstance(row, Mapping)
    ]
    replayability_state["world_events"] = world_events
    replayability_state.setdefault("world_event_receipts", [])
    local_receipts: List[Dict[str, Any]] = []
    engine_events: List[Dict[str, Any]] = []
    remaining_changes = MAX_WORLD_EVENT_CHANGES_PER_TICK
    touched_ids = set()

    candidates = _collect_candidates(
        replayability_state,
        rolling_state if isinstance(rolling_state, Mapping) else {},
        turn_number=turn_number,
        run_seed=seed,
    )
    candidates.sort(
        key=lambda row: (
            -_clamp_int(row.get("severity"), 0, 10),
            str(row.get("event_type") or ""),
            str(row.get("dedupe_key") or ""),
        )
    )

    seen_candidate_keys = set()
    for candidate in candidates:
        diagnostics["world_event_candidates_evaluated"] += 1
        key = (candidate.get("dedupe_key"), tuple(candidate.get("source_event_ids") or []))
        if key in seen_candidate_keys:
            diagnostics["world_event_duplicate_suppressed"] += 1
            continue
        seen_candidate_keys.add(key)
        existing = _find_existing(world_events, candidate)
        if existing is None:
            if remaining_changes <= 0 or len(world_events) >= MAX_WORLD_EVENTS:
                diagnostics["world_event_duplicate_suppressed"] += 1
                continue
            generation = _assign_unique_world_event_id(candidate, world_events, seed)
            world_events.append(candidate)
            if _append_receipt(
                replayability_state,
                local_receipts,
                receipt_type="world_event_created",
                turn_number=turn_number,
                world_event=candidate,
                before={},
                after=candidate,
                detail="created_from_engine_inputs",
                source_event_ids=candidate.get("source_event_ids") or [],
            ):
                diagnostics["world_event_created"] += 1
                if generation > 0:
                    diagnostics["world_event_recreated"] += 1
                touched_ids.add(str(candidate.get("world_event_id") or ""))
                engine_events.append(
                    _engine_event_from_world_event(
                        candidate,
                        run_seed=seed,
                        turn_number=turn_number,
                        receipt_type="world_event_created",
                    )
                )
                remaining_changes -= 1
            continue

        new_sources = [
            source_id
            for source_id in candidate.get("source_event_ids") or []
            if source_id not in (existing.get("source_event_ids") or [])
        ]
        if not new_sources and _clamp_int(candidate.get("severity"), 0, 10) <= _clamp_int(existing.get("severity"), 0, 10):
            diagnostics["world_event_duplicate_suppressed"] += 1
            existing["last_reinforced_turn"] = turn_number
            existing["inactive_turns"] = 0
            continue
        if remaining_changes <= 0:
            continue
        before = copy.deepcopy(existing)
        changed = _reinforce_event(existing, candidate, turn_number)
        if changed:
            touched_ids.add(str(existing.get("world_event_id") or ""))
        if changed and _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type="world_event_reinforced",
            turn_number=turn_number,
            world_event=existing,
            before=before,
            after=existing,
            detail="reinforced_from_engine_inputs",
            source_event_ids=new_sources or candidate.get("source_event_ids") or [],
        ):
            diagnostics["world_event_reinforced"] += 1
            remaining_changes -= 1

    before_merge_receipts = len(local_receipts)
    remaining_changes = _merge_duplicate_events(
        replayability_state,
        world_events,
        local_receipts,
        turn_number,
        remaining_changes,
    )
    diagnostics["world_event_merged"] += sum(
        1 for receipt in local_receipts[before_merge_receipts:]
        if receipt.get("receipt_type") == "world_event_merged"
    )
    diagnostics["world_event_resolved"] += sum(
        1 for receipt in local_receipts[before_merge_receipts:]
        if receipt.get("receipt_type") == "world_event_resolved"
    )

    for event in sorted(world_events, key=lambda row: (-_clamp_int(row.get("severity"), 0, 10), str(row.get("world_event_id") or ""))):
        if remaining_changes <= 0:
            break
        if str(event.get("world_event_id") or "") in touched_ids:
            event["last_evolved_turn"] = turn_number
            continue
        advanced = _advance_existing_event(
            event,
            replayability_state=replayability_state,
            turn_number=turn_number,
        )
        if not advanced:
            continue
        receipt_type, detail, before, after = advanced
        if _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type=receipt_type,
            turn_number=turn_number,
            world_event=event,
            before=before,
            after=after,
            detail=detail,
            source_event_ids=event.get("source_event_ids") or [],
        ):
            if receipt_type == "world_event_progressed":
                diagnostics["world_event_progressed"] += 1
            elif receipt_type == "world_event_resolved":
                diagnostics["world_event_resolved"] += 1
            elif receipt_type == "world_event_failed":
                diagnostics["world_event_failed"] += 1
            elif receipt_type == "world_event_archived":
                diagnostics["world_event_archived"] += 1
            remaining_changes -= 1

    replayability_state["world_events"] = _cap_world_events(world_events)
    diagnostics["world_event_engine_events"] = len(engine_events)
    diagnostics["world_event_engine_executed"] = bool(local_receipts or candidates or replayability_state["world_events"])
    return {"events": engine_events, "receipts": local_receipts, "diagnostics": diagnostics}


def project_active_world_events_for_rolling(
    replayability_state: Mapping[str, Any],
    *,
    limit: int = MAX_PROJECTED_WORLD_EVENTS,
) -> List[Dict[str, Any]]:
    if not isinstance(replayability_state, Mapping):
        return []
    seed = str(replayability_state.get("run_seed") or "world-event-engine")
    events = [
        _normalise_world_event(row, run_seed=seed)
        for row in replayability_state.get("world_events") or []
        if isinstance(row, Mapping) and row.get("status") not in TERMINAL_STATUSES
    ]
    ordered = sorted(
        events,
        key=lambda row: (
            -_clamp_int(row.get("severity"), 0, 10),
            _coerce_int(row.get("created_turn"), 0),
            str(row.get("world_event_id") or ""),
        ),
    )[: max(0, min(MAX_PROJECTED_WORLD_EVENTS, int(limit or 0)))]
    return [
        {
            "title": row.get("title"),
            "severity": row.get("severity"),
            "status": row.get("status"),
            "affected_locations": list(row.get("affected_locations") or [])[:MAX_WORLD_EVENT_REFS],
            "affected_factions": list(row.get("affected_factions") or [])[:MAX_WORLD_EVENT_REFS],
            "progress": row.get("progress"),
        }
        for row in ordered
    ]


def project_world_events_for_prompt(replayability_state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return project_active_world_events_for_rolling(replayability_state, limit=MAX_PROMPT_WORLD_EVENTS)


def prompt_safe_rolling_state(rolling_state: Mapping[str, Any]) -> Dict[str, Any]:
    """Strip world-event internals from a rolling_state copy."""
    if not isinstance(rolling_state, Mapping):
        return {}
    safe = copy.deepcopy(dict(rolling_state))
    rows = safe.get("active_world_events")
    if not isinstance(rows, list):
        return safe
    cleaned: List[Dict[str, Any]] = []
    for row in rows[:MAX_PROMPT_WORLD_EVENTS]:
        if not isinstance(row, Mapping):
            continue
        cleaned.append(
            {
                key: copy.deepcopy(row.get(key))
                for key in (
                    "title",
                    "severity",
                    "status",
                    "affected_locations",
                    "affected_factions",
                    "progress",
                )
                if key in row
            }
        )
    safe["active_world_events"] = cleaned
    return safe


def copy_world_event_state(replayability_state: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(replayability_state, Mapping):
        return {"world_events": []}
    seed = str(replayability_state.get("run_seed") or "world-event-engine")
    events = [
        _normalise_world_event(row, run_seed=seed)
        for row in replayability_state.get("world_events") or []
        if isinstance(row, Mapping)
    ]
    bounded = []
    for row in _cap_world_events(events):
        bounded.append(
            {
                "world_event_id": row.get("world_event_id"),
                "event_type": row.get("event_type"),
                "title": row.get("title"),
                "severity": row.get("severity"),
                "status": row.get("status"),
                "affected_locations": list(row.get("affected_locations") or [])[:MAX_WORLD_EVENT_REFS],
                "affected_regions": list(row.get("affected_regions") or [])[:MAX_WORLD_EVENT_REFS],
                "affected_factions": list(row.get("affected_factions") or [])[:MAX_WORLD_EVENT_REFS],
                "affected_actor_ids": list(row.get("affected_actor_ids") or [])[:MAX_WORLD_EVENT_REFS],
                "progress": row.get("progress"),
            }
        )
    return {"world_events": bounded}


def _token_set(*values: Any) -> set:
    out = set()
    for value in values:
        raw = value if isinstance(value, (list, tuple, set)) else [value]
        for item in raw:
            text = str(item or "").strip().lower()
            if text:
                out.add(text)
    return out


def _world_event_ref_sets(row: Mapping[str, Any]) -> Dict[str, set]:
    return {
        "actor": _token_set(row.get("affected_actor_ids")),
        "location": _token_set(row.get("affected_locations")),
        "faction": _token_set(row.get("affected_factions")),
        "world_event": _token_set(row.get("world_event_id")),
    }


def active_world_events_for_context(
    world_event_state: Mapping[str, Any],
    *,
    actor_ids: Sequence[str] = (),
    location_ids: Sequence[str] = (),
    faction_ids: Sequence[str] = (),
    world_event_ids: Sequence[str] = (),
    limit: int = MAX_CONTEXT_WORLD_EVENTS,
) -> List[Dict[str, Any]]:
    if not isinstance(world_event_state, Mapping):
        return []
    context = {
        "actor": _token_set(actor_ids),
        "location": _token_set(location_ids),
        "faction": _token_set(faction_ids),
        "world_event": _token_set(world_event_ids),
    }
    matched: List[Dict[str, Any]] = []
    for raw in world_event_state.get("world_events") or []:
        if not isinstance(raw, Mapping):
            continue
        row = _normalise_world_event(raw)
        if row.get("status") in TERMINAL_STATUSES:
            continue
        refs = _world_event_ref_sets(row)
        has_specific_refs = any(refs[key] for key in ("actor", "location", "faction"))
        applies = any(refs[key].intersection(context.get(key, set())) for key in refs)
        if applies or not has_specific_refs:
            matched.append(row)
    ordered = sorted(
        matched,
        key=lambda row: (
            -_clamp_int(row.get("severity"), 0, 10),
            str(row.get("world_event_id") or ""),
        ),
    )
    return ordered[: max(0, min(MAX_CONTEXT_WORLD_EVENTS, int(limit or 0)))]
