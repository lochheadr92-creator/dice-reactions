"""Feature 2: leave someone instructions for when I'm gone.

Real action handler, real persistence, real player responses. The narrator is a deterministic
fixture: it writes whatever the engine's result directive tells it, and moves the scene when the
test says so. It never decides that the ferry comes loose; the tests never insert that result.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import uuid
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import order_engine as oe  # noqa: E402
from reliability_support import FakeGateway, MongoEnv, insert_session, make_client, relax_rate_limits  # noqa: E402
from player_features_support import FIXED_NOW, device, dump, headers, session_doc, turn_docs  # noqa: E402

FERRY_ORDER = "If the water reaches the red mark, cut the ferry loose, even if I'm still across the river."
FERRY_ORDER_NO_AWAY = "If the water reaches the red mark, cut the ferry loose."
PARCEL_ORDER = "When Dov Marsh arrives, hand him the parcel."
DOCK, FAR, OFFICE = "the ferry dock", "the far bank", "the harbour office"


def world(*, rise=1, level=1, visible=(DOCK,), mara_inv=("fishing knife", "sealed parcel"), trust=60, dov_at=OFFICE):
    return {
        "scene": DOCK, "location": DOCK, "character": "steady",
        "known_rooms": [DOCK, FAR, OFFICE], "locations": [DOCK, FAR, OFFICE],
        "ferry_state": "moored",
        "gauges": {"river_water": {"label": "water", "mark_name": "red mark", "level": level, "mark": 3,
                                    "rise_per_turn": rise, "visible_from": list(visible)}},
        "npcs": [
            {"name": "Mara Voss", "npc_id": "npc-mara0000000", "role": "ferry hand", "last_seen": DOCK,
             "inventory": list(mara_inv), "stance": "ally"},
            {"name": "Dov Marsh", "npc_id": "npc-dov00000000", "role": "harbourmaster", "last_seen": dov_at,
             "inventory": []},
        ],
        "relationship_vectors": [{"name": "Mara Voss", "trust": trust}],
        "deceased": [],
    }


def seed(sync_db, dev, rolling):
    sid = insert_session(sync_db, dev, turn_count=1, rolling=rolling,
                         extra={"title": "Rising Water", "last_state": {"Health": "stable"}})
    para = "Mara Voss coils rope on the dock. Dov Marsh is a distant figure by the harbour office."
    sync_db.turns.insert_one({
        "id": str(uuid.uuid4()), "session_id": sid, "turn_number": 1, "player_action": None,
        "narrative": para, "canonical_narrative": para, "paragraphs": [para],
        "choices": [{"label": c, "text": f"Seed {c}"} for c in "ABCD"],
        "state": {"Health": "stable"}, "ledger": {}, "rolling_state": rolling, "raw": "", "debug": {},
        "created_at": FIXED_NOW,
    })
    return sid


class Narrator:
    """Scene moves are scripted per call number. Results come only from the engine's directive."""

    def __init__(self):
        self.seen = []
        self.rolling_for_call = {}

    def __call__(self, n, kwargs):
        text = "\n".join(str(m.get("content") or "") for m in kwargs["messages"])
        self.seen.append(text)
        m = re.search(re.escape(oe.DIRECTIVE_MARKER) + r"\n.*?\n((?:- .*\n?)+)", text)
        prose = ("What the player sees: " + " ".join(re.findall(r"- \([^)]*\) (.*)", m.group(1)))) if m else f"The river murmurs (beat {n})."
        rolling = json.dumps(self.rolling_for_call.get(n, {}))
        return (
            f"<rolling_state>{rolling}</rolling_state>\n<narrative>{prose}</narrative>\n"
            f"<choices>\nA. Wait, beat {n}\nB. Watch the water, beat {n}\nC. Check the rope, beat {n}\n"
            f"D. Walk the bank, beat {n}\n</choices>\n"
            "<state>\nHealth: stable\nPressure: steady\nPosition: here\n</state>\n<ledger>\nCarried: nothing\n</ledger>\n"
        )


@pytest.fixture()
def env(monkeypatch):
    mongo = MongoEnv()
    relax_rate_limits(monkeypatch)
    yield mongo
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


def _act(client, sid, dev, expected, *, order=None, text="Wait and watch", rid=None):
    body = {"session_id": sid, "action_text": text, "action_request_id": rid or f"a-{uuid.uuid4()}",
            "expected_turn_count": expected}
    if order:
        body["order"] = {"recipient": order[0], "text": order[1]}
    return client.post("/api/story/action", json=body, headers=headers(dev))


def _preview(client, sid, dev, who, text):
    return client.post(f"/api/story/session/{sid}/orders/preview", json={"recipient": who, "text": text}, headers=headers(dev))


def _play(client, sid, dev, start, last):
    out = {}
    for n in range(start, last):
        r = _act(client, sid, dev, n)
        assert r.status_code == 200, r.text
        out[n + 1] = r.json()["turn"]
    return out


def _doc(env, sid):
    return session_doc(env.sync_db, sid)


