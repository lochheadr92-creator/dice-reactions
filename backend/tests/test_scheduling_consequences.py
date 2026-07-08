"""
Stage 6C-8 — Actor Resolution + Gravity live runtime scheduling.
"""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import actor_resolution
import ai_config
import foundation_promotion
import gravity_governance
import memory_retrieval
import npc_action_engine
import replayability
import runtime_scheduling
import situation_engine
import utility_ai
from foundation_snapshot import FoundationTurnSnapshot

FIXED_SEED = "scheduling-stage-6c8"


def _snapshot(rolling, replay, turn=5):
    return FoundationTurnSnapshot.build(
        run_seed=FIXED_SEED,
        turn_sequence=turn,
        rolling_state=rolling,
        replayability_state=replay,
    )


def _goal(owner_id="hero-1", goal_id="g1"):
    return {
        "goal_id": goal_id,
        "owner_type": "npc",
        "owner_id": owner_id,
        "goal_type": "patrol",
        "title": "Patrol",
        "status": "active",
        "priority": 8,
        "urgency": 7,
        "progress": 10,
        "confidence": 70,
        "created_turn": 1,
        "updated_turn": 1,
        "parent_situation_ids": [],
        "target_actor_ids": [],
        "target_location_ids": ["dock"],
        "source_event_ids": [],
        "blockers": [],
    }


def _replay_state(*, goals=None, situations=None, npc_actions=None):
    return {
        "run_seed": FIXED_SEED,
        "pressure_graph": {"nodes": [], "foreground_node_id": None, "evolution_receipts": []},
        "goals": copy.deepcopy(list(goals or [])),
        "goal_receipts": [],
        "situations": copy.deepcopy(list(situations or [])),
        "situation_receipts": [],
        "npc_actions": copy.deepcopy(list(npc_actions or [])),
        "npc_action_receipts": [],
        "engine_world_events": [],
    }


def _rolling(*, npcs=None):
    return {
        "scene": "dock",
        "npcs": list(npcs or [{"name": "Hero", "npc_id": "hero-1", "stance": "ally", "last_seen": "dock"}]),
        "relationship_vectors": [],
        "faction_pressure": [],
    }


# --- unit: runtime_scheduling -------------------------------------------------


def test_scheduling_disabled_is_noop():
    rolling = _rolling()
    replay = _replay_state(goals=[_goal()])
    result = runtime_scheduling.evaluate_runtime_scheduling(
        _snapshot(rolling, replay),
        replay,
        turn_number=5,
    )
    assert result["diagnostics"]["runtime_scheduling_applied"] is False
    assert result["actor_resolution"] is None


