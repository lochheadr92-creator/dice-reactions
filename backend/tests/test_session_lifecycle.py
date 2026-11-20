"""
Session lifecycle under the lease + revision contract: reset/delete during
generation, lease expiry with a stale worker, competing commits at one
revision, worker-restart recovery, transient/ambiguous transactions, and
fail-closed behaviour when transactions are unavailable.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from pymongo.errors import ConnectionFailure, OperationFailure

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import action_concurrency as ac  # noqa: E402
import action_requests  # noqa: E402
import server  # noqa: E402
import turn_commit  # noqa: E402
from security import DEVICE_ID_HEADER  # noqa: E402
from reliability_support import (  # noqa: E402
    ACTION_TURN,
    FIXED_NOW,
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
    turn_commit.set_checkpoint_hook_for_tests(None)
    ac.set_clock_for_tests(None)
    mongo.close()


@pytest.fixture()
def fake_llm():
    fake = FakeGateway(ACTION_TURN).install()
    yield fake
    fake.restore()


@pytest.fixture()
def client(env, fake_llm):
    with make_client() as tc:
        yield tc


def _headers(device):
    return {DEVICE_ID_HEADER: device}


def _turn_doc(sid, number, text="stale"):
    return {
        "id": str(uuid.uuid4()),
        "session_id": sid,
        "turn_number": number,
        "player_action": text,
        "narrative": text,
        "paragraphs": [text],
        "choices": [],
        "state": {"Health": "stable"},
        "ledger": {},
        "rolling_state": {},
    }


# ---------------------------------------------------------------------------
# Reset / delete during generation
# ---------------------------------------------------------------------------
def test_reset_and_delete_are_rejected_while_an_action_holds_the_lease(client, env):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    _session, token = run_db(ac.acquire_action_lease(env.async_db, sid, device))
    reset = client.post(f"/api/story/session/{sid}/reset", headers=_headers(device))
    assert reset.status_code == 409
    delete = client.delete(f"/api/story/session/{sid}", headers=_headers(device))
    assert delete.status_code == 409
    assert env.sync_db.sessions.find_one({"id": sid})["turn_count"] == 1
    run_db(ac.release_action_lease(env.async_db, sid, token))
    assert client.post(f"/api/story/session/{sid}/reset", headers=_headers(device)).status_code == 200


def test_reset_after_lease_expiry_blocks_the_stale_generation_commit(client, env):
    """Worker A stalls past its lease; the player resets; A's late commit is refused."""
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    ac.set_clock_for_tests(FIXED_NOW)
    session, stale_token = run_db(ac.acquire_action_lease(env.async_db, sid, device))
    expected_turn_count = session["turn_count"]
    expected_revision = session[ac.SESSION_REVISION_FIELD]

    # Lease expires; the reset acquires its own lease and bumps the revision.
    ac.set_clock_for_tests(FIXED_NOW + timedelta(seconds=ac.resolve_lease_seconds() + 1))
    reset = client.post(f"/api/story/session/{sid}/reset", headers=_headers(device))
    assert reset.status_code == 200
    after_reset = env.sync_db.sessions.find_one({"id": sid})
    assert after_reset["turn_count"] == 0
    assert after_reset[ac.SESSION_REVISION_FIELD] == expected_revision + 1

    async def stale_commit():
        with pytest.raises(turn_commit.CommitPreconditionFailed):
            await server._commit_story_action_turn(
                sid,
                _turn_doc(sid, expected_turn_count + 1),
                {"turn_count": expected_turn_count + 1},
                {},
                lease_token=stale_token,
                expected_turn_count=expected_turn_count,
                expected_revision=expected_revision,
            )

    run_db(stale_commit())
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 0
    assert env.sync_db.sessions.find_one({"id": sid})["turn_count"] == 0


