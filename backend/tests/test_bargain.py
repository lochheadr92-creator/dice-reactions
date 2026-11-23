"""Strike a bargain with something at stake, through the real turn, save and inventory.

A medieval healer and a wasteland mechanic run the same engine. The narrator keeps writing the old
carried list on purpose: what the player actually holds is the engine's call.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from play_moves_support import *  # noqa: F401,F403,E402
from play_moves_support import client, device, doc, env, headers, move, moves, narrator, seed, session_view  # noqa: F401,E402

HUT = "the healer's hut"
YARD = "the scrap yard"


def hut(trust=50):
    return {
        "scene": HUT, "location": HUT, "known_rooms": [HUT], "locations": [HUT],
        "npcs": [{"name": "Maren", "npc_id": "npc-maren0000000", "role": "healer", "last_seen": HUT,
                  "inventory": ["healing moss", "linen"], "stance": "neutral"}],
        "relationship_vectors": [{"name": "Maren", "trust": trust}], "deceased": [],
    }


HUT_TURN = [["Maren the healer grinds herbs at her table and glances at your wound."]]
HUT_LEDGER = {"rows": {"npc-maren0000000": {"name": "Maren", "inventory": ["healing moss", "linen"], "known": ["healing moss"], "last_turn": 1}}, "version": 1}


def yard(trust=50):
    return {
        "scene": YARD, "location": YARD, "known_rooms": [YARD], "locations": [YARD],
        "npcs": [{"name": "Dax", "npc_id": "npc-dax000000000", "role": "driver", "last_seen": YARD,
                  "inventory": ["jerry can"], "stance": "neutral"}],
        "relationship_vectors": [{"name": "Dax", "trust": trust}], "deceased": [],
    }


YARD_TURN = [["Dax leans on a rusted truck and eyes the dust storm rolling in."]]


def _carried(env, sid):
    last = env.sync_db.turns.find_one({"session_id": sid}, sort=[("turn_number", -1)])
    return last["ledger"].get("Carried", "")


def test_pledge_the_ring_for_healing_loses_access_then_reclaims_by_fulfilling_terms(client, env, narrator):
    dev = device()
    narrator.carried = "signet ring; waterskin"
    sid = seed(env.sync_db, dev, hut(), HUT_TURN, carried="signet ring; waterskin", npc_ledger=HUT_LEDGER)
    terms = {"with": "Maren", "service": "tend my wound", "pledge": ["signet ring"], "settle": ["healing moss"]}
    pre = client.post(f"/api/story/session/{sid}/moves/preview", headers=headers(dev), json={"kind": "bargain", "args": terms}).json()
    assert pre["can_commit"] and any("security" in t for t in pre["terms"])
    r = move(client, sid, dev, 1, "bargain", terms, rid="deal-0001")
    assert r.status_code == 200, r.text
    assert "accepts" in " ".join(r.json()["turn"]["paragraphs"])
    assert "signet ring" not in _carried(env, sid) and "waterskin" in _carried(env, sid)
    # She holds it now, and the player knows she does.
    maren = doc(env, sid)["npc_ledger"]["rows"]["npc-maren0000000"]
    assert "signet ring" in maren["inventory"] and "signet ring" in maren["known"]
    # A later ordinary turn: the narrator still lists the ring, the engine still removes it.
    r2 = client.post("/api/story/action", headers=headers(dev), json={"session_id": sid, "action_text": "Show the ring to the room", "action_request_id": "n-2", "expected_turn_count": 2})
    assert r2.status_code == 200
    assert "signet ring" not in _carried(env, sid)
    assert "no longer has: signet ring" in narrator.seen[-1]
    # Retrying the accepted offer cannot pay twice or add a second obligation.
    again = move(client, sid, dev, 1, "bargain", terms, rid="deal-0001")
    assert again.status_code == 200
    assert len(doc(env, sid)["play_state"]["bargain"]["records"]) == 1
    # Fulfil the terms: she gets the moss back from the player, the ring comes home.
    narrator.carried = "waterskin; healing moss"
    client.post("/api/story/action", headers=headers(dev), json={"session_id": sid, "action_text": "Gather moss", "action_request_id": "n-3", "expected_turn_count": 3})
    bid = doc(env, sid)["play_state"]["bargain"]["records"][0]["id"]
    s = move(client, sid, dev, 4, "bargain", {"bargain_id": bid}, op="settle")
    assert s.status_code == 200, s.text
    carried = _carried(env, sid)
    assert "signet ring" in carried and "healing moss" not in carried
    assert doc(env, sid)["play_state"]["bargain"]["records"][0]["status"] == "settled"
    view = session_view(client, sid, dev)["play_view"]["bargain"][0]
    assert view["status"] == "settled"


def test_last_battery_for_a_ride_cannot_be_used_afterwards(client, env, narrator):
    dev = device()
    narrator.carried = "last battery; radio"
    sid = seed(env.sync_db, dev, yard(), YARD_TURN, carried="last battery; radio")
    r = move(client, sid, dev, 1, "bargain", {"with": "Dax", "service": "drive me to the depot", "give": ["last battery"]})
    assert r.status_code == 200, r.text
    assert "last battery" not in _carried(env, sid) and "radio" in _carried(env, sid)
    r = client.post("/api/story/action", headers=headers(dev), json={"session_id": sid, "action_text": "Put the last battery in the radio", "action_request_id": "u-1", "expected_turn_count": 2})
    assert r.status_code == 200
    assert "last battery" not in _carried(env, sid)
    assert "no longer has: last battery" in narrator.seen[-1]


def test_declining_keeps_everything(client, env, narrator):
    dev = device()
    narrator.carried = "last battery; radio"
    sid = seed(env.sync_db, dev, yard(trust=5), YARD_TURN, carried="last battery; radio")
    r = move(client, sid, dev, 1, "bargain", {"with": "Dax", "service": "drive me to the depot", "give": ["last battery"]})
    assert r.status_code == 200, r.text
    assert "last battery" in _carried(env, sid)
    st = doc(env, sid)["play_state"]["bargain"]
    assert st["records"][0]["status"] == "declined" and st["custody"] == []


def test_a_counter_is_not_agreed_until_the_player_accepts(client, env, narrator):
    dev = device()
    narrator.carried = "last battery; radio; compass"
    sid = seed(env.sync_db, dev, yard(trust=20), YARD_TURN, carried="last battery; radio; compass")
    r = move(client, sid, dev, 1, "bargain", {"with": "Dax", "service": "drive me to the depot", "give": ["last battery"]})
    assert r.status_code == 200, r.text
    rec = doc(env, sid)["play_state"]["bargain"]["records"][0]
    assert rec["status"] == "countered" and rec["counter"]["pledge"]
    assert "last battery" in _carried(env, sid)
    a = move(client, sid, dev, 2, "bargain", {"bargain_id": rec["id"]}, op="accept")
    assert a.status_code == 200, a.text
    assert "last battery" not in _carried(env, sid)


def test_prerequisites_missing_refuse_without_a_turn(client, env, narrator):
    dev = device()
    rolling = yard()
    rolling["npcs"][0]["last_seen"] = "the far ridge"
    sid = seed(env.sync_db, dev, rolling, [["The yard is empty except for wind."]], carried="last battery")
    r = move(client, sid, dev, 1, "bargain", {"with": "Dax", "service": "drive me", "give": ["last battery"]})
    assert r.status_code == 422 and doc(env, sid)["turn_count"] == 1
    sid2 = seed(env.sync_db, dev, yard(), YARD_TURN, carried="radio")
    assert move(client, sid2, dev, 1, "bargain", {"with": "Dax", "service": "ride", "give": ["gold bar"]}).status_code == 422
    assert move(client, sid2, dev, 1, "bargain", {"with": "Dax", "get": ["jerry can"], "give": ["radio"]}).status_code == 422  # never learned she has it
    assert doc(env, sid2)["turn_count"] == 1


def test_only_the_character_who_struck_the_deal_can_settle_it(client, env, narrator):
    dev = device()
    narrator.carried = "signet ring"
    sid = seed(env.sync_db, dev, hut(), HUT_TURN, carried="signet ring", npc_ledger=HUT_LEDGER)
    move(client, sid, dev, 1, "bargain", {"with": "Maren", "service": "tend my wound", "pledge": ["signet ring"], "settle": ["linen"]})
    state = doc(env, sid)["play_state"]
    state["bargain"]["records"][0]["by"] = "someone-else"
    env.sync_db.sessions.update_one({"id": sid}, {"$set": {"play_state": state}})
    narrator.carried = "linen"
    s = move(client, sid, dev, 2, "bargain", {"bargain_id": state["bargain"]["records"][0]["id"]}, op="settle")
    assert s.status_code == 422


def _trust(env, sid, name):
    vectors = doc(env, sid)["rolling_state"]["relationship_vectors"]
    return next(v["trust"] for v in vectors if v["name"] == name)


def test_settling_a_bargain_is_a_promise_kept_in_the_relationship_system(client, env, narrator):
    dev = device()
    narrator.carried = "signet ring; waterskin"
    sid = seed(env.sync_db, dev, hut(), HUT_TURN, carried="signet ring; waterskin", npc_ledger=HUT_LEDGER)
    terms = {"with": "Maren", "service": "tend my wound", "pledge": ["signet ring"], "settle": ["healing moss"]}
    assert move(client, sid, dev, 1, "bargain", terms, rid="deal-0001").status_code == 200
    after_deal = _trust(env, sid, "Maren")
    assert after_deal <= 50                                   # striking a deal is not a promise kept
    narrator.carried = "waterskin; healing moss"
    client.post("/api/story/action", headers=headers(dev), json={"session_id": sid, "action_text": "Gather moss", "action_request_id": "n-2", "expected_turn_count": 2})
    before = _trust(env, sid, "Maren")
    bid = doc(env, sid)["play_state"]["bargain"]["records"][0]["id"]
    settled = move(client, sid, dev, 3, "bargain", {"bargain_id": bid}, op="settle", rid="settle-0001")
    assert settled.status_code == 200, settled.text
    # The relationship system applied its own keep_promise value, once.
    assert _trust(env, sid, "Maren") == before + 10
    # The same request again is the stored turn: nothing is applied a second time.
    again = move(client, sid, dev, 3, "bargain", {"bargain_id": bid}, op="settle", rid="settle-0001")
    assert again.status_code == 200 and _trust(env, sid, "Maren") == before + 10
    assert doc(env, sid)["turn_count"] == 4
