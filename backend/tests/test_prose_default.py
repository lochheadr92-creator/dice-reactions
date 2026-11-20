"""
New stories use DEFAULT_PROSE_MODE when the request names no prose_mode.

Real disposable MongoDB (replica set) + FastAPI TestClient + scripted gateway.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import server  # noqa: E402
from reliability_support import (  # noqa: E402
    OPENING_TURN,
    FakeGateway,
    MongoEnv,
    make_client,
    relax_rate_limits,
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


def _create(env, body):
    with make_client() as client:
        response = client.post("/api/story/new", json=body)
    assert response.status_code == 200, response.text
    return env.sync_db.sessions.find_one({"id": response.json()["session_id"]})


def test_test_suite_pins_standard_default():
    assert server.DEFAULT_SESSION_PROSE_MODE == "standard"


def test_new_story_without_prose_mode_uses_configured_default(env, fake_llm, monkeypatch):
    monkeypatch.setattr(server, "DEFAULT_SESSION_PROSE_MODE", "story")
    body = {"device_id": f"dev_{uuid.uuid4()}", "genre": "fantasy", "difficulty": "standard"}
    assert _create(env, body)["prose_mode"] == "story"


def test_explicit_prose_mode_beats_configured_default(env, fake_llm, monkeypatch):
    monkeypatch.setattr(server, "DEFAULT_SESSION_PROSE_MODE", "story")
    body = {
        "device_id": f"dev_{uuid.uuid4()}",
        "genre": "fantasy",
        "difficulty": "standard",
        "prose_mode": "brief",
    }
    assert _create(env, body)["prose_mode"] == "brief"
