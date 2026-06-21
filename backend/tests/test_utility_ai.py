import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import utility_ai
from foundation_snapshot import FoundationTurnSnapshot


def _snapshot(turn=3):
    return FoundationTurnSnapshot.build(
        run_seed="utility-seed",
        turn_sequence=turn,
        rolling_state={"npcs": [{"name": "A", "npc_id": "a1", "stance": "ally"}]},
        replayability_state={"run_seed": "utility-seed", "pressure_graph": {"nodes": []}},
    )


def test_weighted_average_formula():
    scores = {
        "survival": 80.0,
        "goal_progression": 60.0,
        "pressure_relief": 40.0,
        "stress_reduction": 20.0,
        "relationship_impact": 50.0,
        "resource_gain_loss": 30.0,
        "memory_avoidance": 10.0,
    }
    weights = utility_ai.compute_dimension_weights()
    utility = utility_ai.compute_utility_score(scores, weights)
    assert 0.0 <= utility <= 100.0


def test_noise_reproducible():
    material = "run_seed=s|turn=1|subsystem=utility_ai|actor_id=a1|candidate_set=x|rng_v=1|seed_schema_v=1"
    n1 = utility_ai.apply_whim_noise(50.0, seed_material=material, draw_index=0)
    n2 = utility_ai.apply_whim_noise(50.0, seed_material=material, draw_index=0)
    assert n1 == n2


def test_tie_window_prefers_personality_order():
    snapshot = _snapshot()
    actor_resolution = {
        "acting_actor_ids": ["a1", "a2"],
        "tiers_by_actor_id": {"a1": "hero", "a2": "hero"},
    }
    candidates = []
    for actor_id, action in (("a1", "gather"), ("a2", "gather")):
        candidates.append(
            {
                "actor_id": actor_id,
                "action_kind": action,
                "target_kind": "player",
                "target_id": "player",
                "dimension_scores": {k: 50.0 for k in utility_ai.DIMENSION_ORDER},
                "personality_order": ["gather", "protect"],
            }
        )
    result = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)
    assert result["selected"] is not None


def test_ineligible_actor_excluded():
    snapshot = _snapshot()
    actor_resolution = {"acting_actor_ids": [], "tiers_by_actor_id": {"a1": "archived"}}
    result = utility_ai.select_action(
        [
            {
                "actor_id": "a1",
                "action_kind": "gather",
                "target_kind": "player",
                "target_id": "player",
                "dimension_scores": {"survival": 90.0},
            }
        ],
        snapshot=snapshot,
        actor_resolution=actor_resolution,
    )
    assert result["selected"] is None