def test_revision_blocks_stale_commit_even_when_turn_count_returns_to_same_value(client, env):
    """turn_count 0 → (reset) → 0 again: only the revision distinguishes the generations."""
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device, turn_count=0)
    ac.set_clock_for_tests(FIXED_NOW)
    session, stale_token = run_db(ac.acquire_action_lease(env.async_db, sid, device))
    ac.set_clock_for_tests(FIXED_NOW + timedelta(seconds=ac.resolve_lease_seconds() + 1))
    assert client.post(f"/api/story/session/{sid}/reset", headers=_headers(device)).status_code == 200
    # A fresh action lease (new token) is now held by nobody; the stale worker still tries.
    assert env.sync_db.sessions.find_one({"id": sid})["turn_count"] == 0

    async def stale_commit():
        with pytest.raises(turn_commit.CommitPreconditionFailed):
            await server._commit_story_action_turn(
                sid,
                _turn_doc(sid, 1),
                {"turn_count": 1},
                {},
                lease_token=stale_token,
                expected_turn_count=0,
                expected_revision=session[ac.SESSION_REVISION_FIELD],
            )

    run_db(stale_commit())
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 0


def test_delete_after_lease_expiry_blocks_stale_commit_and_removes_request_records(client, env, fake_llm):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    rid = f"act-{uuid.uuid4()}"
    assert client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "wait", "action_request_id": rid},
        headers=_headers(device),
    ).status_code == 200
    ac.set_clock_for_tests(FIXED_NOW)
    session, stale_token = run_db(ac.acquire_action_lease(env.async_db, sid, device))
    ac.set_clock_for_tests(FIXED_NOW + timedelta(seconds=ac.resolve_lease_seconds() + 1))
    assert client.delete(f"/api/story/session/{sid}", headers=_headers(device)).status_code == 200
    assert env.sync_db.sessions.count_documents({"id": sid}) == 0
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 0
    assert env.sync_db.action_requests.count_documents({"session_id": sid}) == 0

    async def stale_commit():
        with pytest.raises(turn_commit.CommitPreconditionFailed):
            await server._commit_story_action_turn(
                sid,
                _turn_doc(sid, 3),
                {"turn_count": 3},
                {},
                lease_token=stale_token,
                expected_turn_count=2,
                expected_revision=session[ac.SESSION_REVISION_FIELD],
            )

    run_db(stale_commit())
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 0
    assert client.get(f"/api/story/session/{sid}", headers=_headers(device)).status_code == 404


def test_reset_supersedes_incomplete_request_records(client, env):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    now = ac.utc_now()
    env.sync_db.action_requests.insert_one(
        {
            "_id": f"{sid}|stuck",
            "session_id": sid,
            "device_id": device,
            "request_id": "stuck",
            "fingerprint": "x",
            "status": "uncertain",
            "created_at": now,
            "updated_at": now,
            "expires_at": now + timedelta(days=1),
        }
    )
    assert client.post(f"/api/story/session/{sid}/reset", headers=_headers(device)).status_code == 200
    record = env.sync_db.action_requests.find_one({"_id": f"{sid}|stuck"})
    assert record["status"] == "failed"
    assert record["error_kind"] == action_requests.ERROR_SUPERSEDED


# ---------------------------------------------------------------------------
# Competing workers
# ---------------------------------------------------------------------------
def test_second_lease_acquisition_is_rejected_until_release_or_expiry(env):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    ac.set_clock_for_tests(FIXED_NOW)
    _s, token = run_db(ac.acquire_action_lease(env.async_db, sid, device))

    async def second():
        with pytest.raises(ac.ActionLeaseConflict):
            await ac.acquire_action_lease(env.async_db, sid, device)

    run_db(second())
    ac.set_clock_for_tests(FIXED_NOW + timedelta(seconds=ac.resolve_lease_seconds() + 1))
    _s2, token2 = run_db(ac.acquire_action_lease(env.async_db, sid, device))
    assert token2 != token
    # The expired worker can no longer release the new owner's lease.
    assert run_db(ac.release_action_lease(env.async_db, sid, token)) is False
    assert env.sync_db.sessions.find_one({"id": sid})["action_lock_token"] == token2


