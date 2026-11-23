"""Teach another character a skill: a chancery apprentice and an observatory colleague, one engine."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from play_moves_support import *  # noqa: F401,F403,E402
from play_moves_support import client, device, doc, env, headers, move, moves, narrator, seed, session_view  # noqa: F401,E402

CHANCERY, DOME = "the royal chancery", "the observatory dome"


def chancery(wick_trust=60):
    return {
        "scene": CHANCERY, "location": CHANCERY, "known_rooms": [CHANCERY], "locations": [CHANCERY],
        "npcs": [{"name": "Wick", "npc_id": "npc-wick0000000", "role": "apprentice", "last_seen": CHANCERY},
                 {"name": "Dara", "npc_id": "npc-dara0000000", "role": "clerk", "last_seen": CHANCERY}],
        "relationship_vectors": [{"name": "Wick", "trust": wick_trust}, {"name": "Dara", "trust": 50}], "deceased": [],
    }


CHANCERY_TURNS = [
    ["Wick sweeps wax shavings from the desk. Dara copies a ledger without looking up."],
    ["You hold the king's seal to the lamp and see the wax has been slipped from another letter. Wick leans in to watch."],
    ["Dara sighs over the ledger. Wick fetches a fresh stack of sealed letters."],
]
DEMO = {"turn": 2, "paragraph": 0, "quote": "the wax has been slipped from another letter"}


def dome(trust=55):
    return {
        "scene": DOME, "location": DOME, "known_rooms": [DOME], "locations": [DOME],
        "npcs": [{"name": "Dr. Imre", "npc_id": "npc-imre0000000", "role": "colleague", "last_seen": DOME},
                 {"name": "Mara", "npc_id": "npc-mara0000000", "role": "night assistant", "last_seen": DOME}],
        "relationship_vectors": [{"name": "Dr. Imre", "trust": trust}, {"name": "Mara", "trust": 45}], "deceased": [],
    }


DOME_TURNS = [
    ["Dr. Imre cleans the great lens. Mara logs the night's readings."],
    ["You run a finger down the observation log and find one missing interval where the star count jumps. Dr. Imre frowns at the page."],
    ["Dr. Imre hums over the star charts. Mara yawns."],
]


def _teach(client, sid, dev, expected, learner, skill, effect, demo, on, rid=None):
    return move(client, sid, dev, expected, "teach", {"learner": learner, "skill": skill, "effect": effect, "demonstrated": demo, "practise_on": on}, rid=rid)


def _skills(env, sid):
    return doc(env, sid)["play_state"]["teach"]["skills"]


def test_two_lessons_make_a_skill_for_one_character_only(client, env, narrator):
    dev = device()
    narrator.carried = "king's seal; spare letter"
    sid = seed(env.sync_db, dev, chancery(), CHANCERY_TURNS, carried="king's seal; spare letter")
    first = _teach(client, sid, dev, 3, "Wick", "forged seals", "verify", DEMO, {"item": "king's seal"})
    assert first.status_code == 200, first.text
    assert "is not there yet" in narrator.seen[-1] and _skills(env, sid) == []
    again = _teach(client, sid, dev, 4, "Wick", "forged seals", "verify", DEMO, {"item": "spare letter"})
    assert again.status_code == 200 and "has now got it" in narrator.seen[-1]
    sk = _skills(env, sid)
    assert [(s["holder"]["name"], s["effect"]) for s in sk] == [("Wick", "verify")]  # Dara watched and learned nothing
    view = session_view(client, sid, dev)["play_view"]["teach"]
    assert view["skills"][0]["who"] == "Wick" and view["lessons"] == []


def test_the_apprentice_notices_on_their_own_and_the_clerk_does_not(client, env, narrator):
    dev = device()
    narrator.carried = "king's seal; spare letter"
    sid = seed(env.sync_db, dev, chancery(), CHANCERY_TURNS, carried="king's seal; spare letter")
    _teach(client, sid, dev, 3, "Wick", "forged seals", "verify", DEMO, {"item": "king's seal"})
    _teach(client, sid, dev, 4, "Wick", "forged seals", "verify", DEMO, {"item": "spare letter"})
    client.post("/api/story/action", headers=headers(dev), json={"session_id": sid, "action_text": "Hand Wick the sealed letters", "action_request_id": "h-1", "expected_turn_count": 5})
    standing = narrator.seen[-1].split("[SKILL_STANDING_V1]")[1].split("\n\n")[0]
    assert "Wick learned forged seals" in standing and "may point it out on their own" in standing
    assert "Dara learned" not in standing and "cannot, unless it is plain" in standing  # the player's own character has no such skill


def test_after_handover_the_learner_can_use_it_and_the_clerk_cannot(client, env, narrator):
    for successor, expect_ok in (("Wick", True), ("Dara", False)):
        dev = device()
        narrator.carried = "king's seal; spare letter"
        sid = seed(env.sync_db, dev, chancery(), CHANCERY_TURNS, carried="king's seal; spare letter")
        _teach(client, sid, dev, 3, "Wick", "forged seals", "verify", DEMO, {"item": "king's seal"})
        _teach(client, sid, dev, 4, "Wick", "forged seals", "verify", DEMO, {"item": "spare letter"})
        cands = {c["name"]: c["id"] for c in client.get(f"/api/story/session/{sid}/handover", headers=headers(dev)).json()["candidates"]}
        n = doc(env, sid)["turn_count"]
        ho = client.post(f"/api/story/session/{sid}/handover", headers=headers(dev), json={"request_id": f"ho-{uuid.uuid4()}", "successor_id": cands[successor], "expected_turn_count": n})
        assert ho.status_code == 200, ho.text
        n = doc(env, sid)["turn_count"]
        d = doc(env, sid)
        last = env.sync_db.turns.find_one({"session_id": sid}, sort=[("turn_number", -1)])
        env.sync_db.turns.update_one({"_id": last["_id"]}, {"$set": {"ledger": {"Carried": "forged-looking decree"}}})
        r = move(client, sid, dev, n, "teach", {"op": "use", "effect": "verify", "target": {"item": "forged-looking decree"}})
        if expect_ok:
            assert r.status_code == 200, r.text
            assert "tell a genuine thing from a forgery" in narrator.seen[-1] and "Do not invent a flaw" in narrator.seen[-1]
        else:
            assert r.status_code == 422  # a character who only heard a lesson happened gains no skill


def test_observatory_colleague_learns_to_spot_a_missing_interval(client, env, narrator):
    dev = device()
    narrator.carried = "star chart; pencil"
    sid = seed(env.sync_db, dev, dome(), DOME_TURNS, carried="star chart; pencil")
    demo = {"turn": 2, "paragraph": 0, "quote": "find one missing interval where the star count jumps"}
    assert _teach(client, sid, dev, 3, "Dr. Imre", "missing intervals", "audit", demo, {"item": "star chart"}).status_code == 200
    assert _teach(client, sid, dev, 4, "Dr. Imre", "missing intervals", "audit", demo, {"item": "pencil"}).status_code == 200
    assert [(s["holder"]["name"], s["effect"]) for s in _skills(env, sid)] == [("Dr. Imre", "audit")]
    client.post("/api/story/action", headers=headers(dev), json={"session_id": sid, "action_text": "Open the record", "action_request_id": "o-1", "expected_turn_count": 5})
    standing = narrator.seen[-1].split("[SKILL_STANDING_V1]")[1].split("\n\n")[0]
    assert "notice what is missing or out of sequence" in standing and "Mara" not in standing


def test_being_taught_by_someone_shown_doing_it(client, env, narrator):
    dev = device()
    turns = [["Dr. Imre cleans the great lens. Mara logs the night's readings."],
             ["Dr. Imre kneels by the sill and reads the faint scuffs and smears left on the dome rail by whoever passed."]]
    narrator.carried = "star chart; pencil"
    sid = seed(env.sync_db, dev, dome(), turns, carried="star chart; pencil")
    demo = {"turn": 2, "paragraph": 0, "quote": "reads the faint scuffs and smears left on the dome rail"}
    args = {"teacher": "Dr. Imre", "skill": "scuffs and smears", "effect": "trace", "demonstrated": demo}
    assert move(client, sid, dev, 2, "teach", {**args, "practise_on": {"item": "pencil"}}).status_code == 200
    assert move(client, sid, dev, 3, "teach", {**args, "practise_on": {"item": "star chart"}}).status_code == 200
    mine = _skills(env, sid)[0]
    assert mine["effect"] == "trace" and mine["from"]["name"] == "Dr. Imre" and mine["holder"]["id"] == "player"
    assert move(client, sid, dev, 4, "teach", {"op": "use", "effect": "trace", "target": {"item": "pencil"}}).status_code == 200


def test_prerequisites_and_retries(client, env, narrator):
    dev = device()
    narrator.carried = "king's seal"
    sid = seed(env.sync_db, dev, chancery(wick_trust=5), CHANCERY_TURNS, carried="king's seal")
    assert _teach(client, sid, dev, 3, "Wick", "forged seals", "verify", DEMO, {"item": "king's seal"}).status_code == 422  # unwilling
    narrator.carried = "king's seal"
    sid2 = seed(env.sync_db, dev, chancery(), CHANCERY_TURNS, carried="king's seal")
    bad_demo = {"turn": 1, "paragraph": 0, "quote": "Wick sweeps wax shavings"}
    assert _teach(client, sid2, dev, 3, "Wick", "forged seals", "verify", bad_demo, {"item": "king's seal"}).status_code == 422  # not shown doing it
    assert _teach(client, sid2, dev, 3, "Wick", "forged seals", "verify", DEMO, {"item": "crown jewels"}).status_code == 422  # nothing real to practise on
    assert move(client, sid2, dev, 3, "teach", {"op": "use", "effect": "verify", "target": {"item": "king's seal"}}).status_code == 422  # no skill of your own
    a = _teach(client, sid2, dev, 3, "Wick", "forged seals", "verify", DEMO, {"item": "king's seal"}, rid="les-0001")
    b = _teach(client, sid2, dev, 3, "Wick", "forged seals", "verify", DEMO, {"item": "king's seal"}, rid="les-0001")
    assert a.status_code == b.status_code == 200
    les = doc(env, sid2)["play_state"]["teach"]["lessons"]
    assert len(les) == 1 and les[0]["turns"] == [4] and doc(env, sid2)["turn_count"] == 4
    # A second lesson on the very same turn number is refused; it must be a later turn.
    assert doc(env, sid2)["play_state"]["teach"]["skills"] == []
