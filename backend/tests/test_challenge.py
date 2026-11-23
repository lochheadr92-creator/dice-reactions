"""Challenge a claim with evidence, through the real turn handler, save and player views.

Two unrelated settings (a noir bar, a prehistoric river camp) run the same engine. The narrator is an
offline fixture that echoes only what the engine tells it.
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

import challenge_engine as chal  # noqa: E402
from reliability_support import FakeGateway, MongoEnv, insert_session, make_client, relax_rate_limits  # noqa: E402
from player_features_support import FIXED_NOW, device, headers  # noqa: E402

BAR = "the Blue Lantern bar"
CAMP = "the river camp"


def noir(trust=45):
    return {
        "scene": BAR, "location": BAR, "character": "tired", "known_rooms": [BAR], "locations": [BAR],
        "npcs": [
            {"name": "Mrs. Vance", "npc_id": "npc-vance000000", "role": "witness", "last_seen": BAR, "stance": "neutral"},
            {"name": "Sal Moreno", "npc_id": "npc-sal00000000", "role": "bartender", "last_seen": BAR, "stance": "neutral"},
        ],
        "relationship_vectors": [{"name": "Mrs. Vance", "trust": trust}, {"name": "Sal Moreno", "trust": 50}],
        "deceased": [],
    }


NOIR_TURNS = [
    ['Mrs. Vance wipes the counter and will not meet your eye. "I was home all night," Mrs. Vance says.'],
    ['Sal Moreno leans in over the bar. "Vance left at nine, I held the door for her," Sal Moreno says.'],
]


def prehistoric():
    return {
        "scene": CAMP, "location": CAMP, "character": "wary", "known_rooms": [CAMP], "locations": [CAMP],
        "npcs": [{"name": "Tor", "npc_id": "npc-tor000000000", "role": "scout", "last_seen": CAMP, "stance": "neutral"}],
        "relationship_vectors": [{"name": "Tor", "trust": 50}],
        "deceased": [],
    }


CAMP_TURNS = [
    ['Tor drops his spear by the fire. "The river trail is safe, no beast has crossed it," Tor says.'],
    ["You walk the river trail at dusk and find fresh cat tracks pressed deep into the mud."],
]


def seed(sync_db, dev, rolling, turns, extra=None):
    sid = insert_session(sync_db, dev, turn_count=len(turns), rolling=rolling,
                         extra={"title": "Challenge", "last_state": {"Health": "ok"}, **(extra or {})})
    for i, paras in enumerate(turns, 1):
        text = " ".join(paras)
        sync_db.turns.insert_one({
            "id": str(uuid.uuid4()), "session_id": sid, "turn_number": i, "player_action": None,
            "narrative": text, "canonical_narrative": text, "paragraphs": paras,
            "choices": [{"label": c, "text": f"Seed {c}"} for c in "ABCD"],
            "state": {"Health": "ok"}, "ledger": {"Carried": "a brass lighter; a folded ticket stub"} if i == len(turns) else {},
            "rolling_state": rolling, "raw": "", "debug": {}, "created_at": FIXED_NOW,
        })
    return sid


class Narrator:
    def __init__(self):
        self.seen = []

    def __call__(self, n, kwargs):
        text = "\n".join(str(m.get("content") or "") for m in kwargs["messages"])
        self.seen.append(text)
        bits = [f"The moment stretches (beat {n})."]
        m = re.search(re.escape(chal.RESULT_MARKER) + r"\n- (.*)", text)
        if m:
            bits.append(m.group(1))
        return (
            "<rolling_state>{}</rolling_state>\n"
            f"<narrative>{' '.join(bits)}</narrative>\n"
            f"<choices>\nA. Wait, beat {n}\nB. Look around, beat {n}\nC. Speak, beat {n}\nD. Leave, beat {n}\n</choices>\n"
            "<state>\nHealth: ok\nPressure: steady\nPosition: here\n</state>\n<ledger>\nCarried: nothing\n</ledger>\n"
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
def client(env, narrator):
    fake = FakeGateway(on_request=narrator).install()
    with make_client() as tc:
        yield tc
    fake.restore()


def challenge(client, sid, dev, expected, args, rid=None):
    body = {"session_id": sid, "action_text": "", "action_request_id": rid or f"c-{uuid.uuid4()}",
            "expected_turn_count": expected, "move": {"kind": "challenge", "args": args}}
    return client.post("/api/story/action", json=body, headers=headers(dev))


def _session(client, sid, dev):
    return client.get(f"/api/story/session/{sid}", headers=headers(dev)).json()


def _doc(env, sid):
    return env.sync_db.sessions.find_one({"id": sid}, {"_id": 0})


VANCE_OWN = {"turn": 1, "paragraph": 0, "quote": "I was home all night", "speaker": "Mrs. Vance"}
SAL_SAYS = {"turn": 2, "paragraph": 0, "quote": "Vance left at nine, I held the door for her", "speaker": "Sal Moreno"}


def test_noir_witness_confronted_with_two_accounts_concedes_only_what_they_show(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, noir(), NOIR_TURNS)
    r = challenge(client, sid, dev, 2, {"audience": "Mrs. Vance", "subject": VANCE_OWN, "evidence": [SAL_SAYS, {"item": "folded ticket stub"}]})
    assert r.status_code == 200, r.text
    assert "concedes" in " ".join(r.json()["turn"]["paragraphs"])
    sent = narrator.seen[-1]
    assert chal.RESULT_MARKER in sent and "folded ticket stub" in sent
    doc = _doc(env, sid)
    rec = doc["play_state"]["challenge"]["records"][0]
    assert rec["outcome"] == "concession"
    # An accusation is a record of what was said, never a world fact.
    rolling = doc["rolling_state"]
    assert "guilty" not in json.dumps(rolling).lower() and "lied" not in json.dumps(rolling).lower()
    view = _session(client, sid, dev)["session"]
    assert view["play_view"]["challenge"][0]["audience"] == "Mrs. Vance"
    assert "witnesses" not in json.dumps(view["play_view"])


def test_prehistoric_scout_challenged_with_observed_tracks_explains(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, prehistoric(), CAMP_TURNS)
    tracks = {"turn": 2, "paragraph": 0, "quote": "fresh cat tracks pressed deep into the mud"}
    r = challenge(client, sid, dev, 2, {"audience": "Tor", "subject": {"turn": 1, "paragraph": 0, "quote": "The river trail is safe", "speaker": "Tor"}, "evidence": [tracks]})
    assert r.status_code == 200, r.text
    prose = " ".join(r.json()["turn"]["paragraphs"])
    assert "gives an account" in prose and "not established truth" in prose
    assert _doc(env, sid)["play_state"]["challenge"]["records"][0]["outcome"] == "explanation"


def test_held_back_evidence_and_bystanders_stay_out(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, noir(), NOIR_TURNS)
    r = challenge(client, sid, dev, 2, {"audience": "Mrs. Vance", "subject": VANCE_OWN, "evidence": [{"item": "brass lighter"}]})
    assert r.status_code == 200, r.text
    block = re.search(re.escape(chal.RESULT_MARKER) + r".*?knows only what is listed", narrator.seen[-1], re.S).group(0)
    assert "brass lighter" in block and "ticket stub" not in block
    knowledge = _doc(env, sid)["play_state"]["challenge"]["knowledge"]
    assert {k["holder"]["name"] for k in knowledge} == {"Mrs. Vance"}  # Sal did not hear it
    assert not any("ticket stub" in k["fact"] for k in knowledge)


def test_missing_prerequisite_refuses_without_a_turn(client, env):
    dev = device()
    rolling = noir()
    rolling["npcs"][0]["last_seen"] = "the cellar"
    rolling["npcs"][1]["last_seen"] = "the cellar"
    sid = seed(env.sync_db, dev, rolling, [["Rain taps the empty bar. No one speaks."]])
    r = challenge(client, sid, dev, 1, {"audience": "Mrs. Vance", "subject": VANCE_OWN, "evidence": [{"item": "brass lighter"}]})
    assert r.status_code == 422
    assert _doc(env, sid)["turn_count"] == 1
    opts = client.get(f"/api/story/session/{sid}/moves", headers=headers(dev)).json()["moves"]["challenge"]
    assert opts["available"] is False and opts["reason"]


def test_invented_evidence_is_refused(client, env):
    dev = device()
    sid = seed(env.sync_db, dev, noir(), NOIR_TURNS)
    for evidence in ([{"item": "silver revolver"}], [{"turn": 2, "paragraph": 0, "quote": "She was at the docks"}]):
        r = challenge(client, sid, dev, 2, {"audience": "Mrs. Vance", "subject": VANCE_OWN, "evidence": evidence})
        assert r.status_code in (404, 422), r.text
    assert _doc(env, sid)["turn_count"] == 2


def test_retry_of_the_same_challenge_is_one_turn_one_record(client, env):
    dev = device()
    sid = seed(env.sync_db, dev, noir(), NOIR_TURNS)
    args = {"audience": "Mrs. Vance", "subject": VANCE_OWN, "evidence": [SAL_SAYS]}
    a = challenge(client, sid, dev, 2, args, rid="same-key-0001")
    b = challenge(client, sid, dev, 2, args, rid="same-key-0001")
    assert a.status_code == 200 and b.status_code == 200
    doc = _doc(env, sid)
    assert doc["turn_count"] == 3
    assert len(doc["play_state"]["challenge"]["records"]) == 1


def test_preview_reads_only_and_keeps_nothing(client, env):
    dev = device()
    sid = seed(env.sync_db, dev, noir(), NOIR_TURNS)
    r = client.post(f"/api/story/session/{sid}/moves/preview", headers=headers(dev),
                    json={"kind": "challenge", "args": {"audience": "Mrs. Vance", "subject": VANCE_OWN, "evidence": [SAL_SAYS]}})
    assert r.status_code == 200 and r.json()["can_commit"] is True
    assert "play_state" not in _doc(env, sid)


def test_options_list_what_the_scene_supports(client, env):
    dev = device()
    sid = seed(env.sync_db, dev, prehistoric(), CAMP_TURNS)
    opts = client.get(f"/api/story/session/{sid}/moves", headers=headers(dev)).json()["moves"]["challenge"]
    assert opts["available"] is True
    assert [a["name"] for a in opts["audiences"]] == ["Tor"]
    assert any("river trail is safe" in s["text"] for s in opts["statements"])


def test_after_a_handover_a_former_perspective_pin_is_no_evidence(client, env):
    dev = device()
    turns = NOIR_TURNS + [['Sal Moreno polishes a glass and watches the door. "Closing soon," Sal Moreno says.']]
    sid = seed(env.sync_db, dev, noir(), turns)
    pin = client.post(f"/api/story/session/{sid}/notebook/pins", headers=headers(dev),
                      json={"turn_number": 1, "paragraph_index": 0, "quote": "I was home all night"})
    assert pin.status_code in (200, 201), pin.text
    pin_id = pin.json()["pin"]["id"]
    listing = client.get(f"/api/story/session/{sid}/handover", headers=headers(dev)).json()
    sal = next((c for c in listing["candidates"] if c["name"] == "Sal Moreno"), None)
    assert sal, listing
    ho = client.post(f"/api/story/session/{sid}/handover", headers=headers(dev),
                     json={"request_id": f"ho-{uuid.uuid4()}", "successor_id": sal["id"], "expected_turn_count": 3})
    assert ho.status_code == 200, ho.text
    n = _doc(env, sid)["turn_count"]
    # Sal now plays. Turn 1 never named Sal, so Sal was not shown it, pin or not.
    r = challenge(client, sid, dev, n, {"audience": "Mrs. Vance", "subject": {"turn": 1, "paragraph": 0, "quote": "I was home all night", "speaker": "Mrs. Vance"},
                                         "evidence": [{"pin_id": pin_id}]})
    assert r.status_code == 422, r.text
    r = challenge(client, sid, dev, n, {"audience": "Mrs. Vance", "subject": {"turn": 3, "paragraph": 0, "quote": "Closing soon", "speaker": "Sal Moreno"},
                                         "evidence": [{"pin_id": pin_id}]})
    assert r.status_code == 422, r.text
    assert _doc(env, sid)["turn_count"] == n
    opts = client.get(f"/api/story/session/{sid}/moves", headers=headers(dev)).json()["moves"]["challenge"]
    assert all(s["turn"] != 1 for s in opts["passages"])
