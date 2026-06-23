import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import utility_ai
from foundation_acceptance.utility_oracle import (
    oracle_aggregate,
    oracle_dimension_map,
    oracle_select,
    oracle_survival,
    inputs_complete,
    oracle_band,
    oracle_band_modifiers,
    oracle_weights,
    oracle_weights_banded,
    BAND_MODIFIERS,
)
from foundation_snapshot import FoundationTurnSnapshot


def _complete_fixture(**overrides):
    base = {
        "actor_id": "npc-a",
        "action_kind": "gather",
        "target_kind": "pressure",
        "target_id": "p1",
        "goal_kind": "secure_resources",
        "aligned_goals": ("secure_resources", "restore_loss"),
        "highest_pressure_intensity": 0.8,
        "stress_level": 40.0,
        "resource_scarcity": 0.5,
        "relationship_delta_sum": 10,
        "relationship_importance": 6.0,
        "goal_priority": 10.0,
        "starving": False,
        "negative_memory_match": False,
        "personality_order": ["gather", "protect"],
    }
    base.update(overrides)
    return base


def test_survival_minimum_maximum():
    assert oracle_survival("gather") == pytest.approx(20.0, rel=1e-6)
    assert oracle_survival("withdraw") == 22.5


def test_oracle_tie_window():
    cands = [
        _complete_fixture(actor_id="a1", action_kind="gather"),
        _complete_fixture(actor_id="a2", action_kind="protect"),
    ]
    r1 = oracle_select(cands, run_seed="seed", turn_sequence=3)
    r2 = oracle_select(cands, run_seed="seed", turn_sequence=3)
    assert r1["selected"] == r2["selected"]


def test_missing_stress_blocks_completeness():
    f = _complete_fixture(action_kind="withdraw", stress_level=None)
    assert inputs_complete(f) is False


def test_foundation_matches_oracle_on_complete_fixture():
    fixture = _complete_fixture()
    oracle_result = oracle_select([fixture], run_seed="oracle-seed", turn_sequence=5)
    snapshot = FoundationTurnSnapshot(
        schema_version=2,
        run_id="oracle-seed",
        run_seed="oracle-seed",
        turn_sequence=5,
        actor_registry=(),
        actor_resolution_inputs={},
        pressure_state_ref={"nodes": [{"id": "p1", "status": "active", "magnitude": 80, "kind": "resource"}]},
        confirmed_consequence_refs=(),
        relationship_vector_ref={"vectors": []},
        agenda_refs=({"npc_id": "npc-a", "goal_kind": "secure_resources"},),
        location_ref="yard",
        secret_access_facts=(),
        gravity_metadata={},
        utility_input_refs=(
            {
                "actor_id": "npc-a",
                "goal_kind": "secure_resources",
                "highest_pressure_intensity": 0.8,
                "stress_level": 40.0,
                "resource_scarcity": 0.5,
                "relationship_importance": 6.0,
                "starving": False,
                "memory_signatures": (),
            },
        ),
        source_state_hash="test",
    )
    import npc_world_moves as world_moves

    bundle = utility_ai.build_canonical_dimension_bundle(
        snapshot,
        actor_id="npc-a",
        action_kind="gather",
        target_kind="pressure",
        aligned_goals=world_moves.MOVE_GOAL_ALIGN["gather"],
        relationship_deltas={"loyalty": 10},
    )
    oracle_scores = oracle_dimension_map(fixture)
    for dim, val in bundle["dimension_scores"].items():
        if dim in oracle_scores:
            assert bundle["dimension_scores"][dim] == pytest.approx(oracle_scores[dim], abs=0.01)


def test_insertion_order_independence():
    scores_a = oracle_dimension_map(_complete_fixture())
    scores_b = oracle_dimension_map(_complete_fixture())
    w = {"survival": 100, "goal_progression": 50, "pressure_relief": 30, "memory_avoidance": 15}
    assert oracle_aggregate(scores_a, w) == oracle_aggregate(scores_b, w)


# --------------------------------------------------------------------------- #
# Ch 14 P2 -- oracle equivalence on stress behavioural bands (ADR-021 P2 gate)
# Compares production utility_ai.select_action (banded) against the INDEPENDENT
# oracle band model. Bands change weights only; dimension scores are unaffected.
# --------------------------------------------------------------------------- #
_P2_VARIED_SCORES = {
    "survival": 88.0,
    "goal_progression": 12.0,
    "pressure_relief": 64.0,
    "stress_reduction": 50.0,
    "relationship_impact": 44.0,
    "resource_gain_loss": 33.0,
    "memory_avoidance": 77.0,
}

_P2_INPUTS = {
    "goal_priority": 8.0,
    "highest_pressure_intensity": 0.5,
    "relationship_importance": 6.0,
    "resource_scarcity": 0.4,
    "trauma_intensity": 0.0,
    "starving": False,
}


def _p2_fixture(stress_level):
    f = dict(_P2_INPUTS)
    f["stress_level"] = stress_level
    return f


