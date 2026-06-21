"""Arc Diversity Governor v1 — deterministic beat history tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import arc_diversity as arc  # noqa: E402
import replayability  # noqa: E402

SEED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _candidates():
    return [
        {"kind": "pressure", "subkind": "social", "urgency": 30, "directive": "pressure"},
        {"kind": "npc_move", "subkind": "gather", "urgency": 40, "directive": "move"},
    ]


def test_repeat_penalty_on_low_urgency():
    state = arc.init_arc_diversity()
    arc.record_beat(state, turn_number=1, kind="pressure", subkind="social", urgency=30)
    arc.record_beat(state, turn_number=2, kind="pressure", subkind="social", urgency=30)
    primary = arc.select_primary_beat(_candidates(), state, identity={})
    assert primary["kind"] == "npc_move"


def test_similar_beats_rotate_deterministically():
    state = arc.init_arc_diversity()
    cands = [
        {"kind": "npc_move", "subkind": "gather", "urgency": 50, "directive": "a"},
        {"kind": "npc_move", "subkind": "protect", "urgency": 50, "directive": "b"},
    ]
    p1 = arc.select_primary_beat(cands, state, identity={})
    arc.record_beat(state, turn_number=1, kind=p1["kind"], subkind=p1["subkind"], urgency=50)
    p2 = arc.select_primary_beat(cands, state, identity={})
    assert p1 != p2 or p1["subkind"] != p2["subkind"]


def test_critical_pressure_overrides_variety_penalty():
    state = arc.init_arc_diversity()
    for i in range(3):
        arc.record_beat(state, turn_number=i, kind="pressure", subkind="social", urgency=30)
    cands = [
        {"kind": "pressure", "subkind": "social", "urgency": 90, "directive": "urgent"},
        {"kind": "npc_move", "subkind": "gather", "urgency": 40, "directive": "move"},
    ]
    primary = arc.select_primary_beat(cands, state, identity={})
    assert primary["kind"] == "pressure"


def test_fired_echo_not_suppressed():
    state = arc.init_arc_diversity()
    arc.record_beat(state, turn_number=1, kind="echo", subkind="retaliation", urgency=85)
    cands = [
        {"kind": "echo", "subkind": "retaliation", "urgency": 85, "directive": "echo"},
        {"kind": "npc_move", "subkind": "gather", "urgency": 30, "directive": "move"},
    ]
    primary = arc.select_primary_beat(cands, state, identity={})
    assert primary["kind"] == "echo"


def test_severe_npc_move_remains_observable():
    state = arc.init_arc_diversity()
    arc.record_beat(state, turn_number=1, kind="npc_move", subkind="gather", urgency=40)
    cands = [
        {"kind": "npc_move", "subkind": "defect", "urgency": 75, "directive": "defect"},
        {"kind": "npc_move", "subkind": "gather", "urgency": 35, "directive": "gather"},
    ]
    primary = arc.select_primary_beat(cands, state, identity={})
    assert primary["subkind"] == "defect"


def test_beat_history_cap_enforced():
    state = arc.init_arc_diversity()
    for i in range(20):
        arc.record_beat(state, turn_number=i, kind="pressure", subkind="social", urgency=30)
    assert len(state["recent_beats"]) <= arc.MAX_RECENT_BEATS


def test_beat_history_contains_no_prose():
    state = arc.init_arc_diversity()
    arc.record_beat(state, turn_number=1, kind="npc_move", subkind="fortify", urgency=50)
    blob = str(state)
    assert "narrative" not in blob.lower()
    for beat in state["recent_beats"]:
        assert set(beat.keys()) <= {"turn", "kind", "subkind", "urgency"}


def test_primary_selection_is_deterministic():
    state = arc.init_arc_diversity()
    a = arc.select_primary_beat(_candidates(), state, identity={"echo_bias": "betrayals"})
    b = arc.select_primary_beat(_candidates(), state, identity={"echo_bias": "betrayals"})
    assert a == b


def test_model_output_cannot_alter_beat_history():
    rb, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=SEED,
    )
    auth = copy_arc = arc.copy_arc_state(rb["arc_diversity"])
    rolling = {
        "arc_diversity": {"recent_beats": [{"turn": 9, "kind": "fake", "subkind": "model"}]},
        "scene": "dock",
    }
    replayability.enforce_authoritative(rolling, rb)
    assert "arc_diversity" not in rolling
    assert rb["arc_diversity"] == auth