"""
P0 security tests — session ownership, admin authentication, safe export.

Uses Starlette TestClient against the in-process FastAPI app with a per-test
Motor binding (same pattern as test_gateway_e2e). Requires MONGO_URL, DB_NAME.
Sets ADMIN_API_KEY for the suite if not already configured.
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

TEST_ADMIN_KEY = os.environ.get("ADMIN_API_KEY") or "test-admin-key-for-security-suite"
os.environ["ADMIN_API_KEY"] = TEST_ADMIN_KEY


@pytest.fixture()
def mongo_env():
    """Bind a fresh Motor client for the app; seed via sync PyMongo; restore after."""
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


def _seed_session(sync_db, device_id: str, session_id: str | None = None) -> str:
    sid = session_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    session = {
        "id": sid,
        "device_id": device_id,
        "genre": "fantasy",
        "role": "scout",
        "tone": "grim",
        "difficulty": "standard",
        "debug_mode": False,
        "title": "Secret Chronicle Title",
        "turn_count": 1,
        "last_narrative_snippet": "The wind howls.",
        "last_state": {"Health": "wounded", "Danger": "elevated"},
        "rolling_state": {
            "relationship_vectors": [{"name": "Mira", "trust": 10}],
            "deceased": [],
            "scene": "ruins",
        },
        "rolling_state_updated_at": now,
        "mode": "advanced",
        "scenario_id": None,
        "active_model": "anthropic/claude-3-5-haiku",
        "fallback_chain": [],
        "model_switches": [],
        "cost_mode": "normal",
        "created_at": now,
        "updated_at": now,
    }
    turn = {
        "id": str(uuid.uuid4()),
        "session_id": sid,
        "turn_number": 1,
        "player_action": None,
        "narrative": "Ash falls over the broken gate.",
        "paragraphs": ["Ash falls over the broken gate."],
        "choices": [{"label": "A", "text": "Press on"}],
        "state": {"Health": "wounded", "Danger": "elevated", "Momentum": "steady"},
        "ledger": {"Carried": "torch"},
        "rolling_state": {"scene": "ruins", "secret_registry": True},
        "debug": {"model_used": "anthropic/claude-3-5-haiku", "latency_ms": "1200"},
        "raw": "<narrative>secret raw</narrative>",
        "created_at": now,
    }
    sync_db.sessions.insert_one(session)
    sync_db.turns.insert_one(turn)
    return sid


def _admin_headers(key: str | None = TEST_ADMIN_KEY) -> dict:
    if key is None:
        return {}
    return {ADMIN_API_KEY_HEADER: key}


def _enable_developer_mode(client) -> None:
    client.post(
        "/api/admin/settings",
        headers=_admin_headers(),
        json={"developer_mode": True},
    )


def _disable_developer_mode(client) -> None:
    client.post(
        "/api/admin/settings",
        headers=_admin_headers(),
        json={"developer_mode": False},
    )


# ---------------------------------------------------------------------------
# Session ownership (1–10)
# ---------------------------------------------------------------------------
class TestSessionOwnership:
    def test_owner_can_read_session(self, client, mongo_env):
        owner = f"dev-owner-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.get(f"/api/story/session/{sid}", headers=_device_headers(owner))
        assert r.status_code == 200
        assert r.json()["session"]["id"] == sid

    def test_other_device_cannot_read(self, client, mongo_env):
        owner = f"dev-owner-{uuid.uuid4()}"
        other = f"dev-other-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.get(f"/api/story/session/{sid}", headers=_device_headers(other))
        assert r.status_code == 404
        assert r.json()["detail"] == "Session not found"
        assert "Secret Chronicle" not in r.text

    def test_other_device_cannot_action(self, client, mongo_env):
        owner = f"dev-owner-{uuid.uuid4()}"
        other = f"dev-other-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.post(
            "/api/story/action",
            headers=_device_headers(other),
            json={
                "session_id": sid,
                "action_text": "look around",
                "debug_mode": False,
            },
        )
        assert r.status_code == 404

    def test_other_device_cannot_reset(self, client, mongo_env):
        owner = f"dev-owner-{uuid.uuid4()}"
        other = f"dev-other-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.post(
            f"/api/story/session/{sid}/reset",
            headers=_device_headers(other),
        )
        assert r.status_code == 404

    def test_other_device_cannot_delete(self, client, mongo_env):
        owner = f"dev-owner-{uuid.uuid4()}"
        other = f"dev-other-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.delete(
            f"/api/story/session/{sid}",
            headers=_device_headers(other),
        )
        assert r.status_code == 404

    def test_other_device_cannot_change_mode(self, client, mongo_env):
        owner = f"dev-owner-{uuid.uuid4()}"
        other = f"dev-other-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.post(
            f"/api/story/session/{sid}/mode",
            headers=_device_headers(other),
            json={"mode": "basic"},
        )
        assert r.status_code == 404

    def test_other_device_cannot_export(self, client, mongo_env):
        owner = f"dev-owner-{uuid.uuid4()}"
        other = f"dev-other-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.get(
            f"/api/story/session/{sid}/export",
            headers=_device_headers(other),
        )
        assert r.status_code == 404

    def test_missing_device_id_rejected(self, client, mongo_env):
        owner = f"dev-owner-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.get(f"/api/story/session/{sid}")
        assert r.status_code == 400
        assert r.json()["detail"] == "device_id is required"

    def test_unknown_session_not_found(self, client, mongo_env):
        r = client.get(
            f"/api/story/session/missing-{uuid.uuid4()}",
            headers=_device_headers(f"dev-{uuid.uuid4()}"),
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "Session not found"

    def test_wrong_owner_matches_unknown_session_response(self, client, mongo_env):
        owner = f"dev-owner-{uuid.uuid4()}"
        other = f"dev-other-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        wrong = client.get(f"/api/story/session/{sid}", headers=_device_headers(other))
        missing = client.get(
            f"/api/story/session/missing-{uuid.uuid4()}",
            headers=_device_headers(other),
        )
        assert wrong.status_code == missing.status_code == 404
        assert wrong.json() == missing.json() == {"detail": "Session not found"}
        assert "rolling_state" not in wrong.text
        assert "relationship_vectors" not in wrong.text


# ---------------------------------------------------------------------------
# Admin authentication (11–15)
# ---------------------------------------------------------------------------
class TestAdminAuthentication:
    def test_missing_admin_credential_rejected(self, client, mongo_env):
        r = client.get("/api/admin/settings")
        assert r.status_code == 401

    def test_incorrect_admin_credential_rejected(self, client, mongo_env):
        r = client.get("/api/admin/settings", headers=_admin_headers("wrong-key"))
        assert r.status_code == 401

    def test_correct_admin_credential_permitted(self, client, mongo_env):
        r = client.get("/api/admin/settings", headers=_admin_headers())
        assert r.status_code == 200
        assert "settings" in r.json()

    def test_developer_mode_requires_admin_auth(self, client, mongo_env):
        r = client.post("/api/admin/settings", json={"developer_mode": True})
        assert r.status_code == 401

    def test_developer_mode_change_with_admin_auth(self, client, mongo_env):
        r = client.post(
            "/api/admin/settings",
            headers=_admin_headers(),
            json={"developer_mode": True},
        )
        assert r.status_code == 200
        assert r.json()["settings"]["developer_mode"] is True
        r2 = client.get("/api/admin/settings")
        assert r2.status_code == 401


# ---------------------------------------------------------------------------
# Export safety (16–20)
# ---------------------------------------------------------------------------
class TestExportSafety:
    def test_player_export_is_sanitised(self, client, mongo_env):
        owner = f"dev-owner-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.get(
            f"/api/story/session/{sid}/export",
            headers=_device_headers(owner),
        )
        assert r.status_code == 200
        data = r.json()
        assert "rolling_state" not in data["session"]
        assert "rolling_state" not in (data.get("summary") or {})
        turn = data["turns"][0]
        assert "rolling_state" not in turn
        assert "debug" not in turn
        assert "raw" not in turn
        assert data["session"]["id"] == sid
        assert "device_id" not in data["session"]
        assert turn["narrative"]

    def test_developer_mode_does_not_grant_raw_player_export(self, client, mongo_env):
        _enable_developer_mode(client)
        owner = f"dev-owner-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.get(
            f"/api/story/session/{sid}/export",
            headers=_device_headers(owner),
        )
        assert r.status_code == 200
        assert "rolling_state" not in r.json()["session"]
        assert "debug" not in r.json()["turns"][0]
        _disable_developer_mode(client)

    def test_raw_export_requires_admin_auth(self, client, mongo_env):
        owner = f"dev-owner-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.get(f"/api/story/session/{sid}/export/raw")
        assert r.status_code == 401

    def test_raw_export_unknown_session_404(self, client, mongo_env):
        r = client.get(
            f"/api/story/session/missing-{uuid.uuid4()}/export/raw",
            headers=_admin_headers(),
        )
        assert r.status_code == 404

    def test_raw_export_admin_only_no_device_credential(self, client, mongo_env):
        owner = f"dev-owner-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.get(
            f"/api/story/session/{sid}/export/raw",
            headers=_admin_headers(),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["summary"]["rolling_state"]["scene"] == "ruins"
        assert data["turns"][0]["debug"]["model_used"]
        assert data["turns"][0]["raw"]
        assert data["session"]["title"] == "Secret Chronicle Title"


# ---------------------------------------------------------------------------
# Player routes always sanitised when developer_mode=true (21–25)
# ---------------------------------------------------------------------------
class TestPlayerRouteSanitisation:
    def test_get_session_strips_internal_state_with_developer_mode(self, client, mongo_env):
        _enable_developer_mode(client)
        owner = f"dev-owner-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.get(f"/api/story/session/{sid}", headers=_device_headers(owner))
        assert r.status_code == 200
        data = r.json()
        assert "rolling_state" not in data["session"]
        turn = data["turns"][0]
        assert "rolling_state" not in turn
        assert "debug" not in turn
        assert "raw" not in turn
        _disable_developer_mode(client)

    def test_latest_turn_strips_internal_state_with_developer_mode(self, client, mongo_env):
        _enable_developer_mode(client)
        owner = f"dev-owner-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.get(
            f"/api/story/session/{sid}/latest",
            headers=_device_headers(owner),
        )
        assert r.status_code == 200
        turn = r.json()["turn"]
        assert "rolling_state" not in turn
        assert "debug" not in turn
        assert "raw" not in turn
        _disable_developer_mode(client)

    def test_list_sessions_strips_rolling_state_with_developer_mode(self, client, mongo_env):
        _enable_developer_mode(client)
        owner = f"dev-owner-{uuid.uuid4()}"
        _seed_session(mongo_env, owner)
        r = client.get("/api/story/sessions", headers=_device_headers(owner))
        assert r.status_code == 200
        for session in r.json()["sessions"]:
            assert "rolling_state" not in session
        _disable_developer_mode(client)

    def test_export_strips_internal_state_with_developer_mode(self, client, mongo_env):
        _enable_developer_mode(client)
        owner = f"dev-owner-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)
        r = client.get(
            f"/api/story/session/{sid}/export",
            headers=_device_headers(owner),
        )
        assert r.status_code == 200
        data = r.json()
        assert "rolling_state" not in data["session"]
        assert "debug" not in data["turns"][0]
        _disable_developer_mode(client)

    def test_story_action_response_strips_internal_state_with_developer_mode(self, client, mongo_env):
        _enable_developer_mode(client)
        owner = f"dev-owner-{uuid.uuid4()}"
        sid = _seed_session(mongo_env, owner)

        raw_turn = (
            "<narrative>You step forward.</narrative>"
            "<paragraphs><p>You step forward.</p></paragraphs>"
            "<choices><choice label=\"A\">Continue</choice></choices>"
            "<state><Health>wounded</Health></state>"
            "<ledger><Carried>torch</Carried></ledger>"
            "<rolling_state>{\"scene\": \"ruins\"}</rolling_state>"
            "<debug><Roll>14</Roll></debug>"
        )

        async def fake_chat(**kwargs):
            return {
                "content": raw_turn,
                "model_used": "test",
                "model_requested": "test",
                "telemetry": {"provider": "test"},
                "fallback_events": [],
                "attempts_per_model": {},
            }

        original = gateway.invoke_llm
        gateway.invoke_llm = fake_chat
        try:
            r = client.post(
                "/api/story/action",
                headers=_device_headers(owner),
                json={
                    "session_id": sid,
                    "action_text": "step forward",
                    "debug_mode": True,
                },
            )
        finally:
            gateway.invoke_llm = original

        assert r.status_code == 200, r.text
        turn = r.json()["turn"]
        assert "rolling_state" not in turn
        assert "debug" not in turn
        assert "raw" not in turn
        _disable_developer_mode(client)