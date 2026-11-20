"""
The soft-meta narrative filter blocks talk about the game itself but allows
in-world engines (Qwen3.6 2026-11-21: "The engine sound is louder now" in a
vehicle scene was rejected twice and replaced by fallback text).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


@pytest.mark.parametrize(
    "text",
    [
        "The engine sound is louder now, closer.",
        "This engine has not turned over in years.",
        "You yank the cover off the generator and the engine coughs.",
    ],
)
def test_in_world_engines_are_allowed(text):
    assert not server._SOFT_META_PHRASE_RE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "The story engine is harder than the last.",
        "The game engine decides what happens next.",
        "The narrative engine resolves the moment.",
        "The system carries you forward.",
        "The simulation hums.",
    ],
)
def test_talk_about_the_game_is_still_blocked(text):
    assert server._SOFT_META_PHRASE_RE.search(text)
