"""ADR-024 bridge between Living Cast candidates and canonical Utility AI.

The comparison always runs for diagnostics. A separate, default-off feature
flag controls whether its ``utility_ai.select_action`` winner is handed to the
existing npc_world_moves commit path.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

import utility_ai

SHADOW_SCHEMA_VERSION = 2


def _utility_candidate(
    snapshot: Any, candidate: Mapping[str, Any]
) -> Optional[Dict[str, Any]]:
    """Adapt one eligible npc_world_moves candidate for utility_ai.select_action."""
    actor_id = str(candidate.get("npc_id") or "")
    move_kind = str(candidate.get("move_kind") or "")
    target_type = str(candidate.get("target_type") or "")
    target_id = str(candidate.get("target_id") or "")
    if not (actor_id and move_kind and target_type and target_id):
        return None
    import npc_world_moves as world_moves

    rel_deltas = world_moves._relationship_deltas_for_move(move_kind, target_type)
    bundle = utility_ai.build_canonical_dimension_bundle(
        snapshot,
        actor_id=actor_id,
        action_kind=move_kind,
        target_kind=target_type,
        aligned_goals=world_moves.MOVE_GOAL_ALIGN.get(move_kind, frozenset()),
        relationship_deltas=rel_deltas,
    )
    inputs = utility_ai._utility_inputs_for_actor(snapshot, actor_id)
    aligned = world_moves.MOVE_GOAL_ALIGN.get(move_kind, frozenset())
    return {
        "actor_id": actor_id,
        "action_kind": move_kind,
        "target_kind": target_type,
        "target_id": target_id,
        "dimension_scores": bundle["dimension_scores"],
        "dimension_score_records": bundle["dimension_score_records"],
        "replacement_authorised": bundle["replacement_authorised"],
        "blocker_codes": bundle["blocker_codes"],
        "goal_priority": 10.0 if inputs.get("goal_kind") in aligned else 3.0,
        "pressure_intensity": float(inputs.get("highest_pressure_intensity") or 0.0),
        "stress": float(inputs.get("stress_level") or 0.0),
        "relationship_importance": float(inputs.get("relationship_importance") or 5.0),
        "resource_scarcity": float(inputs.get("resource_scarcity") or 0.0),
        "trauma_intensity": utility_ai._max_trauma(inputs.get("memory_signatures") or ()),
        "starving": bool(inputs.get("starving")),
        "personality_order": utility_ai._personality_order(snapshot.run_seed, actor_id),
    }


def _pick_id(row: Optional[Mapping[str, Any]]):
    if not row:
        return None
    return (row.get("actor_id"), row.get("move_kind"), row.get("target_id"))


def _candidate_id(row: Mapping[str, Any]):
    return (row.get("npc_id"), row.get("move_kind"), row.get("target_id"))


def compare_move_scoring(
    snapshot: Any,
    candidates: Sequence[Mapping[str, Any]],
    heuristic_pick: Optional[Mapping[str, Any]],
    *,
    limit: int = 8,
) -> Dict[str, Any]:
    """Pure comparison record whose canonical winner comes from select_action."""
    source_candidates = list(candidates or [])[:limit]
    utility_candidates = [
        adapted
        for candidate in source_candidates
        if (adapted := _utility_candidate(snapshot, candidate)) is not None
    ]
    utility_blockers = {
        (row.get("actor_id"), row.get("action_kind"), row.get("target_id")): list(row.get("blocker_codes") or [])
        for row in utility_candidates
    }
    actor_ids = sorted({row["actor_id"] for row in utility_candidates})
    utility_result = utility_ai.select_action(
        utility_candidates,
        snapshot=snapshot,
        actor_resolution={"acting_actor_ids": actor_ids},
    )
    score_table = {
        (row.get("actor_id"), row.get("action_kind"), row.get("target_id")): row
        for row in utility_result.get("score_table") or []
    }
    rows: List[Dict[str, Any]] = []
    for cand in source_candidates:
        score = score_table.get(_candidate_id(cand)) or {}
        score_key = (
            str(cand.get("npc_id") or ""),
            str(cand.get("move_kind") or ""),
            str(cand.get("target_id") or ""),
        )
        rows.append(
            {
                "actor_id": str(cand.get("npc_id") or ""),
                "move_kind": str(cand.get("move_kind") or ""),
                "target_id": str(cand.get("target_id") or ""),
                "heuristic_score": cand.get("score"),
                "utility_score": score.get("base_utility"),
                "noisy_utility": score.get("noisy_utility"),
                "replacement_authorised": score.get("replacement_authorised"),
                "blocker_codes": utility_blockers.get(score_key) or [],
                "stress_blocker_code": score.get("stress_blocker_code"),
            }
        )
    utility_pick = None
    selected = utility_result.get("selected")
    if selected:
        selected_key = (
            selected.get("actor_id"),
            selected.get("action_kind"),
            selected.get("target_id"),
        )
        utility_pick = {
            "actor_id": selected.get("actor_id"),
            "move_kind": selected.get("action_kind"),
            "target_id": selected.get("target_id"),
            "utility_score": selected.get("base_utility"),
            "noisy_utility": selected.get("noisy_utility"),
            "replacement_authorised": selected.get("replacement_authorised"),
            "blocker_codes": utility_blockers.get(selected_key) or [],
            "stress_blocker_code": selected.get("stress_blocker_code"),
            "stress_band": selected.get("stress_band"),
        }
    heuristic_row = None
    if heuristic_pick:
        heuristic_row = {
            "actor_id": str(heuristic_pick.get("npc_id") or ""),
            "move_kind": str(heuristic_pick.get("move_kind") or ""),
            "target_id": str(heuristic_pick.get("target_id") or ""),
            "heuristic_score": heuristic_pick.get("score"),
        }
    agree = bool(heuristic_row and utility_pick and _pick_id(heuristic_row) == _pick_id(utility_pick))
    return {
        "shadow_schema_version": SHADOW_SCHEMA_VERSION,
        "candidate_count": len(rows),
        "heuristic_pick": heuristic_row,
        "utility_pick": utility_pick,
        "agree": agree,
        "scores": rows,
        "selector": "utility_ai.select_action",
        "note": "ADR-024 comparison always runs; live handoff is controlled by ENABLE_UTILITY_AI_LIVE_SELECTION",
    }


def choose_live_move(
    candidates: Sequence[Mapping[str, Any]],
    heuristic_pick: Optional[Mapping[str, Any]],
    comparison: Mapping[str, Any],
    *,
    enabled: bool,
    run_seed: str,
    turn_number: int,
) -> tuple[Optional[Dict[str, Any]], bool]:
    """Return the live move and whether Utility AI supplied it."""
    if not enabled:
        return dict(heuristic_pick) if heuristic_pick else None, False
    utility_pick = comparison.get("utility_pick") or {}
    if not utility_pick.get("replacement_authorised"):
        return dict(heuristic_pick) if heuristic_pick else None, False
    wanted = _pick_id(utility_pick)
    for candidate in candidates or []:
        if _candidate_id(candidate) != wanted:
            continue
        import npc_world_moves as world_moves

        move = dict(candidate)
        move["receipt_id"] = world_moves.stable_receipt_id(
            run_seed,
            str(move.get("npc_id") or ""),
            str(move.get("agenda_id") or ""),
            str(move.get("move_kind") or ""),
            turn_number,
            str(move.get("target_id") or ""),
        )
        move["turn"] = turn_number
        return move, True
    return dict(heuristic_pick) if heuristic_pick else None, False
