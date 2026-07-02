"""
Chapter 33 Phase 1 — NPC Lifecycle core tests (deterministic, offline).

Covers lifecycle state + migration, simulation-day aging & Appendix A.7 life
stages, deterministic natural mortality, the idempotent death transition,
tier-aware processing, and safety (flag default OFF, fail-closed, replay
determinism, no prose-driven death, no prompt leakage). No server, no MongoDB,
no LLM.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import ai_config  # noqa: E402
import npc_lifecycle as L  # noqa: E402

SEED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
Y = L.DAYS_PER_SIMULATION_YEAR


def _live_record(npc_id="n1", *, age_years=30, current_day=None, **extra):
    current_day = current_day if current_day is not None else age_years * Y
    birth = current_day - age_years * Y
    rec = {
        "schema_version": L.LIFECYCLE_SCHEMA_VERSION,
        "npc_id": npc_id,
        "birth_simulation_day": birth,
        "lifecycle_profile": "human",
        "alive": True,
        "death_simulation_day": None,
        "death_cause": None,
        "last_mortality_evaluation_day": None,
        "life_stage": L.life_stage(birth, current_day),
    }
    rec.update(extra)
    return rec


# ---------------------------------------------------------------------------
# Aging & life stages (Appendix A.7)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "years,stage",
    [(0, "child"), (15, "child"), (16, "adult"), (49, "adult"),
     (50, "elder"), (69, "elder"), (70, "venerable"), (120, "venerable")],
)
def test_life_stage_boundaries(years, stage):
    assert L.life_stage(0, years * Y) == stage


def test_stage_boundary_exact_days_15_16():
    assert L.life_stage(0, 15 * Y) == "child"
    assert L.life_stage(0, 16 * Y) == "adult"


def test_stage_boundary_exact_days_49_50_69_70():
    assert L.life_stage(0, 49 * Y) == "adult"
    assert L.life_stage(0, 50 * Y) == "elder"
    assert L.life_stage(0, 69 * Y) == "elder"
    assert L.life_stage(0, 70 * Y) == "venerable"


def test_age_uses_explicit_simulation_days_not_turn_proxy():
    # Age is current_day - birth_day, in days; no turn_number x 60 anywhere.
    assert L.age_days(1000, 1000 + 5 * Y) == 5 * Y
    assert L.age_years(1000, 1000 + 5 * Y) == 5
    assert L.age_days(500, 100) == 0  # never negative


def test_non_human_profile_configuration():
    fae = {
        "profile_id": "fae",
        "stage_bounds_years": (("sprout", 0, 40), ("bloom", 40, 200), ("ancient", 200, None)),
        "mortality_min_age_years": 40,
        "age_factor_ref_age_years": 200,
        "age_factor_doubling_years": 40,
        "max_plausible_age_years": 800,
        "migration_default_min_age_years": 60,
        "migration_default_max_age_years": 180,
    }
    assert L.life_stage(0, 39 * Y, profile=fae) == "sprout"
    assert L.life_stage(0, 40 * Y, profile=fae) == "bloom"
    assert L.life_stage(0, 250 * Y, profile=fae) == "ancient"
    assert L.natural_mortality_probability(39, profile=fae) == 0.0  # below fae min age


# ---------------------------------------------------------------------------
# Natural mortality probability
# ---------------------------------------------------------------------------
def test_mortality_base_adult_rate():
    assert L.natural_mortality_probability(16) == pytest.approx(0.005)
    assert L.natural_mortality_probability(50) == pytest.approx(0.005)  # <= ref age


def test_mortality_no_roll_before_min_age():
    assert L.natural_mortality_probability(0) == 0.0
    assert L.natural_mortality_probability(15) == 0.0


def test_mortality_age_factor_doubles_every_8_years_past_50():
    assert L.natural_mortality_probability(58) == pytest.approx(0.01)   # x2
    assert L.natural_mortality_probability(66) == pytest.approx(0.02)   # x4


def test_mortality_health_and_pressure_factors():
    base = L.natural_mortality_probability(30)
    assert L.natural_mortality_probability(30, health_factor=5.0) == pytest.approx(base * 5)
    assert L.natural_mortality_probability(30, pressure_factor=2.0) == pytest.approx(base * 2)
    # factors clamp to their bands
    assert L.natural_mortality_probability(30, health_factor=99) == pytest.approx(base * 5)
    assert L.natural_mortality_probability(30, pressure_factor=0.1) == pytest.approx(base)


def test_mortality_probability_bounded_0_1():
    assert L.natural_mortality_probability(130, health_factor=5, pressure_factor=2) == 1.0
    assert 0.0 <= L.natural_mortality_probability(80) <= 1.0


# ---------------------------------------------------------------------------
# Deterministic mortality evaluation
# ---------------------------------------------------------------------------
def test_mortality_evaluation_seeded_deterministic():
    rec = _live_record(age_years=80)
    a = L.evaluate_natural_mortality(rec, current_simulation_day=80 * Y, run_seed=SEED)
    b = L.evaluate_natural_mortality(rec, current_simulation_day=80 * Y, run_seed=SEED)
    assert a["roll"] == b["roll"] and a["died"] == b["died"]


def test_mortality_roll_differs_by_npc_and_seed():
    r1 = _live_record("a", age_years=80)
    r2 = _live_record("b", age_years=80)
    day = 80 * Y
    roll_a = L.evaluate_natural_mortality(r1, current_simulation_day=day, run_seed=SEED)["roll"]
    roll_b = L.evaluate_natural_mortality(r2, current_simulation_day=day, run_seed=SEED)["roll"]
    roll_a2 = L.evaluate_natural_mortality(r1, current_simulation_day=day, run_seed="other")["roll"]
    assert roll_a != roll_b and roll_a != roll_a2


def test_mortality_no_duplicate_roll_in_same_period():
    rec = _live_record(age_years=80)
    rec["last_mortality_evaluation_day"] = 80 * Y  # already evaluated this sim-year
    out = L.evaluate_natural_mortality(rec, current_simulation_day=80 * Y + 3, run_seed=SEED)
    assert out["evaluated"] is False and out["skip_reason"] == "already_evaluated_period"


def test_mortality_skips_dead_and_archived():
    dead = _live_record(age_years=80, alive=False)
    arch = _live_record(age_years=80, life_stage="archived")
    assert L.evaluate_natural_mortality(dead, current_simulation_day=80 * Y, run_seed=SEED)["skip_reason"] == "not_alive"
    assert L.evaluate_natural_mortality(arch, current_simulation_day=80 * Y, run_seed=SEED)["skip_reason"] == "archived"


# ---------------------------------------------------------------------------
# Death transition (idempotent; natural + unnatural)
# ---------------------------------------------------------------------------
def test_natural_death_event_and_permanence():
    rec = _live_record(age_years=90)
    updated, ev = L.apply_death(rec, death_simulation_day=90 * Y, cause="natural_causes", natural=True)
    assert updated["alive"] is False and updated["death_simulation_day"] == 90 * Y
    assert updated["life_stage"] == "archived" and updated["death_cause"] == "natural_causes"
    assert ev["event_type"] == "npc_death" and ev["classification"] == "natural"
    for field in ("event_id", "npc_id", "simulation_day", "cause", "caused_by", "before", "after"):
        assert field in ev
    assert ev["before"]["alive"] is True and ev["after"]["alive"] is False


def test_unnatural_death_uses_same_transition():
    rec = _live_record(age_years=25)
    updated, ev = L.apply_unnatural_death(rec, death_simulation_day=25 * Y, cause="killed", caused_by=["evt-x"])
    assert updated["alive"] is False and ev["classification"] == "unnatural"
    assert ev["caused_by"] == ["evt-x"] and ev["cause"] == "killed"


def test_death_idempotent_duplicate_rejected():
    rec = _live_record(age_years=90)
    once, ev1 = L.apply_death(rec, death_simulation_day=90 * Y, cause="natural_causes", natural=True)
    twice, ev2 = L.apply_death(once, death_simulation_day=95 * Y, cause="again", natural=True)
    assert ev1 is not None and ev2 is None      # duplicate refused
    assert twice["death_simulation_day"] == 90 * Y  # original death preserved


def test_death_preserves_record_never_deletes():
    rec = _live_record(age_years=90, npc_id="keep-me")
    rec["extra_field"] = "kept"
    updated, _ = L.apply_death(rec, death_simulation_day=90 * Y, cause="natural_causes", natural=True)
    assert updated["npc_id"] == "keep-me" and updated["extra_field"] == "kept"
    assert updated["birth_simulation_day"] == rec["birth_simulation_day"]


def test_natural_death_carries_seed_provenance():
    rec = _live_record(age_years=95)
    m = L.evaluate_natural_mortality(rec, current_simulation_day=95 * Y, run_seed=SEED)
    _, ev = L.apply_death(rec, death_simulation_day=95 * Y, cause="natural_causes",
                          natural=True, seed_provenance=m["seed_material"])
    assert ev["seed_provenance"] == m["seed_material"]


def test_death_event_has_no_prose_fields():
    rec = _live_record(age_years=90)
    _, ev = L.apply_death(rec, death_simulation_day=90 * Y, cause="natural_causes", natural=True)
    for leak in ("narrative", "prose", "text", "paragraphs"):
        assert leak not in ev


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------
def test_migration_creates_deterministic_plausible_adult():
    npc = {"npc_id": "m1", "name": "Mara"}
    r1, mig1 = L.migrate_record(npc, current_simulation_day=100 * Y, run_seed=SEED)
    r2, mig2 = L.migrate_record(npc, current_simulation_day=100 * Y, run_seed=SEED)
    assert mig1 is True and r1 == r2                      # deterministic
    assert r1["alive"] is True and r1["birth_simulation_day"] <= 100 * Y
    age = L.age_years(r1["birth_simulation_day"], 100 * Y)
    assert 18 <= age <= 60 and r1["life_stage"] in ("adult", "elder")


def test_migration_preserves_valid_existing_state():
    existing = _live_record("e1", age_years=40, current_day=100 * Y, last_mortality_evaluation_day=99 * Y)
    r, mig = L.migrate_record(existing, current_simulation_day=100 * Y, run_seed=SEED)
    assert mig is False
    assert r["birth_simulation_day"] == existing["birth_simulation_day"]
    assert r["last_mortality_evaluation_day"] == 99 * Y


def test_migration_never_resurrects_deceased():
    npc = {"npc_id": "d1", "name": "Ghost"}
    r, _ = L.migrate_record(npc, current_simulation_day=100 * Y, run_seed=SEED, deceased_names=["Ghost"])
    assert r["alive"] is False and r["life_stage"] == "archived"
    assert r["death_simulation_day"] == 100 * Y
    assert r["death_cause"] == L.LEGACY_DECEASED_REGISTRY_CAUSE


def test_migration_clamps_impossible_negative_age():
    npc = {"npc_id": "b1", "name": "Backwards", "birth_simulation_day": 200 * Y}  # born in the future
    r, _ = L.migrate_record(npc, current_simulation_day=100 * Y, run_seed=SEED)
    assert r["birth_simulation_day"] <= 100 * Y
    assert L.age_days(r["birth_simulation_day"], 100 * Y) >= 0


# ---------------------------------------------------------------------------
# Tier-aware processing
# ---------------------------------------------------------------------------
def test_process_individual_ages_and_evaluates():
    rec = _live_record(age_years=30, current_day=0)  # born 30y ago relative to day 0
    rec["birth_simulation_day"] = -30 * Y
    updated, death, mort = L.process_individual(rec, current_simulation_day=35 * Y, run_seed=SEED)
    assert updated["life_stage"] == L.life_stage(rec["birth_simulation_day"], 35 * Y)
    assert mort["evaluated"] is True
    assert updated["last_mortality_evaluation_day"] == 35 * Y


def test_process_individual_archived_is_noop():
    rec = _live_record(age_years=80, life_stage="archived", alive=False)
    updated, death, mort = L.process_individual(rec, current_simulation_day=80 * Y, run_seed=SEED)
    assert death is None and mort.get("skipped") is True
    assert updated == rec


def test_dormant_batch_emits_event_per_death():
    # Very old cohort under maximum health/pressure is highly likely to die; assert
    # every death that occurs carries an event (no silent deaths), API shape holds.
    records = [_live_record(f"z{i}", age_years=125) for i in range(5)]
    updated, events, diag = L.process_dormant_batch(records, current_simulation_day=125 * Y, run_seed=SEED)
    assert len(updated) == 5 and diag["batch_evaluated"] == 5
    for ev in events:
        assert ev["event_type"] == "npc_death"
    dead = [r for r in updated if r["alive"] is False]
    assert len(dead) == len(events)  # one event per applied death


# ---------------------------------------------------------------------------
# Seam: evaluate_lifecycle_tick (flag-gated) + safety
# ---------------------------------------------------------------------------
def test_flag_default_off():
    assert ai_config.ENABLE_NPC_LIFECYCLE is False
    assert L.is_enabled() is False


def test_tick_flag_off_is_noop(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_NPC_LIFECYCLE", False)
    npcs = [{"npc_id": "n1", "name": "Mara"}]
    records, events, diag = L.evaluate_lifecycle_tick(npcs, current_simulation_day=100 * Y, run_seed=SEED)
    assert records == {} and events == []
    assert diag["lifecycle_applied"] is False and diag["skip_reason"] == "flag_disabled"


def test_tick_flag_on_applies_and_migrates(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_NPC_LIFECYCLE", True)
    npcs = [{"npc_id": "n1", "name": "Mara"}, {"npc_id": "n2", "name": "Bran"}]
    records, events, diag = L.evaluate_lifecycle_tick(
        npcs, current_simulation_day=100 * Y, run_seed=SEED,
        tier_by_npc_id={"n1": "hero", "n2": "dormant"},
    )
    assert diag["lifecycle_applied"] is True
    assert diag["migrations_performed"] == 2
    assert set(records) == {"n1", "n2"}
    assert diag["current_simulation_day"] == 100 * Y


def test_tick_archived_tier_not_processed(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_NPC_LIFECYCLE", True)
    npcs = [{"npc_id": "n1", "name": "Mara"}]
    records, events, diag = L.evaluate_lifecycle_tick(
        npcs, current_simulation_day=100 * Y, run_seed=SEED, tier_by_npc_id={"n1": "archived"},
    )
    assert diag["npcs_evaluated"] == 0  # archived tier is a no-op for evaluation


def test_tick_no_simulation_day_is_failclosed_noop(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_NPC_LIFECYCLE", True)
    records, events, diag = L.evaluate_lifecycle_tick([{"npc_id": "n1"}], current_simulation_day=None, run_seed=SEED)
    assert records == {} and events == [] and diag["skip_reason"] == "no_simulation_day"


def test_tick_failclosed_on_bad_input_no_raise_no_mutation(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_NPC_LIFECYCLE", True)
    npcs = [123, {"npc_id": "n1", "name": "Mara"}]  # 123 is not a mapping -> internal error
    before = copy.deepcopy(npcs)
    records, events, diag = L.evaluate_lifecycle_tick(npcs, current_simulation_day=100 * Y, run_seed=SEED)
    assert records == {} and events == []
    assert diag["lifecycle_applied"] is False and diag["error"]
    assert npcs == before  # input not corrupted


def test_tick_replay_deterministic(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_NPC_LIFECYCLE", True)
    npcs = [{"npc_id": f"n{i}", "name": f"npc{i}"} for i in range(6)]
    tiers = {f"n{i}": ("hero" if i % 2 else "dormant") for i in range(6)}

    def run():
        return L.evaluate_lifecycle_tick(
            copy.deepcopy(npcs), current_simulation_day=95 * Y, run_seed=SEED, tier_by_npc_id=tiers
        )

    r1, e1, d1 = run()
    r2, e2, d2 = run()
    assert r1 == r2 and e1 == e2
    assert d1["emitted_event_ids"] == d2["emitted_event_ids"]


def test_tick_diagnostics_developer_shape(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_NPC_LIFECYCLE", True)
    _, _, diag = L.evaluate_lifecycle_tick(
        [{"npc_id": "n1", "name": "Mara"}], current_simulation_day=100 * Y, run_seed=SEED,
        tier_by_npc_id={"n1": "hero"},
    )
    for key in ("lifecycle_flag_enabled", "current_simulation_day", "npcs_evaluated",
                "migrations_performed", "stage_transitions", "mortality_probabilities",
                "mortality_rolls", "deaths_applied", "duplicate_events_rejected",
                "emitted_event_ids", "error"):
        assert key in diag
