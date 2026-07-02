"""
NPC Lifecycle core — Chapter 33 Phase 1 (Aging, Mortality, Death Events).

Pure, deterministic lifecycle layer. This module NEVER:
  • reads generated narrative / prose (H1: state is truth, prose is output),
  • calls the LLM, constructs prompts, or touches the frontend,
  • mutates authoritative rolling_state registries in place — it operates on
    lifecycle *records* and RETURNS updated records + structured events, so the
    structured clock seam applies them through approved engine paths.

Scope (Phase 1 only): canonical lifecycle state + migration, simulation-day
aging, Appendix A.7 life stages, deterministic natural mortality, an idempotent
death transition (natural AND unnatural) emitting structured events, and
Actor-Resolution-tier-aware processing contracts. Births, family formation,
inheritance, grudges, succession, and burn-in turnover are OUT OF SCOPE and
deferred to later Chapter 33 phases.

Canon note: Source_of_Truth_v1.2.md contains Chapter 33 and Appendix A.7
lifecycle constants. The numeric defaults below mirror that default-human
contract and stay centralized here rather than scattered. Life stage is
*derived* from simulation time and is never independently mutable by the model.

Time contract: lifecycle functions accept an EXPLICIT integer simulation day.
backend/simulation_clock.py supplies the structured clock seam. This module
never invents live turn duration and never advances lifecycle from ordinary
turns.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import ai_config
from engine_determinism import (
    build_seed_material,
    derive_rng_range,
    derive_rng_unit,
    reject_non_finite,
    stable_hash,
)

LIFECYCLE_SCHEMA_VERSION = 1

# Integer simulation-day → year conversion (designed extension; 365-day year).
DAYS_PER_SIMULATION_YEAR = 365

# ---------------------------------------------------------------------------
# Lifecycle profiles (configurable for non-human / setting-specific species).
# Appendix A.7 default-human boundaries (years): Child 0–15, Adult 16–49,
# Elder 50–69, Venerable 70+.  stage_bounds_years entries are (name, lo, hi)
# with lo inclusive and hi exclusive; hi=None means "and above".
# ---------------------------------------------------------------------------
DEFAULT_HUMAN_PROFILE: Dict[str, Any] = {
    "profile_id": "human",
    "stage_bounds_years": (
        ("child", 0, 16),
        ("adult", 16, 50),
        ("elder", 50, 70),
        ("venerable", 70, None),
    ),
    "mortality_min_age_years": 16,     # no natural mortality roll before this age
    "age_factor_ref_age_years": 50,    # age factor begins past this age
    "age_factor_doubling_years": 8,    # doubles ~every 8 years past the ref age
    "max_plausible_age_years": 130,    # migration sanity ceiling
    "migration_default_min_age_years": 18,
    "migration_default_max_age_years": 60,
}

LIFECYCLE_PROFILES: Dict[str, Dict[str, Any]] = {
    "human": DEFAULT_HUMAN_PROFILE,
}

# Natural mortality constants (designed extensions).
BASE_ADULT_MORTALITY_PER_YEAR = 0.005   # 0.5% per simulation year
HEALTH_FACTOR_MIN, HEALTH_FACTOR_MAX = 1.0, 5.0
PRESSURE_FACTOR_MIN, PRESSURE_FACTOR_MAX = 1.0, 2.0
LEGACY_DECEASED_REGISTRY_CAUSE = "preexisting_deceased_registry"

# Actor-Resolution tiers that receive lifecycle processing, and how.
_INDIVIDUAL_TIERS = ("hero", "active", "relevant")   # individual aging + mortality
_BATCH_TIERS = ("dormant",)                           # batch mortality API
_NO_PROCESS_TIERS = ("archived", "unknown")           # never aged / evaluated

_SUBSYSTEM_MORTALITY = "npc_lifecycle_mortality"
_SUBSYSTEM_MIGRATION = "npc_lifecycle_migration"


class NpcLifecycleError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Flag reader
# ---------------------------------------------------------------------------
def is_enabled() -> bool:
    """Live lifecycle application flag (default OFF). Pure functions ignore it."""
    return bool(getattr(ai_config, "ENABLE_NPC_LIFECYCLE", False))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def get_profile(profile_id: Optional[str]) -> Dict[str, Any]:
    return LIFECYCLE_PROFILES.get(str(profile_id or "human"), DEFAULT_HUMAN_PROFILE)


# ---------------------------------------------------------------------------
# Aging & life-stage derivation (from simulation time only)
# ---------------------------------------------------------------------------
def age_days(birth_simulation_day: int, current_simulation_day: int) -> int:
    """Non-negative elapsed simulation days. Never a turn-number proxy."""
    return max(0, int(current_simulation_day) - int(birth_simulation_day))


def age_years(birth_simulation_day: int, current_simulation_day: int) -> int:
    """Completed simulation years (floor)."""
    return age_days(birth_simulation_day, current_simulation_day) // DAYS_PER_SIMULATION_YEAR


def life_stage(
    birth_simulation_day: int,
    current_simulation_day: int,
    *,
    profile: Optional[Mapping[str, Any]] = None,
) -> str:
    """Derive life stage from age in completed years. Not model-mutable."""
    prof = dict(profile or DEFAULT_HUMAN_PROFILE)
    years = age_years(birth_simulation_day, current_simulation_day)
    for name, lo, hi in prof["stage_bounds_years"]:
        if years >= lo and (hi is None or years < hi):
            return name
    return prof["stage_bounds_years"][-1][0]


# ---------------------------------------------------------------------------
# Natural mortality (pure, deterministic, idempotent per evaluation period)
# ---------------------------------------------------------------------------
def mortality_evaluation_period(current_simulation_day: int) -> int:
    """The sim-year index used both as the per-period guard and the seed period."""
    return int(current_simulation_day) // DAYS_PER_SIMULATION_YEAR


def natural_mortality_probability(
    age_years_value: int,
    *,
    health_factor: float = 1.0,
    pressure_factor: float = 1.0,
    profile: Optional[Mapping[str, Any]] = None,
) -> float:
    """
    P(death) for one simulation year, bounded [0, 1].

        p = base * age_factor * health * pressure
        base       = 0.5% per year
        age_factor = 1 up to ref age (50); doubles ~every 8 years past it
        health     ∈ [1, 5]   pressure ∈ [1, 2]

    Returns 0.0 below the profile's minimum mortality age.
    """
    prof = dict(profile or DEFAULT_HUMAN_PROFILE)
    if age_years_value < prof["mortality_min_age_years"]:
        return 0.0
    reject_non_finite(float(health_factor))
    reject_non_finite(float(pressure_factor))
    ref = prof["age_factor_ref_age_years"]
    doubling = prof["age_factor_doubling_years"]
    if age_years_value <= ref:
        age_factor = 1.0
    else:
        age_factor = 2.0 ** ((age_years_value - ref) / float(doubling))
    health = _clamp(float(health_factor), HEALTH_FACTOR_MIN, HEALTH_FACTOR_MAX)
    pressure = _clamp(float(pressure_factor), PRESSURE_FACTOR_MIN, PRESSURE_FACTOR_MAX)
    p = BASE_ADULT_MORTALITY_PER_YEAR * age_factor * health * pressure
    reject_non_finite(p)
    return _clamp(p, 0.0, 1.0)


def evaluate_natural_mortality(
    record: Mapping[str, Any],
    *,
    current_simulation_day: int,
    run_seed: str,
    health_factor: float = 1.0,
    pressure_factor: float = 1.0,
    profile: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    One deterministic per-period mortality evaluation for a single record.

    Idempotent per evaluation period: an NPC already evaluated in the current
    sim-year is skipped (no reroll). Even without the guard the derived roll is
    a pure function of (run_seed, npc_id, period), so repeated execution can
    never reroll. Dead / archived / sub-age records are never evaluated. Never
    uses process-global RNG.
    """
    prof = dict(profile or DEFAULT_HUMAN_PROFILE)
    npc_id = str(record.get("npc_id") or "")
    period = mortality_evaluation_period(current_simulation_day)
    out: Dict[str, Any] = {
        "npc_id": npc_id,
        "period": period,
        "evaluated": False,
        "skip_reason": None,
        "probability": 0.0,
        "roll": None,
        "died": False,
    }

    if not record.get("alive", True):
        out["skip_reason"] = "not_alive"
        return out
    if str(record.get("life_stage") or "") == "archived":
        out["skip_reason"] = "archived"
        return out

    last_day = record.get("last_mortality_evaluation_day")
    if last_day is not None and mortality_evaluation_period(int(last_day)) == period:
        out["skip_reason"] = "already_evaluated_period"
        return out

    years = age_years(int(record.get("birth_simulation_day") or 0), current_simulation_day)
    if years < prof["mortality_min_age_years"]:
        out["skip_reason"] = "below_min_age"
        out["evaluated"] = True  # a real (zero-probability) evaluation happened
        return out

    probability = natural_mortality_probability(
        years, health_factor=health_factor, pressure_factor=pressure_factor, profile=prof
    )
    seed_material = build_seed_material(
        run_seed=str(run_seed),
        turn_sequence=period,
        subsystem=_SUBSYSTEM_MORTALITY,
        actor_id=npc_id,
        candidate_set_hash_value=stable_hash(
            "npc_lifecycle_mortality_inputs",
            {"age_years": years, "profile": prof["profile_id"]},
        ),
    )
    roll = derive_rng_unit(seed_material, 0)
    out.update(
        {
            "evaluated": True,
            "probability": probability,
            "roll": roll,
            "died": roll < probability,
            "seed_material": seed_material,
        }
    )
    return out


