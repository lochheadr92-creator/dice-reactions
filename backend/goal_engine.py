"""
Deterministic Goal Engine.

Goals are engine-owned multi-turn objectives derived from canonical situations.
The LLM may narrate visible behavior, but it never owns goal creation, progress,
completion, priority, or planning.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import investigation_engine
import npc_agendas
import world_state_consumers

GOAL_ENGINE_VERSION = 1

MAX_GOALS = 16
MAX_ACTIVE_GOALS = 10
MAX_GOAL_INPUTS_PER_TICK = 8
MAX_GOAL_CHANGES_PER_TICK = 6
# Keep one recent provenance receipt per retained canonical goal.
MAX_GOAL_RECEIPTS = 16
MAX_GOAL_REFS = 8
MAX_GOAL_RESOURCES = 4
MAX_GOAL_BLOCKERS = 4
MAX_GOAL_PREREQUISITES = 4
MAX_GOAL_EVIDENCE_REFS = 8
MAX_PLAN_STEPS = 6
MAX_PROJECTED_GOALS = 6
MAX_PROMPT_GOALS = 4
MAX_CONTEXT_GOALS = 4

DEFAULT_EXPIRY_TURNS = 16
ABANDON_AFTER_INACTIVE_TURNS = 3

GOAL_STATUSES = ("forming", "active", "blocked", "completed", "failed", "abandoned")
TERMINAL_STATUSES = frozenset({"completed", "failed", "abandoned"})

GOAL_RECEIPT_TYPES = (
    "goal_created",
    "goal_reinforced",
    "goal_merged",
    "goal_progressed",
    "goal_blocked",
    "goal_completed",
    "goal_failed",
    "goal_abandoned",
)

SITUATION_TYPE_TO_GOAL_TYPE = {
    "missing_child": "rescue_missing_person",
    "search_party": "rescue_missing_person",
    "murder_investigation": "find_murderer",
    "food_shortage": "secure_food",
    "gang_turf_war": "remove_rival_influence",
    "political_unrest": "defend_settlement",
    "disease_outbreak": "contain_disease",
    "flood_recovery": "restore_route",
    "bandit_activity": "secure_trade_route",
    "trade_opportunity": "secure_trade_route",
}

GOAL_TITLES = {
    "rescue_missing_person": "Rescue Missing Person",
    "escape_city": "Escape the City",
    "secure_food": "Earn Enough Food",
    "protect_family": "Protect Family",
    "find_murderer": "Find Murderer",
    "hide_evidence": "Hide Evidence",
    "build_shelter": "Build Shelter",
    "capture_district": "Capture District",
    "recruit_members": "Recruit Members",
    "secure_trade_route": "Secure Trade Route",
    "remove_rival_influence": "Remove Rival Influence",
    "defend_settlement": "Defend Settlement",
    "contain_disease": "Contain Disease",
    "restore_route": "Restore Route",
}

GOAL_REQUIRED_RESOURCES = {
    "secure_food": ("food",),
    "build_shelter": ("materials",),
    "rescue_missing_person": ("witness", "allies"),
    "secure_trade_route": ("route_access",),
    "defend_settlement": ("defenders",),
    "contain_disease": ("medicine",),
    "restore_route": ("materials",),
}

GOAL_PREREQUISITES = {
    "rescue_missing_person": ("last_seen_location",),
    "find_murderer": ("evidence",),
    "hide_evidence": ("evidence",),
    "capture_district": ("staging_area",),
    "remove_rival_influence": ("rival_identified",),
    "contain_disease": ("affected_cases_identified",),
}

PLAN_TEMPLATES = {
    "rescue_missing_person": (
        ("locate_witness", "Locate witness", ("investigate", "negotiate")),
        ("search_area", "Search likely area", ("investigate", "gather")),
        ("gather_allies", "Gather allies", ("gather", "negotiate")),
        ("travel", "Move toward target", ("withdraw", "protect")),
        ("recover_person", "Recover missing person", ("protect", "investigate")),
        ("return_safe", "Return safely", ("protect", "withdraw")),
    ),
    "secure_food": (
        ("assess_need", "Assess need", ("investigate",)),
        ("locate_supplies", "Locate supplies", ("gather", "investigate")),
        ("secure_trade", "Secure exchange", ("negotiate", "gather")),
        ("protect_supply", "Protect supply", ("protect", "fortify")),
    ),
    "find_murderer": (
        ("collect_evidence", "Collect evidence", ("investigate", "gather")),
        ("question_witness", "Question witness", ("negotiate", "pressure")),
        ("identify_suspect", "Identify suspect", ("investigate",)),
        ("confront_truth", "Confront truth", ("pressure", "protect")),
    ),
    "hide_evidence": (
        ("identify_evidence", "Identify evidence", ("investigate",)),
        ("remove_trace", "Remove trace", ("conceal",)),
        ("misdirect_search", "Misdirect search", ("negotiate", "pressure", "conceal")),
    ),
    "build_shelter": (
        ("locate_site", "Locate site", ("investigate",)),
        ("gather_materials", "Gather materials", ("gather",)),
        ("reinforce_structure", "Reinforce structure", ("fortify", "protect")),
    ),
    "secure_trade_route": (
        ("scout_route", "Scout route", ("investigate",)),
        ("reduce_threat", "Reduce threat", ("protect", "fortify", "pressure")),
        ("negotiate_access", "Negotiate access", ("negotiate",)),
        ("maintain_route", "Maintain route", ("fortify", "gather")),
    ),
    "remove_rival_influence": (
        ("identify_rival", "Identify rival", ("investigate",)),
        ("build_support", "Build support", ("negotiate", "gather")),
        ("apply_pressure", "Apply pressure", ("pressure",)),
        ("secure_position", "Secure position", ("fortify", "protect")),
    ),
    "defend_settlement": (
        ("assess_threat", "Assess threat", ("investigate",)),
        ("prepare_defense", "Prepare defense", ("fortify", "gather")),
        ("protect_people", "Protect people", ("protect",)),
        ("stabilize_order", "Stabilize order", ("negotiate", "protect")),
    ),
    "contain_disease": (
        ("identify_cases", "Identify cases", ("investigate",)),
        ("gather_medicine", "Gather medicine", ("gather",)),
        ("separate_risk", "Separate risk", ("protect", "withdraw")),
        ("restore_health", "Restore health", ("protect", "gather")),
    ),
    "restore_route": (
        ("assess_damage", "Assess damage", ("investigate",)),
        ("gather_materials", "Gather materials", ("gather",)),
        ("clear_path", "Clear path", ("fortify", "protect")),
        ("reopen_route", "Reopen route", ("fortify", "negotiate")),
    ),
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


def _bounded_str_list(values: Any, limit: int = MAX_GOAL_REFS) -> List[str]:
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


def _goal_type_for_situation(situation: Mapping[str, Any]) -> str:
    return SITUATION_TYPE_TO_GOAL_TYPE.get(str(situation.get("type") or ""), "defend_settlement")


def _goal_title(goal_type: str) -> str:
    return GOAL_TITLES.get(goal_type, goal_type.replace("_", " ").title())


def _owner_for_situation(situation: Mapping[str, Any]) -> Tuple[str, str]:
    actors = _bounded_str_list(situation.get("involved_actor_ids"), MAX_GOAL_REFS)
    factions = _bounded_str_list(situation.get("involved_factions"), MAX_GOAL_REFS)
    locations = _bounded_str_list(situation.get("involved_locations"), MAX_GOAL_REFS)
    if actors:
        return "npc", actors[0]
    if factions:
        return "faction", factions[0]
    if locations:
        return "settlement", locations[0]
    return "world", "world"


def _dedupe_key(owner_type: str, owner_id: str, goal_type: str, target: str) -> str:
    return f"{owner_type}:{owner_id}:{goal_type}:{target or 'global'}"


def _goal_id(run_seed: str, dedupe_key: str) -> str:
    return _stable_id("goal", run_seed, dedupe_key)


def _goal_id_for_generation(run_seed: str, dedupe_key: str, generation: int) -> str:
    if generation <= 0:
        return _goal_id(run_seed, dedupe_key)
    return _stable_id("goal", run_seed, dedupe_key, "recreated", generation)


def _assign_unique_goal_id(candidate: Dict[str, Any], goals: Sequence[Mapping[str, Any]], run_seed: str) -> int:
    dedupe = _bounded_str(candidate.get("dedupe_key"), 220)
    if not dedupe:
        return 0
    existing_ids = {
        str(row.get("goal_id") or "")
        for row in goals
        if isinstance(row, Mapping) and row.get("goal_id")
    }
    generation = 0
    while True:
        goal_id = _goal_id_for_generation(run_seed, dedupe, generation)
        if goal_id not in existing_ids:
            candidate["goal_id"] = goal_id
            return generation
        generation += 1


def _normalise_status(value: Any, progress: int = 0) -> str:
    status = str(value or "").strip().lower()
    if status in GOAL_STATUSES:
        return status
    return "completed" if progress >= 100 else "active"


def _generate_plan(goal_type: str) -> List[Dict[str, Any]]:
    template = PLAN_TEMPLATES.get(goal_type) or PLAN_TEMPLATES["defend_settlement"]
    steps = []
    for idx, (step_key, summary, action_tags) in enumerate(template[:MAX_PLAN_STEPS]):
        steps.append(
            {
                "step_id": f"{idx + 1}:{step_key}",
                "order": idx,
                "summary": summary,
                "status": "active" if idx == 0 else "pending",
                "action_tags": list(action_tags)[:4],
            }
        )
    return steps


def _normalise_plan(goal_type: str, steps: Any) -> List[Dict[str, Any]]:
    if not isinstance(steps, list) or not steps:
        return _generate_plan(goal_type)
    out = []
    for idx, raw in enumerate(steps[:MAX_PLAN_STEPS]):
        if not isinstance(raw, Mapping):
            continue
        status = str(raw.get("status") or ("active" if idx == 0 else "pending"))
        if status not in {"pending", "active", "completed", "blocked"}:
            status = "pending"
        out.append(
            {
                "step_id": _bounded_str(raw.get("step_id") or f"{idx + 1}:step", 80),
                "order": _coerce_int(raw.get("order"), idx),
                "summary": _bounded_str(raw.get("summary") or "Advance goal", 120),
                "status": status,
                "action_tags": _bounded_str_list(raw.get("action_tags"), 4),
            }
        )
    return out or _generate_plan(goal_type)


def _current_step_index(plan_steps: Sequence[Mapping[str, Any]]) -> int:
    for idx, step in enumerate(plan_steps):
        if step.get("status") in {"active", "blocked"}:
            return idx
    for idx, step in enumerate(plan_steps):
        if step.get("status") == "pending":
            return idx
    return max(0, len(plan_steps) - 1)


def _next_step_summary(goal: Mapping[str, Any]) -> str:
    steps = goal.get("plan_steps") if isinstance(goal.get("plan_steps"), list) else []
    if not steps:
        return ""
    idx = _clamp_int(goal.get("current_step_index"), 0, max(0, len(steps) - 1))
    return _bounded_str((steps[idx] or {}).get("summary"), 120)


def _normalise_goal(row: Mapping[str, Any], *, run_seed: str = "") -> Dict[str, Any]:
    goal_type = _bounded_str(row.get("goal_type") or "defend_settlement", 80)
    owner_type = _bounded_str(row.get("owner_type") or "world", 40)
    owner_id = _bounded_str(row.get("owner_id") or "world", 160)
    target_locations = _bounded_str_list(row.get("target_location_ids"), MAX_GOAL_REFS)
    target_actors = _bounded_str_list(row.get("target_actor_ids"), MAX_GOAL_REFS)
    target = target_locations[0] if target_locations else target_actors[0] if target_actors else owner_id
    dedupe = _bounded_str(row.get("dedupe_key") or _dedupe_key(owner_type, owner_id, goal_type, target), 220)
    created_turn = max(0, _coerce_int(row.get("created_turn"), 0))
    updated_turn = max(created_turn, _coerce_int(row.get("updated_turn"), created_turn))
    progress = _clamp_int(row.get("progress"), 0, 100)
    plan_steps = _normalise_plan(goal_type, row.get("plan_steps"))
    current_idx = _clamp_int(row.get("current_step_index"), 0, max(0, len(plan_steps) - 1))
    return {
        "goal_id": _bounded_str(row.get("goal_id") or _goal_id(run_seed or "goal", dedupe), 160),
        "owner_type": owner_type if owner_type in {"npc", "faction", "settlement", "world"} else "world",
        "owner_id": owner_id,
        "goal_type": goal_type,
        "title": _bounded_str(row.get("title") or _goal_title(goal_type), 120),
        "status": _normalise_status(row.get("status"), progress),
        "priority": _clamp_int(row.get("priority"), 0, 10, default=5),
        "urgency": _clamp_int(row.get("urgency"), 0, 10, default=5),
        "progress": progress,
        "confidence": _clamp_int(row.get("confidence"), 0, 100, default=50),
        "created_turn": created_turn,
        "updated_turn": updated_turn,
        "parent_situation_ids": _bounded_str_list(row.get("parent_situation_ids"), MAX_GOAL_REFS),
        "supporting_pressure_ids": _bounded_str_list(row.get("supporting_pressure_ids"), MAX_GOAL_REFS),
        "target_actor_ids": target_actors,
        "target_location_ids": target_locations,
        "required_resources": _bounded_str_list(row.get("required_resources"), MAX_GOAL_RESOURCES),
        "blockers": _bounded_str_list(row.get("blockers"), MAX_GOAL_BLOCKERS),
        "prerequisites": _bounded_str_list(row.get("prerequisites"), MAX_GOAL_PREREQUISITES),
        "evidence_refs": _bounded_str_list(row.get("evidence_refs"), MAX_GOAL_EVIDENCE_REFS),
        "expiry": max(updated_turn, _coerce_int(row.get("expiry"), created_turn + DEFAULT_EXPIRY_TURNS)),
        "source_event_ids": _bounded_str_list(row.get("source_event_ids"), MAX_GOAL_REFS),
        "plan_steps": plan_steps,
        "current_step_index": current_idx,
        "dedupe_key": dedupe,
        "last_reinforced_turn": _coerce_int(row.get("last_reinforced_turn"), updated_turn),
        "last_evolved_turn": row.get("last_evolved_turn"),
        "inactive_turns": max(0, _coerce_int(row.get("inactive_turns"), 0)),
        "last_action_event_id": _bounded_str(row.get("last_action_event_id"), 160),
    }


def _candidate_from_situation(situation: Mapping[str, Any], *, turn_number: int, run_seed: str) -> Optional[Dict[str, Any]]:
    status = str(situation.get("status") or "")
    if status in {"resolved", "failed"}:
        return None
    situation_id = _bounded_str(situation.get("situation_id"), 160)
    if not situation_id:
        return None
    goal_type = _goal_type_for_situation(situation)
    owner_type, owner_id = _owner_for_situation(situation)
    target_locations = _bounded_str_list(situation.get("involved_locations"), MAX_GOAL_REFS)
    target_actors = _bounded_str_list(situation.get("involved_actor_ids"), MAX_GOAL_REFS)
    target = target_locations[0] if target_locations else target_actors[0] if target_actors else situation_id
    dedupe = _dedupe_key(owner_type, owner_id, goal_type, target)
    priority = _clamp_int(situation.get("priority"), 0, 10, default=5)
    severity = _clamp_int(situation.get("severity"), 0, 10, default=5)
    return _normalise_goal(
        {
            "goal_id": _goal_id(run_seed, dedupe),
            "owner_type": owner_type,
            "owner_id": owner_id,
            "goal_type": goal_type,
            "title": _goal_title(goal_type),
            "status": "active",
            "priority": max(priority, severity),
            "urgency": severity,
            "progress": 0,
            "confidence": min(100, 45 + severity * 5),
            "created_turn": turn_number,
            "updated_turn": turn_number,
            "parent_situation_ids": [situation_id],
            "supporting_pressure_ids": situation.get("originating_pressure_ids") or [],
            "target_actor_ids": target_actors,
            "target_location_ids": target_locations,
            "required_resources": GOAL_REQUIRED_RESOURCES.get(goal_type, ()),
            "blockers": situation.get("blockers") or [],
            "prerequisites": GOAL_PREREQUISITES.get(goal_type, ()),
            "evidence_refs": list(situation.get("evidence_refs") or []) + [f"situation:{situation_id}"],
            "expiry": turn_number + DEFAULT_EXPIRY_TURNS,
            "source_event_ids": [situation_id],
            "plan_steps": _generate_plan(goal_type),
            "dedupe_key": dedupe,
            "last_reinforced_turn": turn_number,
        },
        run_seed=run_seed,
    )


def _candidate_from_investigation(
    investigation: Mapping[str, Any],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    *,
    turn_number: int,
    run_seed: str,
) -> Optional[Dict[str, Any]]:
    if investigation.get("status") in investigation_engine.TERMINAL_STATUSES or investigation.get("archived"):
        return None
    investigation_id = _bounded_str(investigation.get("investigation_id"), 160)
    if not investigation_id:
        return None
    assigned_actors = _bounded_str_list(investigation.get("assigned_actor_ids"), MAX_GOAL_REFS)
    if not assigned_actors:
        return None
    evidence_ids = _bounded_str_list(investigation.get("evidence_ids"), MAX_GOAL_EVIDENCE_REFS)
    evidence_rows = [
        evidence_by_id[eid]
        for eid in evidence_ids
        if eid in evidence_by_id
    ]
    target_locations = _bounded_str_list(
        [row.get("location_id") for row in evidence_rows if row.get("location_id")],
        MAX_GOAL_REFS,
    )
    target_actors = _bounded_str_list(
        list(investigation.get("suspect_ids") or [])
        + [
            actor_id
            for row in evidence_rows
            for actor_id in (row.get("actor_ids") or [])
        ],
        MAX_GOAL_REFS,
    )
    owner_type = "npc"
    owner_id = assigned_actors[0]
    goal_type = "find_murderer"
    target = investigation_id
    dedupe = _dedupe_key(owner_type, owner_id, goal_type, target)
    priority = _clamp_int(investigation.get("priority"), 0, 10, default=5)
    confidence = _clamp_int(investigation.get("confidence"), 0, 100, default=40)
    urgency = max(3, min(10, confidence // 10 + (1 if evidence_ids else 0)))
    return _normalise_goal(
        {
            "goal_id": _goal_id(run_seed, dedupe),
            "owner_type": owner_type,
            "owner_id": owner_id,
            "goal_type": goal_type,
            "title": _goal_title(goal_type),
            "status": "active",
            "priority": priority,
            "urgency": urgency,
            "progress": min(80, _clamp_int(investigation.get("progress"), 0, 100)),
            "confidence": confidence,
            "created_turn": turn_number,
            "updated_turn": turn_number,
            "parent_situation_ids": [investigation.get("situation_id")] if investigation.get("situation_id") else [],
            "supporting_pressure_ids": [],
            "target_actor_ids": target_actors,
            "target_location_ids": target_locations,
            "required_resources": GOAL_REQUIRED_RESOURCES.get(goal_type, ()),
            "blockers": [],
            "prerequisites": () if evidence_ids else GOAL_PREREQUISITES.get(goal_type, ()),
            "evidence_refs": evidence_ids + [f"investigation:{investigation_id}"],
            "expiry": turn_number + DEFAULT_EXPIRY_TURNS,
            "source_event_ids": [investigation_id],
            "plan_steps": _generate_plan(goal_type),
            "dedupe_key": dedupe,
            "last_reinforced_turn": turn_number,
        },
        run_seed=run_seed,
    )


def _goal_summary(row: Mapping[str, Any]) -> Dict[str, Any]:
    if not row:
        return {}
    return {
        key: row.get(key)
        for key in ("status", "progress")
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
    goal_id: str,
    detail: str = "",
    source_event_ids: Optional[Sequence[str]] = None,
) -> str:
    sources = ",".join(sorted(_bounded_str_list(source_event_ids or [], MAX_GOAL_REFS)))
    return _stable_id("goal-receipt", receipt_type, turn_number, goal_id, detail, sources)


def _append_receipt(
    replayability_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    receipt_type: str,
    turn_number: int,
    goal: Mapping[str, Any],
    before: Optional[Mapping[str, Any]] = None,
    after: Optional[Mapping[str, Any]] = None,
    detail: str = "",
    source_event_ids: Optional[Sequence[str]] = None,
) -> bool:
    if receipt_type not in GOAL_RECEIPT_TYPES:
        return False
    goal_id = _bounded_str(goal.get("goal_id"), 160)
    if not goal_id:
        return False
    rid = _receipt_id(
        receipt_type,
        turn_number=turn_number,
        goal_id=goal_id,
        detail=detail,
        source_event_ids=source_event_ids,
    )
    receipts = replayability_state.setdefault("goal_receipts", [])
    if any(isinstance(row, Mapping) and row.get("receipt_id") == rid for row in receipts):
        return False
    receipt = {
        "version": GOAL_ENGINE_VERSION,
        "receipt_id": rid,
        "receipt_type": receipt_type,
        "turn": turn_number,
        "goal_id": goal_id,
        "goal_type": goal.get("goal_type"),
        "owner_type": goal.get("owner_type"),
        "owner_id": goal.get("owner_id"),
        "detail": _bounded_str(detail, 120),
    }
    change = _summary_change(_goal_summary(before or {}), _goal_summary(after or goal))
    if change:
        receipt["change"] = change
    source_ids = _bounded_str_list(source_event_ids or goal.get("source_event_ids"), MAX_GOAL_REFS)
    if source_ids:
        receipt["source_event_ids"] = source_ids
    receipts.append(receipt)
    if len(receipts) > MAX_GOAL_RECEIPTS:
        replayability_state["goal_receipts"] = receipts[-MAX_GOAL_RECEIPTS:]
    local_receipts.append(receipt)
    return True


def _merge_unique(existing: Dict[str, Any], incoming: Mapping[str, Any], key: str, limit: int = MAX_GOAL_REFS) -> bool:
    before = list(existing.get(key) or [])
    merged = _bounded_str_list(before + list(incoming.get(key) or []), limit)
    existing[key] = merged
    return merged != before


def _find_existing(goals: Sequence[Dict[str, Any]], candidate: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    wanted_id = str(candidate.get("goal_id") or "")
    wanted_key = str(candidate.get("dedupe_key") or "")
    for row in goals:
        if row.get("status") in TERMINAL_STATUSES:
            continue
        if wanted_id and row.get("goal_id") == wanted_id:
            return row
        if wanted_key and row.get("dedupe_key") == wanted_key:
            return row
    return None


def _reinforce_goal(existing: Dict[str, Any], candidate: Mapping[str, Any], turn_number: int) -> bool:
    changed = False
    for key, limit in (
        ("parent_situation_ids", MAX_GOAL_REFS),
        ("supporting_pressure_ids", MAX_GOAL_REFS),
        ("target_actor_ids", MAX_GOAL_REFS),
        ("target_location_ids", MAX_GOAL_REFS),
        ("required_resources", MAX_GOAL_RESOURCES),
        ("blockers", MAX_GOAL_BLOCKERS),
        ("prerequisites", MAX_GOAL_PREREQUISITES),
        ("evidence_refs", MAX_GOAL_EVIDENCE_REFS),
        ("source_event_ids", MAX_GOAL_REFS),
    ):
        changed = _merge_unique(existing, candidate, key, limit) or changed
    for key in ("priority", "urgency", "confidence"):
        value = max(_clamp_int(existing.get(key), 0, 100), _clamp_int(candidate.get(key), 0, 100))
        if value != existing.get(key):
            existing[key] = value
            changed = True
    if existing.get("status") == "forming":
        existing["status"] = "active"
        changed = True
    if changed:
        existing["updated_turn"] = turn_number
    existing["last_reinforced_turn"] = turn_number
    existing["inactive_turns"] = 0
    return changed


def _situations_by_id(replayability_state: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in replayability_state.get("situations") or []:
        if isinstance(row, Mapping) and row.get("situation_id"):
            out[str(row.get("situation_id"))] = dict(row)
    return out


WORLD_STATE_SIGNAL_TO_GOAL_TYPE = {
    "resource_shortage": "secure_food",
    "route_blocked": "restore_route",
    "infrastructure_damaged": "restore_route",
    "settlement_unstable": "defend_settlement",
    "faction_pressure": "defend_settlement",
    "settlement_improving": "secure_trade_route",
    "market_strained": "secure_trade_route",
    "actor_missing": "rescue_missing_person",
}

EVIDENCE_EXPOSURE_TO_GOAL_TYPE = {
    "implicated_private": "hide_evidence",
    "implicated_public": "hide_evidence",
    "investigating": "find_murderer",
    "accused_pressure": "hide_evidence",
}

AMBITION_TO_GOAL_TYPE = dict(npc_agendas.AGENDA_GOAL_TO_ENGINE_GOAL)


def _candidate_from_world_state_signal(
    signal: Mapping[str, Any],
    *,
    turn_number: int,
    run_seed: str,
) -> Optional[Dict[str, Any]]:
    signal_kind = str(signal.get("signal_kind") or "")
    goal_type = WORLD_STATE_SIGNAL_TO_GOAL_TYPE.get(signal_kind)
    signal_id = _bounded_str(signal.get("signal_id"), 160)
    if not goal_type or not signal_id:
        return None
    location_id = _bounded_str(signal.get("location_id"), 120)
    faction_id = _bounded_str(signal.get("faction_id"), 120)
    owner_type = "faction" if faction_id and signal_kind == "faction_pressure" else "settlement" if location_id else "world"
    owner_id = faction_id or location_id or "world"
    target = location_id or faction_id or signal_id
    dedupe = _dedupe_key(owner_type, owner_id, goal_type, target)
    severity = _clamp_int(signal.get("severity"), 0, 10, default=5)
    return _normalise_goal(
        {
            "goal_id": _goal_id(run_seed, dedupe),
            "owner_type": owner_type,
            "owner_id": owner_id,
            "goal_type": goal_type,
            "title": _goal_title(goal_type),
            "status": "forming" if severity < 4 else "active",
            "priority": severity,
            "urgency": severity,
            "progress": 0,
            "confidence": min(100, 40 + severity * 5),
            "created_turn": turn_number,
            "updated_turn": turn_number,
            "parent_situation_ids": [],
            "target_location_ids": [location_id] if location_id else [],
            "target_actor_ids": [],
            "required_resources": GOAL_REQUIRED_RESOURCES.get(goal_type, ()),
            "blockers": list(signal.get("conditions") or [])[:MAX_GOAL_BLOCKERS],
            "prerequisites": GOAL_PREREQUISITES.get(goal_type, ()),
            "evidence_refs": [f"world_state:{signal_id}"],
            "expiry": turn_number + DEFAULT_EXPIRY_TURNS,
            "source_event_ids": [signal_id],
            "plan_steps": _generate_plan(goal_type),
            "dedupe_key": dedupe,
            "last_reinforced_turn": turn_number,
        },
        run_seed=run_seed,
    )


def _candidate_from_evidence_exposure(
    signal: Mapping[str, Any],
    *,
    turn_number: int,
    run_seed: str,
) -> Optional[Dict[str, Any]]:
    exposure_kind = str(signal.get("exposure_kind") or "")
    goal_type = EVIDENCE_EXPOSURE_TO_GOAL_TYPE.get(exposure_kind)
    signal_id = _bounded_str(signal.get("signal_id"), 160)
    actor_id = _bounded_str(signal.get("actor_id"), 120)
    if not goal_type or not signal_id or not actor_id:
        return None
    evidence_id = _bounded_str(signal.get("evidence_id"), 160)
    investigation_id = _bounded_str(signal.get("investigation_id"), 160)
    target = evidence_id or investigation_id or signal_id
    dedupe = _dedupe_key("npc", actor_id, goal_type, target)
    severity = _clamp_int(signal.get("severity"), 0, 10, default=5)
    confidence = _clamp_int(signal.get("confidence"), 0, 100, default=50)
    parent_situation_ids = [investigation_id] if investigation_id else []
    return _normalise_goal(
        {
            "goal_id": _goal_id(run_seed, dedupe),
            "owner_type": "npc",
            "owner_id": actor_id,
            "goal_type": goal_type,
            "title": _goal_title(goal_type),
            "status": "active" if severity >= 4 else "forming",
            "priority": severity,
            "urgency": severity,
            "progress": 0,
            "confidence": confidence,
            "created_turn": turn_number,
            "updated_turn": turn_number,
            "parent_situation_ids": parent_situation_ids,
            "supporting_pressure_ids": [],
            "target_actor_ids": [actor_id] if exposure_kind != "investigating" else [],
            "target_location_ids": [],
            "required_resources": GOAL_REQUIRED_RESOURCES.get(goal_type, ()),
            "blockers": list(signal.get("behaviours") or [])[:MAX_GOAL_BLOCKERS],
            "prerequisites": () if evidence_id else GOAL_PREREQUISITES.get(goal_type, ()),
            "evidence_refs": [f"evidence_exposure:{signal_id}"] + ([evidence_id] if evidence_id else []),
            "expiry": turn_number + DEFAULT_EXPIRY_TURNS,
            "source_event_ids": [signal_id],
            "plan_steps": _generate_plan(goal_type),
            "dedupe_key": dedupe,
            "last_reinforced_turn": turn_number,
        },
        run_seed=run_seed,
    )


def _candidate_from_ambition_signal(
    signal: Mapping[str, Any],
    *,
    turn_number: int,
    run_seed: str,
) -> Optional[Dict[str, Any]]:
    ambition_kind = str(signal.get("ambition_kind") or "")
    goal_type = AMBITION_TO_GOAL_TYPE.get(ambition_kind)
    npc_id = _bounded_str(signal.get("npc_id"), 120)
    agenda_id = _bounded_str(signal.get("agenda_id") or signal.get("signal_id"), 160)
    if not goal_type or not npc_id or not agenda_id:
        return None
    dedupe = _dedupe_key("npc", npc_id, goal_type, agenda_id)
    severity = _clamp_int(signal.get("severity"), 0, 10, default=5)
    progress = _clamp_int(signal.get("progress"), 0, 100, default=15)
    return _normalise_goal(
        {
            "goal_id": _goal_id(run_seed, dedupe),
            "owner_type": "npc",
            "owner_id": npc_id,
            "goal_type": goal_type,
            "title": _goal_title(goal_type),
            "status": "active" if severity >= 4 else "forming",
            "priority": severity,
            "urgency": severity,
            "progress": min(60, progress),
            "confidence": min(100, 35 + progress // 2),
            "created_turn": turn_number,
            "updated_turn": turn_number,
            "parent_situation_ids": [],
            "supporting_pressure_ids": [],
            "target_actor_ids": [],
            "target_location_ids": [],
            "required_resources": GOAL_REQUIRED_RESOURCES.get(goal_type, ()),
            "blockers": [],
            "prerequisites": GOAL_PREREQUISITES.get(goal_type, ()),
            "evidence_refs": [f"ambition:{agenda_id}"],
            "expiry": turn_number + DEFAULT_EXPIRY_TURNS,
            "source_event_ids": [agenda_id],
            "plan_steps": _generate_plan(goal_type),
            "dedupe_key": dedupe,
            "last_reinforced_turn": turn_number,
        },
        run_seed=run_seed,
    )


def _resource_blocked(goal: Mapping[str, Any], rolling_state: Mapping[str, Any]) -> bool:
    required = {item.lower() for item in _bounded_str_list(goal.get("required_resources"), MAX_GOAL_RESOURCES)}
    if not required:
        return False
    for row in rolling_state.get("world_resources") or []:
        if not isinstance(row, Mapping):
            continue
        text = " ".join(
            str(row.get(key) or "").lower()
            for key in ("id", "resource_id", "name", "status", "trend")
        )
        if not any(item in text for item in required):
            continue
        status = str(row.get("status") or "").lower()
        trend = str(row.get("trend") or "").lower()
        if status in {"shortage", "reduced", "exhausted"} or trend == "decreasing":
            return True
    return False


def _trade_route_blocked(goal: Mapping[str, Any], rolling_state: Mapping[str, Any]) -> bool:
    if str(goal.get("goal_type") or "") != "secure_trade_route":
        return False
    locations = _bounded_str_list(goal.get("target_location_ids"), MAX_GOAL_REFS)
    signals = world_state_consumers.world_state_signals_for_context(
        rolling_state,
        location_ids=locations or ["world"],
    )
    return any(str(row.get("signal_kind") or "") == "route_blocked" for row in signals)


def _action_event_id(recent_action: Optional[Mapping[str, Any]]) -> str:
    if not isinstance(recent_action, Mapping):
        return ""
    return _bounded_str(recent_action.get("receipt_id") or recent_action.get("event_id"), 160)


def _action_matches_goal(goal: Mapping[str, Any], recent_action: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(recent_action, Mapping):
        return False
    if str(recent_action.get("outcome") or "success") != "success":
        return False
    move_kind = _bounded_str(recent_action.get("move_kind") or recent_action.get("action_kind"), 80)
    if not move_kind:
        return False
    owner_type = str(goal.get("owner_type") or "")
    owner_id = str(goal.get("owner_id") or "")
    actor_id = str(recent_action.get("npc_id") or recent_action.get("actor_id") or "")
    if owner_type == "npc" and owner_id and actor_id and owner_id != actor_id:
        return False
    target_id = str(recent_action.get("target_id") or "")
    targets = set(goal.get("target_actor_ids") or []) | set(goal.get("target_location_ids") or [])
    if targets and target_id and target_id not in targets and owner_type != "npc":
        return False
    plan = goal.get("plan_steps") if isinstance(goal.get("plan_steps"), list) else []
    if not plan:
        return False
    idx = _clamp_int(goal.get("current_step_index"), 0, max(0, len(plan) - 1))
    tags = set(plan[idx].get("action_tags") or [])
    return move_kind in tags


def _advance_plan_step(goal: Dict[str, Any]) -> None:
    plan = goal.get("plan_steps") if isinstance(goal.get("plan_steps"), list) else []
    if not plan:
        return
    idx = _clamp_int(goal.get("current_step_index"), 0, max(0, len(plan) - 1))
    plan[idx]["status"] = "completed"
    for next_idx in range(idx + 1, len(plan)):
        if plan[next_idx].get("status") == "pending":
            plan[next_idx]["status"] = "active"
            goal["current_step_index"] = next_idx
            return
    goal["current_step_index"] = idx


def _advance_goal(
    goal: Dict[str, Any],
    *,
    replayability_state: Mapping[str, Any],
    rolling_state: Mapping[str, Any],
    turn_number: int,
    recent_action: Optional[Mapping[str, Any]],
) -> Optional[Tuple[str, str, Dict[str, Any], Dict[str, Any], List[str]]]:
    if goal.get("status") in TERMINAL_STATUSES:
        return None
    if goal.get("last_evolved_turn") == turn_number:
        return None
    before = copy.deepcopy(goal)
    situations = _situations_by_id(replayability_state)
    parent_ids = _bounded_str_list(goal.get("parent_situation_ids"), MAX_GOAL_REFS)
    parent_statuses = [str((situations.get(pid) or {}).get("status") or "") for pid in parent_ids]
    receipt_type = ""
    detail = ""
    sources: List[str] = []

    if _resource_blocked(goal, rolling_state):
        goal["status"] = "blocked"
        plan = goal.get("plan_steps") if isinstance(goal.get("plan_steps"), list) else []
        if plan:
            plan[_clamp_int(goal.get("current_step_index"), 0, len(plan) - 1)]["status"] = "blocked"
        goal["updated_turn"] = turn_number
        receipt_type = "goal_blocked"
        detail = "required_resource_blocked"
    elif _trade_route_blocked(goal, rolling_state):
        goal["status"] = "blocked"
        plan = goal.get("plan_steps") if isinstance(goal.get("plan_steps"), list) else []
        if plan:
            plan[_clamp_int(goal.get("current_step_index"), 0, len(plan) - 1)]["status"] = "blocked"
        goal["updated_turn"] = turn_number
        receipt_type = "goal_blocked"
        detail = "trade_route_blocked"
    else:
        if goal.get("status") == "blocked":
            goal["status"] = "active"
            plan = goal.get("plan_steps") if isinstance(goal.get("plan_steps"), list) else []
            if plan:
                plan[_clamp_int(goal.get("current_step_index"), 0, len(plan) - 1)]["status"] = "active"
            goal["updated_turn"] = turn_number
        action_id = _action_event_id(recent_action)
        if action_id and action_id != goal.get("last_action_event_id") and goal.get("created_turn") != turn_number:
            if _action_matches_goal(goal, recent_action):
                goal["progress"] = min(100, _clamp_int(goal.get("progress"), 0, 100) + 20)
                _advance_plan_step(goal)
                goal["last_action_event_id"] = action_id
                goal["updated_turn"] = turn_number
                goal["inactive_turns"] = 0
                sources = [action_id]
                receipt_type = "goal_completed" if goal["progress"] >= 100 else "goal_progressed"
                detail = "committed_action"
        if not receipt_type and parent_statuses:
            if all(status in {"resolved", "archived"} for status in parent_statuses):
                if _clamp_int(goal.get("progress"), 0, 100) >= 50:
                    goal["progress"] = 100
                    goal["status"] = "completed"
                    goal["updated_turn"] = turn_number
                    receipt_type = "goal_completed"
                    detail = "parent_situation_resolved"
                elif _clamp_int(goal.get("progress"), 0, 100) == 0:
                    goal["status"] = "abandoned"
                    goal["updated_turn"] = turn_number
                    receipt_type = "goal_abandoned"
                    detail = "parent_situation_resolved_without_progress"
            elif any(status == "failed" for status in parent_statuses):
                goal["status"] = "failed"
                goal["updated_turn"] = turn_number
                receipt_type = "goal_failed"
                detail = "parent_situation_failed"
        if not receipt_type and turn_number >= _coerce_int(goal.get("expiry"), turn_number + 1):
            goal["status"] = "failed" if _clamp_int(goal.get("progress"), 0, 100) < 50 else "completed"
            if goal["status"] == "completed":
                goal["progress"] = 100
            goal["priority"] = min(_clamp_int(goal.get("priority"), 0, 10), 2)
            goal["updated_turn"] = turn_number
            receipt_type = "goal_failed" if goal["status"] == "failed" else "goal_completed"
            detail = "expired"
        if not receipt_type:
            inactive = max(0, _coerce_int(goal.get("inactive_turns"), 0)) + 1
            goal["inactive_turns"] = inactive
            if inactive >= ABANDON_AFTER_INACTIVE_TURNS and not parent_ids and _clamp_int(goal.get("progress"), 0, 100) == 0:
                goal["status"] = "abandoned"
                goal["updated_turn"] = turn_number
                receipt_type = "goal_abandoned"
                detail = "obsolete"

    if goal.get("progress") >= 100 and goal.get("status") not in TERMINAL_STATUSES:
        goal["status"] = "completed"
        receipt_type = "goal_completed"
        detail = detail or "progress_complete"
    goal["last_evolved_turn"] = turn_number
    if receipt_type and before != goal:
        return receipt_type, detail, before, copy.deepcopy(goal), sources or list(goal.get("source_event_ids") or [])
    return None


def _merge_duplicate_goals(
    replayability_state: Dict[str, Any],
    goals: List[Dict[str, Any]],
    local_receipts: List[Dict[str, Any]],
    turn_number: int,
    remaining_changes: int,
) -> int:
    by_key: Dict[str, Dict[str, Any]] = {}
    for goal in sorted(goals, key=lambda row: (_coerce_int(row.get("created_turn"), 0), str(row.get("goal_id") or ""))):
        if goal.get("status") in TERMINAL_STATUSES:
            continue
        key = str(goal.get("dedupe_key") or "")
        if not key:
            continue
        primary = by_key.get(key)
        if primary is None:
            by_key[key] = goal
            continue
        if remaining_changes <= 0:
            break
        before = copy.deepcopy(primary)
        _reinforce_goal(primary, goal, turn_number)
        duplicate_before = copy.deepcopy(goal)
        goal["status"] = "abandoned"
        goal["updated_turn"] = turn_number
        goal["merged_into"] = primary.get("goal_id")
        _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type="goal_merged",
            turn_number=turn_number,
            goal=primary,
            before=before,
            after=primary,
            detail=f"merged:{goal.get('goal_id')}",
            source_event_ids=list(primary.get("source_event_ids") or []) + list(goal.get("source_event_ids") or []),
        )
        _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type="goal_abandoned",
            turn_number=turn_number,
            goal=goal,
            before=duplicate_before,
            after=goal,
            detail="merged_duplicate",
            source_event_ids=goal.get("source_event_ids") or [],
        )
        remaining_changes -= 1
    return remaining_changes


def _compact_terminal_goal(row: Dict[str, Any]) -> Dict[str, Any]:
    if row.get("status") not in TERMINAL_STATUSES:
        return row
    keep = (
        "goal_id",
        "owner_type",
        "owner_id",
        "goal_type",
        "title",
        "status",
        "priority",
        "urgency",
        "progress",
        "created_turn",
        "updated_turn",
        "parent_situation_ids",
        "supporting_pressure_ids",
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


def _cap_goals(goals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    active = [row for row in goals if row.get("status") not in TERMINAL_STATUSES]
    if len(active) > MAX_ACTIVE_GOALS:
        overflow_ids = {
            row.get("goal_id")
            for row in sorted(
                active,
                key=lambda row: (
                    _clamp_int(row.get("priority"), 0, 10),
                    _clamp_int(row.get("urgency"), 0, 10),
                    _coerce_int(row.get("updated_turn"), 0),
                    str(row.get("goal_id") or ""),
                ),
            )[: len(active) - MAX_ACTIVE_GOALS]
        }
        for row in goals:
            if row.get("goal_id") in overflow_ids:
                row["status"] = "abandoned"
                row["priority"] = min(_clamp_int(row.get("priority"), 0, 10), 1)
    goals = [_compact_terminal_goal(row) for row in goals]
    if len(goals) > MAX_GOALS:
        goals = sorted(
            goals,
            key=lambda row: (
                0 if row.get("status") not in TERMINAL_STATUSES else 1,
                -_clamp_int(row.get("priority"), 0, 10),
                -_clamp_int(row.get("urgency"), 0, 10),
                -_coerce_int(row.get("updated_turn"), 0),
                str(row.get("goal_id") or ""),
            ),
        )[:MAX_GOALS]
    return sorted(goals, key=lambda row: (_coerce_int(row.get("created_turn"), 0), str(row.get("goal_id") or "")))


def evolve_goals(
    replayability_state: Dict[str, Any],
    rolling_state: Mapping[str, Any],
    turn_number: int,
    *,
    run_seed: str = "",
    recent_action: Optional[Mapping[str, Any]] = None,
    advance_existing: bool = True,
) -> Dict[str, Any]:
    diagnostics = {
        "goal_engine_executed": False,
        "goal_candidates_evaluated": 0,
        "goal_created": 0,
        "goal_reinforced": 0,
        "goal_merged": 0,
        "goal_progressed": 0,
        "goal_blocked": 0,
        "goal_completed": 0,
        "goal_failed": 0,
        "goal_abandoned": 0,
        "goal_duplicate_suppressed": 0,
        "goal_recreated": 0,
    }
    if not isinstance(replayability_state, dict):
        return {"receipts": [], "diagnostics": diagnostics}

    seed = run_seed or str(replayability_state.get("run_seed") or "goal-engine")
    goals = [
        _normalise_goal(row, run_seed=seed)
        for row in replayability_state.get("goals") or []
        if isinstance(row, Mapping)
    ]
    replayability_state["goals"] = goals
    replayability_state.setdefault("goal_receipts", [])
    local_receipts: List[Dict[str, Any]] = []
    remaining_changes = MAX_GOAL_CHANGES_PER_TICK
    created_goal_ids = set()

    situations = [
        row for row in replayability_state.get("situations") or []
        if isinstance(row, Mapping)
    ]
    situations.sort(
        key=lambda row: (
            -_clamp_int(row.get("priority"), 0, 10),
            -_clamp_int(row.get("severity"), 0, 10),
            str(row.get("situation_id") or ""),
        )
    )
    candidates: List[Dict[str, Any]] = []
    for situation in situations:
        if len(candidates) >= MAX_GOAL_INPUTS_PER_TICK:
            break
        candidate = _candidate_from_situation(situation, turn_number=turn_number, run_seed=seed)
        if candidate:
            candidates.append(candidate)
    evidence_by_id = {
        str(row.get("evidence_id") or ""): row
        for row in replayability_state.get("evidence") or []
        if isinstance(row, Mapping) and row.get("evidence_id")
    }
    investigations = [
        row for row in replayability_state.get("investigations") or []
        if isinstance(row, Mapping)
    ]
    investigations.sort(
        key=lambda row: (
            -_clamp_int(row.get("priority"), 0, 10),
            -_clamp_int(row.get("confidence"), 0, 100),
            str(row.get("investigation_id") or ""),
        )
    )
    for investigation in investigations:
        if len(candidates) >= MAX_GOAL_INPUTS_PER_TICK:
            break
        candidate = _candidate_from_investigation(
            investigation,
            evidence_by_id,
            turn_number=turn_number,
            run_seed=seed,
        )
        if candidate:
            candidates.append(candidate)

    world_signals = world_state_consumers.world_state_signals_for_context(rolling_state)
    for signal in world_signals:
        if len(candidates) >= MAX_GOAL_INPUTS_PER_TICK:
            break
        candidate = _candidate_from_world_state_signal(signal, turn_number=turn_number, run_seed=seed)
        if candidate:
            candidates.append(candidate)

    investigation_state = {
        "investigations": replayability_state.get("investigations") or [],
        "evidence": replayability_state.get("evidence") or [],
    }
    information_state = {
        "information_items": replayability_state.get("information_items") or [],
        "reputation_signals": replayability_state.get("reputation_signals") or [],
    }
    for signal in investigation_engine.evidence_exposure_signals_for_context(
        investigation_state,
        information_state=information_state,
    ):
        if len(candidates) >= MAX_GOAL_INPUTS_PER_TICK:
            break
        candidate = _candidate_from_evidence_exposure(signal, turn_number=turn_number, run_seed=seed)
        if candidate:
            candidates.append(candidate)

    for signal in npc_agendas.ambition_signals_for_context(
        replayability_state.get("npc_agendas") or {},
        rolling_state=rolling_state,
    ):
        if len(candidates) >= MAX_GOAL_INPUTS_PER_TICK:
            break
        candidate = _candidate_from_ambition_signal(signal, turn_number=turn_number, run_seed=seed)
        if candidate:
            candidates.append(candidate)

    seen_candidate_keys = set()
    for candidate in candidates:
        diagnostics["goal_candidates_evaluated"] += 1
        key = (candidate.get("dedupe_key"), tuple(candidate.get("source_event_ids") or []))
        if key in seen_candidate_keys:
            diagnostics["goal_duplicate_suppressed"] += 1
            continue
        seen_candidate_keys.add(key)
        existing = _find_existing(goals, candidate)
        if existing is None:
            if remaining_changes <= 0 or len(goals) >= MAX_GOALS:
                diagnostics["goal_duplicate_suppressed"] += 1
                continue
            generation = _assign_unique_goal_id(candidate, goals, seed)
            goals.append(candidate)
            if _append_receipt(
                replayability_state,
                local_receipts,
                receipt_type="goal_created",
                turn_number=turn_number,
                goal=candidate,
                before={},
                after=candidate,
                detail="created_from_engine_source",
                source_event_ids=candidate.get("source_event_ids") or [],
            ):
                diagnostics["goal_created"] += 1
                if generation > 0:
                    diagnostics["goal_recreated"] += 1
                created_goal_ids.add(str(candidate.get("goal_id") or ""))
                remaining_changes -= 1
            continue
        new_sources = [
            source_id
            for source_id in candidate.get("source_event_ids") or []
            if source_id not in (existing.get("source_event_ids") or [])
        ]
        if not new_sources and _clamp_int(candidate.get("priority"), 0, 10) <= _clamp_int(existing.get("priority"), 0, 10):
            diagnostics["goal_duplicate_suppressed"] += 1
            existing["last_reinforced_turn"] = turn_number
            existing["inactive_turns"] = 0
            continue
        if remaining_changes <= 0:
            continue
        before = copy.deepcopy(existing)
        changed = _reinforce_goal(existing, candidate, turn_number)
        if changed and _append_receipt(
            replayability_state,
            local_receipts,
                receipt_type="goal_reinforced",
                turn_number=turn_number,
                goal=existing,
                before=before,
                after=existing,
                detail="reinforced_from_engine_source",
                source_event_ids=new_sources or candidate.get("source_event_ids") or [],
            ):
            diagnostics["goal_reinforced"] += 1
            remaining_changes -= 1

    before_merge_receipts = len(local_receipts)
    remaining_changes = _merge_duplicate_goals(
        replayability_state,
        goals,
        local_receipts,
        turn_number,
        remaining_changes,
    )
    diagnostics["goal_merged"] += sum(1 for receipt in local_receipts[before_merge_receipts:] if receipt.get("receipt_type") == "goal_merged")
    diagnostics["goal_abandoned"] += sum(1 for receipt in local_receipts[before_merge_receipts:] if receipt.get("receipt_type") == "goal_abandoned")

    if advance_existing:
        for goal in sorted(goals, key=lambda row: (-_clamp_int(row.get("priority"), 0, 10), str(row.get("goal_id") or ""))):
            if remaining_changes <= 0:
                break
            if str(goal.get("goal_id") or "") in created_goal_ids:
                goal["last_evolved_turn"] = turn_number
                continue
            advanced = _advance_goal(
                goal,
                replayability_state=replayability_state,
                rolling_state=rolling_state if isinstance(rolling_state, Mapping) else {},
                turn_number=turn_number,
                recent_action=recent_action,
            )
            if not advanced:
                continue
            receipt_type, detail, before, after, sources = advanced
            if _append_receipt(
                replayability_state,
                local_receipts,
                receipt_type=receipt_type,
                turn_number=turn_number,
                goal=goal,
                before=before,
                after=after,
                detail=detail,
                source_event_ids=sources,
            ):
                if receipt_type == "goal_progressed":
                    diagnostics["goal_progressed"] += 1
                elif receipt_type == "goal_blocked":
                    diagnostics["goal_blocked"] += 1
                elif receipt_type == "goal_completed":
                    diagnostics["goal_completed"] += 1
                elif receipt_type == "goal_failed":
                    diagnostics["goal_failed"] += 1
                elif receipt_type == "goal_abandoned":
                    diagnostics["goal_abandoned"] += 1
                remaining_changes -= 1

    replayability_state["goals"] = _cap_goals(goals)
    diagnostics["goal_engine_executed"] = bool(local_receipts or candidates or replayability_state["goals"])
    return {"receipts": local_receipts, "diagnostics": diagnostics}


def project_active_goals_for_rolling(
    replayability_state: Mapping[str, Any],
    *,
    limit: int = MAX_PROJECTED_GOALS,
) -> List[Dict[str, Any]]:
    if not isinstance(replayability_state, Mapping):
        return []
    goals = [
        _normalise_goal(row, run_seed=str(replayability_state.get("run_seed") or "goal-engine"))
        for row in replayability_state.get("goals") or []
        if isinstance(row, Mapping) and row.get("status") not in TERMINAL_STATUSES
    ]
    ordered = sorted(
        goals,
        key=lambda row: (
            -_clamp_int(row.get("priority"), 0, 10),
            -_clamp_int(row.get("urgency"), 0, 10),
            str(row.get("goal_id") or ""),
        ),
    )[: max(0, min(MAX_PROJECTED_GOALS, int(limit or 0)))]
    return [
        {
            "title": row.get("title"),
            "status": row.get("status"),
            "priority": row.get("priority"),
            "progress": row.get("progress"),
            "next_step_summary": _next_step_summary(row),
        }
        for row in ordered
    ]


def project_goals_for_prompt(replayability_state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return project_active_goals_for_rolling(replayability_state, limit=MAX_PROMPT_GOALS)


def prompt_safe_rolling_state(rolling_state: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(rolling_state, Mapping):
        return {}
    safe = copy.deepcopy(dict(rolling_state))
    rows = safe.get("active_goals")
    if not isinstance(rows, list):
        return safe
    cleaned: List[Dict[str, Any]] = []
    for row in rows[:MAX_PROMPT_GOALS]:
        if not isinstance(row, Mapping):
            continue
        cleaned.append(
            {
                key: copy.deepcopy(row.get(key))
                for key in ("title", "status", "priority", "progress", "next_step_summary")
                if key in row
            }
        )
    safe["active_goals"] = cleaned
    return safe


def copy_goal_state(replayability_state: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(replayability_state, Mapping):
        return {"goals": []}
    seed = str(replayability_state.get("run_seed") or "goal-engine")
    goals = [
        _normalise_goal(row, run_seed=seed)
        for row in replayability_state.get("goals") or []
        if isinstance(row, Mapping)
    ]
    return {"goals": _cap_goals(goals)}


def _token_set(*values: Any) -> set:
    out = set()
    for value in values:
        raw = value if isinstance(value, (list, tuple, set)) else [value]
        for item in raw:
            text = str(item or "").strip().lower()
            if text:
                out.add(text)
    return out


def active_goals_for_context(
    goal_state: Mapping[str, Any],
    *,
    actor_ids: Sequence[str] = (),
    location_ids: Sequence[str] = (),
    faction_ids: Sequence[str] = (),
    goal_ids: Sequence[str] = (),
    limit: int = MAX_CONTEXT_GOALS,
) -> List[Dict[str, Any]]:
    if not isinstance(goal_state, Mapping):
        return []
    actor_tokens = _token_set(actor_ids)
    location_tokens = _token_set(location_ids)
    faction_tokens = _token_set(faction_ids)
    goal_tokens = _token_set(goal_ids)
    matched: List[Dict[str, Any]] = []
    for raw in goal_state.get("goals") or []:
        if not isinstance(raw, Mapping):
            continue
        goal = _normalise_goal(raw)
        if goal.get("status") in TERMINAL_STATUSES:
            continue
        owner_type = str(goal.get("owner_type") or "")
        owner_id = str(goal.get("owner_id") or "").lower()
        applies = False
        if goal.get("goal_id") and str(goal.get("goal_id")).lower() in goal_tokens:
            applies = True
        if owner_type == "npc" and owner_id in actor_tokens:
            applies = True
        if owner_type == "faction" and owner_id in faction_tokens:
            applies = True
        if owner_type == "settlement" and owner_id in location_tokens:
            applies = True
        if set(str(item).lower() for item in goal.get("target_actor_ids") or []).intersection(actor_tokens):
            applies = True
        if set(str(item).lower() for item in goal.get("target_location_ids") or []).intersection(location_tokens):
            applies = True
        if owner_type == "world":
            applies = True
        if applies:
            matched.append(goal)
    ordered = sorted(
        matched,
        key=lambda row: (
            -_clamp_int(row.get("priority"), 0, 10),
            -_clamp_int(row.get("urgency"), 0, 10),
            str(row.get("goal_id") or ""),
        ),
    )
    return ordered[: max(0, min(MAX_CONTEXT_GOALS, int(limit or 0)))]
