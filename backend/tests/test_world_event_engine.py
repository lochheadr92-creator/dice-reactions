import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import memory_retrieval
import pressure_graph
import replayability
import server
import world_event_engine
from foundation_snapshot import FoundationTurnSnapshot

FIXED_SEED = "world-event-seed"


def _pressure_node(node_id="p-food", *, kind="resource", magnitude=70, status="active", actor_ids=None):
    return {
        "id": node_id,
        "kind": kind,
        "status": status,
        "magnitude": magnitude,
        "trend": 1,
        "origin_type": "structured_event",
        "origin_id": node_id,
        "scope": "local",
        "location_ids": ["market"],
        "actor_ids": list(actor_ids or ["g1"]),
        "faction_ids": ["watch"],
        "evidence_refs": [f"pressure:{node_id}"],
        "created_turn": 1,
        "updated_turn": 1,
    }


def _state(*, pressure_nodes=None, world_events=None, situations=None, goals=None, actions=None):
    return {
        "run_seed": FIXED_SEED,
        "pressure_graph": {
            "nodes": copy.deepcopy(list(pressure_nodes or [])),
            "foreground_node_id": None,
            "evolution_receipts": [],
        },
        "engine_world_events": [],
        "world_events": copy.deepcopy(list(world_events or [])),
        "world_event_receipts": [],
        "situations": copy.deepcopy(list(situations or [])),
        "situation_receipts": [],
        "goals": copy.deepcopy(list(goals or [])),
        "goal_receipts": [],
        "npc_actions": copy.deepcopy(list(actions or [])),
        "npc_action_receipts": [],
        "world_state_consumed_event_ids": [],
        "world_state_receipts": [],
        "world_state_guard_receipts": [],
        "transition_receipts": [],
    }


def _world_event(event_id="we-food", *, status="active", progress=0, pressure_ids=None):
    return {
        "world_event_id": event_id,
        "event_type": "resource_shortage",
        "title": "Resource Shortage",
        "severity": 7,
        "status": status,
        "progress": progress,
        "created_turn": 2,
        "updated_turn": 2,
        "originating_pressure_ids": list(pressure_ids or ["p-food"]),
        "originating_situation_ids": [],
        "originating_goal_ids": [],
        "originating_action_ids": [],
        "affected_locations": ["market"],
        "affected_regions": [],
        "affected_factions": ["watch"],
        "affected_actor_ids": ["g1"],
        "evidence_refs": ["pressure:p-food"],
        "expiry": 20,
        "source_event_ids": list(pressure_ids or ["p-food"]),
        "dedupe_key": "resource_shortage:location:market",
        "last_reinforced_turn": 2,
        "inactive_turns": 0,
    }


def test_world_event_creation_is_deterministic_and_duplicate_suppressed():
    state_a = _state(pressure_nodes=[_pressure_node()])
    state_b = copy.deepcopy(state_a)

    result_a = world_event_engine.evolve_world_events(state_a, {}, 3, run_seed=FIXED_SEED)
    result_b = world_event_engine.evolve_world_events(state_b, {}, 3, run_seed=FIXED_SEED)

    assert state_a["world_events"] == state_b["world_events"]
    assert result_a["receipts"] == result_b["receipts"]
    assert result_a["events"] == result_b["events"]
    assert state_a["world_events"][0]["event_type"] == "resource_shortage"
    assert result_a["receipts"][0]["receipt_type"] == "world_event_created"
    assert result_a["events"][0]["event_type"] == "world_event"

    again = world_event_engine.evolve_world_events(state_a, {}, 4, run_seed=FIXED_SEED)
    assert len(state_a["world_events"]) == 1
    assert again["diagnostics"]["world_event_duplicate_suppressed"] >= 1


def test_world_event_merge_resolution_and_archival():
    primary = _world_event("we-primary")
    duplicate = {**_world_event("we-duplicate"), "source_event_ids": ["p-food-2"]}
    state = _state(world_events=[primary, duplicate])

    merge_result = world_event_engine.evolve_world_events(state, {}, 3, run_seed=FIXED_SEED)

    assert any(row["status"] == "resolved" for row in state["world_events"])
    assert any(row["receipt_type"] == "world_event_merged" for row in merge_result["receipts"])

    resolving = _world_event("we-resolve", progress=80)
    resolving["updated_turn"] = 4
    resolving["last_reinforced_turn"] = 4
    resolved_state = _state(
        pressure_nodes=[_pressure_node(status="resolved", magnitude=0)],
        world_events=[resolving],
    )
    resolved = world_event_engine.evolve_world_events(resolved_state, {}, 5, run_seed=FIXED_SEED)
    assert resolved_state["world_events"][0]["status"] == "resolved"
    assert any(row["receipt_type"] == "world_event_resolved" for row in resolved["receipts"])

    archived = world_event_engine.evolve_world_events(resolved_state, {}, 13, run_seed=FIXED_SEED)
    assert resolved_state["world_events"][0]["status"] == "archived"
    assert any(row["receipt_type"] == "world_event_archived" for row in archived["receipts"])


