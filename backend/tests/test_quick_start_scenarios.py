"""Quick Start curated scenario pools — Stage 1 authority + membership."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import opening_state  # noqa: E402
import scenarios  # noqa: E402
from scenarios import ScenarioResolutionError, resolve_new_story_scenario  # noqa: E402


def test_at_least_twenty_four_curated_scenarios():
    assert len(scenarios.SCENARIOS) >= 24


def test_every_quick_start_pool_has_three_resolvable_scenarios():
    for card_key, pool in scenarios.QUICK_START_SCENARIO_POOLS.items():
        assert len(pool) >= 3, card_key
        for sid in pool:
            sc = scenarios.get_scenario(sid)
            assert sc is not None, f"{card_key}: missing {sid}"
            assert sc.get("starting_pressure"), sid
            assert isinstance(sc.get("world_frame"), dict), sid
            assert sc["world_frame"].get("primary_pressures"), sid
            assert sc.get("role"), sid


def test_prehistoric_pool_is_literal_not_modern_containment():
    pool = scenarios.QUICK_START_SCENARIO_POOLS["dinosaur-survival"]
    assert "dinosaur-containment-breach" not in pool
    for sid in pool:
        sc = scenarios.get_scenario(sid)
        assert sc["genre"] == "prehistoric survival"
        frame = sc["world_frame"]
        assert frame["technology"] == "lithic_and_bone"
        forbidden = " ".join(frame.get("forbidden_opening_frames") or [])
        assert "research_facility" in forbidden or "firearms" in forbidden


def test_dinosaur_containment_remains_available_as_modern():
    sc = scenarios.get_scenario("dinosaur-containment-breach")
    assert sc is not None
    assert sc["genre"] == "modern containment"
    for pool in scenarios.QUICK_START_SCENARIO_POOLS.values():
        assert "dinosaur-containment-breach" not in pool


def test_select_scenario_id_deterministic_per_seed():
    pool = scenarios.QUICK_START_SCENARIO_POOLS["fantasy"]
    a = scenarios.select_scenario_id_from_pool(pool, "story-create:abc")
    b = scenarios.select_scenario_id_from_pool(pool, "story-create:abc")
    assert a == b
    assert a in pool
    picks = {
        scenarios.select_scenario_id_from_pool(pool, f"story-create:var-{i}")
        for i in range(20)
    }
    assert len(picks) >= 2


def test_backend_authority_resolves_quick_start_without_client_scenario_id():
    seed = "story-create:authority-1"
    expected = scenarios.select_quick_start_scenario_id("dinosaur-survival", seed)
    sid, sc = resolve_new_story_scenario(
        quick_start_key="dinosaur-survival",
        creation_request_id=seed,
    )
    assert sid == expected
    assert sc is not None
    assert sc["id"] == sid
    assert sc["role"]
    assert sid != "dinosaur-containment-breach"


def test_matching_client_scenario_id_accepted():
    seed = "story-create:match-ok"
    expected = scenarios.select_quick_start_scenario_id("horror", seed)
    sid, sc = resolve_new_story_scenario(
        quick_start_key="horror",
        creation_request_id=seed,
        scenario_id=expected,
    )
    assert sid == expected
    assert sc["id"] == expected


def test_mismatched_client_scenario_id_fails_closed():
    seed = "story-create:mismatch"
    expected = scenarios.select_quick_start_scenario_id("fantasy", seed)
    other = next(
        x for x in scenarios.QUICK_START_SCENARIO_POOLS["fantasy"] if x != expected
    )
    with pytest.raises(ScenarioResolutionError, match="does not match"):
        resolve_new_story_scenario(
            quick_start_key="fantasy",
            creation_request_id=seed,
            scenario_id=other,
        )


def test_scenario_from_other_pool_fails_closed():
    seed = "story-create:cross-pool"
    with pytest.raises(ScenarioResolutionError, match="not in the Quick Start pool"):
        resolve_new_story_scenario(
            quick_start_key="dinosaur-survival",
            creation_request_id=seed,
            scenario_id="suburban-collapse",
        )


def test_unknown_scenario_id_fails_closed():
    with pytest.raises(ScenarioResolutionError, match="Unknown scenario"):
        resolve_new_story_scenario(scenario_id="no-such-scenario-ever")


def test_unknown_quick_start_key_fails_closed():
    with pytest.raises(ScenarioResolutionError, match="Unknown quick_start_key"):
        resolve_new_story_scenario(
            quick_start_key="not-a-card",
            creation_request_id="story-create:x",
        )


def test_prehistoric_cannot_use_containment_even_if_forced_client_id():
    with pytest.raises(ScenarioResolutionError):
        resolve_new_story_scenario(
            quick_start_key="dinosaur-survival",
            creation_request_id="story-create:x",
            scenario_id="dinosaur-containment-breach",
        )


def test_same_creation_request_id_same_scenario():
    a, _ = resolve_new_story_scenario(
        quick_start_key="war-survival",
        creation_request_id="story-create:stable",
    )
    b, _ = resolve_new_story_scenario(
        quick_start_key="war-survival",
        creation_request_id="story-create:stable",
    )
    assert a == b


def test_direct_scenario_path_still_loads_modern_containment():
    sid, sc = resolve_new_story_scenario(scenario_id="dinosaur-containment-breach")
    assert sid == "dinosaur-containment-breach"
    assert sc["genre"] == "modern containment"


def test_scenario_role_is_authoritative_for_each_pool_member():
    for pool in scenarios.QUICK_START_SCENARIO_POOLS.values():
        for sid in pool:
            sc = scenarios.get_scenario(sid)
            assert sc.get("role") and sc["role"].lower() != "wanderer"


def test_scenario_frame_directive_for_prehistoric_pool_member():
    session = {"scenario_id": "flint-band-stalked", "genre": "prehistoric survival"}
    text = opening_state.build_scenario_frame_directive(session)
    assert "SCENARIO_FRAME" in text
    assert len(text) < 800


def test_archetype_hints_cover_quick_pools():
    for pool in scenarios.QUICK_START_SCENARIO_POOLS.values():
        for sid in pool:
            assert sid in opening_state.SCENARIO_ARCHETYPE_HINTS, sid
