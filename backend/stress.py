"""
Chapter 14 — Stress substrate (P1: individual stress state).

Authoritative, persisted per-actor ``stress_level`` (0–100). This module owns
the *production* side of the value Ch 27 Utility AI consumes
(utility_dimensions.score_stress_reduction). It is a pure, deterministic
generation → capacity → accumulation → decay model.

Canon: Source_of_Truth_v1.2.md Chapter 14 is non-numerical ("Thresholds are
behavioural, not numerical"). Every numeric constant here is therefore a
DESIGNED EXTENSION, logged in docs/foundation-canon-deltas.md, not a canon
transcription. The only stress number in canon is the Ch 27.4.2 weight (20),
which lives in utility_ai.BASE_WEIGHTS, not here.

Determinism (invariant): the update is a pure function of prior persisted state
+ the run seed. No wall-clock, no PID, no unordered iteration. Per-actor
capacity is a seeded derivation via engine_determinism (no new RNG source).
"""

from __future__ import annotations

import copy
import math
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional

from engine_determinism import (
    build_seed_material,
    derive_rng_range,
    reject_non_finite,
)

STRESS_SCHEMA_VERSION = 1

# --- Designed-extension constants (canon is non-numerical) -------------------
# Ratified 2026-06-22 from ADR-021 "Proposed constants" table. Turn-based units.
STRESS_MIN: float = 0.0                     # Ch 27.7 range floor
STRESS_MAX: float = 100.0                   # Ch 27.7 range ceiling

# Baseline per-turn dissipation applied to carried stress EVERY update (half-life
# ≈ 4.3 turns). Decay is NOT conditional on safety — continuing pressure generation
# can outweigh it; recovery (14.34) is just the case where generation is low.
STRESS_DECAY_PER_TURN: float = 0.85

# Per-actor capacity band. Higher capacity = more resilient (14.5); it divides
# incoming generation. DESIGNED PROXY: seeded per actor, stable across the run, but
# NOT derived from authoritative personality traits — replace when those exist.
STRESS_CAPACITY_MIN: float = 0.7
STRESS_CAPACITY_MAX: float = 1.3
STRESS_CAPACITY_NOMINAL: float = 1.0

# Generation scale: g_t = SCALE · highest_pressure_intensity · threat_weight / C
# (14.4 pressure → interpretation → stress). highest_pressure_intensity is the
# snapshot-canonical 0–1 value; SCALE lifts it onto the 0–100 stress axis.
STRESS_GENERATION_SCALE: float = 100.0

# Acute-threat modifier: an actor whose agenda carries a fear interprets the same
# pressure as more threatening (14.4 interpretation step). Designed bump.
STRESS_THREAT_WEIGHT_BASE: float = 1.0
STRESS_THREAT_WEIGHT_FEAR_BONUS: float = 0.25


# --- P2 designed extensions: behavioural bands + goal narrowing ------------
# Chapter 14 is qualitative and supplies no numerical cut-points or modifiers.
# Every value below is therefore a DESIGNED_EXTENSION recorded in ADR-022 and
# docs/foundation-canon-deltas.md. Bands are derived on read; they are never
# persisted or accepted from model output.
class StressBand(str, Enum):
    CALM = "CALM"
    ELEVATED = "ELEVATED"
    STRAINED = "STRAINED"
    OVERLOADED = "OVERLOADED"


# Evaluated high-to-low. Lower bounds are inclusive; upper bounds are exclusive,
# except OVERLOADED includes the canonical maximum of 100.
STRESS_BAND_THRESHOLDS = (
    (75.0, StressBand.OVERLOADED),
    (50.0, StressBand.STRAINED),
    (25.0, StressBand.ELEVATED),
    (0.0, StressBand.CALM),
)

# Multipliers apply exactly once on top of the canonical Ch 27 dynamic weights.
# stress_reduction intentionally remains 1.0 because Ch 27 already scales it by
# stress/100; changing it here would double-count authoritative stress.
STRESS_WEIGHT_MODIFIERS: Dict[StressBand, Dict[str, float]] = {
    StressBand.CALM: {
        "survival": 1.0,
        "goal_progression": 1.0,
        "pressure_relief": 1.0,
        "stress_reduction": 1.0,
        "relationship_impact": 1.0,
        "resource_gain_loss": 1.0,
        "memory_avoidance": 1.0,
    },
    StressBand.ELEVATED: {
        "survival": 1.10,
        "goal_progression": 0.85,
        "pressure_relief": 1.10,
        "stress_reduction": 1.0,
        "relationship_impact": 0.95,
        "resource_gain_loss": 1.0,
        "memory_avoidance": 1.0,
    },
    StressBand.STRAINED: {
        "survival": 1.25,
        "goal_progression": 0.60,
        "pressure_relief": 1.30,
        "stress_reduction": 1.0,
        "relationship_impact": 0.80,
        "resource_gain_loss": 0.85,
        "memory_avoidance": 1.10,
    },
    StressBand.OVERLOADED: {
        "survival": 1.60,
        "goal_progression": 0.30,
        "pressure_relief": 1.50,
        "stress_reduction": 1.0,
        "relationship_impact": 0.50,
        "resource_gain_loss": 0.60,
        "memory_avoidance": 1.25,
    },
}

