import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import memory_retrieval
from foundation_snapshot import FoundationTurnSnapshot


def test_pattern_bonus_log10():
    mem = {
        "weight_class": "major",
        "days_since_event": 1.0,
        "context": {"location": "gate"},
        "pattern_count": 100,
    }
    ctx = {"location": "gate"}
    w = memory_retrieval.memory_retrieval_weight(mem, current_context=ctx, turn_sequence=10)
    assert w > 0.0


def test_seeded_sampling_reproducible():
    memories = [
        {"memory_id": "m1", "_weight": 0.5},
        {"memory_id": "m2", "_weight": 0.3},
        {"memory_id": "m3", "_weight": 0.2},
    ]
    material = "run_seed=s|turn=1|subsystem=memory_retrieval|actor_id=a|candidate_set=x|rng_v=1|seed_schema_v=1"
    s1, d1 = memory_retrieval.sample_memories(memories, sample_count=2, seed_material=material)
    s2, d2 = memory_retrieval.sample_memories(memories, sample_count=2, seed_material=material)
    assert [m["memory_id"] for m in s1] == [m["memory_id"] for m in s2]
    assert d1 == d2


def test_shadow_mode_default():
    rolling = {
        "npc_memory": [
            {
                "name": "Guard",
                "remembers": [
                    {"summary": "attack", "since_turn": 1, "weight": "major", "context": {"location": "gate"}}
                ],
            }
        ],
        "npcs": [{"name": "Guard", "npc_id": "g1", "stance": "ally"}],
        "scene": "gate",
    }
    snapshot = FoundationTurnSnapshot.build(
        run_seed="seed",
        turn_sequence=5,
        rolling_state=rolling,
        replayability_state={"run_seed": "seed", "pressure_graph": {"nodes": []}},
    )
    actor_resolution = {
        "tiers_by_actor_id": {"g1": "hero"},
        "acting_actor_ids": ["g1"],
    }
    prepared = memory_retrieval.evaluate_memory_retrieval(
        snapshot,
        actor_resolution=actor_resolution,
        gravity={},
        rolling_state=rolling,
        shadow_mode=True,
        developer_mode=False,
    )
    assert prepared["shadow_mode"] is True


def test_concealed_secret_not_retrieved():
    rolling = {
        "npc_memory": [
            {
                "name": "Spy",
                "remembers": [{"summary": "secret", "since_turn": 1, "weight": "major", "concealed": True}],
            }
        ],
        "npcs": [{"name": "Spy", "npc_id": "s1"}],
    }
    snapshot = FoundationTurnSnapshot.build(
        run_seed="seed",
        turn_sequence=3,
        rolling_state=rolling,
        replayability_state={"run_seed": "seed", "pressure_graph": {"nodes": []}},
    )
    actor_resolution = {"tiers_by_actor_id": {"s1": "hero"}, "acting_actor_ids": ["s1"]}
    prepared = memory_retrieval.evaluate_memory_retrieval(
        snapshot,
        actor_resolution=actor_resolution,
        gravity={},
        rolling_state=rolling,
    )
    assert prepared["selected_memory_ids"] == []