def _shown(client, sid, dev):
    return client.get(f"/api/story/session/{sid}", headers=headers(dev)).json()["session"]


def test_preview_shows_what_she_understood_and_costs_nothing(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world())
    before = _doc(env, sid)
    r = _preview(client, sid, dev, "Mara Voss", FERRY_ORDER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["can_commit"] is True and body["issues"] == []
    assert body["understood"] == {"condition": "the water reaches the red mark", "action": "cut the ferry loose", "even_if_away": True}
    joined = " ".join(body["notes"])
    assert "fishing knife" in joined and "can see the red mark" in joined and "willing" in joined
    assert _doc(env, sid) == before and narrator.seen == [] and len(turn_docs(env.sync_db, sid)) == 1


def test_preview_flags_what_she_cannot_do_and_lets_the_player_revise(client, env):
    dev = device()
    sid = seed(env.sync_db, dev, world())
    vague = _preview(client, sid, dev, "Mara Voss", "If the water gets high, cut the ferry loose.").json()
    assert vague["can_commit"] is False and "red mark" in " ".join(vague["issues"])
    odd = _preview(client, sid, dev, "Mara Voss", "If it rains, burn the dock.").json()
    assert odd["can_commit"] is False and odd["understood"] is None and odd["issues"]
    nobody = _preview(client, sid, dev, "Mara Voss", "When Zed arrives, hand him the parcel.").json()
    assert nobody["can_commit"] is False and "Zed" in " ".join(nobody["issues"])
    no_away = _preview(client, sid, dev, "Mara Voss", FERRY_ORDER_NO_AWAY).json()
    assert no_away["can_commit"] is True and "even if I'm away" in " ".join(no_away["notes"])
    weak = world(mara_inv=(), trust=10)
    sid2 = seed(env.sync_db, dev, weak)
    notes = " ".join(_preview(client, sid2, dev, "Mara Voss", FERRY_ORDER).json()["notes"])
    assert "not carrying anything she could cut with" in notes and "reluctant" in notes
    absent = _preview(client, sid, dev, "Dov Marsh", PARCEL_ORDER)
    assert absent.status_code == 422


def test_ferry_comes_loose_once_and_returning_shows_the_changed_world(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world())
    narrator.rolling_for_call = {1: {"scene": FAR, "location": FAR}}       # the player crosses the river
    r = _act(client, sid, dev, 1, order=("Mara Voss", FERRY_ORDER))
    assert r.status_code == 200, r.text
    assert _doc(env, sid)["rolling_state"]["ferry_state"] == "moored"
    assert _shown(client, sid, dev)["orders_given"][0]["understood"] == "When the water reaches the red mark, cut the ferry loose."
    _play(client, sid, dev, 2, 5)                                          # the water keeps rising while they are away
    doc = _doc(env, sid)
    order = doc["order_state"]["orders"][0]
    assert order["status"] == "done" and doc["rolling_state"]["ferry_state"] == "adrift"
    fired = order["fired_turn"]
    assert not any("cut the ferry loose with" in s and "What the player sees" in s for s in narrator.seen[:3])
    shown = _shown(client, sid, dev)["orders_given"][0]
    assert "result" not in shown                                           # nobody has seen it yet
    assert "pending" not in dump(shown) and "done" not in dump(shown)
    narrator.rolling_for_call = {5: {"scene": DOCK, "location": DOCK}}     # they come back on turn 6
    _play(client, sid, dev, 5, 8)
    final = _shown(client, sid, dev)["orders_given"][0]
    assert final["result"] == "Mara Voss cut the ferry loose with fishing knife. The ferry is now adrift."
    prose = " ".join(t["narrative"] for t in turn_docs(env.sync_db, sid))
    assert "cut the ferry loose with fishing knife" in prose and prose.count("cut the ferry loose with fishing knife") == 1
    _play(client, sid, dev, 8, 11)                                         # nothing fires twice
    after = _doc(env, sid)
    assert [o["status"] for o in after["order_state"]["orders"]] == ["done"] and after["order_state"]["orders"][0]["fired_turn"] == fired
    assert after["rolling_state"]["ferry_state"] == "adrift"


def test_replaying_the_firing_turn_does_not_run_it_again(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(level=2))
    assert _act(client, sid, dev, 1, order=("Mara Voss", FERRY_ORDER)).status_code == 200   # level 3 this turn: fires
    assert _doc(env, sid)["order_state"]["orders"][0]["status"] == "done"
    calls = len(narrator.seen)
    rid = f"fire-{uuid.uuid4()}"
    first = _act(client, sid, dev, 2, rid=rid)
    again = _act(client, sid, dev, 2, rid=rid)
    assert first.status_code == 200 and again.status_code == 200
    assert again.json().get("replayed") is True and len(narrator.seen) == calls + 1
    assert _doc(env, sid)["order_state"]["orders"][0]["status"] == "done" and _doc(env, sid)["turn_count"] == 3


@pytest.mark.parametrize("label, kwargs, status, ferry", [
    ("never reaches the mark", dict(rise=0), "pending", "moored"),
    ("she cannot see it", dict(visible=(FAR,)), "pending", "moored"),
    ("she refuses", dict(trust=10), "refused", "moored"),
    ("she has no tool", dict(mara_inv=("sealed parcel",)), "no_means", "moored"),
])
def test_alternatives_leave_the_ferry_alone(client, env, narrator, label, kwargs, status, ferry):
    dev = device()
    sid = seed(env.sync_db, dev, world(**kwargs))
    assert _act(client, sid, dev, 1, order=("Mara Voss", FERRY_ORDER)).status_code == 200
    _play(client, sid, dev, 2, 7)
    doc = _doc(env, sid)
    assert doc["order_state"]["orders"][0]["status"] == status, label
    assert doc["rolling_state"]["ferry_state"] == ferry, label
    prose = " ".join(t["narrative"] for t in turn_docs(env.sync_db, sid))
    assert "cut the ferry loose with" not in prose
    if status in ("refused", "no_means"):                                    # the player was there: they see her choice
        assert "What the player sees" in prose and ("chose not to" in prose or "had nothing to do it with" in prose)
        assert "result" in _shown(client, sid, dev)["orders_given"][0]
    else:
        assert "result" not in _shown(client, sid, dev)["orders_given"][0]


def test_without_even_if_she_waits_for_the_player(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(level=1))
    narrator.rolling_for_call = {1: {"scene": FAR, "location": FAR}, 5: {"scene": DOCK, "location": DOCK}}
    assert _act(client, sid, dev, 1, order=("Mara Voss", FERRY_ORDER_NO_AWAY)).status_code == 200
    _play(client, sid, dev, 2, 5)
    assert _doc(env, sid)["order_state"]["orders"][0]["status"] == "pending"      # water is high, player is away
    assert _doc(env, sid)["rolling_state"]["ferry_state"] == "moored"
    _play(client, sid, dev, 5, 8)
    assert _doc(env, sid)["order_state"]["orders"][0]["status"] == "done"          # back at the dock: she acts


def test_same_mechanism_delivers_a_parcel_when_a_person_arrives(client, env, narrator):
    dev = device()
    rolling = world(rise=0)
    sid = seed(env.sync_db, dev, rolling)
    arrived = copy.deepcopy(rolling["npcs"])
    arrived[1]["last_seen"] = DOCK
    narrator.rolling_for_call = {3: {"npcs": arrived}}
    assert _act(client, sid, dev, 1, order=("Mara Voss", PARCEL_ORDER)).status_code == 200
    _play(client, sid, dev, 2, 6)
    doc = _doc(env, sid)
    npcs = {n["name"]: n for n in doc["rolling_state"]["npcs"]}
    assert doc["order_state"]["orders"][0]["status"] == "done"
    assert "sealed parcel" in npcs["Dov Marsh"]["inventory"] and "sealed parcel" not in npcs["Mara Voss"]["inventory"]
    assert "fishing knife" in npcs["Mara Voss"]["inventory"]
    prose = " ".join(t["narrative"] for t in turn_docs(env.sync_db, sid))
    assert prose.count("handed the parcel to Dov Marsh") == 1


def test_retry_and_unsupported_orders_cost_nothing(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world())
    rid = f"o-{uuid.uuid4()}"
    r1 = _act(client, sid, dev, 1, order=("Mara Voss", FERRY_ORDER), rid=rid)
    r2 = _act(client, sid, dev, 1, order=("Mara Voss", FERRY_ORDER), rid=rid)
    assert r1.status_code == 200 and r2.status_code == 200 and r2.json().get("replayed") is True
    doc = _doc(env, sid)
    assert len(doc["order_state"]["orders"]) == 1 and doc["turn_count"] == 2 and len(narrator.seen) == 1
    bad = _act(client, sid, dev, 2, order=("Mara Voss", "If it rains, burn the dock."))
    assert bad.status_code == 422 and len(narrator.seen) == 1 and _doc(env, sid)["turn_count"] == 2
    away = _act(client, sid, dev, 2, order=("Dov Marsh", PARCEL_ORDER))
    assert away.status_code == 422 and len(narrator.seen) == 1


def test_narrator_hears_a_waiting_order_only_for_someone_in_the_scene(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(rise=0))
    narrator.rolling_for_call = {1: {"scene": FAR, "location": FAR}}
    assert _act(client, sid, dev, 1, order=("Mara Voss", FERRY_ORDER)).status_code == 200
    _play(client, sid, dev, 2, 4)
    assert oe.CONTEXT_MARKER not in narrator.seen[1] and oe.CONTEXT_MARKER not in narrator.seen[2]   # player is away
    narrator.rolling_for_call = {4: {"scene": DOCK, "location": DOCK}}
    _play(client, sid, dev, 4, 6)
    assert oe.CONTEXT_MARKER in narrator.seen[-1] and "She is waiting for that and has not acted yet" in narrator.seen[-1]
    payload = dump(client.get(f"/api/story/session/{sid}", headers=headers(dev)).json())
    for hidden in ("order_state", "gauges", "visible_from", "last_tick_turn", "fired_turn", "trust"):
        assert hidden not in payload
