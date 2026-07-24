"""
Player API allowlist serializers — unknown/internal fields must not leak.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from player_api import (  # noqa: E402
    build_new_story_session_payload,
    build_player_choices,
    build_player_debug,
    build_player_ledger,
    build_player_paragraphs,
    build_player_session,
    build_player_state,
    build_player_turn,
)


def test_session_allowlist_drops_internal_fields():
    now = datetime.now(timezone.utc)
    raw = {
        "id": "sess-1",
        "device_id": "secret-device",
        "genre": "fantasy",
        "role": "scout",
        "tone": "grim",
        "difficulty": "standard",
        "debug_mode": False,
        "title": "Chronicle",
        "turn_count": 2,
        "last_narrative_snippet": "Ash falls.",
        "last_state": {"Health": "wounded", "Pressure": "Night closing in"},
        "rolling_state": {"scene": "ruins"},
        "active_model": "anthropic/claude-3-5-haiku",
        "fallback_chain": ["a", "b"],
        "model_switches": [{"from": "x"}],
        "cost_mode": "low",
        "custom_world_setup": {"worldConcept": "hidden"},
        "creation_request_id": "story-create-secret",
        "future_internal_field": "must not leak",
        "mode": "advanced",
        "scenario_id": None,
        "created_at": now,
        "updated_at": now,
    }
    out = build_player_session(raw)
    assert out["id"] == "sess-1"
    assert "device_id" not in out
    assert "rolling_state" not in out
    assert "active_model" not in out
    assert "fallback_chain" not in out
    assert "model_switches" not in out
    assert "cost_mode" not in out
    assert "custom_world_setup" not in out
    assert "creation_request_id" not in out
    assert "future_internal_field" not in out
    assert out["mature_content"]["adult_mode_enabled"] is False
    assert out["rendering_policy"]["route"] == "standard"

    new_story_out = build_new_story_session_payload(raw)
    assert new_story_out["id"] == "sess-1"
    assert "creation_request_id" not in new_story_out
    assert new_story_out["mature_content"]["adult_mode_enabled"] is False


def test_turn_allowlist_drops_engine_payloads():
    now = datetime.now(timezone.utc)
    raw = {
        "id": "turn-1",
        "session_id": "sess-1",
        "turn_number": 1,
        "player_action": None,
        "narrative": "Wind howls.",
        "paragraphs": ["Wind howls."],
        "choices": [{"label": "A", "text": "Go"}],
        "state": {"Health": "stable", "Pressure": "Cold rising"},
        "ledger": {"Carried": "knife", "Load": "light"},
        "rolling_state": {"secret": True},
        "debug": {"Roll": "14"},
        "raw": "<debug/>",
        "telemetry_blob": "internal",
        "created_at": now,
    }
    out = build_player_turn(raw)
    assert out["id"] == "turn-1"
    assert "rolling_state" not in out
    assert "debug" not in out
    assert "raw" not in out
    assert "telemetry_blob" not in out
    assert "Pressure" in out["state"]


def test_turn_include_debug_sanitizes_kv():
    raw = {
        "id": "turn-2",
        "session_id": "sess-1",
        "turn_number": 2,
        "narrative": "Wind.",
        "paragraphs": ["Wind."],
        "choices": [],
        "state": {},
        "ledger": {},
        "debug": {
            "model_used": "test-model",
            "latency_ms": "1200",
            "rolling_state": "must drop",
            "raw": "must drop",
        },
        "created_at": datetime.now(timezone.utc),
    }
    out = build_player_turn(raw, include_debug=True)
    assert out["debug"]["model_used"] == "test-model"
    assert out["debug"]["latency_ms"] == "1200"
    assert "rolling_state" not in out["debug"]
    assert "raw" not in out["debug"]


def test_build_player_debug_empty_and_blocked():
    assert build_player_debug(None) == {}
    assert build_player_debug({"secret_registry": "hidden", "Roll": "14"}) == {"Roll": "14"}


def test_unknown_state_and_ledger_keys_dropped():
    state = build_player_state({
        "Health": "stable",
        "Objective": "Find shelter",
        "secret_registry": "internal",
        "Pressure": "Shelter unstable",
    })
    assert "Health" in state
    assert "Pressure" in state
    assert "Objective" not in state
    assert "secret_registry" not in state

    ledger = build_player_ledger({
        "Carried": "torch",
        "engine_inventory_dump": "hidden",
        "Load": "light",
    })
    assert "Carried" in ledger
    assert "Load" in ledger
    assert "engine_inventory_dump" not in ledger


def test_recursive_nested_internal_keys_stripped():
    state = build_player_state({
        "Health": {
            "display": "stable",
            "secret_registry": {"latent": "hidden"},
            "nested_list": [{"trigger": "bad"}, {"ok": "yes"}],
        },
        "Pressure": "Cold",
        "internal_top": "drop me",
    })
    dumped = json.dumps(state)
    assert "secret_registry" not in dumped
    assert "trigger" not in dumped
    assert "internal_top" not in dumped
    assert "Health" in state
    assert "display" in state["Health"]
    assert "Pressure" in state

    ledger = build_player_ledger({
        "Carried": ["knife", {"engine_dump": "no"}],
        "Notes": {"public": "note", "rolling_state": "secret"},
        "hidden_bucket": "gone",
    })
    ledger_dump = json.dumps(ledger)
    assert "engine_dump" not in ledger_dump
    assert "rolling_state" not in ledger_dump
    assert "hidden_bucket" not in ledger_dump


def test_paragraphs_and_choices_recursive_scrub():
    paragraphs = build_player_paragraphs([
        "Safe line.",
        {"text": "Also safe.", "engine_meta": "hidden"},
        {"p": "Paragraph.", "debug": "strip"},
    ])
    assert paragraphs == ["Safe line.", "Also safe.", "Paragraph."]
    assert "engine_meta" not in json.dumps(paragraphs)

    choices = build_player_choices([
        {
            "label": "A",
            "text": "Go",
            "engine_hint": "secret",
            "nested": {"raw": "bad"},
        },
        {"label": "B", "text": {"display": "Wait"}, "telemetry": "x"},
    ])
    assert len(choices) == 2
    dumped = json.dumps(choices)
    assert "engine_hint" not in dumped
    assert "telemetry" not in dumped
    assert "raw" not in dumped
    assert choices[0]["label"] == "A"


def test_last_state_nested_in_session_scrubbed():
    session = build_player_session({
        "id": "s1",
        "genre": "fantasy",
        "last_state": {
            "Health": "fine",
            "secret_registry": "hidden",
            "nested": {"trigger": "x"},
        },
        "debug_mode": True,
    })
    dumped = json.dumps(session)
    assert "secret_registry" not in dumped
    assert "trigger" not in dumped
    assert session["debug_mode"] is True


def test_state_ledger_mechanic_labels_scrubbed():
    state = build_player_state({
        "Health": "stable",
        "Pressure": "Roll: 14 modifier +3 hidden mechanics",
    })
    assert "roll" not in state["Pressure"].lower()
    assert "modifier" not in state["Pressure"].lower()

    ledger = build_player_ledger({
        "Carried": "knife",
        "Notes": "The immune system fights infection",
    })
    assert "immune system" in ledger["Notes"].lower()


def test_safe_ordinary_prose_preserved_in_ledger():
    ledger = build_player_ledger({
        "Carried": "steam engine part, ration tin",
        "Supplies": "water and bandages",
    })
    assert "steam engine" in ledger["Carried"]
    assert "ration" in ledger["Carried"]