MISSING_STRESS_LEVEL = "MISSING_STRESS_LEVEL"
INVALID_STRESS_LEVEL = "INVALID_STRESS_LEVEL"
NONFINITE_STRESS_LEVEL = "NONFINITE_STRESS_LEVEL"
OUT_OF_RANGE_STRESS_LEVEL = "OUT_OF_RANGE_STRESS_LEVEL"

# Subsystem labels for seed material (kept stable — changing them re-seeds runs).
_CAPACITY_SUBSYSTEM = "stress_capacity"
_CAPACITY_TURN_SEQUENCE = 0  # fixed: capacity is a run-stable trait, not per-turn


def clamp_stress(value: float) -> float:
    """Clamp to the canonical 0–100 stress axis; reject non-finite first."""
    reject_non_finite(value)
    return max(STRESS_MIN, min(STRESS_MAX, value))


def _invalid_behaviour(blocker_code: str) -> Dict[str, Any]:
    """Fail-closed result: no band, identity (×1.0) modifiers, explicit blocker.

    Identity modifiers are returned so a caller that blindly multiplies weights
    leaves them unchanged — but ``valid`` is False and ``band`` is None, so an
    invalid input can never be mistaken for CALM nor authorise a replacement.
    """
    return {
        "valid": False,
        "stress_level": None,
        "band": None,
        "modifiers": dict(STRESS_WEIGHT_MODIFIERS[StressBand.CALM]),
        "blocker_code": blocker_code,
    }


def evaluate_stress_behaviour(stress_level: Any) -> Dict[str, Any]:
    """Fail-closed P2 behavioural profile derived from authoritative stress.

    Invalid inputs are deliberately NOT clamped into a valid band. They receive
    no band, identity modifiers, and an explicit blocker so Utility AI cannot
    mistake corrupt state for CALM or award an OVERLOADED bonus. Distinct blocker
    codes separate missing / invalid-type / non-finite / out-of-range causes.
    """
    if stress_level is None:
        return _invalid_behaviour(MISSING_STRESS_LEVEL)
    # bool is an int subclass and numeric strings coerce via float(); both are
    # rejected as invalid-type rather than silently classified, so only genuine
    # numeric authoritative state can produce a band.
    if isinstance(stress_level, bool) or not isinstance(stress_level, (int, float)):
        return _invalid_behaviour(INVALID_STRESS_LEVEL)
    try:
        level = float(stress_level)
    except (TypeError, ValueError, OverflowError):
        return _invalid_behaviour(INVALID_STRESS_LEVEL)
    if not math.isfinite(level):
        return _invalid_behaviour(NONFINITE_STRESS_LEVEL)
    if level < STRESS_MIN or level > STRESS_MAX:
        return _invalid_behaviour(OUT_OF_RANGE_STRESS_LEVEL)
    for threshold, band in STRESS_BAND_THRESHOLDS:
        if level >= threshold:
            return {
                "valid": True,
                "stress_level": level,
                "band": band.value,
                "modifiers": dict(STRESS_WEIGHT_MODIFIERS[band]),
                "blocker_code": None,
            }
    raise AssertionError("canonical stress range was not classified")


def capacity_for(run_seed: str, actor_id: str) -> float:
    """
    Per-actor stress capacity C ∈ [STRESS_CAPACITY_MIN, STRESS_CAPACITY_MAX].

    Deterministic seeded derivation (no new randomness source): identical
    (run_seed, actor_id) → identical C for the life of the run.
    """
    if not actor_id:
        return STRESS_CAPACITY_NOMINAL
    material = build_seed_material(
        run_seed=str(run_seed),
        turn_sequence=_CAPACITY_TURN_SEQUENCE,
        subsystem=_CAPACITY_SUBSYSTEM,
        actor_id=str(actor_id),
    )
    return derive_rng_range(material, 0, STRESS_CAPACITY_MIN, STRESS_CAPACITY_MAX)


def threat_weight(*, fear_present: bool) -> float:
    """Interpretation modifier (14.4): an agenda fear raises perceived threat.

    DELTA D_STRESS_FEAR_INTERPRETATION: this is currently a GENERAL multiplier — any
    agenda fear magnifies ALL applicable pressure, regardless of whether the fear is
    semantically related to that pressure. Pressure-to-fear relevance matching is
    deferred; until then an unrelated fear can amplify an unrelated pressure.
    """
    return STRESS_THREAT_WEIGHT_BASE + (STRESS_THREAT_WEIGHT_FEAR_BONUS if fear_present else 0.0)


