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