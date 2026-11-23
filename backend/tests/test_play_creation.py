"""Moves reachable from saves created through POST /api/story/new, branch independence, old saves."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from play_moves_support import *  # noqa: F401,F403,E402
from play_moves_support import client, device, doc, env, headers, move, moves, narrator, seed, session_view  # noqa: F401,E402
from reliability_support import FakeGateway, make_client  # noqa: E402


class Storyteller:
    """Offline narrator that writes a scripted story with named people, like a normal opening."""

    def __init__(self, place, people, lines):
        self.place, self.people, self.lines = place, people, lines
        self.dest = "the old quay" if "market" in place else "the cargo deck"
        self.seen = []

    def __call__(self, n, kwargs):
        self.seen.append("\n".join(str(m.get("content") or "") for m in kwargs["messages"]))
        rolling = {
            "scene": self.place, "location": self.place, "known_rooms": [self.place, self.dest], "locations": [self.place, self.dest],
            "npcs": [{"name": p, "npc_id": f"npc-{i}{'0' * 9}", "role": "local", "last_seen": self.place, "stance": "neutral"}
                     for i, p in enumerate(self.people)],
            "relationship_vectors": [{"name": p, "trust": 60} for p in self.people], "deceased": [],
        }
        line = self.lines[min(n - 1, len(self.lines) - 1)]
        return (
            f"<rolling_state>{json.dumps(rolling)}</rolling_state>\n<narrative>{line}</narrative>\n"
            f"<choices>\nA. Wait {n}\nB. Look {n}\nC. Speak {n}\nD. Leave {n}\n</choices>\n"
            "<state>\nHealth: ok\nPressure: steady\nPosition: here\n</state>\n<ledger>\nCarried: lantern\n</ledger>\n"
        )


def _create(tc, dev, **extra):
    body = {"device_id": dev, "genre": "fantasy", "difficulty": "standard", "creation_request_id": f"c-{uuid.uuid4()}"}
    body.update(extra)
    r = tc.post("/api/story/new", json=body)
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def _act(tc, sid, dev, text, expected):
    r = tc.post("/api/story/action", headers=headers(dev), json={
        "session_id": sid, "action_text": text, "action_request_id": f"a-{uuid.uuid4()}", "expected_turn_count": expected})
    assert r.status_code == 200, r.text


STORIES = [
    ("fantasy", {}, "the salt market", ["Brenna Oake", "Tomas Reed"],
     ["Brenna Oake haggles over lamp oil while Tomas Reed watches the quay.",
      "Brenna Oake mentions a narrow smugglers stair that descends toward the old quay, and Tomas Reed goes quiet.",
      "Tomas Reed shrugs and Brenna Oake counts her coins."]),
    ("scifi", {"custom_premise": "A salvage crew on a derelict ferry, Ilse and Dov, arguing over the airlock."}, "the ferry airlock",
     ["Ilse Marrow", "Dov Kask"],
     ["Ilse Marrow and Dov Kask argue beside the ferry airlock.",
      "Ilse Marrow taps a maintenance crawlway that descends toward the cargo deck, and Dov Kask pretends not to hear.",
      "Dov Kask sighs and Ilse Marrow checks the seals."]),
]


def _play(tc, dev, genre, extra, place, people, lines):
    story = Storyteller(place, people, lines)
    fake = FakeGateway(on_request=story).install()
    try:
        sid = _create(tc, dev, genre=genre, **extra)
        _act(tc, sid, dev, "Look around", 1)
        _act(tc, sid, dev, "Ask quietly", 2)
    finally:
        fake.restore()
    return sid


def test_normally_created_saves_offer_moves_in_two_genres_and_a_custom_premise(env):
    with make_client() as tc:
        for genre, extra, place, people, lines in STORIES:
            dev = device()
            sid = _play(tc, dev, genre, extra, place, people, lines)
            offered = moves(tc, sid, dev)
            assert set(offered) >= {"challenge", "bargain", "route", "regard", "build", "signal", "teach"}, list(offered)
            quote = lines[1].split("that ")[1].split(",")[0]
            row = env.sync_db.turns.find_one({"session_id": sid, "paragraphs": {"$elemMatch": {"$regex": quote}}})
            assert row, [t["paragraphs"] for t in env.sync_db.turns.find({"session_id": sid})]
            found = {"via": {"turn": row["turn_number"], "paragraph": row["paragraphs"].index(next(x for x in row["paragraphs"] if quote in x)), "quote": quote}, "to": "the old quay" if "market" in place else "the cargo deck"}
            fake = FakeGateway(on_request=Storyteller(place, people, lines)).install()
            try:
                r = move(tc, sid, dev, 3, "route", found)
            finally:
                fake.restore()
            assert r.status_code == 200, r.text
            routes = doc(env, sid)["play_state"]["route"]["routes"]
            assert len(routes) == 1 and routes[0]["a"] == place


def test_old_save_without_play_state_still_plays_and_lists_moves(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, {"scene": "the yard", "npcs": [], "relationship_vectors": []}, [["Rain on the yard."]])
    assert "play_state" not in doc(env, sid)
    assert moves(client, sid, dev)["route"]["routes"] == []
    r = client.post("/api/story/action", headers=headers(dev), json={
        "session_id": sid, "action_text": "Wait", "action_request_id": "old-1", "expected_turn_count": 1})
    assert r.status_code == 200, r.text


def test_branch_keeps_play_state_and_diverges_independently(client, env, narrator):
    dev = device()
    place = "the hotel lobby"
    rolling = {"scene": place, "location": place, "known_rooms": [place, "the boiler room"], "locations": [place, "the boiler room"],
               "npcs": [{"name": "Mr. Pell", "npc_id": "npc-pell0000000", "role": "porter", "last_seen": place, "stance": "ally"}],
               "relationship_vectors": [{"name": "Mr. Pell", "trust": 70}], "deceased": []}
    turns = [["Mr. Pell polishes the bell."],
             ["Behind the desk a narrow service passage descends toward the boiler room, and Mr. Pell looks away."]]
    sid = seed(env.sync_db, dev, rolling, turns)
    found = {"via": {"turn": 2, "paragraph": 0, "quote": "narrow service passage descends toward the boiler room"}, "to": "the boiler room"}
    assert move(client, sid, dev, 2, "route", found).status_code == 200
    before = doc(env, sid)["play_state"]["route"]["routes"]
    b = client.post(f"/api/story/session/{sid}/branch", json={"device_id": dev, "request_id": f"b-{uuid.uuid4()}"}, headers=headers(dev))
    assert b.status_code == 200, b.text
    body = b.json()
    bid = body.get("session_id") or (body.get("session") or {}).get("id") or body["branch"]["id"]
    assert doc(env, bid)["play_state"]["route"]["routes"] == before
    rid = before[0]["id"]
    r = move(client, bid, dev, 3, "route", {"route_id": rid, "with": "Mr. Pell"}, op="teach")
    assert r.status_code == 200, r.text
    assert doc(env, sid)["play_state"]["route"]["routes"] == before
    assert "Mr. Pell" in {k["name"] for k in doc(env, bid)["play_state"]["route"]["routes"][0]["knowers"]}
