"""
End-to-end developer diagnostics regression — player routes + export gating.

Verifies turn.debug exposure requires BOTH server developer_mode AND session
debug_mode, while export and default player responses stay sanitised.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from starlette.testclient import TestClient

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import gateway  # noqa: E402
import server  # noqa: E402
from security import ADMIN_API_KEY_HEADER, DEVICE_ID_HEADER  # noqa: E402

TEST_ADMIN_KEY = "test-admin-key-dev-diagnostics-e2e"


@pytest.fixture()
def mongo_env(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", TEST_ADMIN_KEY)
    motor_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    sync_client = MongoClient(os.environ["MONGO_URL"])
    db_name = os.environ["DB_NAME"]
    original = server.db
    server.db = motor_client[db_name]
    sync_db = sync_client[db_name]
    yield sync_db
    server.db = original
    motor_client.close()
    sync_client.close()


@pytest.fixture()
def client(mongo_env):
    with TestClient(server.app) as c:
        yield c


def _device_headers(device_id: str) -> dict:
    return {DEVICE_ID_HEADER: device_id}


def _admin_headers() -> dict:
    return {ADMIN_API_KEY_HEADER: TEST_ADMIN_KEY}


def _set_developer_mode(client: TestClient, enabled: bool) -> None:
    client.post(
        "/api/admin/settings",
        headers=_admin_headers(),
        json={"developer_mode": enabled},
    )


def _seed_session(sync_db, device_id: str, *, debug_mode: bool) -> str:
    sid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    session = {
        "id": sid,
        "device_id": device_id,
        "genre": "fantasy",
        "role": "scout",
        "tone": "grim",
        "difficulty": "standard",
        "debug_mode": debug_mode,
        "title": "Diagnostics Chronicle",
        "turn_count": 1,
        "last_narrative_snippet": "Wind howls.",
        "last_state": {"Health": "wounded"},
        "rolling_state": {"scene": "ruins"},
        "rolling_state_updated_at": now,
        "mode": "advanced",
        "scenario_id": None,
        "created_at": now,
        "updated_at": now,
    }
    turn = {
        "id": str(uuid.uuid4()),
        "session_id": sid,
        "turn_number": 1,
        "player_action": None,
        "narrative": "Ash falls.",
        "paragraphs": ["Ash falls."],
        "choices": [{"label": "A", "text": "Press on"}],
        "state": {"Health": "wounded"},
        "ledger": {"Carried": "torch"},
        "rolling_state": {"scene": "ruins", "secret_registry": True},
        "debug": {"model_used": "test-model", "latency_ms": "900"},
        "raw": "<narrative>secret</narrative>",
        "created_at": now,
    }
    sync_db.sessions.insert_one(session)
    sync_db.turns.insert_one(turn)
    return sid


def _fake_llm_response():
    return (
        "<narrative>You step forward.</narrative>"
        "<paragraphs><p>You step forward.</p></paragraphs>"
        "<choices><choice label=\"A\">Continue</choice>"
        "<choice label=\"B\">Wait</choice>"
        "<choice label=\"C\">Look</choice>"
        "<choice label=\"D\">Listen</choice></choices>"
        "<state><Health>wounded</Health></state>"
        "<ledger><Carried>torch</Carried></ledger>"
        "<rolling_state>{\"scene\": \"ruins\"}</rolling_state>"
        "<debug><Roll>14</Roll></debug>"
    )


class TestDeveloperDiagnosticsE2E:
    def test_debug_present_when_both_flags_on(self, client, mongo_env):
        _set_developer_mode(client, True)
        owner = f"dev-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner, debug_mode=True)

        for path in (
            f"/api/story/session/{sid}",
            f"/api/story/session/{sid}/latest",
        ):
            r = client.get(path, headers=_device_headers(owner))
            assert r.status_code == 200, r.text
            turn = r.json()["turns"][0] if "turns" in r.json() else r.json()["turn"]
            assert "debug" in turn
            assert turn["debug"].get("model_used") == "test-model"
            assert "rolling_state" not in turn
            assert "raw" not in turn

        _set_developer_mode(client, False)

    def test_debug_absent_when_developer_mode_off(self, client, mongo_env):
        _set_developer_mode(client, False)
        owner = f"dev-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner, debug_mode=True)

        r = client.get(f"/api/story/session/{sid}", headers=_device_headers(owner))
        assert r.status_code == 200
        turn = r.json()["turns"][0]
        assert "debug" not in turn

    def test_debug_absent_when_session_debug_mode_off(self, client, mongo_env):
        _set_developer_mode(client, True)
        owner = f"dev-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner, debug_mode=False)

        r = client.get(f"/api/story/session/{sid}", headers=_device_headers(owner))
        assert r.status_code == 200
        turn = r.json()["turns"][0]
        assert "debug" not in turn
        _set_developer_mode(client, False)

    def test_export_always_strips_debug(self, client, mongo_env):
        _set_developer_mode(client, True)
        owner = f"dev-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner, debug_mode=True)

        r = client.get(
            f"/api/story/session/{sid}/export",
            headers=_device_headers(owner),
        )
        assert r.status_code == 200
        assert "debug" not in r.json()["turns"][0]
        assert "rolling_state" not in r.json()["turns"][0]
        _set_developer_mode(client, False)

    def test_story_action_debug_gated_like_get_session(self, client, mongo_env):
        _set_developer_mode(client, True)
        owner = f"dev-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner, debug_mode=True)

        async def fake_chat(**kwargs):
            return {
                "content": _fake_llm_response(),
                "model_used": "test-model",
                "model_requested": "test-model",
                "telemetry": {"provider": "test", "latency_ms": 42},
                "fallback_events": [],
                "attempts_per_model": {},
            }

        original = gateway.invoke_llm
        gateway.invoke_llm = fake_chat
        try:
            on = client.post(
                "/api/story/action",
                headers=_device_headers(owner),
                json={
                    "session_id": sid,
                    "action_text": "step forward",
                    "debug_mode": True,
                },
            )
            off = client.post(
                "/api/story/action",
                headers=_device_headers(owner),
                json={
                    "session_id": sid,
                    "action_text": "wait",
                    "debug_mode": False,
                },
            )
        finally:
            gateway.invoke_llm = original

        assert on.status_code == 200, on.text
        assert "debug" in on.json()["turn"]
        assert off.status_code == 200, off.text
        assert "debug" not in off.json()["turn"]
        _set_developer_mode(client, False)