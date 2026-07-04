import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import memory_retrieval
import replayability
import server
import situation_engine
import utility_ai
from foundation_snapshot import FoundationTurnSnapshot

FIXED_SEED = "situation-seed"


def _pressure_node(
    node_id="p-food",
    *,
    kind="resource",
    magnitude=70,
    status="active",
    location_ids=None,
    actor_ids=None,
    faction_ids=None,
):
    return {
        "id": node_id,
        "kind": kind,
        "status": status,
        "magnitude": magnitude,
        "trend": 1,
        "origin_type": "structured_event",
        "origin_id": node_id,
        "scope": "local",
        "location_ids": list(location_ids or ["market"]),
        "actor_ids": list(actor_ids or []),
        "faction_ids": list(faction_ids or []),
        "evidence_refs": [f"pressure:{node_id}"],
    }


def _replay_state(*, pressure_nodes=None, world_events=None, situations=None, receipts=None):
    return {
        "run_seed": FIXED_SEED,
        "pressure_graph": {
            "nodes": list(pressure_nodes or []),
            "foreground_node_id": None,
            "evolution_receipts": list(receipts or []),
        },
        "engine_world_events": list(world_events or []),
        "situations": copy.deepcopy(list(situations or [])),
        "situation_receipts": [],
    }


def _world_event(event_id="evt-raid", *, kind="raid", location_ids=None, faction_ids=None, actor_ids=None):
    return {
        "event_id": event_id,
        "event_type": "pressure_world_event",
        "pressure_event_kind": kind,
        "pressure_node_id": "p-conflict",
        "pressure_kind": "conflict",
        "turn": 4,
        "magnitude": 80,
        "location_ids": list(location_ids or ["docks"]),
        "faction_ids": list(faction_ids or ["watch"]),
        "actor_ids": list(actor_ids or []),
    }


def _situation(
    situation_id="s1",
    *,
    situation_type="food_shortage",
    dedupe_key="food_shortage:location:market",
    status="active",
    severity=4,
    progress=0,
    source_event_ids=None,
    pressure_ids=None,
):
    return {
        "situation_id": situation_id,
        "type": situation_type,
        "title": "Food Shortage",
        "status": status,
        "priority": severity,
        "severity": severity,
        "created_turn": 1,
        "updated_turn": 1,
        "originating_pressure_ids": list(pressure_ids or ["p-food"]),
        "originating_world_event_ids": [],
        "involved_actor_ids": [],
        "involved_locations": ["market"],
        "involved_factions": [],
        "objectives": ["secure_supplies"],
        "blockers": ["limited_supplies"],
        "evidence_refs": [],
        "progress": progress,
        "expiry": 20,
        "source_event_ids": list(source_event_ids or ["p-food"]),
        "dedupe_key": dedupe_key,
    }


def test_situation_creation_is_deterministic_from_pressure():
    state_a = _replay_state(pressure_nodes=[_pressure_node()])
    state_b = copy.deepcopy(state_a)

    result_a = situation_engine.evolve_situations(state_a, {}, 3, run_seed=FIXED_SEED)
    result_b = situation_engine.evolve_situations(state_b, {}, 3, run_seed=FIXED_SEED)

    assert state_a["situations"] == state_b["situations"]
    assert result_a["receipts"] == result_b["receipts"]
    situation = state_a["situations"][0]
    assert situation["type"] == "food_shortage"
    assert situation["status"] == "active"
    assert situation["source_event_ids"] == ["p-food"]
    assert result_a["receipts"][0]["receipt_type"] == "situation_created"


def test_duplicate_pressure_and_replay_do_not_create_duplicate_situations():
    state = _replay_state(
        pressure_nodes=[
            _pressure_node("p-food-a"),
            _pressure_node("p-food-b"),
        ]
    )

    first = situation_engine.evolve_situations(state, {}, 3, run_seed=FIXED_SEED)
    second = situation_engine.evolve_situations(state, {}, 3, run_seed=FIXED_SEED)

    active = [row for row in state["situations"] if row["status"] not in {"resolved", "failed"}]
    assert len(active) == 1
    assert len(first["receipts"]) <= 2
    assert second["receipts"] == []
    assert second["diagnostics"]["situation_duplicate_suppressed"] >= 1


def test_duplicate_situations_merge_deterministically():
    primary = _situation("s-primary")
    duplicate = _situation("s-duplicate", severity=6, source_event_ids=["p-food-2"], pressure_ids=["p-food-2"])
    state = _replay_state(situations=[duplicate, primary])

    result = situation_engine.evolve_situations(state, {}, 5, run_seed=FIXED_SEED)

    active = [row for row in state["situations"] if row["status"] not in {"resolved", "failed"}]
    resolved = [row for row in state["situations"] if row["status"] == "resolved"]
    assert len(active) == 1
    assert active[0]["severity"] == 6
    assert resolved[0]["merged_into"] == active[0]["situation_id"]
    assert any(receipt["receipt_type"] == "situation_merged" for receipt in result["receipts"])


