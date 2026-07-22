import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import goal_engine
import memory_retrieval
import replayability
import server
import utility_ai
from foundation_snapshot import FoundationTurnSnapshot

FIXED_SEED = "goal-seed"


def _situation(
    situation_id="s-food",
    *,
    situation_type="food_shortage",
    status="active",
    priority=7,
    severity=7,
    actor_ids=None,
    location_ids=None,
    faction_ids=None,
):
    return {
        "situation_id": situation_id,
        "type": situation_type,
        "title": situation_type.replace("_", " ").title(),
        "status": status,
        "priority": priority,
        "severity": severity,
        "created_turn": 2,
        "updated_turn": 2,
        "originating_pressure_ids": ["p-food"],
        "originating_world_event_ids": ["evt-food"],
        "involved_actor_ids": list(actor_ids or []),
        "involved_locations": list(location_ids or ["market"]),
        "involved_factions": list(faction_ids or []),
        "objectives": ["secure_supplies"],
        "blockers": ["limited_supplies"],
        "evidence_refs": [f"situation:{situation_id}"],
        "progress": 0,
        "expiry": 20,
        "source_event_ids": [situation_id],
        "dedupe_key": f"{situation_type}:location:{(location_ids or ['market'])[0]}",
    }


def _goal(
    goal_id="g-food",
    *,
    owner_type="settlement",
    owner_id="market",
    goal_type="secure_food",
    status="active",
    priority=7,
    urgency=7,
    progress=0,
    parent_situation_ids=None,
    target_actor_ids=None,
    target_location_ids=None,
    required_resources=None,
    expiry=20,
    dedupe_key=None,
    plan_steps=None,
):
    target_locations = list(target_location_ids or ["market"])
    dedupe = dedupe_key or f"{owner_type}:{owner_id}:{goal_type}:{target_locations[0]}"
    return {
        "goal_id": goal_id,
        "owner_type": owner_type,
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
        "parent_situation_ids": list(parent_situation_ids or ["s-food"]),
        "supporting_pressure_ids": ["p-food"],
        "target_actor_ids": list(target_actor_ids or []),
        "target_location_ids": target_locations,
        "required_resources": list(required_resources or []),
        "blockers": [],
        "prerequisites": [],
        "evidence_refs": [],
        "expiry": expiry,
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
                "step_id": "2:protect",
                "order": 1,
                "summary": "Protect supplies",
                "status": "pending",
                "action_tags": ["protect"],
            },
        ],
        "current_step_index": 0,
        "dedupe_key": dedupe,
    }


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


def _action(receipt_id="move-1", *, npc_id="g1", move_kind="gather", target_id="market"):
    return {
        "receipt_id": receipt_id,
        "npc_id": npc_id,
        "move_kind": move_kind,
        "target_id": target_id,
    }


def test_goal_creation_is_deterministic_from_active_situation():
    state_a = _replay_state(situations=[_situation()])
    state_b = copy.deepcopy(state_a)

    result_a = goal_engine.evolve_goals(state_a, {}, 3, run_seed=FIXED_SEED)
    result_b = goal_engine.evolve_goals(state_b, {}, 3, run_seed=FIXED_SEED)

    assert state_a["goals"] == state_b["goals"]
    assert result_a["receipts"] == result_b["receipts"]
    goal = state_a["goals"][0]
    assert goal["goal_type"] == "secure_food"
    assert goal["owner_type"] == "settlement"
    assert goal["plan_steps"][0]["summary"] == "Assess need"
    assert goal["plan_steps"][0]["status"] == "active"
    assert result_a["receipts"][0]["receipt_type"] == "goal_created"


def test_goal_duplicate_suppression_and_replay_idempotence():
    state = _replay_state(situations=[_situation()])

    first = goal_engine.evolve_goals(state, {}, 3, run_seed=FIXED_SEED)
    second = goal_engine.evolve_goals(state, {}, 3, run_seed=FIXED_SEED)

    active = [row for row in state["goals"] if row["status"] not in {"completed", "failed", "abandoned"}]
    assert len(active) == 1
    assert len(first["receipts"]) == 1
    assert second["receipts"] == []
    assert second["diagnostics"]["goal_duplicate_suppressed"] >= 1


def test_goal_receipt_history_keeps_newest_provenance_window():
    state = _replay_state()
    state["goal_receipts"] = [
        {"receipt_id": f"old-{index}", "source_event_ids": [f"evt-{index}"]}
        for index in range(goal_engine.MAX_GOAL_RECEIPTS)
    ]

    added = goal_engine._append_receipt(
        state,
        [],
        receipt_type="goal_created",
        turn_number=99,
        goal=_goal("g-new"),
        source_event_ids=["evt-new"],
    )

    assert added is True
    assert len(state["goal_receipts"]) == goal_engine.MAX_GOAL_RECEIPTS
    assert state["goal_receipts"][0]["receipt_id"] == "old-1"
    assert state["goal_receipts"][-1]["source_event_ids"] == ["evt-new"]


