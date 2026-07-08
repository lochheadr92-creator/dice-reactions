"""
Passive NPC and settlement traits — presence, determinism, and player isolation.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import npc_settlement_traits as traits  # noqa: E402
import player_api  # noqa: E402
import replayability  # noqa: E402
import scenarios  # noqa: E402

SEED = "traits-determinism-seed-6d1a"
SEED_B = "traits-determinism-seed-6d1b"

NPC_TRAIT_KEYS = frozenset({
    "ambition",
    "fear",
    "loyalty_anchor",
    "personal_stakes",
    "risk_tolerance",
    "pressure_sensitivity",
    "social_role",
})

SETTLEMENT_TRAIT_KEYS = frozenset({
    "prosperity",
    "stability",
    "fear",
    "crime",
    "culture_tag",
    "dominant_pressure",
    "local_stakes",
})


def _init_with_scenario(seed: str = SEED):
    scenario = scenarios.get_scenario("suburban-collapse")
    return replayability.init_new_story(
        genre=scenario["genre"],
        role=scenario["role"],
        tone=scenario["tone"],
        difficulty=scenario["difficulty"],
        scenario_id=scenario["id"],
        custom_premise=None,
        custom_world_setup=None,
        scenario=scenario,
        run_seed=seed,
    )


def _strip_trait_metadata(state: dict) -> dict:
    cleaned = copy.deepcopy(state)
    cleaned.pop("npc_traits", None)
    cleaned.pop("settlement_traits", None)
    return cleaned


def _turn_gameplay_fingerprint(state: dict, turn_number: int = 2) -> str:
    out_state, directives, diagnostics, events, cast = replayability.prepare_action_turn(
        copy.deepcopy(state),
        turn_number,
    )
    payload = {
        "state": _strip_trait_metadata(out_state),
        "directives": directives,
        "diagnostics": diagnostics,
        "events": events,
        "cast": cast,
    }
    return json.dumps(payload, sort_keys=True, default=str)


def test_traits_present_after_story_init():
    state, _ = _init_with_scenario()
    assert state["npc_traits"]["version"] == traits.TRAITS_VERSION
    assert state["settlement_traits"]["version"] == traits.TRAITS_VERSION
    assert len(state["npc_traits"]["by_npc_id"]) == 3
    assert len(state["settlement_traits"]["by_location_id"]) == 1

    for row in state["npc_traits"]["by_npc_id"].values():
        assert NPC_TRAIT_KEYS.issubset(row.keys())

    settlement = next(iter(state["settlement_traits"]["by_location_id"].values()))
    assert SETTLEMENT_TRAIT_KEYS.issubset(settlement.keys())
    assert settlement.get("settlement_id", "").startswith("settlement-")


def test_traits_deterministic_for_same_seed():
    state_a, _ = _init_with_scenario(SEED)
    state_b, _ = _init_with_scenario(SEED)
    assert state_a["npc_traits"] == state_b["npc_traits"]
    assert state_a["settlement_traits"] == state_b["settlement_traits"]


def test_traits_can_differ_across_seeds():
    state_a, _ = _init_with_scenario(SEED)
    state_b, _ = _init_with_scenario(SEED_B)
    assert state_a["npc_traits"] != state_b["npc_traits"] or state_a["settlement_traits"] != state_b["settlement_traits"]


def test_gameplay_fingerprint_unchanged_without_trait_metadata():
    state, _ = _init_with_scenario(SEED)
    assert _turn_gameplay_fingerprint(state) == _turn_gameplay_fingerprint(_strip_trait_metadata(state))


def test_player_session_payload_excludes_traits():
    session = {
        "id": "sess-1",
        "genre": "fantasy",
        "role": "scout",
        "tone": "grim",
        "difficulty": "standard",
        "debug_mode": False,
        "title": "Chronicle",
        "turn_count": 1,
        "last_narrative_snippet": "Wind.",
        "last_state": {"Health": "stable"},
        "replayability_state": {
            "npc_traits": {"by_npc_id": {"npc-abc": {"ambition": "high"}}},
            "settlement_traits": {"by_location_id": {"loc-abc": {"prosperity": "low"}}},
        },
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    out = player_api.build_player_session(session)
    blob = json.dumps(out)
    assert "npc_traits" not in blob
    assert "settlement_traits" not in blob
    assert "ambition" not in blob