def test_two_commits_at_the_same_revision_admit_exactly_one(env):
    """Even with the lease check bypassed by identical tokens, the revision CAS admits one commit."""
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    session, token = run_db(ac.acquire_action_lease(env.async_db, sid, device))
    rev = session[ac.SESSION_REVISION_FIELD]
    docs = [_turn_doc(sid, 2, "a"), _turn_doc(sid, 2, "b")]

    async def attempt(doc):
        try:
            await server._commit_story_action_turn(
                sid, doc, {"turn_count": 2}, {}, lease_token=token,
                expected_turn_count=1, expected_revision=rev,
            )
            return "committed"
        except turn_commit.CommitPreconditionFailed:
            return "rejected"

    async def race():
        return await asyncio.gather(attempt(docs[0]), attempt(docs[1]))

    outcomes = run_db(race())
    assert sorted(outcomes) == ["committed", "rejected"]
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1
    stored = env.sync_db.sessions.find_one({"id": sid})
    assert stored["turn_count"] == 2
    assert stored[ac.SESSION_REVISION_FIELD] == rev + 1
    assert stored.get("action_lock_token") is None


# ---------------------------------------------------------------------------
# Worker restart recovery
# ---------------------------------------------------------------------------
def test_recovery_after_worker_restart_with_expired_lease_and_claim(client, env, fake_llm):
    """A crashed worker left an expired lease + claim; the retried request completes once."""
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    rid = f"act-{uuid.uuid4()}"
    past = ac.utc_now() - timedelta(seconds=5)
    env.sync_db.sessions.update_one(
        {"id": sid},
        {"$set": {"action_lock_token": "dead-worker", "action_lock_acquired_at": past, "action_lock_expires_at": past}},
    )
    env.sync_db.action_requests.insert_one(
        {
            "_id": action_requests.request_key(sid, rid),
            "session_id": sid,
            "device_id": device,
            "request_id": rid,
            "fingerprint": action_requests.fingerprint(sid, "wait", False),
            "status": "in_progress",
            "claim_token": "dead-worker",
            "claim_expires_at": past,
            "attempts": 1,
            "created_at": past,
            "updated_at": past,
            "expires_at": past + timedelta(days=1),
        }
    )
    res = client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "wait", "action_request_id": rid},
        headers=_headers(device),
    )
    assert res.status_code == 200, res.text
    assert fake_llm.calls == 1
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1
    record = env.sync_db.action_requests.find_one({"_id": action_requests.request_key(sid, rid)})
    assert record["status"] == "completed" and record["attempts"] == 2
    assert env.sync_db.sessions.find_one({"id": sid}).get("action_lock_token") is None


# ---------------------------------------------------------------------------
# Transaction mechanics: transient retry, ambiguous commit, unsupported topology
# ---------------------------------------------------------------------------
def test_transient_transaction_error_reruns_db_callback_without_second_provider_call(client, env, fake_llm):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    seen = []

    def transient_once(name):
        seen.append(name)
        if name == "after_session_update" and seen.count("after_session_update") == 1:
            raise OperationFailure("write conflict", 112, {"errorLabels": ["TransientTransactionError"]})

    turn_commit.set_checkpoint_hook_for_tests(transient_once)
    res = client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "wait", "action_request_id": f"act-{uuid.uuid4()}"},
        headers=_headers(device),
    )
    assert res.status_code == 200, res.text
    assert seen.count("before_session_update") == 2  # callback re-ran
    assert fake_llm.calls == 1  # provider work was NOT repeated
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1
    assert env.sync_db.sessions.find_one({"id": sid})["turn_count"] == 2


def test_ambiguous_commit_acknowledgement_is_verified_not_replayed(client, env, fake_llm, monkeypatch):
    real_run = turn_commit._run_transaction

    async def commit_then_lose_ack(db, callback):
        await real_run(db, callback)
        raise ConnectionFailure("socket closed while reading commit reply")

    monkeypatch.setattr(turn_commit, "_run_transaction", commit_then_lose_ack)
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    rid = f"act-{uuid.uuid4()}"
    res = client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "wait", "action_request_id": rid},
        headers=_headers(device),
    )
    assert res.status_code == 200, res.text
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1
    assert env.sync_db.sessions.find_one({"id": sid})["turn_count"] == 2
    assert env.sync_db.action_requests.find_one({"_id": f"{sid}|{rid}"})["status"] == "completed"


