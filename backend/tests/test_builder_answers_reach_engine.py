"""Builder answers must reach the engine: premise, time period, title, opening roll.

Regressions from live play on 2026-11-22/23:
- a premise typed into the world type box became the whole story title;
- a typed world had no era, so a mind reader story opened in a pre-industrial hamlet;
- the opening situation was rolled without looking at what the player said had changed.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import creation_contract  # noqa: E402
import opening_state  # noqa: E402
import server  # noqa: E402

PREMISE = "I am the only mind reader alive and no one knows. I use it to get ahead."
SEEDS = [f"seed-{n}" for n in range(200)]


def _contract(setup: dict, genre: str = "modern") -> dict:
    return creation_contract.build_creation_contract(
        genre=genre, role="local resident", custom_world_setup={"creationFlow": "advanced", **setup}
    )


# --- premise ---------------------------------------------------------------


def test_premise_survives_normalisation_at_full_length():
    long_premise = "word " * 100  # 500 characters, over the 120 default cap
    out = creation_contract.normalize_custom_world_setup({"premise": long_premise, "want": "safety"})
    assert out["premise"] == long_premise.strip()


def test_premise_is_bounded():
    out = creation_contract.normalize_custom_world_setup({"premise": "x" * 5000})
    assert len(out["premise"]) == creation_contract.MAX_PREMISE_LEN


def test_premise_reaches_the_opening_request_and_later_turns():
    contract = _contract({"premise": PREMISE})
    assert contract["premise"] == PREMISE
    assert any(PREMISE in line for line in creation_contract.build_opening_setup_lines(contract))
    assert PREMISE in creation_contract.build_later_turn_creation_directive(contract)


def test_no_premise_adds_no_premise_lines():
    contract = _contract({})
    assert "premise" not in contract
    assert not any("premise" in line.lower() for line in creation_contract.build_opening_setup_lines(contract))


# --- time period -----------------------------------------------------------


@pytest.mark.parametrize(
    "answer, era",
    [("present_day", "present_day"), ("past", "historical_past"), ("future", "future")],
)
def test_time_period_sets_the_era_of_a_typed_world(answer, era):
    frame = creation_contract.derive_world_frame("only mind reader alive", setup={"timePeriod": answer})
    assert frame["era"] == era
    assert frame["setting"] == "only mind reader alive"


@pytest.mark.parametrize("answer", [None, "", "world_decides", "nonsense"])
def test_no_time_period_leaves_the_era_to_the_world_type(answer):
    typed = creation_contract.derive_world_frame("only mind reader alive", setup={"timePeriod": answer})
    assert typed["era"] == creation_contract.PLAYER_AUTHORED_FRAME_VALUE
    assert creation_contract.derive_world_frame("fantasy", setup={"timePeriod": answer})["era"] == "secondary_world"


def test_time_period_survives_into_later_turn_state():
    rolling = creation_contract.restore_creation_surfaces(
        {},
        {"genre": "only mind reader alive", "custom_world_setup": {"creationFlow": "advanced", "timePeriod": "present_day"}},
    )
    assert rolling["world_frame"]["era"] == "present_day"


def test_typed_world_setting_keeps_a_full_sentence():
    typed = "regular world except i can read peoples mind . it tells me everything i need to know about that person and how i can use it to my advantage"
    assert creation_contract.derive_world_frame(typed)["setting"] == typed


# --- title -----------------------------------------------------------------


def test_short_names_keep_title_case():
    assert server._story_title(None, "low fantasy survival", "Wandering scout") == "Low Fantasy Survival — Wandering Scout"
    assert server._story_title(None, "modern", None) == "Modern — Wanderer"


def test_a_typed_sentence_becomes_a_short_title_in_the_players_casing():
    title = server._story_title(
        None,
        "regular worl except i can read peoples mind . it tellls me everything i need to know",
        "a man with what seems to be the best luck",
    )
    world, role = title.split(" — ")
    assert world == "Regular worl except i can read peoples mind…"
    assert role == "A man with what seems to be the best luck"
    assert len(world) <= server.STORY_TITLE_PART_MAX_CHARS + 1


def test_scenario_title_is_unchanged():
    assert server._story_title({"title": "Dry Reservoir Claim"}, "post-apocalyptic", "resident") == "Dry Reservoir Claim"


# --- opening roll ----------------------------------------------------------


def _rolled(setup: dict) -> set:
    return {opening_state.select_opening_archetype(seed, setup)["archetype_id"] for seed in SEEDS}


@pytest.mark.parametrize("answer, fitting", sorted(opening_state.RECENT_CHANGE_ARCHETYPES.items()))
def test_opening_grows_out_of_the_recent_change(answer, fitting):
    rolled = _rolled({"genre": "only mind reader alive", "custom_world_setup": {"recentChange": answer}})
    assert rolled <= set(fitting)
    assert len(rolled) >= 2


def test_guided_pressure_narrows_the_opening():
    rolled = _rolled({"genre": "only mind reader alive", "custom_world_setup": {"pressures": ["isolation"]}})
    assert rolled <= set(opening_state.PRESSURE_ARCHETYPES["isolation"])


def test_answers_stay_inside_the_genre_pool_where_they_overlap():
    setup = {"genre": "fantasy", "custom_world_setup": {"recentChange": "resources_became_scarce"}}
    pool = opening_state.opening_archetype_pool(setup)
    assert pool
    assert set(pool) <= set(opening_state.RECENT_CHANGE_ARCHETYPES["resources_became_scarce"])
    shared = set(opening_state.catalog_for_genre("fantasy")) & set(pool)
    assert shared == set(pool) or not shared


@pytest.mark.parametrize("custom", [None, {}, {"recentChange": "custom_event"}, {"recentChange": "nothing_major"}])
def test_no_mappable_answer_keeps_the_genre_pool(custom):
    setup = {"genre": "horror", "custom_world_setup": custom}
    assert opening_state.opening_archetype_pool(setup) == opening_state.catalog_for_genre("horror")


def test_every_mapped_archetype_exists():
    for table in (opening_state.RECENT_CHANGE_ARCHETYPES, opening_state.PRESSURE_ARCHETYPES):
        for archetypes in table.values():
            assert set(archetypes) <= set(opening_state.OPENING_ARCHETYPES)


def test_recent_change_line_tells_the_opening_not_to_contradict_it():
    contract = _contract({"recentChange": "custom_event", "customRecentChange": "opportunities arising"})
    lines = creation_contract.build_opening_setup_lines(contract)
    assert any("opportunities arising" in line and "must not contradict" in line for line in lines)
