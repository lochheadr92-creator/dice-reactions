"""
Utility AI v0.1 — canonical score composition, ranking, tie handling, seeded noise.

Canon: Source_of_Truth_v1.2.md Ch 27 + Appendix A.4.
Domain modules retain action catalogues and target generation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from engine_determinism import (
    NUMERIC_CONTRACT_VERSION,
    build_seed_material,
    candidate_set_hash,
    derive_rng_range,
    evaluate_weighted_average,
    reject_non_finite,
    stable_hash,
)
from foundation_snapshot import FoundationTurnSnapshot

UTILITY_AI_SCHEMA_VERSION = 1
DECISION_VERSION = 1

# Appendix A.4 base weights (Ch 27.4.2)
BASE_WEIGHTS = {
    "survival": 100.0,
    "goal_progression": 50.0,
    "pressure_relief": 30.0,
    "stress_reduction": 20.0,
    "relationship_impact": 40.0,
    "resource_gain_loss": 25.0,
    "memory_avoidance": 15.0,
}

WHIM_NOISE_LOW = -0.5
WHIM_NOISE_HIGH = 0.5
TIE_WINDOW = 0.01

DIMENSION_ORDER = tuple(sorted(BASE_WEIGHTS.keys()))


class UtilityAIError(ValueError):
    pass


def compute_dimension_weights(
    *,
    pressure_intensity: float = 0.0,
    stress: float = 0.0,
    goal_priority: float = 5.0,
    relationship_importance: float = 5.0,
    resource_scarcity: float = 0.0,
    trauma_intensity: float = 0.0,
    starving: bool = False,
) -> Dict[str, float]:
    """Dynamic weights per Ch 27.4.2 table."""
    weights = dict(BASE_WEIGHTS)
    if starving:
        weights["survival"] = 200.0
    else:
        weights["survival"] *= 1.0 + max(0.0, pressure_intensity)
    weights["goal_progression"] *= max(0.1, goal_priority / 10.0)
    weights["pressure_relief"] *= max(0.0, 1.0 + pressure_intensity)
    weights["stress_reduction"] *= max(0.0, stress / 100.0)
    weights["relationship_impact"] *= max(0.1, relationship_importance / 5.0)
    weights["resource_gain_loss"] *= 1.0 + max(0.0, resource_scarcity)
    if trauma_intensity > 0:
        weights["memory_avoidance"] *= 1.0 + min(2.0, trauma_intensity)
    return weights


def compute_utility_score(
    dimension_scores: Mapping[str, float],
    weights: Mapping[str, float],
) -> float:
    """U(a) = Σ(score × weight) / Σ(weight), bounded 0–100 when inputs are 0–100."""
    components = []
    for name in DIMENSION_ORDER:
        if name not in dimension_scores:
            continue
        score = float(dimension_scores[name])
        weight = float(weights.get(name, 0.0))
        reject_non_finite(score)
        reject_non_finite(weight)
        components.append((name, score, weight))
    if not components:
        raise UtilityAIError("no dimension scores supplied")
    utility = evaluate_weighted_average(components)
    return max(0.0, min(100.0, utility))


def apply_whim_noise(
    utility: float,
    *,
    seed_material: str,
    draw_index: int,
) -> float:
    noise = derive_rng_range(seed_material, draw_index, WHIM_NOISE_LOW, WHIM_NOISE_HIGH)
    return utility + noise


def personality_tie_key(
    *,
    actor_id: str,
    action_kind: str,
    personality_order: Sequence[str],
) -> int:
    try:
        return list(personality_order).index(action_kind)
    except ValueError:
        return len(personality_order) + hash_stable_action(actor_id, action_kind)


def hash_stable_action(actor_id: str, action_kind: str) -> int:
    digest = stable_hash("personality_tie", {"actor_id": actor_id, "action_kind": action_kind})
    return int(digest[:8], 16)


def select_action(
    candidates: Sequence[Mapping[str, Any]],
    *,
    snapshot: FoundationTurnSnapshot,
    actor_resolution: Mapping[str, Any],
    seed_draw_start: int = 0,
) -> Dict[str, Any]:
    """
    Rank candidates with canonical utility, noise, and tie handling.

    Candidates must include:
      actor_id, action_kind, target_kind, target_id, dimension_scores, optional context
    """
    acting_ids = set(actor_resolution.get("acting_actor_ids") or [])
    feasible: List[Dict[str, Any]] = []
    for raw in candidates:
        actor_id = str(raw.get("actor_id") or "")
        if actor_id not in acting_ids:
            continue
        action_kind = str(raw.get("action_kind") or "")
        target_kind = str(raw.get("target_kind") or "")
        target_id = str(raw.get("target_id") or "")
        if not action_kind or not target_kind or not target_id:
            continue
        weights = compute_dimension_weights(
            pressure_intensity=float(raw.get("pressure_intensity", 0.0)),
            stress=float(raw.get("stress", 0.0)),
            goal_priority=float(raw.get("goal_priority", 5.0)),
            relationship_importance=float(raw.get("relationship_importance", 5.0)),
            resource_scarcity=float(raw.get("resource_scarcity", 0.0)),
            trauma_intensity=float(raw.get("trauma_intensity", 0.0)),
            starving=bool(raw.get("starving")),
        )
        base_utility = compute_utility_score(raw.get("dimension_scores") or {}, weights)
        c_hash = candidate_set_hash(
            actor_id=actor_id,
            action_kind=action_kind,
            target_kind=target_kind,
            target_id=target_id,
            decision_version=DECISION_VERSION,
            candidates=[raw],
        )
        seed_material = build_seed_material(
            run_seed=snapshot.run_seed,
            turn_sequence=snapshot.turn_sequence,
            subsystem="utility_ai",
            actor_id=actor_id,
            candidate_set_hash_value=c_hash,
        )
        noisy = apply_whim_noise(base_utility, seed_material=seed_material, draw_index=seed_draw_start)
        feasible.append(
            {
                "actor_id": actor_id,
                "action_kind": action_kind,
                "target_kind": target_kind,
                "target_id": target_id,
                "base_utility": base_utility,
                "noisy_utility": noisy,
                "weights": weights,
                "dimension_scores": dict(raw.get("dimension_scores") or {}),
                "personality_order": list(raw.get("personality_order") or []),
                "candidate_set_hash": c_hash,
                "seed_material": seed_material,
            }
        )

    if not feasible:
        return {
            "schema_version": UTILITY_AI_SCHEMA_VERSION,
            "selected": None,
            "candidates_evaluated": 0,
            "source_state_hash": snapshot.source_state_hash,
        }

    max_utility = max(row["noisy_utility"] for row in feasible)
    tied = [
        row
        for row in feasible
        if abs(row["noisy_utility"] - max_utility) <= TIE_WINDOW
    ]
    if len(tied) == 1:
        winner = tied[0]
    else:
        tied_sorted = sorted(
            tied,
            key=lambda row: (
                personality_tie_key(
                    actor_id=row["actor_id"],
                    action_kind=row["action_kind"],
                    personality_order=row.get("personality_order") or [],
                ),
                row["actor_id"],
                row["action_kind"],
                row["target_kind"],
                row["target_id"],
            ),
        )
        winner = tied_sorted[0]

    return {
        "schema_version": UTILITY_AI_SCHEMA_VERSION,
        "numeric_contract_version": NUMERIC_CONTRACT_VERSION,
        "source_state_hash": snapshot.source_state_hash,
        "selected": {
            "actor_id": winner["actor_id"],
            "action_kind": winner["action_kind"],
            "target_kind": winner["target_kind"],
            "target_id": winner["target_id"],
            "base_utility": winner["base_utility"],
            "noisy_utility": winner["noisy_utility"],
        },
        "selected_actor_id": winner["actor_id"],
        "selected_action_kind": winner["action_kind"],
        "selected_target_kind": winner["target_kind"],
        "selected_target_id": winner["target_id"],
        "candidate_set_hash": winner["candidate_set_hash"],
        "candidates_evaluated": len(feasible),
        "score_table": [
            {
                "actor_id": row["actor_id"],
                "action_kind": row["action_kind"],
                "target_kind": row["target_kind"],
                "target_id": row["target_id"],
                "base_utility": row["base_utility"],
                "noisy_utility": row["noisy_utility"],
            }
            for row in sorted(
                feasible,
                key=lambda r: (
                    -r["noisy_utility"],
                    r["actor_id"],
                    r["action_kind"],
                    r["target_kind"],
                    r["target_id"],
                ),
            )
        ],
        "state_hash": stable_hash("utility_ai_prepared", winner),
    }


def candidates_from_agendas(
    snapshot: FoundationTurnSnapshot,
    *,
    rolling_state: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
    run_seed: str,
) -> List[Dict[str, Any]]:
    """Bridge domain catalogue — uses npc_world_moves target resolution, not score_move."""
    import npc_agendas as agenda_mod
    import npc_world_moves as world_moves

    out: List[Dict[str, Any]] = []
    agendas_state = replayability_state.get("npc_agendas") or {}
    for agenda in agendas_state.get("agendas") or []:
        if not isinstance(agenda, dict):
            continue
        npc_id = str(agenda.get("npc_id") or "")
        display_name = str(agenda.get("display_name") or "")
        tier = world_moves.resolve_actor_tier(npc_id, display_name, rolling_state, snapshot.turn_sequence)
        for move_kind in world_moves.MOVE_KINDS:
            target = world_moves.resolve_move_target(
                move_kind, agenda, rolling_state, replayability_state
            )
            if not target:
                continue
            target_type, target_id = target
            vec, _ = agenda_mod.resolve_relationship_vector(npc_id, agenda, rolling_state)
            dimension_scores = _heuristic_dimension_scores(move_kind, target_type, agenda, vec)
            out.append(
                {
                    "actor_id": npc_id,
                    "action_kind": move_kind,
                    "target_kind": target_type,
                    "target_id": target_id,
                    "dimension_scores": dimension_scores,
                    "goal_priority": 7.0 if agenda.get("goal_kind") in world_moves.MOVE_GOAL_ALIGN.get(move_kind, ()) else 3.0,
                    "pressure_intensity": 0.4,
                    "stress": float(agenda.get("stress") or 20.0),
                    "personality_order": _personality_order(run_seed, npc_id),
                    "provisional_tier": tier,
                }
            )
    return out


def _heuristic_dimension_scores(
    move_kind: str,
    target_type: str,
    agenda: Mapping[str, Any],
    relationship: Optional[Mapping[str, Any]],
) -> Dict[str, float]:
    goal = str(agenda.get("goal_kind") or "")
    scores = {
        "survival": 40.0,
        "goal_progression": 70.0 if goal else 30.0,
        "pressure_relief": 45.0,
        "stress_reduction": 35.0,
        "relationship_impact": 40.0,
        "resource_gain_loss": 30.0,
        "memory_avoidance": 50.0,
    }
    if move_kind == "withdraw":
        scores["survival"] = 80.0
        scores["memory_avoidance"] = 85.0
    if move_kind == "protect" and target_type == "player":
        scores["relationship_impact"] = 75.0
    if relationship and move_kind == "pressure":
        scores["relationship_impact"] = min(100.0, float(relationship.get("resentment", 0)) / 2.0)
    return scores


def _personality_order(run_seed: str, actor_id: str) -> List[str]:
    from run_identity import select_from_namespace

    options = tuple(sorted(list(__import__("npc_world_moves").MOVE_KINDS)))
    primary = select_from_namespace(run_seed, f"personality:{actor_id}", options)
    rest = [opt for opt in options if opt != primary]
    return [primary, *rest]