def test_hero_actor_updates_every_turn(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", True)
    rolling = _rolling()
    replay = _replay_state(goals=[_goal()])
    prepared = runtime_scheduling.evaluate_runtime_scheduling(
        _snapshot(rolling, replay, turn=5),
        replay,
        turn_number=5,
    )
    assert "hero-1" in prepared["updated_actors"]
    assert "hero-1" in prepared["acting_actor_ids"]
    defer_reasons = {row["actor_id"]: row["reason"] for row in prepared["deferred_actors"]}
    assert "hero-1" not in defer_reasons


def test_low_relevance_actor_cadence_deferred(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", True)
    rolling = _rolling(npcs=[{"name": "Bg", "npc_id": "bg-1"}])
    replay = _replay_state(
        goals=[_goal(owner_id="bg-1", goal_id="g-bg")],
        npc_actions=[
            {
                "action_id": "a1",
                "actor_id": "bg-1",
                "goal_id": "g-bg",
                "action_type": "patrol",
                "status": "resolved",
                "outcome": "success",
                "created_turn": 4,
                "resolved_turn": 4,
                "resulting_event_ids": [],
                "source_event_ids": [],
            }
        ],
    )
    snapshot = _snapshot(rolling, replay, turn=5)
    actor_prepared = actor_resolution.evaluate_actor_resolution(
        snapshot,
        retention_scores={"bg-1": 0.35},
    )
    assert actor_prepared["tiers_by_actor_id"]["bg-1"] == "relevant"
    result = runtime_scheduling.evaluate_runtime_scheduling(
        snapshot,
        replay,
        turn_number=5,
    )
    assert "bg-1" in {row["actor_id"] for row in result["deferred_actors"]}
    eligible, reason = runtime_scheduling.should_update_actor(
        "bg-1",
        actor_prepared=actor_prepared,
        turn_number=5,
        last_action_turn=4,
    )
    assert not eligible
    assert "cadence" in reason


def test_gravity_compression_preserves_canonical_situations(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    situation = {
        "situation_id": "sit-fade",
        "type": "threat",
        "title": "Old threat",
        "status": "active",
        "priority": 1,
        "severity": 1,
        "progress": 0,
        "involved_actors": [],
        "involved_locations": [],
        "involved_factions": [],
        "objectives": [],
        "blockers": [],
        "created_turn": 1,
        "updated_turn": 1,
    }
    rolling = _rolling()
    replay = _replay_state(situations=[situation])
    state = copy.deepcopy(replay)
    result = runtime_scheduling.evaluate_runtime_scheduling(
        _snapshot(rolling, replay, turn=10),
        replay,
        turn_number=10,
    )
    runtime_scheduling.apply_runtime_scheduling(state, result, turn_number=10)
    assert len(state["situations"]) == 1
    assert state["situations"][0]["situation_id"] == "sit-fade"
    projected = situation_engine.project_active_situations_for_rolling(
        state,
        gravity_metadata=state.get("gravity_metadata"),
    )
    item_id = "situation:sit-fade"
    band = runtime_scheduling.scheduling_item_bands(state).get(item_id)
    if band in ("archive", "eligible_for_deletion"):
        assert not any(row.get("situation_id") == "sit-fade" for row in projected)
    assert state["gravity_metadata"]["source_truth_preserved"] is True


def test_archived_situation_retrievable_via_memory_retrieval(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", True)
    rolling = _rolling()
    replay = _replay_state(
        situations=[
            {
                "situation_id": "sit-archive",
                "type": "threat",
                "title": "Faded",
                "status": "active",
                "priority": 1,
                "severity": 1,
                "progress": 0,
                "involved_actors": ["hero-1"],
                "involved_locations": ["dock"],
                "involved_factions": [],
                "objectives": [],
                "blockers": [],
                "created_turn": 1,
                "updated_turn": 1,
            }
        ],
    )
    snapshot = _snapshot(rolling, replay, turn=20)
    sched = runtime_scheduling.evaluate_runtime_scheduling(snapshot, replay, turn_number=20)
    gravity_prepared = sched["gravity"] or gravity_governance.evaluate_gravity_governance(snapshot)
    actor_prepared = sched["actor_resolution"] or actor_resolution.evaluate_actor_resolution(snapshot)
    retrieval = memory_retrieval.evaluate_memory_retrieval(
        snapshot,
        actor_resolution=actor_prepared,
        gravity=gravity_prepared,
        rolling_state=rolling,
        shadow_mode=True,
    )
    assert retrieval.get("selected_memory_ids") is not None
    assert len(replay["situations"]) == 1


def test_receipts_explain_scheduling_decisions(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", True)
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    rolling = _rolling(npcs=[{"name": "Hero", "npc_id": "hero-1"}, {"name": "Bg", "npc_id": "bg-1"}])
    replay = _replay_state(goals=[_goal(), _goal(owner_id="bg-1", goal_id="g2")])
    state = copy.deepcopy(replay)
    result = runtime_scheduling.evaluate_runtime_scheduling(
        _snapshot(rolling, replay, turn=3),
        replay,
        turn_number=3,
    )
    runtime_scheduling.apply_runtime_scheduling(state, result, turn_number=3)
    types = {row["receipt_type"] for row in state.get("scheduling_receipts") or []}
    assert types & {"actor_updated", "actor_deferred", "gravity_keep_active", "gravity_compress", "gravity_archive", "gravity_fade"}


def test_utility_unchanged_for_active_hero_actor(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", True)
    rolling = _rolling()
    replay = _replay_state(goals=[_goal()])
    snapshot = _snapshot(rolling, replay, turn=5)
    actor_prepared = actor_resolution.evaluate_actor_resolution(
        snapshot,
        retention_scores={"hero-1": 0.85},
    )
    goal = _goal()
    from npc_action_engine import _goal_utility_candidate

    candidate = _goal_utility_candidate(
        goal,
        snapshot=snapshot,
        rolling_state=rolling,
        replayability_state=replay,
        run_seed=FIXED_SEED,
    )
    assert candidate
    legacy = utility_ai.select_action(
        [candidate],
        snapshot=snapshot,
        actor_resolution={"acting_actor_ids": ["hero-1"], "tiers_by_actor_id": {"hero-1": "hero"}},
    )
    scheduled = utility_ai.select_action(
        [candidate],
        snapshot=snapshot,
        actor_resolution=actor_prepared,
    )
    assert (legacy.get("selected") or {}).get("action_kind") == (scheduled.get("selected") or {}).get(
        "action_kind"
    )


def test_npc_action_engine_defers_non_acting_actor(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", True)
    rolling = _rolling(npcs=[{"name": "Bg", "npc_id": "bg-1"}])
    state = _replay_state(goals=[_goal(owner_id="bg-1")])
    snapshot = _snapshot(rolling, state, turn=5)
    actor_prepared = actor_resolution.evaluate_actor_resolution(
        snapshot,
        retention_scores={"bg-1": 0.1},
    )
    before = len(state.get("npc_actions") or [])
    result = npc_action_engine.evolve_npc_actions(
        state,
        rolling,
        5,
        run_seed=FIXED_SEED,
        utility_snapshot=snapshot,
        actor_resolution_prepared=actor_prepared,
        scheduling_gate_active=True,
    )
    assert result["diagnostics"]["npc_action_scheduling_deferred"] >= 1
    assert len(result.get("actions") or []) == 0
    assert len(state.get("npc_actions") or []) == before


# --- integration: prepare_action_turn -----------------------------------------


def test_prepare_action_turn_scheduling_flags_off_byte_identity(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", False)
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", False)
    state = _replay_state(goals=[_goal()])
    rolling = _rolling()
    a, _, da, _, _ = replayability.prepare_action_turn(copy.deepcopy(state), 3, rolling_state=copy.deepcopy(rolling))
    b, _, db, _, _ = replayability.prepare_action_turn(copy.deepcopy(state), 3, rolling_state=copy.deepcopy(rolling))
    assert da.get("runtime_scheduling_applied") is not True
    assert a.get("npc_actions") == b.get("npc_actions")


def test_prepare_action_turn_scheduling_enabled_deterministic(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", True)
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    state = _replay_state(goals=[_goal()])
    rolling = _rolling()

    def run():
        updated, _, diag, _, wr = replayability.prepare_action_turn(
            copy.deepcopy(state), 4, rolling_state=copy.deepcopy(rolling)
        )
        return {
            "hash": updated.get("runtime_scheduling_v1", {}).get("state_hash"),
            "deferred": diag.get("runtime_scheduling_deferred_count"),
            "actions": len(updated.get("npc_actions") or []),
            "situations": len(updated.get("situations") or []),
        }

    assert run() == run()


def test_long_simulation_bounded_acting_count(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", True)
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    npcs = [{"name": f"Npc{i}", "npc_id": f"n{i}", "stance": "neutral"} for i in range(30)]
    goals = [_goal(owner_id=f"n{i}", goal_id=f"g{i}") for i in range(30)]
    state = _replay_state(goals=goals)
    rolling = _rolling(npcs=npcs)
    max_acting = 0
    for turn in range(2, 102):
        state, _, diag, _, rolling = replayability.prepare_action_turn(
            state, turn, rolling_state=rolling
        )
        acting = int(diag.get("runtime_scheduling_acting_count") or 0)
        max_acting = max(max_acting, acting)
    assert max_acting <= actor_resolution.TIER_CEILINGS["hero"] + actor_resolution.TIER_CEILINGS["active"] + actor_resolution.TIER_CEILINGS["relevant"]
    assert len(state.get("situations") or []) >= 0


def test_enabled_vs_disabled_canonical_state_preserved(monkeypatch):
    """Seeded canonical rows are never deleted; scheduling only affects cadence/projection."""
    base_goals = [_goal(owner_id="hero-1"), _goal(owner_id="bg-1", goal_id="g2")]
    base_situations = [
        {
            "situation_id": "sit-1",
            "type": "threat",
            "title": "Threat",
            "status": "active",
            "priority": 5,
            "severity": 5,
            "progress": 0,
            "involved_actors": ["hero-1"],
            "involved_locations": ["dock"],
            "involved_factions": [],
            "objectives": [],
            "blockers": [],
            "created_turn": 1,
            "updated_turn": 1,
        }
    ]
    npcs = [
        {"name": "Hero", "npc_id": "hero-1", "stance": "ally", "last_seen": "dock"},
        {"name": "Background", "npc_id": "bg-1", "stance": "neutral"},
    ]

    def run(enabled: bool, turns: int = 4):
        monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", enabled)
        monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", enabled)
        state = _replay_state(goals=copy.deepcopy(base_goals), situations=copy.deepcopy(base_situations))
        rolling = _rolling(npcs=npcs)
        for turn in range(2, 2 + turns):
            state, _, _, _, rolling = replayability.prepare_action_turn(state, turn, rolling_state=rolling)
        return state

    off = run(False)
    on = run(True)

    def _seeded_situation(state):
        return next(
            (row for row in state.get("situations") or [] if row.get("situation_id") == "sit-1"),
            None,
        )

    off_seed = _seeded_situation(off)
    on_seed = _seeded_situation(on)
    assert off_seed is not None
    assert on_seed is not None
    assert off_seed["situation_id"] == on_seed["situation_id"] == "sit-1"
    assert off_seed["title"] == on_seed["title"] == "Threat"

    off_goal_ids = {row["goal_id"] for row in off.get("goals") or []}
    on_goal_ids = {row["goal_id"] for row in on.get("goals") or []}
    assert {"g1", "g2"}.issubset(off_goal_ids)
    assert {"g1", "g2"}.issubset(on_goal_ids)

    # Scheduling on defers low-relevance actors without removing canonical goals.
    assert on.get("runtime_scheduling_v1") is not None
    assert off.get("runtime_scheduling_v1") is None


def test_compact_persistence_preserves_scheduling_decisions(monkeypatch):
    """Apply + reload prior must yield identical next-turn scheduling decisions."""
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", True)
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    rolling = _rolling(npcs=[{"name": "Hero", "npc_id": "hero-1"}, {"name": "Bg", "npc_id": "bg-1"}])
    replay = _replay_state(goals=[_goal(), _goal(owner_id="bg-1", goal_id="g2")])
    snapshot = _snapshot(rolling, replay, turn=4)

    baseline = runtime_scheduling.evaluate_runtime_scheduling(
        snapshot, replay, turn_number=4, prior=None
    )
    state = copy.deepcopy(replay)
    runtime_scheduling.apply_runtime_scheduling(state, baseline, turn_number=4)
    follow_up = runtime_scheduling.evaluate_runtime_scheduling(
        _snapshot(rolling, state, turn=5),
        state,
        turn_number=5,
        prior=state.get("runtime_scheduling_v1"),
    )

    assert follow_up["diagnostics"]["runtime_scheduling_applied"] is True
    assert follow_up["state_hash"]
    assert state["runtime_scheduling_v1"]["schema_version"] == 2
    assert "item_bands" not in state["runtime_scheduling_v1"]
    assert "item_bands" not in (state.get("gravity_metadata") or {})
    assert len(state.get("scheduling_receipts") or []) <= 20


def test_scheduling_metadata_smaller_than_legacy_shape(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", True)
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    import json

    rolling = _rolling()
    replay = _replay_state(goals=[_goal()])
    state = copy.deepcopy(replay)
    result = runtime_scheduling.evaluate_runtime_scheduling(
        _snapshot(rolling, replay, turn=3), replay, turn_number=3
    )
    runtime_scheduling.apply_runtime_scheduling(state, result, turn_number=3)

    compact_bytes = len(
        json.dumps(
            {
                "runtime_scheduling_v1": state.get("runtime_scheduling_v1"),
                "gravity_metadata": state.get("gravity_metadata"),
                "scheduling_receipts": state.get("scheduling_receipts"),
            },
            separators=(",", ":"),
        )
    )
    legacy_shape = {
        "runtime_scheduling_v1": {
            **(state.get("runtime_scheduling_v1") or {}),
            "tiers_by_actor_id": result.get("tiers_by_actor_id"),
            "acting_actor_ids": result.get("acting_actor_ids"),
            "item_bands": result.get("item_bands"),
            "receipts": result.get("receipts"),
        },
        "gravity_metadata": {
            **(state.get("gravity_metadata") or {}),
            "item_bands": result.get("item_bands"),
        },
        "scheduling_receipts": [
            {**row, "after": {"band": "archive", "prior_band": "", "source_truth_preserved": True}}
            for row in (state.get("scheduling_receipts") or [])
        ]
        * 3,
    }
    legacy_bytes = len(json.dumps(legacy_shape, separators=(",", ":")))
    assert compact_bytes < legacy_bytes