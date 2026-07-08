import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import goal_engine
import replayability
import situation_engine
import utility_ai
import world_state_consumers
from foundation_snapshot import FoundationTurnSnapshot

FIXED_SEED = "world-state-seed"


def _pressure_world_event(event_id, kind, *, location_ids=None, faction_ids=None, turn=4):
    return {
        "event_id": event_id,
        "event_type": "pressure_world_event",
        "pressure_event_kind": kind,
        "pressure_node_id": f"p-{kind}",
        "pressure_kind": "danger",
        "turn": turn,
        "magnitude": 80,
        "location_ids": list(location_ids or []),
        "faction_ids": list(faction_ids or []),
        "actor_ids": [],
        "tags": ["pressure_world_event"],
    }


def _consume_world_events(events, rolling=None, turn=4):
    state = {
        "run_seed": FIXED_SEED,
        "engine_world_events": copy.deepcopy(events),
        "world_state_consumed_event_ids": [],
        "world_state_receipts": [],
    }
    world = copy.deepcopy(rolling or {})
    result = world_state_consumers.consume_pressure_world_events(state, world, turn)
    return state, world, result


def _replay_state(*, situations=None, goals=None):
    return {
        "run_seed": FIXED_SEED,
        "pressure_graph": {"nodes": [], "foreground_node_id": None, "evolution_receipts": []},
        "engine_world_events": [],
        "situations": copy.deepcopy(list(situations or [])),
        "situation_receipts": [],
        "goals": copy.deepcopy(list(goals or [])),
        "goal_receipts": [],
    }


def _goal(
    goal_id="g-trade",
    *,
    goal_type="secure_trade_route",
    target_location_ids=None,
    status="active",
):
    locations = list(target_location_ids or ["dock"])
    return {
        "goal_id": goal_id,
        "owner_type": "settlement",
        "owner_id": locations[0],
        "goal_type": goal_type,
        "title": goal_type.replace("_", " ").title(),
        "status": status,
        "priority": 6,
        "urgency": 6,
        "progress": 0,
        "confidence": 70,
        "created_turn": 1,
        "updated_turn": 1,
        "parent_situation_ids": [],
        "target_actor_ids": [],
        "target_location_ids": locations,
        "required_resources": [],
        "blockers": [],
        "prerequisites": [],
        "evidence_refs": [],
        "expiry": 20,
        "source_event_ids": ["market-trade"],
        "plan_steps": [
            {
                "step_id": "1:trade",
                "order": 0,
                "summary": "Open trade route",
                "status": "active",
                "action_tags": ["trade"],
            }
        ],
        "current_step_index": 0,
        "dedupe_key": f"settlement:{locations[0]}:{goal_type}:{locations[0]}",
    }


def _situation(
    situation_id="s-route",
    *,
    situation_type="bandit_activity",
    location_ids=None,
):
    locations = list(location_ids or ["dock"])
    return {
        "situation_id": situation_id,
        "type": situation_type,
        "title": situation_type.replace("_", " ").title(),
        "status": "active",
        "priority": 6,
        "severity": 6,
        "created_turn": 1,
        "updated_turn": 1,
        "originating_pressure_ids": [],
        "originating_world_event_ids": [],
        "involved_actor_ids": [],
        "involved_locations": locations,
        "involved_factions": [],
        "objectives": ["reopen_route"],
        "blockers": ["blocked_path"],
        "evidence_refs": [],
        "progress": 0,
        "expiry": 20,
        "source_event_ids": ["route-dock"],
        "dedupe_key": f"{situation_type}:location:{locations[0]}",
    }


def _utility_snapshot(*, rolling):
    return FoundationTurnSnapshot.build(
        run_seed=FIXED_SEED,
        turn_sequence=4,
        rolling_state=rolling,
        replayability_state={
            "run_seed": FIXED_SEED,
            "pressure_graph": {"nodes": [], "foreground_node_id": None},
        },
    )


def _candidate(actor_id="g1", action_kind="fortify"):
    return {
        "actor_id": actor_id,
        "action_kind": action_kind,
        "target_kind": "player",
        "target_id": "player",
        "dimension_scores": {k: 50.0 for k in utility_ai.DIMENSION_ORDER},
        "personality_order": ["fortify", "trade", "investigate", "idle"],
    }


def _score_row(result, *, actor_id="g1", action_kind="fortify"):
    for row in result["score_table"]:
        if row["actor_id"] == actor_id and row["action_kind"] == action_kind:
            return row
    raise AssertionError(f"missing score row {actor_id}:{action_kind}")


def test_collapse_event_creates_restore_route_goal_from_world_state():
    _, world, _ = _consume_world_events([
        _pressure_world_event("evt-collapse", "collapse", location_ids=["dock"])
    ])
    state = _replay_state()

    result = goal_engine.evolve_goals(state, world, 4, run_seed=FIXED_SEED)

    restore_goals = [row for row in state["goals"] if row["goal_type"] == "restore_route"]
    assert len(restore_goals) == 1
    goal = restore_goals[0]
    assert goal["target_location_ids"] == ["dock"]
    assert any(ref.startswith("world_state:") for ref in goal["evidence_refs"])
    assert result["receipts"][0]["receipt_type"] == "goal_created"


