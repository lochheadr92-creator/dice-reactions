"""HUD shaping (Pressure / Danger / Momentum, no Objective) unit tests."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import hud  # noqa: E402


def test_objective_is_removed():
    state = {"Health": "stable", "Objective": "Locate medical supplies, secure shelter"}
    hud.shape_hud(state, {})
    assert "Objective" not in state


def test_danger_and_momentum_defaults_present():
    state = {"Health": "wounded"}
    hud.shape_hud(state, {})
    assert state["Danger"] in hud.DANGER_VALUES
    assert state["Momentum"] in hud.MOMENTUM_VALUES
    assert state["Danger"] == "elevated"  # wounded -> elevated


def test_invalid_chip_values_are_normalised():
    state = {"Health": "stable", "Danger": "spicy", "Momentum": "vibing"}
    hud.shape_hud(state, {})
    assert state["Danger"] in hud.DANGER_VALUES
    assert state["Momentum"] == "steady"


def test_pressure_survival_flag_wins():
    state = {"Health": "critical"}
    rolling = {"injuries": [{"name": "gunshot wound", "severity": "critical", "status": "worsening"}]}
    hud.shape_hud(state, rolling)
    assert state["Pressure"] == "Gunshot wound worsening"


def test_pressure_keeps_grounded_model_phrase():
    state = {"Health": "stable", "Pressure": "Nightfall approaching"}
    hud.shape_hud(state, {})
    assert state["Pressure"] == "Nightfall approaching"


def test_pressure_rejects_prescriptive_phrase():
    state = {"Health": "wounded", "Pressure": "Find medical supplies and secure shelter"}
    hud.shape_hud(state, {})
    # Prescriptive phrase dropped -> derived fallback (wound throbbing), never the instruction.
    assert "find" not in state["Pressure"].lower()
    assert "secure" not in state["Pressure"].lower()
    assert state["Pressure"]  # a grounded fallback exists


def test_pressure_threat_fallback():
    state = {"Health": "stable"}
    rolling = {"active_threats": [{"desc": "raiders"}]}
    hud.shape_hud(state, rolling)
    assert state["Pressure"] == "Unseen threat closing in"


def test_pressure_absent_when_nothing_presses():
    state = {"Health": "stable", "Stress": "clear", "Fatigue": "rested"}
    hud.shape_hud(state, {})
    assert "Pressure" not in state
