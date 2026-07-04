import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import goal_engine
import memory_retrieval
import npc_action_engine
import pressure_graph
import replayability
import server
import situation_engine
import world_state_consumers
from foundation_snapshot import FoundationTurnSnapshot

FIXED_SEED = "npc-action-seed"


def _goal(
    goal_id="g-food",
    *,
    owner_id="g1",
    goal_type="secure_food",
    status="active",
    priority=7,
    urgency=7,
    progress=0,
    target_location_ids=None,
    target_actor_ids=None,
    supporting_pressure_ids=None,
    blockers=None,
    plan_steps=None,
):
    return {
        "goal_id": goal_id,
        "owner_type": "npc",
        "owner_id": owner_id,
        "goal_type": goal_type,
        "title": goal_type.replace("_", " ").title(),
        "status": status,
        "priority": priority,
        "urgency": urgency,
        "progress": progress,
        "confidence": 70,
        "created_turn": 1,
        "updated_turn": 1,
        "parent_situation_ids": ["s-food"],
        "supporting_pressure_ids": list(supporting_pressure_ids or []),
        "target_actor_ids": list(target_actor_ids or []),
        "target_location_ids": list(["market"] if target_location_ids is None else target_location_ids),
        "required_resources": [],
        "blockers": list(blockers or []),
        "prerequisites": [],
        "evidence_refs": [],
        "expiry": 20,
        "source_event_ids": ["s-food"],
        "plan_steps": plan_steps
        or [
            {
                "step_id": "1:gather",
                "order": 0,
                "summary": "Gather supplies",
                "status": "active",
                "action_tags": ["gather"],
            },
            {
                "step_id": "2:defend",
                "order": 1,
                "summary": "Defend supplies",
                "status": "pending",
                "action_tags": ["protect"],
            },
        ],
        "current_step_index": 0,
        "dedupe_key": f"npc:{owner_id}:{goal_type}:market",
    }


def _replay_state(*, goals=None, situations=None, graph=None):
    return {
        "run_seed": FIXED_SEED,
        "pressure_graph": graph or {"nodes": [], "foreground_node_id": None, "evolution_receipts": []},
        "engine_world_events": [],
        "situations": copy.deepcopy(list(situations or [])),
        "situation_receipts": [],
        "goals": copy.deepcopy(list(goals or [])),
        "goal_receipts": [],
        "npc_actions": [],
        "npc_action_receipts": [],
        "world_state_consumed_event_ids": [],
        "world_state_receipts": [],
    }


def _rolling():
    return {
        "scene": "market",
        "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "market"}],
    }


def _pressure_graph():
    graph = pressure_graph.copy_pressure_graph(None)
    pressure_graph.upsert_pressure_node(
        graph,
        node_id="p-food",
        run_seed=FIXED_SEED,
        kind="resource",
        origin_type="test",
        origin_id="food",
        scope="local",
        magnitude=45,
        trend=0,
        turn_number=1,
        actor_ids=["g1"],
        location_ids=["market"],
        tags=["test"],
    )
    return graph


def test_action_selection_and_event_generation_are_deterministic():
    state_a = _replay_state(goals=[_goal()])
    state_b = copy.deepcopy(state_a)

    result_a = npc_action_engine.evolve_npc_actions(state_a, _rolling(), 3, run_seed=FIXED_SEED)
    result_b = npc_action_engine.evolve_npc_actions(state_b, _rolling(), 3, run_seed=FIXED_SEED)

    assert result_a["actions"] == result_b["actions"]
    assert result_a["events"] == result_b["events"]
    action = result_a["actions"][0]
    event = result_a["events"][0]
    assert action["action_type"] == "gather"
    assert action["outcome"] == "success"
    assert event["event_type"] == "npc_action_event"
    assert event["event_kind"] == "npc_gathered_food"
    assert [row["receipt_type"] for row in result_a["receipts"]] == [
        "npc_action_selected",
        "npc_action_resolved",
        "npc_action_event_generated",
    ]


