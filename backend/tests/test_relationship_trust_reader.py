"""One reader for how far someone trusts the player, owned by the relationship system."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import npc_possessions  # noqa: E402
import order_engine  # noqa: E402
import play_facts  # noqa: E402
import relationships as rel  # noqa: E402

VECTORS = {"relationship_vectors": [{"name": "Mara Voss", "trust": 5}, {"name": "Old Tom", "trust": -40}]}


def test_the_engine_vector_outranks_a_number_on_the_cast_row():
    assert rel.recorded_trust(VECTORS, {"name": "Mara Voss", "trust": 95}) == 5
    assert rel.recorded_trust(VECTORS, {"name": "mara  voss!", "trust": 95}) == 5         # same person, loosely written
    assert rel.recorded_trust(VECTORS, {"name": "Old Tom"}) == -40
    assert rel.recorded_trust({}, {"name": "Mara Voss", "trust": 95}) == 95
    assert rel.recorded_trust(VECTORS, {"name": "Stranger"}) is None
    assert rel.recorded_trust(None, {"name": ""}) is None


@pytest.mark.parametrize("stance,expected", [
    ("ally", rel.TRUST_IF_FRIENDLY), ("Friend", rel.TRUST_IF_FRIENDLY), ("devoted", rel.TRUST_IF_FRIENDLY),
    ("hostile", rel.TRUST_IF_HOSTILE), ("enemy", rel.TRUST_IF_HOSTILE),
    ("neutral", rel.TRUST_IF_UNKNOWN), ("", rel.TRUST_IF_UNKNOWN), (None, rel.TRUST_IF_UNKNOWN),
])
def test_with_nothing_recorded_the_stance_fills_in(stance, expected):
    assert rel.trust_in_player({}, {"name": "Stranger", "stance": stance}) == expected


def test_a_recorded_number_beats_the_stance():
    assert rel.trust_in_player(VECTORS, {"name": "Mara Voss", "stance": "ally"}) == 5


def test_who_will_not_deal_with_the_player_and_who_is_friendly():
    assert rel.refuses_player({"stance": "Hostile"}) and rel.refuses_player({"stance": "neutral", "refuses_orders": True})
    assert not rel.refuses_player({"stance": "wary"}) and not rel.refuses_player({})
    assert rel.is_friendly({"stance": "friend"}) and not rel.is_friendly({"stance": "neutral"})


def test_every_engine_reads_trust_through_the_relationship_system():
    row = {"name": "Mara Voss", "trust": 95, "stance": "neutral"}
    assert play_facts.trust_of(VECTORS, row) == 5
    assert order_engine._willing(VECTORS, row) is False                        # 5 is under the order threshold
    assert npc_possessions._discloses(VECTORS, row) is False                   # and under the disclosure threshold
    assert npc_possessions._discloses({}, row) is True
    assert play_facts.hostile({"stance": "enemy"}) is True
    # No engine keeps a stance table or a trust reader of its own.
    for module, names in ((play_facts, ("_HOSTILE", "_FRIENDLY")), (order_engine, ("_HOSTILE", "_trust")),
                          (npc_possessions, ("_FRIENDLY", "oe"))):
        for name in names:
            assert not hasattr(module, name), f"{module.__name__}.{name}"
