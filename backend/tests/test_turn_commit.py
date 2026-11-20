"""
turn_commit unit coverage on a real replica set: topology check, opening
turn commit, ambiguity verification, and the read-only consistency report
(including the admin route).
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from pymongo.errors import ConnectionFailure

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import action_concurrency as ac  # noqa: E402
import server  # noqa: E402
import turn_commit  # noqa: E402
from security import ADMIN_API_KEY_HEADER  # noqa: E402
from reliability_support import MongoEnv, insert_session, make_client, relax_rate_limits, run_db  # noqa: E402

TEST_ADMIN_KEY = os.environ.get("ADMIN_API_KEY") or "test-admin-key-for-turn-commit"
os.environ["ADMIN_API_KEY"] = TEST_ADMIN_KEY


@pytest.fixture()
def env(monkeypatch):
    mongo = MongoEnv()
    relax_rate_limits(monkeypatch)
    yield mongo
    turn_commit.set_checkpoint_hook_for_tests(None)
    mongo.close()


def _opening_doc(sid):
    return {
        "id": str(uuid.uuid4()),
        "session_id": sid,
        "turn_number": 1,
        "player_action": None,
        "narrative": "opening",
        "paragraphs": ["opening"],
        "choices": [],
        "state": {},
        "ledger": {},
        "rolling_state": {},
    }


def test_replica_set_reports_transaction_support(env):
    facts = run_db(turn_commit.check_transaction_support(env.async_db))
    assert facts["topology"] in ("replica_set", "mongos")
    assert facts["writable_primary"] is True


def test_opening_turn_commits_atomically_and_only_once(env):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device, turn_count=0)
    doc = _opening_doc(sid)
    result = run_db(
        turn_commit.commit_opening_turn(
            env.async_db,
            session_id=sid,
            turn_doc=doc,
            update_set={"turn_count": 1, "last_state": {"Health": "stable"}},
            meta={"model_used": "test", "fallback_events": [{"from": "a", "to": "b", "reason": "r", "message": "m"}]},
        )
    )
    assert result.committed and result.turn_number == 1
    stored = env.sync_db.sessions.find_one({"id": sid})
    assert stored["turn_count"] == 1
    assert stored["active_model"] == "test"
    assert stored["model_switches"][0]["to_model"] == "b"
    assert stored[ac.SESSION_REVISION_FIELD] == 1
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1

    async def again():
        with pytest.raises(turn_commit.CommitPreconditionFailed):
            await turn_commit.commit_opening_turn(
                env.async_db, session_id=sid, turn_doc=_opening_doc(sid),
                update_set={"turn_count": 1}, meta={},
            )

    run_db(again())
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1


def test_opening_turn_interrupted_before_commit_writes_nothing(env):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device, turn_count=0)

    real_run = turn_commit._run_transaction

    async def abort_mid_way(db, callback):
        async def wrapped(session):
            await callback(session)
            raise RuntimeError("interrupted before commit")

        return await real_run(db, wrapped)

    turn_commit._run_transaction = abort_mid_way
    try:
        async def attempt():
            with pytest.raises(RuntimeError):
                await turn_commit.commit_opening_turn(
                    env.async_db, session_id=sid, turn_doc=_opening_doc(sid),
                    update_set={"turn_count": 1}, meta={},
                )

        run_db(attempt())
    finally:
        turn_commit._run_transaction = real_run
    assert env.sync_db.sessions.find_one({"id": sid})["turn_count"] == 0
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 0


def test_ambiguous_opening_commit_is_verified_by_turn_id(env, monkeypatch):
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device, turn_count=0)
    real_run = turn_commit._run_transaction

    async def commit_then_lose_ack(db, callback):
        await real_run(db, callback)
        raise ConnectionFailure("ack lost")

    monkeypatch.setattr(turn_commit, "_run_transaction", commit_then_lose_ack)
    result = run_db(
        turn_commit.commit_opening_turn(
            env.async_db, session_id=sid, turn_doc=_opening_doc(sid), update_set={"turn_count": 1}, meta={}
        )
    )
    assert result.verified_after_ambiguity is True
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 1


def test_consistency_report_is_read_only_and_finds_each_anomaly(env):
    device = f"dev_{uuid.uuid4()}"
    healthy = insert_session(env.sync_db, device, turn_count=1)
    env.sync_db.turns.insert_one({**_opening_doc(healthy)})
    mismatched = insert_session(env.sync_db, device, turn_count=3)
    env.sync_db.turns.insert_one({**_opening_doc(mismatched)})
    orphan_session = str(uuid.uuid4())
    env.sync_db.turns.insert_one({**_opening_doc(orphan_session), "turn_number": 2})
    dup_session = insert_session(env.sync_db, device, turn_count=2)
    # Legacy data may predate the unique (session_id, turn_number) index.
    try:
        env.sync_db.turns.drop_index("turns_session_turn_unique")
    except Exception:
        pass
    env.sync_db.turns.insert_one({**_opening_doc(dup_session), "turn_number": 2})
    env.sync_db.turns.insert_one({**_opening_doc(dup_session), "turn_number": 2})
    now = ac.utc_now()
    env.sync_db.action_requests.insert_many(
        [
            {"_id": "a|1", "session_id": "a", "device_id": device, "request_id": "1", "status": "in_progress",
             "claim_expires_at": now - timedelta(seconds=1), "expires_at": now + timedelta(days=1)},
            {"_id": "a|2", "session_id": "a", "device_id": device, "request_id": "2", "status": "in_progress",
             "claim_expires_at": now + timedelta(seconds=100), "expires_at": now + timedelta(days=1)},
            {"_id": "a|3", "session_id": "a", "device_id": device, "request_id": "3", "status": "uncertain",
             "expires_at": now + timedelta(days=1)},
            {"_id": "a|4", "session_id": "a", "device_id": device, "request_id": "4", "status": "completed",
             "turn_id": "missing-turn", "turn_number": 9, "expires_at": now + timedelta(days=1)},
        ]
    )
    before = {
        "sessions": list(env.sync_db.sessions.find({}, {"_id": 0})),
        "turns": list(env.sync_db.turns.find({}, {"_id": 0})),
        "requests": list(env.sync_db.action_requests.find({}, {"_id": 0})),
    }

    report = run_db(turn_commit.consistency_report(env.async_db))

    assert report["read_only"] is True
    mismatch_ids = {row["id"] for row in report["sessions_with_turn_count_mismatch"]["sample"]}
    assert mismatched in mismatch_ids
    assert healthy not in mismatch_ids
    assert report["orphaned_turns"]["count"] == 1
    assert report["orphaned_turns"]["sample"][0]["session_id"] == orphan_session
    assert report["duplicate_turn_numbers"]["count"] == 1
    assert report["duplicate_turn_numbers"]["sample"][0]["session_id"] == dup_session
    assert report["action_requests"]["in_progress_stale_claim"] == 1
    assert report["action_requests"]["in_progress_active"] == 1
    assert report["action_requests"]["uncertain"] == 1
    assert report["action_requests"]["completed_without_turn"]["count"] == 1
    # Samples carry identifiers only.
    assert "narrative" not in str(report) and "device_id" not in str(report)

    after = {
        "sessions": list(env.sync_db.sessions.find({}, {"_id": 0})),
        "turns": list(env.sync_db.turns.find({}, {"_id": 0})),
        "requests": list(env.sync_db.action_requests.find({}, {"_id": 0})),
    }
    assert before == after
    # Restore the unique index for later tests (the report itself never does this).
    env.sync_db.turns.delete_many({"session_id": dup_session})
    run_db(ac.ensure_action_concurrency_indexes(env.async_db))


def test_admin_consistency_route_requires_admin_key(env):
    with make_client() as client:
        anonymous = client.get("/api/admin/consistency")
        assert anonymous.status_code == 401
        allowed = client.get("/api/admin/consistency", headers={ADMIN_API_KEY_HEADER: TEST_ADMIN_KEY})
        assert allowed.status_code == 200
        body = allowed.json()
        assert body["read_only"] is True
        assert body["transaction_support_error"] is None
        assert "orphaned_turns" in body
