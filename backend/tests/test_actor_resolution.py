import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import actor_resolution
from foundation_snapshot import FoundationTurnSnapshot


def _snapshot(rolling, replay=None, turn=5):
    return FoundationTurnSnapshot.build(
        run_seed="seed-1",
        turn_sequence=turn,
        rolling_state=rolling,
        replayability_state=replay or {"run_seed": "seed-1", "pressure_graph": {"nodes": []}},
    )


def test_dead_actor_referenceable_not_acting():
    rolling = {
        "deceased": ["Mira"],
        "npcs": [{"name": "Mira", "npc_id": "npc-mira"}],
    }
    prepared = actor_resolution.evaluate_actor_resolution(_snapshot(rolling))
    assert "npc-mira" in [row["actor_id"] for row in prepared["referenceable_registry"]]
    assert "npc-mira" not in prepared["acting_actor_ids"]
    assert prepared["tiers_by_actor_id"]["npc-mira"] == "archived"


def test_acting_set_excludes_archived_and_unknown():
    rolling = {
        "npcs": [
            {"name": "Hero", "npc_id": "hero-1", "stance": "ally", "last_seen": "here"},
            {"name": "Active", "npc_id": "active-1"},
        ]
    }
    prepared = actor_resolution.evaluate_actor_resolution(
        _snapshot(rolling),
        retention_scores={"hero-1": 0.8, "active-1": 0.55},
        gravity_scores={"hero-1": 0.85, "active-1": 0.6},
    )
    assert "hero-1" in prepared["acting_actor_ids"]
    assert "active-1" in prepared["acting_actor_ids"]


def test_tier_ceiling_demotes_overflow():
    rolling = {"npcs": [{"name": f"N{i}", "npc_id": f"n{i}", "stance": "ally"} for i in range(20)]}
    retention = {f"n{i}": 0.9 for i in range(20)}
    gravity = {f"n{i}": 0.9 for i in range(20)}
    prepared = actor_resolution.evaluate_actor_resolution(
        _snapshot(rolling),
        retention_scores=retention,
        gravity_scores=gravity,
    )
    hero_count = sum(1 for tier in prepared["tiers_by_actor_id"].values() if tier == "hero")
    assert hero_count <= actor_resolution.TIER_CEILINGS["hero"]


def test_insertion_order_independence():
    rolling_a = {"npcs": [{"name": "B", "npc_id": "b"}, {"name": "A", "npc_id": "a"}]}
    rolling_b = {"npcs": [{"name": "A", "npc_id": "a"}, {"name": "B", "npc_id": "b"}]}
    p1 = actor_resolution.evaluate_actor_resolution(_snapshot(rolling_a))
    p2 = actor_resolution.evaluate_actor_resolution(_snapshot(rolling_b))
    assert p1["state_hash"] == p2["state_hash"]


def test_cadence_blocks_rapid_actions():
    prepared = {
        "tiers_by_actor_id": {"a1": "relevant"},
        "acting_actor_ids": ["a1"],
    }
    assert not actor_resolution.is_actor_eligible_for_action(
        "a1", prepared, turn_sequence=4, last_action_turn=3
    )
    assert actor_resolution.is_actor_eligible_for_action(
        "a1", prepared, turn_sequence=5, last_action_turn=3
    )


def test_schema_refuses_newer_version():
    with pytest.raises(actor_resolution.ActorResolutionError):
        actor_resolution.normalize_actor_resolution_state({"schema_version": 99})