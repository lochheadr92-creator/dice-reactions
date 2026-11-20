"""
Story creation never leaves a stuck provisional session (review 2026-11-20, finding 3).

Real disposable MongoDB (replica set) + FastAPI TestClient + scripted gateway.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import server  # noqa: E402
from security import DEVICE_ID_HEADER  # noqa: E402
from reliability_support import (  # noqa: E402
    OPENING_TURN,
    FakeGateway,
    MongoEnv,
    make_client,
    relax_rate_limits,
    run_db,
)


@pytest.fixture()
def env(monkeypatch):
    mongo = MongoEnv()
    relax_rate_limits(monkeypatch)
    yield mongo
    mongo.close()


@pytest.fixture()
def fake_llm():
    fake = FakeGateway(OPENING_TURN).install()
    yield fake
    fake.restore()


def _new(device, creation_request_id=None):
    body = {"device_id": device, "genre": "fantasy", "difficulty": "standard"}
    if creation_request_id:
        body["creation_request_id"] = creation_request_id
    return body


def _provisional_shell(sync_db, device, creation_request_id, *, age_seconds):
    sid = str(uuid.uuid4())
    sync_db.sessions.insert_one(
        {
            "id": sid,
            "device_id": device,
            "genre": "fantasy",
            "difficulty": "standard",
            "title": "Fantasy — Wanderer",
            "turn_count": 0,
            "creation_request_id": creation_request_id,
            "created_at": datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
            "updated_at": datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
        }
    )
    return sid


def test_post_generation_failure_removes_provisional_session_and_retry_succeeds(env, fake_llm):
    device = f"dev_{uuid.uuid4()}"
    crid = f"create-{uuid.uuid4()}"

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated post-processing failure")

    original_shape_hud = server.hud.shape_hud
    with make_client() as client:
        server.hud.shape_hud = boom
        try:
            first = client.post("/api/story/new", json=_new(device, crid))
        finally:
            server.hud.shape_hud = original_shape_hud
        assert first.status_code == 502
        assert env.sync_db.sessions.count_documents({"device_id": device}) == 0
        retry = client.post("/api/story/new", json=_new(device, crid))
        assert retry.status_code == 200, retry.text
    assert env.sync_db.sessions.count_documents({"device_id": device}) == 1


def test_stale_provisional_session_is_taken_over_by_a_retry(env, fake_llm):
    device = f"dev_{uuid.uuid4()}"
    crid = f"create-{uuid.uuid4()}"
    stale_sid = _provisional_shell(
        env.sync_db, device, crid, age_seconds=server._provisional_session_stale_seconds() + 5
    )
    with make_client() as client:
        response = client.post("/api/story/new", json=_new(device, crid))
    assert response.status_code == 200, response.text
    assert response.json()["session_id"] != stale_sid
    assert env.sync_db.sessions.count_documents({"id": stale_sid}) == 0
    assert env.sync_db.sessions.count_documents({"device_id": device, "turn_count": 1}) == 1


def test_recent_provisional_session_still_answers_in_progress(env, fake_llm):
    device = f"dev_{uuid.uuid4()}"
    crid = f"create-{uuid.uuid4()}"
    sid = _provisional_shell(env.sync_db, device, crid, age_seconds=5)
    with make_client() as client:
        response = client.post("/api/story/new", json=_new(device, crid))
    assert response.status_code == 409
    assert env.sync_db.sessions.count_documents({"id": sid}) == 1
    assert fake_llm.calls == 0


def test_session_list_hides_provisional_sessions(env, fake_llm):
    device = f"dev_{uuid.uuid4()}"
    _provisional_shell(env.sync_db, device, f"create-{uuid.uuid4()}", age_seconds=5)
    with make_client() as client:
        created = client.post("/api/story/new", json=_new(device))
        assert created.status_code == 200
        listed = client.get("/api/story/sessions", headers={DEVICE_ID_HEADER: device}).json()
    assert [s["turn_count"] for s in listed["sessions"]] == [1]


def test_cancelled_creation_removes_provisional_session(env):
    device = f"dev_{uuid.uuid4()}"
    started = asyncio.Event()

    async def slow_llm(**_kwargs):
        started.set()
        await asyncio.sleep(30)

    fake = FakeGateway(on_request=lambda _n, kw: slow_llm(**kw)).install()
    try:

        async def scenario():
            task = asyncio.create_task(server._create_new_story(server.NewStoryRequest(**_new(device))))
            await asyncio.wait_for(started.wait(), timeout=10)
            assert await server.db.sessions.count_documents({"device_id": device}) == 1
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            return await server.db.sessions.count_documents({"device_id": device})

        remaining = run_db(scenario())
    finally:
        fake.restore()
    assert remaining == 0
