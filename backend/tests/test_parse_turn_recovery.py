"""
parse_turn recovers a <narrative> block whose closing tag is missing or
misspelled (seen with Qwen3.6 on Ollama, 2026-11-21: "no narrative paragraphs"
turns that carried 800-4500 chars of valid prose).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

_TAIL = (
    "<choices>\nA. Wait by the pillar.\nB. Climb the embankment.\n"
    "C. Search the van.\nD. Call out to the voices.\n</choices>\n"
    "<state>\nHealth: bruised\n</state>\n<ledger>\nCarried: machete\n</ledger>"
)
_STATE = '<rolling_state>\n{"scene": "overpass"}\n</rolling_state>\n\n'
_PROSE = "The air tastes of rust.\n\nYour ribs throb with every breath."


def test_well_formed_narrative_unchanged():
    parsed = server.parse_turn(_STATE + f"<narrative>\n{_PROSE}\n</narrative>\n" + _TAIL)
    assert parsed.paragraphs == ["The air tastes of rust.", "Your ribs throb with every breath."]
    assert len(parsed.choices) == 4


def test_missing_narrative_close_runs_to_next_block():
    parsed = server.parse_turn(_STATE + f"<narrative>\n{_PROSE}\n\n" + _TAIL)
    assert parsed.paragraphs == ["The air tastes of rust.", "Your ribs throb with every breath."]
    assert len(parsed.choices) == 4
    assert parsed.rolling_state == {"scene": "overpass"}


def test_misspelled_narrative_close_is_dropped():
    parsed = server.parse_turn(_STATE + f"<narrative>\n{_PROSE}\n</narrage>\n" + _TAIL)
    assert parsed.paragraphs == ["The air tastes of rust.", "Your ribs throb with every breath."]
    assert "narrage" not in parsed.narrative


def test_narrative_without_any_following_block_still_lacks_choices():
    parsed = server.parse_turn(_STATE + f"<narrative>\n{_PROSE}\n")
    assert parsed.paragraphs
    assert parsed.choices == []


def test_no_narrative_tag_gives_empty_narrative():
    parsed = server.parse_turn(_STATE + _TAIL)
    assert parsed.narrative == ""
