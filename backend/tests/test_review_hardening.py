"""
Hardening from the 2026-11-20 adversarial review:
  finding 7  - invalid creation requests do not consume creation quota
  finding 12 - non-ASCII credentials are rejected, never answered with 500
  finding 14 - one action request key maps to at most one turn (unique index)
  finding 8  - startup lease clearing for single-process deployments

Real disposable MongoDB (replica set) + FastAPI TestClient + scripted gateway.
"""

from __future__ import annotations

import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from pymongo.errors import DuplicateKeyError

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import action_concurrency as ac  # noqa: E402
import action_requests  # noqa: E402
import provider_budget  # noqa: E402
import rate_limit  # noqa: E402
import server  # noqa: E402
from security import ADMIN_API_KEY_HEADER, DEVICE_ID_HEADER, constant_time_equals  # noqa: E402
from reliability_support import (  # noqa: E402
    FIXED_NOW,
    OPENING_TURN,
    FakeGateway,
    MongoEnv,
    insert_session,
    make_client,
    relax_rate_limits,
    run_db,
)


@pytest.fixture()
def env(monkeypatch):
    mongo = MongoEnv()
    relax_rate_limits(monkeypatch)
    ac.set_clock_for_tests(None)
    yield mongo
    ac.set_clock_for_tests(None)
    mongo.close()


@pytest.fixture()
def fake_llm():
    fake = FakeGateway(OPENING_TURN).install()
    yield fake
    fake.restore()


# ---------------------------------------------------------------------------
# Creation quota is refunded for 4xx answers
# ---------------------------------------------------------------------------
def test_invalid_creation_requests_do_not_consume_quota(env, fake_llm, monkeypatch):
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_DEVICE_MAX", 2)
    device = f"dev_{uuid.uuid4()}"
    bad = {"device_id": device, "genre": "fantasy", "scenario_id": "no-such-scenario"}
    with make_client() as client:
        codes = [client.post("/api/story/new", json=bad).status_code for _ in range(3)]
        good = client.post("/api/story/new", json={"device_id": device, "genre": "fantasy"})
    assert codes == [422, 422, 422]
    assert good.status_code == 200, good.text
    device_count = sum(
        int(d.get("count", 0))
        for d in env.sync_db.rate_limits.find({"_id": {"$regex": "^device:"}})
    )
    assert device_count == 1


def test_failed_paid_creation_still_consumes_quota(env, monkeypatch):
    device = f"dev_{uuid.uuid4()}"
    fake = FakeGateway(on_request=lambda _n, _kw: (_ for _ in ()).throw(RuntimeError("down"))).install()
    try:
        with make_client() as client:
            response = client.post("/api/story/new", json={"device_id": device, "genre": "fantasy"})
    finally:
        fake.restore()
    assert response.status_code == 502
    device_count = sum(
        int(d.get("count", 0))
        for d in env.sync_db.rate_limits.find({"_id": {"$regex": "^device:"}})
    )
    assert device_count == 1


# ---------------------------------------------------------------------------
# Non-ASCII credentials
# ---------------------------------------------------------------------------
def test_constant_time_equals_accepts_any_text():
    assert constant_time_equals("é", "é")
    assert not constant_time_equals("é", "e")
    assert not constant_time_equals("abc", "abcd")


def test_non_ascii_admin_key_and_device_id_are_rejected_not_500(env):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    latin1 = "é".encode("latin-1")
    with make_client() as client:
        admin = client.get("/api/admin/settings", headers={ADMIN_API_KEY_HEADER.encode(): latin1})
        session = client.get(f"/api/story/session/{sid}", headers={DEVICE_ID_HEADER.encode(): latin1})
        action = client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "wait"},
            headers={DEVICE_ID_HEADER.encode(): latin1},
        )
    assert admin.status_code == 401
    assert session.status_code == 404
    assert action.status_code == 404


# ---------------------------------------------------------------------------
# Unique request key
# ---------------------------------------------------------------------------
def test_turn_request_key_is_unique(env):
    with make_client():
        pass  # startup creates the indexes
    info = env.sync_db.turns.index_information()
    index = info[action_requests.TURN_REQUEST_KEY_UNIQUE_INDEX]
    assert index.get("unique") is True
    key = f"session|req-{uuid.uuid4()}"
    env.sync_db.turns.insert_one({"id": str(uuid.uuid4()), "session_id": "s1", "turn_number": 1, "action_request_key": key})
    with pytest.raises(DuplicateKeyError):
        env.sync_db.turns.insert_one({"id": str(uuid.uuid4()), "session_id": "s1", "turn_number": 2, "action_request_key": key})
    # Turns without a request key (legacy clients) are not constrained.
    env.sync_db.turns.insert_one({"id": str(uuid.uuid4()), "session_id": "s1", "turn_number": 3})
    env.sync_db.turns.insert_one({"id": str(uuid.uuid4()), "session_id": "s1", "turn_number": 4})


