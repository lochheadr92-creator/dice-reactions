"""
Stage 6C-0 -- Pressure Genesis scaffold tests.

Covers only what 6C-0 claims: the flag defaults OFF, empty_genesis_state()
has the minimal documented shape, ORIGIN_TYPES includes the new member, and
prepare_action_turn only touches replayability_state when the flag is on.
Rule-table / candidate-derivation / live-commit behaviour belongs to Stage
6C-1 and 6C-2 and is deliberately NOT tested here.
"""

from __future__ import annotations

import ai_config
import pressure_genesis
import pressure_graph
import replayability


def test_flag_defaults_off():
    assert ai_config.ENABLE_PRESSURE_GENESIS is False
    assert pressure_genesis.genesis_enabled() is False


def test_flag_reads_ai_config_at_call_time(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_PRESSURE_GENESIS", True)
    assert pressure_genesis.genesis_enabled() is True


def test_empty_genesis_state_shape():
    assert pressure_genesis.empty_genesis_state() == {
        "version": pressure_genesis.GENESIS_VERSION
    }


def test_empty_genesis_state_returns_fresh_dict():
    a = pressure_genesis.empty_genesis_state()
    b = pressure_genesis.empty_genesis_state()
    assert a == b
    assert a is not b


def test_origin_types_includes_pressure_genesis():
    assert "pressure_genesis" in pressure_graph.ORIGIN_TYPES


def test_prepare_action_turn_flag_off_is_noop():
    state, *_ = replayability.prepare_action_turn(
        {"run_seed": "test-genesis-off"}, 2, {}
    )
    assert "pressure_genesis" not in state


def test_prepare_action_turn_flag_on_adds_empty_block(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_PRESSURE_GENESIS", True)
    state, *_ = replayability.prepare_action_turn(
        {"run_seed": "test-genesis-on"}, 2, {}
    )
    assert state.get("pressure_genesis") == {
        "version": pressure_genesis.GENESIS_VERSION
    }
