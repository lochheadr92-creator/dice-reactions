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
import scenarios  # noqa: E402
import server  # noqa: E402
from ai_service import AIServiceError  # noqa: E402
from security import ADMIN_API_KEY_HEADER, DEVICE_ID_HEADER  # noqa: E402

TEST_ADMIN_KEY = os.environ.get("ADMIN_API_KEY") or "test-admin-key-for-http-integration"
os.environ["ADMIN_API_KEY"] = TEST_ADMIN_KEY

FAKE_TURN = (
    "<rolling_state>{}</rolling_state>\n"
    "<narrative>The gate creaks.</narrative>\n"
    "<choices>\n"
    "A. Enter\n"
    "B. Listen\n"
    "C. Retreat\n"
    "D. Call out\n"
    "</choices>\n"
    "<state>\n"
    "Health: stable\n"
    "Stress: clear\n"
    "Fatigue: rested\n"
    "Position: at the gate\n"
    "Inventory Summary: torch\n"
    "Pressure: wind rising\n"
    "</state>\n"
    "<ledger>\n"
    "Carried: torch\n"
    "Load: light\n"
    "</ledger>\n"
)

ACTION_TURN = (
    "<rolling_state>{}</rolling_state>\n"
    "<narrative>You step forward.</narrative>\n"
    "<choices>\n"
    "A. Continue\n"
    "B. Look around\n"
    "C. Listen carefully\n"
    "D. Hold position\n"
    "</choices>\n"
    "<state>\n"
    "Health: stable\n"
    "Pressure: steady\n"
    "Position: forward\n"
    "</state>\n"
    "<ledger>\n"
    "Carried: torch\n"
    "</ledger>\n"
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

    def test_quick_start_backend_selects_and_stores_scenario_and_role(
        self, client, mongo_env
    ):
        device = f"quick-{uuid.uuid4()}"
        seed = f"story-create:quick-{uuid.uuid4()}"
        expected = scenarios.select_quick_start_scenario_id("dinosaur-survival", seed)
        expected_sc = scenarios.get_scenario(expected)
        assert expected_sc is not None

        payload = {
            "device_id": device,
            "genre": "prehistoric survival",
            "tone": "tense",
            "difficulty": "brutal",
            "debug_mode": False,
            "mode": "advanced",
            "role": "card-default-should-not-win",
            "quick_start_key": "dinosaur-survival",
            "creation_request_id": seed,
        }
        created = client.post("/api/story/new", json=payload)
        assert created.status_code == 200, created.text
        body = created.json()
        session = body["session"]
        assert session["scenario_id"] == expected
        assert session["scenario_id"] != "dinosaur-containment-breach"
        assert session["role"] == expected_sc["role"]
        assert session["role"] != "card-default-should-not-win"
        assert session["title"] == expected_sc["title"]
        assert "Wanderer" not in session["title"]

        # Same seed → same session on retry
        again = client.post("/api/story/new", json=payload)
        assert again.status_code == 200
        assert again.json()["session_id"] == body["session_id"]

        # Mismatch fails closed
        bad = client.post(
            "/api/story/new",
            json={
                **payload,
                "device_id": f"quick-bad-{uuid.uuid4()}",
                "creation_request_id": f"story-create:bad-{uuid.uuid4()}",
                "scenario_id": "suburban-collapse",
            },
        )
        assert bad.status_code == 422

    def test_custom_setup_dedupes_dict_simulation_hooks_without_crashing(
        self, client, mongo_env, monkeypatch
    ):
        custom_turn = (
            "<rolling_state>"
            "{\"simulation_hooks\":"
            "[\"keep watch\","
            "{\"kind\":\"omen\",\"value\":\"storm\",\"tags\":[\"weather\",\"risk\"]},"
            "{\"value\":\"storm\",\"tags\":[\"weather\",\"risk\"],\"kind\":\"omen\"},"
            "\"keep watch\"]}"
            "</rolling_state>\n"
            "<narrative>The gate creaks. Dust hangs in the air.</narrative>\n"
            "<choices>\n"
            "A. Enter\n"
            "B. Listen\n"
            "C. Retreat\n"
            "D. Call out\n"
            "</choices>\n"
            "<state>\n"
            "Health: stable\n"
            "Stress: clear\n"
            "Fatigue: rested\n"
            "Position: at the gate\n"
            "Inventory Summary: torch\n"
            "Pressure: wind rising\n"
            "</state>\n"
            "<ledger>\n"
            "Carried: torch\n"
            "Load: light\n"
            "</ledger>\n"
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
        # Stage 2A compact coded hooks (not prose "core desire: …").
        assert "desire:keep the convoy alive" in hooks
        assert "world danger: sirens trigger stampedes" in hooks

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

    def test_hard_coherence_both_fail_uses_fail_forward_http(self, client, mongo_env):
        """Both model attempts hard-invalid: preserve state, one retry, session stays playable."""
        device = f"hard-ff-{uuid.uuid4()}"
        prior = {
            "scene": "small settlement lane",
            "character": "a weary scholar",
            "active_pressures": [{"id": "scar", "label": "scarcity", "status": "active"}],
            "inventory_objects": [{"object": "satchel"}],
            "object_locations": [{"object": "well", "location": "lane"}],
            "npcs": [{"name": "Mira", "alive": True}],
        }
        sid = str(uuid.uuid4())
        mongo_env.sessions.insert_one(
            {
                "id": sid,
                "device_id": device,
                "genre": "fantasy",
                "role": "a scholar",
                "tone": "grim",
                "difficulty": "hard",
                "mode": "basic",
                "turn_count": 1,
                "last_state": {
                    "Health": "stable",
                    "Pressure": "scarcity",
                    "Position": "lane",
                },
                "rolling_state": prior,
                "custom_world_setup": {
                    "creationFlow": "guided",
                    "want": "knowledge",
                    "fear": "failure",
                    "whoMatters": "nobody",
                    "pressures": ["scarcity"],
                    "startingLocation": "small_settlement",
                    "worldExclusions": "firearms",
                    "settingGroundedness": "mostly_grounded",
                },
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        mongo_env.turns.insert_one(
            {
                "id": str(uuid.uuid4()),
                "session_id": sid,
                "turn_number": 1,
                "narrative": "Opening lane.",
                "paragraphs": ["Opening lane."],
                "choices": [
                    {"label": "A", "text": "Look"},
                    {"label": "B", "text": "Wait"},
                    {"label": "C", "text": "Listen"},
                    {"label": "D", "text": "Move"},
                ],
                "state": {"Health": "stable", "Pressure": "scarcity"},
                "ledger": {},
                "rolling_state": prior,
            }
        )

        def _xml(narrative, choices, rolling):
            choice_lines = "\n".join(
                f"{lab}. {txt}" for lab, txt in zip("ABCD", choices)
            )
            return (
                f"<rolling_state>{json.dumps(rolling)}</rolling_state>\n"
                f"<narrative>\n{narrative}\n</narrative>\n"
                f"<choices>\n{choice_lines}\n</choices>\n"
                f"<state>\nHealth: stable\nPressure: scarcity\nPosition: lane\n</state>\n"
                f"<ledger>\nCarried: satchel\n</ledger>\n"
            )

        first = _xml(
            "Rain on the lane near the well and satchel.",
            [
                "Ask Harwood for directions out of town",
                "Check the well carefully",
                "Watch Mira closely",
                "Hold position and wait",
            ],
            {
                **prior,
                "npcs": prior["npcs"] + [{"name": "Harwood", "alive": True}],
                "scene": "enemy trenches",
                "character": "a frontline soldier",
            },
        )
        second = _xml(
            "You fire a shotgun into the crowd.",
            [
                "Fire the shotgun at the crowd",
                "Reload the pistol quickly",
                "Throw a grenade toward the ridge",
                "Sprint for the jeep",
            ],
            {**prior, "active_pressures": [], "scene": "neon arcade"},
        )
        calls = {"n": 0}

        async def hard_invalid_chat(**_kwargs):
            calls["n"] += 1
            content = first if calls["n"] == 1 else second
            return {
                "content": content,
                "model_used": "test",
                "model_requested": "test",
                "telemetry": {"provider": "test"},
                "fallback_events": [],
                "attempts_per_model": {},
            }

        original = gateway.invoke_llm
        gateway.invoke_llm = hard_invalid_chat
        try:
            r1 = client.post(
                "/api/story/action",
                headers=_device_headers(device),
                json={
                    "session_id": sid,
                    "action_text": "ask around",
                    "debug_mode": True,
                },
            )
            assert r1.status_code == 200, r1.text
            assert calls["n"] == 2  # exactly one bounded retry
            body1 = r1.json()
            narr = body1["turn"]["narrative"]
            choice_blob = " ".join(
                c.get("text") or "" for c in body1["turn"].get("choices") or []
            )
            assert "Harwood" not in narr
            assert "shotgun" not in narr.lower()
            assert "Harwood" not in choice_blob
            assert "shotgun" not in choice_blob.lower()
            assert len(body1["turn"].get("choices") or []) >= 4

            stored = mongo_env.sessions.find_one({"id": sid})
            assert stored["turn_count"] == 2
            assert stored["rolling_state"]["scene"] == prior["scene"]
            assert stored["rolling_state"]["character"] == prior["character"]
            assert any(
                (p.get("label") if isinstance(p, dict) else p) == "scarcity"
                for p in (stored["rolling_state"].get("active_pressures") or [])
            )
            assert all(
                n.get("name") != "Harwood"
                for n in (stored["rolling_state"].get("npcs") or [])
            )
            turn2 = mongo_env.turns.find_one({"session_id": sid, "turn_number": 2})
            assert turn2 is not None
            dbg = turn2.get("debug") or {}
            assert (
                dbg.get("validation_hard_fallback") == "yes"
                or (turn2.get("raw") or "").find("fail_forward") >= 0
                or "validation_hard_fallback" in json.dumps(turn2)
            )

            # Following turn remains playable with a valid model response
            valid = (
                "<rolling_state>{}</rolling_state>\n"
                "<narrative>\nYou check the well carefully.\n</narrative>\n"
                "<choices>\nA. Look around\nB. Check the satchel\n"
                "C. Watch Mira\nD. Wait\n</choices>\n"
                "<state>\nHealth: stable\nPressure: scarcity\nPosition: lane\n</state>\n"
                "<ledger>\nCarried: satchel\n</ledger>\n"
            )

            async def valid_chat(**_kwargs):
                calls["n"] += 1
                return {
                    "content": valid,
                    "model_used": "test",
                    "model_requested": "test",
                    "telemetry": {},
                    "fallback_events": [],
                    "attempts_per_model": {},
                }

            gateway.invoke_llm = valid_chat
            before = calls["n"]
            r2 = client.post(
                "/api/story/action",
                headers=_device_headers(device),
                json={"session_id": sid, "action_text": "check the well", "debug_mode": False},
            )
            assert r2.status_code == 200, r2.text
            assert calls["n"] == before + 1  # no unbounded regen
            assert "well" in r2.json()["turn"]["narrative"].lower()
            assert mongo_env.sessions.find_one({"id": sid})["turn_count"] == 3
        finally:
            gateway.invoke_llm = original
