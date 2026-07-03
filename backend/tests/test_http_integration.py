"""
Hermetic HTTP integration tests — FastAPI TestClient with mocked LLM gateway.

No OpenRouter credits or live external model required.
"""

from __future__ import annotations

import json
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
import rate_limit  # noqa: E402
import server  # noqa: E402
from ai_service import AIServiceError  # noqa: E402
from security import ADMIN_API_KEY_HEADER, DEVICE_ID_HEADER  # noqa: E402

TEST_ADMIN_KEY = os.environ.get("ADMIN_API_KEY") or "test-admin-key-for-http-integration"
os.environ["ADMIN_API_KEY"] = TEST_ADMIN_KEY

FAKE_TURN = (
    "<narrative>The gate creaks.</narrative>"
    "<paragraphs><p>The gate creaks.</p><p>Dust hangs in the air.</p></paragraphs>"
    "<choices>"
    "<choice label=\"A\">Enter</choice>"
    "<choice label=\"B\">Listen</choice>"
    "<choice label=\"C\">Retreat</choice>"
    "<choice label=\"D\">Call out</choice>"
    "</choices>"
    "<state><Health>stable</Health><Stress>clear</Stress><Fatigue>rested</Fatigue>"
    "<Position>at the gate</Position><Inventory Summary>torch</Inventory Summary>"
    "<Pressure>wind rising</Pressure></state>"
    "<ledger><Carried>torch</Carried><Load>light</Load></ledger>"
    "<rolling_state>{}</rolling_state>"
)

ACTION_TURN = (
    "<narrative>You step forward.</narrative>"
    "<paragraphs><p>You step forward.</p></paragraphs>"
    "<choices><choice label=\"A\">Continue</choice></choices>"
    "<state><Health>stable</Health><Pressure>steady</Pressure></state>"
    "<ledger><Carried>torch</Carried></ledger>"
    "<rolling_state>{}</rolling_state>"
)


@pytest.fixture()
def mongo_env(monkeypatch):
    motor_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    sync_client = MongoClient(os.environ["MONGO_URL"])
    db_name = os.environ["DB_NAME"]
    original_db = server.db
    server.db = motor_client[db_name]
    sync_db = sync_client[db_name]
    sync_db.rate_limits.delete_many({})
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_IP_MAX", 20)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_DEVICE_MAX", 20)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_MAX", 200)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_CONCURRENT", 10)
    monkeypatch.setattr(rate_limit, "TRUSTED_PROXY_COUNT", 0)
    yield sync_db
    server.db = original_db
    motor_client.close()
    sync_client.close()