def _p2_candidate(stress_level, replacement_authorised=True, actor_id="npc-a"):
    return {
        "actor_id": actor_id,
        "action_kind": "gather",
        "target_kind": "pressure",
        "target_id": "p1",
        "dimension_scores": dict(_P2_VARIED_SCORES),
        "stress": 0.0 if stress_level is None else float(stress_level),
        "pressure_intensity": _P2_INPUTS["highest_pressure_intensity"],
        "goal_priority": _P2_INPUTS["goal_priority"],
        "relationship_importance": _P2_INPUTS["relationship_importance"],
        "resource_scarcity": _P2_INPUTS["resource_scarcity"],
        "trauma_intensity": _P2_INPUTS["trauma_intensity"],
        "starving": _P2_INPUTS["starving"],
        "replacement_authorised": replacement_authorised,
        "personality_order": ["gather"],
    }


def _p2_snapshot(stress_level, actor_id="npc-a"):
    rolling = {"npcs": [{"npc_id": actor_id, "name": "Mara"}]}
    if stress_level is not None:
        rolling["actor_stress"] = {actor_id: {"stress_level": stress_level, "capacity": 1.0}}
    replay = {
        "run_seed": "oracle-seed",
        "pressure_graph": {"nodes": [{"id": "p1", "status": "active", "magnitude": 50}]},
        "npc_agendas": {"agendas": [{"npc_id": actor_id, "goal_kind": "secure_resources"}]},
    }
    return FoundationTurnSnapshot.build(
        run_seed="oracle-seed", turn_sequence=5, rolling_state=rolling, replayability_state=replay
    )


def _p2_actor_resolution(actor_id="npc-a"):
    return {"acting_actor_ids": [actor_id], "tiers_by_actor_id": {actor_id: "hero"}}


@pytest.mark.parametrize(
    "value,band",
    [(0.0, "CALM"), (24.999, "CALM"), (25.0, "ELEVATED"), (49.999, "ELEVATED"),
     (50.0, "STRAINED"), (74.999, "STRAINED"), (75.0, "OVERLOADED"), (100.0, "OVERLOADED")],
)
def test_oracle_band_boundaries(value, band):
    assert oracle_band(value) == band


@pytest.mark.parametrize(
    "value",
    [None, True, False, "40", "nan", float("nan"), float("inf"), float("-inf"),
     -0.001, -5, 100.001, 150, [], {}],
)
def test_oracle_band_invalid_is_none(value):
    assert oracle_band(value) is None


def test_oracle_banded_weights_applied_once():
    f = _p2_fixture(90.0)  # OVERLOADED
    base = oracle_weights(f)
    banded = oracle_weights_banded(f)
    assert banded["goal_progression"] == pytest.approx(base["goal_progression"] * 0.30)
    assert banded["survival"] == pytest.approx(base["survival"] * 1.60)
    assert banded["stress_reduction"] == pytest.approx(base["stress_reduction"])  # x1.0
    assert banded["goal_progression"] != pytest.approx(base["goal_progression"] * 0.30 * 0.30)


@pytest.mark.parametrize(
    "stress_level,band",
    [(10.0, "CALM"), (40.0, "ELEVATED"), (60.0, "STRAINED"), (90.0, "OVERLOADED")],
)
def test_foundation_select_matches_oracle_each_band(stress_level, band):
    res = utility_ai.select_action(
        [_p2_candidate(stress_level)],
        snapshot=_p2_snapshot(stress_level),
        actor_resolution=_p2_actor_resolution(),
    )
    sel = res["selected"]
    assert sel is not None
    assert sel["stress_band"] == band == oracle_band(stress_level)
    expected = oracle_aggregate(_P2_VARIED_SCORES, oracle_weights_banded(_p2_fixture(stress_level)))
    assert sel["base_utility"] == pytest.approx(expected, abs=1e-6)
    if band != "CALM":
        unbanded = oracle_aggregate(_P2_VARIED_SCORES, oracle_weights(_p2_fixture(stress_level)))
        twice_w = {
            n: w * BAND_MODIFIERS[band].get(n, 1.0)
            for n, w in oracle_weights_banded(_p2_fixture(stress_level)).items()
        }
        twice = oracle_aggregate(_P2_VARIED_SCORES, twice_w)
        assert sel["base_utility"] != pytest.approx(unbanded, abs=1e-6)  # bands engage
        assert sel["base_utility"] != pytest.approx(twice, abs=1e-6)     # applied once, not twice


def test_foundation_calm_equals_unbanded_oracle():
    res = utility_ai.select_action(
        [_p2_candidate(10.0)], snapshot=_p2_snapshot(10.0), actor_resolution=_p2_actor_resolution()
    )
    unbanded = oracle_aggregate(_P2_VARIED_SCORES, oracle_weights(_p2_fixture(10.0)))
    assert res["selected"]["base_utility"] == pytest.approx(unbanded, abs=1e-9)


@pytest.mark.parametrize("bad", [None, 150.0])
def test_foundation_failclosed_matches_unbanded_oracle(bad):
    res = utility_ai.select_action(
        [_p2_candidate(bad, replacement_authorised=True)],
        snapshot=_p2_snapshot(bad),
        actor_resolution=_p2_actor_resolution(),
    )
    sel = res["selected"]
    assert sel is not None
    assert oracle_band(bad) is None
    assert sel["stress_band"] is None
    assert sel["stress_input_valid"] is False
    assert sel["replacement_authorised"] is False  # fail-closed despite candidate True
    expected_unbanded = oracle_aggregate(_P2_VARIED_SCORES, oracle_weights(_p2_fixture(bad)))
    assert sel["base_utility"] == pytest.approx(expected_unbanded, abs=1e-6)
