"""
Deterministic NPC Action Engine.

NPC actions are engine-owned consequences of active NPC goals. The LLM may
narrate visible behavior, but it never creates actions, resolves outcomes, or
mutates canonical action history.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import goal_engine

NPC_ACTION_ENGINE_VERSION = 1

MAX_NPC_ACTIONS = 32
MAX_NPC_ACTIONS_PER_TICK = 4
MAX_NPC_ACTION_RECEIPTS = 64
MAX_ACTION_EVENTS_PER_TICK = 4
MAX_ACTION_REFS = 8
MAX_PROJECTED_ACTIONS = 6
MAX_PROMPT_ACTIONS = 4
MAX_CONTEXT_ACTIONS = 4

ACTION_STATUSES = ("selected", "resolved")
ACTION_OUTCOMES = ("success", "failure", "blocked")
TERMINAL_GOAL_STATUSES = frozenset({"completed", "failed", "abandoned"})

ACTION_TYPES = (
    "travel",
    "investigate",
    "search",
    "gather",
    "trade",
    "repair",
    "recruit",
    "warn",
    "hide",
    "patrol",
    "escort",
    "defend",
    "attack",
    "retreat",
    "observe",
    "negotiate",
    "deliver",
    "wait",
    "support",
)

ACTION_RECEIPT_TYPES = (
    "npc_action_selected",
    "npc_action_resolved",
    "npc_action_event_generated",
)

UTILITY_ACTION_KIND_BY_ACTION_TYPE = {
    "defend": "protect",
    "warn": "pressure",
    "hide": "conceal",
    "retreat": "withdraw",
    "repair": "fortify",
    "patrol": "protect",
    "escort": "protect",
    "support": "protect",
    "attack": "pressure",
    "wait": "idle",
}

UTILITY_ACTION_KINDS = tuple(
    sorted(set(UTILITY_ACTION_KIND_BY_ACTION_TYPE.values()) | set(ACTION_TYPES))
)

PROMPT_ACTION_FIELDS = (
    "current_action",
    "destination",
    "goal_title",
    "progress",
    "status",
)


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


def _bounded_str_list(values: Any, limit: int = MAX_ACTION_REFS) -> List[str]:
    out: List[str] = []
    raw = values if isinstance(values, (list, tuple, set)) else [values]
    for value in raw or []:
        text = _bounded_str(value)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _active_goals(replayability_state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    copied = goal_engine.copy_goal_state(replayability_state)
    return [
        row
        for row in copied.get("goals") or []
        if isinstance(row, dict)
        and row.get("owner_type") == "npc"
        and row.get("status") not in TERMINAL_GOAL_STATUSES
    ]


def _goal_by_id(replayability_state: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(row.get("goal_id") or ""): row
        for row in goal_engine.copy_goal_state(replayability_state).get("goals") or []
        if isinstance(row, dict) and row.get("goal_id")
    }


def _current_step(goal: Mapping[str, Any]) -> Dict[str, Any]:
    steps = goal.get("plan_steps") if isinstance(goal.get("plan_steps"), list) else []
    if not steps:
        return {}
    idx = _clamp_int(goal.get("current_step_index"), 0, max(0, len(steps) - 1))
    return dict(steps[idx]) if isinstance(steps[idx], Mapping) else {}


def _action_type_for_goal(goal: Mapping[str, Any]) -> str:
    step = _current_step(goal)
    step_text = " ".join(
        [
            str(step.get("step_id") or ""),
            str(step.get("summary") or ""),
            str(goal.get("goal_type") or ""),
        ]
    ).lower()
    tags = {str(tag or "").strip().lower() for tag in step.get("action_tags") or []}
    goal_type = str(goal.get("goal_type") or "")

    if "travel" in step_text or "move toward" in step_text or "return safe" in step_text:
        return "travel"
    if "search" in step_text:
        return "search"
    if "recruit" in step_text or goal_type == "recruit_members":
        return "recruit"
    if goal_type in {"restore_route", "build_shelter"} and tags.intersection({"fortify", "protect"}):
        return "repair"
    if goal_type == "secure_trade_route" and "negotiate" in tags:
        return "trade"
    if goal_type == "remove_rival_influence" and "pressure" in tags:
        return "warn"
    if "conceal" in tags:
        return "hide"
    if "withdraw" in tags:
        return "retreat"
    if "protect" in tags:
        return "defend"
    if goal_type == "find_murderer" and "investigate" in tags:
        return "investigate"
    if "gather" in tags:
        return "gather"
    if "negotiate" in tags:
        return "negotiate"
    if "investigate" in tags:
        return "investigate"
    if "pressure" in tags:
        return "warn"
    return "wait"


def _actor_location(actor_id: str, rolling_state: Mapping[str, Any]) -> str:
    for row in rolling_state.get("actor_location_registry") or []:
        if isinstance(row, Mapping) and str(row.get("id") or "") == actor_id and row.get("location_id"):
            return _bounded_str(row.get("location_id"), 160)
    for row in rolling_state.get("npcs") or []:
        if not isinstance(row, Mapping):
            continue
        if actor_id in {str(row.get("npc_id") or ""), str(row.get("id") or ""), str(row.get("name") or "")}:
            loc = row.get("location_id") or row.get("location") or row.get("last_seen")
            if loc:
                return _bounded_str(loc, 160)
    return _bounded_str(rolling_state.get("scene") or rolling_state.get("location") or "local", 160)


def _target_location(goal: Mapping[str, Any], rolling_state: Mapping[str, Any], actor_id: str) -> str:
    locations = _bounded_str_list(goal.get("target_location_ids"), MAX_ACTION_REFS)
    return locations[0] if locations else _actor_location(actor_id, rolling_state)


def _target_actor(goal: Mapping[str, Any]) -> str:
    actors = _bounded_str_list(goal.get("target_actor_ids"), MAX_ACTION_REFS)
    return actors[0] if actors else ""


def _goal_factions(goal: Mapping[str, Any]) -> List[str]:
    if str(goal.get("owner_type") or "") == "faction":
        return _bounded_str_list(goal.get("owner_id"), MAX_ACTION_REFS)
    return []


def _pressure_node_for_goal(goal: Mapping[str, Any], replayability_state: Mapping[str, Any]) -> Tuple[str, int]:
    graph = replayability_state.get("pressure_graph") if isinstance(replayability_state, Mapping) else {}
    supported = set(_bounded_str_list(goal.get("supporting_pressure_ids"), MAX_ACTION_REFS))
    best_id = ""
    best_magnitude = 0
    for node in (graph or {}).get("nodes") or []:
        if not isinstance(node, Mapping) or node.get("status") != "active":
            continue
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        if supported and node_id not in supported:
            continue
        magnitude = _clamp_int(node.get("magnitude"), 0, 100)
        if magnitude > best_magnitude or (magnitude == best_magnitude and node_id < best_id):
            best_id = node_id
            best_magnitude = magnitude
    return best_id, best_magnitude


def _select_goal_for_actor(goals: Sequence[Mapping[str, Any]], actor_id: str) -> Optional[Dict[str, Any]]:
    actor_goals = [dict(row) for row in goals if str(row.get("owner_id") or "") == actor_id]
    if not actor_goals:
        return None
    actor_goals.sort(
        key=lambda row: (
            -_clamp_int(row.get("priority"), 0, 10),
            -_clamp_int(row.get("urgency"), 0, 10),
            _clamp_int(row.get("current_step_index"), 0, 99),
            str(row.get("goal_id") or ""),
        )
    )
    return actor_goals[0]


def _utility_action_kind(action_type: str) -> str:
    action_type = _bounded_str(action_type, 40)
    return UTILITY_ACTION_KIND_BY_ACTION_TYPE.get(action_type, action_type)


def _utility_inputs_for_actor(snapshot: Any, actor_id: str) -> Dict[str, Any]:
    for ref in getattr(snapshot, "utility_input_refs", ()) or ():
        if isinstance(ref, Mapping) and str(ref.get("actor_id") or "") == actor_id:
            return dict(ref)
    return {}


def _utility_personality_order(preferred: str) -> List[str]:
    preferred = _bounded_str(preferred, 40)
    ordered = [preferred] if preferred else []
    for action in UTILITY_ACTION_KINDS:
        if action and action not in ordered:
            ordered.append(action)
    return ordered


def _float4(value: Any) -> Optional[float]:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _utility_score_row_summary(
    row: Mapping[str, Any],
    candidate_by_key: Mapping[Tuple[str, str, str, str], Mapping[str, Any]],
) -> Dict[str, Any]:
    key = (
        str(row.get("actor_id") or ""),
        str(row.get("action_kind") or ""),
        str(row.get("target_kind") or ""),
        str(row.get("target_id") or ""),
    )
    candidate = candidate_by_key.get(key) or {}
    out: Dict[str, Any] = {
        "goal_id": candidate.get("goal_id") or row.get("target_id"),
        "action_kind": row.get("action_kind"),
        "npc_action_type": candidate.get("npc_action_type") or row.get("action_kind"),
        "target_kind": row.get("target_kind"),
        "target_id": row.get("target_id"),
    }
    for key_name in ("base_utility", "noisy_utility", "pressure_modifier", "situation_modifier", "goal_modifier"):
        number = _float4(row.get(key_name))
        if number is not None:
            out[key_name] = number
    for key_name in ("pressure_node_ids", "situation_ids", "goal_ids"):
        if row.get(key_name):
            out[key_name] = _bounded_str_list(row.get(key_name), MAX_ACTION_REFS)
    return out


def _utility_selection_summary(
    result: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    candidate_by_key = {
        (
            str(row.get("actor_id") or ""),
            str(row.get("action_kind") or ""),
            str(row.get("target_kind") or ""),
            str(row.get("target_id") or ""),
        ): row
        for row in candidates
        if isinstance(row, Mapping)
    }
    selected = result.get("selected") if isinstance(result.get("selected"), Mapping) else {}
    selected_key = (
        str(selected.get("actor_id") or ""),
        str(selected.get("action_kind") or ""),
        str(selected.get("target_kind") or ""),
        str(selected.get("target_id") or ""),
    )
    selected_candidate = candidate_by_key.get(selected_key) or {}
    score_table = [
        _utility_score_row_summary(row, candidate_by_key)
        for row in (result.get("score_table") or [])[:4]
        if isinstance(row, Mapping)
    ]
    summary: Dict[str, Any] = {
        "schema_version": result.get("schema_version"),
        "selected_goal_id": selected_candidate.get("goal_id") or selected.get("target_id"),
        "selected_action_kind": selected.get("action_kind"),
        "selected_npc_action_type": selected_candidate.get("npc_action_type") or selected.get("action_kind"),
        "selected_target_kind": selected.get("target_kind"),
        "selected_target_id": selected.get("target_id"),
        "candidate_set_hash": result.get("candidate_set_hash"),
        "candidates_evaluated": result.get("candidates_evaluated"),
        "score_table": score_table,
    }
    for key_name in ("base_utility", "noisy_utility", "pressure_modifier", "situation_modifier", "goal_modifier"):
        number = _float4(selected.get(key_name))
        if number is not None:
            summary[key_name] = number
    return summary


def _normalise_utility_selection(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    out: Dict[str, Any] = {
        "schema_version": value.get("schema_version"),
        "selected_goal_id": _bounded_str(value.get("selected_goal_id"), 160),
        "selected_action_kind": _bounded_str(value.get("selected_action_kind"), 80),
        "selected_npc_action_type": _bounded_str(value.get("selected_npc_action_type"), 80),
        "selected_target_kind": _bounded_str(value.get("selected_target_kind"), 80),
        "selected_target_id": _bounded_str(value.get("selected_target_id"), 160),
        "candidate_set_hash": _bounded_str(value.get("candidate_set_hash"), 160),
        "candidates_evaluated": _clamp_int(value.get("candidates_evaluated"), 0, 99),
    }
    for key_name in ("base_utility", "noisy_utility", "pressure_modifier", "situation_modifier", "goal_modifier"):
        number = _float4(value.get(key_name))
        if number is not None:
            out[key_name] = number
    rows: List[Dict[str, Any]] = []
    for row in value.get("score_table") or []:
        if not isinstance(row, Mapping):
            continue
        clean = {
            "goal_id": _bounded_str(row.get("goal_id"), 160),
            "action_kind": _bounded_str(row.get("action_kind"), 80),
            "npc_action_type": _bounded_str(row.get("npc_action_type"), 80),
            "target_kind": _bounded_str(row.get("target_kind"), 80),
            "target_id": _bounded_str(row.get("target_id"), 160),
        }
        for key_name in ("base_utility", "noisy_utility", "pressure_modifier", "situation_modifier", "goal_modifier"):
            number = _float4(row.get(key_name))
            if number is not None:
                clean[key_name] = number
        for key_name in ("pressure_node_ids", "situation_ids", "goal_ids"):
            if row.get(key_name):
                clean[key_name] = _bounded_str_list(row.get(key_name), MAX_ACTION_REFS)
        rows.append(clean)
        if len(rows) >= 4:
            break
    if rows:
        out["score_table"] = rows
    return {key: value for key, value in out.items() if value not in ("", None, [], {})}


def _goal_utility_candidate(
    goal: Mapping[str, Any],
    *,
    snapshot: Any,
    rolling_state: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
    run_seed: str,
) -> Optional[Dict[str, Any]]:
    actor_id = _bounded_str(goal.get("owner_id"), 160)
    goal_id = _bounded_str(goal.get("goal_id"), 160)
    if not actor_id or not goal_id:
        return None
    action_type = _action_type_for_goal(goal)
    utility_action = _utility_action_kind(action_type)
    inputs = _utility_inputs_for_actor(snapshot, actor_id)
    actor_inputs = {
        **inputs,
        "goal_kind": str(goal.get("goal_type") or inputs.get("goal_kind") or ""),
        "goal_priority": _clamp_int(goal.get("priority"), 0, 10) / 10.0,
        "goal_urgency": _clamp_int(goal.get("urgency"), 0, 10) / 10.0,
    }
    try:
        import utility_ai

        bundle = utility_ai.build_canonical_dimension_bundle(
            snapshot,
            actor_id=actor_id,
            action_kind=utility_action,
            target_kind="goal",
            aligned_goals=frozenset({str(goal.get("goal_type") or "")}),
            relationship_deltas={},
            actor_inputs=actor_inputs,
        )
    except Exception:
        return None
    return {
        "actor_id": actor_id,
        "action_kind": utility_action,
        "target_kind": "goal",
        "target_id": goal_id,
        "goal_id": goal_id,
        "goal_type": goal.get("goal_type"),
        "npc_action_type": action_type,
        "dimension_scores": bundle["dimension_scores"],
        "dimension_score_records": bundle["dimension_score_records"],
        "replacement_authorised": bundle["replacement_authorised"],
        "blocker_codes": bundle["blocker_codes"],
        "goal_priority": float(actor_inputs["goal_priority"] or 0.0),
        "pressure_intensity": float(actor_inputs.get("highest_pressure_intensity") or 0.0),
        "stress": float(actor_inputs.get("stress_level") or 0.0),
        "relationship_importance": float(actor_inputs.get("relationship_importance") or 5.0),
        "resource_scarcity": float(actor_inputs.get("resource_scarcity") or 0.0),
        "trauma_intensity": 0.0,
        "starving": bool(actor_inputs.get("starving")),
        "personality_order": _utility_personality_order(utility_action),
        "run_seed": run_seed,
        "target_location": _target_location(goal, rolling_state, actor_id),
        "target_actor": _target_actor(goal),
        "replayability_state_seen": bool(replayability_state),
    }


def _select_goal_with_utility(
    actor_goals: Sequence[Mapping[str, Any]],
    *,
    actor_id: str,
    replayability_state: Mapping[str, Any],
    rolling_state: Mapping[str, Any],
    run_seed: str,
    turn_number: int,
    utility_snapshot: Optional[Any] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], List[Dict[str, Any]], bool]:
    if not actor_goals:
        return None, None, [], False
    snapshot = utility_snapshot
    if snapshot is None:
        try:
            from foundation_snapshot import FoundationTurnSnapshot

            snapshot = FoundationTurnSnapshot.build(
                run_seed=run_seed,
                turn_sequence=turn_number,
                rolling_state=rolling_state if isinstance(rolling_state, Mapping) else {},
                replayability_state=replayability_state if isinstance(replayability_state, Mapping) else {},
            )
        except Exception:
            snapshot = None
    if snapshot is None:
        return None, None, [], False

    candidates = [
        candidate
        for goal in actor_goals
        for candidate in [
            _goal_utility_candidate(
                goal,
                snapshot=snapshot,
                rolling_state=rolling_state if isinstance(rolling_state, Mapping) else {},
                replayability_state=replayability_state,
                run_seed=run_seed,
            )
        ]
        if candidate
    ]
    if not candidates:
        return None, None, [], False
    try:
        import utility_ai

        result = utility_ai.select_action(
            candidates,
            snapshot=snapshot,
            actor_resolution={
                "acting_actor_ids": [actor_id],
                "tiers_by_actor_id": {actor_id: "goal_owned"},
            },
        )
    except Exception:
        return None, None, candidates, False
    selected = result.get("selected") if isinstance(result.get("selected"), Mapping) else None
    if not selected:
        return None, _utility_selection_summary(result, candidates), candidates, False
    selected_key = (
        str(selected.get("actor_id") or ""),
        str(selected.get("action_kind") or ""),
        str(selected.get("target_kind") or ""),
        str(selected.get("target_id") or ""),
    )
    by_key = {
        (
            str(row.get("actor_id") or ""),
            str(row.get("action_kind") or ""),
            str(row.get("target_kind") or ""),
            str(row.get("target_id") or ""),
        ): row
        for row in candidates
    }
    candidate = by_key.get(selected_key)
    if not candidate:
        return None, _utility_selection_summary(result, candidates), candidates, False
    goal_id = str(candidate.get("goal_id") or "")
    for goal in actor_goals:
        if str(goal.get("goal_id") or "") == goal_id:
            return dict(goal), _utility_selection_summary(result, candidates), candidates, True
    return None, _utility_selection_summary(result, candidates), candidates, False


def _outcome_for(goal: Mapping[str, Any], action_type: str) -> str:
    step = _current_step(goal)
    if goal.get("status") == "blocked" or step.get("status") == "blocked":
        return "blocked"
    blockers = {str(item or "").strip().lower() for item in goal.get("blockers") or []}
    if (
        action_type in {"search", "investigate"}
        and "uncertain_location" in blockers
        and not _bounded_str_list(goal.get("target_location_ids"), MAX_ACTION_REFS)
    ):
        return "failure"
    return "success"


def _event_kind(action_type: str, outcome: str, goal_type: str) -> str:
    if outcome == "blocked":
        return "npc_waited"
    if outcome == "failure":
        return "npc_failed_search" if action_type in {"search", "investigate"} else "npc_action_failed"
    if action_type == "travel":
        return "npc_travelled"
    if action_type in {"investigate", "search", "observe"}:
        return "npc_found_clue"
    if action_type == "gather":
        return "npc_gathered_food" if goal_type == "secure_food" else "npc_secured_resource"
    if action_type == "trade":
        return "npc_secured_resource"
    if action_type == "repair":
        return "npc_repaired_bridge"
    if action_type == "recruit":
        return "npc_recruited_member"
    if action_type == "warn":
        return "npc_warned_settlement"
    if action_type == "hide":
        return "npc_hid_evidence"
    if action_type in {"patrol", "defend", "escort", "support"}:
        return "npc_defended_area"
    if action_type == "attack":
        return "npc_attacked"
    if action_type == "retreat":
        return "npc_retreated"
    if action_type == "negotiate":
        return "npc_negotiated"
    if action_type == "deliver":
        return "npc_delivered_resource"
    return "npc_waited"


def _action_id(
    run_seed: str,
    *,
    actor_id: str,
    goal_id: str,
    action_type: str,
    target_location: str,
    target_actor: str,
    turn_number: int,
) -> str:
    return _stable_id(
        "npc-action",
        run_seed,
        actor_id,
        goal_id,
        action_type,
        target_location,
        target_actor,
        turn_number,
    )


def _event_id(run_seed: str, action_id: str, event_kind: str, turn_number: int) -> str:
    return _stable_id("npc-action-event", run_seed, action_id, event_kind, turn_number)


def _normalise_action(row: Mapping[str, Any]) -> Dict[str, Any]:
    action_type = _bounded_str(row.get("action_type") or "wait", 40)
    if action_type not in ACTION_TYPES:
        action_type = "wait"
    outcome = _bounded_str(row.get("outcome") or "success", 40)
    if outcome not in ACTION_OUTCOMES:
        outcome = "success"
    status = _bounded_str(row.get("status") or "resolved", 40)
    if status not in ACTION_STATUSES:
        status = "resolved"
    created_turn = max(0, _coerce_int(row.get("created_turn"), 0))
    resolved_turn = max(created_turn, _coerce_int(row.get("resolved_turn"), created_turn))
    return {
        "action_id": _bounded_str(row.get("action_id"), 160),
        "actor_id": _bounded_str(row.get("actor_id"), 160),
        "goal_id": _bounded_str(row.get("goal_id"), 160),
        "situation_id": _bounded_str(row.get("situation_id"), 160),
        "action_type": action_type,
        "target_actor": _bounded_str(row.get("target_actor"), 160),
        "target_location": _bounded_str(row.get("target_location"), 160),
        "priority": _clamp_int(row.get("priority"), 0, 100, default=50),
        "status": status,
        "outcome": outcome,
        "created_turn": created_turn,
        "resolved_turn": resolved_turn,
        "resulting_event_ids": _bounded_str_list(row.get("resulting_event_ids"), MAX_ACTION_REFS),
        "source_event_ids": _bounded_str_list(row.get("source_event_ids"), MAX_ACTION_REFS),
        "goal_title": _bounded_str(row.get("goal_title"), 120),
        "goal_progress": _clamp_int(row.get("goal_progress"), 0, 100),
        "destination": _bounded_str(row.get("destination") or row.get("target_location"), 160),
        "selection_source": _bounded_str(row.get("selection_source") or "priority", 40),
        "utility_selection": _normalise_utility_selection(row.get("utility_selection")),
    }


def _action_summary(action: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "action_id": action.get("action_id"),
        "actor_id": action.get("actor_id"),
        "goal_id": action.get("goal_id"),
        "action_type": action.get("action_type"),
        "status": action.get("status"),
        "outcome": action.get("outcome"),
        "resolved_turn": action.get("resolved_turn"),
        "resulting_event_ids": list(action.get("resulting_event_ids") or [])[:MAX_ACTION_REFS],
        "selection_source": action.get("selection_source"),
    }


def _receipt_id(receipt_type: str, action_id: str, turn_number: int, detail: str = "") -> str:
    return _stable_id("npc-action-receipt", receipt_type, action_id, turn_number, detail)


def _append_receipt(
    replayability_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    receipt_type: str,
    action: Mapping[str, Any],
    turn_number: int,
    detail: str,
) -> bool:
    if receipt_type not in ACTION_RECEIPT_TYPES:
        return False
    action_id = _bounded_str(action.get("action_id"), 160)
    if not action_id:
        return False
    rid = _receipt_id(receipt_type, action_id, turn_number, detail)
    receipts = replayability_state.setdefault("npc_action_receipts", [])
    if any(isinstance(row, Mapping) and row.get("receipt_id") == rid for row in receipts):
        return False
    receipt = {
        "version": NPC_ACTION_ENGINE_VERSION,
        "receipt_id": rid,
        "receipt_type": receipt_type,
        "turn": turn_number,
        "action_id": action_id,
        "actor_id": action.get("actor_id"),
        "goal_id": action.get("goal_id"),
        "detail": _bounded_str(detail, 120),
        "after": _action_summary(action),
        "source_event_ids": list(action.get("source_event_ids") or [])[:MAX_ACTION_REFS],
    }
    utility_selection = _normalise_utility_selection(action.get("utility_selection"))
    if receipt_type == "npc_action_selected" and utility_selection:
        receipt["utility_selection"] = utility_selection
    receipts.append(receipt)
    if len(receipts) > MAX_NPC_ACTION_RECEIPTS:
        replayability_state["npc_action_receipts"] = receipts[-MAX_NPC_ACTION_RECEIPTS:]
    local_receipts.append(receipt)
    return True


def _build_action_and_event(
    goal: Mapping[str, Any],
    *,
    replayability_state: Mapping[str, Any],
    rolling_state: Mapping[str, Any],
    run_seed: str,
    turn_number: int,
    action_type_override: str = "",
    utility_selection: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    actor_id = _bounded_str(goal.get("owner_id"), 160)
    goal_id = _bounded_str(goal.get("goal_id"), 160)
    action_type = _bounded_str(action_type_override, 40) or _action_type_for_goal(goal)
    if action_type not in ACTION_TYPES:
        action_type = _action_type_for_goal(goal)
    outcome = _outcome_for(goal, action_type)
    if outcome == "blocked":
        action_type = "wait"
    target_location = _target_location(goal, rolling_state, actor_id)
    target_actor = _target_actor(goal)
    situation_ids = _bounded_str_list(goal.get("parent_situation_ids"), MAX_ACTION_REFS)
    situation_id = situation_ids[0] if situation_ids else ""
    pressure_node_id, pressure_magnitude = _pressure_node_for_goal(goal, replayability_state)
    priority = min(100, _clamp_int(goal.get("priority"), 0, 10) * 10 + _clamp_int(goal.get("urgency"), 0, 10))
    action_id = _action_id(
        run_seed,
        actor_id=actor_id,
        goal_id=goal_id,
        action_type=action_type,
        target_location=target_location,
        target_actor=target_actor,
        turn_number=turn_number,
    )
    kind = _event_kind(action_type, outcome, str(goal.get("goal_type") or ""))
    event_id = _event_id(run_seed, action_id, kind, turn_number)
    source_ids = _bounded_str_list([goal_id] + list(goal.get("source_event_ids") or []), MAX_ACTION_REFS)
    action = _normalise_action(
        {
            "action_id": action_id,
            "actor_id": actor_id,
            "goal_id": goal_id,
            "situation_id": situation_id,
            "action_type": action_type,
            "target_actor": target_actor,
            "target_location": target_location,
            "priority": priority,
            "status": "resolved",
            "outcome": outcome,
            "created_turn": turn_number,
            "resolved_turn": turn_number,
            "resulting_event_ids": [event_id],
            "source_event_ids": source_ids,
            "goal_title": goal.get("title"),
            "goal_progress": goal.get("progress"),
            "destination": target_location,
            "selection_source": "utility_ai" if utility_selection else "priority",
            "utility_selection": utility_selection or {},
        }
    )
    effects: List[Dict[str, Any]] = []
    if pressure_node_id and outcome == "success":
        effects.append(
            {
                "effect_type": "pressure_magnitude",
                "pressure_node_id": pressure_node_id,
                "delta": -4,
                "source_event_id": event_id,
            }
        )
    event = {
        "event_type": "npc_action_event",
        "event_kind": kind,
        "event_id": event_id,
        "action_id": action_id,
        "actor_ids": [actor_id],
        "goal_id": goal_id,
        "situation_id": situation_id,
        "location_ids": [target_location] if target_location else [],
        "faction_ids": _goal_factions(goal),
        "turn": turn_number,
        "outcome": outcome,
        "magnitude": max(priority, pressure_magnitude),
        "tags": _bounded_str_list(["npc_action", action_type, outcome, str(goal.get("goal_type") or "")], 8),
        "effects": effects,
    }
    if target_actor:
        event["target_actor"] = target_actor
    if pressure_node_id:
        event["pressure_node_id"] = pressure_node_id
    return action, event


def _cap_actions(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    actions = [_normalise_action(row) for row in actions if isinstance(row, Mapping)]
    if len(actions) > MAX_NPC_ACTIONS:
        actions = sorted(
            actions,
            key=lambda row: (
                -_coerce_int(row.get("resolved_turn"), 0),
                -_coerce_int(row.get("priority"), 0),
                str(row.get("action_id") or ""),
            ),
        )[:MAX_NPC_ACTIONS]
    return sorted(actions, key=lambda row: (_coerce_int(row.get("created_turn"), 0), str(row.get("action_id") or "")))


def evolve_npc_actions(
    replayability_state: Dict[str, Any],
    rolling_state: Mapping[str, Any],
    turn_number: int,
    *,
    run_seed: str = "",
    utility_snapshot: Optional[Any] = None,
) -> Dict[str, Any]:
    diagnostics = {
        "npc_action_engine_executed": False,
        "npc_action_candidates_evaluated": 0,
        "npc_action_utility_candidates_evaluated": 0,
        "npc_action_utility_selections": 0,
        "npc_action_utility_fallbacks": 0,
        "npc_actions_created": 0,
        "npc_action_events_generated": 0,
        "npc_action_duplicate_suppressed": 0,
    }
    if not isinstance(replayability_state, dict):
        return {"actions": [], "events": [], "receipts": [], "diagnostics": diagnostics}

    seed = run_seed or str(replayability_state.get("run_seed") or "npc-action-engine")
    actions = [
        _normalise_action(row)
        for row in replayability_state.get("npc_actions") or []
        if isinstance(row, Mapping)
    ]
    replayability_state["npc_actions"] = actions
    replayability_state.setdefault("npc_action_receipts", [])
    local_receipts: List[Dict[str, Any]] = []
    local_actions: List[Dict[str, Any]] = []
    local_events: List[Dict[str, Any]] = []

    goals = _active_goals(replayability_state)
    actors = sorted({str(goal.get("owner_id") or "") for goal in goals if goal.get("owner_id")})
    existing_action_ids = {str(row.get("action_id") or "") for row in actions}

    for actor_id in actors:
        if len(local_actions) >= MAX_NPC_ACTIONS_PER_TICK or len(local_events) >= MAX_ACTION_EVENTS_PER_TICK:
            break
        actor_goals = [dict(row) for row in goals if str(row.get("owner_id") or "") == actor_id]
        goal, utility_selection, utility_candidates, utility_selected = _select_goal_with_utility(
            actor_goals,
            actor_id=actor_id,
            replayability_state=replayability_state,
            rolling_state=rolling_state if isinstance(rolling_state, Mapping) else {},
            run_seed=seed,
            turn_number=turn_number,
            utility_snapshot=utility_snapshot,
        )
        if utility_candidates:
            diagnostics["npc_action_utility_candidates_evaluated"] += len(utility_candidates)
            diagnostics["npc_action_candidates_evaluated"] += len(utility_candidates)
        if utility_selected:
            diagnostics["npc_action_utility_selections"] += 1
        else:
            diagnostics["npc_action_utility_fallbacks"] += 1
            goal = _select_goal_for_actor(goals, actor_id)
            if not utility_candidates:
                diagnostics["npc_action_candidates_evaluated"] += 1
        if not goal:
            continue
        action_type_override = ""
        if utility_selected and utility_selection:
            action_type_override = _bounded_str(utility_selection.get("selected_npc_action_type"), 40)
        action, event = _build_action_and_event(
            goal,
            replayability_state=replayability_state,
            rolling_state=rolling_state if isinstance(rolling_state, Mapping) else {},
            run_seed=seed,
            turn_number=turn_number,
            action_type_override=action_type_override,
            utility_selection=utility_selection if utility_selected else None,
        )
        action_id = str(action.get("action_id") or "")
        if not action_id or action_id in existing_action_ids:
            diagnostics["npc_action_duplicate_suppressed"] += 1
            continue
        actions.append(action)
        existing_action_ids.add(action_id)
        local_actions.append(action)
        local_events.append(event)
        if _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type="npc_action_selected",
            action=action,
            turn_number=turn_number,
            detail=(
                f"utility_selected:{action.get('action_type')}"
                if utility_selected
                else "selected_from_goal"
            ),
        ):
            diagnostics["npc_actions_created"] += 1
        _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type="npc_action_resolved",
            action=action,
            turn_number=turn_number,
            detail=f"outcome:{action.get('outcome')}",
        )
        if event.get("event_id"):
            _append_receipt(
                replayability_state,
                local_receipts,
                receipt_type="npc_action_event_generated",
                action=action,
                turn_number=turn_number,
                detail=str(event.get("event_kind") or "event_generated"),
            )
            diagnostics["npc_action_events_generated"] += 1

    replayability_state["npc_actions"] = _cap_actions(actions)
    diagnostics["npc_action_engine_executed"] = bool(local_actions or replayability_state["npc_actions"])
    return {
        "actions": local_actions,
        "events": local_events,
        "receipts": local_receipts,
        "diagnostics": diagnostics,
    }


def latest_action_for_goal_engine(actions: Sequence[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    successful = [
        _normalise_action(row)
        for row in actions
        if isinstance(row, Mapping) and row.get("outcome") == "success"
    ]
    if not successful:
        return None
    successful.sort(key=lambda row: (-_coerce_int(row.get("resolved_turn"), 0), str(row.get("action_id") or "")))
    action = successful[0]
    return {
        "receipt_id": action.get("resulting_event_ids", [""])[0] if action.get("resulting_event_ids") else action.get("action_id"),
        "event_id": action.get("resulting_event_ids", [""])[0] if action.get("resulting_event_ids") else action.get("action_id"),
        "npc_id": action.get("actor_id"),
        "actor_id": action.get("actor_id"),
        "goal_id": action.get("goal_id"),
        "move_kind": action.get("action_type"),
        "action_kind": action.get("action_type"),
        "target_id": action.get("target_location") or action.get("target_actor"),
        "outcome": action.get("outcome"),
    }


def pressure_mitigations_from_events(events: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for event in events or []:
        if not isinstance(event, Mapping):
            continue
        for effect in event.get("effects") or []:
            if not isinstance(effect, Mapping) or effect.get("effect_type") != "pressure_magnitude":
                continue
            delta = _coerce_int(effect.get("delta"), 0)
            if delta >= 0:
                continue
            node_id = _bounded_str(effect.get("pressure_node_id") or effect.get("target_id"), 160)
            source_id = _bounded_str(effect.get("source_event_id") or event.get("event_id"), 160)
            if not node_id or not source_id:
                continue
            out.append(
                {
                    "pressure_node_id": node_id,
                    "delta": delta,
                    "source_event_id": source_id,
                }
            )
    out.sort(key=lambda row: (row["pressure_node_id"], row["source_event_id"]))
    return out[:MAX_ACTION_EVENTS_PER_TICK]


def copy_action_state(replayability_state: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(replayability_state, Mapping):
        return {"npc_actions": []}
    return {
        "npc_actions": _cap_actions(
            [
                _normalise_action(row)
                for row in replayability_state.get("npc_actions") or []
                if isinstance(row, Mapping)
            ]
        )
    }


def _projected_action_row(action: Mapping[str, Any], goals_by_id: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    goal = goals_by_id.get(str(action.get("goal_id") or "")) or {}
    return {
        "current_action": str(action.get("action_type") or "").replace("_", " "),
        "destination": action.get("destination") or action.get("target_location") or "",
        "goal_title": goal.get("title") or action.get("goal_title") or "",
        "progress": goal.get("progress", action.get("goal_progress", 0)),
        "status": goal.get("status") or action.get("status") or "",
    }


def project_active_npc_actions_for_rolling(
    replayability_state: Mapping[str, Any],
    *,
    limit: int = MAX_PROJECTED_ACTIONS,
) -> List[Dict[str, Any]]:
    if not isinstance(replayability_state, Mapping):
        return []
    actions = [
        _normalise_action(row)
        for row in replayability_state.get("npc_actions") or []
        if isinstance(row, Mapping)
    ]
    actions.sort(
        key=lambda row: (
            -_coerce_int(row.get("resolved_turn"), 0),
            -_coerce_int(row.get("priority"), 0),
            str(row.get("action_id") or ""),
        )
    )
    goals_by_id = _goal_by_id(replayability_state)
    projected: List[Dict[str, Any]] = []
    seen_actors = set()
    for action in actions:
        actor_id = str(action.get("actor_id") or "")
        if actor_id in seen_actors:
            continue
        seen_actors.add(actor_id)
        projected.append(_projected_action_row(action, goals_by_id))
        if len(projected) >= max(0, min(MAX_PROJECTED_ACTIONS, int(limit or 0))):
            break
    return projected


def project_actions_for_prompt(replayability_state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return project_active_npc_actions_for_rolling(replayability_state, limit=MAX_PROMPT_ACTIONS)


def prompt_safe_rolling_state(rolling_state: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(rolling_state, Mapping):
        return {}
    safe = copy.deepcopy(dict(rolling_state))
    rows = safe.get("active_npc_actions")
    if not isinstance(rows, list):
        return safe
    cleaned: List[Dict[str, Any]] = []
    for row in rows[:MAX_PROMPT_ACTIONS]:
        if not isinstance(row, Mapping):
            continue
        cleaned.append({key: copy.deepcopy(row.get(key)) for key in PROMPT_ACTION_FIELDS if key in row})
    safe["active_npc_actions"] = cleaned
    return safe


def _token_set(*values: Any) -> set:
    out = set()
    for value in values:
        raw = value if isinstance(value, (list, tuple, set)) else [value]
        for item in raw:
            text = str(item or "").strip().lower()
            if text:
                out.add(text)
    return out


def actions_for_context(
    action_state: Mapping[str, Any],
    *,
    actor_ids: Sequence[str] = (),
    goal_ids: Sequence[str] = (),
    location_ids: Sequence[str] = (),
    action_ids: Sequence[str] = (),
    limit: int = MAX_CONTEXT_ACTIONS,
) -> List[Dict[str, Any]]:
    if not isinstance(action_state, Mapping):
        return []
    actor_tokens = _token_set(actor_ids)
    goal_tokens = _token_set(goal_ids)
    location_tokens = _token_set(location_ids)
    action_tokens = _token_set(action_ids)
    matched: List[Dict[str, Any]] = []
    for raw in action_state.get("npc_actions") or []:
        if not isinstance(raw, Mapping):
            continue
        action = _normalise_action(raw)
        applies = False
        if action.get("action_id") and str(action.get("action_id")).lower() in action_tokens:
            applies = True
        if action.get("actor_id") and str(action.get("actor_id")).lower() in actor_tokens:
            applies = True
        if action.get("goal_id") and str(action.get("goal_id")).lower() in goal_tokens:
            applies = True
        if action.get("target_location") and str(action.get("target_location")).lower() in location_tokens:
            applies = True
        if applies:
            matched.append(action)
    matched.sort(
        key=lambda row: (
            -_coerce_int(row.get("resolved_turn"), 0),
            -_coerce_int(row.get("priority"), 0),
            str(row.get("action_id") or ""),
        )
    )
    return matched[: max(0, min(MAX_CONTEXT_ACTIONS, int(limit or 0)))]
