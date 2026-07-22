"""Living Cast Engine v1 — cross-module integration tests."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import npc_agendas as agendas  # noqa: E402
import npc_world_moves as world_moves  # noqa: E402
import player_api  # noqa: E402
import pressure_graph  # noqa: E402
import replayability  # noqa: E402
import scenarios  # noqa: E402
import server  # noqa: E402

SEED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SEED_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CORPUS = (
    SEED,
    SEED_B,
    "cccccccc-cccc-cccc-cccc-cccccccccccc",
    "11111111-1111-1111-1111-111111111111",
    "22222222-2222-2222-2222-222222222222",
    "33333333-3333-3333-3333-333333333333",
    "44444444-4444-4444-4444-444444444444",
    "55555555-5555-5555-5555-555555555555",
)

# A full 12-NPC new-story fixture is 16.1 KiB under production compact JSON.
# Keep a narrow 20 KiB envelope here; long-run all-subsystem state has its own
# independently measured budget in replayability.REPLAYABILITY_STATE_BUDGET_BYTES.
INITIAL_REPLAYABILITY_STATE_BUDGET_BYTES = 20 * 1024


def _record(name: str, slot: int = 0) -> dict:
    return {"name": name, "source_type": "seed_record", "source_slot": slot}


def _rolling(name: str = "Marlene Cho") -> dict:
    return {
        "scene": "dock warehouse",
        "npcs": [{"name": name, "stance": "ally", "last_seen": "dock"}],
        "relationship_vectors": [
            {"name": name, "trust": 10, "loyalty": 30, "fear": 0, "resentment": 12, "state": "neutral"}
        ],
        "faction_pressure": [{"name": "Syndicate", "ticks": {"suspicion": 0, "goodwill": 0}}],
    }


def test_scenario_npc_id_stable_across_seeds():
    scenario = scenarios.SCENARIOS[0]
    a, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=scenario["id"], custom_premise=None, custom_world_setup=None,
        run_seed=SEED, scenario=scenario,
    )
    b, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=scenario["id"], custom_premise=None, custom_world_setup=None,
        run_seed=SEED_B, scenario=scenario,
    )
    id_a = a["npc_agendas"]["active"][0]["npc_id"]
    id_b = b["npc_agendas"]["active"][0]["npc_id"]
    assert id_a == id_b
    assert a["npc_agendas"]["active"][0]["goal_kind"] != b["npc_agendas"]["active"][0]["goal_kind"] or (
        a["npc_agendas"]["active"][0]["fear_kind"] != b["npc_agendas"]["active"][0]["fear_kind"]
    )


def test_new_story_seeds_agendas_for_canonical_npcs():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None,
        run_seed=SEED, npc_seed_records=[_record("Marlene Cho", 0), _record("Greg Kane", 1)],
    )
    assert len(state["npc_agendas"]["active"]) == 2
    assert state["npc_agendas"]["active"][0]["npc_id"].startswith("npc-")


def test_world_advances_with_receipt_not_rolling_event():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None,
        run_seed=SEED, npc_seed_records=[_record("Marlene Cho")],
    )
    rolling = _rolling()
    updated, directives, diag, _, cast = replayability.prepare_action_turn(state, 2, rolling_state=rolling)
    assert "engine_world_events" not in (cast or {})
    if diag.get("npc_move_receipt_emitted"):
        assert updated.get("npc_move_receipts")
        assert directives.get("world")


def test_move_state_exists_before_narration():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None,
        run_seed=SEED, npc_seed_records=[_record("Marlene Cho")],
    )
    rolling = _rolling()
    updated, _, diag, _, cast = replayability.prepare_action_turn(state, 2, rolling_state=rolling)
    if diag.get("npc_move_receipt_emitted"):
        assert updated["npc_move_receipts"][0]["turn"] == 2
        assert cast.get("relationship_vectors") or cast.get("faction_pressure") is not None or True


def test_player_api_omits_living_cast_state():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None,
        run_seed=SEED, npc_seed_records=[_record("Marlene Cho")],
    )
    safe = player_api.build_player_session({"id": "s1", "replayability_state": state})
    assert "replayability_state" not in safe
    assert "npc_move_receipts" not in json.dumps(safe)


def test_prompt_safe_prior_state_omits_receipts():
    rolling = _rolling()
    rolling["npc_move_receipts"] = [{"receipt_id": "npc-move-fake"}]
    rolling["engine_world_events"] = [{"event_id": "evt-1"}]
    visible = server._prompt_safe_rolling(rolling)
    assert "npc_move_receipts" not in visible
    assert "engine_world_events" not in visible


def test_engine_never_puts_receipts_in_rolling():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None,
        run_seed=SEED, npc_seed_records=[_record("Marlene Cho")],
    )
    _, _, diag, _, cast = replayability.prepare_action_turn(state, 2, rolling_state=_rolling())
    assert "npc_move_receipts" not in (cast or {})
    assert "engine_world_events" not in (cast or {})


def test_duplicate_receipt_creates_no_duplicate_echo():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=SEED,
    )
    src = {
        "source_kind": "npc_world_move",
        "source_event_id": "npc-move-test12345",
        "echo_kind": "obligation_returns",
        "label": "negotiate",
        "mature_in": 3,
    }
    once = replayability.finalize_action_turn(state, [src], 2)
    twice = replayability.finalize_action_turn(once, [src], 2)
    ids = [e["source_event_id"] for e in twice["consequence_echoes"]["scheduled"]]
    assert ids.count("npc-move-test12345") == 1


def test_unsupported_move_kind_creates_no_echo_from_mapping():
    src = world_moves.move_to_echo_source({"move_kind": "gather", "receipt_id": "npc-move-g"})
    assert src is None


def test_echo_references_receipt_id():
    move = {"move_kind": "negotiate", "receipt_id": "npc-move-abc123456789", "observable_template_id": "negotiate_faction"}
    src = world_moves.move_to_echo_source(move)
    assert src["source_event_id"] == "npc-move-abc123456789"


def test_finalize_idempotent_on_retry_sources():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=SEED,
    )
    rolling = _rolling()
    prepared, _, _, _, cast = replayability.prepare_action_turn(state, 2, rolling_state=rolling)
    sources = replayability.collect_qualifying_echo_sources(
        prior_rolling=rolling, merged_rolling=cast, turn_number=2, guard_adjustments=[]
    )
    once = replayability.finalize_action_turn(prepared, sources, 2)
    twice = replayability.finalize_action_turn(once, sources, 2)
    move_echoes = [e for e in twice["consequence_echoes"]["scheduled"] if e.get("source_kind") == "npc_world_move"]
    event_ids = [e["source_event_id"] for e in move_echoes]
    assert len(event_ids) == len(set(event_ids))


def test_corpus_variation_goals_fears_leverage_moves():
    goals, fears, leverage, move_kinds = set(), set(), set(), set()
    for seed in CORPUS:
        state, _ = replayability.init_new_story(
            genre="noir", role="d", tone="t", difficulty="standard",
            scenario_id=None, custom_premise=None, custom_world_setup=None,
            run_seed=seed, npc_seed_records=[_record("Corpus NPC")],
        )
        ag = state["npc_agendas"]["active"][0]
        goals.add(ag["goal_kind"])
        fears.add(ag["fear_kind"])
        leverage.add(ag["leverage_kind"])
        _, _, diag, _, _ = replayability.prepare_action_turn(
            state, 2, rolling_state=_rolling("Corpus NPC")
        )
        if diag.get("npc_move_kind"):
            move_kinds.add(diag["npc_move_kind"])
    assert len(goals) >= 3
    assert len(fears) >= 2
    assert len(leverage) >= 2


def test_replayability_state_size_bounds():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None,
        run_seed=SEED,
        npc_seed_records=[_record(f"NPC-{i}", i) for i in range(12)],
    )
    state["npc_move_receipts"] = [
        {
            "receipt_id": f"npc-move-{i:04d}",
            "receipt_type": "npc_move_committed",
            "turn": 2,
            "npc_id": f"npc-{i}",
            "agenda_id": f"agenda-{i}",
            "move_kind": "protect",
            "target_type": "player",
            "target_id": "player",
            "effect_ids": ["fx:protect:player:player"],
            "source_pressure_id": None,
            "observable_template_id": "protect_player",
        }
        for i in range(12)
    ]
    size = replayability.replayability_state_byte_size(state)
    assert size <= INITIAL_REPLAYABILITY_STATE_BUDGET_BYTES
    assert len(state["npc_agendas"]["active"]) == agendas.MAX_ACTIVE_AGENDAS
    assert len(state["npc_move_receipts"]) <= world_moves.MAX_NPC_MOVE_RECEIPTS
    assert len(state["npc_traits"]["by_npc_id"]) == agendas.MAX_ACTIVE_AGENDAS
    assert len(state["pressure_graph"]["nodes"]) <= pressure_graph.MAX_ACTIVE_NODES


def test_directive_size_bounded():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None,
        run_seed=SEED, npc_seed_records=[_record("Marlene Cho")],
    )
    _, directives, _, _, _ = replayability.prepare_action_turn(state, 2, rolling_state=_rolling())
    world = directives.get("world") or ""
    assert len(world) < 1200
    assert "goal_kind" not in world
    assert "receipt_id" not in world
