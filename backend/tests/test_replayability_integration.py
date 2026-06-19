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
import opening_state  # noqa: E402
import player_api  # noqa: E402
import pressure_graph  # noqa: E402
import replayability  # noqa: E402
import server  # noqa: E402
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
    updated, directives, diag, _ = replayability.prepare_action_turn(state, 2)
    assert updated["pressure_graph"]["tick"] >= 1
    assert directives["opening"] == ""
    assert directives["pressure"]


def test_prepare_action_turn_passthrough_without_state():
    updated, directives, diag, _ = replayability.prepare_action_turn(None, 2)
    assert updated == {}
    assert directives == {"opening": "", "pressure": "", "echo": ""}
    assert diag == {}


# 69–72: Policy A + enforcement
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
    tampered["magnitude"] = 99
    tampered["trend"] = 1
    adj = replayability.enforce_authoritative(rolling, state)
    assert "pressure_graph" not in rolling
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
    updated, _, _, thresholds = replayability.prepare_action_turn(state, 2)
    assert thresholds
    assert thresholds[0]["event_id"]
    scheduled = updated["consequence_echoes"]["scheduled"]
    assert any(e.get("source_event_id") == thresholds[0]["event_id"] for e in scheduled)


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
        pressure_idx = next(i for i, c in enumerate(system) if pressure_graph.PRESSURE_DIRECTIVE_MARKER in c)
        echo_idx = next(i for i, c in enumerate(system) if "[REPLAYABILITY_ECHO_V1]" in c)
        assert pacing_idx < opening_idx < secret_idx
        assert secret_idx < pressure_idx < echo_idx

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