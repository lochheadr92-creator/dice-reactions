"""
Independent Utility AI canon oracle — does NOT import production scoring functions.

Duplicates Ch 27.4–27.5 formulas for acceptance verification only.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# Canon constants — Source_of_Truth_v1.2.md Appendix A.4 / Ch 27.4.2
BASE_WEIGHTS = {
    "survival": 100.0,
    "goal_progression": 50.0,
    "pressure_relief": 30.0,
    "stress_reduction": 20.0,
    "relationship_impact": 40.0,
    "resource_gain_loss": 25.0,
    "memory_avoidance": 15.0,
}
WHIM_LOW = -0.5
WHIM_HIGH = 0.5
TIE_WINDOW = 0.01
DIMENSION_ORDER = tuple(sorted(BASE_WEIGHTS.keys()))

MOVE_SURVIVAL_DELTAS = {
    "gather": {"food": 0.6, "water": 0.1, "shelter": 0.0, "safety": 0.1},
    "protect": {"food": 0.0, "water": 0.0, "shelter": 0.0, "safety": 0.7},
    "fortify": {"food": 0.0, "water": 0.0, "shelter": 0.3, "safety": 0.8},
    "withdraw": {"food": 0.0, "water": 0.0, "shelter": 0.0, "safety": 0.9},
}
MOVE_PRESSURE_REDUCTION = {"gather": 0.6, "protect": 0.3, "fortify": 0.5, "withdraw": 0.2}
MOVE_STRESS_REDUCTION = {"withdraw": 0.35, "negotiate": 0.15, "protect": 0.1}
MOVE_RESOURCE_SVU = {"gather": 0.5, "negotiate": 0.2}


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def oracle_survival(action_kind: str) -> Optional[float]:
    d = MOVE_SURVIVAL_DELTAS.get(action_kind)
    if not d:
        return None
    return _clamp(sum(d[k] * 25.0 for k in ("food", "water", "shelter", "safety")))


def oracle_goal(action_kind: str, goal_kind: str, aligned: Sequence[str]) -> float:
    movement = 1.0 if goal_kind in aligned else 0.0
    priority = 10 if movement else 3
    return _clamp((priority * movement / 10.0) * 100.0)


def oracle_pressure(action_kind: str, highest: float) -> float:
    return _clamp(MOVE_PRESSURE_REDUCTION.get(action_kind, 0.0) * highest * 100.0)


def oracle_stress(action_kind: str, stress_level: float) -> Optional[float]:
    red = MOVE_STRESS_REDUCTION.get(action_kind, 0.0)
    if red <= 0:
        return None
    return _clamp(red * stress_level)


def oracle_relationship(delta_sum: int, importance: float) -> float:
    return _clamp(50.0 + delta_sum * (importance / 10.0))


def oracle_resource(action_kind: str, scarcity: float) -> Optional[float]:
    svu = MOVE_RESOURCE_SVU.get(action_kind)
    if svu is None:
        return None
    return _clamp(50.0 + float(svu) * (1.0 + scarcity) * 50.0)


def oracle_memory_avoidance(negative_match: bool) -> float:
    return 15.0 if negative_match else 90.0


def oracle_dimension_map(fixture: Mapping[str, Any]) -> Dict[str, float]:
    action = str(fixture["action_kind"])
    scores: Dict[str, float] = {}
    surv = oracle_survival(action)
    if surv is not None:
        scores["survival"] = surv
    scores["goal_progression"] = oracle_goal(
        action, str(fixture.get("goal_kind", "")), fixture.get("aligned_goals", ())
    )
    if fixture.get("highest_pressure_intensity") is not None:
        scores["pressure_relief"] = oracle_pressure(action, float(fixture["highest_pressure_intensity"]))
    if fixture.get("stress_level") is not None:
        st = oracle_stress(action, float(fixture["stress_level"]))
        if st is not None:
            scores["stress_reduction"] = st
    if fixture.get("relationship_delta_sum") is not None:
        scores["relationship_impact"] = oracle_relationship(
            int(fixture["relationship_delta_sum"]),
            float(fixture.get("relationship_importance", 5.0)),
        )
    if fixture.get("resource_scarcity") is not None and action in MOVE_RESOURCE_SVU:
        res = oracle_resource(action, float(fixture["resource_scarcity"]))
        if res is not None:
            scores["resource_gain_loss"] = res
    scores["memory_avoidance"] = oracle_memory_avoidance(bool(fixture.get("negative_memory_match")))
    return scores


def oracle_weights(fixture: Mapping[str, Any]) -> Dict[str, float]:
    w = dict(BASE_WEIGHTS)
    hp = float(fixture.get("highest_pressure_intensity") or 0.0)
    if fixture.get("starving"):
        w["survival"] = 200.0
    else:
        w["survival"] *= 1.0 + hp
    gp = float(fixture.get("goal_priority") or 5.0)
    w["goal_progression"] *= max(0.1, gp / 10.0)
    w["pressure_relief"] *= 1.0 + hp
    stress = float(fixture.get("stress_level") or 0.0)
    w["stress_reduction"] *= stress / 100.0
    w["relationship_impact"] *= max(0.1, float(fixture.get("relationship_importance", 5.0)) / 5.0)
    scarcity = float(fixture.get("resource_scarcity") or 0.0)
    w["resource_gain_loss"] *= 1.0 + scarcity
    trauma = float(fixture.get("trauma_intensity") or 0.0)
    if trauma > 0:
        w["memory_avoidance"] *= 1.0 + min(2.0, trauma)
    return w


def oracle_aggregate(scores: Mapping[str, float], weights: Mapping[str, float]) -> float:
    total_w = 0.0
    total = 0.0
    for name in DIMENSION_ORDER:
        if name not in scores:
            continue
        wt = weights.get(name, 0.0)
        total += scores[name] * wt
        total_w += wt
    if total_w <= 0:
        raise ValueError("no applicable dimensions")
    return _clamp(total / total_w)


def _seed_material(run_seed: str, turn: int, actor_id: str, c_hash: str) -> str:
    return (
        f"run_seed={run_seed}|turn={turn}|subsystem=utility_ai|actor_id={actor_id}"
        f"|candidate_set={c_hash}|rng_v=1|seed_schema_v=1"
    )


def _rng_unit(material: str, draw_index: int) -> float:
    digest = hashlib.sha256(f"{material}|draw={draw_index}".encode()).hexdigest()
    return int(digest[:13], 16) / float(2**52)


def oracle_noise(utility: float, material: str, draw_index: int) -> float:
    unit = _rng_unit(material, draw_index)
    return utility + (WHIM_LOW + unit * (WHIM_HIGH - WHIM_LOW))


def oracle_select(
    candidates: Sequence[Mapping[str, Any]],
    *,
    run_seed: str,
    turn_sequence: int,
    draw_start: int = 0,
) -> Dict[str, Any]:
    evaluated = []
    for raw in candidates:
        fixture = dict(raw)
        scores = oracle_dimension_map(fixture)
        weights = oracle_weights(fixture)
        base = oracle_aggregate(scores, weights)
        c_hash = hashlib.sha256(
            f"{raw.get('actor_id')}:{raw.get('action_kind')}:{raw.get('target_id')}".encode()
        ).hexdigest()[:16]
        material = _seed_material(run_seed, turn_sequence, str(raw.get("actor_id")), c_hash)
        noisy = oracle_noise(base, material, draw_start)
        evaluated.append({**raw, "base_utility": base, "noisy_utility": noisy, "dimension_scores": scores})
    if not evaluated:
        return {"selected": None}
    max_u = max(r["noisy_utility"] for r in evaluated)
    tied = [r for r in evaluated if abs(r["noisy_utility"] - max_u) <= TIE_WINDOW]
    tied.sort(
        key=lambda r: (
            list(r.get("personality_order") or []).index(r["action_kind"])
            if r["action_kind"] in (r.get("personality_order") or [])
            else 99,
            r.get("actor_id"),
            r.get("action_kind"),
            r.get("target_kind"),
            r.get("target_id"),
        )
    )
    winner = tied[0]
    return {
        "selected": {
            "actor_id": winner["actor_id"],
            "action_kind": winner["action_kind"],
            "target_kind": winner["target_kind"],
            "target_id": winner["target_id"],
            "base_utility": winner["base_utility"],
            "noisy_utility": winner["noisy_utility"],
        },
        "dimension_scores": winner["dimension_scores"],
        "tie_set_size": len(tied),
    }


def inputs_complete(fixture: Mapping[str, Any]) -> bool:
    required = ("action_kind", "goal_kind", "highest_pressure_intensity")
    for key in required:
        if key not in fixture or fixture[key] is None:
            return False
    action = str(fixture["action_kind"])
    if action in MOVE_STRESS_REDUCTION and fixture.get("stress_level") is None:
        return False
    if action in MOVE_RESOURCE_SVU and fixture.get("resource_scarcity") is None:
        return False
    return True