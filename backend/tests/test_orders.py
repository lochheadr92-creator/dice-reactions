"""Feature 2: leave someone instructions for when I'm gone.

Real action handler, real persistence, real player responses. The narrator is a deterministic
fixture: it writes whatever the engine's result directive tells it, and moves the scene when the
test says so. It never decides that something changes hands; the tests never insert that result.
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

MARK_ORDER = "If the water reaches the red mark, hand the parcel to Dov Marsh."
PARCEL_ORDER = "When Dov Marsh arrives, hand him the parcel."
DOCK, FAR, OFFICE = "the ferry dock", "the far bank", "the harbour office"


def world(*, rise=1, level=1, visible=(DOCK,), mara_inv=("fishing knife", "sealed parcel"), trust=60, dov_at=OFFICE):
    return {
        "scene": DOCK, "location": DOCK, "character": "steady",
        "known_rooms": [DOCK, FAR, OFFICE], "locations": [DOCK, FAR, OFFICE],
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
    sid = seed(env.sync_db, dev, world(dov_at=DOCK))
    before = _doc(env, sid)
    r = _preview(client, sid, dev, "Mara Voss", MARK_ORDER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["can_commit"] is True and body["issues"] == []
    assert body["understood"] == {"condition": "the water reaches the red mark", "action": "hand the parcel to Dov Marsh"}
    joined = " ".join(body["notes"])
    assert "can see the red mark" in joined and "willing" in joined
    assert "sealed parcel" not in joined and "fishing knife" not in joined      # a preview shows nothing she carries
    assert _doc(env, sid) == before and narrator.seen == [] and len(turn_docs(env.sync_db, sid)) == 1


def test_preview_flags_what_she_cannot_do_and_lets_the_player_revise(client, env):
    dev = device()
    sid = seed(env.sync_db, dev, world())
    vague = _preview(client, sid, dev, "Mara Voss", "If the water gets high, hand the parcel to Dov Marsh.").json()
    assert vague["can_commit"] is False and "red mark" in " ".join(vague["issues"])
    odd = _preview(client, sid, dev, "Mara Voss", "If it rains, burn the dock.").json()
    assert odd["can_commit"] is False and odd["understood"] is None and odd["issues"]
    gone = _preview(client, sid, dev, "Mara Voss", "If the water reaches the red mark, cut the ferry loose.").json()
    assert gone["can_commit"] is False and gone["understood"] is None          # that action no longer exists
    nobody = _preview(client, sid, dev, "Mara Voss", "When Zed arrives, hand him the parcel.").json()
    assert nobody["can_commit"] is False and "Zed" in " ".join(nobody["issues"])
    weak = world(mara_inv=(), trust=10)
    sid2 = seed(env.sync_db, dev, weak)
    notes = " ".join(_preview(client, sid2, dev, "Mara Voss", MARK_ORDER).json()["notes"])
    assert "reluctant" in notes and "not carrying" not in notes
    absent = _preview(client, sid, dev, "Dov Marsh", PARCEL_ORDER)
    assert absent.status_code == 422


def _inventories(doc):
    return {n["name"]: n.get("inventory") or [] for n in doc["rolling_state"]["npcs"]}


def test_an_order_fires_once_while_the_player_is_away_and_returning_shows_the_changed_world(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(dov_at=DOCK))
    narrator.rolling_for_call = {1: {"scene": FAR, "location": FAR}}       # the player crosses the river
    r = _act(client, sid, dev, 1, order=("Mara Voss", MARK_ORDER))
    assert r.status_code == 200, r.text
    assert "sealed parcel" in _inventories(_doc(env, sid))["Mara Voss"]
    assert _shown(client, sid, dev)["orders_given"][0]["understood"] == "When the water reaches the red mark, hand the parcel to Dov Marsh."
    _play(client, sid, dev, 2, 5)                                          # the water keeps rising while they are away
    doc = _doc(env, sid)
    order = doc["order_state"]["orders"][0]
    assert order["status"] == "done"
    assert "sealed parcel" in _inventories(doc)["Dov Marsh"] and "sealed parcel" not in _inventories(doc)["Mara Voss"]
    assert "fishing knife" in _inventories(doc)["Mara Voss"]                # only the named item moved
    fired = order["fired_turn"]
    assert not any("handed the parcel to" in s and "What the player sees" in s for s in narrator.seen[:3])
    shown = _shown(client, sid, dev)["orders_given"][0]
    assert "result" not in shown                                           # nobody has seen it yet
    assert "pending" not in dump(shown) and "done" not in dump(shown)
    narrator.rolling_for_call = {5: {"scene": DOCK, "location": DOCK}}     # they come back on turn 6
    _play(client, sid, dev, 5, 8)
    final = _shown(client, sid, dev)["orders_given"][0]
    assert final["result"] == "Mara Voss handed the parcel to Dov Marsh."
    prose = " ".join(t["narrative"] for t in turn_docs(env.sync_db, sid))
    assert prose.count("handed the parcel to Dov Marsh") == 1
    _play(client, sid, dev, 8, 11)                                         # nothing fires twice
    after = _doc(env, sid)
    assert [o["status"] for o in after["order_state"]["orders"]] == ["done"] and after["order_state"]["orders"][0]["fired_turn"] == fired
    assert _inventories(after)["Dov Marsh"].count("sealed parcel") == 1


def test_replaying_the_firing_turn_does_not_run_it_again(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(level=2, dov_at=DOCK))
    assert _act(client, sid, dev, 1, order=("Mara Voss", MARK_ORDER)).status_code == 200   # level 3 this turn: fires
    assert _doc(env, sid)["order_state"]["orders"][0]["status"] == "done"
    calls = len(narrator.seen)
    rid = f"fire-{uuid.uuid4()}"
    first = _act(client, sid, dev, 2, rid=rid)
    again = _act(client, sid, dev, 2, rid=rid)
    assert first.status_code == 200 and again.status_code == 200
    assert again.json().get("replayed") is True and len(narrator.seen) == calls + 1
    assert _doc(env, sid)["order_state"]["orders"][0]["status"] == "done" and _doc(env, sid)["turn_count"] == 3


@pytest.mark.parametrize("label, kwargs, status", [
    ("never reaches the mark", dict(rise=0, dov_at=DOCK), "pending"),
    ("she cannot see it", dict(visible=(FAR,), dov_at=DOCK), "pending"),
    ("he is somewhere else", dict(dov_at=OFFICE), "pending"),
    ("she refuses", dict(trust=10, dov_at=DOCK), "refused"),
    ("she does not have it", dict(mara_inv=("fishing knife",), dov_at=DOCK), "no_means"),
])
def test_alternatives_leave_everything_where_it_was(client, env, narrator, label, kwargs, status):
    dev = device()
    start = world(**kwargs)
    sid = seed(env.sync_db, dev, start)
    assert _act(client, sid, dev, 1, order=("Mara Voss", MARK_ORDER)).status_code == 200
    _play(client, sid, dev, 2, 7)
    doc = _doc(env, sid)
    assert doc["order_state"]["orders"][0]["status"] == status, label
    assert _inventories(doc)["Dov Marsh"] == [], label
    assert _inventories(doc)["Mara Voss"] == start["npcs"][0]["inventory"], label
    prose = " ".join(t["narrative"] for t in turn_docs(env.sync_db, sid))
    assert "handed the parcel to" not in prose
    if status in ("refused", "no_means"):                                    # the player was there: they see her choice
        assert "What the player sees" in prose and ("chose not to" in prose or "had nothing to do it with" in prose)
        assert "result" in _shown(client, sid, dev)["orders_given"][0]
    else:
        assert "result" not in _shown(client, sid, dev)["orders_given"][0]


def test_a_handover_waits_until_the_two_are_in_the_same_place(client, env, narrator):
    dev = device()
    rolling = world(level=2)                                                # the mark is reached at once, Dov is at the office
    sid = seed(env.sync_db, dev, rolling)
    assert _act(client, sid, dev, 1, order=("Mara Voss", MARK_ORDER)).status_code == 200
    _play(client, sid, dev, 2, 4)
    waiting = _doc(env, sid)
    assert waiting["order_state"]["orders"][0]["status"] == "pending" and _inventories(waiting)["Dov Marsh"] == []
    arrived = copy.deepcopy(rolling["npcs"])
    arrived[1]["last_seen"] = DOCK
    narrator.rolling_for_call = {4: {"npcs": arrived}}                     # he walks down to the dock
    _play(client, sid, dev, 4, 7)
    done = _doc(env, sid)
    assert done["order_state"]["orders"][0]["status"] == "done" and "sealed parcel" in _inventories(done)["Dov Marsh"]


def test_an_order_saved_for_the_removed_ferry_action_ends_quietly(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(level=2))
    assert _act(client, sid, dev, 1, order=("Mara Voss", PARCEL_ORDER)).status_code == 200
    env.sync_db.sessions.update_one({"id": sid}, {"$set": {
        "order_state.orders.0.action": {"kind": "cut_ferry_loose", "summary": "cut the ferry loose"},
        "order_state.orders.0.condition": {"kind": "gauge_reaches", "gauge": "river_water", "summary": "the water reaches the red mark"},
        "order_state.orders.0.status": "pending"}})
    _play(client, sid, dev, 2, 5)
    doc = _doc(env, sid)
    assert doc["order_state"]["orders"][0]["status"] == "void"
    assert _inventories(doc)["Mara Voss"] == ["fishing knife", "sealed parcel"]
    assert "result" not in _shown(client, sid, dev)["orders_given"][0]


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
    r1 = _act(client, sid, dev, 1, order=("Mara Voss", MARK_ORDER), rid=rid)
    r2 = _act(client, sid, dev, 1, order=("Mara Voss", MARK_ORDER), rid=rid)
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
    assert _act(client, sid, dev, 1, order=("Mara Voss", MARK_ORDER)).status_code == 200
    _play(client, sid, dev, 2, 4)
    assert oe.CONTEXT_MARKER not in narrator.seen[1] and oe.CONTEXT_MARKER not in narrator.seen[2]   # player is away
    narrator.rolling_for_call = {4: {"scene": DOCK, "location": DOCK}}
    _play(client, sid, dev, 4, 6)
    assert oe.CONTEXT_MARKER in narrator.seen[-1] and "She is waiting for that and has not acted yet" in narrator.seen[-1]
    payload = dump(client.get(f"/api/story/session/{sid}", headers=headers(dev)).json())
    for hidden in ("order_state", "gauges", "visible_from", "last_tick_turn", "fired_turn", "trust"):
        assert hidden not in payload