def test_route_blocked_prefers_fortify_over_trade():
    rolling = {
        "scene": "dock",
        "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "dock"}],
        "travel_routes": [
            {
                "id": "route-dock",
                "location_id": "dock",
                "status": "blocked",
                "conditions": ["route_obstructed"],
            }
        ],
    }
    snapshot = _utility_snapshot(rolling=rolling)
    actor_resolution = {"acting_actor_ids": ["g1"], "tiers_by_actor_id": {"g1": "hero"}}
    candidates = [
        _candidate("g1", action_kind="fortify"),
        _candidate("g1", action_kind="trade"),
    ]

    result = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)

    fortify = _score_row(result, action_kind="fortify")
    trade = _score_row(result, action_kind="trade")
    assert fortify["world_state_modifier"] > 0
    assert trade["world_state_modifier"] < 0
    assert fortify["world_state_signal_ids"]
    assert result["selected_action_kind"] == "fortify"


def test_resource_shortage_creates_food_shortage_situation_from_world_state():
    world = {
        "world_resources": [
            {"id": "food", "status": "shortage", "trend": "decreasing", "quantity_delta": -3}
        ]
    }
    state = _replay_state()

    result = situation_engine.evolve_situations(state, world, 4, run_seed=FIXED_SEED)

    shortages = [row for row in state["situations"] if row["type"] == "food_shortage"]
    assert len(shortages) == 1
    assert any(ref.startswith("world_state:") for ref in shortages[0]["evidence_refs"])
    assert result["receipts"][0]["receipt_type"] == "situation_created"


def test_promoted_situation_includes_world_state_opportunities():
    state = _replay_state(situations=[_situation()])
    rolling = {
        "scene": "dock",
        "travel_routes": [
            {"id": "route-dock", "location_id": "dock", "status": "blocked", "conditions": ["route_obstructed"]}
        ],
    }

    promoted = situation_engine.project_promoted_situations_for_rolling(state, rolling_state=rolling)

    assert len(promoted) == 1
    row = promoted[0]
    assert row["world_state_signals"]
    assert row["world_state_signals"][0]["signal_kind"] == "route_blocked"
    assert "reopen blocked route" in row["world_state_opportunities"]
    assert "reopen blocked route" in row["player_opportunities"]


def test_secure_trade_route_goal_blocked_when_route_blocked():
    state = _replay_state(goals=[_goal()])

    result = goal_engine.evolve_goals(
        state,
        {
            "travel_routes": [
                {"id": "route-dock", "location_id": "dock", "status": "blocked", "conditions": ["route_obstructed"]}
            ]
        },
        4,
        run_seed=FIXED_SEED,
    )

    assert state["goals"][0]["status"] == "blocked"
    assert state["goals"][0]["plan_steps"][0]["status"] == "blocked"
    assert any(receipt["receipt_type"] == "goal_blocked" for receipt in result["receipts"])


def test_world_state_utility_bridge_replay_is_deterministic():
    rolling = {
        "scene": "dock",
        "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "dock"}],
        "travel_routes": [
            {"id": "route-dock", "location_id": "dock", "status": "blocked", "conditions": ["route_obstructed"]}
        ],
        "world_resources": [
            {"id": "food", "status": "shortage", "trend": "decreasing", "quantity_delta": -2, "location_id": "dock"}
        ],
    }
    snapshot = _utility_snapshot(rolling=rolling)
    candidates = [
        _candidate("g1", action_kind="fortify"),
        _candidate("g1", action_kind="gather"),
        _candidate("g1", action_kind="trade"),
    ]
    actor_resolution = {"acting_actor_ids": ["g1"], "tiers_by_actor_id": {"g1": "hero"}}

    first = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)
    second = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)

    assert first == second


def test_world_state_absent_keeps_legacy_utility_scores():
    baseline_rolling = {
        "scene": "dock",
        "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "dock"}],
    }
    unrelated_rolling = {
        "scene": "dock",
        "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "dock"}],
        "travel_routes": [
            {"id": "route-mountain", "location_id": "mountain", "status": "blocked", "conditions": ["route_obstructed"]}
        ],
    }
    actor_resolution = {"acting_actor_ids": ["g1"], "tiers_by_actor_id": {"g1": "hero"}}
    candidates = [_candidate("g1", action_kind="fortify")]

    baseline = utility_ai.select_action(
        candidates,
        snapshot=_utility_snapshot(rolling=baseline_rolling),
        actor_resolution=actor_resolution,
    )
    unrelated = utility_ai.select_action(
        candidates,
        snapshot=_utility_snapshot(rolling=unrelated_rolling),
        actor_resolution=actor_resolution,
    )

    base_row = _score_row(baseline, action_kind="fortify")
    unrelated_row = _score_row(unrelated, action_kind="fortify")
    assert base_row["base_utility"] == unrelated_row["base_utility"] == 50.0
    assert "world_state_modifier" not in base_row
    assert "world_state_modifier" not in unrelated_row


def test_world_state_goals_remain_in_replayability_state():
    _, world, _ = _consume_world_events([
        _pressure_world_event("evt-collapse", "collapse", location_ids=["dock"])
    ])
    state = _replay_state()
    rolling = {"scene": "dock", "npcs": []}

    goal_engine.evolve_goals(state, world, 4, run_seed=FIXED_SEED)
    replayability.enforce_authoritative(rolling, state)

    assert state["goals"]
    assert "goals" not in rolling
    assert rolling["active_goals"]
    assert "goal_id" not in rolling["active_goals"][0]


def test_foundation_snapshot_exposes_world_state_signal_refs():
    rolling = {
        "scene": "dock",
        "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "dock"}],
        "travel_routes": [
            {"id": "route-dock", "location_id": "dock", "status": "blocked", "conditions": ["route_obstructed"]}
        ],
    }
    snapshot = _utility_snapshot(rolling=rolling)

    ref = snapshot.utility_input_refs[0]
    assert "route_blocked" in ref["world_state_signal_kinds"]
    assert ref["world_state_signal_ids"]
    assert snapshot.world_state_ref.get("travel_routes")