"""
Consequence Echoes v1 — structured source events only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import consequence_echoes as echoes  # noqa: E402


def _state():
    return echoes.init_consequence_echoes()


def _source(event_id="evt-1", kind="pressure_threshold_crossed", echo_kind="pressure_escalation"):
    return {
        "source_kind": kind,
        "source_event_id": event_id,
        "echo_kind": echo_kind,
        "label": "test",
    }


def test_schedule_requires_source_event_id():
    state = _state()
    added = echoes.schedule_from_structured_events(state, [_source()], turn_number=2)
    assert len(added) == 1
    assert state["scheduled"][0]["source_event_id"] == "evt-1"


def test_schedule_rejects_unknown_source_kind():
    state = _state()
    added = echoes.schedule_from_structured_events(
        state, [{"source_kind": "player_text_guess", "source_event_id": "x"}], 1
    )
    assert added == []


def test_schedule_deduplicates_by_source_event_id():
    state = _state()
    evt = _source(event_id="evt-dup")
    echoes.schedule_from_structured_events(state, [evt], 1)
    echoes.schedule_from_structured_events(state, [evt], 2)
    assert len(state["scheduled"]) == 1


def test_one_canonical_source_creates_one_echo():
    state = _state()
    src = _source(event_id="evt-canonical")
    added1 = echoes.schedule_from_structured_events(state, [src], 1)
    added2 = echoes.schedule_from_structured_events(state, [src], 2, processed_source_ids=echoes.processed_source_event_ids(state))
    assert len(added1) == 1
    assert len(added2) == 0


def test_mature_moves_ready_entries_to_pending():
    state = _state()
    echoes.schedule_from_structured_events(
        state, [{**_source(), "mature_in": 1}], turn_number=1
    )
    matured = echoes.mature_echoes(state, turn_number=2)
    assert matured
    assert state["pending"]


def test_pending_echoes_keep_newest_bounded_window():
    state = _state()
    first_batch = [
        {**_source(event_id=f"old-{index}"), "mature_in": 1}
        for index in range(echoes.MAX_PENDING)
    ]
    echoes.schedule_from_structured_events(state, first_batch, turn_number=1)
    echoes.mature_echoes(state, turn_number=2)

    second_batch = [
        {**_source(event_id=f"new-{index}"), "mature_in": 1}
        for index in range(echoes.MAX_PENDING)
    ]
    echoes.schedule_from_structured_events(state, second_batch, turn_number=2)
    retained = echoes.mature_echoes(state, turn_number=3)

    assert len(state["pending"]) == echoes.MAX_PENDING
    assert len(retained) == echoes.MAX_PENDING
    assert all(row["source_event_id"].startswith("new-") for row in state["pending"])


def test_fire_at_most_one_per_turn():
    state = _state()
    echoes.schedule_from_structured_events(state, [_source(event_id="a")], 1)
    echoes.schedule_from_structured_events(state, [_source(event_id="b")], 1)
    echoes.mature_echoes(state, 2)
    echoes.fire_echo(state, 2)
    second, did = echoes.fire_echo(state, 2)
    assert not did
    assert second is None


def test_fired_echo_references_source_event_id():
    state = _state()
    echoes.schedule_from_structured_events(
        state, [{**_source(event_id="evt-fired"), "mature_in": 1}], 1
    )
    echoes.mature_echoes(state, 2)
    fired, did = echoes.fire_echo(state, 2)
    assert did
    assert fired["source_event_id"] == "evt-fired"


def test_echo_directive_only_when_fired():
    state = _state()
    echoes.schedule_from_structured_events(state, [{**_source(), "mature_in": 1}], 1)
    echoes.mature_echoes(state, 2)
    assert echoes.build_echo_directive(state) == ""
    fired, did = echoes.fire_echo(state, 2)
    assert did
    directive = echoes.build_echo_directive(state, fired_this_turn=fired)
    assert echoes.ECHO_DIRECTIVE_MARKER in directive


@pytest.mark.parametrize("kind", echoes.ECHO_KINDS)
def test_supported_echo_kinds_schedulable_with_valid_source(kind):
    state = _state()
    src = {
        "source_kind": "pressure_threshold_crossed",
        "source_event_id": f"evt-{kind}",
        "echo_kind": kind,
        "label": kind,
    }
    added = echoes.schedule_from_structured_events(state, [src], 1)
    assert len(added) == 1