def test_recreated_goal_after_terminal_history_gets_new_deterministic_id():
    base = _replay_state(situations=[_situation()])
    goal_engine.evolve_goals(base, {}, 3, run_seed=FIXED_SEED)
    terminal_goal = copy.deepcopy(base["goals"][0])
    terminal_goal["status"] = "failed"
    terminal_goal["updated_turn"] = 4
    terminal_goal["expiry"] = 4

    state_a = _replay_state(situations=[_situation()], goals=[terminal_goal])
    state_b = copy.deepcopy(state_a)

    result_a = goal_engine.evolve_goals(state_a, {}, 5, run_seed=FIXED_SEED)
    result_b = goal_engine.evolve_goals(state_b, {}, 5, run_seed=FIXED_SEED)

    ids = [row["goal_id"] for row in state_a["goals"]]
    assert len(ids) == len(set(ids))
    assert state_a["goals"][0]["status"] == "failed"
    assert state_a["goals"][1]["status"] == "active"
    assert state_a["goals"][1]["goal_id"] != terminal_goal["goal_id"]
    assert result_a["diagnostics"]["goal_recreated"] == 1
    assert state_a["goals"] == state_b["goals"]
    assert result_a["receipts"] == result_b["receipts"]


def test_duplicate_goals_merge_deterministically():
    primary = _goal("g-primary", priority=5)
    duplicate = _goal("g-duplicate", priority=9, parent_situation_ids=["s-food-2"])
    state = _replay_state(goals=[duplicate, primary])

    result = goal_engine.evolve_goals(state, {}, 5, run_seed=FIXED_SEED)

    active = [row for row in state["goals"] if row["status"] not in {"completed", "failed", "abandoned"}]
    abandoned = [row for row in state["goals"] if row["status"] == "abandoned"]
    assert len(active) == 1
    assert active[0]["priority"] == 9
    assert abandoned[0]["merged_into"] == active[0]["goal_id"]
    assert any(receipt["receipt_type"] == "goal_merged" for receipt in result["receipts"])


def test_goal_progression_completion_and_replay_idempotence_from_action():
    goal = _goal(
        "g-action",
        owner_type="npc",
        owner_id="g1",
        progress=80,
        parent_situation_ids=[],
        target_location_ids=["market"],
    )
    state = _replay_state(goals=[goal])

    first = goal_engine.evolve_goals(
        state,
        {},
        5,
        run_seed=FIXED_SEED,
        recent_action=_action("move-1", npc_id="g1", move_kind="gather"),
    )
    second = goal_engine.evolve_goals(
        state,
        {},
        5,
        run_seed=FIXED_SEED,
        recent_action=_action("move-1", npc_id="g1", move_kind="gather"),
    )

    assert state["goals"][0]["status"] == "completed"
    assert state["goals"][0]["progress"] == 100
    assert first["receipts"][0]["receipt_type"] == "goal_completed"
    assert second["receipts"] == []


def test_goal_blocked_failed_and_abandoned_paths():
    blocked = _replay_state(goals=[_goal("g-blocked", required_resources=["food"], parent_situation_ids=[])])
    blocked_result = goal_engine.evolve_goals(
        blocked,
        {"world_resources": [{"id": "food", "status": "shortage", "trend": "decreasing"}]},
        4,
        run_seed=FIXED_SEED,
    )
    assert blocked["goals"][0]["status"] == "blocked"
    assert blocked["goals"][0]["plan_steps"][0]["status"] == "blocked"
    assert any(receipt["receipt_type"] == "goal_blocked" for receipt in blocked_result["receipts"])

    failed = _replay_state(goals=[_goal("g-failed", progress=20, parent_situation_ids=[], expiry=4)])
    failed_result = goal_engine.evolve_goals(failed, {}, 4, run_seed=FIXED_SEED)
    assert failed["goals"][0]["status"] == "failed"
    assert any(receipt["receipt_type"] == "goal_failed" for receipt in failed_result["receipts"])

    abandoned = _replay_state(
        situations=[_situation(status="resolved")],
        goals=[_goal("g-abandoned", progress=0, parent_situation_ids=["s-food"])],
    )
    abandoned_result = goal_engine.evolve_goals(abandoned, {}, 6, run_seed=FIXED_SEED)
    assert abandoned["goals"][0]["status"] == "abandoned"
    assert any(receipt["receipt_type"] == "goal_abandoned" for receipt in abandoned_result["receipts"])


def test_goal_projection_and_prompt_safety_hide_internal_metadata():
    state = _replay_state(goals=[_goal("g-safe")])
    projected = goal_engine.project_active_goals_for_rolling(state)
    assert projected == [
        {
            "title": "secure_food".replace("_", " ").title(),
            "status": "active",
            "priority": 7,
            "progress": 0,
            "next_step_summary": "Gather supplies",
        }
    ]

    rolling = {
        "goal_receipts": [{"receipt_id": "hidden"}],
        "active_goals": [
            {
                "goal_id": "hidden",
                "title": "Secure Food",
                "status": "active",
                "priority": 7,
                "progress": 20,
                "next_step_summary": "Gather supplies",
                "source_event_ids": ["hidden"],
                "plan_steps": [{"summary": "hidden"}],
            }
        ],
    }
    safe = server._prompt_safe_rolling(rolling)
    assert "goal_receipts" not in safe
    assert safe["active_goals"][0] == {
        "title": "Secure Food",
        "status": "active",
        "priority": 7,
        "progress": 20,
        "next_step_summary": "Gather supplies",
    }