def test_world_events_integrate_with_pressure_consumers_situations_goals_and_npcs():
    state = _state(pressure_nodes=[_pressure_node(kind="resource", magnitude=72)])

    updated, _, diagnostics, _, rolling = replayability.prepare_action_turn(
        state,
        3,
        rolling_state={
            "scene": "market",
            "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "market"}],
        },
    )

    assert diagnostics["world_event_created"] >= 1
    assert updated["world_events"]
    assert any(
        row.get("origin_type") == "world_event"
        for row in updated["pressure_graph"]["nodes"]
    )
    assert updated["world_state_consumed_event_ids"]
    assert updated["situations"]
    assert updated["goals"]
    assert any(row["title"] == "Resource Shortage" for row in rolling["active_world_events"])
    assert all("world_event_id" not in row for row in rolling["active_world_events"])
    assert diagnostics["npc_actions_created"] >= 1
    assert updated["npc_actions"]
    assert rolling["active_npc_actions"]

    updated2, _, diagnostics2, _, rolling2 = replayability.prepare_action_turn(
        updated,
        4,
        rolling_state=rolling,
    )
    assert updated2["npc_actions"]
    assert rolling2["active_npc_actions"]


def test_prompt_safe_foundation_and_memory_retrieval_world_event_cues():
    state = _state(world_events=[_world_event("we-memory")])
    rolling = {
        "scene": "market",
        "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "market"}],
        "npc_memory": [
            {
                "name": "Guard",
                "remembers": [
                    {
                        "summary": "saw the ration line fail",
                        "since_turn": 2,
                        "weight": "major",
                        "context": {"world_event_ids": ["we-memory"]},
                    },
                    {
                        "summary": "unrelated rumour",
                        "since_turn": 2,
                        "weight": "major",
                        "context": {"world_event_ids": ["other"]},
                    },
                ],
            }
        ],
    }
    replayability.enforce_authoritative(rolling, state)
    safe = server._prompt_safe_rolling(
        {
            **rolling,
            "world_events": state["world_events"],
            "world_event_receipts": [{"receipt_id": "hidden"}],
            "active_world_events": [
                {
                    "world_event_id": "hidden",
                    "title": "Resource Shortage",
                    "severity": 7,
                    "status": "active",
                    "source_event_ids": ["p-food"],
                    "diagnostics": {"bad": True},
                }
            ],
        }
    )
    assert "world_events" not in safe
    assert "world_event_receipts" not in safe
    assert "world_event_id" not in safe["active_world_events"][0]
    assert "source_event_ids" not in safe["active_world_events"][0]

    snapshot = FoundationTurnSnapshot.build(
        run_seed=FIXED_SEED,
        turn_sequence=5,
        rolling_state=rolling,
        replayability_state=state,
    )
    assert snapshot.world_event_state_ref["world_events"][0]["world_event_id"] == "we-memory"
    assert "source_event_ids" not in snapshot.world_event_state_ref["world_events"][0]
    ref = snapshot.utility_input_refs[0]
    assert ref["active_world_event_ids"] == ["we-memory"]

    prepared = memory_retrieval.evaluate_memory_retrieval(
        snapshot,
        actor_resolution={"tiers_by_actor_id": {"g1": "hero"}, "acting_actor_ids": ["g1"]},
        gravity={},
        rolling_state=rolling,
    )
    trace = prepared["retrieval_traces"][0]
    assert trace["candidate_count"] == 1
    assert trace["world_event_ids"] == ["we-memory"]
    assert prepared["world_event_context"]["active"][0]["title"] == "Resource Shortage"


def test_pressure_graph_world_event_conversion_is_idempotent():
    graph = pressure_graph.copy_pressure_graph(None)
    event = {
        "event_id": "evt-world-1",
        "event_type": "world_event",
        "world_event_id": "we-pressure",
        "world_event_type": "bandit_activity",
        "world_event_status": "active",
        "magnitude": 70,
        "location_ids": ["market"],
        "actor_ids": ["g1"],
        "faction_ids": ["watch"],
        "source_event_ids": ["p-danger"],
    }

    first = pressure_graph.apply_world_event_engine_events(graph, [event], 3, run_seed=FIXED_SEED)
    second = pressure_graph.apply_world_event_engine_events(graph, [event], 3, run_seed=FIXED_SEED)

    assert len([row for row in graph["nodes"] if row.get("origin_type") == "world_event"]) == 1
    assert first["applied_event_ids"] == ["evt-world-1"]
    assert second["applied_event_ids"] == ["evt-world-1"]