def generate(
    highest_pressure_intensity: Optional[float],
    capacity: float,
    *,
    fear_present: bool = False,
) -> float:
    """
    Per-turn stress generation g_t = SCALE · pressure · threat_weight / C (14.4).

    No active pressure → no generation. Capacity divides incoming load.
    """
    if highest_pressure_intensity is None:
        return 0.0
    p = float(highest_pressure_intensity)
    reject_non_finite(p)
    if p <= 0.0:
        return 0.0
    c = float(capacity) if capacity and capacity > 0.0 else STRESS_CAPACITY_NOMINAL
    g = STRESS_GENERATION_SCALE * p * threat_weight(fear_present=fear_present) / c
    reject_non_finite(g)
    return max(0.0, g)


def accumulate(prev_stress: float, generated: float, *, decay: float = STRESS_DECAY_PER_TURN) -> float:
    """
    stress_t = clamp( stress_{t-1} · decay + g_t ), accumulation+decay (14.6/14.34).

    Carried stress decays multiplicatively each turn; this turn's generation is
    added on top. Bounded to the canonical 0–100 axis.
    """
    prev = float(prev_stress)
    reject_non_finite(prev)
    reject_non_finite(float(generated))
    return clamp_stress(prev * float(decay) + float(generated))


def _fear_present(agenda: Mapping[str, Any]) -> bool:
    return bool(str((agenda or {}).get("fear_kind") or "").strip())


def update_actor_stress(
    rolling_state: Dict[str, Any],
    pressure_state: Optional[Mapping[str, Any]],
    *,
    run_seed: str,
    turn_sequence: int,
    agendas_by_actor: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Deterministic per-turn stress update for every authoritative actor.

    Mutates ``rolling_state['actor_stress']`` in place and returns it. Keyed by
    the SAME actor_id the foundation snapshot registry uses, so
    foundation_snapshot._utility_input_refs can read it back directly.

    Pure w.r.t. (prior actor_stress, pressure_state, run_seed, actor set): no
    wall-clock, no unordered iteration (actors processed in sorted id order).

    SCOPE (P1 policy): only actors in the authoritative interpretation set this turn
    update — i.e. ALIVE actors the engine is actually simulating (those carrying an
    active agenda). Actors OUTSIDE that set retain their existing stress unchanged
    (no decay, no generation) — this avoids free global recovery without inventing
    tier cadence prematurely. Full tier-based recovery / offscreen decay (Ch 27.6)
    is deferred to before P2. See docs/foundation-canon-deltas.md.
    """
    if not isinstance(rolling_state, dict):
        return {}

    # Local import avoids a module-load cycle (foundation_snapshot is heavy).
    from foundation_snapshot import build_actor_registry, highest_pressure_intensity

    registry = build_actor_registry(rolling_state)
    pressure = highest_pressure_intensity(dict(pressure_state or {}))

    prior = rolling_state.get("actor_stress")
    prior = prior if isinstance(prior, dict) else {}
    agendas = dict(agendas_by_actor or {})

    # In-scope = the authoritative interpretation set this turn: ALIVE actors the
    # engine is actually simulating (those carrying an active agenda). Only these
    # accumulate/decay; everyone else is retained verbatim below.
    in_scope = {
        str(actor.get("actor_id") or "")
        for actor in registry
        if str(actor.get("actor_id") or "")
        and actor.get("life_status") != "deceased"
        and str(actor.get("actor_id") or "") in agendas
    }

    # Carry every prior entry forward unchanged (offscreen retention), then update
    # only in-scope actors in deterministic id order.
    updated: Dict[str, Dict[str, Any]] = {
        str(sid): dict(row) for sid, row in prior.items() if isinstance(row, dict)
    }
    for actor_id in sorted(in_scope):
        prev_row = prior.get(actor_id) if isinstance(prior.get(actor_id), dict) else {}
        prev_stress = float(prev_row.get("stress_level") or 0.0)
        capacity = capacity_for(run_seed, actor_id)
        gen = generate(
            pressure,
            capacity,
            fear_present=_fear_present(agendas.get(actor_id, {})),
        )
        updated[actor_id] = {
            "schema_version": STRESS_SCHEMA_VERSION,
            "stress_level": accumulate(prev_stress, gen),
            "capacity": capacity,
        }

    rolling_state["actor_stress"] = updated
    return updated


def enforce_authoritative_stress(
    merged_rolling: Dict[str, Any],
    authoritative: Optional[Mapping[str, Any]],
) -> List[str]:
    """
    Restore engine-owned actor_stress after consolidation (mirror of
    secrets.enforce_authoritative_registry). The LLM never owns this field; any
    model-emitted value is stripped and replaced with the engine's.
    """
    if not isinstance(merged_rolling, dict):
        return []
    auth = copy.deepcopy(dict(authoritative)) if isinstance(authoritative, dict) else {}
    if merged_rolling.get("actor_stress") != auth:
        merged_rolling["actor_stress"] = auth
        return ["actor_stress_model_mutation_stripped"]
    return []
