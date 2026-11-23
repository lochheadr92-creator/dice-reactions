"""Feature 1: plant a claim, see which version comes back.

Real action handler, real persistence, real player responses. The narrator is a deterministic
fixture that writes prose from what the engine sends it: it only mentions guards searching the
chapel when the engine's own consequence directive is in the request. The tests never insert
that consequence.
"""

from __future__ import annotations

import copy
import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import claim_engine as ce  # noqa: E402
from reliability_support import FakeGateway, MongoEnv, insert_session, make_client, relax_rate_limits  # noqa: E402
from player_features_support import FIXED_NOW, device, dump, headers, session_doc, turn_docs  # noqa: E402

MILL = "The missing passenger is at the mill"
CHAPEL = "The missing passenger is at the chapel"
SEARCH_PROSE = "Harbour guards are searching the chapel, lanterns bobbing between the pews."
THEORY_PHRASE = "THEORY-PHRASE-quince the innkeeper lied"
TRUTH = {"actual_location": "the boathouse loft"}


def ferry_world(*, innkeeper_contacts=("Dov Marsh",), potboy=False):
    npcs = [
        {"name": "Corin Hale", "npc_id": "npc-ferryman00", "role": "ferryman", "last_seen": "the ferry dock"},
        {"name": "Wren Alder", "npc_id": "npc-innkeeper0", "role": "innkeeper", "last_seen": "the inn",
         "contacts": list(innkeeper_contacts)},
        {"name": "Dov Marsh", "npc_id": "npc-harbourmstr", "role": "harbourmaster", "last_seen": "the harbour office"},
    ]
    if potboy:
        npcs.append({"name": "Tam Pike", "npc_id": "npc-potboy0000", "role": "potboy", "last_seen": "the inn",
                     "within_earshot": True, "contacts": ["Dov Marsh"]})
    return {
        "scene": "the ferry dock", "location": "the ferry dock", "character": "steady",
        "known_rooms": ["the ferry dock", "the inn", "the mill", "the chapel", "the harbour office"],
        "locations": ["the ferry dock", "the inn", "the mill", "the chapel", "the harbour office"],
        "npcs": npcs, "deceased": [], "missing_passenger": copy.deepcopy(TRUTH),
    }


def seed(sync_db, dev, rolling):
    sid = insert_session(sync_db, dev, turn_count=1, rolling=rolling,
                         extra={"title": "Missing Passenger", "last_state": {"Health": "stable"}})
    paragraphs = ["Corin Hale poles the ferry in. Wren Alder waves from the inn. Dov Marsh logs the tide."]
    sync_db.turns.insert_one({
        "id": str(uuid.uuid4()), "session_id": sid, "turn_number": 1, "player_action": None,
        "narrative": paragraphs[0], "canonical_narrative": paragraphs[0], "paragraphs": paragraphs,
        "choices": [{"label": c, "text": f"Seed {c}"} for c in "ABCD"],
        "state": {"Health": "stable"}, "ledger": {}, "rolling_state": rolling, "raw": "", "debug": {},
        "created_at": FIXED_NOW,
    })
    return sid


