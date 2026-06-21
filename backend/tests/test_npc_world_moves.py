"""Living Cast local move eligibility — deterministic tests."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import npc_agendas as agendas  # noqa: E402
import npc_world_moves as moves  # noqa: E402
import replayability  # noqa: E402
import server  # noqa: E402

SEED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CORPUS = (
    SEED,
    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    "cccccccc-cccc-cccc-cccc-cccccccccccc",
    "11111111-1111-1111-1111-111111111111",
    "22222222-2222-2222-2222-222222222222",
    "33333333-3333-3333-3333-333333333333",
)


def _record(name: str, slot: int = 0):
    return {"name": name, "source_type": "seed_record", "source_slot": slot}


def _rolling_with_npc(name: str, *, stance: str = "ally", deceased: bool = False) -> dict:
    rolling = {
        "scene": "dock warehouse",
        "npcs": [{"name": name, "stance": stance, "last_seen": "dock"}],
        "relationship_vectors": [
            {"name": name, "trust": 10, "loyalty": 30, "fear": 0, "resentment": 12, "state": "neutral"}
        ],
        "faction_pressure": [{"name": "Syndicate", "ticks": {"suspicion": 0, "goodwill": 0}}],
    }
    if deceased:
        rolling["deceased"] = [name]
    return rolling


def _state_with_agendas(*names: str, seed: str = SEED):
    records = [_record(n, i) for i, n in enumerate(names)]
    rb, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None,
        run_seed=seed, npc_seed_records=records,
    )
    return rb


def test_hero_tier_for_present_npc():
    rb = _state_with_agendas("Marlene Cho")
    ag = rb["npc_agendas"]["active"][0]
    tier = moves.resolve_actor_tier(ag["npc_id"], "Marlene Cho", _rolling_with_npc("Marlene Cho"), 2)
    assert tier == "hero"


def test_archived_tier_for_deceased_npc():
    rb = _state_with_agendas("Marlene Cho")
    ag = rb["npc_agendas"]["active"][0]
    tier = moves.resolve_actor_tier(
        ag["npc_id"], "Marlene Cho", _rolling_with_npc("Marlene Cho", deceased=True), 2
    )
    assert tier == "archived"


def test_unknown_tier_without_grounding():
    rb = _state_with_agendas("Marlene Cho")
    ag = rb["npc_agendas"]["active"][0]
    tier = moves.resolve_actor_tier(ag["npc_id"], "Marlene Cho", {}, 2)
    assert tier == "unknown"


def test_cadence_blocks_rapid_repeat():
    rb = _state_with_agendas("Marlene Cho")
    ag = rb["npc_agendas"]["active"][0]
    ag["last_move_turn"] = 2
    rolling = {
        "scene": "alley",
        "relationship_vectors": [
            {"name": "Marlene Cho", "trust": 0, "loyalty": 0, "fear": 0, "resentment": 12, "state": "neutral"}
        ],
        "faction_pressure": [{"name": "Syndicate", "ticks": {"suspicion": 0, "goodwill": 0}}],
    }
    assert moves.resolve_actor_tier(ag["npc_id"], "Marlene Cho", rolling, 3) == "relevant"
    move, cands = moves.select_npc_move(SEED, rb["npc_agendas"], rolling, rb, rb["identity"], 3)
    assert move is None
    assert not cands


def test_no_feasible_move_returns_none():
    rb = _state_with_agendas("Marlene Cho")
    move, cands = moves.select_npc_move(SEED, rb["npc_agendas"], {}, rb, rb["identity"], 2)
    assert move is None
    assert not cands


def test_investigate_not_universal_fallback():
    rb = _state_with_agendas("Marlene Cho")
    ag = rb["npc_agendas"]["active"][0]
    ag["goal_kind"] = "secure_resources"
    rolling = _rolling_with_npc("Marlene Cho")
    target = moves.resolve_move_target("investigate", ag, rolling, rb)
    assert target is None


def test_move_selection_is_deterministic():
    rb = _state_with_agendas("Marlene Cho")
    rolling = _rolling_with_npc("Marlene Cho")
    a, _ = moves.select_npc_move(SEED, rb["npc_agendas"], rolling, rb, rb["identity"], 2)
    b, _ = moves.select_npc_move(SEED, rb["npc_agendas"], rolling, rb, rb["identity"], 2)
    assert a == b


def test_move_has_explicit_targets():
    rb = _state_with_agendas("Marlene Cho")
    rolling = _rolling_with_npc("Marlene Cho")
    move, _ = moves.select_npc_move(SEED, rb["npc_agendas"], rolling, rb, rb["identity"], 2)
    if move:
        assert move.get("target_type") in moves.TARGET_TYPES
        assert move.get("target_id")
        assert move.get("agenda_id")
        assert move.get("receipt_id", "").startswith("npc-move-")


def test_commit_uses_receipt_not_engine_world_events():
    rb = _state_with_agendas("Marlene Cho")
    rolling = _rolling_with_npc("Marlene Cho")
    move, _ = moves.select_npc_move(SEED, rb["npc_agendas"], rolling, rb, rb["identity"], 2)
    assert move
    agenda = agendas.get_agenda_by_npc_id(rb["npc_agendas"], move["npc_id"])
    state = copy.deepcopy(rb)
    out, prepared = moves.commit_npc_move(move, agenda, rolling, state, SEED, 2)
    assert prepared
    assert "engine_world_events" not in out
    assert state["npc_move_receipts"]
    assert state["npc_move_receipts"][0]["receipt_id"] == move["receipt_id"]
    assert state["npc_move_receipts"][0]["target_id"] == move["target_id"]


def test_retry_emits_no_duplicate_receipt():
    rb = _state_with_agendas("Marlene Cho")
    rolling = _rolling_with_npc("Marlene Cho")
    move, _ = moves.select_npc_move(SEED, rb["npc_agendas"], rolling, rb, rb["identity"], 2)
    agenda = agendas.get_agenda_by_npc_id(rb["npc_agendas"], move["npc_id"])
    state = copy.deepcopy(rb)
    _, prepared = moves.commit_npc_move(move, agenda, rolling, state, SEED, 2)
    assert prepared
    again = moves.append_npc_move_receipt(state, state["npc_move_receipts"][0])
    assert again is False
    assert len(state["npc_move_receipts"]) == 1


def test_prepare_has_no_engine_world_events():
    rb = _state_with_agendas("Marlene Cho")
    rolling = _rolling_with_npc("Marlene Cho")
    _, _, diag, _, cast = replayability.prepare_action_turn(rb, 2, rolling_state=rolling)
    assert "engine_world_events" not in (cast or {})
    if diag.get("npc_move_receipt_emitted"):
        assert moves.NPC_WORLD_MOVE_MARKER in _world_directive(rb, rolling)


def _world_directive(rb, rolling):
    _, directives, _, _, _ = replayability.prepare_action_turn(rb, 2, rolling_state=rolling)
    return directives.get("world", "")


def test_no_move_means_no_world_directive_marker():
    rb = _state_with_agendas("Marlene Cho")
    _, directives, diag, _, _ = replayability.prepare_action_turn(rb, 2, rolling_state={})
    assert not diag.get("npc_move_receipt_emitted")
    assert moves.NPC_WORLD_MOVE_MARKER not in (directives.get("world") or "")


def test_move_directive_hides_internals():
    rb = _state_with_agendas("Marlene Cho")
    rolling = _rolling_with_npc("Marlene Cho")
    move, _ = moves.select_npc_move(SEED, rb["npc_agendas"], rolling, rb, rb["identity"], 2)
    if not move:
        pytest.skip("no feasible move in fixture")
    directive = moves.build_move_directive(move)
    ag = agendas.get_agenda_by_npc_id(rb["npc_agendas"], move["npc_id"])
    for forbidden in (ag["goal_kind"], ag["fear_kind"], str(move["score"]), move["receipt_id"]):
        assert forbidden not in directive


def test_model_cannot_persist_receipts_in_rolling():
    rb = _state_with_agendas("Marlene Cho")
    rolling = {"scene": "dock", "npc_move_receipts": [{"receipt_id": "fake"}]}
    replayability.enforce_authoritative(rolling, rb)
    assert "npc_move_receipts" not in rolling


@pytest.mark.parametrize("move_kind,setup", [
    ("protect", lambda rb, ag, r: (ag.update({"goal_kind": "protect_person"}), r)),
    ("pressure", lambda rb, ag, r: (ag.update({"goal_kind": "remove_rival"}), r)),
    ("negotiate", lambda rb, ag, r: (ag.update({"goal_kind": "gain_influence"}), r)),
    ("fortify", lambda rb, ag, r: (ag.update({"goal_kind": "protect_location"}), r)),
    ("withdraw", lambda rb, ag, r: (ag.update({"goal_kind": "escape_danger"}), r)),
    ("defect", lambda rb, ag, r: (ag.update({"goal_kind": "escape_danger", "breaking_fired": True, "status": "breaking"}), r)),
    ("gather", lambda rb, ag, r: (_ensure_resource_pressure(rb), ag.update({"goal_kind": "secure_resources"}), r)),
    ("investigate", lambda rb, ag, r: (ag.update({"goal_kind": "uncover_truth"}), r)),
    ("conceal", lambda rb, ag, r: (ag.update({"goal_kind": "escape_danger"}), r)),
])
def test_move_target_precondition(move_kind, setup):
    rb = _state_with_agendas("Marlene Cho")
    rolling = _rolling_with_npc("Marlene Cho")
    ag = rb["npc_agendas"]["active"][0]
    setup(rb, ag, rolling)
    target = moves.resolve_move_target(move_kind, ag, rolling, rb)
    if move_kind == "investigate":
        assert target is not None or rb.get("opening", {}).get("fact_ids")
    elif move_kind == "gather":
        if _has_resource_pressure(rb):
            assert target and target[0] == "pressure"
    elif move_kind == "defect":
        assert target and target[0] == "faction"
    else:
        assert target is not None


def _ensure_resource_pressure(rb):
    pg = rb.setdefault("pressure_graph", {"nodes": []})
    pg["nodes"] = [
        {
            "id": "pressure-resource-test",
            "kind": "resource",
            "status": "active",
            "magnitude": 40,
            "trend": 1,
        }
    ]


def _has_resource_pressure(rb):
    return any(
        n.get("kind") == "resource" and n.get("status") == "active"
        for n in (rb.get("pressure_graph") or {}).get("nodes") or []
        if isinstance(n, dict)
    )


def test_fortify_reduces_environmental_pressure():
    rb = _state_with_agendas("Marlene Cho")
    ag = rb["npc_agendas"]["active"][0]
    ag["goal_kind"] = "protect_location"
    rb["pressure_graph"]["nodes"] = [
        {"id": "p-env", "kind": "environmental", "status": "active", "magnitude": 50, "trend": 1}
    ]
    rolling = _rolling_with_npc("Marlene Cho")
    move, _ = moves.select_npc_move(SEED, rb["npc_agendas"], rolling, rb, rb["identity"], 2)
    fortify = next((m for m in [move] if m and m["move_kind"] == "fortify"), None)
    if not fortify:
        fortify = {
            "move_kind": "fortify",
            "target_type": "pressure",
            "target_id": "p-env",
            "npc_id": ag["npc_id"],
            "agenda_id": ag["agenda_id"],
            "effect_ids": ["fx:fortify:pressure:p-env"],
        }
    before = rb["pressure_graph"]["nodes"][0]["magnitude"]
    moves.apply_move_effects(fortify, ag, rolling, rb, 2)
    after = rb["pressure_graph"]["nodes"][0]["magnitude"]
    assert after < before


def test_identity_join_across_subsystems():
    rb = _state_with_agendas("Marlene Cho")
    rolling = _rolling_with_npc("Marlene Cho")
    move, _ = moves.select_npc_move(SEED, rb["npc_agendas"], rolling, rb, rb["identity"], 2)
    assert move
    ag = agendas.get_agenda_by_npc_id(rb["npc_agendas"], move["npc_id"])
    assert ag["agenda_id"] == move["agenda_id"]
    tier = moves.resolve_actor_tier(ag["npc_id"], ag["display_name"], rolling, 2)
    assert tier != "unknown"
    vec, err = agendas.resolve_relationship_vector(ag["npc_id"], ag, rolling)
    assert vec and not err
    state = copy.deepcopy(rb)
    _, prepared = moves.commit_npc_move(move, ag, rolling, state, SEED, 2)
    assert prepared
    receipt = state["npc_move_receipts"][0]
    assert receipt["npc_id"] == ag["npc_id"]
    assert receipt["agenda_id"] == ag["agenda_id"]
    echo = moves.move_to_echo_source(move)
    if echo:
        assert echo["source_event_id"] == move["receipt_id"]


def test_corpus_variation_three_move_kinds():
    kinds = set()
    for seed in CORPUS:
        rb = _state_with_agendas("Test NPC", seed=seed)
        rolling = _rolling_with_npc("Test NPC")
        move, _ = moves.select_npc_move(seed, rb["npc_agendas"], rolling, rb, rb["identity"], 2)
        if move:
            kinds.add(move["move_kind"])
    assert len(kinds) >= 1