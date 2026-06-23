"""
Utility AI v0.1 — canonical score composition, ranking, tie handling, seeded noise.

Canon: Source_of_Truth_v1.2.md Ch 27 + Appendix A.4.
Domain modules retain action catalogues and target generation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import stress
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
from utility_dimensions import (
    DimensionScore,
    compute_dimension_scores,
    dimension_scores_to_aggregate_map,
)

UTILITY_AI_SCHEMA_VERSION = 2
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


# --- P2 stress behavioural integration (Ch 14 P2 -- shadow-only) -----------
# Diagnostic-only keys attached to each evaluated candidate for shadow tracing.
# They are EXCLUDED from the prepared decision hash (see _hashable_candidate):
# recording a band must not change canonical decision identity. A *valid* band's
# weight change DOES flow into the hash via "weights"/"base_utility" -- that is
# real scoring, not a diagnostic -- but CALM and any invalid/missing stress apply
# x1.0 modifiers and so leave the hash byte-identical.
_P2_SHADOW_KEYS = ("stress_band", "stress_input_valid", "stress_blocker_code")


def apply_stress_band_modifiers(
    weights: Mapping[str, float], modifiers: Mapping[str, float]
) -> Dict[str, float]:
    """Multiply canonical Ch 27 weights by P2 band modifiers exactly once.

    Identity (all-1.0) modifiers return bit-identical weights, so CALM and every
    fail-closed (invalid/missing) input leave the canonical weights unchanged.
    The band never selects an action directly -- it only reshapes the weighting.
    """
    return {
        name: float(weight) * float(modifiers.get(name, 1.0))
        for name, weight in weights.items()
    }


def _hashable_candidate(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluated-candidate projection excluding P2 diagnostic-only keys."""
    return {key: value for key, value in row.items() if key not in _P2_SHADOW_KEYS}


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


def build_canonical_dimension_bundle(
    snapshot: FoundationTurnSnapshot,
    *,
    actor_id: str,
    action_kind: str,
    target_kind: str,
    aligned_goals: frozenset[str],
    relationship_deltas: Mapping[str, int],
) -> Dict[str, Any]:
    scores = compute_dimension_scores(
        snapshot,
        actor_id=actor_id,
        action_kind=action_kind,
        target_kind=target_kind,
        aligned_goals=aligned_goals,
        relationship_deltas=relationship_deltas,
    )
    numeric, authorised, blockers = dimension_scores_to_aggregate_map(scores)
    return {
        "dimension_scores": numeric,
        "dimension_score_records": [ _score_record(row) for row in scores ],
        "replacement_authorised": authorised,
        "blocker_codes": blockers,
    }


def _score_record(row: DimensionScore) -> Dict[str, Any]:
    return {
        "dimension": row.dimension.value,
        "value": row.value,
        "source_status": row.source_status.value,
        "source_ids": list(row.source_ids),
        "canon_rule_id": row.canon_rule_id,
        "blocker_code": row.blocker_code,
    }


def select_action(
    candidates: Sequence[Mapping[str, Any]],
    *,
    snapshot: FoundationTurnSnapshot,
    actor_resolution: Mapping[str, Any],
    seed_draw_start: int = 0,
) -> Dict[str, Any]:
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
        dimension_scores = dict(raw.get("dimension_scores") or {})
        baseline_weights = compute_dimension_weights(
            pressure_intensity=float(raw.get("pressure_intensity", 0.0)),
            stress=float(raw.get("stress", 0.0)),
            goal_priority=float(raw.get("goal_priority", 5.0)),
            relationship_importance=float(raw.get("relationship_importance", 5.0)),
            resource_scarcity=float(raw.get("resource_scarcity", 0.0)),
            trauma_intensity=float(raw.get("trauma_intensity", 0.0)),
            starving=bool(raw.get("starving")),
        )
        # Ch 14 P2 (shadow-only): derive the behavioural profile from the
        # AUTHORITATIVE stress_level on the snapshot -- not the candidate "stress"
        # field, which candidates_from_agendas flattens missing -> 0.0 and would
        # misread as a valid CALM band. Modifiers apply EXACTLY ONCE here on top of
        # the canonical Ch 27 weights; missing/invalid stress yields identity
        # (x1.0) modifiers, so weights stay byte-identical.
        authoritative_stress = _utility_inputs_for_actor(snapshot, actor_id).get("stress_level")
        stress_behaviour = stress.evaluate_stress_behaviour(authoritative_stress)
        stress_input_valid = bool(stress_behaviour["valid"])
        weights = apply_stress_band_modifiers(baseline_weights, stress_behaviour["modifiers"])
        # Fail closed: missing/invalid authoritative stress can NEVER authorise a
        # replacement. The band never forces an action -- it only gates
        # authorisation and reshapes weights; selection stays argmax-with-noise.
        replacement_authorised = bool(raw.get("replacement_authorised")) and stress_input_valid
        base_utility = compute_utility_score(dimension_scores, weights)
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
                "dimension_scores": dimension_scores,
                "dimension_score_records": list(raw.get("dimension_score_records") or []),
                "replacement_authorised": replacement_authorised,
                "personality_order": list(raw.get("personality_order") or []),
                "candidate_set_hash": c_hash,
                "seed_material": seed_material,
                # P2 diagnostic-only (shadow) -- excluded from state_hash.
                "stress_band": stress_behaviour["band"],
                "stress_input_valid": stress_input_valid,
                "stress_blocker_code": stress_behaviour["blocker_code"],
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
    tied = [row for row in feasible if abs(row["noisy_utility"] - max_utility) <= TIE_WINDOW]
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
            "replacement_authorised": winner.get("replacement_authorised"),
            "stress_band": winner.get("stress_band"),
            "stress_input_valid": winner.get("stress_input_valid"),
            "stress_blocker_code": winner.get("stress_blocker_code"),
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
                "replacement_authorised": row.get("replacement_authorised"),
                "stress_band": row.get("stress_band"),
                "stress_input_valid": row.get("stress_input_valid"),
                "stress_blocker_code": row.get("stress_blocker_code"),
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
        "state_hash": stable_hash("utility_ai_prepared", _hashable_candidate(winner)),
    }


