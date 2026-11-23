"""Finding 5 (review 2, 2026-11-23): a builder selection must mean what its label says.

The expected meanings below are written from the builder labels the player
sees (frontend/src/newstory/AdvancedBuilder.tsx), not copied from the engine
table. The seed 8 case from the review: "A route or supply line failed" drew an
opening about an approaching hazard, and the failed route never appeared.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import creation_contract as cc  # noqa: E402
import opening_state  # noqa: E402
import replayability  # noqa: E402

# id -> (label shown in the builder, words the engine fact must contain, tense marker)
EXPECTED = {
    "someone_disappeared": ("A leader disappeared", ("leader", "disappeared")),
    "resources_became_scarce": ("An important resource became scarce", ("resource", "scarce")),
    "conflict_intensified": ("Violence increased", ("violence", "increased")),
    "disaster_occurred": ("A route or supply line failed", ("route", "supply line", "failed")),
    "important_discovery": ("Something unexplained occurred", ("unexplained", "occurred")),
}
BUILDER = Path(__file__).resolve().parents[2] / "frontend" / "src" / "newstory" / "AdvancedBuilder.tsx"


def _builder_options():
    source = BUILDER.read_text(encoding="utf-8")
    block = source[source.index("const CHANGE_OPTIONS_FIXED"):]
    block = block[: block.index("];")]
    return dict(re.findall(r'value: "([a-z_]+)", label: "([^"]+)"', block))


def test_the_table_covers_every_selectable_change():
    options = _builder_options()
    assert set(options) - {"nothing_major", "custom_event"} == set(EXPECTED)
    for change_id, (label, _words) in EXPECTED.items():
        assert options[change_id] == label  # stable IDs, same labels


@pytest.mark.parametrize("change_id", sorted(EXPECTED))
def test_each_selection_resolves_to_the_fact_its_label_states(change_id):
    _label, words = EXPECTED[change_id]
    fact = cc.resolve_recent_disruption({"recentChange": change_id})
    for word in words:
        assert word in fact, (change_id, fact)
    assert " has " in f" {fact} "  # stated as something that has already happened


@pytest.mark.parametrize("change_id", sorted(EXPECTED))
def test_each_selection_reaches_both_prompts_as_an_established_past_event(change_id):
    setup = cc.normalize_custom_world_setup({"creationFlow": "advanced", "recentChange": change_id})
    contract = cc.build_creation_contract(genre="fantasy", custom_world_setup=setup)
    fact = cc.resolve_recent_disruption(setup)
    opening = "\n".join(cc.build_opening_setup_lines(contract, {}))
    later = cc.build_later_turn_creation_directive(contract, {})
    opening_line = next(line for line in opening.split("\n") if line.startswith("Established past event"))
    assert fact in opening_line
    assert "already happened before the story starts" in opening_line
    assert "its effect must be visible in the opening" in opening_line
    assert "never replaces it or undoes it" in opening_line
    later_line = next(line for line in later.split("\n") if line.startswith("Established past event"))
    assert fact in later_line and "its effects persist" in later_line


def test_nothing_major_and_custom_are_unchanged():
    assert cc.resolve_recent_disruption({"recentChange": "nothing_major"}) == ""
    typed = cc.resolve_recent_disruption({"recentChange": "custom_event", "customRecentChange": "The mill burned."})
    assert typed == "The mill burned."


def test_failed_route_with_an_approaching_second_threat():
    """The review's case: the roll picks an approaching hazard for a failed route."""
    story = {"genre": "canal town", "custom_world_setup": {"recentChange": "disaster_occurred"}}
    seed = next(
        str(i) for i in range(200)
        if opening_state.select_opening_archetype(str(i), story)["archetype_id"] == "storm_approaches"
    )
    archetype = opening_state.select_opening_archetype(seed, story)
    assert archetype["immediate_problem"] == "environmental hazard closing in"  # a second threat may approach

    setup = cc.normalize_custom_world_setup({"creationFlow": "advanced", **story["custom_world_setup"]})
    contract = cc.build_creation_contract(genre="canal town", custom_world_setup=setup)
    line = next(
        l for l in cc.build_opening_setup_lines(contract, {}) if l.startswith("Established past event")
    )
    # The route has already failed, it matters in the opening, and the hazard cannot stand in for it.
    assert "a route or supply line has failed" in line
    assert "its effect must be visible in the opening" in line
    assert "A new threat may arrive on top of it" in line


def test_an_older_save_keeps_its_identity_and_gains_the_stated_meaning(monkeypatch):
    # Stored IDs are untouched. The stored identity and opening are never rolled again.
    state, _ = replayability.init_new_story(
        genre="fantasy", role="scout", tone="dark", difficulty="standard", scenario_id=None,
        custom_premise=None, custom_world_setup={"recentChange": "important_discovery"}, run_seed="older-save",
    )
    identity, opening = dict(state["identity"]), dict(state["opening"])

    def forbidden(*args, **kwargs):
        pytest.fail("an existing story was rolled again")

    monkeypatch.setattr(replayability, "derive_run_identity", forbidden)
    monkeypatch.setattr(replayability.opening_state, "select_opening_archetype", forbidden)
    state, *_ = replayability.prepare_action_turn(state, 2, {})
    assert state["identity"] == identity and state["opening"] == opening
    # Its later turns now read the stored ID as the label the player picked.
    assert cc.resolve_recent_disruption({"recentChange": "important_discovery"}) == "something unexplained has occurred"
    # An ID this build does not know (hand-made or much older) keeps the old reading.
    assert cc.resolve_recent_disruption({"recentChange": "plague_arrived"}) == "plague arrived"
