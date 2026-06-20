"""
Canonical Utility AI dimension scoring — Ch 27.4.1 formulas only.

Reads immutable snapshot utility inputs. No heuristics, no silent fallbacks.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from engine_determinism import reject_non_finite
from foundation_snapshot import FoundationTurnSnapshot

UTILITY_DIMENSIONS_SCHEMA_VERSION = 1

# Ch 27.4.1 survival deltas per move_kind — engine-owned structured catalog.
MOVE_SURVIVAL_DELTAS: Dict[str, Dict[str, float]] = {
    "gather": {"food": 0.6, "water": 0.1, "shelter": 0.0, "safety": 0.1},
    "protect": {"food": 0.0, "water": 0.0, "shelter": 0.0, "safety": 0.7},
    "investigate": {"food": 0.0, "water": 0.0, "shelter": 0.0, "safety": -0.2},
    "negotiate": {"food": 0.0, "water": 0.0, "shelter": 0.0, "safety": 0.1},
    "pressure": {"food": 0.0, "water": 0.0, "shelter": 0.0, "safety": -0.3},
    "conceal": {"food": 0.0, "water": 0.0, "shelter": 0.0, "safety": 0.2},
    "fortify": {"food": 0.0, "water": 0.0, "shelter": 0.3, "safety": 0.8},
    "withdraw": {"food": 0.0, "water": 0.0, "shelter": 0.0, "safety": 0.9},
    "defect": {"food": 0.0, "water": 0.0, "shelter": 0.0, "safety": -0.4},
}

MOVE_PRESSURE_REDUCTION: Dict[str, float] = {
    "gather": 0.6,
    "protect": 0.3,
    "negotiate": 0.4,
    "fortify": 0.5,
    "withdraw": 0.2,
    "investigate": 0.1,
    "pressure": 0.0,
    "conceal": 0.0,
    "defect": 0.0,
}

MOVE_STRESS_REDUCTION: Dict[str, float] = {
    "withdraw": 0.35,
    "negotiate": 0.15,
    "protect": 0.1,
    "gather": 0.05,
}

MOVE_RESOURCE_SVU_DELTA: Dict[str, Optional[float]] = {
    "gather": 0.5,
    "negotiate": 0.2,
    "defect": -0.3,
}

GOAL_PRIORITY_LIFE = 10
GOAL_PRIORITY_OPERATIONAL = 3

AUTHORISING_STATUSES = frozenset(
    {"exact_canon", "exact_canon_derived", "not_applicable"}
)


class UtilityDimension(str, enum.Enum):
    SURVIVAL = "survival"
    GOAL_PROGRESSION = "goal_progression"
    PRESSURE_RELIEF = "pressure_relief"
    STRESS_REDUCTION = "stress_reduction"
    RELATIONSHIP_IMPACT = "relationship_impact"
    RESOURCE_GAIN_LOSS = "resource_gain_loss"
    MEMORY_AVOIDANCE = "memory_avoidance"


class DimensionSourceStatus(str, enum.Enum):
    EXACT_CANON = "exact_canon"
    EXACT_CANON_DERIVED = "exact_canon_derived"
    NOT_APPLICABLE = "not_applicable"
    MISSING_AUTHORITATIVE_INPUT = "missing_authoritative_input"
    PLACEHOLDER_HEURISTIC = "placeholder_heuristic"
    PROHIBITED_SOURCE = "prohibited_source"


@dataclass(frozen=True)
class DimensionScore:
    dimension: UtilityDimension
    value: Optional[float]
    source_status: DimensionSourceStatus
    source_ids: Tuple[str, ...]
    canon_rule_id: str
    blocker_code: Optional[str] = None

    def authorising(self) -> bool:
        return self.source_status.value in AUTHORISING_STATUSES


def clamp_score(value: float) -> float:
    reject_non_finite(value)
    return max(0.0, min(100.0, value))


def score_survival(action_kind: str) -> DimensionScore:
    """Ch 27.4.1 — Survival_score = Σ(Δ×25) clamped 0–100."""
    deltas = MOVE_SURVIVAL_DELTAS.get(action_kind)
    if deltas is None:
        return DimensionScore(
            dimension=UtilityDimension.SURVIVAL,
            value=None,
            source_status=DimensionSourceStatus.MISSING_AUTHORITATIVE_INPUT,
            source_ids=("move_catalog",),
            canon_rule_id="27.4.1.survival",
            blocker_code="UNKNOWN_MOVE_KIND",
        )
    raw = sum(deltas[k] * 25.0 for k in ("food", "water", "shelter", "safety"))
    return DimensionScore(
        dimension=UtilityDimension.SURVIVAL,
        value=clamp_score(raw),
        source_status=DimensionSourceStatus.EXACT_CANON_DERIVED,
        source_ids=(f"move:{action_kind}",),
        canon_rule_id="27.4.1.survival",
    )


def score_goal_progression(
    action_kind: str,
    *,
    goal_kind: str,
    aligned_goals: frozenset[str],
) -> DimensionScore:
    """Ch 27.4.1 — weighted goals normalised 0–100."""
    if not goal_kind:
        return DimensionScore(
            dimension=UtilityDimension.GOAL_PROGRESSION,
            value=None,
            source_status=DimensionSourceStatus.MISSING_AUTHORITATIVE_INPUT,
            source_ids=(),
            canon_rule_id="27.4.1.goal_progression",
            blocker_code="MISSING_GOAL_KIND",
        )
    movement = 1.0 if goal_kind in aligned_goals else 0.0
    priority = GOAL_PRIORITY_LIFE if movement else GOAL_PRIORITY_OPERATIONAL
    value = clamp_score((priority * movement / GOAL_PRIORITY_LIFE) * 100.0)
    return DimensionScore(
        dimension=UtilityDimension.GOAL_PROGRESSION,
        value=value,
        source_status=DimensionSourceStatus.EXACT_CANON_DERIVED,
        source_ids=(f"agenda:goal:{goal_kind}", f"move:{action_kind}"),
        canon_rule_id="27.4.1.goal_progression",
    )


def score_pressure_relief(
    action_kind: str,
    *,
    highest_pressure_intensity: Optional[float],
) -> DimensionScore:
    """Ch 27.4.1 — reduction × 100."""
    if highest_pressure_intensity is None:
        return DimensionScore(
            dimension=UtilityDimension.PRESSURE_RELIEF,
            value=None,
            source_status=DimensionSourceStatus.NOT_APPLICABLE,
            source_ids=(),
            canon_rule_id="27.4.1.pressure_relief",
        )
    reduction = MOVE_PRESSURE_REDUCTION.get(action_kind, 0.0) * float(highest_pressure_intensity)
    return DimensionScore(
        dimension=UtilityDimension.PRESSURE_RELIEF,
        value=clamp_score(reduction * 100.0),
        source_status=DimensionSourceStatus.EXACT_CANON_DERIVED,
        source_ids=("pressure_graph", f"move:{action_kind}"),
        canon_rule_id="27.4.1.pressure_relief",
    )


def score_stress_reduction(
    action_kind: str,
    *,
    stress_level: Optional[float],
) -> DimensionScore:
    reduction_factor = MOVE_STRESS_REDUCTION.get(action_kind, 0.0)
    if reduction_factor <= 0.0:
        return DimensionScore(
            dimension=UtilityDimension.STRESS_REDUCTION,
            value=None,
            source_status=DimensionSourceStatus.NOT_APPLICABLE,
            source_ids=(f"move:{action_kind}",),
            canon_rule_id="27.4.1.stress_reduction",
        )
    if stress_level is None:
        return DimensionScore(
            dimension=UtilityDimension.STRESS_REDUCTION,
            value=None,
            source_status=DimensionSourceStatus.MISSING_AUTHORITATIVE_INPUT,
            source_ids=(f"move:{action_kind}",),
            canon_rule_id="27.4.1.stress_reduction",
            blocker_code="MISSING_STRESS_LEVEL",
        )
    value = clamp_score(reduction_factor * float(stress_level))
    return DimensionScore(
        dimension=UtilityDimension.STRESS_REDUCTION,
        value=value,
        source_status=DimensionSourceStatus.EXACT_CANON,
        source_ids=(f"move:{action_kind}", "actor:stress_level"),
        canon_rule_id="27.4.1.stress_reduction",
    )


def score_relationship_impact(
    action_kind: str,
    target_kind: str,
    *,
    relationship_deltas: Mapping[str, int],
    relationship_importance: Optional[float],
) -> DimensionScore:
    if not relationship_deltas:
        return DimensionScore(
            dimension=UtilityDimension.RELATIONSHIP_IMPACT,
            value=None,
            source_status=DimensionSourceStatus.NOT_APPLICABLE,
            source_ids=(f"move:{action_kind}",),
            canon_rule_id="27.4.1.relationship_impact",
        )
    if relationship_importance is None:
        return DimensionScore(
            dimension=UtilityDimension.RELATIONSHIP_IMPACT,
            value=None,
            source_status=DimensionSourceStatus.MISSING_AUTHORITATIVE_INPUT,
            source_ids=("relationship_vectors",),
            canon_rule_id="27.4.1.relationship_impact",
            blocker_code="MISSING_RELATIONSHIP_IMPORTANCE",
        )
    raw_delta = sum(relationship_deltas.values())
    weighted = raw_delta * (float(relationship_importance) / 10.0)
    normalised = clamp_score(50.0 + weighted)
    return DimensionScore(
        dimension=UtilityDimension.RELATIONSHIP_IMPACT,
        value=normalised,
        source_status=DimensionSourceStatus.EXACT_CANON_DERIVED,
        source_ids=("relationship_effect_catalog", "relationship_vectors"),
        canon_rule_id="27.4.1.relationship_impact",
    )


def score_resource_gain_loss(
    action_kind: str,
    *,
    svu_delta: Optional[float],
    resource_scarcity: Optional[float],
) -> DimensionScore:
    delta = MOVE_RESOURCE_SVU_DELTA.get(action_kind)
    if delta is None:
        return DimensionScore(
            dimension=UtilityDimension.RESOURCE_GAIN_LOSS,
            value=None,
            source_status=DimensionSourceStatus.NOT_APPLICABLE,
            source_ids=(f"move:{action_kind}",),
            canon_rule_id="27.4.1.resource_gain_loss",
        )
    if resource_scarcity is None:
        return DimensionScore(
            dimension=UtilityDimension.RESOURCE_GAIN_LOSS,
            value=None,
            source_status=DimensionSourceStatus.MISSING_AUTHORITATIVE_INPUT,
            source_ids=("pressure_graph:resource",),
            canon_rule_id="27.4.1.resource_gain_loss",
            blocker_code="MISSING_RESOURCE_SCARCITY",
        )
    effective = float(delta) * (1.0 + float(resource_scarcity))
    value = clamp_score(50.0 + effective * 50.0)
    return DimensionScore(
        dimension=UtilityDimension.RESOURCE_GAIN_LOSS,
        value=value,
        source_status=DimensionSourceStatus.EXACT_CANON_DERIVED,
        source_ids=("svu_catalog", "pressure_graph:resource"),
        canon_rule_id="27.4.1.resource_gain_loss",
    )


def score_memory_avoidance(
    *,
    action_kind: str,
    target_kind: str,
    location_ref: str,
    memory_signatures: Sequence[Mapping[str, Any]],
) -> DimensionScore:
    if not memory_signatures:
        return DimensionScore(
            dimension=UtilityDimension.MEMORY_AVOIDANCE,
            value=50.0,
            source_status=DimensionSourceStatus.NOT_APPLICABLE,
            source_ids=(),
            canon_rule_id="27.4.1.memory_avoidance",
        )
    worst_match = 0.0
    for sig in memory_signatures:
        if not isinstance(sig, dict):
            continue
        if sig.get("negative") and _context_matches(sig, action_kind, target_kind, location_ref):
            worst_match = max(worst_match, float(sig.get("trauma_intensity", 1.0)))
    if worst_match <= 0.0:
        value = 90.0
    else:
        value = clamp_score(20.0 - worst_match * 5.0)
        value = max(0.0, min(20.0, value)) if worst_match >= 1.0 else 80.0
    return DimensionScore(
        dimension=UtilityDimension.MEMORY_AVOIDANCE,
        value=value,
        source_status=DimensionSourceStatus.EXACT_CANON_DERIVED,
        source_ids=tuple(f"memory:{i}" for i in range(len(memory_signatures))),
        canon_rule_id="27.4.1.memory_avoidance",
    )


def _context_matches(
    sig: Mapping[str, Any],
    action_kind: str,
    target_kind: str,
    location_ref: str,
) -> bool:
    loc = str(sig.get("location") or "")
    activity = str(sig.get("activity") or "")
    actor_type = str(sig.get("actor_type") or "")
    if loc and location_ref and loc == location_ref:
        return True
    if activity and activity == action_kind:
        return True
    if actor_type and actor_type == target_kind:
        return True
    return False


def compute_dimension_scores(
    snapshot: FoundationTurnSnapshot,
    *,
    actor_id: str,
    action_kind: str,
    target_kind: str,
    aligned_goals: frozenset[str],
    relationship_deltas: Mapping[str, int],
    actor_inputs: Optional[Mapping[str, Any]] = None,
) -> Tuple[DimensionScore, ...]:
    inputs = dict(actor_inputs or {})
    for ref in snapshot.utility_input_refs:
        if ref.get("actor_id") == actor_id:
            inputs = {**ref, **inputs}
            break
    goal_kind = str(inputs.get("goal_kind") or "")
    return (
        score_survival(action_kind),
        score_goal_progression(action_kind, goal_kind=goal_kind, aligned_goals=aligned_goals),
        score_pressure_relief(
            action_kind,
            highest_pressure_intensity=inputs.get("highest_pressure_intensity"),
        ),
        score_stress_reduction(action_kind, stress_level=inputs.get("stress_level")),
        score_relationship_impact(
            action_kind,
            target_kind,
            relationship_deltas=relationship_deltas,
            relationship_importance=inputs.get("relationship_importance"),
        ),
        score_resource_gain_loss(
            action_kind,
            svu_delta=MOVE_RESOURCE_SVU_DELTA.get(action_kind),
            resource_scarcity=inputs.get("resource_scarcity"),
        ),
        score_memory_avoidance(
            action_kind=action_kind,
            target_kind=target_kind,
            location_ref=snapshot.location_ref,
            memory_signatures=inputs.get("memory_signatures") or (),
        ),
    )


def dimension_scores_to_aggregate_map(
    scores: Sequence[DimensionScore],
) -> Tuple[Dict[str, float], bool, Tuple[str, ...]]:
    """
    Return numeric map for aggregation, replacement-authorised flag, blocker codes.
    Excludes non-authorising dimensions from aggregate; missing blocks replacement.
    """
    out: Dict[str, float] = {}
    blockers: list[str] = []
    authorised = True
    for row in scores:
        if row.source_status == DimensionSourceStatus.MISSING_AUTHORITATIVE_INPUT:
            authorised = False
            if row.blocker_code:
                blockers.append(row.blocker_code)
            continue
        if row.source_status == DimensionSourceStatus.PROHIBITED_SOURCE:
            authorised = False
            blockers.append("PROHIBITED_SOURCE")
            continue
        if row.source_status == DimensionSourceStatus.PLACEHOLDER_HEURISTIC:
            authorised = False
            blockers.append("PLACEHOLDER_HEURISTIC")
            continue
        if row.source_status == DimensionSourceStatus.NOT_APPLICABLE:
            continue
        if row.value is None:
            authorised = False
            blockers.append(f"NULL_VALUE:{row.dimension.value}")
            continue
        out[row.dimension.value] = row.value
    return out, authorised, tuple(sorted(set(blockers)))