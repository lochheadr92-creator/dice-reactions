"""ADR-024 Phase 1 -- shadow comparison ONLY.

Scores the npc_world_moves candidate set with the canonical Ch 27 Utility AI
model and records agreement vs the live heuristic pick, for side-by-side
evaluation. Diagnostic/internal only: it never selects, commits, mutates state,
hands off action selection, or promotes Utility AI to load-bearing.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

import stress
import utility_ai

SHADOW_SCHEMA_VERSION = 1


def _candidate_utility(snapshot: Any, candidate: Mapping[str, Any]) -> Optional[float]:
    """Canonical Ch 27 utility for one npc_world_moves candidate (mirrors
    candidates_from_agendas + select_action scoring, incl. P2 stress bands)."""
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
    baseline = utility_ai.compute_dimension_weights(
        pressure_intensity=float(inputs.get("highest_pressure_intensity") or 0.0),
        stress=float(inputs.get("stress_level") or 0.0),
        goal_priority=10.0 if inputs.get("goal_kind") in aligned else 3.0,
        relationship_importance=float(inputs.get("relationship_importance") or 5.0),
        resource_scarcity=float(inputs.get("resource_scarcity") or 0.0),
        trauma_intensity=utility_ai._max_trauma(inputs.get("memory_signatures") or ()),
        starving=bool(inputs.get("starving")),
    )
    behaviour = stress.evaluate_stress_behaviour(inputs.get("stress_level"))
    weights = utility_ai.apply_stress_band_modifiers(baseline, behaviour["modifiers"])
    try:
        return utility_ai.compute_utility_score(bundle["dimension_scores"], weights)
    except utility_ai.UtilityAIError:
        return None


def _pick_id(row: Optional[Mapping[str, Any]]):
    if not row:
        return None
    return (row.get("actor_id"), row.get("move_kind"), row.get("target_id"))


def compare_move_scoring(
    snapshot: Any,
    candidates: Sequence[Mapping[str, Any]],
    heuristic_pick: Optional[Mapping[str, Any]],
    *,
    limit: int = 8,
) -> Dict[str, Any]:
    """Pure shadow comparison record. Never mutates inputs; never selects an action."""
    rows: List[Dict[str, Any]] = []
    for cand in list(candidates or [])[:limit]:
        rows.append(
            {
                "actor_id": str(cand.get("npc_id") or ""),
                "move_kind": str(cand.get("move_kind") or ""),
                "target_id": str(cand.get("target_id") or ""),
                "heuristic_score": cand.get("score"),
                "utility_score": _candidate_utility(snapshot, cand),
            }
        )
    scored = [r for r in rows if r["utility_score"] is not None]
    utility_pick = None
    if scored:
        utility_pick = sorted(
            scored,
            key=lambda r: (-float(r["utility_score"]), r["actor_id"], r["move_kind"], r["target_id"]),
        )[0]
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
        "note": "ADR-024 Phase 1 shadow only; live selection unchanged; no action handoff; Utility AI not promoted",
    }
