"""Feature 3: end a chapter and continue the same save as another character.

Fixture: the scout (protagonist) owns an iron crowbar and holds a secret clue;
Mara Voss owns a brass key and remembers her own fact. Tomas Reed has appeared twice,
Old Hob once (not yet earned as a choice).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import action_concurrency as ac  # noqa: E402
import chapter_handover as ch  # noqa: E402
from reliability_support import (  # noqa: E402
    ACTION_TURN,
    ACTION_TURN_B,
    FakeGateway,
    MongoEnv,
    make_client,
    relax_rate_limits,
    run_db,
)
from player_features_support import (  # noqa: E402
    HOB_ID,
    HOOK_TEXT,
    MARA_FACT,
    MARA_ID,
    PROTAG_SECRET,
    TOMAS_FACT,
    TOMAS_ID,
    FERRYMAN_LINE,
    device,
    dump,
    headers,
    seed_story,
    session_doc,
    story_rolling,
    turn_docs,
)

KEY_TURN = ACTION_TURN.replace(
    "<rolling_state>{}</rolling_state>",
    '<rolling_state>{"clues":[{"text":"Mara found a scratch on the lock","witnesses":["Mara Voss"]}]}</rolling_state>',
)


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
    fake = FakeGateway(KEY_TURN, on_request=lambda n, kw: seen.append(kw["messages"]) or None).install()
    fake.seen = seen
    yield fake
    fake.restore()


@pytest.fixture()
def client(env, fake_llm):
    with make_client() as tc:
        yield tc


def _list(client, sid, dev):
    return client.get(f"/api/story/session/{sid}/handover", headers=headers(dev))


def _handover(client, sid, dev, successor=MARA_ID, expected=3, rid=None):
    return client.post(
        f"/api/story/session/{sid}/handover",
        json={"request_id": rid or f"ho-{uuid.uuid4()}", "successor_id": successor, "expected_turn_count": expected},
        headers=headers(dev),
    )


def _act(client, sid, dev, text="Take stock of what you are carrying", expected=4):
    return client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": text, "action_request_id": f"a-{uuid.uuid4()}",
              "expected_turn_count": expected},
        headers=headers(dev),
    )


def test_only_earned_living_characters_are_offered(client, env):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    listing = _list(client, sid, dev).json()
    ids = {c["id"] for c in listing["candidates"]}
    assert listing["can_end_chapter"] is True
    assert ids == {MARA_ID, TOMAS_ID}            # Old Hob appeared once
    assert HOB_ID not in ids
    blob = dump(listing)
    for hidden in (PROTAG_SECRET, MARA_FACT, TOMAS_FACT, HOOK_TEXT, "brass key", "storm lantern"):
        assert hidden not in blob                 # nothing the player has not earned
    # A dead character is not offered.
    rolling = story_rolling()
    rolling["deceased"] = ["Tomas Reed"]
    sid2 = seed_story(env.sync_db, dev, rolling=rolling)
    assert {c["id"] for c in _list(client, sid2, dev).json()["candidates"]} == {MARA_ID}


def test_nobody_qualifies_is_reported_before_closing(client, env):
    dev = device()
    rolling = story_rolling()
    rolling["npcs"] = [r for r in rolling["npcs"] if r["npc_id"] == HOB_ID]
    sid = seed_story(env.sync_db, dev, rolling=rolling)
    listing = _list(client, sid, dev).json()
    assert listing["can_end_chapter"] is False and listing["reason"] == "nobody_qualifies"
    before = session_doc(env.sync_db, sid)
    res = _handover(client, sid, dev, successor=HOB_ID)
    assert res.status_code == 422
    after = session_doc(env.sync_db, sid)
    after.pop("session_revision", None)   # the lease normalises a legacy missing revision
    assert after == before and len(turn_docs(env.sync_db, sid)) == 3


def test_handover_then_real_action_uses_only_the_successors_world(client, env, fake_llm):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    res = _handover(client, sid, dev)
    assert res.status_code == 200, res.text
    body = res.json()
    assert fake_llm.calls == 0                                    # engine-written, no narrator
    assert body["session"]["protagonist"]["name"] == "Mara Voss"
    assert body["turn"]["turn_number"] == 4
    text = "\n".join(body["turn"]["paragraphs"])
    assert "Mara Voss" in text and "brass key" in text and "the ferry dock" in text
    assert MARA_FACT in text and PROTAG_SECRET not in text and "iron crowbar" not in text
    assert len(body["turn"]["choices"]) == 4

    # Reload: same identity, earlier turns still name whom the player was at the time.
    got = client.get(f"/api/story/session/{sid}", headers=headers(dev)).json()
    assert got["session"]["protagonist"]["name"] == "Mara Voss"
    assert [t["character"]["role"] for t in got["turns"][:3]] == ["scout"] * 3
    assert got["turns"][3]["character"]["name"] == "Mara Voss"

    # World state: one former-protagonist NPC, successor no longer an NPC.
    rolling = session_doc(env.sync_db, sid)["rolling_state"]
    names = [r["name"] for r in rolling["npcs"]]
    assert "Mara Voss" not in names and names.count("The scout") == 1
    former = next(r for r in rolling["npcs"] if r["name"] == "The scout")
    assert former["controller"] == "engine" and former["inventory"] == ["iron crowbar"]
    assert [r["object"] for r in rolling["inventory_objects"]] == ["brass key"]
    assert any(r["object"] == "iron crowbar" and r["status"] == "stored" for r in rolling["object_locations"])
    assert rolling["injuries"] == [] and rolling["character"] == "winded"

    # A real action through the normal turn path.
    act = _act(client, sid, dev, expected=4)
    assert act.status_code == 200, act.text
    assert act.json()["turn"]["turn_number"] == 5
    messages = fake_llm.seen[-1]
    blob = dump(messages)
    assert MARA_FACT in blob and "brass key" in blob            # the successor's own fact and item reach the narrator
    assert PROTAG_SECRET not in blob and HOOK_TEXT not in blob  # the former protagonist's do not
    assert FERRYMAN_LINE not in blob and "Turn 2 opens" not in blob   # no pre-handover prose is replayed
    assert "CONTROLLED_CHARACTER" in blob and "Mara Voss" in blob
    # The engine still holds the withheld clue; the narrator just cannot see it.
    after = session_doc(env.sync_db, sid)
    assert any(PROTAG_SECRET in str(c) for c in after["rolling_state"]["clues"])
    assert any("scratch on the lock" in str(c) for c in after["rolling_state"]["clues"])
    assert len([r for r in after["rolling_state"]["npcs"] if r["name"] == "The scout"]) == 1


def test_withheld_items_hidden_unless_the_successor_is_evidenced(client, env):
    session = session_doc(env.sync_db, seed_story(env.sync_db, device()))
    view_session = dict(session)
    plan = ch.plan_handover(session, [{"turn_number": n, "paragraphs": ch_paragraphs(n)} for n in (1, 2, 3)],
                            successor_id=MARA_ID, request_id="ho-unit-1234")
    view_session.update(plan.update_set)
    rolling = plan.update_set["rolling_state"]
    view = ch.narrator_view(view_session, rolling)
    texts = dump(view)
    assert PROTAG_SECRET not in texts and "Who cut the ferry rope" not in texts
    assert "A shared map of the dock" in texts                  # Mara witnessed it
    assert "character_hooks" not in view


def ch_paragraphs(n):
    from player_features_support import turn_paragraphs
    return turn_paragraphs(n)


def test_duplicate_confirmation_and_second_handover(client, env):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    rid = f"ho-{uuid.uuid4()}"
    first = _handover(client, sid, dev, rid=rid)
    again = _handover(client, sid, dev, rid=rid)
    assert first.status_code == 200 and again.status_code == 200
    assert again.json()["replayed"] is True and again.json()["turn"]["id"] == first.json()["turn"]["id"]
    assert len(turn_docs(env.sync_db, sid)) == 4
    other = _handover(client, sid, dev, successor=TOMAS_ID, expected=4)
    assert other.status_code == 409 and len(turn_docs(env.sync_db, sid)) == 4
    assert session_doc(env.sync_db, sid)["controlled_character"]["name"] == "Mara Voss"


def test_stale_choices_and_stale_handover_are_refused(client, env, fake_llm):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    assert _handover(client, sid, dev, expected=2).status_code == 409
    assert len(turn_docs(env.sync_db, sid)) == 3
    assert _handover(client, sid, dev).status_code == 200
    stale = _act(client, sid, dev, text="Seed choice A3", expected=3)   # a choice from before the handover
    assert stale.status_code == 409 and fake_llm.calls == 0
    assert len(turn_docs(env.sync_db, sid)) == 4
    assert _act(client, sid, dev, expected=4).status_code == 200


def test_turn_in_flight_blocks_handover_and_leaves_save_playable(client, env, fake_llm):
    dev = device()
    sid = seed_story(env.sync_db, dev)

    async def hold():
        import server
        await ac.acquire_action_lease(server.db, sid, dev)

    run_db(hold())
    before = session_doc(env.sync_db, sid)["rolling_state"]
    assert _handover(client, sid, dev).status_code == 409
    env.sync_db.sessions.update_one({"id": sid}, {"$unset": {f: "" for f in ac.ACTION_LOCK_FIELDS}})
    assert session_doc(env.sync_db, sid)["rolling_state"] == before
    assert len(turn_docs(env.sync_db, sid)) == 3
    assert "handover" not in session_doc(env.sync_db, sid)
    assert _act(client, sid, dev, text="Ask the guard", expected=3).status_code == 200


def test_ineligible_successor_leaves_save_consistent(client, env, fake_llm):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    for bad in (HOB_ID, "npc-doesnotexist", ch.candidate_id({"name": "Nobody Here"})):
        assert _handover(client, sid, dev, successor=bad).status_code == 422
    assert len(turn_docs(env.sync_db, sid)) == 3 and "handover" not in session_doc(env.sync_db, sid)
    assert _act(client, sid, dev, text="Ask the guard", expected=3).status_code == 200


def test_notebook_survives_handover_and_stays_private(client, env, fake_llm):
    dev = device()
    sid = seed_story(env.sync_db, dev)
    pin = client.post(f"/api/story/session/{sid}/notebook/pins", json={"turn_number": 1, "paragraph_index": 1},
                      headers=headers(dev)).json()["pin"]
    client.post(f"/api/story/session/{sid}/notebook/theories",
                json={"title": "T", "body": "OWL-THEORY secret idea", "pin_ids": [pin["id"]]}, headers=headers(dev))
    assert _handover(client, sid, dev).status_code == 200
    nb = client.get(f"/api/story/session/{sid}/notebook", headers=headers(dev)).json()
    assert len(nb["pins"]) == 1 and len(nb["theories"]) == 1
    assert _act(client, sid, dev, expected=4).status_code == 200
    assert "OWL-THEORY" not in dump(fake_llm.seen)


def test_agendas_successor_stops_being_driven_and_former_gets_one(env):
    session = session_doc(env.sync_db, seed_story(env.sync_db, device()))
    session["replayability_state"] = {
        "run_seed": "seed",
        "npc_agendas": {"version": 1, "archived": [], "active": [
            {"npc_id": MARA_ID, "status": "active", "display_name": "Mara Voss"},
            {"npc_id": TOMAS_ID, "status": "active", "display_name": "Tomas Reed"},
        ]},
    }
    plan = ch.plan_handover(session, [{"turn_number": n, "paragraphs": ch_paragraphs(n)} for n in (1, 2, 3)],
                            successor_id=MARA_ID, request_id="ho-unit-5678")
    active = plan.update_set["replayability_state"]["npc_agendas"]["active"]
    by_id = {a["npc_id"]: a for a in active}
    assert by_id[MARA_ID]["status"] == "player_controlled"
    assert by_id[TOMAS_ID]["status"] == "active"
    former_id = plan.former["actor_id"]
    assert by_id[former_id]["status"] == "active"
    assert sum(1 for a in active if a["npc_id"] == former_id) == 1
