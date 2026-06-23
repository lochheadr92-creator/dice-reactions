"""
Ch 14 P1 — stress substrate tests.

Covers the pure numeric model, the seeded per-actor capacity, the persisted
accumulation hook, byte-identical determinism per seed, and the Ch 27 gate flip
(stress_level reaching the utility dimension bundle → replacement_authorised).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import stress
from engine_determinism import DeterminismError, canonical_json
from foundation_snapshot import FoundationTurnSnapshot


# --------------------------------------------------------------------------- #
# capacity_for
# --------------------------------------------------------------------------- #
def test_capacity_in_band_and_deterministic():
    c1 = stress.capacity_for("seed-1", "npc-a")
    c2 = stress.capacity_for("seed-1", "npc-a")
    assert c1 == c2
    assert stress.STRESS_CAPACITY_MIN <= c1 <= stress.STRESS_CAPACITY_MAX


def test_capacity_varies_by_actor_and_seed():
    assert stress.capacity_for("seed-1", "npc-a") != stress.capacity_for("seed-1", "npc-b")
    assert stress.capacity_for("seed-1", "npc-a") != stress.capacity_for("seed-2", "npc-a")


def test_capacity_empty_actor_is_nominal():
    assert stress.capacity_for("seed-1", "") == stress.STRESS_CAPACITY_NOMINAL


# --------------------------------------------------------------------------- #
# generate
# --------------------------------------------------------------------------- #
def test_generation_zero_when_no_pressure():
    assert stress.generate(None, 1.0) == 0.0
    assert stress.generate(0.0, 1.0) == 0.0


def test_generation_scales_with_pressure():
    g = stress.generate(0.5, 1.0)
    assert g == pytest.approx(stress.STRESS_GENERATION_SCALE * 0.5)


def test_fear_increases_generation():
    base = stress.generate(0.5, 1.0, fear_present=False)
    feared = stress.generate(0.5, 1.0, fear_present=True)
    assert feared > base
    assert feared == pytest.approx(base * (1.0 + stress.STRESS_THREAT_WEIGHT_FEAR_BONUS))


def test_higher_capacity_reduces_generation():
    resilient = stress.generate(0.8, stress.STRESS_CAPACITY_MAX)
    fragile = stress.generate(0.8, stress.STRESS_CAPACITY_MIN)
    assert fragile > resilient


# --------------------------------------------------------------------------- #
# accumulate / decay
# --------------------------------------------------------------------------- #
def test_accumulate_adds_generation():
    assert stress.accumulate(0.0, 30.0) == pytest.approx(30.0)


def test_decay_reduces_carried_stress_under_zero_generation():
    after = stress.accumulate(80.0, 0.0)
    assert after == pytest.approx(80.0 * stress.STRESS_DECAY_PER_TURN)
    assert after < 80.0


def test_accumulate_clamps_to_ceiling():
    assert stress.accumulate(95.0, 100.0) == stress.STRESS_MAX


def test_accumulate_floors_at_zero():
    assert stress.accumulate(0.0, 0.0) == stress.STRESS_MIN


def test_recovery_trends_to_zero_under_safety():
    s = 90.0
    for _ in range(40):
        s = stress.accumulate(s, 0.0)
    assert s < 1.0


def test_clamp_rejects_non_finite():
    with pytest.raises(DeterminismError):
        stress.clamp_stress(float("nan"))


# --------------------------------------------------------------------------- #
# update_actor_stress — persistence, keying, accumulation
# --------------------------------------------------------------------------- #
def _rolling_with_actor():
    return {"npcs": [{"npc_id": "npc-a", "name": "Mara"}]}


def _pressure(magnitude=50):
    return {"nodes": [{"id": "p1", "status": "active", "magnitude": magnitude}]}


# npc-a is in the authoritative interpretation set (has an active agenda) so it updates.
_IN_SCOPE = {"npc-a": {"goal_kind": "escape_danger"}}


def test_update_keys_by_registry_actor_id():
    rolling = _rolling_with_actor()
    out = stress.update_actor_stress(rolling, _pressure(), run_seed="s", turn_sequence=1, agendas_by_actor=_IN_SCOPE)
    assert "npc-a" in out
    assert rolling["actor_stress"]["npc-a"]["stress_level"] > 0.0


def test_stress_accumulates_across_turns():
    rolling = _rolling_with_actor()
    stress.update_actor_stress(rolling, _pressure(60), run_seed="s", turn_sequence=1, agendas_by_actor=_IN_SCOPE)
    t1 = rolling["actor_stress"]["npc-a"]["stress_level"]
    stress.update_actor_stress(rolling, _pressure(60), run_seed="s", turn_sequence=2, agendas_by_actor=_IN_SCOPE)
    t2 = rolling["actor_stress"]["npc-a"]["stress_level"]
    # Under sustained pressure, stress climbs turn-over-turn until decay balances.
    assert t2 > t1


def test_stress_recovers_when_pressure_clears():
    rolling = _rolling_with_actor()
    for t in range(1, 6):
        stress.update_actor_stress(rolling, _pressure(80), run_seed="s", turn_sequence=t, agendas_by_actor=_IN_SCOPE)
    peak = rolling["actor_stress"]["npc-a"]["stress_level"]
    for t in range(6, 16):
        stress.update_actor_stress(rolling, {"nodes": []}, run_seed="s", turn_sequence=t, agendas_by_actor=_IN_SCOPE)
    assert rolling["actor_stress"]["npc-a"]["stress_level"] < peak


def test_offscreen_actor_retains_stress_unchanged():
    # Actor accrues stress while in-scope, then drops out of the agenda set.
    rolling = _rolling_with_actor()
    stress.update_actor_stress(rolling, _pressure(70), run_seed="s", turn_sequence=1, agendas_by_actor=_IN_SCOPE)
    held = rolling["actor_stress"]["npc-a"]["stress_level"]
    assert held > 0.0
    # Next turn npc-a is NOT simulated (empty interpretation set): no decay, no gen.
    stress.update_actor_stress(rolling, _pressure(70), run_seed="s", turn_sequence=2, agendas_by_actor={})
    assert rolling["actor_stress"]["npc-a"]["stress_level"] == held


# --------------------------------------------------------------------------- #
# Determinism — byte-identical trajectory per seed
# --------------------------------------------------------------------------- #
def _trajectory(seed, turns=12):
    rolling = _rolling_with_actor()
    traj = []
    for t in range(1, turns + 1):
        stress.update_actor_stress(rolling, _pressure(55), run_seed=seed, turn_sequence=t, agendas_by_actor=_IN_SCOPE)
        traj.append(rolling["actor_stress"]["npc-a"]["stress_level"])
    return traj


def test_trajectory_byte_identical_for_fixed_seed():
    a = _trajectory("fixed-seed")
    b = _trajectory("fixed-seed")
    assert canonical_json(a) == canonical_json(b)


def test_trajectory_differs_across_seeds():
    assert canonical_json(_trajectory("seed-x")) != canonical_json(_trajectory("seed-y"))


# --------------------------------------------------------------------------- #
# enforce_authoritative_stress
# --------------------------------------------------------------------------- #
def test_enforce_strips_model_mutation():
    merged = {"actor_stress": {"npc-a": {"stress_level": 999.0}}}
    auth = {"npc-a": {"stress_level": 42.0, "capacity": 1.0, "schema_version": 1}}
    notes = stress.enforce_authoritative_stress(merged, auth)
    assert merged["actor_stress"] == auth
    assert notes == ["actor_stress_model_mutation_stripped"]


def test_enforce_noop_when_already_authoritative():
    auth = {"npc-a": {"stress_level": 42.0}}
    merged = {"actor_stress": dict(auth)}
    assert stress.enforce_authoritative_stress(merged, auth) == []


# --------------------------------------------------------------------------- #
# Ch 27 gate flip — stress_level flows snapshot -> dimension bundle
# --------------------------------------------------------------------------- #
def _build_snapshot(with_stress):
    rolling = {
        "npcs": [{"npc_id": "npc-a", "name": "Mara"}],
    }
    if with_stress:
        rolling["actor_stress"] = {"npc-a": {"stress_level": 30.0, "capacity": 1.0}}
    replay = {
        "run_seed": "s",
        "pressure_graph": {"nodes": [{"id": "p1", "status": "active", "magnitude": 50}]},
        "npc_agendas": {"agendas": [{"npc_id": "npc-a", "goal_kind": "escape_danger"}]},
    }
    return FoundationTurnSnapshot.build(
        run_seed="s",
        turn_sequence=1,
        rolling_state=rolling,
        replayability_state=replay,
    )


def test_gate_blocked_without_stress():
    import npc_world_moves as world_moves
    import utility_ai

    snapshot = _build_snapshot(with_stress=False)
    bundle = utility_ai.build_canonical_dimension_bundle(
        snapshot,
        actor_id="npc-a",
        action_kind="withdraw",
        target_kind="location",
        aligned_goals=world_moves.MOVE_GOAL_ALIGN["withdraw"],
        relationship_deltas={},
    )
    assert bundle["replacement_authorised"] is False
    assert "MISSING_STRESS_LEVEL" in bundle["blocker_codes"]


def test_gate_authorised_with_stress():
    import npc_world_moves as world_moves
    import utility_ai

    snapshot = _build_snapshot(with_stress=True)
    # stress_level made it into the snapshot's utility inputs.
    ref = next(r for r in snapshot.utility_input_refs if r["actor_id"] == "npc-a")
    assert ref["stress_level"] == 30.0

    bundle = utility_ai.build_canonical_dimension_bundle(
        snapshot,
        actor_id="npc-a",
        action_kind="withdraw",
        target_kind="location",
        aligned_goals=world_moves.MOVE_GOAL_ALIGN["withdraw"],
        relationship_deltas={},
    )
    assert "MISSING_STRESS_LEVEL" not in bundle["blocker_codes"]
    assert bundle["replacement_authorised"] is True


# --------------------------------------------------------------------------- #
# #3 — capacity is divided exactly once (no pressure/C^2 regression)
# --------------------------------------------------------------------------- #
def test_generation_divides_capacity_exactly_once():
    # SCALE(100) * intensity(1.0) * threat(1.0) / C(2.0) == 50.0
    assert stress.generate(1.0, 2.0) == 50.0
    # accumulate adds generation unchanged apart from decay+clamp (no second /C).
    assert stress.accumulate(0.0, 50.0) == 50.0
    assert stress.accumulate(10.0, 50.0) == pytest.approx(10.0 * stress.STRESS_DECAY_PER_TURN + 50.0)


# --------------------------------------------------------------------------- #
# #6 — snapshot source_state_hash commits authoritative stress values
# --------------------------------------------------------------------------- #
def _snapshot_with_stress_level(level):
    rolling = {"npcs": [{"npc_id": "npc-a", "name": "Mara"}]}
    if level is not None:
        rolling["actor_stress"] = {"npc-a": {"stress_level": level, "capacity": 1.0}}
    replay = {
        "run_seed": "s",
        "pressure_graph": {"nodes": [{"id": "p1", "status": "active", "magnitude": 50}]},
        "npc_agendas": {"agendas": [{"npc_id": "npc-a", "goal_kind": "escape_danger"}]},
    }
    return FoundationTurnSnapshot.build(
        run_seed="s", turn_sequence=1, rolling_state=rolling, replayability_state=replay
    )


def test_snapshot_hash_commits_stress_values():
    # Same everything except stress_level -> different snapshot identity.
    a = _snapshot_with_stress_level(20.0)
    b = _snapshot_with_stress_level(80.0)
    assert a.source_state_hash != b.source_state_hash


def _snapshot_with_raw_actor_stress(actor_stress):
    # Same rolling_keys in both branches (actor_stress key always present) so this
    # isolates the digest contribution from the pre-existing rolling_keys term.
    rolling = {"npcs": [{"npc_id": "npc-a", "name": "Mara"}], "actor_stress": actor_stress}
    replay = {
        "run_seed": "s",
        "pressure_graph": {"nodes": [{"id": "p1", "status": "active", "magnitude": 50}]},
        "npc_agendas": {"agendas": [{"npc_id": "npc-a", "goal_kind": "escape_danger"}]},
    }
    return FoundationTurnSnapshot.build(
        run_seed="s", turn_sequence=1, rolling_state=rolling, replayability_state=replay
    )


def test_snapshot_hash_digest_inert_without_values():
    # Digest commits nothing when there are no real stress values: empty dict and a
    # None-valued entry both yield no commitment -> identical snapshot identity.
    empty = _snapshot_with_raw_actor_stress({})
    none_valued = _snapshot_with_raw_actor_stress({"npc-a": {"stress_level": None}})
    assert empty.source_state_hash == none_valued.source_state_hash
