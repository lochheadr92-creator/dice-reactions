"""
Session Action Concurrency Guard v1 — deterministic tests.

No live LLM calls. Covers lease acquire/release, HTTP 409 conflicts,
persistence CAS, overlap simulation, secret-reveal safety, and index setup.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from starlette.testclient import TestClient

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import action_concurrency as ac  # noqa: E402
import gateway  # noqa: E402
import player_api  # noqa: E402
import secrets  # noqa: E402
import server  # noqa: E402
from action_concurrency import (  # noqa: E402
    ACTION_CONFLICT_DETAIL,
    ACTION_LOCK_FIELDS,
    ActionLeaseConflict,
    ActionLeaseLost,
)
from ai_service import AIServiceError  # noqa: E402
from security import ADMIN_API_KEY_HEADER, DEVICE_ID_HEADER  # noqa: E402

SECRET_A = "I set the fire that killed the convoy."
TEST_ADMIN_KEY = os.environ.get("ADMIN_API_KEY") or "test-admin-key-for-action-concurrency"
os.environ["ADMIN_API_KEY"] = TEST_ADMIN_KEY

FIXED_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)


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


def _action_turn_response(*, leak: str = "") -> str:
    narrative = f"You steady your breath. {leak}".strip()
    return (
        f"<narrative>{narrative}</narrative>"
        f"<paragraphs><p>{narrative}</p></paragraphs>"
        "<choices>A. Continue\nB. Wait\nC. Listen\nD. Move</choices>"
        "<state><Health>stable</Health><Pressure>steady</Pressure></state>"
        "<ledger><Carried>torch</Carried></ledger>"
        "<rolling_state>{}</rolling_state>"
    )


def _registry(*entries) -> Dict[str, Any]:
    return {"secret_registry": list(entries)}


def _entry(secret: str, revealed: bool = False, turn_added: int = 1, **extra) -> Dict[str, Any]:
    row = {
        "secret": secret,
        "revealed": revealed,
        "turn_added": turn_added,
        "reveal_policy": secrets.DEFAULT_REVEAL_POLICY,
    }
    row.update(extra)
    return row


@pytest.fixture(autouse=True)
def reset_clock():
    ac.set_clock_for_tests(None)
    yield
    ac.set_clock_for_tests(None)


@pytest.fixture()
def mongo_env(monkeypatch):
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
    llm_calls = {"n": 0}
    directive_seen = {"value": None}

    async def fake_chat(**kwargs):
        llm_calls["n"] += 1
        directive_seen["value"] = kwargs.get("secret_reveal_directive")
        return {
            "content": _action_turn_response(),
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat
    with TestClient(server.app) as tc:
        tc.llm_calls = llm_calls  # type: ignore[attr-defined]
        tc.directive_seen = directive_seen  # type: ignore[attr-defined]
        yield tc
    gateway.invoke_llm = original


def _insert_session(sync_db, device_id: str, *, turn_count: int = 1, rolling=None):
    sid = str(uuid.uuid4())
    sync_db.sessions.insert_one(
        {
            "id": sid,
            "device_id": device_id,
            "genre": "horror",
            "role": "scout",
            "tone": "grim",
            "difficulty": "standard",
            "mode": "advanced",
            "turn_count": turn_count,
            "rolling_state": copy.deepcopy(rolling or {}),
            "last_state": {"Health": "stable"},
            "created_at": FIXED_NOW.isoformat(),
            "updated_at": FIXED_NOW.isoformat(),
        }
    )
    return sid


def _set_active_lease(sync_db, sid: str, token: str, *, expires_at: datetime):
    sync_db.sessions.update_one(
        {"id": sid},
        {
            "$set": {
                "action_lock_token": token,
                "action_lock_acquired_at": FIXED_NOW,
                "action_lock_expires_at": expires_at,
            }
        },
    )


# ---------------------------------------------------------------------------
# Lease module unit tests (1–16)
# ---------------------------------------------------------------------------
class TestLeaseModule:
    def test_acquire_succeeds_with_no_existing_lock(self, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)

        async def run():
            session, token = await ac.acquire_action_lease(
                server.db, sid, device_id, now=FIXED_NOW
            )
            assert token
            assert session["id"] == sid
            assert session["action_lock_token"] == token
            stored = await server.db.sessions.find_one({"id": sid})
            assert stored["action_lock_token"] == token

        _run_db(run())

    def test_locked_authoritative_session_returned(self, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id, turn_count=3)

        async def run():
            session, _token = await ac.acquire_action_lease(
                server.db, sid, device_id, now=FIXED_NOW
            )
            assert session["turn_count"] == 3

        _run_db(run())

    def test_second_acquire_on_active_lease_fails(self, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        token = str(uuid.uuid4())
        _set_active_lease(
            mongo_env,
            sid,
            token,
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )

        async def run():
            with pytest.raises(ActionLeaseConflict):
                await ac.acquire_action_lease(server.db, sid, device_id, now=FIXED_NOW)

        _run_db(run())

    def test_expired_lease_can_be_reclaimed(self, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        old_token = str(uuid.uuid4())
        _set_active_lease(
            mongo_env,
            sid,
            old_token,
            expires_at=FIXED_NOW - timedelta(seconds=1),
        )

        async def run():
            _session, new_token = await ac.acquire_action_lease(
                server.db, sid, device_id, now=FIXED_NOW
            )
            assert new_token != old_token
            stored = await server.db.sessions.find_one({"id": sid})
            assert stored["action_lock_token"] == new_token

        _run_db(run())

    def test_fresh_lease_cannot_be_reclaimed(self, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        token = str(uuid.uuid4())
        _set_active_lease(
            mongo_env,
            sid,
            token,
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )

        async def run():
            with pytest.raises(ActionLeaseConflict):
                await ac.acquire_action_lease(server.db, sid, device_id, now=FIXED_NOW)

        _run_db(run())

    def test_release_removes_lease_fields(self, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        token = str(uuid.uuid4())
        _set_active_lease(
            mongo_env,
            sid,
            token,
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )

        async def run():
            ok = await ac.release_action_lease(server.db, sid, token)
            assert ok
            stored = await server.db.sessions.find_one({"id": sid})
            for field in ACTION_LOCK_FIELDS:
                assert field not in stored or stored.get(field) is None

        _run_db(run())

    def test_release_requires_exact_token(self, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        token = str(uuid.uuid4())
        _set_active_lease(
            mongo_env,
            sid,
            token,
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )

        async def run():
            ok = await ac.release_action_lease(server.db, sid, "wrong-token")
            assert not ok
            stored = await server.db.sessions.find_one({"id": sid})
            assert stored["action_lock_token"] == token

        _run_db(run())

    def test_old_token_cannot_release_newer_lease(self, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        old = str(uuid.uuid4())
        new = str(uuid.uuid4())
        _set_active_lease(
            mongo_env,
            sid,
            new,
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )

        async def run():
            ok = await ac.release_action_lease(server.db, sid, old)
            assert not ok
            stored = await server.db.sessions.find_one({"id": sid})
            assert stored["action_lock_token"] == new

        _run_db(run())

    def test_release_is_idempotent(self, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        token = str(uuid.uuid4())
        _set_active_lease(
            mongo_env,
            sid,
            token,
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )

        async def run():
            assert await ac.release_action_lease(server.db, sid, token)
            assert not await ac.release_action_lease(server.db, sid, token)

        _run_db(run())

    def test_next_turn_number_from_locked_session(self, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id, turn_count=5)

        async def run():
            session, _token = await ac.acquire_action_lease(
                server.db, sid, device_id, now=FIXED_NOW
            )
            assert session.get("turn_count", 0) + 1 == 6

        _run_db(run())

    def test_persist_cas_filter_requires_turn_count_and_token(self):
        filt = ac.build_persist_cas_filter("sid", "tok", 4)
        assert filt == {
            "id": "sid",
            "action_lock_token": "tok",
            "turn_count": 4,
        }


# ---------------------------------------------------------------------------
# HTTP conflict tests (4–7, 21–22, 24–27, 30–32)
# ---------------------------------------------------------------------------
class TestStoryActionConflict:
    def test_conflict_returns_http_409(self, client, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        _set_active_lease(
            mongo_env,
            sid,
            str(uuid.uuid4()),
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )
        ac.set_clock_for_tests(FIXED_NOW)
        r = client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "look around"},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert r.status_code == 409
        assert r.json()["detail"] == ACTION_CONFLICT_DETAIL

    def test_conflict_makes_zero_provider_calls(self, client, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        _set_active_lease(
            mongo_env,
            sid,
            str(uuid.uuid4()),
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )
        ac.set_clock_for_tests(FIXED_NOW)
        client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "look around"},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert client.llm_calls["n"] == 0

    def test_conflict_creates_no_turn(self, client, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        _set_active_lease(
            mongo_env,
            sid,
            str(uuid.uuid4()),
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )
        ac.set_clock_for_tests(FIXED_NOW)
        client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "look around"},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert mongo_env.turns.count_documents({"session_id": sid}) == 0

    def test_conflict_changes_no_gameplay_session_fields(self, client, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        rolling = _registry(_entry(SECRET_A))
        sid = _insert_session(mongo_env, device_id, rolling=rolling)
        before = copy.deepcopy(mongo_env.sessions.find_one({"id": sid}))
        _set_active_lease(
            mongo_env,
            sid,
            str(uuid.uuid4()),
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )
        ac.set_clock_for_tests(FIXED_NOW)
        client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "Reveal my secret."},
            headers={DEVICE_ID_HEADER: device_id},
        )
        after = mongo_env.sessions.find_one({"id": sid})
        assert after["turn_count"] == before["turn_count"]
        assert after["rolling_state"] == before["rolling_state"]

    def test_provider_failure_releases_lease(self, client, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)

        async def boom(**_kwargs):
            raise AIServiceError("down")

        original = gateway.invoke_llm
        gateway.invoke_llm = boom
        try:
            r = client.post(
                "/api/story/action",
                json={"session_id": sid, "action_text": "look"},
                headers={DEVICE_ID_HEADER: device_id},
            )
            assert r.status_code == 502
        finally:
            gateway.invoke_llm = original
        stored = mongo_env.sessions.find_one({"id": sid})
        assert "action_lock_token" not in stored or stored.get("action_lock_token") is None

    def test_validation_exception_releases_lease(self, client, mongo_env, monkeypatch):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)

        async def boom_gen(*_a, **_k):
            raise RuntimeError("validation pipeline failed")

        monkeypatch.setattr(server, "_generate_validated_turn", boom_gen)
        r = client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "look"},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert r.status_code == 502
        stored = mongo_env.sessions.find_one({"id": sid})
        assert "action_lock_token" not in stored or stored.get("action_lock_token") is None

    def test_successful_action_preserves_response_contract(self, client, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        r = client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "look around"},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert r.status_code == 200
        body = r.json()
        assert "turn" in body
        turn = body["turn"]
        assert turn["session_id"] == sid
        assert turn["turn_number"] == 2
        assert "rolling_state" not in turn
        assert "debug" not in turn

    def test_successful_action_at_most_two_provider_calls(self, client, mongo_env, monkeypatch):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)

        def always_fail(*_a, **_k):
            return False, "bad", "format"

        monkeypatch.setattr(server, "_full_validate", always_fail)
        client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "look"},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert client.llm_calls["n"] <= 2


# ---------------------------------------------------------------------------
# Persistence CAS (16–20)
# ---------------------------------------------------------------------------
class TestPersistenceCAS:
    def test_cas_conflict_returns_409_not_restore_snapshot(self, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        rolling = _registry(_entry(SECRET_A))
        sid = _insert_session(mongo_env, device_id, rolling=rolling)
        lease_token = str(uuid.uuid4())
        _set_active_lease(
            mongo_env,
            sid,
            lease_token,
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )
        winner_revealed = _registry(
            _entry(SECRET_A, revealed=True, revealed_turn=2, reveal_mode="player_confession")
        )
        mongo_env.sessions.update_one(
            {"id": sid},
            {"$set": {"turn_count": 2, "rolling_state": winner_revealed}},
        )
        turn_doc = {
            "id": str(uuid.uuid4()),
            "session_id": sid,
            "turn_number": 2,
            "player_action": "loser",
            "narrative": "loser",
            "paragraphs": ["loser"],
            "choices": [],
            "state": {"Health": "stable"},
            "ledger": {},
            "rolling_state": rolling,
        }
        update_set = {"turn_count": 2, "last_state": {"Health": "stable"}}

        async def run():
            with pytest.raises(ActionLeaseLost):
                await server._persist_story_action_turn(
                    sid,
                    2,
                    turn_doc,
                    update_set,
                    {"turn_count": 1, "rolling_state": rolling},
                    {"model_used": "test"},
                    lease_token=lease_token,
                    expected_turn_count=1,
                )

        _run_db(run())
        stored = mongo_env.sessions.find_one({"id": sid})
        assert stored["turn_count"] == 2
        assert stored["rolling_state"]["secret_registry"][0]["revealed"] is True
        assert mongo_env.turns.count_documents({"session_id": sid, "id": turn_doc["id"]}) == 0

    def test_lost_lease_deletes_only_exact_inserted_turn(self, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id, turn_count=1)
        winner_id = str(uuid.uuid4())
        loser_id = str(uuid.uuid4())
        mongo_env.turns.insert_one(
            {
                "id": winner_id,
                "session_id": sid,
                "turn_number": 3,
                "player_action": "winner",
                "narrative": "winner",
                "paragraphs": ["winner"],
                "choices": [],
                "state": {},
                "ledger": {},
                "rolling_state": {},
            }
        )
        lease_token = str(uuid.uuid4())
        _set_active_lease(
            mongo_env,
            sid,
            lease_token,
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )
        mongo_env.sessions.update_one({"id": sid}, {"$set": {"turn_count": 3}})
        turn_doc = {
            "id": loser_id,
            "session_id": sid,
            "turn_number": 2,
            "player_action": "loser",
            "narrative": "loser",
            "paragraphs": ["loser"],
            "choices": [],
            "state": {},
            "ledger": {},
            "rolling_state": {},
        }

        async def run():
            with pytest.raises(ActionLeaseLost):
                await server._persist_story_action_turn(
                    sid,
                    2,
                    turn_doc,
                    {"turn_count": 2},
                    {"turn_count": 1},
                    {},
                    lease_token=lease_token,
                    expected_turn_count=1,
                )

        _run_db(run())
        assert mongo_env.turns.count_documents({"session_id": sid, "id": winner_id}) == 1
        assert mongo_env.turns.count_documents({"session_id": sid, "id": loser_id}) == 0


# ---------------------------------------------------------------------------
# Overlap simulation (21–23)
# ---------------------------------------------------------------------------
class TestOverlapSimulation:
    def test_two_overlapping_requests_one_provider_call_one_turn(self, client, mongo_env):
        """Simulate overlap: owner holds lease while a second POST is rejected."""
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        owner_token = str(uuid.uuid4())
        _set_active_lease(
            mongo_env,
            sid,
            owner_token,
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )
        ac.set_clock_for_tests(FIXED_NOW)
        blocked = client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "blocked"},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert blocked.status_code == 409
        assert client.llm_calls["n"] == 0

        async def release_owner():
            await ac.release_action_lease(server.db, sid, owner_token)

        _run_db(release_owner())
        allowed = client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "allowed"},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert allowed.status_code == 200
        assert client.llm_calls["n"] == 1
        assert mongo_env.turns.count_documents({"session_id": sid}) == 1
        assert mongo_env.sessions.find_one({"id": sid})["turn_count"] == 2

    def test_no_duplicate_session_turn_number_rows(self, client, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "first"},
            headers={DEVICE_ID_HEADER: device_id},
        )
        pipeline = [
            {"$group": {"_id": {"session_id": "$session_id", "turn_number": "$turn_number"}, "c": {"$sum": 1}}},
            {"$match": {"c": {"$gt": 1}}},
        ]
        dupes = list(mongo_env.turns.aggregate(pipeline))
        assert dupes == []


# ---------------------------------------------------------------------------
# Secret reveal concurrency (34–35, 38)
# ---------------------------------------------------------------------------
class TestSecretRevealConcurrency:
    def test_confession_by_lock_owner_reveals_once(self, client, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        rolling = _registry(_entry(SECRET_A))
        sid = _insert_session(mongo_env, device_id, rolling=rolling)
        r = client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "Reveal my secret."},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert r.status_code == 200
        stored = mongo_env.sessions.find_one({"id": sid})
        assert stored["rolling_state"]["secret_registry"][0]["revealed"] is True

    def test_rejected_concurrent_confession_reveals_nothing(self, client, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        rolling = _registry(_entry(SECRET_A))
        sid = _insert_session(mongo_env, device_id, rolling=rolling)
        _set_active_lease(
            mongo_env,
            sid,
            str(uuid.uuid4()),
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )
        ac.set_clock_for_tests(FIXED_NOW)
        r = client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "Reveal my secret."},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert r.status_code == 409
        assert client.llm_calls["n"] == 0
        assert client.directive_seen["value"] is None
        stored = mongo_env.sessions.find_one({"id": sid})
        assert stored["rolling_state"]["secret_registry"][0]["revealed"] is False

    def test_lease_fields_absent_from_llm_prompt_construction(self, mongo_env):
        rolling = _registry(_entry(SECRET_A))
        session = {
            "id": "s1",
            "turn_count": 1,
            "rolling_state": rolling,
            "action_lock_token": "hidden",
            "action_lock_acquired_at": FIXED_NOW,
            "action_lock_expires_at": FIXED_NOW,
        }
        safe = server._prompt_safe_rolling(session.get("rolling_state"))
        assert "action_lock_token" not in json.dumps(safe)


# ---------------------------------------------------------------------------
# Player payload safety (36–37, 39)
# ---------------------------------------------------------------------------
class TestPlayerPayloadSafety:
    def test_lease_fields_absent_from_player_session_serializer(self, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        _set_active_lease(
            mongo_env,
            sid,
            str(uuid.uuid4()),
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )
        raw = mongo_env.sessions.find_one({"id": sid})
        out = player_api.build_player_session(raw)
        for field in ACTION_LOCK_FIELDS:
            assert field not in out

    def test_lease_fields_absent_from_player_safe_export(self, client, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        _set_active_lease(
            mongo_env,
            sid,
            str(uuid.uuid4()),
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )
        r = client.get(
            f"/api/story/session/{sid}/export",
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert r.status_code == 200
        payload = json.dumps(r.json())
        for field in ACTION_LOCK_FIELDS:
            assert field not in payload

    def test_raw_admin_export_may_include_lease_fields(self, client, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        token = str(uuid.uuid4())
        _set_active_lease(
            mongo_env,
            sid,
            token,
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )
        r = client.get(
            f"/api/story/session/{sid}/export/raw",
            headers={ADMIN_API_KEY_HEADER: TEST_ADMIN_KEY},
        )
        assert r.status_code == 200
        assert r.json()["session"].get("action_lock_token") == token


# ---------------------------------------------------------------------------
# Release failure + cancellation (27–29)
# ---------------------------------------------------------------------------
class TestReleaseEdgeCases:
    def test_release_failure_does_not_expose_internals(self, client, mongo_env, monkeypatch):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)

        async def fail_release(*_a, **_k):
            raise RuntimeError("release failed")

        monkeypatch.setattr(ac, "release_action_lease", fail_release)
        r = client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "look"},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert r.status_code == 200
        assert "action_lock" not in r.text.lower()

    def test_stale_request_cannot_release_current_owner_lease(self, mongo_env):
        device_id = f"dev_{uuid.uuid4()}"
        sid = _insert_session(mongo_env, device_id)
        old = str(uuid.uuid4())
        new = str(uuid.uuid4())
        _set_active_lease(
            mongo_env,
            sid,
            new,
            expires_at=FIXED_NOW + timedelta(seconds=600),
        )

        async def run():
            ok = await ac.release_action_lease(server.db, sid, old)
            assert not ok
            stored = await server.db.sessions.find_one({"id": sid})
            assert stored["action_lock_token"] == new

        _run_db(run())


# ---------------------------------------------------------------------------
# Index setup (40–41)
# ---------------------------------------------------------------------------
class TestIndexSetup:
    def test_unique_index_setup_idempotent(self, mongo_env):
        async def run():
            await ac.ensure_action_concurrency_indexes(server.db)
            await ac.ensure_action_concurrency_indexes(server.db)
            indexes = await server.db.turns.index_information()
            assert "turns_session_turn_unique" in indexes

        _run_db(run())

    def test_duplicate_detection_defers_unique_index(self, mongo_env, monkeypatch):
        created = {"called": False}

        async def fake_dupes(_db):
            return [{"_id": {"session_id": "s", "turn_number": 2}, "count": 2}]

        async def fake_create(*_a, **_k):
            created["called"] = True

        monkeypatch.setattr(ac, "find_duplicate_turn_numbers", fake_dupes)
        monkeypatch.setattr(server.db.turns, "create_index", fake_create)

        async def run():
            await ac.ensure_action_concurrency_indexes(server.db)

        _run_db(run())
        assert not created["called"]