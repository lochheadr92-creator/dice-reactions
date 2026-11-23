"""Engine decisions enter the relationship system as structured events, through its one mutation path."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import bargain_engine  # noqa: E402
import play_moves  # noqa: E402
import relationship_provenance as rp  # noqa: E402
import relationships  # noqa: E402


def _rolling(trust=20):
    return {"npcs": [{"name": "Maren"}, {"name": "Dax"}],
            "relationship_vectors": [{"name": "Maren", "trust": trust, "loyalty": 10, "fear": 0, "resentment": 30}]}


def _maren(rolling):
    return next(v for v in rolling["relationship_vectors"] if v["name"] == "Maren")


def test_an_engine_event_takes_its_value_from_the_canonical_table():
    ev = rp.engine_event("keep_promise", "Maren", source_kind="bargain", source_id="b-1", turn=7)
    assert ev["deltas"] == relationships.EVENT_DELTAS["keep_promise"] and ev["source_kind"] == "bargain"
    assert ev["event_id"] == rp.engine_event("keep_promise", "Maren", source_kind="bargain", source_id="b-1", turn=9)["event_id"]
    assert ev["event_id"] != rp.engine_event("keep_promise", "Maren", source_kind="bargain", source_id="b-2", turn=7)["event_id"]
    with pytest.raises(ValueError):
        rp.engine_event("made_up_kind", "Maren", source_kind="bargain", source_id="b-1", turn=7)
    with pytest.raises(ValueError):
        rp.engine_event("keep_promise", "  ", source_kind="bargain", source_id="b-1", turn=7)


def test_an_engine_event_moves_the_vector_once_and_records_where_it_came_from():
    prior, merged, sink = _rolling(), _rolling(), []
    ev = rp.engine_event("keep_promise", "Maren", source_kind="bargain", source_id="b-1", turn=4)
    rp.update_from_player_action(prior, merged, "You settle terms with Maren.", 4, provenance_sink=sink, engine_events=[ev, dict(ev)])
    m = _maren(merged)
    assert (m["trust"], m["loyalty"], m["resentment"]) == (30, 15, 25)
    applied = [p for p in sink if not p.get("rejected")]
    assert len(applied) == 1 and applied[0]["source_kind"] == "bargain" and applied[0]["kind"] == "keep_promise"


def test_the_engine_decision_stands_over_the_same_event_read_from_the_sentence():
    # "save" in the sentence resolves to save_life toward Maren. The engine also decided save_life.
    prior, merged, sink = _rolling(), _rolling(), []
    ev = rp.engine_event("save_life", "Maren", source_kind="test_engine", source_id="x-1", turn=4)
    rp.update_from_player_action(prior, merged, "You save Maren from the fire.", 4, provenance_sink=sink, engine_events=[ev])
    applied = [p for p in sink if not p.get("rejected")]
    assert [p["source_kind"] for p in applied] == ["test_engine"]
    assert _maren(merged)["trust"] == 20 + relationships.EVENT_DELTAS["save_life"]["trust"]


def test_without_engine_events_the_relationship_update_is_unchanged():
    a, b = _rolling(), _rolling()
    relationships.update_relationship_calculus(None, _rolling(), a, "You save Maren from the fire.", 4)
    relationships.update_relationship_calculus(None, _rolling(), b, "You save Maren from the fire.", 4, engine_events=None)
    assert a == b and _maren(a)["trust"] == 20 + relationships.EVENT_DELTAS["save_life"]["trust"]


def test_only_a_settled_bargain_raises_a_kept_promise_and_a_replay_raises_nothing():
    result = {"kind": "bargain", "status": "settled", "replayed": False,
              "relationship_events": [{"kind": "keep_promise", "target_name": "Maren", "source_kind": "bargain", "source_id": "b-1"}]}
    events = play_moves.relationship_events(result, 5)
    assert [(e["kind"], e["target_name"], e["source_kind"]) for e in events] == [("keep_promise", "Maren", "bargain")]
    assert play_moves.relationship_events({**result, "replayed": True}, 5) == []
    assert play_moves.relationship_events({"kind": "bargain", "status": "accepted", "replayed": False}, 5) == []
    assert play_moves.relationship_events(None, 5) == []
    rec = {"id": "b-1", "with": {"name": "Maren"}, "terms": {"give": [], "get": [], "service": "", "pledge": [], "settle": []},
           "status": "accepted", "reason": "agrees", "counter": None}
    assert "relationship_events" not in bargain_engine._result(rec, replay=False)
