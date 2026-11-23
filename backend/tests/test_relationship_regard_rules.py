"""The relationship system owns the rules for how one NPC sees another. The edges stay with the caller."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import regard_engine  # noqa: E402
import relationships as rel  # noqa: E402

A = {"id": "npc-a", "name": "Asha"}
B = {"id": "npc-b", "name": "Bram"}


def test_regard_is_directional_and_two_strangers_start_at_the_default():
    edges = []
    assert rel.regard_value(edges, "npc-a", "npc-b") == rel.REGARD_DEFAULT and not rel.has_regard(edges, "npc-a", "npc-b")
    assert rel.set_regard(edges, A, B, 62) == 62
    assert rel.regard_value(edges, "npc-a", "npc-b") == 62
    assert rel.regard_value(edges, "npc-b", "npc-a") == rel.REGARD_DEFAULT        # the other way is its own number
    assert rel.set_regard(edges, A, B, 400) == rel.REGARD_MAX and rel.set_regard(edges, A, B, -9) == rel.REGARD_MIN
    assert len(edges) == 1 and edges[0]["holder_name"] == "Asha" and edges[0]["toward_name"] == "Bram"
    assert rel.regard_value(None, "npc-a", "npc-b") == rel.REGARD_DEFAULT


@pytest.mark.parametrize("trust,hostile,pull", [
    (0, False, 0), (19, False, 0), (20, False, 5), (26, False, 5), (40, False, 10), (100, False, 40), (90, True, 0),
])
def test_how_far_the_player_can_move_someone_follows_their_trust_in_the_player(trust, hostile, pull):
    assert rel.regard_pull(trust, hostile) == pull


def test_each_act_moves_regard_by_its_own_rule_and_stays_in_range():
    assert rel.regard_after("vouch", 30, 10) == 40 and rel.regard_after("vouch", 30, 0) is None
    assert rel.regard_after("mediate", 30, 10) == 35 and rel.regard_after("mediate", 30, 1) is None
    assert rel.regard_after("expose", 30, 10) == 10 and rel.regard_after("expose", 30, 0) is None
    assert rel.regard_after("vouch", 95, 40) == rel.REGARD_MAX and rel.regard_after("expose", 5, 40) == rel.REGARD_MIN
    with pytest.raises(ValueError):
        rel.regard_after("flatter", 30, 10)


def test_the_words_and_the_errand_rule_use_the_same_thresholds():
    assert [rel.regard_word(v) for v in (0, 19, 20, 39, 40, 49, 50, 100)] == [
        "cold toward", "cold toward", "wary of", "wary of", "civil but unsure of", "civil but unsure of", "warm toward", "warm toward"]
    assert not rel.errand_agreed(rel.REGARD_WILL_HELP - 1) and rel.errand_agreed(rel.REGARD_WILL_HELP)
    assert rel.regard_word(rel.REGARD_MET) == "civil but unsure of"              # an introduction makes people civil, no more


def test_the_move_engine_keeps_no_regard_rules_of_its_own():
    for name in ("DEFAULT", "WILL_HELP", "MET", "LISTENS_FROM", "regard", "_set", "word"):
        assert not hasattr(regard_engine, name), name
