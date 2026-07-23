"""Scenario coherence — Quick Start dinosaur drift regressions."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import opening_state  # noqa: E402
import scenario_coherence as sc  # noqa: E402
from scenarios import get_scenario  # noqa: E402


def test_dinosaur_survival_genre_normalizes_to_prehistoric_catalog():
    assert opening_state.normalize_genre("dinosaur survival") == "prehistoric survival"
    catalog = opening_state.catalog_for_genre("dinosaur survival")
    assert "debt_called" not in catalog
    assert "authority_demands" not in catalog
    assert "injury_complicates" in catalog


def test_dinosaur_scenario_has_world_frame_and_forbidden_debt_frames():
    scenario = get_scenario("dinosaur-containment-breach")
    assert scenario is not None
    frame = scenario["world_frame"]
    assert frame["era"] == "modern_research_containment"
    assert any("debt" in f or "property" in f for f in frame["forbidden_opening_frames"])
    assert "escaped_predators" in frame["primary_pressures"]


def test_choice_rejects_unknown_person_before_introduction():
    ok, reason = sc.validate_choices_named_entities(
        [{"label": "C", "text": "Leave now and intercept Harwood on the switchback"}],
        narrative="Rain hammers the substation roof. Tracks cross the floor.",
        prior_rolling=None,
        scenario=None,
    )
    assert ok is False
    assert "Harwood" in reason


def test_choice_allows_scenario_npc_after_narrative_introduces_them():
    scenario = get_scenario("dinosaur-containment-breach")
    narrative = (
        "Rain hammers Substation 4. Dr. Aris Kemal leans against the generator, "
        "his thigh dark with blood. Three-toed tracks cross the wet concrete."
    )
    ok, reason = sc.validate_choices_named_entities(
        [{"label": "A", "text": "Stay with Kemal and try to stop the bleeding"}],
        narrative=narrative,
        prior_rolling=None,
        scenario=scenario,
    )
    assert ok is True, reason


def test_opening_rejects_property_debt_frame_for_dinosaur_scenario():
    scenario = get_scenario("dinosaur-containment-breach")
    narrative = (
        "The shelter beam bows in the rain. Harwood will arrive to collect the debt "
        "and repossess the property after the inspection failed."
    )
    choices = [
        {"label": "A", "text": "Prepare to renegotiate terms with Harwood"},
    ]
    ok, reason = sc.validate_scenario_frame_coherence(
        scenario=scenario,
        narrative=narrative,
        choices=choices,
        is_opening=True,
    )
    assert ok is False
    assert "debt" in reason or "property" in reason


def test_opening_accepts_containment_survival_frame():
    scenario = get_scenario("dinosaur-containment-breach")
    narrative = (
        "Rain hammers Substation 4 of Mainland Site B. Dr. Aris Kemal bleeds against "
        "the generator housing while three-toed tracks cross the flooded floor. "
        "The radio crackles once and dies."
    )
    ok, reason = sc.validate_scenario_opening_context(
        scenario=scenario,
        narrative=narrative,
        paragraphs=[narrative],
    )
    assert ok is True, reason


def test_scenario_frame_directive_is_compact():
    session = {"scenario_id": "dinosaur-containment-breach", "genre": "prehistoric survival"}
    text = opening_state.build_scenario_frame_directive(session)
    assert "SCENARIO_FRAME" in text
    assert "Dinosaur Containment" in text or "dinosaur" in text.lower()
    assert len(text) < 800


def test_run_coherence_blocks_harwood_opening_choice():
    scenario = get_scenario("dinosaur-containment-breach")
    narrative = (
        "Rain hammers Substation 4 of Mainland Site B. Three-toed tracks cross the "
        "flooded concrete. A heavy shape moves beyond the paddock fence while the "
        "radio only returns static. No one else is visible inside the bunker."
    )
    parsed = SimpleNamespace(
        narrative=narrative,
        paragraphs=[narrative],
        choices=[
            {"label": "A", "text": "Brace the damaged hatch"},
            {"label": "B", "text": "Check the fence line"},
            {"label": "C", "text": "Intercept Harwood on the switchback"},
            {"label": "D", "text": "Listen for movement uphill"},
        ],
    )
    ok, reason = sc.run_coherence_checks(
        parsed=parsed,
        session={"scenario_id": "dinosaur-containment-breach"},
        scenario=scenario,
        prior_rolling=None,
        is_opening=True,
    )
    assert ok is False
    assert "Harwood" in reason or "unknown person" in reason