# ---------------------------------------------------------------------------
# Death transition (one authoritative, idempotent path for natural + unnatural)
# ---------------------------------------------------------------------------
def _record_snapshot(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "alive": bool(record.get("alive", True)),
        "life_stage": record.get("life_stage"),
        "death_simulation_day": record.get("death_simulation_day"),
        "death_cause": record.get("death_cause"),
    }


def _death_event(
    *,
    npc_id: str,
    simulation_day: int,
    cause: str,
    natural: bool,
    caused_by: Sequence[str],
    seed_provenance: Optional[str],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> Dict[str, Any]:
    event_id = "lifeevt-" + stable_hash(
        "npc_lifecycle_death",
        {"npc_id": npc_id, "day": int(simulation_day), "cause": str(cause)},
    )[:16]
    return {
        "schema_version": LIFECYCLE_SCHEMA_VERSION,
        "event_id": event_id,
        "event_type": "npc_death",
        "npc_id": npc_id,
        "simulation_day": int(simulation_day),
        "cause": str(cause),
        "classification": "natural" if natural else "unnatural",
        "caused_by": [str(c) for c in (caused_by or [])],
        "seed_provenance": seed_provenance,
        "before": dict(before),
        "after": dict(after),
    }


def apply_death(
    record: Mapping[str, Any],
    *,
    death_simulation_day: int,
    cause: str,
    natural: bool,
    caused_by: Sequence[str] = (),
    seed_provenance: Optional[str] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """
    The single authoritative death transition. Returns (updated_record, event).

    Idempotent: a record that is already dead is returned unchanged with event
    None (duplicate death refused). The NPC record is PRESERVED (never deleted)
    and projected to archived/historical (alive=False, life_stage='archived').
    Both natural and unnatural death pass through here. Death is never inferred
    from prose — the caller supplies the cause and classification explicitly.
    """
    updated = dict(record)
    if not record.get("alive", True):
        return updated, None  # already dead → refuse duplicate application

    before = _record_snapshot(record)
    updated["alive"] = False
    updated["death_simulation_day"] = int(death_simulation_day)
    updated["death_cause"] = str(cause)
    updated["prior_life_stage"] = record.get("life_stage")
    updated["life_stage"] = "archived"
    after = _record_snapshot(updated)

    event = _death_event(
        npc_id=str(record.get("npc_id") or ""),
        simulation_day=death_simulation_day,
        cause=cause,
        natural=natural,
        caused_by=caused_by,
        seed_provenance=seed_provenance,
        before=before,
        after=after,
    )
    return updated, event


def apply_unnatural_death(
    record: Mapping[str, Any],
    *,
    death_simulation_day: int,
    cause: str,
    caused_by: Sequence[str] = (),
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Explicit engine-sourced (non-prose) unnatural death via the same transition."""
    return apply_death(
        record,
        death_simulation_day=death_simulation_day,
        cause=cause,
        natural=False,
        caused_by=caused_by,
    )


# ---------------------------------------------------------------------------
# Migration / defaulting for existing NPC records
# ---------------------------------------------------------------------------
def _has_valid_lifecycle(npc: Mapping[str, Any]) -> bool:
    if not isinstance(npc, Mapping):
        return False
    birth = npc.get("birth_simulation_day")
    return isinstance(birth, int) and not isinstance(birth, bool)


def _valid_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def migrate_record(
    npc: Mapping[str, Any],
    *,
    current_simulation_day: int,
    run_seed: str,
    deceased_names: Optional[Sequence[str]] = None,
    profile_id: str = "human",
) -> Tuple[Dict[str, Any], bool]:
    """
    Produce a canonical lifecycle record for an NPC, migrating deterministically
    if lifecycle fields are absent. Returns (record, migrated).

    Guarantees: valid existing lifecycle state is never overwritten; ages are
    never negative; deceased NPCs are never resurrected; identical (npc, seed,
    day) yields an identical record.
    """
    prof = get_profile(profile_id)
    npc_id = str(npc.get("npc_id") or npc.get("name") or "")
    name_key = str(npc.get("name") or npc_id).strip().lower()
    deceased = {str(d).strip().lower() for d in (deceased_names or [])}
    is_dead = (npc.get("alive") is False) or (name_key in deceased)

    if _has_valid_lifecycle(npc):
        record = dict(npc)
        record.setdefault("npc_id", npc_id)
        record.setdefault("lifecycle_profile", profile_id)
        # Clamp an impossible negative age to a birth no later than 'now'.
        if int(record["birth_simulation_day"]) > int(current_simulation_day):
            record["birth_simulation_day"] = int(current_simulation_day)
        record.setdefault("alive", not is_dead)
        if is_dead:
            record["alive"] = False  # never resurrect
        record.setdefault("death_simulation_day", None)
        record.setdefault("death_cause", None)
        if not record.get("alive", True):
            if not _valid_int(record.get("death_simulation_day")):
                record["death_simulation_day"] = int(current_simulation_day)
            if not record.get("death_cause"):
                record["death_cause"] = LEGACY_DECEASED_REGISTRY_CAUSE
        record.setdefault("last_mortality_evaluation_day", None)
        record["life_stage"] = (
            "archived"
            if not record.get("alive", True)
            else life_stage(int(record["birth_simulation_day"]), current_simulation_day, profile=prof)
        )
        record["schema_version"] = LIFECYCLE_SCHEMA_VERSION
        record["migrated"] = False
        return record, False

    # Deterministic default birth: a stable adult age in the profile band.
    seed_material = build_seed_material(
        run_seed=str(run_seed),
        turn_sequence=0,
        subsystem=_SUBSYSTEM_MIGRATION,
        actor_id=npc_id,
    )
    lo = int(prof["migration_default_min_age_years"])
    hi = int(prof["migration_default_max_age_years"])
    assigned_age_years = int(derive_rng_range(seed_material, 0, float(lo), float(hi)))
    assigned_age_years = max(0, min(assigned_age_years, int(prof["max_plausible_age_years"])))
    birth_day = int(current_simulation_day) - assigned_age_years * DAYS_PER_SIMULATION_YEAR
    birth_day = min(birth_day, int(current_simulation_day))  # never negative age

    record = {
        "schema_version": LIFECYCLE_SCHEMA_VERSION,
        "npc_id": npc_id,
        "birth_simulation_day": birth_day,
        "lifecycle_profile": profile_id,
        "alive": not is_dead,
        "death_simulation_day": int(current_simulation_day) if is_dead else None,
        "death_cause": LEGACY_DECEASED_REGISTRY_CAUSE if is_dead else None,
        "last_mortality_evaluation_day": None,
        "migrated": True,
    }
    record["life_stage"] = (
        "archived" if is_dead else life_stage(birth_day, current_simulation_day, profile=prof)
    )
    return record, True


# ---------------------------------------------------------------------------
# Tier-aware processing (uses existing Actor Resolution tier output as input)
# ---------------------------------------------------------------------------
def process_individual(
    record: Mapping[str, Any],
    *,
    current_simulation_day: int,
    run_seed: str,
    health_factor: float = 1.0,
    pressure_factor: float = 1.0,
    profile: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Age one record and run one mortality evaluation. Returns
    (updated_record, death_event_or_None, mortality_diag). Archived/dead records
    are aged/evaluated no further.
    """
    prof = dict(profile or DEFAULT_HUMAN_PROFILE)
    updated = dict(record)
    if not record.get("alive", True) or str(record.get("life_stage") or "") == "archived":
        return updated, None, {"npc_id": str(record.get("npc_id") or ""), "skipped": True}

    # Aging: life_stage is derived from simulation time (never model-set).
    updated["life_stage"] = life_stage(
        int(record.get("birth_simulation_day") or 0), current_simulation_day, profile=prof
    )

    mortality = evaluate_natural_mortality(
        updated,
        current_simulation_day=current_simulation_day,
        run_seed=run_seed,
        health_factor=health_factor,
        pressure_factor=pressure_factor,
        profile=prof,
    )
    death_event = None
    if mortality.get("evaluated"):
        updated["last_mortality_evaluation_day"] = int(current_simulation_day)
    if mortality.get("died"):
        updated, death_event = apply_death(
            updated,
            death_simulation_day=current_simulation_day,
            cause="natural_causes",
            natural=True,
            seed_provenance=mortality.get("seed_material"),
        )
    return updated, death_event, mortality


def process_dormant_batch(
    records: Sequence[Mapping[str, Any]],
    *,
    current_simulation_day: int,
    run_seed: str,
    profile: Optional[Mapping[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Batch mortality API for Dormant-tier actors. Aggregate BIRTHS are NOT
    implemented in Phase 1, but every individual death produced here still emits
    a structured event (no silent deaths). Returns (updated_records, events, diag).
    """
    updated_records: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []
    evaluated = 0
    for rec in records or []:
        new_rec, death_event, mortality = process_individual(
            rec,
            current_simulation_day=current_simulation_day,
            run_seed=run_seed,
            profile=profile,
        )
        if mortality.get("evaluated"):
            evaluated += 1
        if death_event is not None:
            events.append(death_event)
        updated_records.append(new_rec)
    return updated_records, events, {"batch_evaluated": evaluated, "batch_deaths": len(events)}


def due_mortality_periods(processed_through_day: int, current_simulation_day: int) -> List[int]:
    """Sim-year periods strictly after the processed cursor, through the current day."""
    last = mortality_evaluation_period(int(processed_through_day))
    now = mortality_evaluation_period(int(current_simulation_day))
    return list(range(last + 1, now + 1)) if now > last else []


def process_due_periods(
    record: Mapping[str, Any],
    *,
    processed_through_day: int,
    current_simulation_day: int,
    run_seed: str,
    health_factor: float = 1.0,
    pressure_factor: float = 1.0,
    profile: Optional[Mapping[str, Any]] = None,
    max_periods: Optional[int] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], int, Optional[int]]:
    """
    Catch-up processing for one record over the DUE sim-year mortality periods.

    Ages the record to current_simulation_day and evaluates each due period
    exactly once (deterministic, idempotent per the Phase-1 contract), stopping
    at death. Bounded by max_periods; unprocessed periods are left for a later
    deterministic retry. Returns (updated_record, death_event_or_None,
    periods_evaluated, last_period_processed). Archived/dead records are never
    processed. Stage is derived from the final day (never one loop per day).
    """
    prof = dict(profile or DEFAULT_HUMAN_PROFILE)
    updated = dict(record)
    if not record.get("alive", True) or str(record.get("life_stage") or "") == "archived":
        return updated, None, 0, None

    periods = due_mortality_periods(processed_through_day, current_simulation_day)
    if max_periods is not None:
        periods = periods[: max(0, int(max_periods))]

    death_event: Optional[Dict[str, Any]] = None
    evaluated = 0
    last_period: Optional[int] = None
    for period in periods:
        period_day = period * DAYS_PER_SIMULATION_YEAR
        mortality = evaluate_natural_mortality(
            updated,
            current_simulation_day=period_day,
            run_seed=run_seed,
            health_factor=health_factor,
            pressure_factor=pressure_factor,
            profile=prof,
        )
        last_period = period
        if mortality.get("evaluated"):
            evaluated += 1
            updated["last_mortality_evaluation_day"] = period_day
        if mortality.get("died"):
            updated, death_event = apply_death(
                updated,
                death_simulation_day=period_day,
                cause="natural_causes",
                natural=True,
                seed_provenance=mortality.get("seed_material"),
            )
            break

    if updated.get("alive", True):
        updated["life_stage"] = life_stage(
            int(updated.get("birth_simulation_day") or 0), current_simulation_day, profile=prof
        )
    return updated, death_event, evaluated, last_period


def _empty_tick_diagnostics() -> Dict[str, Any]:
    return {
        "lifecycle_flag_enabled": is_enabled(),
        "lifecycle_applied": False,
        "current_simulation_day": None,
        "npcs_evaluated": 0,
        "migrations_performed": 0,
        "stage_transitions": [],
        "mortality_probabilities": {},
        "mortality_rolls": {},
        "deaths_applied": 0,
        "duplicate_events_rejected": 0,
        "emitted_event_ids": [],
        "error": None,
    }


def evaluate_lifecycle_tick(
    npcs: Sequence[Mapping[str, Any]],
    *,
    current_simulation_day: Optional[int],
    run_seed: str,
    tier_by_npc_id: Optional[Mapping[str, str]] = None,
    existing_lifecycle: Optional[Mapping[str, Mapping[str, Any]]] = None,
    deceased_names: Optional[Sequence[str]] = None,
    health_by_npc_id: Optional[Mapping[str, float]] = None,
    pressure_by_npc_id: Optional[Mapping[str, float]] = None,
    profile_id: str = "human",
) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Flag-gated lifecycle seam entry point. Returns
    (lifecycle_records_by_npc_id, events, diagnostics).

    Fail-closed: the flag OFF, a missing simulation day, or any internal error
    yields a no-op (empty records + events) with a developer diagnostic — never
    a raised exception and never mutated NPC state. Structured-clock integration
    calls this pure seam only with an authoritative simulation day.
    """
    diag = _empty_tick_diagnostics()
    if not is_enabled():
        diag["skip_reason"] = "flag_disabled"
        return {}, [], diag
    if current_simulation_day is None:
        diag["skip_reason"] = "no_simulation_day"
        return {}, [], diag

    try:
        prof = get_profile(profile_id)
        tiers = {str(k): str(v) for k, v in (tier_by_npc_id or {}).items()}
        existing = existing_lifecycle or {}
        health = health_by_npc_id or {}
        pressure = pressure_by_npc_id or {}

        records_out: Dict[str, Dict[str, Any]] = {}
        events: List[Dict[str, Any]] = []
        dormant_records: List[Dict[str, Any]] = []
        dormant_ids: List[str] = []
        migrations = 0
        evaluated = 0
        stage_transitions: List[Dict[str, Any]] = []
        probabilities: Dict[str, float] = {}
        rolls: Dict[str, Any] = {}

        for npc in npcs or []:
            npc_id = str(npc.get("npc_id") or npc.get("name") or "")
            if not npc_id:
                continue
            source = existing.get(npc_id) or npc
            record, migrated = migrate_record(
                source,
                current_simulation_day=current_simulation_day,
                run_seed=run_seed,
                deceased_names=deceased_names,
                profile_id=str(source.get("lifecycle_profile") or profile_id),
            )
            if migrated:
                migrations += 1
            prior_stage = record.get("life_stage")

            tier = tiers.get(npc_id, "active")
            if tier in _NO_PROCESS_TIERS or not record.get("alive", True):
                records_out[npc_id] = record
                continue
            if tier in _BATCH_TIERS:
                dormant_records.append(record)
                dormant_ids.append(npc_id)
                continue

            updated, death_event, mortality = process_individual(
                record,
                current_simulation_day=current_simulation_day,
                run_seed=run_seed,
                health_factor=float(health.get(npc_id, 1.0)),
                pressure_factor=float(pressure.get(npc_id, 1.0)),
                profile=prof,
            )
            if mortality.get("evaluated"):
                evaluated += 1
                probabilities[npc_id] = mortality.get("probability")
                rolls[npc_id] = mortality.get("roll")
            if updated.get("life_stage") != prior_stage:
                stage_transitions.append(
                    {"npc_id": npc_id, "from": prior_stage, "to": updated.get("life_stage")}
                )
            if death_event is not None:
                events.append(death_event)
            records_out[npc_id] = updated

        if dormant_records:
            batch_updated, batch_events, batch_diag = process_dormant_batch(
                dormant_records,
                current_simulation_day=current_simulation_day,
                run_seed=run_seed,
                profile=prof,
            )
            evaluated += int(batch_diag.get("batch_evaluated", 0))
            for npc_id, rec in zip(dormant_ids, batch_updated):
                records_out[npc_id] = rec
            events.extend(batch_events)

        # Dedupe events by event_id (idempotency at the tick boundary).
        seen_ids: set = set()
        deduped: List[Dict[str, Any]] = []
        rejected = 0
        for ev in events:
            eid = ev.get("event_id")
            if eid in seen_ids:
                rejected += 1
                continue
            seen_ids.add(eid)
            deduped.append(ev)

        diag.update(
            {
                "lifecycle_applied": True,
                "current_simulation_day": int(current_simulation_day),
                "npcs_evaluated": evaluated,
                "migrations_performed": migrations,
                "stage_transitions": stage_transitions,
                "mortality_probabilities": probabilities,
                "mortality_rolls": rolls,
                "deaths_applied": len(deduped),
                "duplicate_events_rejected": rejected,
                "emitted_event_ids": [ev.get("event_id") for ev in deduped],
            }
        )
        return records_out, deduped, diag
    except Exception as exc:  # fail-closed: never corrupt NPC state
        diag["lifecycle_applied"] = False
        diag["error"] = str(exc)[:200]
        return {}, [], diag
