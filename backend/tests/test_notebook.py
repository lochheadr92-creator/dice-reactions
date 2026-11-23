"""Feature 2: private notebook of pins and theories, scoped to one save."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import server  # noqa: E402
from reliability_support import (  # noqa: E402
    ACTION_TURN,
    FakeGateway,
    MongoEnv,
    make_client,
    relax_rate_limits,
)
from player_features_support import (  # noqa: E402
    ENGINE_ONLY,
    FERRYMAN_LINE,
    GUARD_LINE,
    device,
    dump,
    headers,
    seed_story,
    session_doc,
    turn_docs,
)

THEORY_PHRASE = "ZEBRA-THEORY the ferryman lied to cover the guard"


@pytest.fixture()
def env(monkeypatch):
    mongo = MongoEnv()
    mongo.sync_db.notebook_items.delete_many({})
    relax_rate_limits(monkeypatch)
    yield mongo
    mongo.sync_db.notebook_items.delete_many({})
    mongo.close()


@pytest.fixture()
def fake_llm():
    seen = []
    fake = FakeGateway(ACTION_TURN, on_request=lambda n, kw: seen.append(kw["messages"]) or None).install()
    fake.seen = seen
    yield fake
    fake.restore()


@pytest.fixture()
def client(env, fake_llm):
    with make_client() as tc:
        yield tc


def _pin(client, sid, dev, turn, para, quote=None, note=None):
    body = {"turn_number": turn, "paragraph_index": para}
    if quote is not None:
        body["quote"] = quote
    if note is not None:
        body["note"] = note
    return client.post(f"/api/story/session/{sid}/notebook/pins", json=body, headers=headers(dev))


def _two_pins_and_theory(client, sid, dev):
    a = _pin(client, sid, dev, 1, 1, quote="toll was paid").json()["pin"]
    b = _pin(client, sid, dev, 3, 2, note="contradicts the ferryman").json()["pin"]
    t = client.post(
        f"/api/story/session/{sid}/notebook/theories",
        json={"title": "Who lied?", "body": THEORY_PHRASE, "pin_ids": [a["id"], b["id"]]},
        headers=headers(dev),
    )
    assert t.status_code == 200, t.text
    return a, b, t.json()["theory"]


def test_pins_and_theory_survive_reload_and_older_turn_opens(client, env, monkeypatch):
    dev = device()
    sid = seed_story(env.sync_db, dev, turns=3)
    a, b, theory = _two_pins_and_theory(client, sid, dev)
    assert a["text"] == "toll was paid" and b["text"] == GUARD_LINE
    assert a["turn_number"] == 1 and b["turn_number"] == 3

    nb = client.get(f"/api/story/session/{sid}/notebook", headers=headers(dev)).json()
    assert {p["id"] for p in nb["pins"]} == {a["id"], b["id"]}
    assert nb["theories"][0]["pin_ids"] == [a["id"], b["id"]]
    assert nb["theories"][0]["body"] == THEORY_PHRASE

    # Turn 1 is older than the history window: the play screen no longer loads it,
    # but the pin still opens the exact passage.
    monkeypatch.setattr(server, "TURN_WINDOW_MAX", 2)
    windowed = client.get(f"/api/story/session/{sid}", headers=headers(dev)).json()["turns"]
    assert [t["turn_number"] for t in windowed] == [2, 3]
    opened = client.get(f"/api/story/session/{sid}/turn/{a['turn_number']}", headers=headers(dev)).json()["turn"]
    para = opened["paragraphs"][a["paragraph_index"]]
    assert para[a["start"]:a["end"]] == a["text"] and FERRYMAN_LINE == para


def test_pinning_and_editing_change_no_story_state(client, env, fake_llm):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    before_session = session_doc(env.sync_db, sid)
    before_turns = turn_docs(env.sync_db, sid)
    limits_before = list(env.sync_db.rate_limits.find({}, {"_id": 1, "count": 1}))
    a, b, theory = _two_pins_and_theory(client, sid, dev)
    edit = client.put(
        f"/api/story/session/{sid}/notebook/theories/{theory['id']}",
        json={"body": "edited", "pin_ids": [a["id"]]}, headers=headers(dev),
    )
    assert edit.status_code == 200 and edit.json()["theory"]["pin_ids"] == [a["id"]]
    assert client.delete(f"/api/story/session/{sid}/notebook/pins/{b['id']}", headers=headers(dev)).status_code == 200
    assert client.delete(f"/api/story/session/{sid}/notebook/theories/{theory['id']}", headers=headers(dev)).status_code == 200
    assert session_doc(env.sync_db, sid) == before_session
    assert turn_docs(env.sync_db, sid) == before_turns
    assert list(env.sync_db.rate_limits.find({}, {"_id": 1, "count": 1})) == limits_before
    assert fake_llm.calls == 0
    nb = client.get(f"/api/story/session/{sid}/notebook", headers=headers(dev)).json()
    assert [p["id"] for p in nb["pins"]] == [a["id"]] and nb["theories"] == []


def test_removing_a_pin_detaches_it_but_keeps_the_theory(client, env):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    a, b, theory = _two_pins_and_theory(client, sid, dev)
    assert client.delete(f"/api/story/session/{sid}/notebook/pins/{a['id']}", headers=headers(dev)).status_code == 200
    kept = client.get(f"/api/story/session/{sid}/notebook", headers=headers(dev)).json()["theories"][0]
    assert kept["pin_ids"] == [b["id"]] and kept["body"] == THEORY_PHRASE


def test_only_published_text_can_be_pinned(client, env):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    assert _pin(client, sid, dev, 1, 1, quote=ENGINE_ONLY).status_code == 422   # raw/debug text
    assert _pin(client, sid, dev, 1, 9).status_code == 422                       # no such paragraph
    assert _pin(client, sid, dev, 99, 0).status_code == 404                      # no such turn
    assert _pin(client, sid, dev, 1, 1, quote="not in this passage").status_code == 422
    assert env.sync_db.notebook_items.count_documents({"session_id": sid}) == 0


def test_same_passage_pins_once(client, env):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    first = _pin(client, sid, dev, 1, 1).json()
    again = _pin(client, sid, dev, 1, 1).json()
    assert first["created"] is True and again["created"] is False
    assert first["pin"]["id"] == again["pin"]["id"]


def test_notebook_is_private_and_export_omits_it(client, env):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    _two_pins_and_theory(client, sid, dev)
    other = device()
    for path, method in (
        (f"/api/story/session/{sid}/notebook", "get"),
        (f"/api/story/session/{sid}/turn/1", "get"),
    ):
        assert getattr(client, method)(path, headers=headers(other)).status_code in (403, 404)
    assert _pin(client, sid, other, 1, 1).status_code in (403, 404)
    export = client.get(f"/api/story/session/{sid}/export", headers=headers(dev))
    assert export.status_code == 200
    text = json.dumps(export.json())
    assert THEORY_PHRASE not in text and "notebook" not in text.lower() and "pin" not in export.json()
    full = client.get(f"/api/story/session/{sid}", headers=headers(dev)).text
    assert THEORY_PHRASE not in full


def test_theory_phrase_never_reaches_the_narrator(client, env, fake_llm):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    _two_pins_and_theory(client, sid, dev)
    res = client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "Ask the guard", "action_request_id": f"a-{uuid.uuid4()}",
              "expected_turn_count": 3},
        headers=headers(dev),
    )
    assert res.status_code == 200, res.text
    assert fake_llm.seen, "narrator was not called"
    blob = dump(fake_llm.seen)
    assert THEORY_PHRASE not in blob and "Who lied?" not in blob


def test_delete_and_reset_remove_the_notebook(client, env):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    _two_pins_and_theory(client, sid, dev)
    assert env.sync_db.notebook_items.count_documents({"session_id": sid}) == 3
    assert client.post(f"/api/story/session/{sid}/reset", headers=headers(dev)).status_code == 200
    assert env.sync_db.notebook_items.count_documents({"session_id": sid}) == 0
    sid2 = seed_story(env.sync_db, dev)
    _two_pins_and_theory(client, sid2, dev)
    assert client.delete(f"/api/story/session/{sid2}", headers=headers(dev)).status_code == 200
    assert env.sync_db.notebook_items.count_documents({"session_id": sid2}) == 0