def test_existing_duplicate_request_keys_do_not_block_startup(env):
    if action_requests.TURN_REQUEST_KEY_UNIQUE_INDEX in env.sync_db.turns.index_information():
        env.sync_db.turns.drop_index(action_requests.TURN_REQUEST_KEY_UNIQUE_INDEX)
    key = f"session|dup-{uuid.uuid4()}"
    for n in (1, 2):
        env.sync_db.turns.insert_one({"id": str(uuid.uuid4()), "session_id": "dup", "turn_number": n, "action_request_key": key})
    run_db(action_requests.ensure_action_request_indexes(server.db))
    assert action_requests.TURN_REQUEST_KEY_UNIQUE_INDEX not in env.sync_db.turns.index_information()
    env.sync_db.turns.delete_many({"session_id": "dup"})


# ---------------------------------------------------------------------------
# Lease lifetime and startup clearing
# ---------------------------------------------------------------------------
def test_default_lease_is_generation_deadline_plus_commit_slack(monkeypatch):
    monkeypatch.delenv(ac.LEASE_ENV_VAR, raising=False)
    assert ac.resolve_lease_seconds() == provider_budget.ACTION_GENERATION_DEADLINE_SEC + 60


def _seed_dead_worker_state(env, device):
    sid = insert_session(env.sync_db, device)
    env.sync_db.sessions.update_one(
        {"id": sid},
        {"$set": {
            ac.ACTION_LOCK_TOKEN_FIELD: "dead-worker",
            ac.ACTION_LOCK_ACQUIRED_AT_FIELD: FIXED_NOW,
            ac.ACTION_LOCK_EXPIRES_AT_FIELD: FIXED_NOW + timedelta(days=3650),
        }},
    )
    key = action_requests.request_key(sid, "req-dead")
    env.sync_db.action_requests.insert_one({
        "_id": key, "session_id": sid, "device_id": device, "request_id": "req-dead",
        "fingerprint": "f", "status": "in_progress", "claim_token": "dead",
        "claim_expires_at": FIXED_NOW + timedelta(days=3650),
    })
    env.sync_db.rate_limits.update_one(
        {"_id": provider_budget.PROVIDER_CONCURRENCY_POOL_ID},
        {"$set": {"leases": [{"token": "dead", "owner": "dead", "acquired_at": FIXED_NOW,
                              "expires_at": FIXED_NOW + timedelta(days=3650)}]}},
        upsert=True,
    )
    return sid, key


def test_startup_keeps_leases_when_clearing_is_not_enabled(env, monkeypatch):
    device = f"dev_{uuid.uuid4()}"
    sid, _key = _seed_dead_worker_state(env, device)
    monkeypatch.delenv(ac.CLEAR_LEASES_ENV_VAR, raising=False)
    with make_client():
        pass
    assert env.sync_db.sessions.find_one({"id": sid}).get(ac.ACTION_LOCK_TOKEN_FIELD) == "dead-worker"
    pool = env.sync_db.rate_limits.find_one({"_id": provider_budget.PROVIDER_CONCURRENCY_POOL_ID})
    assert len(pool["leases"]) == 1


def test_startup_clears_dead_leases_when_enabled(env, monkeypatch):
    device = f"dev_{uuid.uuid4()}"
    sid, key = _seed_dead_worker_state(env, device)
    monkeypatch.setenv(ac.CLEAR_LEASES_ENV_VAR, "1")
    with make_client():
        pass
    session = env.sync_db.sessions.find_one({"id": sid})
    assert ac.ACTION_LOCK_TOKEN_FIELD not in session
    record = env.sync_db.action_requests.find_one({"_id": key})
    assert record["status"] == "in_progress"  # resolved on next read, not rewritten here
    pool = env.sync_db.rate_limits.find_one({"_id": provider_budget.PROVIDER_CONCURRENCY_POOL_ID})
    assert pool["leases"] == []


def test_expired_claim_after_startup_resolves_as_retryable(env, monkeypatch):
    device = f"dev_{uuid.uuid4()}"
    sid, key = _seed_dead_worker_state(env, device)
    monkeypatch.setenv(ac.CLEAR_LEASES_ENV_VAR, "1")
    with make_client() as client:
        status = client.get(
            f"/api/story/session/{sid}/action/req-dead", headers={DEVICE_ID_HEADER: device}
        )
    assert status.json() == {"status": "failed", "error_kind": "interrupted"}