class Narrator:
    """Deterministic fixture. Scene moves and prose are scripted; consequences are not."""

    def __init__(self):
        self.seen = []
        self.scene_for_call = {}

    def __call__(self, n, kwargs):
        blob = json.dumps(kwargs["messages"], ensure_ascii=False, default=str)
        self.seen.append(blob)
        prose = SEARCH_PROSE if ce.DIRECTIVE_MARKER in blob else f"The talk settles (beat {n})."
        scene = self.scene_for_call.get(n)
        rolling = json.dumps({"scene": scene}) if scene else "{}"
        return (
            f"<rolling_state>{rolling}</rolling_state>\n<narrative>{prose}</narrative>\n"
            f"<choices>\nA. Wait, beat {n}\nB. Watch the quay, beat {n}\nC. Ask around, beat {n}\n"
            f"D. Walk the harbour, beat {n}\n</choices>\n"
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


def _act(client, sid, dev, expected, *, tell=None, text="Wait and watch", rid=None, aloud=False):
    body = {"session_id": sid, "action_text": text, "action_request_id": rid or f"a-{uuid.uuid4()}",
            "expected_turn_count": expected}
    if tell:
        body["disclosure"] = {"recipient": tell[0], "claim": tell[1], "aloud": aloud}
    return client.post("/api/story/action", json=body, headers=headers(dev))


def _play_until(client, sid, dev, start, last):
    """Ordinary turns from ``start`` (the current turn count) up to turn ``last``."""
    out = {}
    for n in range(start, last):
        r = _act(client, sid, dev, n)
        assert r.status_code == 200, r.text
        out[n + 1] = r.json()["turn"]
    return out


def _tell_both(client, env, narrator, dev, rolling):
    """Corin hears the mill version at the dock, Wren the chapel version at the inn."""
    sid = seed(env.sync_db, dev, rolling)
    narrator.scene_for_call = {1: "the inn"}  # after the first telling the player walks to the inn
    r1 = _act(client, sid, dev, 1, tell=("Corin Hale", MILL))
    assert r1.status_code == 200, r1.text
    r2 = _act(client, sid, dev, 2, tell=("Wren Alder", CHAPEL))
    assert r2.status_code == 200, r2.text
    return sid


def _belief_map(sync_db, sid):
    state = session_doc(sync_db, sid).get("claim_state") or {}
    claims = {c["id"]: c["text"] for c in state.get("claims", [])}
    out = {}
    for b in state.get("beliefs", []):
        out.setdefault(b["actor"]["name"], []).append((claims[b["claim_id"]], b["source"]))
    return out


def test_each_character_initially_knows_only_what_they_heard(client, env, narrator):
    dev = device()
    sid = _tell_both(client, env, narrator, dev, ferry_world())
    beliefs = _belief_map(env.sync_db, sid)
    assert beliefs == {"Corin Hale": [(MILL, "told")], "Wren Alder": [(CHAPEL, "told")]}
    doc = session_doc(env.sync_db, sid)
    assert doc["rolling_state"]["missing_passenger"] == TRUTH          # the engine never wrote the truth
    state = doc["claim_state"]
    assert [c["location"] for c in state["claims"]] == ["the mill", "the chapel"]
    assert [c["speaker"] for c in state["claims"]] == ["the player", "the player"]
    assert state["claims"][0]["witnesses"] == [] and state["claims"][1]["witnesses"] == []
    # Reload: the player sees only what they said, nothing about who believes it.
    shown = client.get(f"/api/story/session/{sid}", headers=headers(dev)).json()
    assert [(c["to"], c["text"]) for c in shown["session"]["claims_told"]] == [("Corin Hale", MILL), ("Wren Alder", CHAPEL)]
    blob = dump(shown)
    assert "beliefs" not in blob and "relays" not in blob and "witnesses" not in blob
    # The narrator was told what the person in the scene heard, as a claim and not a fact.
    assert ce.BELIEF_MARKER in narrator.seen[-1]
    section = narrator.seen[-1].split(ce.BELIEF_MARKER)[1].split('"}, {"role"')[0]   # just this message
    assert "Wren Alder was told" in section and CHAPEL in section
    assert "Corin Hale" not in section and MILL not in section            # he is at the dock, not here


def test_chapel_version_reaches_the_harbourmaster_and_guards_search_the_chapel(client, env, narrator):
    dev = device()
    sid = _tell_both(client, env, narrator, dev, ferry_world())
    turns = _play_until(client, sid, dev, 3, 8)
    # Wren told turn 3 hmm: claims were told on turns 2 and 3 (two tellings), so relay lands two turns later.
    text = {n: " ".join(t["paragraphs"]) for n, t in turns.items()}
    searching = [n for n, t in text.items() if "searching the chapel" in t]
    assert searching, text
    first = searching[0]
    assert all("searching" not in text[n] for n in text if n < first)
    state = session_doc(env.sync_db, sid)["claim_state"]
    beliefs = _belief_map(env.sync_db, sid)
    assert (CHAPEL, "relayed") in beliefs["Dov Marsh"]
    assert all(c[0] != MILL for c in beliefs["Dov Marsh"])             # the mill version never travelled
    assert [(a["actor"]["name"], a["location"]) for a in state["actions"]] == [("Dov Marsh", "the chapel")]
    assert state["actions"][0]["observed_turn"] == first
    # The player sees the clue but not the culprit or the chain.
    shown = dump(client.get(f"/api/story/session/{sid}", headers=headers(dev)).json())
    assert "Wren" not in text[first] and "innkeeper" not in text[first].lower()
    assert "relayed" not in shown and "Dov Marsh" not in dump(client.get(f"/api/story/session/{sid}", headers=headers(dev)).json()["session"])
    # It is told once: later turns are not told to show the same search again.
    assert all(ce.DIRECTIVE_MARKER not in blob for blob in narrator.seen[first:])


def test_no_onward_contact_means_nobody_learns_it(client, env, narrator):
    dev = device()
    sid = _tell_both(client, env, narrator, dev, ferry_world(innkeeper_contacts=()))
    turns = _play_until(client, sid, dev, 3, 10)
    assert all("searching" not in " ".join(t["paragraphs"]) for t in turns.values())
    state = session_doc(env.sync_db, sid)["claim_state"]
    assert set(_belief_map(env.sync_db, sid)) == {"Corin Hale", "Wren Alder"}
    assert state["relays"] == [] and state["actions"] == []


def test_a_real_overhearer_can_carry_it_instead_of_the_person_told(client, env, narrator):
    dev = device()
    world = ferry_world(innkeeper_contacts=(), potboy=True)
    sid = seed(env.sync_db, dev, world)
    narrator.scene_for_call = {1: "the inn"}
    assert _act(client, sid, dev, 1).status_code == 200                    # walk to the inn
    assert _act(client, sid, dev, 2, tell=("Wren Alder", CHAPEL)).status_code == 200
    state = session_doc(env.sync_db, sid)["claim_state"]
    assert [w["name"] for w in state["claims"][0]["witnesses"]] == ["Tam Pike"]
    turns = _play_until(client, sid, dev, 3, 8)
    assert any("searching the chapel" in " ".join(t["paragraphs"]) for t in turns.values())
    relays = [(r["from"]["name"], r["to"]["name"]) for r in session_doc(env.sync_db, sid)["claim_state"]["relays"]]
    assert relays == [("Tam Pike", "Dov Marsh")]                           # accusing Wren would be wrong
    beliefs = _belief_map(env.sync_db, sid)
    assert (CHAPEL, "overheard") in beliefs["Tam Pike"]


def test_retry_makes_one_disclosure_and_one_action(client, env, fake):
    dev = device()
    sid = seed(env.sync_db, dev, ferry_world())
    rid = "retry-me-1"
    first = _act(client, sid, dev, 1, tell=("Corin Hale", MILL), rid=rid)
    again = _act(client, sid, dev, 1, tell=("Corin Hale", MILL), rid=rid)
    assert first.status_code == 200 and again.status_code == 200
    assert first.json()["turn"]["turn_number"] == again.json()["turn"]["turn_number"] == 2
    doc = session_doc(env.sync_db, sid)
    assert doc["turn_count"] == 2 and len(doc["claim_state"]["claims"]) == 1
    assert fake.calls == 1                                                 # one narrator call, one action's cost
    assert len(turn_docs(env.sync_db, sid)) == 2


def test_telling_someone_who_is_not_here_is_refused_before_any_cost(client, env, fake):
    dev = device()
    sid = seed(env.sync_db, dev, ferry_world())
    r = _act(client, sid, dev, 1, tell=("Wren Alder", CHAPEL))             # she is at the inn
    assert r.status_code == 422
    r2 = _act(client, sid, dev, 1, tell=("Nobody Here", CHAPEL))
    assert r2.status_code == 422
    assert fake.calls == 0 and session_doc(env.sync_db, sid)["turn_count"] == 1
    assert "claim_state" not in session_doc(env.sync_db, sid)


def test_tick_is_idempotent_for_the_same_turn():
    world = ferry_world()
    world["scene"] = "the inn"
    state, _ = ce.record_disclosure(None, world, turn=2, request_id="r1", recipient_ref="Wren Alder", text=CHAPEL, speaker="the player")
    a, _ = ce.tick(state, world, 4)
    b, notes = ce.tick(a, world, 4)
    assert a == b and notes == []
    assert [r["status"] for r in a["relays"]] == ["delivered"]


def test_notebook_pin_of_the_clue_and_private_theory_stay_out_of_the_narrator(client, env, narrator):
    dev = device()
    sid = _tell_both(client, env, narrator, dev, ferry_world())
    turns = _play_until(client, sid, dev, 3, 8)
    clue_turn = next(n for n, t in turns.items() if "searching the chapel" in " ".join(t["paragraphs"]))
    idx = next(i for i, p in enumerate(turns[clue_turn]["paragraphs"]) if "searching the chapel" in p)
    pin = client.post(f"/api/story/session/{sid}/notebook/pins",
                      json={"turn_number": clue_turn, "paragraph_index": idx}, headers=headers(dev))
    assert pin.status_code == 200, pin.text
    pin_id = pin.json()["id"] if "id" in pin.json() else pin.json()["pin"]["id"]
    theory = client.post(f"/api/story/session/{sid}/notebook/theories",
                         json={"title": THEORY_PHRASE, "body": "someone talked", "pin_ids": [pin_id]}, headers=headers(dev))
    assert theory.status_code == 200, theory.text
    before = len(narrator.seen)
    assert _act(client, sid, dev, 8).status_code == 200
    assert len(narrator.seen) > before
    assert all(THEORY_PHRASE not in blob and "quince" not in blob for blob in narrator.seen)

