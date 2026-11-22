"""Turn 1 must always tell the model to orient the player in plain words.

Regression: an opening left out who the player was, why they were there and
what they needed, because the request buried that ask under "in medias res"
and "preserve mystery" instructions.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import opening_state  # noqa: E402
import server  # noqa: E402


def _prompt(dev_mode: bool = False) -> str:
    return server._build_opening_prompt(
        "Genre: Dinosaur Island Survival\nCharacter role: traveller",
        debug_marker="[DEV_MODE: ON]" if dev_mode else "[DEV_MODE: OFF]",
        difficulty_marker="[DIFFICULTY: standard]",
        mode_marker="[MODE: advanced]",
        dev_mode=dev_mode,
    )


@pytest.mark.parametrize("dev_mode", [False, True])
def test_orientation_rule_is_always_the_last_thing_in_the_opening_request(dev_mode):
    assert _prompt(dev_mode).endswith(opening_state.OPENING_ORIENTATION_RULE)


def test_orientation_rule_names_the_four_facts_and_overrides_withholding():
    rule = opening_state.OPENING_ORIENTATION_RULE
    for fact in (
        "who the player character is",
        "where they are",
        "why they are there",
        "what they need right now",
    ):
        assert fact in rule
    assert "end of the first paragraph" in rule
    assert "this wins" in rule
    assert "everyday words" in rule.lower()


def test_orientation_rule_asks_for_natural_prose_not_a_list():
    rule = opening_state.OPENING_ORIENTATION_RULE
    assert "Do not list them" in rule
    assert "in the story's own voice" in rule
    assert "first three sentences" not in rule


def test_opening_request_keeps_setup_and_block_order_instruction():
    prompt = _prompt()
    assert "Genre: Dinosaur Island Survival" in prompt
    assert "Emit <rolling_state> first" in prompt
    assert ", <debug>" not in prompt
    assert ", <debug>" in _prompt(dev_mode=True)