def test_replayability_enforces_authoritative_goal_projection():
    state = _replay_state(goals=[_goal("g-auth")])
    rolling = {
        "active_goals": [{"goal_id": "model-made", "title": "Wrong", "source_event_ids": ["bad"]}],
        "goals": [{"bad": True}],
        "goal_receipts": [{"bad": True}],
    }

    adjustments = replayability.enforce_authoritative(rolling, state)

    assert "goals" not in rolling
    assert "goal_receipts" not in rolling
    assert rolling["active_goals"][0]["title"] == "Secure Food"
    assert "goal_id" not in rolling["active_goals"][0]
    assert "rolling_active_goals_engine_derived" in adjustments


def test_foundation_snapshot_exposes_bounded_goal_summaries():
    rolling = {"scene": "market", "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "market"}]}
    snapshot = FoundationTurnSnapshot.build(
        run_seed=FIXED_SEED,
        turn_sequence=5,
        rolling_state=rolling,
        replayability_state={
            "run_seed": FIXED_SEED,
            "pressure_graph": {"nodes": []},
            "goals": [_goal("g-foundation", owner_type="npc", owner_id="g1")],
        },
    )
    ref = snapshot.utility_input_refs[0]
    assert ref["active_goal_ids"] == ["g-foundation"]
    assert ref["active_goal_types"] == ["secure_food"]
    assert ref["goal_priority"] == 0.7
    assert ref["goal_owners"] == [{"owner_type": "npc", "owner_id": "g1"}]


def test_utility_ai_goal_modifier_biases_score_without_selecting_directly():
    rolling = {"scene": "market", "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "market"}]}
    snapshot = FoundationTurnSnapshot.build(
        run_seed=FIXED_SEED,
        turn_sequence=5,
        rolling_state=rolling,
        replayability_state={
            "run_seed": FIXED_SEED,
            "pressure_graph": {"nodes": []},
            "goals": [_goal("g-food", owner_type="npc", owner_id="g1", priority=10, urgency=10)],
        },
    )
    actor_resolution = {"acting_actor_ids": ["g1"], "tiers_by_actor_id": {"g1": "hero"}}
    candidate = {
        "actor_id": "g1",
        "action_kind": "gather",
        "target_kind": "location",
        "target_id": "market",
        "dimension_scores": {key: 50.0 for key in utility_ai.DIMENSION_ORDER},
        "personality_order": ["gather", "protect"],
    }
    result = utility_ai.select_action([candidate], snapshot=snapshot, actor_resolution=actor_resolution)
    row = result["score_table"][0]
    assert row["goal_modifier"] == 3.5
    assert row["base_utility"] == 53.5
    assert row["goal_ids"] == ["g-food"]


def test_memory_retrieval_uses_goal_ids_as_bounded_cues():
    rolling = {
        "scene": "market",
        "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "market"}],
        "npc_memory": [
            {
                "name": "Guard",
                "remembers": [
                    {
                        "summary": "knows where food is stored",
                        "since_turn": 2,
                        "weight": "major",
                        "context": {"goal_ids": ["g-food"]},
                    },
                    {
                        "summary": "unrelated old rumor",
                        "since_turn": 2,
                        "weight": "major",
                        "context": {"goal_ids": ["g-other"]},
                    },
                ],
            }
        ],
    }
    snapshot = FoundationTurnSnapshot.build(
        run_seed=FIXED_SEED,
        turn_sequence=5,
        rolling_state=rolling,
        replayability_state={
            "run_seed": FIXED_SEED,
            "pressure_graph": {"nodes": []},
            "goals": [_goal("g-food", owner_type="npc", owner_id="g1")],
        },
    )
    prepared = memory_retrieval.evaluate_memory_retrieval(
        snapshot,
        actor_resolution={"tiers_by_actor_id": {"g1": "hero"}, "acting_actor_ids": ["g1"]},
        gravity={},
        rolling_state=rolling,
    )
    trace = prepared["retrieval_traces"][0]
    assert trace["candidate_count"] == 1
    assert trace["goal_ids"] == ["g-food"]
    assert len(set(prepared["selected_memory_ids"])) == 1


def test_prepare_action_turn_creates_goal_from_existing_situation_projection():
    state = replayability.empty_replayability_state()
    state["run_seed"] = FIXED_SEED
    state["pressure_graph"] = {"nodes": [], "foreground_node_id": None, "evolution_receipts": []}
    state["situations"] = [_situation()]

    updated, _, diagnostics, _, rolling = replayability.prepare_action_turn(
        state,
        4,
        rolling_state={"scene": "market"},
    )

    assert diagnostics["goal_created"] == 1
    assert updated["goals"][0]["goal_type"] == "secure_food"
    assert rolling["active_goals"][0]["title"] == "Earn Enough Food"
    assert "goal_id" not in rolling["active_goals"][0]
