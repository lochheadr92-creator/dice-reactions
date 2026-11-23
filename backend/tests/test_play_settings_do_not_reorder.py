"""Finding 4 (review 2, 2026-11-23): opening an older story must not move it up the list.

The play screen sends the Settings defaults whenever it gains focus. The
endpoint used to stamp ``updated_at`` on every call, identical or not, and the
story list is ordered by ``updated_at``.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gateway  # noqa: E402
import server  # noqa: E402
import turn_commit  # noqa: E402
from reliability_support import ACTION_TURN_B, fake_llm_result  # noqa: E402
from test_security import _device_headers, _seed_session, client, mongo_env  # noqa: E402,F401


def _two_stories(mongo_env, owner):
    """An older story and a newer one, with clearly separated play times."""
    older = _seed_session(mongo_env, owner)
    newer = _seed_session(mongo_env, owner)
    base = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    mongo_env.sessions.update_one({"id": older}, {"$set": {"updated_at": base, "prose_mode": "standard"}})
    mongo_env.sessions.update_one({"id": newer}, {"$set": {"updated_at": base + timedelta(days=2)}})
    return older, newer


def _list_order(client, owner):
    response = client.get("/api/story/sessions", headers=_device_headers(owner))
    assert response.status_code == 200
    body = response.json()
    rows = body if isinstance(body, list) else body.get("sessions", body)
    return [row["id"] for row in rows]


def test_opening_an_older_story_repeatedly_leaves_the_list_order_alone(client, mongo_env):
    owner = str(uuid.uuid4())
    older, newer = _two_stories(mongo_env, owner)
    before = mongo_env.sessions.find_one({"id": older})
    assert _list_order(client, owner) == [newer, older]
    path = f"/api/story/session/{older}/play-settings"
    for _ in range(3):  # what the play screen sends each time it gains focus
        response = client.post(path, headers=_device_headers(owner), json={"prose_mode": "M"})
        assert response.status_code == 200
        assert response.json() == {"prose_mode": "standard"}
    assert _list_order(client, owner) == [newer, older]
    assert mongo_env.sessions.find_one({"id": older}) == before  # identical values write nothing


def test_a_real_preference_change_is_stored_without_looking_newly_played(client, mongo_env, monkeypatch):
    owner = str(uuid.uuid4())
    older, newer = _two_stories(mongo_env, owner)
    before = mongo_env.sessions.find_one({"id": older})
    path = f"/api/story/session/{older}/play-settings"
    assert client.post(path, headers=_device_headers(owner), json={"prose_mode": "L", "prose_style": "plain"}).status_code == 200
    after = mongo_env.sessions.find_one({"id": older})
    assert (after["prose_mode"], after["prose_style"]) == ("story", "plain")
    assert after["updated_at"] == before["updated_at"]
    assert after["turn_count"] == before["turn_count"]
    assert after.get("session_revision") == before.get("session_revision")
    assert after["settings_updated_at"] > before["updated_at"]
    assert _list_order(client, owner) == [newer, older]

    # The next action uses the new length and style, and playing does move the story up.
    seen = {}

    async def scripted(**kwargs):
        seen["text"] = "\n".join(str(m["content"]) for m in kwargs["messages"])
        return fake_llm_result(ACTION_TURN_B)

    monkeypatch.setattr(gateway, "invoke_llm", scripted)
    response = client.post(
        "/api/story/action",
        headers=_device_headers(owner),
        json={"session_id": older, "action_text": "Walk the corridor."},
    )
    assert response.status_code == 200, response.text
    assert "4-6 paragraphs" in seen["text"]
    assert "[WRITING STYLE: PLAIN]" in seen["text"]
    assert _list_order(client, owner) == [older, newer]
    assert mongo_env.sessions.find_one({"id": older})["updated_at"] > after["updated_at"]


def test_settings_sent_during_a_held_action_lease_do_not_disturb_the_commit(client, mongo_env):
    owner = str(uuid.uuid4())
    older, _newer = _two_stories(mongo_env, owner)
    held, token = client.portal.call(server.acquire_action_lease, server.db, older, owner)
    before = mongo_env.sessions.find_one({"id": older})
    path = f"/api/story/session/{older}/play-settings"
    for body in ({"prose_mode": "M"}, {"prose_mode": "XL"}, {"prose_mode": "XL"}):
        assert client.post(path, headers=_device_headers(owner), json=body).status_code == 200
    during = mongo_env.sessions.find_one({"id": older})
    for field in ("action_lock_token", "action_lock_acquired_at", "action_lock_expires_at", "session_revision", "turn_count", "updated_at"):
        assert during.get(field) == before.get(field), field
    assert during["prose_mode"] == "cinematic"

    async def commit():
        await turn_commit.commit_action_turn(
            server.db,
            session_id=older,
            lease_token=token,
            expected_turn_count=1,
            expected_revision=held["session_revision"],
            turn_doc={"id": str(uuid.uuid4()), "session_id": older, "turn_number": 2},
            update_set={"turn_count": 2},
            meta={},
        )

    client.portal.call(commit)
    with pytest.raises(turn_commit.CommitPreconditionFailed):
        client.portal.call(commit)  # the stale duplicate is refused
    assert mongo_env.turns.count_documents({"session_id": older, "turn_number": 2}) == 1
    assert mongo_env.sessions.find_one({"id": older})["prose_mode"] == "cinematic"
