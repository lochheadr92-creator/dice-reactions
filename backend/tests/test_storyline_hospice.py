"""A storyline none of the feature tests use: a blizzard, a mountain hospice, a stolen relic.

Nothing here is the ferry dock. Different people, places, items and vocabulary, played through the
real turn, save and player-visibility paths. The narrator is a deterministic fixture that writes
only what the engine tells it, so any leak or invention is the engine's doing, not the fixture's.

It checks that the engine rules hold outside the setting they were built in: who knows what,
who carries what, relays that need a real route, orders the engine does not understand being
refused, and a handover plus a branch that keep the story's facts apart.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import claim_engine as ce  # noqa: E402
import npc_possessions as np  # noqa: E402
from reliability_support import FakeGateway, MongoEnv, insert_session, make_client, relax_rate_limits  # noqa: E402
from player_features_support import FIXED_NOW, device, dump, headers, session_doc, turn_docs  # noqa: E402

HALL, TOWER, CELLAR, INFIRMARY, GATE = "the hospice hall", "the bell tower", "the cellar", "the infirmary", "the pass gate"
CORVIN_ITEMS = ["iron key", "tithe ledger"]
TAMSIN_ITEMS = ["willow salve", "oil lantern"]
OKU_ITEMS = ["brass compass", "wolfsbane vial"]
HIDDEN_FOR_PLAYER = ["iron key", "tithe ledger", "brass compass", "wolfsbane vial"]
CLAIM = "The relic thief is hiding in the cellar"


def hospice(*, tamsin_contacts=("Warden Hale",), oku_here=False):
    return {
        "scene": HALL, "location": HALL, "character": "steady",
        "known_rooms": [HALL, TOWER, CELLAR, INFIRMARY, GATE],
        "locations": [HALL, TOWER, CELLAR, INFIRMARY, GATE],
        "npcs": [
            {"name": "Abbot Corvin", "npc_id": "npc-abbot000000", "role": "abbot", "last_seen": HALL,
             "inventory": list(CORVIN_ITEMS), "stance": "neutral"},
            {"name": "Brother Tamsin", "npc_id": "npc-tamsin00000", "role": "infirmarian", "last_seen": HALL,
             "inventory": list(TAMSIN_ITEMS), "stance": "ally", "contacts": list(tamsin_contacts)},
            {"name": "Warden Hale", "npc_id": "npc-warden00000", "role": "warden", "last_seen": GATE,
             "inventory": ["signal horn"]},
            {"name": "Oku", "npc_id": "npc-oku00000000", "role": "pilgrim", "last_seen": HALL if oku_here else INFIRMARY,
             "inventory": list(OKU_ITEMS), "stance": "neutral"},
        ],
        "relationship_vectors": [
            {"name": "Abbot Corvin", "trust": 20},
            {"name": "Brother Tamsin", "trust": 70},
            {"name": "Oku", "trust": 15},
        ],
        "deceased": [],
    }


def seed(sync_db, dev, rolling):
    sid = insert_session(sync_db, dev, turn_count=1, rolling=rolling,
                         extra={"title": "The Hospice Relic", "last_state": {"Health": "stable"}})
    para = "Abbot Corvin bars the door against the snow. Brother Tamsin tends the fire. Warden Hale stamps at the pass gate."
    sync_db.turns.insert_one({
        "id": str(uuid.uuid4()), "session_id": sid, "turn_number": 1, "player_action": None,
        "narrative": para, "canonical_narrative": para, "paragraphs": [para],
        "choices": [{"label": c, "text": f"Seed {c}"} for c in "ABCD"],
        "state": {"Health": "stable"}, "ledger": {}, "rolling_state": rolling, "raw": "", "debug": {},
        "created_at": FIXED_NOW,
    })
    return sid


class Narrator:
    """Writes only what the engine's directives say. Names the people so they can earn a handover."""

    def __init__(self):
        self.seen = []
        self.rolling_for_call = {}

    def __call__(self, n, kwargs):
        text = "\n".join(str(m.get("content") or "") for m in kwargs["messages"])
        self.seen.append(text)
        bits = [f"Snow hammers the shutters (beat {n}). Brother Tamsin and Abbot Corvin keep the hall."]
        m = re.search(re.escape(np.DIRECTIVE_MARKER) + r" RESULT\n- (.*)", text)
        if m:
            bits.append(m.group(1))
        if ce.DIRECTIVE_MARKER in text:
            bits.append("A lantern bobs down the cellar stair where Warden Hale is searching.")
        rolling = json.dumps(self.rolling_for_call.get(n, {}))
        return (
            f"<rolling_state>{rolling}</rolling_state>\n<narrative>{' '.join(bits)}</narrative>\n"
            f"<choices>\nA. Wait, beat {n}\nB. Warm your hands, beat {n}\nC. Check the door, beat {n}\n"
            f"D. Climb the stair, beat {n}\n</choices>\n"
            "<state>\nHealth: stable\nPressure: steady\nPosition: here\n</state>\n<ledger>\nCarried: nothing\n</ledger>\n"
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
def narrator():
    return Narrator()


@pytest.fixture()
def fake(narrator):
    f = FakeGateway(on_request=narrator).install()
    yield f
    f.restore()


@pytest.fixture()
def client(env, fake):
    with make_client() as tc:
        yield tc


def _act(client, sid, dev, expected, *, text="Warm your hands by the fire", tell=None, order=None, rid=None):
    body = {"session_id": sid, "action_text": text, "action_request_id": rid or f"a-{uuid.uuid4()}",
            "expected_turn_count": expected}
    if tell:
        body["disclosure"] = {"recipient": tell[0], "claim": tell[1], "aloud": False}
    if order:
        body["order"] = {"recipient": order[0], "text": order[1]}
    return client.post("/api/story/action", json=body, headers=headers(dev))


def _prose(r):
    return " ".join(r.json()["turn"]["paragraphs"])


def _shown(client, sid, dev):
    return client.get(f"/api/story/session/{sid}", headers=headers(dev)).json()


def test_a_whole_evening_in_the_hospice(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, hospice())
    log = []

    # 1. A man with a low opinion of a stranger keeps his pockets to himself.
    r = _act(client, sid, dev, 1, text="Ask Abbot Corvin what he is carrying")
    assert r.status_code == 200, r.text
    log.append(("ask Corvin (trust 20)", _prose(r)))
    assert "iron key" not in _prose(r) and "tithe ledger" not in _prose(r)
    assert "does not want to say what they carry" in narrator.seen[-1]
    assert _entry(env, sid, "npc-abbot000000")["known"] == []

    # 2. A friend with good standing answers, and what she says becomes known.
    r = _act(client, sid, dev, 2, text="Ask Brother Tamsin what she is carrying")
    assert r.status_code == 200, r.text
    log.append(("ask Tamsin (trust 70)", _prose(r)))
    assert "willow salve" in _prose(r) and "oil lantern" in _prose(r)
    assert sorted(_entry(env, sid, "npc-tamsin00000")["known"]) == sorted(TAMSIN_ITEMS)

    # 3. Asking for something she does not have gets an honest no, not an invented item.
    r = _act(client, sid, dev, 3, text="Ask Brother Tamsin if she has a brass compass")
    assert r.status_code == 200, r.text
    log.append(("ask Tamsin for the compass", _prose(r)))
    assert "does not have what the player asked about" in narrator.seen[-1]
    assert "compass" not in _prose(r)

    # 4. Someone who is not in the room cannot be interrogated, and nothing about Oku leaks.
    r = _act(client, sid, dev, 4, text="Ask Oku what she is carrying")
    assert r.status_code == 200, r.text
    log.append(("ask Oku (infirmary, absent)", _prose(r)))
    assert "brass compass" not in _prose(r) and "wolfsbane" not in _prose(r)
    assert _entry(env, sid, "npc-oku00000000")["known"] == []

    # 5. The player plants a claim. Tamsin has a route to the warden, who acts on it.
    r = _act(client, sid, dev, 5, text="Tell Tamsin quietly", tell=("Brother Tamsin", CLAIM))
    assert r.status_code == 200, r.text
    log.append(("tell Tamsin the cellar claim", _prose(r)))
    for n in range(6, 11):
        r = _act(client, sid, dev, n)
        assert r.status_code == 200, r.text
        log.append((f"turn {n + 1}", _prose(r)))
    searches = [t for who, t in log if "searching" in t]
    assert searches, log
    state = session_doc(env.sync_db, sid)["claim_state"]
    assert [(a["actor"]["name"], a["location"]) for a in state["actions"]] == [("Warden Hale", "the cellar")]
    belief = {(b["actor"]["name"], b["source"]) for b in state["beliefs"]}
    assert ("Brother Tamsin", "told") in belief and ("Warden Hale", "relayed") in belief
    assert not any(name == "Abbot Corvin" for name, _ in belief)   # nobody carried it to the abbot

    # 6. At no point did the player or the narrator get the pockets of people who never told.
    # (The compass is excluded: the player typed that word themselves in turn 3.)
    never_named = ("iron key", "tithe ledger", "wolfsbane vial")
    for blob in narrator.seen:
        for hidden in never_named:
            assert hidden not in blob, hidden
    shown = dump(_shown(client, sid, dev))
    for hidden in never_named + ("npc_ledger", "beliefs", "relays"):
        assert hidden not in shown, hidden
    print("\n=== PLAY TRANSCRIPT (hospice) ===")
    for who, text in log:
        print(f"[{who}] {text}")


def _entry(env, sid, npc_id):
    return session_doc(env.sync_db, sid)["npc_ledger"]["rows"][npc_id]


def test_orders_outside_the_engine_vocabulary_are_refused_not_invented(client, env, narrator):
    """The engine knows a water mark and a parcel. A hospice order must be refused cleanly."""
    dev = device()
    sid = seed(env.sync_db, dev, hospice())
    before = session_doc(env.sync_db, sid)
    p = client.post(f"/api/story/session/{sid}/orders/preview",
                    json={"recipient": "Brother Tamsin", "text": "If the bell rings twice, bar the cellar door."},
                    headers=headers(dev))
    assert p.status_code == 200, p.text
    body = p.json()
    assert body["can_commit"] is False and body["understood"] is None and body["issues"]
    r = _act(client, sid, dev, 1, order=("Brother Tamsin", "If the bell rings twice, bar the cellar door."))
    assert r.status_code in (400, 422), r.text
    after = session_doc(env.sync_db, sid)
    assert after["turn_count"] == before["turn_count"] and len(turn_docs(env.sync_db, sid)) == 1
    assert narrator.seen == []          # refused before any paid work


def test_a_stranger_does_not_hand_over_a_key_and_a_friend_does(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, hospice())
    r = _act(client, sid, dev, 1, text="Ask Abbot Corvin to give me the iron key")
    assert r.status_code == 200, r.text
    assert "does not trust the player enough" in narrator.seen[-1] and "iron key" not in _prose(r)
    assert _entry(env, sid, "npc-abbot000000")["inventory"] == CORVIN_ITEMS      # nothing changed hands
    r = _act(client, sid, dev, 2, text="Ask Brother Tamsin to give me the willow salve")
    assert r.status_code == 200, r.text
    assert "hands the player their willow salve" in _prose(r)
    assert _entry(env, sid, "npc-tamsin00000")["inventory"] == ["oil lantern"]


def test_handover_then_branch_keep_the_two_sides_apart(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, hospice())
    for n in range(1, 3):
        assert _act(client, sid, dev, n).status_code == 200
    # Names appear in published prose every turn, so Tamsin and Corvin have each earned a turn.
    listing = client.get(f"/api/story/session/{sid}/handover", headers=headers(dev)).json()
    ids = {c["id"] for c in listing["candidates"]}
    assert "npc-tamsin00000" in ids and "npc-oku00000000" not in ids
    blob = dump(listing)
    for hidden in HIDDEN_FOR_PLAYER:
        assert hidden not in blob
    ho = client.post(f"/api/story/session/{sid}/handover",
                     json={"request_id": f"ho-{uuid.uuid4()}", "successor_id": "npc-tamsin00000", "expected_turn_count": 3},
                     headers=headers(dev))
    assert ho.status_code == 200, ho.text
    # The save continues as Tamsin; a branch from here is a separate save with the same ledger.
    br = client.post(f"/api/story/session/{sid}/branch",
                     json={"request_id": f"br-{uuid.uuid4()}", "expected_turn_count": 4}, headers=headers(dev))
    assert br.status_code == 200, br.text
    bid = br.json()["session"]["id"]
    assert bid != sid
    assert session_doc(env.sync_db, bid)["npc_ledger"] == session_doc(env.sync_db, sid)["npc_ledger"]
    r = _act(client, bid, dev, 4)
    assert r.status_code == 200, r.text
    assert session_doc(env.sync_db, sid)["turn_count"] == 4         # the original did not move
    shown = dump(_shown(client, bid, dev))
    for hidden in HIDDEN_FOR_PLAYER:
        assert hidden not in shown


def test_notebook_pin_survives_in_a_new_setting(client, env):
    dev = device()
    sid = seed(env.sync_db, dev, hospice())
    pin = client.post(f"/api/story/session/{sid}/notebook/pins",
                      json={"turn_number": 1, "paragraph_index": 0, "quote": "Warden Hale stamps"}, headers=headers(dev))
    assert pin.status_code in (200, 201), pin.text
    nb = client.get(f"/api/story/session/{sid}/notebook", headers=headers(dev)).json()
    assert "Warden Hale stamps" in dump(nb)