def candidates_from_agendas(
    snapshot: FoundationTurnSnapshot,
    *,
    rolling_state: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
    run_seed: str,
) -> List[Dict[str, Any]]:
    import npc_agendas as agenda_mod
    import npc_world_moves as world_moves

    out: List[Dict[str, Any]] = []
    agendas_state = replayability_state.get("npc_agendas") or {}
    agenda_rows = agendas_state.get("agendas") or agendas_state.get("active") or []
    for agenda in agenda_rows:
        if not isinstance(agenda, dict):
            continue
        npc_id = str(agenda.get("npc_id") or "")
        display_name = str(agenda.get("display_name") or "")
        tier = world_moves.resolve_actor_tier(npc_id, display_name, rolling_state, snapshot.turn_sequence)
        inputs = _utility_inputs_for_actor(snapshot, npc_id)
        for move_kind in world_moves.MOVE_KINDS:
            target = world_moves.resolve_move_target(
                move_kind, agenda, rolling_state, replayability_state
            )
            if not target:
                continue
            target_type, target_id = target
            rel_deltas = world_moves._relationship_deltas_for_move(move_kind, target_type)
            bundle = build_canonical_dimension_bundle(
                snapshot,
                actor_id=npc_id,
                action_kind=move_kind,
                target_kind=target_type,
                aligned_goals=world_moves.MOVE_GOAL_ALIGN.get(move_kind, frozenset()),
                relationship_deltas=rel_deltas,
            )
            out.append(
                {
                    "actor_id": npc_id,
                    "action_kind": move_kind,
                    "target_kind": target_type,
                    "target_id": target_id,
                    "dimension_scores": bundle["dimension_scores"],
                    "dimension_score_records": bundle["dimension_score_records"],
                    "replacement_authorised": bundle["replacement_authorised"],
                    "blocker_codes": bundle["blocker_codes"],
                    "goal_priority": 10.0 if agenda.get("goal_kind") in world_moves.MOVE_GOAL_ALIGN.get(move_kind, ()) else 3.0,
                    "pressure_intensity": float(inputs.get("highest_pressure_intensity") or 0.0),
                    "stress": float(inputs.get("stress_level") or 0.0),
                    "relationship_importance": float(inputs.get("relationship_importance") or 5.0),
                    "resource_scarcity": float(inputs.get("resource_scarcity") or 0.0),
                    "trauma_intensity": _max_trauma(inputs.get("memory_signatures") or ()),
                    "starving": bool(inputs.get("starving")),
                    "personality_order": _personality_order(run_seed, npc_id),
                    "provisional_tier": tier,
                }
            )
    return out


def _utility_inputs_for_actor(snapshot: FoundationTurnSnapshot, actor_id: str) -> Dict[str, Any]:
    for ref in snapshot.utility_input_refs:
        if ref.get("actor_id") == actor_id:
            return dict(ref)
    return {}


def _max_trauma(signatures: Sequence[Mapping[str, Any]]) -> float:
    peak = 0.0
    for sig in signatures:
        if isinstance(sig, dict) and sig.get("negative"):
            peak = max(peak, float(sig.get("trauma_intensity", 0.0)))
    return peak


def _personality_order(run_seed: str, actor_id: str) -> List[str]:
    from run_identity import select_from_namespace

    import npc_world_moves as world_moves

    options = tuple(sorted(list(world_moves.MOVE_KINDS)))
    primary = select_from_namespace(run_seed, f"personality:{actor_id}", options)
    rest = [opt for opt in options if opt != primary]
    return [primary, *rest]