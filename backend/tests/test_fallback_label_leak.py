"""Hidden-mechanics rule: fallback text never shows internal pressure labels.

rolling_state.active_pressures is an engine projection of the pressure graph
(ADR-023). Its labels ("trust duty", "information debt", "ammo social") are
internal names. The fail-forward turn used to copy the first one into the
narrative and a choice (eval baseline 2026-11-21: 14 of 16 fallback turns).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "dice_reactions_test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402

INTERNAL_LABELS = ["trust duty", "information debt", "ammo social", "trust trust"]


def _session(last_state, active_pressures):
    return {
        "id": "s1",
        "role": "Wandering scout",
        "turn_count": 5,
        "last_state": last_state,
        "rolling_state": {
            "scene": "frozen ridge",
            "character": "cold, tired",
            "active_pressures": active_pressures,
            "npcs": [{"name": "Mira", "alive": True}],
            "inventory_objects": [{"object": "iron staff"}],
        },
        "replayability_state": {
            "pressure_graph": {
                "nodes": [
                    {"id": "n1", "label": label, "origin_type": "opening_state", "status": "active"}
                    for label in INTERNAL_LABELS
                ]
            }
        },
    }


def _player_text(parsed) -> str:
    parts = [parsed.narrative]
    parts += [c["text"] for c in parsed.choices]
    parts += [str(v) for v in (parsed.state or {}).values()]
    parts += [str(v) for v in (parsed.ledger or {}).values()]
    return "\n".join(parts).casefold()


def _fallback(session):
    parsed, _raw, _receipt = server._build_fail_forward_parsed_turn(
        session,
        "I look around.",
        first_kind="format",
        first_reason="missing required choice labels: A,B,C,D",
        second_kind="format",
        second_reason="missing required choice labels: A,B,C,D",
    )
    return parsed


@pytest.mark.parametrize(
    "active_pressures",
    [
        ["trust duty"],
        ["information debt", "ammo social"],
        [{"id": "ammo social", "label": "trust trust"}],
        [{"id": "information debt"}],
    ],
)
@pytest.mark.parametrize(
    "last_state",
    [
        {"Health": "stable", "Pressure": "Firewood dwindling", "Position": "ridge"},
        {"Health": "stable", "Position": "ridge"},
        {},
    ],
)
def test_fallback_text_never_contains_internal_pressure_labels(active_pressures, last_state):
    text = _player_text(_fallback(_session(last_state, active_pressures)))
    for label in INTERNAL_LABELS:
        assert label not in text, f"internal label {label!r} reached the player"


def test_fallback_uses_the_last_shown_pressure_line():
    parsed = _fallback(_session({"Pressure": "[Firewood dwindling]"}, ["trust duty"]))
    assert "What presses on you has not changed either: Firewood dwindling." in parsed.narrative
    assert "[" not in parsed.narrative
    # Fallback choices no longer carry pressure text (review 2, finding 2).
    assert not any("Firewood" in c["text"] or "[" in c["text"] for c in parsed.choices)


def test_fallback_without_a_pressure_line_uses_generic_wording():
    parsed = _fallback(_session({}, ["trust duty"]))
    assert "Nothing is settled yet." in parsed.narrative
    assert "What presses on you" not in parsed.narrative
    assert any(c["text"] == "Listen to the people around you before you move" for c in parsed.choices)
    assert "Pressure" not in (parsed.state or {})
