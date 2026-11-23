"""Discover a route and choose who learns it: a horror hotel and a cyberpunk plaza, one engine."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from play_moves_support import *  # noqa: F401,F403,E402
from play_moves_support import client, device, doc, env, headers, move, moves, narrator, seed, session_view  # noqa: F401,E402

LOBBY, BOILER = "the hotel lobby", "the boiler room"
PLAZA = "Sector Nine plaza"


def hotel():
    return {
        "scene": LOBBY, "location": LOBBY, "known_rooms": [LOBBY, BOILER], "locations": [LOBBY, BOILER],
        "npcs": [
            {"name": "Mr. Pell", "npc_id": "npc-pell0000000", "role": "night porter", "last_seen": LOBBY, "stance": "ally"},
            {"name": "Lena Voss", "npc_id": "npc-lena0000000", "role": "guest", "last_seen": LOBBY, "stance": "neutral"},
        ],
        "relationship_vectors": [{"name": "Mr. Pell", "trust": 70}, {"name": "Lena Voss", "trust": 40}], "deceased": [],
    }


HOTEL_TURNS = [
    ["Mr. Pell polishes the brass bell at the front desk. Lena Voss waits by the stairs."],
    ["Behind the desk a narrow service passage descends toward the boiler room, and Mr. Pell pretends not to notice it."],
    ["Mr. Pell mutters about the pipes. Lena Voss checks her watch."],
]
FOUND = {"via": {"turn": 2, "paragraph": 0, "quote": "narrow service passage descends toward the boiler room"}, "to": "the boiler room"}


def _find(client, env, sid, dev, expected=3, args=None):
    r = move(client, sid, dev, expected, "route", args or FOUND)
    assert r.status_code == 200, r.text
    return doc(env, sid)["play_state"]["route"]["routes"][0]


def test_horror_service_passage_becomes_a_real_travel_option(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, hotel(), HOTEL_TURNS, carried="torch")
    assert moves(client, sid, dev)["route"]["routes"] == []
    route = _find(client, env, sid, dev)
    opt = moves(client, sid, dev)["route"]["routes"][0]
    assert opt["can_travel"] and opt["a"] == LOBBY and opt["b"] == BOILER
    r = move(client, sid, dev, 4, "route", {"route_id": route["id"]}, op="travel")
    assert r.status_code == 200, r.text
    assert doc(env, sid)["rolling_state"]["location"] == BOILER


def test_taught_person_knows_it_and_the_untold_do_not(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, hotel(), HOTEL_TURNS, carried="torch")
    route = _find(client, env, sid, dev)
    assert move(client, sid, dev, 4, "route", {"route_id": route["id"], "with": "Mr. Pell"}, op="teach").status_code == 200
    st = doc(env, sid)["play_state"]["route"]["routes"][0]
    names = {k["name"] for k in st["knowers"]}
    assert "Mr. Pell" in names and "Lena Voss" not in names
    r = move(client, sid, dev, 4, "route", {"route_id": route["id"], "with": "Mr. Pell"}, op="teach")
    assert r.status_code == 409  # already knows
    client.post("/api/story/action", headers=headers(dev), json={"session_id": sid, "action_text": "Wait", "action_request_id": "w-1", "expected_turn_count": 4})
    assert "is known to:" in narrator.seen[-1] and "Mr. Pell" in narrator.seen[-1].split("is known to:")[1].split("\n")[0]
    assert "Lena Voss" not in narrator.seen[-1].split("is known to:")[1].split("\n")[0]


def test_a_blocked_route_and_what_was_learned_survive_a_reload(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, hotel(), HOTEL_TURNS, carried="torch")
    route = _find(client, env, sid, dev)
    assert move(client, sid, dev, 4, "route", {"route_id": route["id"], "note": "a fallen rack of crates"}, op="block").status_code == 200
    opt = moves(client, sid, dev)["route"]["routes"][0]
    assert opt["status"] == "blocked" and opt["can_travel"] is False and "crates" in opt["why_not"]
    blocked = move(client, sid, dev, 5, "route", {"route_id": route["id"]}, op="travel")
    assert blocked.status_code == 422
    shown = session_view(client, sid, dev)["play_view"]["route"][0]
    assert shown["status"] == "blocked" and shown["b"] == BOILER
    assert move(client, sid, dev, 5, "route", {"route_id": route["id"]}, op="reopen").status_code == 200
    assert moves(client, sid, dev)["route"]["routes"][0]["can_travel"] is True


def test_knowing_where_it_leads_is_not_having_the_key(client, env, narrator):
    dev = device()
    plaza = {
        "scene": PLAZA, "location": PLAZA, "known_rooms": [PLAZA, "Undercity"], "locations": [PLAZA, "Undercity"],
        "npcs": [{"name": "Kiri", "npc_id": "npc-kiri0000000", "role": "fixer", "last_seen": PLAZA}],
        "relationship_vectors": [{"name": "Kiri", "trust": 55}], "deceased": [],
    }
    turns = [["Neon rain hammers the Sector Nine plaza. A maintenance hatch behind the noodle stall, locked with a keycard, drops toward the Undercity."]]
    sid = seed(env.sync_db, dev, plaza, turns, carried="stim patch")
    r = move(client, sid, dev, 1, "route", {"via": {"turn": 1, "paragraph": 0, "quote": "maintenance hatch behind the noodle stall"}, "to": "Undercity", "gate": "keycard"})
    assert r.status_code == 200, r.text
    opt = moves(client, sid, dev)["route"]["routes"][0]
    assert opt["can_travel"] is False and "keycard" in opt["why_not"]
    # Carrying the keycard (as the ledger says) opens it.
    last = env.sync_db.turns.find_one({"session_id": sid}, sort=[("turn_number", -1)])
    env.sync_db.turns.update_one({"_id": last["_id"]}, {"$set": {"ledger": {"Carried": "stim patch; keycard"}}})
    assert moves(client, sid, dev)["route"]["routes"][0]["can_travel"] is True


def test_discovery_needs_something_shown_and_a_known_place(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, hotel(), HOTEL_TURNS, carried="torch")
    assert move(client, sid, dev, 3, "route", {**FOUND, "to": "the roof garden"}).status_code == 422
    assert move(client, sid, dev, 3, "route", {"via": {"turn": 1, "paragraph": 0, "quote": "brass bell"}, "to": "the boiler room", "gate": "skeleton key"}).status_code == 422
    assert doc(env, sid)["turn_count"] == 3


def test_retry_does_not_find_it_twice(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, hotel(), HOTEL_TURNS, carried="torch")
    a = move(client, sid, dev, 3, "route", FOUND, rid="find-0001")
    b = move(client, sid, dev, 3, "route", FOUND, rid="find-0001")
    assert a.status_code == b.status_code == 200
    assert len(doc(env, sid)["play_state"]["route"]["routes"]) == 1 and doc(env, sid)["turn_count"] == 4


import pytest  # noqa: E402


@pytest.mark.parametrize("successor,gets_route", [("Mr. Pell", True), ("Lena Voss", False)])
def test_after_handover_only_those_who_learned_it_can_use_it(client, env, narrator, successor, gets_route):
    dev = device()
    sid = seed(env.sync_db, dev, hotel(), HOTEL_TURNS, carried="torch")
    route = _find(client, env, sid, dev)
    assert move(client, sid, dev, 4, "route", {"route_id": route["id"], "with": "Mr. Pell"}, op="teach").status_code == 200
    cands = client.get(f"/api/story/session/{sid}/handover", headers=headers(dev)).json()["candidates"]
    by_name = {c["name"]: c["id"] for c in cands}
    n = doc(env, sid)["turn_count"]
    ho = client.post(f"/api/story/session/{sid}/handover", headers=headers(dev),
                     json={"request_id": f"ho-{uuid.uuid4()}", "successor_id": by_name[successor], "expected_turn_count": n})
    assert ho.status_code == 200, ho.text
    got = moves(client, sid, dev)["route"]["routes"]
    if gets_route:
        assert [r["id"] for r in got] == [route["id"]] and got[0]["can_travel"]
    else:
        assert got == []


def test_connected_sequence_route_bargain_teach_then_handover(client, env, narrator):
    """Find a route, strike a bargain, teach the route to one person, hand the story to someone who knows neither."""
    dev = device()
    sid = seed(env.sync_db, dev, hotel(), HOTEL_TURNS, carried="torch, brass key")
    narrator.carried = "torch, brass key"
    route = _find(client, env, sid, dev)
    deal = move(client, sid, dev, 4, "bargain", {"with": "Lena Voss", "service": "keep watch on the stairs", "give": ["brass key"]})
    assert deal.status_code == 200, deal.text
    assert move(client, sid, dev, 5, "route", {"route_id": route["id"], "with": "Mr. Pell"}, op="teach").status_code == 200
    state = doc(env, sid)["play_state"]
    assert "Lena Voss" not in {k["name"] for k in state["route"]["routes"][0]["knowers"]}
    cands = client.get(f"/api/story/session/{sid}/handover", headers=headers(dev)).json()["candidates"]
    by_name = {c["name"]: c["id"] for c in cands}
    n = doc(env, sid)["turn_count"]
    ho = client.post(f"/api/story/session/{sid}/handover", headers=headers(dev),
                     json={"request_id": f"ho-{uuid.uuid4()}", "successor_id": by_name["Lena Voss"], "expected_turn_count": n})
    assert ho.status_code == 200, ho.text
    after = moves(client, sid, dev)
    assert after["route"]["routes"] == []  # Lena never learned it, so it is not hers to use
