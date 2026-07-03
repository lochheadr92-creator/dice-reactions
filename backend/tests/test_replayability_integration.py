"""
Replayability Engine v1 — integration tests (spec items 65–80).
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from starlette.testclient import TestClient

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import gateway  # noqa: E402
import npc_world_moves as world_moves  # noqa: E402
import opening_state  # noqa: E402
import player_api  # noqa: E402
import pressure_graph  # noqa: E402
import replayability  # noqa: E402
import server  # noqa: E402
import world_state_consumers  # noqa: E402
from memory import enforce_context_budget  # noqa: E402
from security import DEVICE_ID_HEADER  # noqa: E402

TEST_DEVICE = "replayability-test-device"
FIXED_SEED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-replayability")


def _run_db(coro):
    async def wrapper():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        orig = server.db
        server.db = client[os.environ["DB_NAME"]]
        try:
            return await coro
        finally:
            server.db = orig
            client.close()

    return asyncio.run(wrapper())


def _opening_response() -> str:
    return (
        "<narrative>You step into the rain.</narrative>"
        "<paragraphs><p>You step into the rain.</p></paragraphs>"
        "<choices>A. Move\nB. Wait\nC. Listen\nD. Speak</choices>"
        "<state><Health>stable</Health><Pressure>deadline closing</Pressure></state>"
        "<ledger><Carried>torch</Carried></ledger>"
        '<rolling_state>{"active_pressures":["rain"],"objectives":["escape"],"replayability_identity":{"bad":true}}</rolling_state>'
    )


def _action_response() -> str:
    return (
        "<narrative>You steady yourself.</narrative>"
        "<paragraphs><p>You steady yourself.</p></paragraphs>"
        "<choices>A. Continue\nB. Wait\nC. Listen\nD. Move</choices>"
        "<state><Health>stable</Health><Pressure>steady</Pressure></state>"
        "<ledger><Carried>torch</Carried></ledger>"
        '<rolling_state>{"pressure_graph":{"nodes":[]}}</rolling_state>'
    )


# 65–68: init + state container
def test_init_new_story_returns_state_and_directives():
    state, directives = replayability.init_new_story(
        genre="noir",
        role="detective",
        tone="gritty",
        difficulty="standard",
        scenario_id=None,
        custom_premise="",
        custom_world_setup={},
        run_seed=FIXED_SEED,
    )
    assert state["run_seed"] == FIXED_SEED
    assert state["identity"]
    assert state["opening"]["archetype_id"]
    assert directives["opening"]
    assert opening_state.OPENING_DIRECTIVE_MARKER in directives["opening"]


def test_init_new_story_seeds_pressure_from_structured_setup_only():
    state, _ = replayability.init_new_story(
        genre="custom-world",
        role="courier",
        tone="grim",
        difficulty="standard",
        scenario_id=None,
        custom_premise="",
        custom_world_setup={
            "danger": "flood sirens trigger stampedes",
            "pressures": ["scarcity", "civil unrest"],
        },
        run_seed=FIXED_SEED,
    )

    nodes = state["pressure_graph"]["nodes"]
    custom_nodes = [node for node in nodes if node.get("origin_type") == "custom_setup"]
    assert any(node.get("origin_id") == "danger" for node in custom_nodes)
    assert any(node.get("origin_id") == "pressure:0" for node in custom_nodes)
    assert all(node.get("evidence_refs") for node in custom_nodes)


def test_init_uses_transition_receipts_not_engine_events():
    state, _ = replayability.init_new_story(
        genre="fantasy", role="mage", tone="epic", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=FIXED_SEED,
    )
    assert "engine_events" not in state
    assert state.get("transition_receipts")
    assert state["transition_receipts"][0]["receipt_type"] == "echo_scheduled"
    for _ in range(40):
        replayability._append_transition_receipt(
            state, source_event_id=f"evt-{_}", receipt_type="echo_scheduled", turn_number=1
        )
    assert len(state["transition_receipts"]) <= replayability.TRANSITION_RECEIPTS_MAX


def test_prepare_action_turn_ticks_pressure_and_returns_directives():
    state, _ = replayability.init_new_story(
        genre="horror", role="survivor", tone="dark", difficulty="hard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=FIXED_SEED,
    )
    updated, directives, diag, _, _ = replayability.prepare_action_turn(state, 2)
    assert updated["pressure_graph"]["tick"] >= 1
    assert directives["opening"] == ""
    assert directives["pressure"]


def test_prepare_action_turn_passthrough_without_state():
    updated, directives, diag, _, _ = replayability.prepare_action_turn(None, 2)
    assert updated == {}
    assert directives == {"opening": "", "world": "", "pressure": "", "echo": ""}
    assert diag == {}


# 69–72: Policy A + enforcement
def test_turn_debug_history_includes_utility_ai_live_selection_evidence():
    debug = server._meta_into_debug(
        None,
        {
            "replayability_utility_ai_live_selection_enabled": True,
            "replayability_utility_ai_live_selection_applied": False,
            "replayability_utility_ai_selected_live_winner_source": "heuristic",
            "replayability_utility_ai_shadow_comparison": {"scores": [1]},
        },
    )

    assert debug["replayability_utility_ai_live_selection_enabled"] == "True"
    assert debug["replayability_utility_ai_live_selection_applied"] == "False"
    assert debug["replayability_utility_ai_selected_live_winner_source"] == "heuristic"
    assert "replayability_utility_ai_shadow_comparison" not in debug


def test_replayability_active_requires_run_seed():
    assert not replayability.replayability_active({})
    assert not replayability.replayability_active({"replayability_state": {}})
    assert replayability.replayability_active({"replayability_state": {"run_seed": FIXED_SEED}})


def test_strip_replayability_from_rolling_removes_engine_keys():
    rolling = {
        "scene": "alley",
        "replayability_identity": {"x": 1},
        "pressure_graph": {"nodes": []},
        "run_seed": FIXED_SEED,
    }
    stripped = replayability.strip_replayability_from_rolling(rolling)
    assert "replayability_identity" not in rolling
    assert "pressure_graph" not in rolling
    assert "run_seed" not in rolling
    assert stripped


def test_enforce_authoritative_strips_model_replayability_fields():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=FIXED_SEED,
    )
    rolling = {"pressure_graph": copy.deepcopy(state["pressure_graph"]), "scene": "dock"}
    tampered = rolling["pressure_graph"]["nodes"][0]
    tampered_id = tampered["id"]
    tampered["magnitude"] = 99
    tampered["trend"] = 1
    adj = replayability.enforce_authoritative(rolling, state)
    projected = {node["id"]: node for node in rolling["pressure_graph"]["nodes"]}
    authoritative = {node["id"]: node for node in state["pressure_graph"]["nodes"]}
    assert projected[tampered_id]["magnitude"] == authoritative[tampered_id]["magnitude"]
    assert projected[tampered_id]["trend"] == authoritative[tampered_id]["trend"]
    assert "rolling_pressure_graph_engine_derived" in adj
    assert adj


@pytest.mark.parametrize("phrase", [
    "I think about stealing the key.",
    "I pretend I rescued them.",
    "I promise nothing.",
    "Did someone attack the merchant?",
    "I tell them I abandoned nobody.",
])
def test_raw_player_phrases_create_no_echo_events(phrase):
    assert replayability.structured_events_from_action(phrase) == []
    sources = replayability.collect_qualifying_echo_sources(
        prior_rolling={},
        merged_rolling={},
        turn_number=2,
        guard_adjustments=[],
    )
    assert sources == []


def test_genuine_structured_event_creates_exactly_one_echo():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=FIXED_SEED,
    )
    sources = [{
        "source_kind": "delayed_consequence_fired",
        "source_event_id": "evt-delayed-0-turn-2",
        "echo_kind": "delayed_consequence",
        "label": "debt collector arrives",
    }]
    once = replayability.finalize_action_turn(state, sources, 2)
    twice = replayability.finalize_action_turn(once, sources, 2)
    scheduled = twice["consequence_echoes"]["scheduled"]
    assert len([e for e in scheduled if e.get("source_event_id") == "evt-delayed-0-turn-2"]) == 1


def test_pressure_threshold_references_canonical_event_id():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=FIXED_SEED,
    )
    node = state["pressure_graph"]["nodes"][0]
    node["trend"] = 1
    node["magnitude"] = 68
    node["threshold"] = 70
    updated, _, _, thresholds, _ = replayability.prepare_action_turn(state, 2)
    assert thresholds
    assert thresholds[0]["event_id"]
    scheduled = updated["consequence_echoes"]["scheduled"]
    assert any(e.get("source_event_id") == thresholds[0]["event_id"] for e in scheduled)


def _state_with_high_pressure():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=FIXED_SEED,
    )
    state["pressure_graph"]["nodes"] = [
        {
            "id": "p-danger-world",
            "kind": "danger",
            "origin_type": "structured_event",
            "origin_id": "evt-danger-world",
            "origin": {"type": "structured_event", "id": "evt-danger-world"},
            "scope": "local",
            "status": "active",
            "magnitude": 80,
            "trend": 1,
            "trend_label": "rising",
            "actor_ids": [],
            "location_ids": ["dock"],
            "faction_ids": [],
            "tags": [],
            "linked_node_ids": [],
            "linked_pressure_ids": [],
            "created_turn": 1,
            "updated_turn": 1,
            "last_foreground_turn": None,
            "threshold": 95,
            "last_threshold": "below",
            "evidence_refs": ["evt-danger-world"],
            "label": "dock danger",
        }
    ]
    state["pressure_graph"]["foreground_node_id"] = "p-danger-world"
    state["pressure_graph"]["threshold_crossings"] = []
    state["pressure_graph"]["evolution_receipts"] = []
    state["engine_world_events"] = []
    return state


def test_prepare_action_turn_records_pressure_world_event_and_receipts():
    state = _state_with_high_pressure()

    updated, _, diag, _, working_rolling = replayability.prepare_action_turn(
        state,
        3,
        rolling_state={"scene": "dock"},
    )

    events = updated["engine_world_events"]
    assert len(events) == 1
    assert events[0]["event_type"] == "pressure_world_event"
    assert events[0]["pressure_node_id"] == "p-danger-world"
    assert "engine_world_events" not in working_rolling
    assert working_rolling["locations"][0]["id"] == "dock"
    assert working_rolling["locations"][0]["status"] == "unstable"
    assert diag["pressure_spawned_events"] == 1
    assert diag["world_state_events_consumed"] == 1
    receipt_types = {r["receipt_type"] for r in updated["pressure_graph"]["evolution_receipts"]}
    assert {"pressure_escalated", "pressure_spawned_event"} <= receipt_types
    assert any(r["receipt_type"] == "location_updated" for r in updated["world_state_receipts"])
    assert any(
        r.get("receipt_type") == "pressure_spawned_event"
        and r.get("source_event_id") == events[0]["event_id"]
        for r in updated["transition_receipts"]
    )


def test_pressure_world_event_replay_is_deterministic():
    state = _state_with_high_pressure()
    a, _, _, _, _ = replayability.prepare_action_turn(copy.deepcopy(state), 3, rolling_state={"scene": "dock"})
    b, _, _, _, _ = replayability.prepare_action_turn(copy.deepcopy(state), 3, rolling_state={"scene": "dock"})

    assert a["engine_world_events"] == b["engine_world_events"]
    assert a["pressure_graph"] == b["pressure_graph"]
    assert a["transition_receipts"] == b["transition_receipts"]


def _pressure_world_event(event_id, kind, *, location_ids=None, faction_ids=None, actor_ids=None, turn=3):
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
        "actor_ids": list(actor_ids or []),
        "tags": ["pressure_world_event"],
    }


def _consume_world_events(events, rolling=None, turn=3):
    state = {
        "run_seed": FIXED_SEED,
        "engine_world_events": copy.deepcopy(events),
        "world_state_consumed_event_ids": [],
        "world_state_receipts": [],
    }
    world = copy.deepcopy(rolling or {})
    result = world_state_consumers.consume_pressure_world_events(state, world, turn)
    return state, world, result


def test_world_state_consumer_bridge_collapse_updates_location():
    state, world, result = _consume_world_events([
        _pressure_world_event("evt-collapse", "collapse", location_ids=["bridge-east"])
    ])

    assert result["diagnostics"]["world_state_events_consumed"] == 1
    assert world["locations"][0]["id"] == "bridge-east"
    assert world["locations"][0]["status"] == "blocked"
    assert "collapsed" in world["locations"][0]["conditions"]
    assert world["infrastructure_state"][0]["status"] == "damaged"
    assert world["travel_routes"][0]["status"] == "blocked"
    receipt_types = {receipt["receipt_type"] for receipt in state["world_state_receipts"]}
    assert {"location_updated", "infrastructure_changed", "travel_network_changed"} <= receipt_types


def test_world_state_consumer_raid_changes_structured_resources():
    state, world, result = _consume_world_events([
        _pressure_world_event("evt-raid", "raid", location_ids=["market"], faction_ids=["watch"])
    ])

    assert result["diagnostics"]["world_state_mutation_count"] == 3
    assert world["world_resources"][0]["quantity_delta"] == -2
    assert world["world_resources"][0]["trend"] == "decreasing"
    faction = world["faction_pressure"][0]
    assert faction["id"] == "watch"
    assert faction["ticks"]["security"] == -1
    receipt_types = {receipt["receipt_type"] for receipt in state["world_state_receipts"]}
    assert {"resource_changed", "faction_changed", "settlement_changed"} <= receipt_types


def test_world_state_consumer_trader_arrival_updates_market_state():
    state, world, result = _consume_world_events([
        _pressure_world_event("evt-trader", "trader_arrival", location_ids=["market"])
    ])

    assert result["diagnostics"]["world_state_events_consumed"] == 1
    assert world["world_resources"][0]["quantity_delta"] == 2
    assert world["world_resources"][0]["trend"] == "increasing"
    assert world["market_state"][0]["status"] == "active"
    assert "trader_arrived" in world["market_state"][0]["conditions"]


def test_world_state_consumer_duplicate_replay_ignored():
    event = _pressure_world_event("evt-raid", "raid", location_ids=["market"], faction_ids=["watch"])
    state, world, first = _consume_world_events([event])
    receipts_after_first = copy.deepcopy(state["world_state_receipts"])
    resources_after_first = copy.deepcopy(world["world_resources"])

    second = world_state_consumers.consume_pressure_world_events(state, world, 3)

    assert first["diagnostics"]["world_state_events_consumed"] == 1
    assert second["diagnostics"]["world_state_replay_suppressed"] == 1
    assert state["world_state_receipts"] == receipts_after_first
    assert world["world_resources"] == resources_after_first


def test_world_state_consumer_unrelated_event_ignored():
    state, world, result = _consume_world_events([
        {"event_id": "evt-other", "event_type": "npc_move", "turn": 3}
    ])

    assert result["diagnostics"]["world_state_consumer_executed"] is False
    assert result["diagnostics"]["world_state_mutation_count"] == 0
    assert state["world_state_consumed_event_ids"] == []
    assert world == {}


def test_world_state_consumer_missing_target_handled_safely():
    state, world, result = _consume_world_events([
        _pressure_world_event("evt-collapse-missing", "collapse")
    ])

    assert result["diagnostics"]["world_state_events_consumed"] == 1
    assert result["diagnostics"]["world_state_skipped_mutations"] == 1
    assert state["world_state_consumed_event_ids"] == ["evt-collapse-missing"]
    assert state["world_state_receipts"] == []
    assert world == {}


def test_world_state_consumer_multiple_events_are_deterministic():
    events = [
        _pressure_world_event("evt-trader", "trader_arrival", location_ids=["market"]),
        _pressure_world_event("evt-raid", "raid", location_ids=["market"], faction_ids=["watch"]),
    ]

    first_state, first_world, first_result = _consume_world_events(events)
    second_state, second_world, second_result = _consume_world_events(events)

    assert first_world == second_world
    assert first_state["world_state_receipts"] == second_state["world_state_receipts"]
    assert first_result == second_result


def test_world_state_consumer_duplicate_event_in_history_suppressed():
    event = _pressure_world_event("evt-raid", "raid", location_ids=["market"])
    state, world, result = _consume_world_events([event, dict(event)])

    assert result["diagnostics"]["world_state_events_consumed"] == 1
    assert result["diagnostics"]["world_state_duplicate_suppressed"] == 1
    assert world["world_resources"][0]["quantity_delta"] == -2
    assert state["world_state_consumed_event_ids"] == ["evt-raid"]


def test_world_state_consumer_mutations_remain_bounded():
    state, world, result = _consume_world_events([
        _pressure_world_event("evt-collapse", "collapse", location_ids=["bridge-east"])
    ])

    assert result["diagnostics"]["world_state_mutation_count"] <= (
        world_state_consumers.MAX_WORLD_STATE_MUTATIONS_PER_EVENT
    )
    assert len(state["world_state_receipts"]) <= world_state_consumers.MAX_WORLD_STATE_MUTATIONS_PER_EVENT


def test_world_state_consumer_updates_actor_registries_when_present():
    state, world, _ = _consume_world_events([
        _pressure_world_event("evt-disease", "disease", location_ids=["camp"], actor_ids=["npc-a"]),
        _pressure_world_event("evt-missing", "unexplained_disappearance", location_ids=["camp"], actor_ids=["npc-b"]),
    ])

    health = {row["id"]: row for row in world["actor_health_registry"]}
    locations = {row["id"]: row for row in world["actor_location_registry"]}
    assert health["npc-a"]["health_status"] == "sick"
    assert locations["npc-b"]["status"] == "missing"
    assert locations["npc-b"]["location_id"] == "camp"
    assert state["world_state_receipts"]


def _guard_fixture():
    authoritative = {
        "world_resources": [
            {
                "id": "resource-market",
                "quantity_delta": -2,
                "trend": "decreasing",
                "status": "shortage",
                "source_event_ids": ["evt-raid"],
                "updated_turn": 3,
            }
        ],
        "travel_routes": [
            {
                "id": "route-east",
                "location_id": "bridge-east",
                "status": "blocked",
                "conditions": ["route_obstructed"],
                "source_event_ids": ["evt-collapse"],
                "updated_turn": 3,
            }
        ],
        "infrastructure_state": [
            {
                "id": "infrastructure-east",
                "location_id": "bridge-east",
                "status": "damaged",
                "conditions": ["structural_failure"],
                "source_event_ids": ["evt-collapse"],
                "updated_turn": 3,
            }
        ],
        "settlement_conditions": [
            {
                "id": "settlement-east",
                "location_id": "bridge-east",
                "status": "unstable",
                "conditions": ["security_decreased"],
                "source_event_ids": ["evt-raid"],
                "updated_turn": 3,
            }
        ],
        "faction_pressure": [
            {
                "id": "watch",
                "name": "watch",
                "ticks": {"security": -1, "influence": -1},
                "source_event_ids": ["evt-raid"],
                "updated_turn": 3,
            }
        ],
        "actor_health_registry": [
            {
                "id": "npc-a",
                "health_status": "sick",
                "source_event_ids": ["evt-disease"],
                "updated_turn": 3,
            }
        ],
        "actor_location_registry": [
            {
                "id": "npc-b",
                "location_id": "camp",
                "status": "missing",
                "source_event_ids": ["evt-missing"],
                "updated_turn": 3,
            }
        ],
    }
    replay = {"run_seed": FIXED_SEED, "world_state_guard_receipts": []}
    return authoritative, replay


def test_post_llm_guard_restores_consumer_owned_world_resources():
    authoritative, replay = _guard_fixture()
    merged = copy.deepcopy(authoritative)
    merged["world_resources"][0]["quantity_delta"] = 0
    merged["world_resources"][0]["trend"] = "stable"
    merged["world_resources"][0]["status"] = "stable"
    merged["scene"] = "market"

    result = world_state_consumers.enforce_consumer_world_state(merged, authoritative, replay, 4)

    assert merged["world_resources"][0]["quantity_delta"] == -2
    assert merged["world_resources"][0]["trend"] == "decreasing"
    assert merged["world_resources"][0]["status"] == "shortage"
    assert merged["scene"] == "market"
    receipt = next(r for r in replay["world_state_guard_receipts"] if r["receipt_type"] == "world_state_row_restored")
    assert receipt["collection"] == "world_resources"
    assert receipt["row_id"] == "resource-market"
    assert receipt["source_event_ids"] == ["evt-raid"]
    assert receipt["attempted_value_summary"]
    assert receipt["authoritative_value_summary"]
    assert result["diagnostics"]["world_state_guard_rows_restored"] == 1


def test_post_llm_guard_reinserts_or_restores_route_infrastructure_settlement_and_faction():
    authoritative, replay = _guard_fixture()
    merged = {
        "travel_routes": [],
        "infrastructure_state": [],
        "settlement_conditions": [],
        "faction_pressure": [{"id": "watch", "name": "watch", "ticks": {"security": 0, "influence": 0, "goodwill": 2}}],
    }

    world_state_consumers.enforce_consumer_world_state(merged, authoritative, replay, 4)

    assert merged["travel_routes"][0]["status"] == "blocked"
    assert merged["infrastructure_state"][0]["status"] == "damaged"
    assert merged["settlement_conditions"][0]["status"] == "unstable"
    assert merged["faction_pressure"][0]["ticks"]["security"] == -1
    assert merged["faction_pressure"][0]["ticks"]["influence"] == -1
    assert merged["faction_pressure"][0]["ticks"]["goodwill"] == 2
    receipt_types = {row["receipt_type"] for row in replay["world_state_guard_receipts"]}
    assert "world_state_row_reinserted" in receipt_types
    assert "world_state_field_restored" in receipt_types
    reinserted = [row for row in replay["world_state_guard_receipts"] if row["receipt_type"] == "world_state_row_reinserted"]
    assert any(row["attempted_value_summary"] == '{"attempt":"delete_or_omit"}' for row in reinserted)


def test_post_llm_guard_is_idempotent_and_replay_safe():
    authoritative, replay = _guard_fixture()
    merged = copy.deepcopy(authoritative)
    merged["world_resources"][0]["quantity_delta"] = 0

    first = world_state_consumers.enforce_consumer_world_state(merged, authoritative, replay, 4)
    receipts_after_first = copy.deepcopy(replay["world_state_guard_receipts"])
    merged_after_first = copy.deepcopy(merged)
    second = world_state_consumers.enforce_consumer_world_state(merged, authoritative, replay, 4)

    assert merged == merged_after_first
    assert replay["world_state_guard_receipts"] == receipts_after_first
    assert first["diagnostics"]["world_state_guard_rows_restored"] == 1
    assert second["diagnostics"]["world_state_guard_rows_restored"] == 0


def test_post_llm_guard_survives_two_consecutive_merge_cycles():
    authoritative, replay = _guard_fixture()
    merged_turn_4 = copy.deepcopy(authoritative)
    merged_turn_4["world_resources"][0]["quantity_delta"] = 0
    merged_turn_4["travel_routes"][0]["status"] = "open"

    first = world_state_consumers.enforce_consumer_world_state(merged_turn_4, authoritative, replay, 4)
    authoritative_turn_4 = copy.deepcopy(merged_turn_4)

    merged_turn_5 = copy.deepcopy(authoritative_turn_4)
    merged_turn_5["world_resources"][0]["trend"] = "stable"
    merged_turn_5["infrastructure_state"][0]["conditions"] = []
    merged_turn_5["settlement_conditions"][0]["status"] = "stable"
    merged_turn_5["faction_pressure"][0]["ticks"]["security"] = 0

    second = world_state_consumers.enforce_consumer_world_state(merged_turn_5, authoritative_turn_4, replay, 5)

    assert merged_turn_5["world_resources"][0]["quantity_delta"] == -2
    assert merged_turn_5["world_resources"][0]["trend"] == "decreasing"
    assert merged_turn_5["travel_routes"][0]["status"] == "blocked"
    assert merged_turn_5["infrastructure_state"][0]["conditions"] == ["structural_failure"]
    assert merged_turn_5["settlement_conditions"][0]["status"] == "unstable"
    assert merged_turn_5["faction_pressure"][0]["ticks"]["security"] == -1
    assert first["diagnostics"]["world_state_guard_rows_restored"] >= 1
    assert second["diagnostics"]["world_state_guard_rows_restored"] >= 1


def test_post_llm_guard_preserves_legitimate_unrelated_updates():
    authoritative, replay = _guard_fixture()
    merged = copy.deepcopy(authoritative)
    merged["recent_beats"] = ["new beat"]
    merged["world_resources"].append(
        {
            "id": "resource-harbor",
            "quantity_delta": 3,
            "trend": "increasing",
            "status": "improving",
        }
    )

    world_state_consumers.enforce_consumer_world_state(merged, authoritative, replay, 4)

    assert merged["recent_beats"] == ["new beat"]
    assert any(row["id"] == "resource-harbor" for row in merged["world_resources"])
    assert replay["world_state_guard_receipts"] == []


def test_post_llm_guard_preserves_unrelated_rows_in_same_container_across_two_cycles():
    authoritative, replay = _guard_fixture()
    merged_turn_4 = copy.deepcopy(authoritative)
    merged_turn_4["world_resources"].append(
        {"id": "resource-harbor", "quantity_delta": 3, "trend": "increasing", "status": "improving"}
    )
    merged_turn_4["world_resources"][0]["status"] = "stable"

    world_state_consumers.enforce_consumer_world_state(merged_turn_4, authoritative, replay, 4)
    assert next(row for row in merged_turn_4["world_resources"] if row["id"] == "resource-harbor")["status"] == "improving"

    authoritative_turn_4 = copy.deepcopy(merged_turn_4)
    merged_turn_5 = copy.deepcopy(authoritative_turn_4)
    harbor = next(row for row in merged_turn_5["world_resources"] if row["id"] == "resource-harbor")
    harbor["status"] = "scarce-but-recovering"
    merged_turn_5["world_resources"][0]["quantity_delta"] = 99

    world_state_consumers.enforce_consumer_world_state(merged_turn_5, authoritative_turn_4, replay, 5)

    assert next(row for row in merged_turn_5["world_resources"] if row["id"] == "resource-harbor")["status"] == "scarce-but-recovering"
    assert merged_turn_5["world_resources"][0]["quantity_delta"] == -2


def test_post_llm_guard_restores_actor_health_and_location_rows():
    authoritative, replay = _guard_fixture()
    merged = copy.deepcopy(authoritative)
    merged["actor_health_registry"][0]["health_status"] = "healthy"
    merged["actor_location_registry"][0]["status"] = "present"
    merged["actor_location_registry"][0]["location_id"] = "safehouse"

    world_state_consumers.enforce_consumer_world_state(merged, authoritative, replay, 4)

    assert merged["actor_health_registry"][0]["health_status"] == "sick"
    assert merged["actor_location_registry"][0]["status"] == "missing"
    assert merged["actor_location_registry"][0]["location_id"] == "camp"
    assert any(row["collection"] == "actor_health_registry" for row in replay["world_state_guard_receipts"])
    assert any(row["collection"] == "actor_location_registry" for row in replay["world_state_guard_receipts"])


def test_prompt_safe_rolling_hides_consumer_metadata():
    safe = server._prompt_safe_rolling(
        {
            "world_resources": [
                {
                    "id": "resource-market",
                    "quantity_delta": -2,
                    "source_event_ids": ["evt-raid"],
                    "updated_turn": 3,
                }
            ],
            "actor_location_registry": [
                {"id": "npc-b", "location_id": "camp", "status": "missing", "source_event_ids": ["evt-missing"], "updated_turn": 3}
            ],
            "world_state_guard_receipts": [{"receipt_id": "guard-1"}],
        }
    )

    assert "source_event_ids" not in safe["world_resources"][0]
    assert "updated_turn" not in safe["world_resources"][0]
    assert "source_event_ids" not in safe["actor_location_registry"][0]
    assert "updated_turn" not in safe["actor_location_registry"][0]
    assert "world_state_guard_receipts" not in safe


def test_replayability_state_is_not_second_event_history():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=FIXED_SEED,
    )
    assert "engine_events" not in state
    receipts = state["transition_receipts"]
    assert all("source_event_id" in r and "receipt_type" in r for r in receipts)
    assert not any("detail" in r or "summary" in r for r in receipts)


# 73–76: message plumbing + directive order
def test_build_messages_order_pacing_opening_secret_pressure_echo():
    async def run():
        session = {
            "id": str(uuid.uuid4()),
            "turn_count": 0,
            "rolling_state": None,
        }
        rb = {
            "opening": opening_state.OPENING_DIRECTIVE_MARKER + "\nOPEN",
            "world": world_moves.NPC_WORLD_MOVE_MARKER + "\nWORLD",
            "pressure": pressure_graph.PRESSURE_DIRECTIVE_MARKER + "\nPRESS",
            "echo": "[REPLAYABILITY_ECHO_V1]\nECHO",
        }
        msgs = await server._build_messages(
            session,
            "Begin",
            memory_depth=2,
            history_window_fallback=10,
            early_game_stage=1,
            secret_reveal_directive="[SECRET_REVEAL_DIRECTIVE_V1]\nSECRET",
            replayability_directives=rb,
        )
        system = [m["content"] for m in msgs if m["role"] == "system"]
        assert server.STORY_ENGINE_SYSTEM_PROMPT in system[0]
        pacing_idx = next(i for i, c in enumerate(system) if "[CHRONICLE_CONTINUITY]" in c)
        opening_idx = next(i for i, c in enumerate(system) if opening_state.OPENING_DIRECTIVE_MARKER in c)
        secret_idx = next(i for i, c in enumerate(system) if "[SECRET_REVEAL_DIRECTIVE_V1]" in c)
        world_idx = next(i for i, c in enumerate(system) if world_moves.NPC_WORLD_MOVE_MARKER in c)
        pressure_idx = next(i for i, c in enumerate(system) if pressure_graph.PRESSURE_DIRECTIVE_MARKER in c)
        echo_idx = next(i for i, c in enumerate(system) if "[REPLAYABILITY_ECHO_V1]" in c)
        assert pacing_idx < opening_idx < secret_idx
        assert secret_idx < world_idx < pressure_idx < echo_idx

    _run_db(run())


def test_opening_directive_omitted_after_turn_one():
    async def run():
        session = {"id": str(uuid.uuid4()), "turn_count": 2, "rolling_state": {"scene": "x"}}
        rb = {
            "opening": opening_state.OPENING_DIRECTIVE_MARKER + "\nOPEN",
            "pressure": pressure_graph.PRESSURE_DIRECTIVE_MARKER + "\nPRESS",
            "echo": "",
        }
        msgs = await server._build_messages(
            session, "Player action: wait", 2, 10, early_game_stage=None,
            replayability_directives=rb,
        )
        blob = json.dumps(msgs)
        assert opening_state.OPENING_DIRECTIVE_MARKER not in blob
        assert pressure_graph.PRESSURE_DIRECTIVE_MARKER in blob

    _run_db(run())


def test_replayability_directives_frozen_on_retry():
    state, frozen = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=FIXED_SEED,
    )
    session = {"id": str(uuid.uuid4()), "turn_count": 0, "mode": "advanced", "replayability_state": state}
    captured: List[Dict[str, str]] = []

    original_build = server._build_messages

    async def track_build(*args, **kwargs):
        captured.append(copy.deepcopy(kwargs.get("replayability_directives") or {}))
        return await original_build(*args, **kwargs)

    server._build_messages = track_build
    calls = {"n": 0}

    async def fake_chat(**kwargs):
        calls["n"] += 1
        return {
            "content": _opening_response() if calls["n"] == 1 else _opening_response(),
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat

    def fail_opening(parsed, sess, player_action, early_game_stage=None):
        if calls["n"] <= 1:
            return False, "missing Pressure in state", "pacing"
        return True, "", "ok"

    original_validate = server._full_validate
    server._full_validate = fail_opening
    try:
        _run_db(
            server._generate_validated_turn(
                session, "[DEV_MODE: OFF]\n\nBegin",
                replayability_directives=frozen,
            )
        )
        assert len(captured) == 2
        assert captured[0] == captured[1] == frozen
    finally:
        server._build_messages = original_build
        server._full_validate = original_validate
        gateway.invoke_llm = original


def test_replayability_markers_scrubbed_from_player_text():
    text = (
        f"Before {opening_state.OPENING_DIRECTIVE_MARKER} "
        f"and {pressure_graph.PRESSURE_DIRECTIVE_MARKER} after"
    )
    scrubbed, hits = server._scrub_meta_from_text(text)
    assert opening_state.OPENING_DIRECTIVE_MARKER not in scrubbed
    assert hits >= 1


# 77–80: HTTP integration + reset + export safety
@pytest.fixture()
def mongo_env():
    motor_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    sync_client = MongoClient(os.environ["MONGO_URL"])
    db_name = os.environ["DB_NAME"]
    original_db = server.db
    server.db = motor_client[db_name]
    sync_db = sync_client[db_name]
    sync_db.sessions.delete_many({})
    sync_db.turns.delete_many({})
    yield sync_db
    server.db = original_db
    motor_client.close()
    sync_client.close()


@pytest.fixture()
def client(mongo_env):
    original = gateway.invoke_llm

    async def fake_chat(**kwargs):
        messages = kwargs.get("messages") or []
        last_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
        content = _action_response() if "Player action:" in last_user else _opening_response()
        return {
            "content": content,
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    gateway.invoke_llm = fake_chat
    with TestClient(server.app) as tc:
        yield tc
    gateway.invoke_llm = original


def test_new_story_persists_replayability_state(client, mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    resp = client.post(
        "/api/story/new",
        json={
            "device_id": device_id,
            "genre": "noir",
            "role": "detective",
            "tone": "gritty",
            "difficulty": "standard",
            "debug_mode": False,
        },
        headers={DEVICE_ID_HEADER: device_id},
    )
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["session_id"]
    doc = mongo_env.sessions.find_one({"id": session_id}, {"_id": 0})
    assert doc.get("replayability_state", {}).get("run_seed")
    assert "replayability_identity" not in (doc.get("rolling_state") or {})


def test_legacy_session_without_replayability_skips_prepare(client, mongo_env):
    session_id = str(uuid.uuid4())
    mongo_env.sessions.insert_one({
        "id": session_id,
        "device_id": TEST_DEVICE,
        "genre": "noir",
        "difficulty": "standard",
        "turn_count": 1,
        "rolling_state": {"scene": "old"},
        "mode": "advanced",
        "title": "Legacy",
        "last_state": {},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    resp = client.post(
        "/api/story/action",
        json={"session_id": session_id, "action_text": "look around", "debug_mode": False},
        headers={DEVICE_ID_HEADER: TEST_DEVICE},
    )
    assert resp.status_code == 200, resp.text
    doc = mongo_env.sessions.find_one({"id": session_id}, {"_id": 0})
    assert doc.get("replayability_state") is None


def test_reset_clears_replayability_state(client, mongo_env):
    session_id = str(uuid.uuid4())
    mongo_env.sessions.insert_one({
        "id": session_id,
        "device_id": TEST_DEVICE,
        "genre": "noir",
        "difficulty": "standard",
        "turn_count": 1,
        "rolling_state": {},
        "replayability_state": {"run_seed": FIXED_SEED, "version": 1},
        "mode": "advanced",
        "title": "Reset me",
        "last_state": {},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    resp = client.post(
        f"/api/story/session/{session_id}/reset",
        headers={DEVICE_ID_HEADER: TEST_DEVICE},
    )
    assert resp.status_code == 200
    doc = mongo_env.sessions.find_one({"id": session_id}, {"_id": 0})
    assert doc.get("replayability_state") is None


def test_player_export_excludes_replayability_state(client, mongo_env):
    session_id = str(uuid.uuid4())
    mongo_env.sessions.insert_one({
        "id": session_id,
        "device_id": TEST_DEVICE,
        "genre": "noir",
        "difficulty": "standard",
        "turn_count": 0,
        "replayability_state": {"run_seed": FIXED_SEED, "identity": {"has_secret": True}},
        "mode": "advanced",
        "title": "Export",
        "last_state": {},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    resp = client.get(
        f"/api/story/session/{session_id}/export",
        headers={DEVICE_ID_HEADER: TEST_DEVICE},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert "replayability_state" not in payload["session"]
    safe = player_api.build_player_session(
        {"id": session_id, "replayability_state": {"run_seed": FIXED_SEED}}
    )
    assert "replayability_state" not in safe


def test_replayability_directive_survives_context_budget_trim():
    rb = {
        "opening": opening_state.OPENING_DIRECTIVE_MARKER + "\n" + ("x" * 200),
        "pressure": pressure_graph.PRESSURE_DIRECTIVE_MARKER + "\n" + ("y" * 200),
        "echo": "",
    }
    msgs = [
        {"role": "system", "content": server.STORY_ENGINE_SYSTEM_PROMPT},
        {"role": "system", "content": rb["opening"]},
        {"role": "system", "content": rb["pressure"]},
        *[{"role": "user", "content": f"old {i} " + ("z" * 500)} for i in range(16)],
        {"role": "user", "content": "current action"},
    ]
    trimmed, _ = enforce_context_budget(msgs, budget_tokens=300, protected_recent_msgs=2)
    system_blob = " ".join(m["content"] for m in trimmed if m["role"] == "system")
    assert opening_state.OPENING_DIRECTIVE_MARKER in system_blob
