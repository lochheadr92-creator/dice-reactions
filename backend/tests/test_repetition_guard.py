"""Repetition guard (regression: Qwen3.6 2026-11-21 repeated ending + choices)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import repetition_guard as rg  # noqa: E402
import server  # noqa: E402

_END = (
    "You are left kneeling in the mud, your rifle still in your hands, your arm "
    "throbbing. The gate is open, but you cannot move. Miller's rifle is still "
    "pointing at you, and you do not know what he will do next."
)
_CHOICES = [
    {"label": "A", "text": "Stay down, hands raised, to avoid being shot."},
    {"label": "B", "text": "Try to explain yourself to the guard."},
    {"label": "C", "text": "Sprint for the nearest building."},
    {"label": "D", "text": "Check your wound and the rifle."},
]
_NEW_CHOICES = [
    {"label": "A", "text": "Answer the medic's questions."},
    {"label": "B", "text": "Ask about the body Miller mentioned."},
    {"label": "C", "text": "Hand over the rifle."},
    {"label": "D", "text": "Refuse to move until Miller lowers his gun."},
]


def _prev():
    return rg.turn_fingerprint(["You check the wound; it is deep. " + _END], _CHOICES)


def test_same_ending_is_rejected():
    reason = rg.repetition_reason(_prev(), ["You wave at the patrol vehicle. " + _END], _NEW_CHOICES)
    assert "ends with the same passage" in reason


def test_same_opening_is_rejected():
    start = "You stay where you are, your hands still raised, the rifle heavy in your grip. " * 3
    prev = rg.turn_fingerprint([start + "Miller walks off."], _CHOICES)
    reason = rg.repetition_reason(prev, [start + "A medic runs toward you through the rain, shouting."], _NEW_CHOICES)
    assert "opens with the same passage" in reason


def test_same_choices_are_rejected_even_with_new_prose():
    fresh = ["A medic jogs out of the dark with a canvas bag and kneels beside you, already reaching for your arm."]
    reworded = [dict(c, text=c["text"].upper()) for c in _CHOICES]
    assert "choices repeat" in rg.repetition_reason(_prev(), fresh, reworded)


def test_new_turn_passes_and_one_carried_choice_is_fine():
    fresh = ["A medic jogs out of the dark with a canvas bag and kneels beside you, already reaching for your arm."]
    assert rg.repetition_reason(_prev(), fresh, _NEW_CHOICES) == ""
    assert rg.repetition_reason(_prev(), fresh, _NEW_CHOICES[:3] + _CHOICES[:1]) == ""


def test_no_previous_fingerprint_passes():
    assert rg.repetition_reason(None, [_END], _CHOICES) == ""


def test_full_validate_reports_repetition_kind():
    raw = (
        '<rolling_state>{"scene": "gate"}</rolling_state>'
        f"<narrative>You wave at the patrol vehicle. {_END}</narrative>"
        "<choices>\nA. Answer the medic.\nB. Ask about the body.\nC. Hand over the rifle.\nD. Refuse to move.\n</choices>"
        "<state>\nHealth: hurt\n</state><ledger>\nCarried: rifle\n</ledger>"
    )
    parsed = server.parse_turn(raw)
    session = {"turn_count": 5, "last_turn_fingerprint": _prev()}
    ok, reason, kind = server._full_validate(parsed, session, "wave at the vehicle")
    assert (ok, kind) == (False, "repetition"), reason
    session.pop("last_turn_fingerprint")
    _ok, _reason, kind2 = server._full_validate(parsed, session, "wave at the vehicle")
    assert kind2 != "repetition"
