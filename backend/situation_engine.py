"""
Deterministic Situation Engine.

Situations are engine-owned long-lived objects derived from pressure, engine
world events, and structured world state changes. The LLM never owns or mutates
canonical situation state; rolling_state only receives a bounded projection.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import investigation_engine
import npc_agendas
import world_state_consumers

SITUATION_ENGINE_VERSION = 1

MAX_SITUATIONS = 12
MAX_ACTIVE_SITUATIONS = 8
MAX_SITUATION_INPUTS_PER_TICK = 8
MAX_SITUATION_CHANGES_PER_TICK = 6
MAX_SITUATION_RECEIPTS = 64
MAX_SITUATION_REFS = 8
MAX_SITUATION_OBJECTIVES = 4
MAX_SITUATION_BLOCKERS = 4
MAX_SITUATION_EVIDENCE_REFS = 8
MAX_PROJECTED_SITUATIONS = 6
MAX_PROMPT_SITUATIONS = 4
MAX_CONTEXT_SITUATIONS = 4
MAX_PROMOTED_GOALS = 3
MAX_PROMOTED_INFORMATION = 3
MAX_PROMOTED_PRESSURE_LABELS = 3
MAX_PROMOTED_WORLD_EVENTS = 2
MAX_PROMOTED_OPPORTUNITIES = 4
MAX_PROMOTED_ACTORS = 6
MAX_PROMOTED_RELATIONSHIP_SHIFTS = 2

SITUATION_STATUS_PHRASES = {
    "forming": "taking shape",
    "active": "unfolding now",
    "resolving": "heading toward resolution",
}

WHY_IT_MATTERS_BY_TYPE = {
    "food_shortage": "Supplies are strained and daily needs are at risk",
    "gang_turf_war": "Violence is escalating and control of the area is contested",
    "murder_investigation": "A death demands answers before trust collapses",
    "political_unrest": "Tensions are rising and public order is fragile",
    "bandit_activity": "Routes and settlements face an active threat",
    "trade_opportunity": "A time-sensitive exchange could shift local fortunes",
    "disease_outbreak": "Illness is spreading and containment is urgent",
    "flood_recovery": "Damage is disrupting movement and recovery",
    "search_party": "Someone is missing and time works against rescue",
    "missing_child": "A child is unaccounted for and every hour matters",
}

WORLD_STATE_SIGNAL_TO_SITUATION_TYPE = {
    "resource_shortage": "food_shortage",
    "route_blocked": "bandit_activity",
    "infrastructure_damaged": "flood_recovery",
    "settlement_unstable": "political_unrest",
    "faction_pressure": "political_unrest",
    "settlement_improving": "trade_opportunity",
    "market_strained": "food_shortage",
    "actor_missing": "missing_child",
}

PROMOTED_SITUATION_FIELDS = (
    "situation_id",
    "type",
    "title",
    "status",
    "priority",
    "severity",
    "progress",
    "headline",
    "why_it_matters",
    "affected_actors",
    "affected_locations",
    "affected_factions",
    "objectives",
    "blockers",
    "player_opportunities",
    "related_goals",
    "related_information",
    "pressure_labels",
    "related_world_events",
    "relationship_shifts",
    "world_state_signals",
    "world_state_opportunities",
    "evidence_exposure_signals",
    "evidence_exposure_behaviours",
    "ambition_signals",
    "ambition_opportunities",
)

CREATION_PRESSURE_THRESHOLD = 50
DEFAULT_EXPIRY_TURNS = 12
DECAY_AFTER_INACTIVE_TURNS = 2
ARCHIVE_AFTER_TERMINAL_TURNS = 8

SITUATION_STATUSES = ("forming", "active", "resolving", "resolved", "failed", "archived")
TERMINAL_STATUSES = frozenset({"resolved", "failed", "archived"})

SITUATION_RECEIPT_TYPES = (
    "situation_created",
    "situation_reinforced",
    "situation_merged",
    "situation_progressed",
    "situation_decayed",
    "situation_resolved",
    "situation_failed",
    "situation_archived",
)

PRESSURE_KIND_GROUPS = {
    "danger": "danger",
    "environmental": "danger",
    "environmental_threat": "danger",
    "pursuit": "danger",
    "injury_or_fatigue": "danger",
    "resource": "scarcity",
    "resource_pressure": "scarcity",
    "scarcity": "scarcity",
    "social": "conflict",
    "social_tension": "conflict",
    "conflict": "conflict",
    "suspicion": "conflict",
    "opportunity": "opportunity",
    "unresolved_thread": "unknown",
    "unknown": "unknown",
}

EVENT_KIND_TO_TYPE = {
    "resource_shortage": "food_shortage",
    "trade_disruption": "trade_opportunity",
    "investigation": "murder_investigation",
    "search_operation": "search_party",
    "disease_outbreak": "disease_outbreak",
    "infrastructure_failure": "flood_recovery",
    "settlement_recovery": "flood_recovery",
    "bandit_activity": "bandit_activity",
    "political_unrest": "political_unrest",
    "migration": "search_party",
    "military_mobilisation": "gang_turf_war",
    "construction": "trade_opportunity",
    "fire": "flood_recovery",
    "flood": "flood_recovery",
    "crop_failure": "food_shortage",
    "guard_patrol": "political_unrest",
    "refugee_movement": "search_party",
    "wildlife_migration": "bandit_activity",
    "environmental_hazard": "flood_recovery",
    "collapse": "flood_recovery",
    "fire": "flood_recovery",
    "evacuation": "search_party",
    "accident": "bandit_activity",
    "attack": "bandit_activity",
    "injury": "bandit_activity",
    "supplies_exhausted": "food_shortage",
    "theft": "food_shortage",
    "price_increase": "food_shortage",
    "resource_discovery": "trade_opportunity",
    "abandoned_cache": "trade_opportunity",
    "trader_arrival": "trade_opportunity",
    "argument": "political_unrest",
    "protest": "political_unrest",
    "raid": "gang_turf_war",
    "retaliation": "gang_turf_war",
    "alliance_fracture": "political_unrest",
    "strange_evidence": "murder_investigation",
    "mysterious_signal": "murder_investigation",
    "unexplained_disappearance": "missing_child",
    "disease": "disease_outbreak",
    "npc_found_clue": "murder_investigation",
    "npc_failed_search": "search_party",
    "npc_gathered_food": "food_shortage",
    "npc_secured_resource": "trade_opportunity",
    "npc_repaired_bridge": "flood_recovery",
    "npc_warned_settlement": "political_unrest",
    "npc_recruited_member": "political_unrest",
    "npc_defended_area": "bandit_activity",
    "npc_attacked": "gang_turf_war",
    "npc_retreated": "bandit_activity",
    "npc_travelled": "search_party",
    "npc_negotiated": "political_unrest",
    "npc_delivered_resource": "trade_opportunity",
}

PRESSURE_GROUP_TO_TYPE = {
    "danger": "bandit_activity",
    "scarcity": "food_shortage",
    "conflict": "political_unrest",
    "opportunity": "trade_opportunity",
    "unknown": "murder_investigation",
}

SITUATION_TITLES = {
    "murder_investigation": "Murder Investigation",
    "food_shortage": "Food Shortage",
    "gang_turf_war": "Gang Turf War",
    "disease_outbreak": "Disease Outbreak",
    "political_unrest": "Political Unrest",
    "search_party": "Search Party",
    "flood_recovery": "Flood Recovery",
    "missing_child": "Missing Child",
    "bandit_activity": "Bandit Activity",
    "trade_opportunity": "Trade Opportunity",
}

SITUATION_OBJECTIVES = {
    "murder_investigation": ("gather_evidence", "identify_cause"),
    "food_shortage": ("secure_supplies", "stabilize_distribution"),
    "gang_turf_war": ("reduce_violence", "identify_leaders"),
    "disease_outbreak": ("isolate_cases", "restore_health"),
    "political_unrest": ("reduce_tension", "protect_civilians"),
    "search_party": ("locate_missing", "coordinate_search"),
    "flood_recovery": ("restore_routes", "repair_damage"),
    "missing_child": ("locate_missing", "gather_witnesses"),
    "bandit_activity": ("identify_threat", "protect_routes"),
    "trade_opportunity": ("assess_offer", "secure_benefit"),
}

SITUATION_BLOCKERS = {
    "murder_investigation": ("missing_evidence",),
    "food_shortage": ("limited_supplies",),
    "gang_turf_war": ("retaliation_risk",),
    "disease_outbreak": ("spread_risk",),
    "political_unrest": ("low_trust",),
    "search_party": ("uncertain_location",),
    "flood_recovery": ("damaged_infrastructure",),
    "missing_child": ("uncertain_location",),
    "bandit_activity": ("threat_unidentified",),
    "trade_opportunity": ("terms_unclear",),
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


def _bounded_str(value: Any, limit: int = 120) -> str:
    return str(value or "").strip()[:limit]


def _bounded_str_list(values: Any, limit: int = MAX_SITUATION_REFS) -> List[str]:
    out: List[str] = []
    raw = values if isinstance(values, (list, tuple, set)) else [values]
    for value in raw or []:
        text = _bounded_str(value)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _clamp_int(value: Any, low: int, high: int, default: int = 0) -> int:
    return max(low, min(high, _coerce_int(value, default)))


def _pressure_group(kind: Any) -> str:
    return PRESSURE_KIND_GROUPS.get(str(kind or "").strip().lower(), "unknown")


def _event_kind(event: Mapping[str, Any]) -> str:
    return _bounded_str(event.get("pressure_event_kind") or event.get("event_kind"), 80)


def _situation_type_for_pressure(kind: Any) -> str:
    return PRESSURE_GROUP_TO_TYPE.get(_pressure_group(kind), "murder_investigation")


def _situation_type_for_event(kind: Any) -> str:
    return EVENT_KIND_TO_TYPE.get(str(kind or "").strip().lower(), "murder_investigation")


def _refs_from_pressure(node: Mapping[str, Any]) -> Tuple[List[str], List[str], List[str]]:
    return (
        _bounded_str_list(node.get("actor_ids") or node.get("linked_actor_ids")),
        _bounded_str_list(
            list(node.get("location_ids") or [])
            + list(node.get("region_ids") or [])
            + list(node.get("linked_location_ids") or [])
            + list(node.get("linked_region_ids") or [])
        ),
        _bounded_str_list(node.get("faction_ids") or node.get("linked_faction_ids")),
    )


def _refs_from_event(event: Mapping[str, Any]) -> Tuple[List[str], List[str], List[str]]:
    return (
        _bounded_str_list(event.get("actor_ids")),
        _bounded_str_list(list(event.get("location_ids") or []) + list(event.get("region_ids") or [])),
        _bounded_str_list(event.get("faction_ids")),
    )


def _scope_key(
    *,
    situation_type: str,
    actor_ids: Sequence[str],
    locations: Sequence[str],
    factions: Sequence[str],
    fallback: str,
) -> str:
    if locations:
        return f"{situation_type}:location:{locations[0]}"
    if factions:
        return f"{situation_type}:faction:{factions[0]}"
    if actor_ids:
        return f"{situation_type}:actor:{actor_ids[0]}"
    return f"{situation_type}:global:{fallback}"


def _situation_id(run_seed: str, dedupe_key: str) -> str:
    return _stable_id("situation", run_seed, dedupe_key)


def _situation_id_for_generation(run_seed: str, dedupe_key: str, generation: int) -> str:
    if generation <= 0:
        return _situation_id(run_seed, dedupe_key)
    return _stable_id("situation", run_seed, dedupe_key, "recreated", generation)


def _assign_unique_situation_id(
    candidate: Dict[str, Any],
    situations: Sequence[Mapping[str, Any]],
    run_seed: str,
) -> int:
    dedupe = _bounded_str(candidate.get("dedupe_key"), 180)
    if not dedupe:
        return 0
    existing_ids = {
        str(row.get("situation_id") or "")
        for row in situations
        if isinstance(row, Mapping) and row.get("situation_id")
    }
    generation = 0
    while True:
        situation_id = _situation_id_for_generation(run_seed, dedupe, generation)
        if situation_id not in existing_ids:
            candidate["situation_id"] = situation_id
            return generation
        generation += 1


def _default_title(situation_type: str) -> str:
    return SITUATION_TITLES.get(situation_type, situation_type.replace("_", " ").title())


def _normalise_status(value: Any, severity: int = 0) -> str:
    status = str(value or "").strip().lower()
    if status in SITUATION_STATUSES:
        return status
    return "active" if severity >= 4 else "forming"


def _normalise_situation(row: Mapping[str, Any], *, run_seed: str = "") -> Dict[str, Any]:
    situation_type = _bounded_str(row.get("type") or "murder_investigation", 80)
    actor_ids = _bounded_str_list(row.get("involved_actor_ids"), MAX_SITUATION_REFS)
    locations = _bounded_str_list(row.get("involved_locations"), MAX_SITUATION_REFS)
    factions = _bounded_str_list(row.get("involved_factions"), MAX_SITUATION_REFS)
    dedupe_key = _bounded_str(
        row.get("dedupe_key")
        or _scope_key(
            situation_type=situation_type,
            actor_ids=actor_ids,
            locations=locations,
            factions=factions,
            fallback=situation_type,
        ),
        180,
    )
    created_turn = max(0, _coerce_int(row.get("created_turn"), 0))
    updated_turn = max(created_turn, _coerce_int(row.get("updated_turn"), created_turn))
    severity = _clamp_int(row.get("severity"), 0, 10, default=1)
    out = {
        "situation_id": _bounded_str(
            row.get("situation_id") or _situation_id(run_seed or "situation", dedupe_key),
            160,
        ),
        "type": situation_type,
        "title": _bounded_str(row.get("title") or _default_title(situation_type), 120),
        "status": _normalise_status(row.get("status"), severity),
        "priority": _clamp_int(row.get("priority"), 0, 10, default=severity),
        "severity": severity,
        "created_turn": created_turn,
        "updated_turn": updated_turn,
        "originating_pressure_ids": _bounded_str_list(row.get("originating_pressure_ids"), MAX_SITUATION_REFS),
        "originating_world_event_ids": _bounded_str_list(row.get("originating_world_event_ids"), MAX_SITUATION_REFS),
        "involved_actor_ids": actor_ids,
        "involved_locations": locations,
        "involved_factions": factions,
        "objectives": _bounded_str_list(row.get("objectives"), MAX_SITUATION_OBJECTIVES),
        "blockers": _bounded_str_list(row.get("blockers"), MAX_SITUATION_BLOCKERS),
        "evidence_refs": _bounded_str_list(row.get("evidence_refs"), MAX_SITUATION_EVIDENCE_REFS),
        "progress": _clamp_int(row.get("progress"), 0, 100, default=0),
        "expiry": max(updated_turn, _coerce_int(row.get("expiry"), created_turn + DEFAULT_EXPIRY_TURNS)),
        "source_event_ids": _bounded_str_list(row.get("source_event_ids"), MAX_SITUATION_REFS),
        "dedupe_key": dedupe_key,
        "last_reinforced_turn": _coerce_int(row.get("last_reinforced_turn"), updated_turn),
        "last_evolved_turn": row.get("last_evolved_turn"),
        "inactive_turns": max(0, _coerce_int(row.get("inactive_turns"), 0)),
    }
    if out["status"] in TERMINAL_STATUSES:
        out["priority"] = min(out["priority"], 2)
    if not out["objectives"]:
        out["objectives"] = list(SITUATION_OBJECTIVES.get(situation_type, ("understand_situation",)))[:MAX_SITUATION_OBJECTIVES]
    if not out["blockers"]:
        out["blockers"] = list(SITUATION_BLOCKERS.get(situation_type, ("missing_context",)))[:MAX_SITUATION_BLOCKERS]
    return out


def _candidate_from_pressure(node: Mapping[str, Any], *, turn_number: int, run_seed: str) -> Optional[Dict[str, Any]]:
    if str(node.get("status") or "") != "active":
        return None
    magnitude = _clamp_int(node.get("magnitude"), 0, 100)
    trend = _coerce_int(node.get("trend"), 0)
    if magnitude < CREATION_PRESSURE_THRESHOLD and trend <= 0:
        return None
    pressure_id = _bounded_str(node.get("id"), 160)
    if not pressure_id:
        return None
    situation_type = _situation_type_for_pressure(node.get("kind"))
    actor_ids, locations, factions = _refs_from_pressure(node)
    dedupe_key = _scope_key(
        situation_type=situation_type,
        actor_ids=actor_ids,
        locations=locations,
        factions=factions,
        fallback=_pressure_group(node.get("kind")),
    )
    severity = max(1, min(10, round(magnitude / 10)))
    return _normalise_situation(
        {
            "situation_id": _situation_id(run_seed, dedupe_key),
            "type": situation_type,
            "title": _default_title(situation_type),
            "status": "active" if severity >= 4 else "forming",
            "priority": min(10, severity + (1 if trend > 0 else 0)),
            "severity": severity,
            "created_turn": turn_number,
            "updated_turn": turn_number,
            "originating_pressure_ids": [pressure_id],
            "involved_actor_ids": actor_ids,
            "involved_locations": locations,
            "involved_factions": factions,
            "objectives": SITUATION_OBJECTIVES.get(situation_type, ()),
            "blockers": SITUATION_BLOCKERS.get(situation_type, ()),
            "evidence_refs": list(node.get("evidence_refs") or []) + [f"pressure:{pressure_id}"],
            "progress": 0,
            "expiry": turn_number + DEFAULT_EXPIRY_TURNS,
            "source_event_ids": [pressure_id],
            "dedupe_key": dedupe_key,
            "last_reinforced_turn": turn_number,
            "inactive_turns": 0,
        },
        run_seed=run_seed,
    )


def _candidate_from_world_state_signal(
    signal: Mapping[str, Any],
    *,
    turn_number: int,
    run_seed: str,
) -> Optional[Dict[str, Any]]:
    signal_kind = str(signal.get("signal_kind") or "")
    situation_type = WORLD_STATE_SIGNAL_TO_SITUATION_TYPE.get(signal_kind)
    signal_id = _bounded_str(signal.get("signal_id"), 160)
    if not situation_type or not signal_id:
        return None
    location_id = _bounded_str(signal.get("location_id"), 120)
    faction_id = _bounded_str(signal.get("faction_id"), 120)
    actor_ids: List[str] = []
    locations = [location_id] if location_id else []
    factions = [faction_id] if faction_id else []
    dedupe_key = _scope_key(
        situation_type=situation_type,
        actor_ids=actor_ids,
        locations=locations,
        factions=factions,
        fallback=signal_id,
    )
    severity = max(3, min(10, _clamp_int(signal.get("severity"), 0, 10, default=4)))
    return _normalise_situation(
        {
            "situation_id": _situation_id(run_seed, dedupe_key),
            "type": situation_type,
            "title": _default_title(situation_type),
            "status": "active" if severity >= 4 else "forming",
            "priority": severity,
            "severity": severity,
            "created_turn": turn_number,
            "updated_turn": turn_number,
            "originating_pressure_ids": [],
            "originating_world_event_ids": [],
            "involved_actor_ids": actor_ids,
            "involved_locations": locations,
            "involved_factions": factions,
            "objectives": SITUATION_OBJECTIVES.get(situation_type, ()),
            "blockers": SITUATION_BLOCKERS.get(situation_type, ()),
            "evidence_refs": [f"world_state:{signal_id}"],
            "progress": 0,
            "expiry": turn_number + DEFAULT_EXPIRY_TURNS,
            "source_event_ids": [signal_id],
            "dedupe_key": dedupe_key,
            "last_reinforced_turn": turn_number,
            "inactive_turns": 0,
        },
        run_seed=run_seed,
    )


def _candidate_from_world_event(event: Mapping[str, Any], *, turn_number: int, run_seed: str) -> Optional[Dict[str, Any]]:
    engine_event_type = str(event.get("event_type") or "")
    if engine_event_type not in {"pressure_world_event", "npc_action_event", "world_event"}:
        return None
    event_id = _bounded_str(event.get("event_id"), 160)
    if not event_id:
        return None
    world_event_id = _bounded_str(event.get("world_event_id"), 160)
    situation_type = _situation_type_for_event(event.get("world_event_type") or _event_kind(event))
    actor_ids, locations, factions = _refs_from_event(event)
    pressure_id = _bounded_str(event.get("pressure_node_id"), 160)
    originating_world_event_id = world_event_id or event_id
    dedupe_key = _scope_key(
        situation_type=situation_type,
        actor_ids=actor_ids,
        locations=locations,
        factions=factions,
        fallback=originating_world_event_id or pressure_id or _event_kind(event) or situation_type,
    )
    severity = max(3, min(10, round(_clamp_int(event.get("magnitude"), 0, 100, default=50) / 10)))
    return _normalise_situation(
        {
            "situation_id": _situation_id(run_seed, dedupe_key),
            "type": situation_type,
            "title": _default_title(situation_type),
            "status": "active",
            "priority": severity,
            "severity": severity,
            "created_turn": turn_number,
            "updated_turn": turn_number,
            "originating_pressure_ids": [pressure_id] if pressure_id else [],
            "originating_world_event_ids": [originating_world_event_id],
            "involved_actor_ids": actor_ids,
            "involved_locations": locations,
            "involved_factions": factions,
            "objectives": SITUATION_OBJECTIVES.get(situation_type, ()),
            "blockers": SITUATION_BLOCKERS.get(situation_type, ()),
            "evidence_refs": [f"world_event:{originating_world_event_id}"],
            "progress": 0,
            "expiry": turn_number + DEFAULT_EXPIRY_TURNS,
            "source_event_ids": [event_id],
            "dedupe_key": dedupe_key,
            "last_reinforced_turn": turn_number,
            "inactive_turns": 0,
        },
        run_seed=run_seed,
    )


def _situation_summary(row: Mapping[str, Any]) -> Dict[str, Any]:
    if not row:
        return {}
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
    situation_id: str,
    detail: str = "",
    source_event_ids: Optional[Sequence[str]] = None,
) -> str:
    sources = ",".join(sorted(_bounded_str_list(source_event_ids or [], MAX_SITUATION_REFS)))
    return _stable_id("situation-receipt", receipt_type, turn_number, situation_id, detail, sources)


def _append_receipt(
    replayability_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    receipt_type: str,
    turn_number: int,
    situation: Mapping[str, Any],
    before: Optional[Mapping[str, Any]] = None,
    after: Optional[Mapping[str, Any]] = None,
    detail: str = "",
    source_event_ids: Optional[Sequence[str]] = None,
) -> bool:
    if receipt_type not in SITUATION_RECEIPT_TYPES:
        return False
    situation_id = _bounded_str(situation.get("situation_id"), 160)
    if not situation_id:
        return False
    rid = _receipt_id(
        receipt_type,
        turn_number=turn_number,
        situation_id=situation_id,
        detail=detail,
        source_event_ids=source_event_ids,
    )
    receipts = replayability_state.setdefault("situation_receipts", [])
    if any(isinstance(row, Mapping) and row.get("receipt_id") == rid for row in receipts):
        return False
    receipt = {
        "version": SITUATION_ENGINE_VERSION,
        "receipt_id": rid,
        "receipt_type": receipt_type,
        "turn": turn_number,
        "situation_id": situation_id,
        "situation_type": situation.get("type"),
        "detail": _bounded_str(detail, 120),
    }
    change = _summary_change(_situation_summary(before or {}), _situation_summary(after or situation))
    if change:
        receipt["change"] = change
    source_ids = _bounded_str_list(source_event_ids or situation.get("source_event_ids"), MAX_SITUATION_REFS)
    if source_ids:
        receipt["source_event_ids"] = source_ids
    receipts.append(receipt)
    if len(receipts) > MAX_SITUATION_RECEIPTS:
        replayability_state["situation_receipts"] = receipts[-MAX_SITUATION_RECEIPTS:]
    local_receipts.append(receipt)
    return True


def _merge_unique(existing: Dict[str, Any], incoming: Mapping[str, Any], key: str, limit: int = MAX_SITUATION_REFS) -> bool:
    before = list(existing.get(key) or [])
    merged = _bounded_str_list(before + list(incoming.get(key) or []), limit)
    existing[key] = merged
    return merged != before


def _find_existing(situations: Sequence[Dict[str, Any]], candidate: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    wanted_id = str(candidate.get("situation_id") or "")
    wanted_key = str(candidate.get("dedupe_key") or "")
    for row in situations:
        if row.get("status") in TERMINAL_STATUSES:
            continue
        if wanted_id and row.get("situation_id") == wanted_id:
            return row
        if wanted_key and row.get("dedupe_key") == wanted_key:
            return row
    return None


def _reinforce_situation(existing: Dict[str, Any], candidate: Mapping[str, Any], turn_number: int) -> bool:
    changed = False
    for key, limit in (
        ("originating_pressure_ids", MAX_SITUATION_REFS),
        ("originating_world_event_ids", MAX_SITUATION_REFS),
        ("involved_actor_ids", MAX_SITUATION_REFS),
        ("involved_locations", MAX_SITUATION_REFS),
        ("involved_factions", MAX_SITUATION_REFS),
        ("objectives", MAX_SITUATION_OBJECTIVES),
        ("blockers", MAX_SITUATION_BLOCKERS),
        ("evidence_refs", MAX_SITUATION_EVIDENCE_REFS),
        ("source_event_ids", MAX_SITUATION_REFS),
    ):
        changed = _merge_unique(existing, candidate, key, limit) or changed
    severity = max(_clamp_int(existing.get("severity"), 0, 10), _clamp_int(candidate.get("severity"), 0, 10))
    priority = max(_clamp_int(existing.get("priority"), 0, 10), _clamp_int(candidate.get("priority"), 0, 10))
    if severity != existing.get("severity"):
        existing["severity"] = severity
        changed = True
    if priority != existing.get("priority"):
        existing["priority"] = priority
        changed = True
    if existing.get("status") == "forming" and severity >= 4:
        existing["status"] = "active"
        changed = True
    if changed:
        existing["updated_turn"] = turn_number
    existing["last_reinforced_turn"] = turn_number
    existing["inactive_turns"] = 0
    return changed


def _pressure_statuses(replayability_state: Mapping[str, Any]) -> Dict[str, str]:
    graph = replayability_state.get("pressure_graph") if isinstance(replayability_state, Mapping) else {}
    statuses: Dict[str, str] = {}
    for node in (graph or {}).get("nodes") or []:
        if isinstance(node, Mapping) and node.get("id"):
            statuses[str(node.get("id"))] = str(node.get("status") or "")
    return statuses


def _pressure_receipts_by_node(replayability_state: Mapping[str, Any], turn_number: int) -> Dict[str, List[str]]:
    graph = replayability_state.get("pressure_graph") if isinstance(replayability_state, Mapping) else {}
    out: Dict[str, List[str]] = {}
    for receipt in (graph or {}).get("evolution_receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        if _coerce_int(receipt.get("turn"), -1) != turn_number:
            continue
        node_id = _bounded_str(receipt.get("node_id"), 160)
        receipt_type = _bounded_str(receipt.get("receipt_type"), 80)
        if node_id and receipt_type:
            out.setdefault(node_id, []).append(receipt_type)
    return out


def _advance_existing_situation(
    situation: Dict[str, Any],
    *,
    replayability_state: Mapping[str, Any],
    turn_number: int,
) -> Optional[Tuple[str, str, Dict[str, Any], Dict[str, Any]]]:
    if situation.get("status") in TERMINAL_STATUSES:
        return None
    if situation.get("last_evolved_turn") == turn_number:
        return None
    before = copy.deepcopy(situation)
    pressure_ids = _bounded_str_list(situation.get("originating_pressure_ids"), MAX_SITUATION_REFS)
    statuses = _pressure_statuses(replayability_state)
    receipt_types = _pressure_receipts_by_node(replayability_state, turn_number)
    active_pressure_count = sum(1 for pid in pressure_ids if statuses.get(pid) == "active")
    reduced = any(
        receipt_type in {"pressure_reduced", "pressure_resolved"}
        for pid in pressure_ids
        for receipt_type in receipt_types.get(pid, [])
    )
    resolved = bool(pressure_ids) and active_pressure_count == 0 and all(statuses.get(pid) in {"resolved", "reduced", "archived", ""} for pid in pressure_ids)

    receipt_type = ""
    detail = ""
    if reduced or resolved:
        situation["progress"] = _clamp_int(situation.get("progress"), 0, 100) + (35 if resolved else 20)
        situation["progress"] = min(100, situation["progress"])
        situation["severity"] = max(0, _clamp_int(situation.get("severity"), 0, 10) - (2 if resolved else 1))
        situation["status"] = "resolved" if situation["progress"] >= 100 or situation["severity"] <= 0 else "resolving"
        situation["updated_turn"] = turn_number
        situation["inactive_turns"] = 0
        receipt_type = "situation_resolved" if situation["status"] == "resolved" else "situation_progressed"
        detail = "pressure_mitigation"
    else:
        inactive = max(0, _coerce_int(situation.get("inactive_turns"), 0)) + 1
        situation["inactive_turns"] = inactive
        if inactive >= DECAY_AFTER_INACTIVE_TURNS and _clamp_int(situation.get("severity"), 0, 10) <= 4:
            situation["progress"] = min(100, _clamp_int(situation.get("progress"), 0, 100) + 5)
            situation["severity"] = max(0, _clamp_int(situation.get("severity"), 0, 10) - 1)
            situation["status"] = "resolved" if situation["severity"] <= 0 and situation["progress"] >= 50 else "resolving"
            situation["updated_turn"] = turn_number
            receipt_type = "situation_resolved" if situation["status"] == "resolved" else "situation_decayed"
            detail = "inactive_decay"
        elif turn_number >= _coerce_int(situation.get("expiry"), turn_number + 1):
            situation["status"] = "failed"
            situation["priority"] = min(_clamp_int(situation.get("priority"), 0, 10), 2)
            situation["updated_turn"] = turn_number
            receipt_type = "situation_failed"
            detail = "expired"

    situation["last_evolved_turn"] = turn_number
    if receipt_type and before != situation:
        return receipt_type, detail, before, copy.deepcopy(situation)
    return None


def _merge_duplicate_situations(
    replayability_state: Dict[str, Any],
    situations: List[Dict[str, Any]],
    local_receipts: List[Dict[str, Any]],
    turn_number: int,
    remaining_changes: int,
) -> int:
    by_key: Dict[str, Dict[str, Any]] = {}
    for situation in sorted(
        situations,
        key=lambda row: (_coerce_int(row.get("created_turn"), 0), str(row.get("situation_id") or "")),
    ):
        if situation.get("status") in TERMINAL_STATUSES:
            continue
        key = str(situation.get("dedupe_key") or "")
        if not key:
            continue
        primary = by_key.get(key)
        if primary is None:
            by_key[key] = situation
            continue
        if remaining_changes <= 0:
            break
        before = copy.deepcopy(primary)
        _reinforce_situation(primary, situation, turn_number)
        duplicate_before = copy.deepcopy(situation)
        situation["status"] = "resolved"
        situation["progress"] = 100
        situation["priority"] = min(_clamp_int(situation.get("priority"), 0, 10), 1)
        situation["updated_turn"] = turn_number
        situation["merged_into"] = primary.get("situation_id")
        _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type="situation_merged",
            turn_number=turn_number,
            situation=primary,
            before=before,
            after=primary,
            detail=f"merged:{situation.get('situation_id')}",
            source_event_ids=list(primary.get("source_event_ids") or []) + list(situation.get("source_event_ids") or []),
        )
        _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type="situation_resolved",
            turn_number=turn_number,
            situation=situation,
            before=duplicate_before,
            after=situation,
            detail="merged_duplicate",
            source_event_ids=situation.get("source_event_ids") or [],
        )
        remaining_changes -= 1
    return remaining_changes


def _cap_situations(situations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    active = [row for row in situations if row.get("status") not in TERMINAL_STATUSES]
    if len(active) > MAX_ACTIVE_SITUATIONS:
        overflow_ids = {
            row.get("situation_id")
            for row in sorted(
                active,
                key=lambda row: (
                    _clamp_int(row.get("priority"), 0, 10),
                    _clamp_int(row.get("severity"), 0, 10),
                    _coerce_int(row.get("updated_turn"), 0),
                    str(row.get("situation_id") or ""),
                ),
            )[: len(active) - MAX_ACTIVE_SITUATIONS]
        }
        for row in situations:
            if row.get("situation_id") in overflow_ids:
                row["status"] = "failed"
                row["priority"] = min(_clamp_int(row.get("priority"), 0, 10), 1)
    situations = [_compact_terminal_situation(row) for row in situations]
    if len(situations) > MAX_SITUATIONS:
        situations = sorted(
            situations,
            key=lambda row: (
                0 if row.get("status") not in TERMINAL_STATUSES else 1,
                -_clamp_int(row.get("priority"), 0, 10),
                -_clamp_int(row.get("severity"), 0, 10),
                -_coerce_int(row.get("updated_turn"), 0),
                str(row.get("situation_id") or ""),
            ),
        )[:MAX_SITUATIONS]
    return sorted(situations, key=lambda row: (_coerce_int(row.get("created_turn"), 0), str(row.get("situation_id") or "")))


def _compact_terminal_situation(row: Dict[str, Any]) -> Dict[str, Any]:
    if row.get("status") not in TERMINAL_STATUSES:
        return row
    keep = (
        "situation_id",
        "type",
        "title",
        "status",
        "priority",
        "severity",
        "progress",
        "created_turn",
        "updated_turn",
        "originating_pressure_ids",
        "originating_world_event_ids",
        "source_event_ids",
        "dedupe_key",
        "merged_into",
    )
    compact: Dict[str, Any] = {}
    for key in keep:
        value = row.get(key)
        if value is None or value == "" or value == []:
            continue
        compact[key] = copy.deepcopy(value)
    return compact


def _archive_terminal_situations(
    replayability_state: Dict[str, Any],
    situations: List[Dict[str, Any]],
    local_receipts: List[Dict[str, Any]],
    turn_number: int,
    remaining_changes: int,
) -> int:
    for situation in sorted(
        situations,
        key=lambda row: (_coerce_int(row.get("updated_turn"), 0), str(row.get("situation_id") or "")),
    ):
        if remaining_changes <= 0:
            break
        if situation.get("status") not in {"resolved", "failed"}:
            continue
        if turn_number - _coerce_int(situation.get("updated_turn"), turn_number) < ARCHIVE_AFTER_TERMINAL_TURNS:
            continue
        before = copy.deepcopy(situation)
        situation["status"] = "archived"
        situation["priority"] = min(_clamp_int(situation.get("priority"), 0, 10), 1)
        situation["updated_turn"] = turn_number
        if _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type="situation_archived",
            turn_number=turn_number,
            situation=situation,
            before=before,
            after=situation,
            detail="terminal_archive",
            source_event_ids=situation.get("source_event_ids") or [],
        ):
            remaining_changes -= 1
    return remaining_changes


def evolve_situations(
    replayability_state: Dict[str, Any],
    rolling_state: Mapping[str, Any],
    turn_number: int,
    *,
    run_seed: str = "",
) -> Dict[str, Any]:
    """Evaluate pressure/world state into bounded canonical situations."""
    diagnostics = {
        "situation_engine_executed": False,
        "situation_candidates_evaluated": 0,
        "situation_created": 0,
        "situation_reinforced": 0,
        "situation_merged": 0,
        "situation_progressed": 0,
        "situation_decayed": 0,
        "situation_resolved": 0,
        "situation_failed": 0,
        "situation_archived": 0,
        "situation_duplicate_suppressed": 0,
        "situation_recreated": 0,
    }
    if not isinstance(replayability_state, dict):
        return {"receipts": [], "diagnostics": diagnostics}

    seed = run_seed or str(replayability_state.get("run_seed") or "situation-engine")
    situations = [
        _normalise_situation(row, run_seed=seed)
        for row in replayability_state.get("situations") or []
        if isinstance(row, Mapping)
    ]
    replayability_state["situations"] = situations
    replayability_state.setdefault("situation_receipts", [])
    local_receipts: List[Dict[str, Any]] = []
    remaining_changes = MAX_SITUATION_CHANGES_PER_TICK
    evolved_this_turn_ids = set()

    candidates: List[Dict[str, Any]] = []
    graph = replayability_state.get("pressure_graph") if isinstance(replayability_state.get("pressure_graph"), Mapping) else {}
    pressure_nodes = [
        node for node in graph.get("nodes") or []
        if isinstance(node, Mapping)
    ]
    pressure_nodes.sort(
        key=lambda node: (
            -_clamp_int(node.get("magnitude"), 0, 100),
            str(node.get("id") or ""),
        )
    )
    for node in pressure_nodes:
        candidate = _candidate_from_pressure(node, turn_number=turn_number, run_seed=seed)
        if candidate:
            candidates.append(candidate)
        if len(candidates) >= MAX_SITUATION_INPUTS_PER_TICK:
            break

    events = [
        event for event in replayability_state.get("engine_world_events") or []
        if isinstance(event, Mapping)
    ]
    events.sort(key=lambda event: (_coerce_int(event.get("turn"), 0), str(event.get("event_id") or "")))
    for event in events:
        if len(candidates) >= MAX_SITUATION_INPUTS_PER_TICK:
            break
        candidate = _candidate_from_world_event(event, turn_number=turn_number, run_seed=seed)
        if candidate:
            candidates.append(candidate)

    if isinstance(rolling_state, Mapping):
        for signal in world_state_consumers.world_state_signals_for_context(rolling_state):
            if len(candidates) >= MAX_SITUATION_INPUTS_PER_TICK:
                break
            candidate = _candidate_from_world_state_signal(signal, turn_number=turn_number, run_seed=seed)
            if candidate:
                candidates.append(candidate)

    seen_candidate_keys = set()
    for candidate in candidates:
        diagnostics["situation_candidates_evaluated"] += 1
        key = (candidate.get("dedupe_key"), tuple(candidate.get("source_event_ids") or []))
        if key in seen_candidate_keys:
            diagnostics["situation_duplicate_suppressed"] += 1
            continue
        seen_candidate_keys.add(key)
        existing = _find_existing(situations, candidate)
        if existing is None:
            if remaining_changes <= 0 or len(situations) >= MAX_SITUATIONS:
                diagnostics["situation_duplicate_suppressed"] += 1
                continue
            generation = _assign_unique_situation_id(candidate, situations, seed)
            situations.append(candidate)
            if _append_receipt(
                replayability_state,
                local_receipts,
                receipt_type="situation_created",
                turn_number=turn_number,
                situation=candidate,
                before={},
                after=candidate,
                detail="created_from_engine_inputs",
                source_event_ids=candidate.get("source_event_ids") or [],
            ):
                diagnostics["situation_created"] += 1
                if generation > 0:
                    diagnostics["situation_recreated"] += 1
                evolved_this_turn_ids.add(str(candidate.get("situation_id") or ""))
                remaining_changes -= 1
            continue

        new_sources = [
            source_id
            for source_id in candidate.get("source_event_ids") or []
            if source_id not in (existing.get("source_event_ids") or [])
        ]
        if not new_sources and _clamp_int(candidate.get("severity"), 0, 10) <= _clamp_int(existing.get("severity"), 0, 10):
            diagnostics["situation_duplicate_suppressed"] += 1
            continue
        if remaining_changes <= 0:
            continue
        before = copy.deepcopy(existing)
        changed = _reinforce_situation(existing, candidate, turn_number)
        if changed:
            evolved_this_turn_ids.add(str(existing.get("situation_id") or ""))
        if changed and _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type="situation_reinforced",
            turn_number=turn_number,
            situation=existing,
            before=before,
            after=existing,
            detail="reinforced_from_engine_inputs",
            source_event_ids=new_sources or candidate.get("source_event_ids") or [],
        ):
            diagnostics["situation_reinforced"] += 1
            remaining_changes -= 1

    before_merge_receipts = len(local_receipts)
    remaining_changes = _merge_duplicate_situations(
        replayability_state,
        situations,
        local_receipts,
        turn_number,
        remaining_changes,
    )
    diagnostics["situation_merged"] += sum(
        1 for receipt in local_receipts[before_merge_receipts:]
        if receipt.get("receipt_type") == "situation_merged"
    )
    diagnostics["situation_resolved"] += sum(
        1 for receipt in local_receipts[before_merge_receipts:]
        if receipt.get("receipt_type") == "situation_resolved"
    )

    touched = {
        situation_id
        for situation_id in evolved_this_turn_ids
        if situation_id
    }
    for situation in sorted(
        situations,
        key=lambda row: (-_clamp_int(row.get("priority"), 0, 10), str(row.get("situation_id") or "")),
    ):
        if remaining_changes <= 0:
            break
        if str(situation.get("situation_id") or "") in touched:
            situation["last_evolved_turn"] = turn_number
            continue
        advanced = _advance_existing_situation(
            situation,
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
            situation=situation,
            before=before,
            after=after,
            detail=detail,
            source_event_ids=situation.get("source_event_ids") or [],
        ):
            if receipt_type == "situation_progressed":
                diagnostics["situation_progressed"] += 1
            elif receipt_type == "situation_decayed":
                diagnostics["situation_decayed"] += 1
            elif receipt_type == "situation_resolved":
                diagnostics["situation_resolved"] += 1
            elif receipt_type == "situation_failed":
                diagnostics["situation_failed"] += 1
            remaining_changes -= 1

    before_archive_receipts = len(local_receipts)
    remaining_changes = _archive_terminal_situations(
        replayability_state,
        situations,
        local_receipts,
        turn_number,
        remaining_changes,
    )
    diagnostics["situation_archived"] += sum(
        1 for receipt in local_receipts[before_archive_receipts:]
        if receipt.get("receipt_type") == "situation_archived"
    )

    replayability_state["situations"] = _cap_situations(situations)
    diagnostics["situation_engine_executed"] = bool(local_receipts or candidates or replayability_state["situations"])
    return {"receipts": local_receipts, "diagnostics": diagnostics}


def _pressure_nodes_by_id(replayability_state: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    graph = replayability_state.get("pressure_graph") if isinstance(replayability_state, Mapping) else {}
    out: Dict[str, Dict[str, Any]] = {}
    for node in (graph or {}).get("nodes") or []:
        if isinstance(node, Mapping) and node.get("id"):
            out[str(node.get("id"))] = dict(node)
    return out


def _refs_overlap(left: Sequence[str], right: Sequence[str]) -> bool:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    return bool(left_tokens.intersection(right_tokens))


def _humanize_token(value: Any) -> str:
    return _bounded_str(str(value or "").replace("_", " "), 80)


def _headline_for_situation(row: Mapping[str, Any]) -> str:
    title = _bounded_str(row.get("title"), 120)
    status = str(row.get("status") or "active")
    phrase = SITUATION_STATUS_PHRASES.get(status, status.replace("_", " "))
    locations = list(row.get("involved_locations") or [])
    if locations:
        return _bounded_str(f"{title} — {phrase} at {locations[0]}", 160)
    return _bounded_str(f"{title} — {phrase}", 160)


def _why_it_matters_for_situation(row: Mapping[str, Any], pressure_nodes: Mapping[str, Mapping[str, Any]]) -> str:
    situation_type = str(row.get("type") or "")
    base = WHY_IT_MATTERS_BY_TYPE.get(situation_type, "Conditions are worsening and consequences are spreading")
    severity = _clamp_int(row.get("severity"), 0, 10)
    blockers = list(row.get("blockers") or [])
    pressure_ids = _bounded_str_list(row.get("originating_pressure_ids"), MAX_SITUATION_REFS)
    rising = [
        _bounded_str(
            (pressure_nodes.get(pid) or {}).get("label")
            or (pressure_nodes.get(pid) or {}).get("kind")
            or pid,
            60,
        )
        for pid in pressure_ids
        if str((pressure_nodes.get(pid) or {}).get("status") or "") == "active"
    ]
    parts = [base]
    if severity >= 7:
        parts.append("severity is high")
    elif severity >= 4:
        parts.append("stakes are rising")
    if rising:
        parts.append(f"pressure from {rising[0]}")
    if blockers:
        parts.append(f"blocked by {_humanize_token(blockers[0])}")
    return _bounded_str("; ".join(parts), 200)


def _related_goals_for_situation(
    row: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    situation_id = str(row.get("situation_id") or "")
    actor_tokens = _token_set(row.get("involved_actor_ids"))
    location_tokens = _token_set(row.get("involved_locations"))
    faction_tokens = _token_set(row.get("involved_factions"))
    matched: List[Dict[str, Any]] = []
    for raw in replayability_state.get("goals") or []:
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("status") or "") in {"completed", "failed", "abandoned"}:
            continue
        parents = [str(item) for item in raw.get("parent_situation_ids") or []]
        applies = situation_id in parents
        if not applies and _refs_overlap(raw.get("target_actor_ids") or [], actor_tokens):
            applies = True
        if not applies and _refs_overlap(raw.get("target_location_ids") or [], location_tokens):
            applies = True
        if not applies and str(raw.get("owner_type") or "") == "faction" and str(raw.get("owner_id") or "").lower() in faction_tokens:
            applies = True
        if applies:
            steps = raw.get("plan_steps") if isinstance(raw.get("plan_steps"), list) else []
            idx = _clamp_int(raw.get("current_step_index"), 0, max(0, len(steps) - 1))
            next_step = _bounded_str((steps[idx] or {}).get("summary"), 120) if steps else ""
            matched.append(
                {
                    "title": _bounded_str(raw.get("title"), 120),
                    "status": raw.get("status"),
                    "priority": _clamp_int(raw.get("priority"), 0, 10),
                    "progress": _clamp_int(raw.get("progress"), 0, 100),
                    "next_step_summary": next_step,
                }
            )
    matched.sort(
        key=lambda goal: (
            -_clamp_int(goal.get("priority"), 0, 10),
            str(goal.get("title") or ""),
        )
    )
    return matched[:MAX_PROMOTED_GOALS]


def _related_information_for_situation(
    row: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    actor_tokens = _token_set(row.get("involved_actor_ids"))
    location_tokens = _token_set(row.get("involved_locations"))
    faction_tokens = _token_set(row.get("involved_factions"))
    rows = [
        raw
        for raw in replayability_state.get("information_items") or []
        if isinstance(raw, Mapping) and str(raw.get("status") or "active") not in {"archived", "expired"}
    ]
    matched: List[Dict[str, Any]] = []
    for raw in rows:
        subject_ids = {
            str(ref.get("subject_id") or "").lower()
            for ref in raw.get("subject_refs") or []
            if isinstance(ref, Mapping)
        }
        applies = bool(subject_ids.intersection(actor_tokens | location_tokens | faction_tokens))
        anchor = raw.get("anchor") if isinstance(raw.get("anchor"), Mapping) else {}
        anchor_ids = _token_set(
            list(anchor.get("location_ids") or [])
            + list(anchor.get("actor_ids") or [])
            + list(anchor.get("faction_ids") or [])
        )
        if not applies:
            applies = bool(anchor_ids.intersection(actor_tokens | location_tokens | faction_tokens))
        if applies:
            matched.append(
                {
                    "information_type": raw.get("information_type"),
                    "summary": _bounded_str(raw.get("summary"), 160),
                    "reliability_band": raw.get("reliability_band"),
                }
            )
    matched.sort(key=lambda item: (_bounded_str(item.get("summary"), 160), str(item.get("information_type") or "")))
    return matched[:MAX_PROMOTED_INFORMATION]


def _related_world_events_for_situation(
    row: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    wanted = _token_set(row.get("originating_world_event_ids"))
    location_tokens = _token_set(row.get("involved_locations"))
    faction_tokens = _token_set(row.get("involved_factions"))
    matched: List[Dict[str, Any]] = []
    for store_key in ("world_events", "engine_world_events"):
        for raw in replayability_state.get(store_key) or []:
            if not isinstance(raw, Mapping):
                continue
            event_id = str(raw.get("world_event_id") or raw.get("event_id") or "")
            applies = event_id and event_id.lower() in wanted
            if not applies:
                applies = _refs_overlap(raw.get("location_ids") or raw.get("affected_locations") or [], location_tokens)
            if not applies:
                applies = _refs_overlap(raw.get("faction_ids") or raw.get("affected_factions") or [], faction_tokens)
            if not applies:
                continue
            title = _bounded_str(
                raw.get("title")
                or raw.get("pressure_event_kind")
                or raw.get("world_event_type")
                or raw.get("event_type")
                or "world event",
                120,
            )
            matched.append(
                {
                    "title": title,
                    "status": raw.get("status") or "active",
                    "severity": _clamp_int(raw.get("severity") or raw.get("magnitude"), 0, 10, default=0),
                }
            )
    matched.sort(
        key=lambda event: (
            -_clamp_int(event.get("severity"), 0, 10),
            str(event.get("title") or ""),
        )
    )
    deduped: List[Dict[str, Any]] = []
    seen_titles = set()
    for event in matched:
        title = str(event.get("title") or "")
        if title in seen_titles:
            continue
        seen_titles.add(title)
        deduped.append(event)
    return deduped[:MAX_PROMOTED_WORLD_EVENTS]


def _relationship_shifts_for_situation(
    row: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
    *,
    rolling_state: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    actor_tokens = _token_set(row.get("involved_actor_ids"))
    location_tokens = _token_set(row.get("involved_locations"))
    relevant_names: set = set()
    if isinstance(rolling_state, Mapping):
        for npc in rolling_state.get("npcs") or []:
            if not isinstance(npc, Mapping):
                continue
            npc_id = str(npc.get("npc_id") or "").lower()
            npc_name = str(npc.get("name") or "").strip()
            npc_location = str(npc.get("location_id") or "").lower()
            if not npc_name:
                continue
            if actor_tokens and npc_id in actor_tokens:
                relevant_names.add(npc_name)
            elif location_tokens and npc_location in location_tokens:
                relevant_names.add(npc_name)
    matched: List[Dict[str, Any]] = []
    for raw in replayability_state.get("relationship_effect_receipts") or []:
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("receipt_type") or "") != "relationship_threshold_crossed":
            continue
        npc_name = str(raw.get("npc_name") or "").strip()
        if not npc_name or npc_name not in relevant_names:
            continue
        matched.append(
            {
                "npc_name": _bounded_str(npc_name, 80),
                "before_state": raw.get("before_state"),
                "after_state": raw.get("after_state"),
            }
        )
    matched.sort(key=lambda shift: (str(shift.get("npc_name") or ""), str(shift.get("after_state") or "")))
    return matched[:MAX_PROMOTED_RELATIONSHIP_SHIFTS]


def _world_state_signals_for_situation(
    row: Mapping[str, Any],
    rolling_state: Optional[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    if not isinstance(rolling_state, Mapping):
        return []
    locations = list(row.get("involved_locations") or [])
    factions = list(row.get("involved_factions") or [])
    if not locations and not factions:
        locations = [_bounded_str(rolling_state.get("scene") or rolling_state.get("location"), 120)]
    matched = world_state_consumers.world_state_signals_for_context(
        rolling_state,
        location_ids=locations,
        faction_ids=factions,
    )
    return [
        {
            "signal_kind": signal.get("signal_kind"),
            "signal_id": signal.get("signal_id"),
            "severity": signal.get("severity"),
            "status": signal.get("status"),
        }
        for signal in matched
    ]


def _evidence_exposure_signals_for_situation(
    row: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    investigation_state = {
        "investigations": replayability_state.get("investigations") or [],
        "evidence": replayability_state.get("evidence") or [],
    }
    information_state = {
        "information_items": replayability_state.get("information_items") or [],
        "reputation_signals": replayability_state.get("reputation_signals") or [],
    }
    situation_id = _bounded_str(row.get("situation_id"), 160)
    locations = list(row.get("involved_locations") or [])
    actors = list(row.get("involved_actor_ids") or [])
    matched = investigation_engine.evidence_exposure_signals_for_context(
        investigation_state,
        information_state=information_state,
        actor_ids=actors,
        location_ids=locations,
    )
    if situation_id:
        case_ids = {
            _bounded_str(inv.get("investigation_id"), 160)
            for inv in investigation_state.get("investigations") or []
            if isinstance(inv, Mapping) and inv.get("situation_id") == situation_id
        }
        if case_ids:
            matched = [
                signal
                for signal in matched
                if str(signal.get("investigation_id") or "") in case_ids
                or not signal.get("investigation_id")
            ]
    return [
        {
            "exposure_kind": signal.get("exposure_kind"),
            "signal_id": signal.get("signal_id"),
            "actor_id": signal.get("actor_id"),
            "behaviours": list(signal.get("behaviours") or [])[:4],
            "severity": signal.get("severity"),
        }
        for signal in matched
    ]


def _ambition_signals_for_situation(
    row: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
    *,
    rolling_state: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    actors = list(row.get("involved_actor_ids") or [])
    matched = npc_agendas.ambition_signals_for_context(
        replayability_state.get("npc_agendas") or {},
        actor_ids=actors,
        rolling_state=rolling_state,
    )
    return [
        {
            "ambition_kind": signal.get("ambition_kind"),
            "signal_id": signal.get("signal_id"),
            "npc_id": signal.get("npc_id"),
            "plan_kind": signal.get("plan_kind"),
            "progress": signal.get("progress"),
        }
        for signal in matched
    ]


def _player_opportunities_for_situation(
    row: Mapping[str, Any],
    related_goals: Sequence[Mapping[str, Any]],
    *,
    world_state_signals: Sequence[Mapping[str, Any]] = (),
    evidence_exposure_signals: Sequence[Mapping[str, Any]] = (),
    ambition_signals: Sequence[Mapping[str, Any]] = (),
) -> List[str]:
    opportunities: List[str] = []
    for label in npc_agendas.ambition_opportunity_labels(ambition_signals):
        if label not in opportunities:
            opportunities.append(label)
        if len(opportunities) >= MAX_PROMOTED_OPPORTUNITIES:
            return opportunities[:MAX_PROMOTED_OPPORTUNITIES]
    for label in investigation_engine.evidence_exposure_opportunity_labels(evidence_exposure_signals):
        if label not in opportunities:
            opportunities.append(label)
        if len(opportunities) >= MAX_PROMOTED_OPPORTUNITIES:
            return opportunities[:MAX_PROMOTED_OPPORTUNITIES]
    for label in world_state_consumers.world_state_opportunity_labels(world_state_signals):
        if label not in opportunities:
            opportunities.append(label)
        if len(opportunities) >= MAX_PROMOTED_OPPORTUNITIES:
            return opportunities[:MAX_PROMOTED_OPPORTUNITIES]
    for objective in row.get("objectives") or []:
        text = _humanize_token(objective)
        if text and text not in opportunities:
            opportunities.append(text)
        if len(opportunities) >= MAX_PROMOTED_OPPORTUNITIES:
            return opportunities[:MAX_PROMOTED_OPPORTUNITIES]
    for goal in related_goals:
        next_step = _bounded_str(goal.get("next_step_summary"), 120)
        if next_step and next_step not in opportunities:
            opportunities.append(next_step)
        if len(opportunities) >= MAX_PROMOTED_OPPORTUNITIES:
            break
    for blocker in row.get("blockers") or []:
        text = f"address {_humanize_token(blocker)}"
        if text not in opportunities:
            opportunities.append(text)
        if len(opportunities) >= MAX_PROMOTED_OPPORTUNITIES:
            break
    return opportunities[:MAX_PROMOTED_OPPORTUNITIES]


def _pressure_labels_for_situation(
    row: Mapping[str, Any],
    pressure_nodes: Mapping[str, Mapping[str, Any]],
) -> List[str]:
    labels: List[str] = []
    for pressure_id in _bounded_str_list(row.get("originating_pressure_ids"), MAX_SITUATION_REFS):
        node = pressure_nodes.get(pressure_id) or {}
        label = _bounded_str(node.get("label") or node.get("kind") or pressure_id, 80)
        if label and label not in labels:
            labels.append(label)
        if len(labels) >= MAX_PROMOTED_PRESSURE_LABELS:
            break
    return labels


def _affected_actors_for_situation(
    row: Mapping[str, Any],
    related_goals: Sequence[Mapping[str, Any]],
    relationship_shifts: Sequence[Mapping[str, Any]],
) -> List[str]:
    actors = _bounded_str_list(row.get("involved_actor_ids"), MAX_PROMOTED_ACTORS)
    for shift in relationship_shifts:
        npc_name = _bounded_str(shift.get("npc_name"), 80)
        if npc_name and npc_name not in actors:
            actors.append(npc_name)
        if len(actors) >= MAX_PROMOTED_ACTORS:
            break
    return actors[:MAX_PROMOTED_ACTORS]


def project_promoted_situation(
    row: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
    *,
    rolling_state: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Aggregate canonical engine state into one player-facing situation projection."""
    pressure_nodes = _pressure_nodes_by_id(replayability_state)
    related_goals = _related_goals_for_situation(row, replayability_state)
    related_information = _related_information_for_situation(row, replayability_state)
    related_world_events = _related_world_events_for_situation(row, replayability_state)
    relationship_shifts = _relationship_shifts_for_situation(
        row,
        replayability_state,
        rolling_state=rolling_state,
    )
    world_state_signals = _world_state_signals_for_situation(row, rolling_state)
    evidence_exposure_signals = _evidence_exposure_signals_for_situation(row, replayability_state)
    ambition_signals = _ambition_signals_for_situation(
        row,
        replayability_state,
        rolling_state=rolling_state,
    )
    return {
        "situation_id": row.get("situation_id"),
        "type": row.get("type"),
        "title": row.get("title"),
        "status": row.get("status"),
        "priority": row.get("priority"),
        "severity": row.get("severity"),
        "progress": row.get("progress"),
        "headline": _headline_for_situation(row),
        "why_it_matters": _why_it_matters_for_situation(row, pressure_nodes),
        "affected_actors": _affected_actors_for_situation(row, related_goals, relationship_shifts),
        "affected_locations": list(row.get("involved_locations") or [])[:MAX_SITUATION_REFS],
        "affected_factions": list(row.get("involved_factions") or [])[:MAX_SITUATION_REFS],
        "objectives": list(row.get("objectives") or [])[:MAX_SITUATION_OBJECTIVES],
        "blockers": list(row.get("blockers") or [])[:MAX_SITUATION_BLOCKERS],
        "player_opportunities": _player_opportunities_for_situation(
            row,
            related_goals,
            world_state_signals=world_state_signals,
            evidence_exposure_signals=evidence_exposure_signals,
            ambition_signals=ambition_signals,
        ),
        "related_goals": related_goals,
        "related_information": related_information,
        "pressure_labels": _pressure_labels_for_situation(row, pressure_nodes),
        "related_world_events": related_world_events,
        "relationship_shifts": relationship_shifts,
        "world_state_signals": world_state_signals,
        "world_state_opportunities": world_state_consumers.world_state_opportunity_labels(world_state_signals),
        "evidence_exposure_signals": evidence_exposure_signals,
        "evidence_exposure_behaviours": investigation_engine.evidence_exposure_opportunity_labels(
            evidence_exposure_signals
        ),
        "ambition_signals": ambition_signals,
        "ambition_opportunities": npc_agendas.ambition_opportunity_labels(ambition_signals),
    }