def test_action_duplicate_suppression_is_replay_idempotent():
    state = _replay_state(goals=[_goal()])

    first = npc_action_engine.evolve_npc_actions(state, _rolling(), 3, run_seed=FIXED_SEED)
    second = npc_action_engine.evolve_npc_actions(state, _rolling(), 3, run_seed=FIXED_SEED)

    assert len(state["npc_actions"]) == 1
    assert len(first["actions"]) == 1
    assert second["actions"] == []
    assert second["events"] == []
    assert second["receipts"] == []
    assert second["diagnostics"]["npc_action_duplicate_suppressed"] == 1


def test_travel_action_updates_actor_location_through_consumers():
    travel_goal = _goal(
        "g-travel",
        goal_type="rescue_missing_person",
        target_location_ids=["safehouse"],
        plan_steps=[
            {
                "step_id": "1:travel",
                "order": 0,
                "summary": "Move toward target",
                "status": "active",
                "action_tags": ["withdraw"],
            }
        ],
    )
    state = _replay_state(goals=[travel_goal])
    rolling = _rolling()

    result = npc_action_engine.evolve_npc_actions(state, rolling, 4, run_seed=FIXED_SEED)
    state["engine_world_events"].extend(result["events"])
    consumed = world_state_consumers.consume_pressure_world_events(state, rolling, 4)

    assert result["actions"][0]["action_type"] == "travel"
    assert consumed["diagnostics"]["world_state_events_consumed"] == 1
    assert rolling["actor_location_registry"][0]["id"] == "g1"
    assert rolling["actor_location_registry"][0]["location_id"] == "safehouse"
    assert rolling["actor_location_registry"][0]["source_event_ids"] == [result["events"][0]["event_id"]]


def test_resource_action_updates_world_resources_through_consumers():
    state = _replay_state(goals=[_goal()])
    rolling = _rolling()

    result = npc_action_engine.evolve_npc_actions(state, rolling, 4, run_seed=FIXED_SEED)
    state["engine_world_events"].extend(result["events"])
    consumed = world_state_consumers.consume_pressure_world_events(state, rolling, 4)

    assert consumed["diagnostics"]["world_state_mutation_count"] >= 1
    resource = rolling["world_resources"][0]
    assert resource["status"] == "improving"
    assert resource["trend"] == "increasing"
    assert resource["quantity_delta"] == 1


def test_prepare_action_turn_reduces_supported_pressure_from_action_event():
    graph = _pressure_graph()
    state = _replay_state(goals=[_goal(supporting_pressure_ids=["p-food"])], graph=graph)
    before = graph["nodes"][0]["magnitude"]

    updated, _, diagnostics, _, rolling = replayability.prepare_action_turn(
        state,
        3,
        rolling_state=_rolling(),
    )

    node = next(row for row in updated["pressure_graph"]["nodes"] if row["id"] == "p-food")
    assert node["magnitude"] < before
    assert updated["npc_actions"][0]["outcome"] == "success"
    assert any(row["event_type"] == "npc_action_event" for row in updated["engine_world_events"])
    assert diagnostics["npc_action_engine_events_appended"] == 1
    assert rolling["active_npc_actions"][0]["current_action"] == "gather"


def test_action_event_can_seed_situation_without_llm_authority():
    event = {
        "event_type": "npc_action_event",
        "event_kind": "npc_found_clue",
        "event_id": "evt-clue",
        "actor_ids": ["g1"],
        "location_ids": ["market"],
        "turn": 4,
        "magnitude": 60,
    }
    state = _replay_state()
    state["engine_world_events"] = [event]

    result = situation_engine.evolve_situations(state, _rolling(), 4, run_seed=FIXED_SEED)

    assert result["diagnostics"]["situation_created"] == 1
    assert state["situations"][0]["type"] == "murder_investigation"
    assert state["situations"][0]["originating_world_event_ids"] == ["evt-clue"]


