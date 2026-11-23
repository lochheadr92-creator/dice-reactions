"""Change how two other people see each other: a family drama and a survival convoy, one engine."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))
from play_moves_support import *  # noqa: F401,F403,E402
from play_moves_support import client, device, doc, env, headers, move, moves, narrator, seed, session_view  # noqa: F401,E402

PARLOUR, DEPOT, CLINIC = "the family parlour", "the supply depot", "the field clinic"


def family(cal_trust=70):
    return {
        "scene": PARLOUR, "location": PARLOUR, "known_rooms": [PARLOUR], "locations": [PARLOUR],
        "npcs": [
            {"name": "Ben Hartley", "npc_id": "npc-ben00000000", "role": "younger brother", "last_seen": PARLOUR},
            {"name": "Cal Hartley", "npc_id": "npc-cal00000000", "role": "older brother", "last_seen": PARLOUR},
        ],
        "relationship_vectors": [{"name": "Ben Hartley", "trust": 60}, {"name": "Cal Hartley", "trust": cal_trust}], "deceased": [],
    }


FAMILY_TURN = [["Ben Hartley stares at the carpet. Cal Hartley folds his arms by the cold fireplace."]]


def convoy():
    return {
        "scene": DEPOT, "location": DEPOT, "known_rooms": [DEPOT, CLINIC], "locations": [DEPOT, CLINIC],
        "npcs": [
            {"name": "Rook", "npc_id": "npc-rook0000000", "role": "driver", "last_seen": DEPOT},
            {"name": "Dr. Wen", "npc_id": "npc-wen00000000", "role": "medic", "last_seen": DEPOT},
        ],
        "relationship_vectors": [{"name": "Rook", "trust": 66}, {"name": "Dr. Wen", "trust": 58}], "deceased": [],
    }


CONVOY_TURN = [["Rook checks the tyres on the water truck. Dr. Wen counts crates of antibiotics beside the loading ramp."]]


def _edges(env, sid):
    return {(e["holder_name"], e["toward_name"]): e["value"] for e in doc(env, sid)["play_state"]["regard"]["edges"]}


def _move_them(env, sid, where, scene):
    d = doc(env, sid)["rolling_state"]
    for n in d["npcs"]:
        n["last_seen"] = where
        n["location"] = where
    d["scene"] = scene
    d["location"] = scene
    env.sync_db.sessions.update_one({"id": sid}, {"$set": {"rolling_state": d}})


def _wait(client, sid, dev, n, rid):
    r = client.post("/api/story/action", headers=headers(dev), json={"session_id": sid, "action_text": "Wait and watch", "action_request_id": rid, "expected_turn_count": n})
    assert r.status_code == 200, r.text
    return r


def test_vouching_moves_one_direction_only_and_the_errand_is_decided_without_me(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, convoy(), CONVOY_TURN)
    errand = {"asker": "Dr. Wen", "giver": "Rook", "what": "carry the antibiotics to the clinic"}
    r = move(client, sid, dev, 1, "regard", {"op": "vouch", "a": "Dr. Wen", "b": "Rook", "errand": errand})
    assert r.status_code == 200, r.text
    edges = _edges(env, sid)
    assert edges[("Rook", "Dr. Wen")] >= 50 and ("Dr. Wen", "Rook") not in edges  # the medic still distrusts the driver
    # The player's own standing with each of them is untouched by this.
    vec = {v["name"]: v["trust"] for v in doc(env, sid)["rolling_state"]["relationship_vectors"]}
    control = seed(env.sync_db, dev, convoy(), CONVOY_TURN)
    _wait(client, control, dev, 1, "ctl-1")  # an ordinary turn drifts trust on its own; the move adds nothing to that
    assert vec == {v["name"]: v["trust"] for v in doc(env, control)["rolling_state"]["relationship_vectors"]}
    # They go to the clinic together while the player stays at the depot.
    _move_them(env, sid, CLINIC, DEPOT)
    _wait(client, sid, dev, 2, "w-1")
    er = doc(env, sid)["play_state"]["regard"]["errands"][0]
    assert er["status"] == "agreed" and er["seen"] is False
    assert "agrees to" not in " ".join(session_view(client, sid, dev)["play_view"]["regard"][0]["effects"])  # not known yet
    # The player walks in on them: only now is the result told, and it becomes visible.
    _move_them(env, sid, DEPOT, DEPOT)
    _wait(client, sid, dev, 3, "w-2")
    assert "agrees to it" in narrator.seen[-1] or "agrees to" in narrator.seen[-1]
    assert any("agreed to" in e for v in session_view(client, sid, dev)["play_view"]["regard"] for e in v["effects"])


def test_replay_without_my_intervention_gives_a_different_outcome(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, convoy(), CONVOY_TURN)
    # No vouching: plant only the errand through an introduction (regard stays at 'civil').
    errand = {"asker": "Dr. Wen", "giver": "Rook", "what": "carry the antibiotics to the clinic"}
    r = move(client, sid, dev, 1, "regard", {"op": "introduce", "a": "Dr. Wen", "b": "Rook", "errand": errand})
    assert r.status_code == 200, r.text
    _move_them(env, sid, CLINIC, DEPOT)
    _wait(client, sid, dev, 2, "w-1")
    assert doc(env, sid)["play_state"]["regard"]["errands"][0]["status"] == "refused"


def test_family_sibling_helps_after_a_good_word_and_not_after_a_bad_one(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, family(), FAMILY_TURN)
    errand = {"asker": "Ben Hartley", "giver": "Cal Hartley", "what": "lend him the cabin keys"}
    assert move(client, sid, dev, 1, "regard", {"op": "mediate", "a": "Ben Hartley", "b": "Cal Hartley", "errand": errand}).status_code == 200
    e = _edges(env, sid)
    assert e[("Cal Hartley", "Ben Hartley")] > 30 and e[("Ben Hartley", "Cal Hartley")] > 30
    # A distrusted outsider cannot move them.
    low = family(cal_trust=10)
    sid2 = seed(env.sync_db, dev, low, FAMILY_TURN)
    r = move(client, sid2, dev, 1, "regard", {"op": "vouch", "a": "Ben Hartley", "b": "Cal Hartley"})
    assert r.status_code == 200
    assert _edges(env, sid2) == {}
    assert "does not take the player's word" in narrator.seen[-1]


def test_exposing_someone_needs_something_shown_and_is_not_proof(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, family(), FAMILY_TURN)
    bad = move(client, sid, dev, 1, "regard", {"op": "expose", "a": "Ben Hartley", "b": "Cal Hartley", "evidence": {"turn": 1, "paragraph": 0, "quote": "stole the cash"}})
    assert bad.status_code == 422
    ok = move(client, sid, dev, 1, "regard", {"op": "expose", "a": "Ben Hartley", "b": "Cal Hartley", "evidence": {"turn": 1, "paragraph": 0, "quote": "Ben Hartley stares at the carpet"}})
    assert ok.status_code == 200, ok.text
    assert _edges(env, sid)[("Cal Hartley", "Ben Hartley")] < 30
    assert "not what is proven" in " ".join(ok.json()["turn"]["paragraphs"]) or "not what is proven" in narrator.seen[-1]
    assert "guilty" not in str(doc(env, sid)["rolling_state"]).lower()


def test_one_person_is_not_enough(client, env, narrator):
    dev = device()
    rolling = convoy()
    rolling["npcs"][1]["last_seen"] = CLINIC
    sid = seed(env.sync_db, dev, rolling, [["Rook checks the tyres alone."]])
    assert move(client, sid, dev, 1, "regard", {"op": "introduce", "a": "Rook", "b": "Dr. Wen"}).status_code == 422
    assert moves(client, sid, dev)["regard"]["available"] is False


def test_retrying_the_same_word_is_applied_once(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, convoy(), CONVOY_TURN)
    args = {"op": "vouch", "a": "Dr. Wen", "b": "Rook"}
    move(client, sid, dev, 1, "regard", args, rid="v-0001")
    first = _edges(env, sid)[("Rook", "Dr. Wen")]
    move(client, sid, dev, 1, "regard", args, rid="v-0001")
    assert _edges(env, sid)[("Rook", "Dr. Wen")] == first and doc(env, sid)["turn_count"] == 2
