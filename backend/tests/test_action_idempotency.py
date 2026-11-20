"""
Action request idempotency — POST /story/action with ``action_request_id``.

Real disposable MongoDB (replica set) + FastAPI TestClient + scripted gateway.
One submitted request id ⇒ at most one committed game transition.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import action_concurrency as ac  # noqa: E402
import action_requests  # noqa: E402
import server  # noqa: E402
import turn_commit  # noqa: E402
from security import DEVICE_ID_HEADER  # noqa: E402
from reliability_support import (  # noqa: E402
    ACTION_TURN,
    FakeGateway,
    MongoEnv,
    insert_session,
    make_client,
    relax_rate_limits,
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


def _post(client, sid, device, text="wait", request_id=None, debug=False):
    body = {"session_id": sid, "action_text": text, "debug_mode": debug}
    if request_id is not None:
        body["action_request_id"] = request_id
    return client.post("/api/story/action", json=body, headers={DEVICE_ID_HEADER: device})


def _device_action_buckets(sync_db) -> int:
    return sum(
        int(doc.get("count", 0))
        for doc in sync_db.rate_limits.find({"_id": {"$regex": "^action-device:"}})
    )


# ---------------------------------------------------------------------------
# Sequential duplicates
# ---------------------------------------------------------------------------
def test_sequential_duplicate_returns_saved_turn_without_new_transition(client, env, fake_llm):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    rid = f"act-{uuid.uuid4()}"

    first = _post(client, sid, device, request_id=rid)
    assert first.status_code == 200, first.text
    turn_id = first.json()["turn"]["id"]
    quota_after_first = _device_action_buckets(env.sync_db)
    usage_after_first = env.sync_db.provider_usage.count_documents({})

    second = _post(client, sid, device, request_id=rid)
    assert second.status_code == 200, second.text
    assert second.json()["turn"]["id"] == turn_id
    assert second.json()["turn"]["turn_number"] == 2
    assert second.json().get("replayed") is True

    assert fake_llm.calls == 1
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1
    assert env.sync_db.sessions.find_one({"id": sid})["turn_count"] == 2
    # A completed retry is free: no new quota reservation, no new usage rows.
    assert _device_action_buckets(env.sync_db) == quota_after_first
    assert env.sync_db.provider_usage.count_documents({}) == usage_after_first
    record = env.sync_db.action_requests.find_one({"_id": f"{sid}|{rid}"})
    assert record["status"] == "completed"
    assert record["turn_id"] == turn_id


def test_legacy_request_without_id_is_not_idempotent_and_documented(client, env, fake_llm):
    """Legacy clients (no action_request_id) keep the pre-release behaviour."""
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    first = _post(client, sid, device)
    second = _post(client, sid, device)
    assert first.status_code == 200 and second.status_code == 200
    assert [first.json()["turn"]["turn_number"], second.json()["turn"]["turn_number"]] == [2, 3]
    assert fake_llm.calls == 2
    assert env.sync_db.action_requests.count_documents({"session_id": sid}) == 0


# ---------------------------------------------------------------------------
# Simultaneous duplicates
# ---------------------------------------------------------------------------
def test_simultaneous_duplicates_commit_exactly_one_turn(env, monkeypatch):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    rid = f"act-{uuid.uuid4()}"

    async def slow_first(call_index):
        await asyncio.sleep(0.4)
        return ACTION_TURN

    fake = FakeGateway(ACTION_TURN, on_call=slow_first).install()
    try:
        with make_client() as client:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(_post, client, sid, device, "wait", rid) for _ in range(2)
                ]
                responses = [f.result() for f in futures]
            statuses = sorted(r.status_code for r in responses)
            assert statuses == [200, 409], [r.text for r in responses]
            conflict = next(r for r in responses if r.status_code == 409)
            assert conflict.json()["detail"] == ac.ACTION_CONFLICT_DETAIL

            # After the winner commits, the same id resolves to the saved turn.
            replay = _post(client, sid, device, "wait", rid)
            assert replay.status_code == 200
            status = client.get(
                f"/api/story/session/{sid}/action/{rid}", headers={DEVICE_ID_HEADER: device}
            )
            assert status.status_code == 200
            assert status.json()["status"] == "completed"
            assert status.json()["turn"]["id"] == replay.json()["turn"]["id"]
    finally:
        fake.restore()

    assert fake.calls == 1
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1
    assert env.sync_db.sessions.find_one({"id": sid})["turn_count"] == 2


# ---------------------------------------------------------------------------
# Mismatch / validation
# ---------------------------------------------------------------------------
def test_same_id_with_different_contents_is_a_clear_conflict(client, env, fake_llm):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    rid = f"act-{uuid.uuid4()}"
    assert _post(client, sid, device, "open the door", rid).status_code == 200
    mismatch = _post(client, sid, device, "run away", rid)
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"] == action_requests.REQUEST_MISMATCH_DETAIL
    assert fake_llm.calls == 1
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1


def test_debug_flag_is_part_of_request_identity(client, env, fake_llm):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    rid = f"act-{uuid.uuid4()}"
    assert _post(client, sid, device, "wait", rid, debug=False).status_code == 200
    assert _post(client, sid, device, "wait", rid, debug=True).status_code == 409


def test_input_limits_reject_before_quota_or_provider(client, env, fake_llm, monkeypatch):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    monkeypatch.setattr(server, "ACTION_TEXT_MAX_CHARS", 20)
    too_long = _post(client, sid, device, "x" * 21, f"act-{uuid.uuid4()}")
    assert too_long.status_code == 422
    assert "too long" in too_long.json()["detail"]
    empty = _post(client, sid, device, "   ", f"act-{uuid.uuid4()}")
    assert empty.status_code == 422
    assert fake_llm.calls == 0
    assert _device_action_buckets(env.sync_db) == 0
    assert env.sync_db.action_requests.count_documents({"session_id": sid}) == 0
    assert env.sync_db.sessions.find_one({"id": sid}).get("action_lock_token") is None


# ---------------------------------------------------------------------------
# Lost response after commit / uncertain outcomes
# ---------------------------------------------------------------------------
def test_lost_response_after_commit_is_recovered_by_retry_and_status(client, env, fake_llm):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    rid = f"act-{uuid.uuid4()}"

    def lose_response(name):
        if name == "after_commit":
            raise RuntimeError("connection dropped after commit")

    turn_commit.set_checkpoint_hook_for_tests(lose_response)
    failed = _post(client, sid, device, "wait", rid)
    turn_commit.set_checkpoint_hook_for_tests(None)
    assert failed.status_code == 502
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1

    status = client.get(
        f"/api/story/session/{sid}/action/{rid}", headers={DEVICE_ID_HEADER: device}
    )
    assert status.status_code == 200
    assert status.json()["status"] == "completed"
    assert status.json()["turn"]["turn_number"] == 2

    retry = _post(client, sid, device, "wait", rid)
    assert retry.status_code == 200
    assert retry.json().get("replayed") is True
    assert fake_llm.calls == 1
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1
    assert env.sync_db.sessions.find_one({"id": sid})["turn_count"] == 2


def test_uncertain_commit_without_turn_becomes_retryable(client, env, fake_llm, monkeypatch):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    rid = f"act-{uuid.uuid4()}"
    real_commit = server._commit_story_action_turn
    state = {"n": 0}

    async def lose_ack_without_commit(*args, **kwargs):
        state["n"] += 1
        if state["n"] == 1:
            raise turn_commit.CommitOutcomeUnknown("ack lost; nothing committed")
        return await real_commit(*args, **kwargs)

    monkeypatch.setattr(server, "_commit_story_action_turn", lose_ack_without_commit)
    first = _post(client, sid, device, "wait", rid)
    assert first.status_code == 503
    status = client.get(
        f"/api/story/session/{sid}/action/{rid}", headers={DEVICE_ID_HEADER: device}
    )
    assert status.json()["status"] == "failed"
    assert status.json()["error_kind"] == action_requests.ERROR_STORAGE

    retry = _post(client, sid, device, "wait", rid)
    assert retry.status_code == 200
    assert retry.json().get("replayed") is None
    assert fake_llm.calls == 2  # the first attempt never committed, so paid work ran again
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1


def test_provider_failure_marks_request_failed_and_retry_runs_again(env, monkeypatch):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    rid = f"act-{uuid.uuid4()}"
    from ai_service import AIServiceError

    def fail_first(call_index):
        if call_index == 1:
            raise AIServiceError("provider down", kind="provider_unavailable")
        return ACTION_TURN

    fake = FakeGateway(ACTION_TURN, on_call=fail_first).install()
    try:
        with make_client() as client:
            first = _post(client, sid, device, "wait", rid)
            assert first.status_code == 502
            status = client.get(
                f"/api/story/session/{sid}/action/{rid}", headers={DEVICE_ID_HEADER: device}
            )
            assert status.json() == {"status": "failed", "error_kind": action_requests.ERROR_PROVIDER}
            second = _post(client, sid, device, "wait", rid)
            assert second.status_code == 200
    finally:
        fake.restore()
    assert fake.calls == 2
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1


def test_stale_in_progress_claim_is_reclaimed_after_expiry(client, env, fake_llm):
    """Worker crash: claim left in_progress; once expired a retry takes over."""
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    rid = f"act-{uuid.uuid4()}"
    key = action_requests.request_key(sid, rid)
    now = ac.utc_now()
    env.sync_db.action_requests.insert_one(
        {
            "_id": key,
            "session_id": sid,
            "device_id": device,
            "request_id": rid,
            "fingerprint": action_requests.fingerprint(sid, "wait", False),
            "status": "in_progress",
            "claim_token": "crashed-worker",
            "claim_expires_at": now + timedelta(seconds=300),
            "attempts": 1,
            "created_at": now,
            "updated_at": now,
            "expires_at": now + timedelta(days=1),
        }
    )
    blocked = _post(client, sid, device, "wait", rid)
    assert blocked.status_code == 409
    status = client.get(
        f"/api/story/session/{sid}/action/{rid}", headers={DEVICE_ID_HEADER: device}
    )
    assert status.json()["status"] == "in_progress"

    env.sync_db.action_requests.update_one(
        {"_id": key}, {"$set": {"claim_expires_at": now - timedelta(seconds=1)}}
    )
    status = client.get(
        f"/api/story/session/{sid}/action/{rid}", headers={DEVICE_ID_HEADER: device}
    )
    assert status.json()["status"] == "failed"
    retried = _post(client, sid, device, "wait", rid)
    assert retried.status_code == 200
    assert fake_llm.calls == 1
    record = env.sync_db.action_requests.find_one({"_id": key})
    assert record["status"] == "completed"
    assert record["attempts"] == 2


# ---------------------------------------------------------------------------
# Ownership + sanitisation
# ---------------------------------------------------------------------------
def test_other_device_cannot_replay_or_read_status(client, env, fake_llm):
    owner = f"dev_{uuid.uuid4()}"
    intruder = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, owner)
    rid = f"act-{uuid.uuid4()}"
    assert _post(client, sid, owner, "wait", rid).status_code == 200

    stolen = _post(client, sid, intruder, "wait", rid)
    assert stolen.status_code == 404
    status = client.get(
        f"/api/story/session/{sid}/action/{rid}", headers={DEVICE_ID_HEADER: intruder}
    )
    assert status.status_code == 404
    assert fake_llm.calls == 1


def test_replayed_response_is_player_safe(client, env, fake_llm):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device, rolling={"secret_registry": [{"secret": "hidden"}]})
    rid = f"act-{uuid.uuid4()}"
    assert _post(client, sid, device, "wait", rid, debug=True).status_code == 200
    replay = _post(client, sid, device, "wait", rid, debug=True)
    assert replay.status_code == 200
    body = replay.text
    turn = replay.json()["turn"]
    for forbidden in ("rolling_state", "raw", "debug", "secret_registry", "action_request_key", "device_id", "action_lock"):
        assert forbidden not in turn
        assert forbidden not in body
    status = client.get(
        f"/api/story/session/{sid}/action/{rid}", headers={DEVICE_ID_HEADER: device}
    )
    for forbidden in ("rolling_state", "raw", "debug", "secret_registry", "claim_token", "fingerprint"):
        assert forbidden not in status.text


def test_status_unknown_for_never_seen_id(client, env, fake_llm):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    status = client.get(
        f"/api/story/session/{sid}/action/never-sent", headers={DEVICE_ID_HEADER: device}
    )
    assert status.status_code == 200
    assert status.json() == {"status": "unknown"}