def project_promoted_situations_for_rolling(
    replayability_state: Mapping[str, Any],
    *,
    rolling_state: Optional[Mapping[str, Any]] = None,
    limit: int = MAX_PROJECTED_SITUATIONS,
    gravity_metadata: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Stage 6C-3 — player-facing situation collision layer (projection only)."""
    if not isinstance(replayability_state, Mapping):
        return []
    seed = str(replayability_state.get("run_seed") or "situation-engine")
    situations = [
        _normalise_situation(row, run_seed=seed)
        for row in replayability_state.get("situations") or []
        if isinstance(row, Mapping) and row.get("status") not in TERMINAL_STATUSES
    ]
    meta = gravity_metadata if isinstance(gravity_metadata, Mapping) else replayability_state.get("gravity_metadata")
    if meta:
        try:
            import runtime_scheduling

            if runtime_scheduling.scheduling_enabled():
                situations = [
                    row
                    for row in situations
                    if runtime_scheduling.situation_projection_eligible(
                        str(row.get("situation_id") or ""),
                        meta,
                    )
                ]
        except Exception:
            pass
    ordered = sorted(
        situations,
        key=lambda row: (
            -_clamp_int(row.get("priority"), 0, 10),
            -_clamp_int(row.get("severity"), 0, 10),
            str(row.get("situation_id") or ""),
        ),
    )[: max(0, min(MAX_PROJECTED_SITUATIONS, int(limit or 0)))]
    return [
        project_promoted_situation(row, replayability_state, rolling_state=rolling_state)
        for row in ordered
    ]


def project_active_situations_for_rolling(
    replayability_state: Mapping[str, Any],
    *,
    rolling_state: Optional[Mapping[str, Any]] = None,
    limit: int = MAX_PROJECTED_SITUATIONS,
    gravity_metadata: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Bounded prompt-safe projection for rolling_state.active_situations."""
    return project_promoted_situations_for_rolling(
        replayability_state,
        rolling_state=rolling_state,
        limit=limit,
        gravity_metadata=gravity_metadata,
    )


def project_situations_for_prompt(
    replayability_state: Mapping[str, Any],
    *,
    rolling_state: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    return project_promoted_situations_for_rolling(
        replayability_state,
        rolling_state=rolling_state,
        limit=MAX_PROMPT_SITUATIONS,
    )


def prompt_safe_rolling_state(rolling_state: Mapping[str, Any]) -> Dict[str, Any]:
    """Strip situation internals from a rolling_state copy."""
    if not isinstance(rolling_state, Mapping):
        return {}
    safe = copy.deepcopy(dict(rolling_state))
    rows = safe.get("active_situations")
    if not isinstance(rows, list):
        return safe
    cleaned: List[Dict[str, Any]] = []
    for row in rows[:MAX_PROMPT_SITUATIONS]:
        if not isinstance(row, Mapping):
            continue
        cleaned.append(
            {
                key: copy.deepcopy(row.get(key))
                for key in PROMOTED_SITUATION_FIELDS
                if key in row
            }
        )
    safe["active_situations"] = cleaned
    return safe


def copy_situation_state(replayability_state: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(replayability_state, Mapping):
        return {"situations": []}
    seed = str(replayability_state.get("run_seed") or "situation-engine")
    situations = [
        _normalise_situation(row, run_seed=seed)
        for row in replayability_state.get("situations") or []
        if isinstance(row, Mapping)
    ]
    return {"situations": _cap_situations(situations)}


def _token_set(*values: Any) -> set:
    out = set()
    for value in values:
        raw = value if isinstance(value, (list, tuple, set)) else [value]
        for item in raw:
            text = str(item or "").strip().lower()
            if text:
                out.add(text)
    return out


def _situation_ref_sets(row: Mapping[str, Any]) -> Dict[str, set]:
    return {
        "actor": _token_set(row.get("involved_actor_ids")),
        "location": _token_set(row.get("involved_locations")),
        "faction": _token_set(row.get("involved_factions")),
        "situation": _token_set(row.get("situation_id")),
    }


def active_situations_for_context(
    situation_state: Mapping[str, Any],
    *,
    actor_ids: Sequence[str] = (),
    location_ids: Sequence[str] = (),
    faction_ids: Sequence[str] = (),
    situation_ids: Sequence[str] = (),
    limit: int = MAX_CONTEXT_SITUATIONS,
) -> List[Dict[str, Any]]:
    """Return active situations affecting the supplied deterministic context."""
    if not isinstance(situation_state, Mapping):
        return []
    context = {
        "actor": _token_set(actor_ids),
        "location": _token_set(location_ids),
        "faction": _token_set(faction_ids),
        "situation": _token_set(situation_ids),
    }
    matched: List[Dict[str, Any]] = []
    for raw in situation_state.get("situations") or []:
        if not isinstance(raw, Mapping):
            continue
        row = _normalise_situation(raw)
        if row.get("status") in TERMINAL_STATUSES:
            continue
        refs = _situation_ref_sets(row)
        has_specific_refs = any(refs[key] for key in ("actor", "location", "faction"))
        applies = any(refs[key].intersection(context.get(key, set())) for key in refs)
        if applies or not has_specific_refs:
            matched.append(row)
    ordered = sorted(
        matched,
        key=lambda row: (
            -_clamp_int(row.get("priority"), 0, 10),
            -_clamp_int(row.get("severity"), 0, 10),
            str(row.get("situation_id") or ""),
        ),
    )
    return ordered[: max(0, min(MAX_CONTEXT_SITUATIONS, int(limit or 0)))]
