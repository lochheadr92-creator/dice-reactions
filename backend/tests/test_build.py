"""Leave something behind that others can use: a flood-camp shelter and a noir safe flat, one engine."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))
from play_moves_support import *  # noqa: F401,F403,E402
from play_moves_support import client, device, doc, env, headers, move, moves, narrator, seed, session_view  # noqa: F401,E402

RIDGE, FLAT = "the high ridge camp", "the Dunmore Street flat"


def ridge():
    return {
        "scene": RIDGE, "location": RIDGE, "known_rooms": [RIDGE], "locations": [RIDGE],
        "npcs": [{"name": "Tala", "npc_id": "npc-tala0000000", "role": "traveller", "last_seen": RIDGE},
                 {"name": "Oren", "npc_id": "npc-oren0000000", "role": "traveller", "last_seen": RIDGE}],
        "relationship_vectors": [{"name": "Tala", "trust": 60}, {"name": "Oren", "trust": 60}], "deceased": [],
    }


RIDGE_TURN = [["Tala and Oren shiver on the ridge while black clouds stack over the river valley."]]


def flat():
    return {
        "scene": FLAT, "location": FLAT, "known_rooms": [FLAT], "locations": [FLAT],
        "npcs": [{"name": "Iris Cole", "npc_id": "npc-iris0000000", "role": "witness", "last_seen": FLAT},
                 {"name": "Walt", "npc_id": "npc-walt0000000", "role": "informant", "last_seen": FLAT}],
        "relationship_vectors": [{"name": "Iris Cole", "trust": 55}, {"name": "Walt", "trust": 25}], "deceased": [],
    }


FLAT_TURN = [["Iris Cole closes the blinds in the Dunmore Street flat. Walt lights a cigarette by the window."]]


def _again(env, sid, text):
    """Another published beat that names the same people twice over, so a handover can offer them."""
    d = doc(env, sid)
    n = d["turn_count"] + 1
    last = env.sync_db.turns.find_one({"session_id": sid}, sort=[("turn_number", -1)])
    env.sync_db.turns.insert_one({**{k: v for k, v in last.items() if k not in ("_id", "action_request_key")}, "id": str(uuid.uuid4()), "turn_number": n,
                                  "narrative": text, "canonical_narrative": text, "paragraphs": [text]})
    env.sync_db.sessions.update_one({"id": sid}, {"$set": {"turn_count": n}})


def _carried(env, sid):
    return env.sync_db.turns.find_one({"session_id": sid}, sort=[("turn_number", -1)])["ledger"].get("Carried", "")


def test_a_shelter_costs_what_it_costs_and_blocks_the_other_choice(client, env, narrator):
    dev = device()
    narrator.carried = "oilcloth; rope"
    sid = seed(env.sync_db, dev, ridge(), RIDGE_TURN, carried="oilcloth; rope")
    opts = moves(client, sid, dev)["build"]
    assert {k["kind"] for k in opts["kinds"] if k["can_afford"]} >= {"shelter", "rest"}
    r = move(client, sid, dev, 1, "build", {"kind": "shelter", "items": ["oilcloth", "rope"], "note": "so Tala can sleep dry"})
    assert r.status_code == 200, r.text
    assert _carried(env, sid) == "-"
    opts = moves(client, sid, dev)["build"]
    assert not any(k["can_afford"] for k in opts["kinds"])  # nothing left to spend on the other improvement
    assert move(client, sid, dev, 2, "build", {"kind": "rest", "items": ["oilcloth", "rope"]}).status_code == 422
    # Reopening the save: the improvement and its cost are still there.
    view = session_view(client, sid, dev)["play_view"]["build"][0]
    assert view["kind"] == "shelter" and view["cost"] == ["oilcloth", "rope"] and view["place"] == RIDGE


def test_the_other_choice_leaves_a_different_capability_for_the_next_person(client, env, narrator):
    dev = device()
    narrator.carried = "oilcloth; rope"
    sid = seed(env.sync_db, dev, ridge(), RIDGE_TURN, carried="oilcloth; rope")
    assert move(client, sid, dev, 1, "build", {"kind": "rest", "items": ["oilcloth", "rope"]}).status_code == 200
    _again(env, sid, "Tala pulls her cloak tight beside Oren as the rain begins.")
    n = doc(env, sid)["turn_count"]
    cands = {c["name"]: c["id"] for c in client.get(f"/api/story/session/{sid}/handover", headers=headers(dev)).json()["candidates"]}
    ho = client.post(f"/api/story/session/{sid}/handover", headers=headers(dev), json={"request_id": f"ho-{uuid.uuid4()}", "successor_id": cands["Tala"], "expected_turn_count": n})
    assert ho.status_code == 200, ho.text
    works = moves(client, sid, dev)["build"]["works"]
    assert [w["kind"] for w in works] == ["rest"]  # visible, so Tala can see it without being told
    assert works[0]["note"] == ""


def test_flood_shelter_is_offered_to_the_people_there_by_the_engine(client, env, narrator):
    dev = device()
    narrator.carried = "oilcloth; rope"
    sid = seed(env.sync_db, dev, ridge(), RIDGE_TURN, carried="oilcloth; rope")
    move(client, sid, dev, 1, "build", {"kind": "shelter", "items": ["oilcloth", "rope"], "note": "private worry about Oren"})
    client.post("/api/story/action", headers=headers(dev), json={"session_id": sid, "action_text": "Watch the river rise", "action_request_id": "f-1", "expected_turn_count": 2})
    sent = narrator.seen[-1]
    assert "[BUILD_STANDING_V1]" in sent and "a shelter" in sent and "Tala" in sent.split("[BUILD_STANDING_V1]")[1]
    assert "private worry" not in sent


def test_noir_safe_flat_is_usable_only_by_the_one_who_was_shown(client, env, narrator):
    dev = device()
    narrator.carried = "spare key; cash roll"
    sid = seed(env.sync_db, dev, flat(), FLAT_TURN, carried="spare key; cash roll")
    r = move(client, sid, dev, 1, "build", {"kind": "hideout", "items": ["spare key"], "note": "Iris would be safe here, I owe her"})
    assert r.status_code == 200, r.text
    work = doc(env, sid)["play_state"]["build"]["works"][0]
    s = move(client, sid, dev, 2, "build", {"op": "share", "work_id": work["id"], "with": "Iris Cole"})
    assert s.status_code == 200, s.text
    n = doc(env, sid)["turn_count"]
    cands = {c["name"]: c["id"] for c in client.get(f"/api/story/session/{sid}/handover", headers=headers(dev)).json()["candidates"]}
    ho = client.post(f"/api/story/session/{sid}/handover", headers=headers(dev), json={"request_id": f"ho-{uuid.uuid4()}", "successor_id": cands["Iris Cole"], "expected_turn_count": n})
    assert ho.status_code == 200, ho.text
    works = moves(client, sid, dev)["build"]["works"]
    assert [w["kind"] for w in works] == ["hideout"] and works[0]["note"] == ""  # she can use it; she never sees why it was built
    # Walt was never told, and a hideout is out of sight.
    sid2 = seed(env.sync_db, dev, flat(), FLAT_TURN, carried="spare key")
    move(client, sid2, dev, 1, "build", {"kind": "hideout", "items": ["spare key"]})
    _again(env, sid2, "Walt taps ash into a saucer and watches the street.")
    n2 = doc(env, sid2)["turn_count"]
    cands2 = {c["name"]: c["id"] for c in client.get(f"/api/story/session/{sid2}/handover", headers=headers(dev)).json()["candidates"]}
    ho2 = client.post(f"/api/story/session/{sid2}/handover", headers=headers(dev), json={"request_id": f"ho-{uuid.uuid4()}", "successor_id": cands2["Walt"], "expected_turn_count": n2})
    assert ho2.status_code == 200, ho2.text
    assert moves(client, sid2, dev)["build"]["works"] == []


def test_a_cache_hands_its_stock_to_whoever_takes_it(client, env, narrator):
    dev = device()
    narrator.carried = "flare; ration tin"
    sid = seed(env.sync_db, dev, flat(), FLAT_TURN, carried="flare; ration tin")
    move(client, sid, dev, 1, "build", {"kind": "cache", "items": ["flare", "ration tin"]})
    assert "flare" not in _carried(env, sid)
    wid = doc(env, sid)["play_state"]["build"]["works"][0]["id"]
    narrator.carried = "-"
    r = move(client, sid, dev, 2, "build", {"op": "use", "work_id": wid, "items": ["flare"]})
    assert r.status_code == 200, r.text
    assert _carried(env, sid) == "flare"
    assert doc(env, sid)["play_state"]["build"]["works"][0]["stock"] == ["ration tin"]
    assert move(client, sid, dev, 3, "build", {"op": "use", "work_id": wid, "items": ["flare"]}).status_code == 422


def test_missing_prerequisites_and_retries(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, ridge(), RIDGE_TURN, carried="")
    assert move(client, sid, dev, 1, "build", {"kind": "shelter", "items": ["oilcloth"]}).status_code == 422
    assert doc(env, sid)["turn_count"] == 1
    narrator.carried = "oilcloth; rope"
    sid2 = seed(env.sync_db, dev, ridge(), RIDGE_TURN, carried="oilcloth; rope")
    assert move(client, sid2, dev, 1, "build", {"kind": "shelter", "items": ["oilcloth"]}).status_code == 422  # too little
    a = move(client, sid2, dev, 1, "build", {"kind": "shelter", "items": ["oilcloth", "rope"]}, rid="b-0001")
    b = move(client, sid2, dev, 1, "build", {"kind": "shelter", "items": ["oilcloth", "rope"]}, rid="b-0001")
    assert a.status_code == b.status_code == 200
    d = doc(env, sid2)
    assert len(d["play_state"]["build"]["works"]) == 1 and d["turn_count"] == 2
