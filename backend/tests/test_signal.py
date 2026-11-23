"""Agree on a signal with an NPC: a spy in a cafe and a wizard's tavern, one engine."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from play_moves_support import *  # noqa: F401,F403,E402
from play_moves_support import client, device, doc, env, headers, move, moves, narrator, seed, session_view  # noqa: F401,E402

CAFE, TAVERN = "the Café Lumière", "the Gilded Stag tavern"


def cafe(trust=60):
    return {
        "scene": CAFE, "location": CAFE, "known_rooms": [CAFE], "locations": [CAFE],
        "npcs": [{"name": "Odile", "npc_id": "npc-odile000000", "role": "courier", "last_seen": CAFE},
                 {"name": "Inspector Brandt", "npc_id": "npc-brandt00000", "role": "inspector", "last_seen": CAFE, "stance": "hostile"}],
        "relationship_vectors": [{"name": "Odile", "trust": trust}, {"name": "Inspector Brandt", "trust": 5}], "deceased": [],
    }


CAFE_TURN = [["Odile stirs her coffee at the corner table. Inspector Brandt reads a newspaper and watches the room."]]


def tavern():
    return {
        "scene": TAVERN, "location": TAVERN, "known_rooms": [TAVERN], "locations": [TAVERN],
        "npcs": [{"name": "Pip", "npc_id": "npc-pip00000000", "role": "apprentice", "last_seen": TAVERN},
                 {"name": "Gorm", "npc_id": "npc-gorm0000000", "role": "drunk", "last_seen": TAVERN}],
        "relationship_vectors": [{"name": "Pip", "trust": 70}, {"name": "Gorm", "trust": 30}], "deceased": [],
    }


TAVERN_TURN = [["Pip carries mugs between the benches. Gorm snores into his sleeve by the hearth."]]


def _sigs(env, sid):
    return doc(env, sid)["play_state"]["signal"]["signals"]


def test_cafe_signal_partner_understands_and_the_inspector_only_notices(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, cafe(), CAFE_TURN)
    r = move(client, sid, dev, 1, "signal", {"with": "Odile", "channel": "sight", "sign": "napkin folded in a triangle", "meaning": "the contact is late, leave"})
    assert r.status_code == 200, r.text
    sid_ = _sigs(env, sid)[0]["id"]
    s = move(client, sid, dev, 2, "signal", {"op": "send", "signal_id": sid_})
    assert s.status_code == 200, s.text
    block = narrator.seen[-1].split("[SIGNAL_RESULT_V1]")[1].split("\n\n")[0]
    assert "Inspector Brandt" in block and "Only Odile knows what it means" in block
    assert "recognises it: the contact is late" in block
    send = _sigs(env, sid)[0]["sends"][0]
    assert [p["name"] for p in send["understood_by"]] == ["Odile"] and send["unsure"] == []
    # The player sees that others noticed, not who they are or what they made of it.
    v = session_view(client, sid, dev)["play_view"]["signal"][0]["sends"][0]
    assert v["partner_understood"] is True and v["others_noticed"] == 1
    assert "Brandt" not in str(session_view(client, sid, dev)["play_view"])


def test_faint_signal_leaves_the_partner_with_incomplete_information(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, cafe(), CAFE_TURN)
    move(client, sid, dev, 1, "signal", {"with": "Odile", "channel": "sight", "sign": "tilt of the hat", "meaning": "abort"})
    sid_ = _sigs(env, sid)[0]["id"]
    assert move(client, sid, dev, 2, "signal", {"op": "send", "signal_id": sid_, "clarity": "faint"}).status_code == 200
    block = narrator.seen[-1].split("[SIGNAL_RESULT_V1]")[1].split("\n\n")[0]
    assert "cannot be sure" in block and "abort" not in block
    send = _sigs(env, sid)[0]["sends"][0]
    assert send["understood_by"] == [] and [p["name"] for p in send["unsure"]] == ["Odile"]


def test_tavern_phrase_is_known_by_the_apprentice_and_not_the_drunk(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, tavern(), TAVERN_TURN)
    assert move(client, sid, dev, 1, "signal", {"with": "Pip", "channel": "phrase", "sign": "the hearth burns green tonight", "meaning": "fetch the master"}).status_code == 200
    sig = _sigs(env, sid)[0]
    assert {p["name"] for p in sig["parties"]} == {"Pip", doc(env, sid)["play_state"]["signal"]["signals"][0]["parties"][0]["name"]}
    move(client, sid, dev, 2, "signal", {"op": "send", "signal_id": sig["id"]})
    client.post("/api/story/action", headers=headers(dev), json={"session_id": sid, "action_text": "Wait", "action_request_id": "w-1", "expected_turn_count": 3})
    standing = narrator.seen[-1].split("[SIGNAL_STANDING_V1]")[1].split("\n\n")[0]
    assert "Pip and the player have a sign" in standing and "Gorm" not in standing


def test_partner_not_in_the_room_receives_nothing(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, cafe(), CAFE_TURN)
    move(client, sid, dev, 1, "signal", {"with": "Odile", "channel": "sight", "sign": "scarf", "meaning": "go"})
    d = doc(env, sid)["rolling_state"]
    d["npcs"][0]["last_seen"] = "the street"
    env.sync_db.sessions.update_one({"id": sid}, {"$set": {"rolling_state": d}})
    move(client, sid, dev, 2, "signal", {"op": "send", "signal_id": _sigs(env, sid)[0]["id"]})
    assert "reaches no one who knows its meaning" in narrator.seen[-1]


def test_prerequisites_and_retries(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, cafe(trust=10), CAFE_TURN)
    assert move(client, sid, dev, 1, "signal", {"with": "Odile", "channel": "sight", "sign": "x", "meaning": "y"}).status_code == 422  # distrusts the player
    assert move(client, sid, dev, 1, "signal", {"with": "Inspector Brandt", "channel": "sight", "sign": "x", "meaning": "y"}).status_code == 422
    assert move(client, sid, dev, 1, "signal", {"with": "Nobody", "channel": "sight", "sign": "x", "meaning": "y"}).status_code == 422
    sid2 = seed(env.sync_db, dev, cafe(), CAFE_TURN)
    assert move(client, sid2, dev, 1, "signal", {"with": "Odile", "channel": "smoke", "sign": "x", "meaning": "y"}).status_code == 422
    a = move(client, sid2, dev, 1, "signal", {"with": "Odile", "channel": "sight", "sign": "napkin", "meaning": "go"}, rid="sg-0001")
    b = move(client, sid2, dev, 1, "signal", {"with": "Odile", "channel": "sight", "sign": "napkin", "meaning": "go"}, rid="sg-0001")
    assert a.status_code == b.status_code == 200 and len(_sigs(env, sid2)) == 1 and doc(env, sid2)["turn_count"] == 2
    assert doc(env, sid)["turn_count"] == 1