def test_lost_acknowledgement_without_commit_reports_uncertain_then_retries_cleanly(client, env, fake_llm, monkeypatch):
    real_run = turn_commit._run_transaction

    async def never_committed(db, callback):
        raise ConnectionFailure("network partition before commit")

    monkeypatch.setattr(turn_commit, "_run_transaction", never_committed)
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    rid = f"act-{uuid.uuid4()}"
    res = client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "wait", "action_request_id": rid},
        headers=_headers(device),
    )
    assert res.status_code == 503
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 0
    record = env.sync_db.action_requests.find_one({"_id": f"{sid}|{rid}"})
    assert record["status"] == "uncertain"
    monkeypatch.setattr(turn_commit, "_run_transaction", real_run)
    retry = client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "wait", "action_request_id": rid},
        headers=_headers(device),
    )
    assert retry.status_code == 200
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1


def test_lease_and_claim_outlive_the_generation_deadline(monkeypatch):
    """A retry must not be able to take over an action that is still generating."""
    import provider_budget

    monkeypatch.setattr(provider_budget, "ACTION_GENERATION_DEADLINE_SEC", 1000)
    monkeypatch.setenv(ac.LEASE_ENV_VAR, "60")
    assert ac.resolve_lease_seconds() >= 1060
    assert action_requests.claim_ttl_seconds() == ac.resolve_lease_seconds()
    monkeypatch.setattr(provider_budget, "ACTION_GENERATION_DEADLINE_SEC", 240)
    monkeypatch.delenv(ac.LEASE_ENV_VAR, raising=False)
    assert ac.resolve_lease_seconds() == ac.DEFAULT_LEASE_SECONDS
    monkeypatch.setenv(ac.LEASE_ENV_VAR, "60")
    assert ac.resolve_lease_seconds() == 300


def test_no_transaction_error_is_classified():
    exc = OperationFailure(
        "Transaction numbers are only allowed on a replica set member or mongos", 20, {}
    )
    assert turn_commit._is_no_transaction_error(exc) is True
    assert turn_commit._is_no_transaction_error(OperationFailure("other", 11000, {})) is False


def test_unavailable_transaction_support_fails_closed_for_writes_only(env, fake_llm, monkeypatch):
    async def unsupported(_db):
        raise turn_commit.TransactionSupportUnavailable("standalone server")

    monkeypatch.setattr(turn_commit, "check_transaction_support", unsupported)
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    try:
        with make_client() as client:
            assert server._TRANSACTION_SUPPORT_ERROR
            action = client.post(
                "/api/story/action", json={"session_id": sid, "action_text": "wait"}, headers=_headers(device)
            )
            assert action.status_code == 503
            assert action.json()["detail"] == "Service unavailable"
            assert client.post("/api/story/new", json={"device_id": device, "genre": "fantasy"}).status_code == 503
            assert client.post(f"/api/story/session/{sid}/reset", headers=_headers(device)).status_code == 503
            assert client.delete(f"/api/story/session/{sid}", headers=_headers(device)).status_code == 503
            assert client.get(f"/api/story/session/{sid}", headers=_headers(device)).status_code == 200
            assert client.get("/api/story/sessions", headers=_headers(device)).status_code == 200
    finally:
        server._TRANSACTION_SUPPORT_ERROR = None
    assert fake_llm.calls == 0
    assert env.sync_db.sessions.find_one({"id": sid})["turn_count"] == 1


def test_commit_refuses_when_transaction_runner_reports_no_support(env, monkeypatch):
    async def no_support(db, callback):
        raise turn_commit.TransactionSupportUnavailable("standalone")

    monkeypatch.setattr(turn_commit, "_run_transaction", no_support)
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    session, token = run_db(ac.acquire_action_lease(env.async_db, sid, device))

    async def attempt():
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await server._commit_story_action_turn(
                sid, _turn_doc(sid, 2), {"turn_count": 2}, {}, lease_token=token,
                expected_turn_count=1, expected_revision=session[ac.SESSION_REVISION_FIELD],
            )
        assert exc.value.status_code == 503

    run_db(attempt())
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 0
    assert env.sync_db.sessions.find_one({"id": sid})["turn_count"] == 1