def test_successful_action_progresses_and_completes_goal_in_prepare_turn():
    state = _replay_state(goals=[_goal("g-complete", progress=80)])

    updated, _, diagnostics, _, rolling = replayability.prepare_action_turn(
        state,
        3,
        rolling_state=_rolling(),
    )

    completed = next(row for row in updated["goals"] if row["goal_id"] == "g-complete")
    assert completed["status"] == "completed"
    assert completed["progress"] == 100
    assert diagnostics["goal_completed"] >= 1
    assert rolling["active_npc_actions"][0]["progress"] == 100


def test_failed_search_action_does_not_progress_goal():
    failing_goal = _goal(
        "g-failed-search",
        goal_type="rescue_missing_person",
        target_location_ids=[],
        blockers=["uncertain_location"],
        plan_steps=[
            {
                "step_id": "1:search",
                "order": 0,
                "summary": "Search likely area",
                "status": "active",
                "action_tags": ["investigate"],
            }
        ],
    )
    state = _replay_state(goals=[failing_goal])

    action_result = npc_action_engine.evolve_npc_actions(state, {"npcs": [{"name": "Guard", "npc_id": "g1"}]}, 3, run_seed=FIXED_SEED)
    recent = npc_action_engine.latest_action_for_goal_engine(action_result["actions"])
    goal_result = goal_engine.evolve_goals(state, {}, 3, run_seed=FIXED_SEED, recent_action=recent)

    assert action_result["actions"][0]["outcome"] == "failure"
    assert recent is None
    assert state["goals"][0]["progress"] == 0
    assert not any(row["receipt_type"] == "goal_progressed" for row in goal_result["receipts"])


def test_foundation_memory_and_prompt_projections_are_bounded_and_clean():
    state = _replay_state(goals=[_goal("g-memory")])
    action_result = npc_action_engine.evolve_npc_actions(state, _rolling(), 5, run_seed=FIXED_SEED)
    action_id = action_result["actions"][0]["action_id"]
    state["npc_actions"] = action_result["actions"]
    rolling = _rolling()
    rolling["npc_memory"] = [
        {
            "name": "Guard",
            "remembers": [
                {
                    "summary": "found food by the old market",
                    "since_turn": 4,
                    "weight": "major",
                    "context": {"action_ids": [action_id], "action_type": "gather"},
                },
                {
                    "summary": "unrelated patrol",
                    "since_turn": 4,
                    "weight": "major",
                    "context": {"action_ids": ["other-action"]},
                },
            ],
        }
    ]

    snapshot = FoundationTurnSnapshot.build(
        run_seed=FIXED_SEED,
        turn_sequence=6,
        rolling_state=rolling,
        replayability_state=state,
    )
    ref = snapshot.utility_input_refs[0]
    assert ref["current_action"] == "gather"
    assert ref["last_action"] == "gather"
    assert ref["destination"] == "market"

    prepared = memory_retrieval.evaluate_memory_retrieval(
        snapshot,
        actor_resolution={"tiers_by_actor_id": {"g1": "hero"}, "acting_actor_ids": ["g1"]},
        gravity={},
        rolling_state=rolling,
    )
    trace = prepared["retrieval_traces"][0]
    assert trace["candidate_count"] == 1
    assert trace["action_ids"] == [action_id]

    unsafe = {
        "npc_actions": state["npc_actions"],
        "npc_action_receipts": [{"receipt_id": "hidden"}],
        "active_npc_actions": [
            {
                "action_id": action_id,
                "source_event_ids": ["hidden"],
                "internal_score": 99,
                "current_action": "gather",
                "destination": "market",
                "goal_title": "Secure Food",
                "progress": 20,
                "status": "active",
            }
        ],
    }
    safe = server._prompt_safe_rolling(unsafe)
    assert "npc_actions" not in safe
    assert "npc_action_receipts" not in safe
    assert safe["active_npc_actions"] == [
        {
            "current_action": "gather",
            "destination": "market",
            "goal_title": "Secure Food",
            "progress": 20,
            "status": "active",
        }
    ]
