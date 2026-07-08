"""
Stage 6C-1 -- Pressure Genesis tests.

Covers the flag-off byte-identity invariant, the 6C-1 rule table (blocked
goals / open investigations / overloaded actor stress -> bounded pressure
via pressure_graph.upsert_pressure_node), determinism, cross-pass dedup, the
per-turn cap, and receipt correctness (created/skipped/deduped/linked/capped).
"""

from __future__ import annotations

import copy

import ai_config
import pressure_genesis
import pressure_graph
import replayability


def _fresh_state(**extra):
    state = {
        "run_seed": "test-genesis",
        "pressure_graph": pressure_graph.copy_pressure_graph(None),
    }
    state.update(extra)
    return state


# --- flag defaults / seam ----------------------------------------------------


def test_flag_defaults_off():
    assert ai_config.ENABLE_PRESSURE_GENESIS is False
    assert pressure_genesis.genesis_enabled() is False


def test_flag_reads_ai_config_at_call_time(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_PRESSURE_GENESIS", True)
    assert pressure_genesis.genesis_enabled() is True


def test_empty_genesis_state_shape():
    assert pressure_genesis.empty_genesis_state() == {
        "version": pressure_genesis.GENESIS_VERSION,
        "receipts": [],
    }


def test_empty_genesis_state_returns_fresh_dict():
    a = pressure_genesis.empty_genesis_state()
    b = pressure_genesis.empty_genesis_state()
    assert a == b
    assert a is not b
    assert a["receipts"] is not b["receipts"]


def test_origin_types_includes_pressure_genesis():
    assert "pressure_genesis" in pressure_graph.ORIGIN_TYPES


# --- flag OFF: zero read/write -----------------------------------------------


def test_evolve_pressure_genesis_flag_off_is_noop():
    state = _fresh_state(
        goals=[
            {
                "goal_id": "g1",
                "status": "blocked",
                "priority": 9,
                "owner_type": "npc",
                "owner_id": "npc-1",
            }
        ]
    )
    before = copy.deepcopy(state)
    result = pressure_genesis.evolve_pressure_genesis(state, {}, 2, run_seed="s")
    assert result == {"receipts": [], "diagnostics": {}}
    assert state == before


def test_prepare_action_turn_flag_off_is_noop():
    state, *_ = replayability.prepare_action_turn({"run_seed": "test-genesis-off"}, 2, {})
    assert "pressure_genesis" not in state


# --- flag ON: creates expected pressure from real signals --------------------


def test_flag_on_creates_pressure_from_blocked_goal(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_PRESSURE_GENESIS", True)
    state = _fresh_state(
        goals=[
            {
                "goal_id": "g1",
                "status": "blocked",
                "priority": 9,
                "owner_type": "npc",
                "owner_id": "npc-1",
            }
        ]
    )
    result = pressure_genesis.evolve_pressure_genesis(state, {}, 2, run_seed="seed-a")
    assert result["diagnostics"]["pressure_genesis_created"] == 1
    genesis_nodes = [
        n for n in state["pressure_graph"]["nodes"] if n.get("origin_type") == "pressure_genesis"
    ]
    assert len(genesis_nodes) == 1
    assert genesis_nodes[0]["origin_id"] == "g1"
    receipt_types = {r["receipt_type"] for r in result["receipts"]}
    assert "genesis_created" in receipt_types


def test_flag_on_creates_pressure_from_investigation_and_stress(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_PRESSURE_GENESIS", True)
    state = _fresh_state(
        investigations=[
            {
                "investigation_id": "inv-1",
                "status": "open",
                "priority": 7,
                "assigned_actor_ids": ["npc-2"],
            }
        ],
    )
    rolling = {"actor_stress": {"npc-5": {"stress_level": 90.0}}}
    result = pressure_genesis.evolve_pressure_genesis(state, rolling, 2, run_seed="seed-b")
    origins = {
        (n.get("origin_type"), n.get("origin_id")) for n in state["pressure_graph"]["nodes"]
    }
    assert ("pressure_genesis", "inv-1") in origins
    assert ("pressure_genesis", "npc-5") in origins
    assert result["diagnostics"]["pressure_genesis_created"] == 2


# --- skip reasons -------------------------------------------------------------


def test_low_priority_goal_is_skipped(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_PRESSURE_GENESIS", True)
    state = _fresh_state(
        goals=[
            {
                "goal_id": "g-low",
                "status": "blocked",
                "priority": 1,
                "owner_type": "npc",
                "owner_id": "npc-1",
            }
        ]
    )
    result = pressure_genesis.evolve_pressure_genesis(state, {}, 2, run_seed="seed-c")
    assert result["diagnostics"]["pressure_genesis_created"] == 0
    assert result["diagnostics"]["pressure_genesis_skipped"] == 1
    assert result["receipts"][0]["receipt_type"] == "genesis_skipped"
    assert result["receipts"][0]["reason"] == "below_priority_threshold"
    assert state["pressure_graph"]["nodes"] == []


def test_already_supported_goal_is_skipped(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_PRESSURE_GENESIS", True)
    state = _fresh_state(
        goals=[
            {
                "goal_id": "g-supported",
                "status": "blocked",
                "priority": 9,
                "owner_type": "npc",
                "owner_id": "npc-1",
                "supporting_pressure_ids": ["pressure-existing"],
            }
        ]
    )
    result = pressure_genesis.evolve_pressure_genesis(state, {}, 2, run_seed="seed-d")
    assert result["diagnostics"]["pressure_genesis_created"] == 0
    assert result["receipts"][0]["reason"] == "already_supported"


def test_elevated_stress_below_band_is_skipped(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_PRESSURE_GENESIS", True)
    state = _fresh_state()
    rolling = {"actor_stress": {"npc-6": {"stress_level": 40.0}}}
    result = pressure_genesis.evolve_pressure_genesis(state, rolling, 2, run_seed="seed-e")
    assert result["diagnostics"]["pressure_genesis_created"] == 0
    assert result["diagnostics"]["pressure_genesis_skipped"] == 1


# --- determinism ---------------------------------------------------------------


def test_same_seed_gives_same_output(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_PRESSURE_GENESIS", True)
    goals = [
        {"goal_id": "g1", "status": "blocked", "priority": 8, "owner_type": "npc", "owner_id": "npc-1"},
        {"goal_id": "g2", "status": "blocked", "priority": 7, "owner_type": "npc", "owner_id": "npc-2"},
    ]
    investigations = [{"investigation_id": "inv-1", "status": "active", "priority": 6}]

    state_a = _fresh_state(goals=copy.deepcopy(goals), investigations=copy.deepcopy(investigations))
    state_b = _fresh_state(goals=copy.deepcopy(goals), investigations=copy.deepcopy(investigations))

    result_a = pressure_genesis.evolve_pressure_genesis(state_a, {}, 3, run_seed="seed-fixed")
    result_b = pressure_genesis.evolve_pressure_genesis(state_b, {}, 3, run_seed="seed-fixed")

    assert state_a["pressure_graph"]["nodes"] == state_b["pressure_graph"]["nodes"]
    assert result_a["receipts"] == result_b["receipts"]
    assert result_a["diagnostics"] == result_b["diagnostics"]


# --- repeated pass does not duplicate -------------------------------------------


def test_repeated_pass_does_not_duplicate(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_PRESSURE_GENESIS", True)
    state = _fresh_state(
        goals=[
            {"goal_id": "g1", "status": "blocked", "priority": 8, "owner_type": "npc", "owner_id": "npc-1"},
        ]
    )
    first = pressure_genesis.evolve_pressure_genesis(state, {}, 2, run_seed="seed-repeat")
    assert first["diagnostics"]["pressure_genesis_created"] == 1

    second = pressure_genesis.evolve_pressure_genesis(state, {}, 3, run_seed="seed-repeat")
    assert second["diagnostics"]["pressure_genesis_created"] == 0
    assert second["diagnostics"]["pressure_genesis_deduped"] == 1
    genesis_nodes = [
        n for n in state["pressure_graph"]["nodes"] if n.get("origin_type") == "pressure_genesis"
    ]
    assert len(genesis_nodes) == 1


# --- cap -------------------------------------------------------------------------


def test_per_turn_cap_limits_creation(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_PRESSURE_GENESIS", True)
    goals = [
        {
            "goal_id": f"g{i}",
            "status": "blocked",
            "priority": 9 - i,
            "owner_type": "npc",
            "owner_id": f"npc-{i}",
        }
        for i in range(4)
    ]
    state = _fresh_state(goals=goals)
    result = pressure_genesis.evolve_pressure_genesis(state, {}, 2, run_seed="seed-cap")
    cap = pressure_genesis.MAX_GENESIS_CANDIDATES_PER_TURN
    assert result["diagnostics"]["pressure_genesis_created"] == cap
    assert result["diagnostics"]["pressure_genesis_capped"] == len(goals) - cap
    receipt_types = [r["receipt_type"] for r in result["receipts"]]
    assert receipt_types.count("genesis_created") == cap
    assert receipt_types.count("genesis_capped") == len(goals) - cap


# --- linking ------------------------------------------------------------------


def test_linked_receipt_when_sharing_actor(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_PRESSURE_GENESIS", True)
    state = _fresh_state(
        goals=[
            {
                "goal_id": "g1",
                "status": "blocked",
                "priority": 8,
                "owner_type": "npc",
                "owner_id": "npc-shared",
            }
        ],
        investigations=[
            {
                "investigation_id": "inv-1",
                "status": "open",
                "priority": 7,
                "assigned_actor_ids": ["npc-shared"],
            }
        ],
    )
    result = pressure_genesis.evolve_pressure_genesis(state, {}, 2, run_seed="seed-link")
    receipt_types = {r["receipt_type"] for r in result["receipts"]}
    assert "genesis_linked" in receipt_types


# --- integration wiring through prepare_action_turn -----------------------------


def test_prepare_action_turn_flag_on_generates_from_goals(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_PRESSURE_GENESIS", True)
    replayability_state = {
        "run_seed": "test-genesis-integration",
        "goals": [
            {
                "goal_id": "g1",
                "status": "blocked",
                "priority": 9,
                "owner_type": "npc",
                "owner_id": "npc-1",
            }
        ],
    }
    state, *_ = replayability.prepare_action_turn(replayability_state, 2, {})
    assert "pressure_genesis" in state
    genesis_nodes = [
        n for n in state["pressure_graph"]["nodes"] if n.get("origin_type") == "pressure_genesis"
    ]
    assert len(genesis_nodes) == 1
