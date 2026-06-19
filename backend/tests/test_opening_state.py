"""
Opening State v1 — deterministic tests (structured truth + scenario preservation).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import opening_state  # noqa: E402
import replayability  # noqa: E402
import run_identity  # noqa: E402
from scenarios import get_scenario  # noqa: E402

SEED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CORPUS = (
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    "cccccccc-cccc-cccc-cccc-cccccccccccc",
    "11111111-1111-1111-1111-111111111111",
    "22222222-2222-2222-2222-222222222222",
    "33333333-3333-3333-3333-333333333333",
    "44444444-4444-4444-4444-444444444444",
    "55555555-5555-5555-5555-555555555555",
)


def _setup(**over):
    base = {"genre": "noir", "scenario_id": None}
    base.update(over)
    return base


REQUIRED_FIELDS = (
    "archetype_id",
    "immediate_problem",
    "threatened_resource",
    "relationship_tension",
    "time_pressure",
    "opportunity",
    "pressure_origins",
    "fact_ids",
)


def test_at_least_twelve_opening_archetypes():
    assert len(opening_state.OPENING_ARCHETYPES) >= 12


def test_every_archetype_has_structured_template_fields():
    for meta in opening_state.OPENING_ARCHETYPES.values():
        assert meta.get("label")
        assert meta.get("immediate_problem")
        assert meta.get("threatened_resource")


def test_generated_opening_has_required_structured_fields():
    identity = run_identity.derive_run_identity(SEED, _setup())
    opening = opening_state.select_opening_archetype(SEED, _setup(), identity=identity)
    for field in REQUIRED_FIELDS:
        assert opening.get(field)
    assert len(opening["immediate_problem"]) <= opening_state.MAX_FACT_LEN
    assert 1 <= len(opening["pressure_origins"]) <= opening_state.MAX_ORIGINS


def test_same_seed_reproduces_fact_ids():
    identity = run_identity.derive_run_identity(SEED, _setup())
    a = opening_state.select_opening_archetype(SEED, _setup(), identity=identity)
    b = opening_state.select_opening_archetype(SEED, _setup(), identity=identity)
    assert a["fact_ids"] == b["fact_ids"]
    assert a["pressure_origins"] == b["pressure_origins"]


def test_corpus_produces_three_opening_archetypes():
    setup = _setup()
    archetypes = set()
    for seed in CORPUS:
        identity = run_identity.derive_run_identity(seed, setup)
        opening = opening_state.select_opening_archetype(seed, setup, identity=identity)
        archetypes.add(opening["archetype_id"])
    assert len(archetypes) >= 3


def test_scenario_preservation_sets_flag_and_hinted_archetype():
    scenario = get_scenario("suburban-collapse")
    identity = run_identity.derive_run_identity(SEED, _setup(genre=scenario["genre"], scenario_id=scenario["id"]))
    opening = opening_state.select_opening_archetype(
        SEED, _setup(genre=scenario["genre"], scenario_id=scenario["id"]), identity=identity, scenario=scenario
    )
    assert opening["preserved_scenario"] is True
    assert opening["archetype_id"] == "unexpected_visitor"
    assert opening.get("scenario_title")


def test_scenario_directive_mentions_canonical_seed():
    scenario = get_scenario("dinosaur-containment-breach")
    identity = run_identity.derive_run_identity(SEED, _setup(genre=scenario["genre"], scenario_id=scenario["id"]))
    opening = opening_state.select_opening_archetype(
        SEED, _setup(genre=scenario["genre"], scenario_id=scenario["id"]), identity=identity, scenario=scenario
    )
    directive = opening_state.build_opening_directive(opening, identity, scenario=scenario)
    assert opening_state.OPENING_DIRECTIVE_MARKER in directive
    assert "authoritative" in directive.lower()
    assert scenario["title"] in directive or scenario["id"] in directive


def test_hidden_threat_not_in_opening_facts_or_directive():
    scenario = get_scenario("suburban-collapse")
    hidden = scenario.get("hidden_threat", "")
    identity = run_identity.derive_run_identity(SEED, _setup(scenario_id=scenario["id"], hidden_threat=hidden))
    opening = opening_state.select_opening_archetype(SEED, _setup(scenario_id=scenario["id"]), identity=identity, scenario=scenario)
    blob = str(opening)
    directive = opening_state.build_opening_directive(opening, identity, scenario=scenario)
    if hidden:
        assert hidden not in blob
        assert hidden not in directive


def test_opening_directive_uses_structured_facts_not_hook_labels():
    identity = run_identity.derive_run_identity(SEED, _setup(genre="mystery"))
    opening = opening_state.select_opening_archetype(SEED, _setup(genre="mystery"), identity=identity)
    directive = opening_state.build_opening_directive(opening, identity)
    assert opening["immediate_problem"] in directive
    assert opening["threatened_resource"] in directive
    assert identity["primary_pressure_kind"] in directive


def test_opening_pressure_origins_seed_pressure_graph():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=SEED,
    )
    origin_ids = {o["origin_id"] for o in state["opening"]["pressure_origins"]}
    node_origins = {n["origin_id"] for n in state["pressure_graph"]["nodes"]}
    assert origin_ids & node_origins


def test_empty_opening_returns_empty_directive():
    assert opening_state.build_opening_directive({}, {}) == ""


@pytest.mark.parametrize("genre", ["noir", "horror", "romance", "mystery", "fantasy"])
def test_each_catalog_genre_selects_valid_archetype(genre):
    identity = run_identity.derive_run_identity(SEED, _setup(genre=genre))
    opening = opening_state.select_opening_archetype(SEED, _setup(genre=genre), identity=identity)
    assert opening["archetype_id"] in opening_state.OPENING_ARCHETYPES