@pytest.fixture()
def client(mongo_env):
    llm_calls = {"n": 0}

    async def fake_chat(**kwargs):
        llm_calls["n"] += 1
        if llm_calls["n"] == 1:
            content = FAKE_TURN
        else:
            content = ACTION_TURN
        return {
            "content": content,
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {"provider": "test"},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat
    with TestClient(server.app) as c:
        c.llm_calls = llm_calls  # type: ignore[attr-defined]
        yield c
    gateway.invoke_llm = original


def _device_headers(device_id: str) -> dict:
    return {DEVICE_ID_HEADER: device_id}


def _new_payload(device_id: str | None = None) -> dict:
    return {
        "device_id": device_id or f"http-{uuid.uuid4()}",
        "genre": "fantasy",
        "difficulty": "standard",
        "debug_mode": False,
    }


class TestHermeticHttpIntegration:
    def test_create_story_list_get_action_export_flow(self, client, mongo_env):
        device = f"http-{uuid.uuid4()}"
        created = client.post("/api/story/new", json=_new_payload(device))
        assert created.status_code == 200, created.text
        body = created.json()
        sid = body["session_id"]
        assert body["session"]["id"] == sid
        assert "rolling_state" not in body["turn"]
        assert "debug" not in body["turn"]

        listed = client.get("/api/story/sessions", headers=_device_headers(device))
        assert listed.status_code == 200
        ids = [s["id"] for s in listed.json()["sessions"]]
        assert sid in ids
        for session in listed.json()["sessions"]:
            assert "rolling_state" not in session

        fetched = client.get(f"/api/story/session/{sid}", headers=_device_headers(device))
        assert fetched.status_code == 200
        data = fetched.json()
        assert data["session"]["id"] == sid
        assert data["turns"]
        assert "rolling_state" not in data["session"]
        assert "debug" not in data["turns"][0]

        action = client.post(
            "/api/story/action",
            headers=_device_headers(device),
            json={"session_id": sid, "action_text": "look around", "debug_mode": False},
        )
        assert action.status_code == 200, action.text
        assert "rolling_state" not in action.json()["turn"]

        export = client.get(
            f"/api/story/session/{sid}/export",
            headers=_device_headers(device),
        )
        assert export.status_code == 200
        exp = export.json()
        assert exp["session"]["id"] == sid
        assert "rolling_state" not in exp["session"]
        assert "debug" not in exp["turns"][0]

        raw = client.get(
            f"/api/story/session/{sid}/export/raw",
            headers={ADMIN_API_KEY_HEADER: TEST_ADMIN_KEY},
        )
        assert raw.status_code == 200
        raw_data = raw.json()
        assert raw_data["session"]["device_id"] == device
        assert raw_data["turns"][0].get("raw") or raw_data["turns"][0].get("debug")
        rolling = (raw_data.get("summary") or {}).get("rolling_state") or {}
        pressure = rolling.get("pressure_graph") or {}
        assert pressure.get("nodes"), "engine pressure_graph missing from rolling_state"
        assert all(node.get("status") == "active" for node in pressure.get("nodes") or [])

    def test_creation_request_id_returns_existing_completed_session_without_duplicate(
        self, client, mongo_env, monkeypatch
    ):
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_DEVICE_MAX", 1)
        device = f"retry-{uuid.uuid4()}"
        creation_request_id = f"story-create:{uuid.uuid4()}"
        payload = {
            **_new_payload(device),
            "creation_request_id": creation_request_id,
        }

        first = client.post("/api/story/new", json=payload)
        assert first.status_code == 200, first.text
        first_body = first.json()
        sid = first_body["session_id"]
        calls_after_first = client.llm_calls["n"]  # type: ignore[attr-defined]

        second = client.post("/api/story/new", json=payload)
        assert second.status_code == 200, second.text
        second_body = second.json()
        assert second_body["session_id"] == sid
        assert second_body["session"]["id"] == sid
        assert second_body["turn"]["session_id"] == sid
        assert client.llm_calls["n"] == calls_after_first  # type: ignore[attr-defined]
        assert mongo_env.sessions.count_documents(
            {"device_id": device, "creation_request_id": creation_request_id}
        ) == 1
        assert mongo_env.turns.count_documents({"session_id": sid}) == 1
        assert "creation_request_id" not in json.dumps(second_body)

    def test_custom_setup_dedupes_dict_simulation_hooks_without_crashing(
        self, client, mongo_env, monkeypatch
    ):
        custom_turn = (
            "<narrative>The gate creaks.</narrative>"
            "<paragraphs><p>The gate creaks.</p><p>Dust hangs in the air.</p></paragraphs>"
            "<choices>"
            "<choice label=\"A\">Enter</choice>"
            "<choice label=\"B\">Listen</choice>"
            "<choice label=\"C\">Retreat</choice>"
            "<choice label=\"D\">Call out</choice>"
            "</choices>"
            "<state><Health>stable</Health><Stress>clear</Stress><Fatigue>rested</Fatigue>"
            "<Position>at the gate</Position><Inventory Summary>torch</Inventory Summary>"
            "<Pressure>wind rising</Pressure></state>"
            "<ledger><Carried>torch</Carried><Load>light</Load></ledger>"
            "<rolling_state>"
            "{\"simulation_hooks\":"
            "[\"keep watch\","
            "{\"kind\":\"omen\",\"value\":\"storm\",\"tags\":[\"weather\",\"risk\"]},"
            "{\"value\":\"storm\",\"tags\":[\"weather\",\"risk\"],\"kind\":\"omen\"},"
            "\"keep watch\"]}"
            "</rolling_state>"
        )

        async def fake_custom_chat(**kwargs):
            return {
                "content": custom_turn,
                "model_used": "test",
                "model_requested": "test",
                "telemetry": {"provider": "test"},
                "fallback_events": [],
                "attempts_per_model": {},
            }

        monkeypatch.setattr(gateway, "invoke_llm", fake_custom_chat)
        device = f"custom-hooks-{uuid.uuid4()}"
        payload = {
            **_new_payload(device),
            "mode": "advanced",
            "custom_world_setup": {
                "danger": "sirens trigger stampedes",
                "want": "keep the convoy alive",
            },
        }

        created = client.post("/api/story/new", json=payload)
        assert created.status_code == 200, created.text

        sid = created.json()["session_id"]
        exported = client.get(
            f"/api/story/session/{sid}/export/raw",
            headers={ADMIN_API_KEY_HEADER: TEST_ADMIN_KEY},
        )
        assert exported.status_code == 200, exported.text
        rolling = ((exported.json().get("summary") or {}).get("rolling_state") or {})
        hooks = rolling.get("simulation_hooks") or []

        assert hooks.count("keep watch") == 1
        dict_hooks = [hook for hook in hooks if isinstance(hook, dict)]
        assert dict_hooks == [
            {"kind": "omen", "value": "storm", "tags": ["weather", "risk"]}
        ]
        assert "core desire: keep the convoy alive" in hooks

    def test_creation_request_id_pending_duplicate_does_not_start_second_llm(
        self, client, mongo_env
    ):
        device = f"pending-{uuid.uuid4()}"
        creation_request_id = f"story-create:{uuid.uuid4()}"
        now = datetime.now(timezone.utc)
        mongo_env.sessions.insert_one({
            "id": str(uuid.uuid4()),
            "device_id": device,
            "genre": "fantasy",
            "difficulty": "standard",
            "debug_mode": False,
            "title": "Pending Chronicle",
            "turn_count": 0,
            "creation_request_id": creation_request_id,
            "created_at": now,
            "updated_at": now,
        })
        calls_before = client.llm_calls["n"]  # type: ignore[attr-defined]

        duplicate = client.post(
            "/api/story/new",
            json={**_new_payload(device), "creation_request_id": creation_request_id},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"] == "Story creation already in progress"
        assert client.llm_calls["n"] == calls_before  # type: ignore[attr-defined]

    def test_wrong_owner_rejected_indistinguishably(self, client, mongo_env):
        owner = f"owner-{uuid.uuid4()}"
        other = f"other-{uuid.uuid4()}"
        created = client.post("/api/story/new", json=_new_payload(owner))
        sid = created.json()["session_id"]

        wrong = client.get(f"/api/story/session/{sid}", headers=_device_headers(other))
        missing = client.get(
            f"/api/story/session/missing-{uuid.uuid4()}",
            headers=_device_headers(other),
        )
        assert wrong.status_code == missing.status_code == 404
        assert wrong.json() == missing.json()

    def test_per_device_limit_via_http(self, client, mongo_env, monkeypatch):
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_DEVICE_MAX", 1)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_IP_MAX", 100)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_MAX", 100)
        device = f"dev-cap-{uuid.uuid4()}"
        assert client.post("/api/story/new", json=_new_payload(device)).status_code == 200
        blocked = client.post("/api/story/new", json=_new_payload(device))
        assert blocked.status_code == 429
        assert blocked.json()["detail"] == "Too many requests"

    def test_per_ip_limit_via_http(self, client, mongo_env, monkeypatch):
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_IP_MAX", 1)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_DEVICE_MAX", 100)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_MAX", 100)
        assert client.post("/api/story/new", json=_new_payload()).status_code == 200
        blocked = client.post("/api/story/new", json=_new_payload())
        assert blocked.status_code == 429

    def test_global_fixed_limit_via_http(self, client, mongo_env, monkeypatch):
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_MAX", 1)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_IP_MAX", 100)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_DEVICE_MAX", 100)
        assert client.post("/api/story/new", json=_new_payload()).status_code == 200
        blocked = client.post("/api/story/new", json=_new_payload())
        assert blocked.status_code == 429

    def test_provider_failure_cleanup_via_http(self, client, mongo_env):
        secret = "provider-secret-token-ABC"

        async def boom(**_kwargs):
            raise AIServiceError(secret)

        original = gateway.invoke_llm
        gateway.invoke_llm = boom
        try:
            before_s = mongo_env.sessions.count_documents({})
            before_t = mongo_env.turns.count_documents({})
            r = client.post("/api/story/new", json=_new_payload(f"fail-{uuid.uuid4()}"))
            assert r.status_code == 502
            assert r.json()["detail"] == "Story engine unavailable"
            assert secret not in r.text
            assert mongo_env.sessions.count_documents({}) == before_s
            assert mongo_env.turns.count_documents({}) == before_t
        finally:
            gateway.invoke_llm = original