def test_situation_progresses_decays_and_resolves_from_structured_state():
    resolved_pressure = _pressure_node(status="resolved", magnitude=0)
    receipt = {"receipt_type": "pressure_resolved", "turn": 6, "node_id": "p-food"}
    state = _replay_state(
        pressure_nodes=[resolved_pressure],
        situations=[_situation(severity=1, progress=80)],
        receipts=[receipt],
    )

    result = situation_engine.evolve_situations(state, {}, 6, run_seed=FIXED_SEED)

    assert state["situations"][0]["status"] == "resolved"
    assert state["situations"][0]["progress"] == 100
    assert any(receipt["receipt_type"] == "situation_resolved" for receipt in result["receipts"])

    decaying = _replay_state(
        pressure_nodes=[],
        situations=[
            {
                **_situation("s-decay", severity=2, progress=10, pressure_ids=[]),
                "inactive_turns": 1,
                "dedupe_key": "food_shortage:location:market",
            }
        ],
    )
    decay_result = situation_engine.evolve_situations(decaying, {}, 7, run_seed=FIXED_SEED)
    assert decaying["situations"][0]["status"] == "resolving"
    assert decaying["situations"][0]["severity"] == 1
    assert any(receipt["receipt_type"] == "situation_decayed" for receipt in decay_result["receipts"])


def test_replayability_projects_active_situations_and_strips_model_authorship():
    state = _replay_state(situations=[_situation("s-auth", severity=7)])
    rolling = {
        "scene": "market",
        "active_situations": [{"situation_id": "model-made", "source_event_ids": ["bad"]}],
        "situations": [{"bad": True}],
        "situation_receipts": [{"bad": True}],
    }

    adjustments = replayability.enforce_authoritative(rolling, state)

    assert "situations" not in rolling
    assert "situation_receipts" not in rolling
    assert rolling["active_situations"][0]["situation_id"] == "s-auth"
    assert "source_event_ids" not in rolling["active_situations"][0]
    assert "rolling_active_situations_engine_derived" in adjustments


def test_prompt_safe_projection_hides_situation_receipts_and_metadata():
    rolling = {
        "scene": "market",
        "situation_receipts": [{"receipt_id": "hidden"}],
        "active_situations": [
            {
                "situation_id": "s1",
                "title": "Food Shortage",
                "status": "active",
                "severity": 5,
                "source_event_ids": ["evt-hidden"],
                "updated_turn": 3,
            }
        ],
    }

    safe = server._prompt_safe_rolling(rolling)

    assert "situation_receipts" not in safe
    assert safe["active_situations"][0]["situation_id"] == "s1"
    assert "source_event_ids" not in safe["active_situations"][0]
    assert "updated_turn" not in safe["active_situations"][0]


def test_utility_ai_situation_modifier_is_bounded_and_absent_keeps_legacy_score():
    rolling = {"scene": "market", "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "market"}]}
    actor_resolution = {"acting_actor_ids": ["g1"], "tiers_by_actor_id": {"g1": "hero"}}
    candidate = {
        "actor_id": "g1",
        "action_kind": "gather",
        "target_kind": "location",
        "target_id": "market",
        "dimension_scores": {key: 50.0 for key in utility_ai.DIMENSION_ORDER},
        "personality_order": ["gather", "protect", "investigate"],
    }
    baseline_snapshot = FoundationTurnSnapshot.build(
        run_seed=FIXED_SEED,
        turn_sequence=4,
        rolling_state=rolling,
        replayability_state={"run_seed": FIXED_SEED, "pressure_graph": {"nodes": []}},
    )
    situation_snapshot = FoundationTurnSnapshot.build(
        run_seed=FIXED_SEED,
        turn_sequence=4,
        rolling_state=rolling,
        replayability_state={
            "run_seed": FIXED_SEED,
            "pressure_graph": {"nodes": []},
            "situations": [_situation("s-food", severity=10)],
        },
    )

    baseline = utility_ai.select_action([candidate], snapshot=baseline_snapshot, actor_resolution=actor_resolution)
    modified = utility_ai.select_action([candidate], snapshot=situation_snapshot, actor_resolution=actor_resolution)

    base_row = baseline["score_table"][0]
    modified_row = modified["score_table"][0]
    assert base_row["base_utility"] == 50.0
    assert "situation_modifier" not in base_row
    assert modified_row["situation_modifier"] == 3.0
    assert modified_row["base_utility"] == 53.0
    assert modified_row["situation_ids"] == ["s-food"]


def test_memory_retrieval_uses_situation_ids_as_bounded_cues():
    rolling = {
        "scene": "market",
        "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "market"}],
        "npc_memory": [
            {
                "name": "Guard",
                "remembers": [
                    {
                        "summary": "saw the supply room empty",
                        "since_turn": 2,
                        "weight": "major",
                        "context": {"situation_ids": ["s-food"]},
                    },
                    {
                        "summary": "unrelated old rumor",
                        "since_turn": 2,
                        "weight": "major",
                        "context": {"situation_ids": ["s-other"]},
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
            "situations": [_situation("s-food", severity=7)],
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
    assert trace["situation_ids"] == ["s-food"]
    assert len(set(prepared["selected_memory_ids"])) == 1


def test_prepare_action_turn_creates_world_event_situation_projection():
    state = replayability.empty_replayability_state()
    state["run_seed"] = FIXED_SEED
    state["pressure_graph"] = {"nodes": [], "foreground_node_id": None, "evolution_receipts": []}
    state["engine_world_events"] = [_world_event("evt-raid", kind="raid")]

    updated, _, diagnostics, _, rolling = replayability.prepare_action_turn(
        state,
        4,
        rolling_state={"scene": "docks"},
    )

    assert diagnostics["situation_created"] == 1
    assert updated["situations"][0]["type"] == "gang_turf_war"
    assert rolling["active_situations"][0]["type"] == "gang_turf_war"
    assert "source_event_ids" not in rolling["active_situations"][0]
