"""Feature 1: branch a save from its latest committed turn.

Real disposable MongoDB (replica set) + FastAPI TestClient + scripted narrator.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import action_concurrency as ac  # noqa: E402
import turn_commit  # noqa: E402
from reliability_support import (  # noqa: E402
    ACTION_TURN,
    ACTION_TURN_B,
    FakeGateway,
    MongoEnv,
    make_client,
    relax_rate_limits,
)
from player_features_support import (  # noqa: E402
    device,
    headers,
    seed_story,
    session_doc,
    turn_docs,
)

LOCKET_TURN = ACTION_TURN.replace(
    "<rolling_state>{}</rolling_state>",
    '<rolling_state>{"inventory_objects":[{"object":"silver locket","location_state":"carried"}]}</rolling_state>',
)
KNIFE_TURN = ACTION_TURN_B.replace(
    "<rolling_state>{}</rolling_state>",
    '<rolling_state>{"inventory_objects":[{"object":"rusty knife","location_state":"carried"}]}</rolling_state>',
)


@pytest.fixture()
def env(monkeypatch):
    mongo = MongoEnv()
    mongo.sync_db.notebook_items.delete_many({})
    relax_rate_limits(monkeypatch)
    yield mongo
    mongo.close()


@pytest.fixture()
def fake_llm():
    fake = FakeGateway(LOCKET_TURN).install()
    yield fake
    fake.restore()


@pytest.fixture()
def client(env, fake_llm):
    with make_client() as tc:
        yield tc


def _branch(client, sid, dev, request_id=None, expected=None):
    body = {"request_id": request_id or f"br-{uuid.uuid4()}"}
    if expected is not None:
        body["expected_turn_count"] = expected
    return client.post(f"/api/story/session/{sid}/branch", json=body, headers=headers(dev))


def _act(client, sid, dev, text="Continue", expected=None):
    body = {"session_id": sid, "action_text": text, "action_request_id": f"act-{uuid.uuid4()}"}
    if expected is not None:
        body["expected_turn_count"] = expected
    return client.post("/api/story/action", json=body, headers=headers(dev))


def _inventory(sync_db, sid):
    rolling = session_doc(sync_db, sid)["rolling_state"]
    return sorted(r["object"] for r in rolling.get("inventory_objects") or [])


def test_branch_copies_decision_and_costs_nothing(client, env, fake_llm):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    usage_before = env.sync_db.rate_limits.count_documents({})
    original = session_doc(env.sync_db, sid)

    res = _branch(client, sid, dev, expected=3)
    assert res.status_code == 200, res.text
    body = res.json()
    bid = body["session"]["id"]
    assert bid != sid and body["replayed"] is False
    assert body["session"]["turn_count"] == 3
    assert body["session"]["branched_from"]["turn_number"] == 3
    assert body["session"]["branch_label"] and body["session"]["title"] != original["title"]
    assert "device_id" not in body["session"]

    branch = session_doc(env.sync_db, bid)
    for field in ("rolling_state", "last_state", "genre", "role", "tone", "difficulty", "mode"):
        assert branch[field] == original[field], field
    assert branch["session_revision"] == 0
    for field in ac.ACTION_LOCK_FIELDS:
        assert field not in branch
    src_turns, new_turns = turn_docs(env.sync_db, sid), turn_docs(env.sync_db, bid)
    assert [t["paragraphs"] for t in src_turns] == [t["paragraphs"] for t in new_turns]
    assert [t["choices"] for t in src_turns] == [t["choices"] for t in new_turns]
    assert {t["id"] for t in src_turns}.isdisjoint({t["id"] for t in new_turns})
    # No narrator call, no credit spent, source untouched.
    assert fake_llm.calls == 0
    assert env.sync_db.rate_limits.count_documents({}) == usage_before
    assert env.sync_db.action_requests.count_documents({}) == 0
    assert session_doc(env.sync_db, sid)["turn_count"] == 3
    after = session_doc(env.sync_db, sid)
    # The lease only normalises a legacy missing revision to 0; no turn committed.
    assert (after.get("session_revision") or 0) == 0
    assert after["rolling_state"] == original["rolling_state"]
    for field in ac.ACTION_LOCK_FIELDS:
        assert field not in after


def test_double_tap_and_two_requests(client, env):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    rid = f"br-{uuid.uuid4()}"
    first = _branch(client, sid, dev, rid).json()
    again = _branch(client, sid, dev, rid).json()
    assert again["session"]["id"] == first["session"]["id"] and again["replayed"] is True
    assert env.sync_db.sessions.count_documents({"branched_from.session_id": sid}) == 1
    other = _branch(client, sid, dev).json()
    assert other["session"]["id"] != first["session"]["id"]
    assert other["session"]["branch_label"] != first["session"]["branch_label"]
    assert len(turn_docs(env.sync_db, other["session"]["id"])) == 3


def test_branch_refused_while_turn_in_flight_or_stale(client, env):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    stale = _branch(client, sid, dev, expected=2)
    assert stale.status_code == 409
    token_holder = {}

    async def hold():
        import server
        _s, token = await ac.acquire_action_lease(server.db, sid, dev)
        token_holder["t"] = token

    from reliability_support import run_db
    run_db(hold())
    busy = _branch(client, sid, dev)
    assert busy.status_code == 409
    assert env.sync_db.sessions.count_documents({"branched_from.session_id": sid}) == 0
    assert len(turn_docs(env.sync_db, sid)) == 3


def test_branches_diverge_survive_reload_and_deletes(client, env, fake_llm):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    bid = _branch(client, sid, dev).json()["session"]["id"]

    assert _act(client, bid, dev, "Take the locket", expected=3).status_code == 200
    fake_llm.content = KNIFE_TURN
    assert _act(client, sid, dev, "Take the knife", expected=3).status_code == 200

    assert _inventory(env.sync_db, bid) == ["iron crowbar", "silver locket"]
    assert _inventory(env.sync_db, sid) == ["iron crowbar", "rusty knife"]
    for s in (sid, bid):
        got = client.get(f"/api/story/session/{s}", headers=headers(dev)).json()
        assert [t["turn_number"] for t in got["turns"]] == [1, 2, 3, 4]
        assert got["turns"][0]["paragraphs"] == turn_docs(env.sync_db, s)[0]["paragraphs"]

    listing = client.get("/api/story/sessions", headers=headers(dev)).json()["sessions"]
    titles = {s["id"]: s["title"] for s in listing}
    assert titles[sid] != titles[bid]

    # Delete the original: the branch still shows its history and takes the next action.
    assert client.delete(f"/api/story/session/{sid}", headers=headers(dev)).status_code == 200
    got = client.get(f"/api/story/session/{bid}", headers=headers(dev)).json()
    assert [t["turn_number"] for t in got["turns"]] == [1, 2, 3, 4]
    fake_llm.content = ACTION_TURN_B
    assert _act(client, bid, dev, "Go on", expected=4).status_code == 200
    assert len(turn_docs(env.sync_db, bid)) == 5


def test_delete_branch_leaves_original_playable(client, env, fake_llm):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    bid = _branch(client, sid, dev).json()["session"]["id"]
    assert client.delete(f"/api/story/session/{bid}", headers=headers(dev)).status_code == 200
    assert env.sync_db.turns.count_documents({"session_id": bid}) == 0
    got = client.get(f"/api/story/session/{sid}", headers=headers(dev)).json()
    assert len(got["turns"]) == 3
    assert _act(client, sid, dev, "Carry on", expected=3).status_code == 200


def test_branch_requires_owner_and_a_turn(client, env):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    assert _branch(client, sid, device()).status_code in (403, 404)
    empty = seed_story(env.sync_db, dev, turns=0)
    assert _branch(client, empty, dev).status_code == 422


def test_branch_leaves_no_notebook_behind(client, env):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    pin = client.post(
        f"/api/story/session/{sid}/notebook/pins",
        json={"turn_number": 1, "paragraph_index": 1}, headers=headers(dev),
    )
    assert pin.status_code == 200, pin.text
    bid = _branch(client, sid, dev).json()["session"]["id"]
    nb = client.get(f"/api/story/session/{bid}/notebook", headers=headers(dev)).json()
    assert nb == {"pins": [], "theories": []}
