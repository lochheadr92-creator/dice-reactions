"""Living Cast §11–17 — relationship order, liveness, atomic bundles, provenance."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import gateway  # noqa: E402
import living_cast_provenance as provenance  # noqa: E402
import npc_agendas as agendas  # noqa: E402
import npc_liveness  # noqa: E402
import npc_world_moves as moves  # noqa: E402
import player_api  # noqa: E402
import relationships as rel  # noqa: E402
import replayability  # noqa: E402
import server  # noqa: E402

SEED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _record(name: str, slot: int = 0) -> dict:
    return {"name": name, "source_type": "seed_record", "source_slot": slot}


def _rolling(name: str = "Marlene Cho", **extra) -> dict:
    base = {
        "scene": "dock warehouse",
        "npcs": [{"name": name, "stance": "ally", "last_seen": "dock"}],
        "relationship_vectors": [
            {
                "name": name,
                "trust": 10,
                "loyalty": 30,
                "fear": 0,
                "resentment": 12,
                "state": "neutral",
            }
        ],
        "faction_pressure": [{"name": "Syndicate", "ticks": {"suspicion": 0, "goodwill": 0}}],
    }
    base.update(extra)
    return base


def _rb(*names: str) -> dict:
    records = [_record(n, i) for i, n in enumerate(names)]
    state, _ = replayability.init_new_story(
        genre="noir",
        role="d",
        tone="t",
        difficulty="standard",
        scenario_id=None,
        custom_premise=None,
        custom_world_setup=None,
        run_seed=SEED,
        npc_seed_records=records,
    )
    return state


def _trust_minus_five_effect(name: str) -> dict:
    return {
        "effect_id": "fx:test:relationship_delta:player:trust",
        "effect_type": "relationship_delta",
        "target_id": name,
        "target_name": name,
        "dimension": "trust",
        "delta": -5,
        "defer_finalize": True,
    }


class _Parsed:
    def __init__(self, narrative: str = "", rolling_state: dict | None = None):
        self.narrative = narrative
        self.rolling_state = rolling_state or {}


# --------------------------------------------------------------------------- §11
def test_trust_minus_five_finishes_exactly_from_pre_effect_value():
    rb = _rb("Marlene Cho")
    rolling = _rolling("Marlene Cho")
    merged = copy.deepcopy(rolling)
    prior = copy.deepcopy(rolling)
    rel.update_relationship_calculus(_Parsed("Quiet turn."), prior, merged, "wait", 2)
    post_calc_trust = merged["relationship_vectors"][0]["trust"]

    rb["frozen_npc_move"] = {
        "receipt_id": "npc-move-test-trust",
        "effects": [_trust_minus_five_effect("Marlene Cho")],
    }
    rb, _ = replayability.finalize_living_cast_relationships(rb, merged, 2)
    final_trust = merged["relationship_vectors"][0]["trust"]
    assert final_trust == post_calc_trust - 5


def test_post_generation_calculus_cannot_erase_lc_move_effect():
    rb = _rb("Marlene Cho")
    rolling = _rolling("Marlene Cho")
    working, prepared = moves.commit_npc_move(
        {
            "receipt_id": "npc-move-erase-test",
            "move_kind": "withdraw",
            "target_type": "location",
            "target_id": moves._location_id(rolling),
            "npc_id": rb["npc_agendas"]["active"][0]["npc_id"],
            "agenda_id": rb["npc_agendas"]["active"][0]["agenda_id"],
        },
        rb["npc_agendas"]["active"][0],
        rolling,
        rb,
        SEED,
        2,
    )
    assert prepared
    merged = copy.deepcopy(working)
    rel.update_relationship_calculus(_Parsed("Silence."), working, merged, "wait", 2)
    rb["frozen_npc_move"] = prepared
    rb, _ = replayability.finalize_living_cast_relationships(rb, merged, 2)
    trust = merged["relationship_vectors"][0]["trust"]
    assert trust == pytest.approx(working["relationship_vectors"][0]["trust"] * 0.96 - 3, abs=1)


def test_post_generation_calculus_cannot_duplicate_lc_move_effect():
    rb = _rb("Marlene Cho")
    rolling = _rolling("Marlene Cho")
    merged = copy.deepcopy(rolling)
    prior = copy.deepcopy(rolling)
    rel.update_relationship_calculus(_Parsed(""), prior, merged, "wait", 2)
    rb["frozen_npc_move"] = {
        "receipt_id": "npc-move-dup-test",
        "effects": [_trust_minus_five_effect("Marlene Cho")],
    }
    rb, _ = replayability.finalize_living_cast_relationships(rb, merged, 2)
    once = merged["relationship_vectors"][0]["trust"]
    rb, _ = replayability.finalize_living_cast_relationships(rb, merged, 2)
    assert merged["relationship_vectors"][0]["trust"] == once


def test_decay_applies_only_once_with_lc_finalize():
    rb = _rb("Marlene Cho")
    rolling = _rolling("Marlene Cho")
    rolling["relationship_vectors"][0]["trust"] = 50
    start_trust = rolling["relationship_vectors"][0]["trust"]
    prior = copy.deepcopy(rolling)
    merged = copy.deepcopy(rolling)
    rel.update_relationship_calculus(_Parsed(""), prior, merged, "wait", 2)
    decayed_once = merged["relationship_vectors"][0]["trust"]
    assert decayed_once < start_trust
    rb["frozen_npc_move"] = {
        "receipt_id": "npc-move-decay-test",
        "effects": [_trust_minus_five_effect("Marlene Cho")],
    }
    replayability.finalize_living_cast_relationships(rb, merged, 2)
    assert merged["relationship_vectors"][0]["trust"] == decayed_once - 5


def test_lc_threshold_creates_one_effect_receipt():
    rb = _rb("Marlene Cho")
    rolling = _rolling("Marlene Cho")
    rolling["relationship_vectors"][0].update(
        {"trust": -40, "loyalty": 10, "resentment": 65, "state": "resentful"}
    )
    merged = copy.deepcopy(rolling)
    rel.update_relationship_calculus(_Parsed(""), rolling, merged, "wait", 2)
    rb["frozen_npc_move"] = {
        "receipt_id": "npc-move-threshold",
        "effects": [
            {
                "effect_id": "fx:test:relationship_delta:player:resentment",
                "effect_type": "relationship_delta",
                "target_name": "Marlene Cho",
                "dimension": "resentment",
                "delta": 10,
                "defer_finalize": True,
            }
        ],
    }
    rb, _ = replayability.finalize_living_cast_relationships(rb, merged, 2)
    receipts = rb.get("relationship_effect_receipts") or []
    assert len(receipts) == 1
    assert receipts[0]["after_state"] == "betrayal_risk"


def test_legacy_threshold_creates_no_lc_effect_receipt():
    prior = _rolling("Marlene Cho")
    prior["relationship_vectors"][0].update(
        {"trust": -30, "loyalty": 15, "resentment": 50, "state": "resentful"}
    )
    merged = copy.deepcopy(prior)
    rel.update_relationship_calculus(
        _Parsed("Marlene Cho betrays you and sells you out."),
        prior,
        merged,
        "betray",
        2,
    )
    rb = _rb("Marlene Cho")
    rb, _ = replayability.finalize_living_cast_relationships(rb, merged, 2)
    assert not rb.get("relationship_effect_receipts")


def test_lc_finalize_retry_same_final_vector():
    rb = _rb("Marlene Cho")
    merged = copy.deepcopy(_rolling("Marlene Cho"))
    rel.update_relationship_calculus(_Parsed(""), merged, merged, "wait", 2)
    rb["frozen_npc_move"] = {
        "receipt_id": "npc-move-retry",
        "effects": [_trust_minus_five_effect("Marlene Cho")],
    }
    rb1, _ = replayability.finalize_living_cast_relationships(rb, merged, 2)
    vec1 = copy.deepcopy(merged["relationship_vectors"])
    merged2 = copy.deepcopy(_rolling("Marlene Cho"))
    rel.update_relationship_calculus(_Parsed(""), merged2, merged2, "wait", 2)
    rb2 = copy.deepcopy(rb)
    rb2["lc_relationship_applied_receipt_id"] = None
    rb2["frozen_npc_move"] = rb["frozen_npc_move"]
    replayability.finalize_living_cast_relationships(rb2, merged2, 2)
    assert merged["relationship_vectors"] == vec1
    assert merged2["relationship_vectors"] == vec1


def test_unrelated_relationship_rows_unchanged():
    rb = _rb("Marlene Cho")
    rolling = _rolling("Marlene Cho")
    rolling["relationship_vectors"].append(
        {
            "name": "Greg Kane",
            "trust": 5,
            "loyalty": 20,
            "fear": 0,
            "resentment": 0,
            "state": "neutral",
        }
    )
    prior = copy.deepcopy(rolling)
    merged = copy.deepcopy(rolling)
    rel.update_relationship_calculus(_Parsed(""), prior, merged, "wait", 2)
    greg_after_calculus = json.dumps(merged["relationship_vectors"][1], sort_keys=True)
    rb["frozen_npc_move"] = {
        "receipt_id": "npc-move-iso",
        "effects": [_trust_minus_five_effect("Marlene Cho")],
    }
    replayability.finalize_living_cast_relationships(rb, merged, 2)
    assert json.dumps(merged["relationship_vectors"][1], sort_keys=True) == greg_after_calculus


# --------------------------------------------------------------------------- §12
def test_dead_npc_cannot_move():
    rb = _rb("Marlene Cho")
    rolling = _rolling("Marlene Cho", deceased=["Marlene Cho"])
    move, cands = moves.select_npc_move(SEED, rb["npc_agendas"], rolling, rb, rb["identity"], 2)
    assert move is None
    assert not cands


def test_dead_npc_cannot_receive_new_agenda():
    rolling = _rolling("Marlene Cho", deceased=["Marlene Cho"])
    state = agendas.seed_agendas_from_npcs(SEED, [_record("Marlene Cho")], rolling_state=rolling)
    assert not state["active"]


def test_dead_target_makes_move_infeasible():
    rb = _rb("Marlene Cho", "Greg Kane")
    rolling = _rolling("Marlene Cho")
    rolling["npcs"].append({"name": "Greg Kane", "stance": "dead", "next_move": "deceased"})
    rolling["deceased"] = ["Greg Kane"]
    assert not npc_liveness.is_target_valid(
        "npc",
        "npc-dead",
        actor_npc_id=rb["npc_agendas"]["active"][0]["npc_id"],
        rolling=rolling,
        replayability_state=rb,
    )


def test_destroyed_location_cannot_be_fortified():
    rb = _rb("Marlene Cho")
    rolling = _rolling("Marlene Cho")
    loc_id = moves._location_id(rolling)
    rolling["object_locations"] = [
        {"name": rolling["scene"], "status": "destroyed"},
    ]
    assert not npc_liveness.is_location_target_valid(loc_id, rolling)


def test_removed_faction_cannot_be_negotiated():
    rb = _rb("Marlene Cho")
    rolling = _rolling("Marlene Cho")
    fac_id = moves._faction_id("Syndicate")
    rolling["faction_pressure"][0]["removed"] = True
    assert not npc_liveness.is_faction_target_valid(fac_id, rolling)


def test_stale_memory_cannot_revive_dead_actor():
    rb = _rb("Marlene Cho")
    rolling = _rolling("Marlene Cho", deceased=["Marlene Cho"])
    rolling["npc_memory"] = [
        {"name": "Marlene Cho", "remembers": [{"since_turn": 99, "summary": "recent"}]}
    ]
    assert not npc_liveness.is_actor_eligible(
        rb["npc_agendas"]["active"][0]["npc_id"],
        rb["npc_agendas"]["active"][0],
        rolling,
    )[0]


def test_invalid_actor_creates_no_receipt_or_echo():
    rb = _rb("Marlene Cho")
    rolling = _rolling("Marlene Cho", deceased=["Marlene Cho"])
    _, _, diag, _, _ = replayability.prepare_action_turn(rb, 2, rolling_state=rolling)
    assert not diag.get("npc_move_receipt_emitted")
    assert not rb.get("npc_move_receipts")


# --------------------------------------------------------------------------- §13
def test_defect_persists_all_deltas_together():
    rb = _rb("Marlene Cho")
    ag = rb["npc_agendas"]["active"][0]
    ag.update({"goal_kind": "escape_danger", "breaking_fired": True, "status": "breaking"})
    rolling = _rolling("Marlene Cho")
    fac_before = copy.deepcopy(rolling["faction_pressure"][0]["ticks"])
    move = {
        "receipt_id": "npc-move-defect-bundle",
        "move_kind": "defect",
        "target_type": "faction",
        "target_id": moves._faction_id("Syndicate"),
        "npc_id": ag["npc_id"],
        "agenda_id": ag["agenda_id"],
    }
    out, prepared = moves.commit_npc_move(move, ag, rolling, rb, SEED, 2)
    assert prepared
    assert out["faction_pressure"][0]["ticks"]["suspicion"] == fac_before["suspicion"] + 1
    rel_effects = [e for e in prepared["effects"] if e.get("defer_finalize")]
    assert len(rel_effects) == 2


def test_partial_effect_failure_leaves_state_untouched():
    rb = _rb("Marlene Cho")
    ag = rb["npc_agendas"]["active"][0]
    rolling = _rolling("Marlene Cho")
    progress_before = ag["progress"]
    move = {
        "receipt_id": "npc-move-fail-bundle",
        "move_kind": "fortify",
        "target_type": "pressure",
        "target_id": "missing-pressure-node",
        "npc_id": ag["npc_id"],
        "agenda_id": ag["agenda_id"],
    }
    out, prepared = moves.commit_npc_move(move, ag, rolling, rb, SEED, 2)
    assert prepared is None
    assert out is rolling
    assert ag["progress"] == progress_before
    assert not rb.get("npc_move_receipts")


def test_no_receipt_after_partial_effect_failure():
    rb = _rb("Marlene Cho")
    ag = rb["npc_agendas"]["active"][0]
    rolling = _rolling("Marlene Cho")
    move = {
        "receipt_id": "npc-move-no-receipt",
        "move_kind": "gather",
        "target_type": "pressure",
        "target_id": "missing",
        "npc_id": ag["npc_id"],
        "agenda_id": ag["agenda_id"],
    }
    moves.commit_npc_move(move, ag, rolling, rb, SEED, 2)
    assert not rb.get("npc_move_receipts")


def test_effect_order_is_deterministic():
    rb = _rb("Marlene Cho")
    ag = rb["npc_agendas"]["active"][0]
    ag.update({"goal_kind": "escape_danger", "breaking_fired": True, "status": "breaking"})
    rolling = _rolling("Marlene Cho")
    move = {
        "receipt_id": "npc-move-order",
        "move_kind": "defect",
        "target_type": "faction",
        "target_id": moves._faction_id("Syndicate"),
        "npc_id": ag["npc_id"],
        "agenda_id": ag["agenda_id"],
    }
    bundle, _ = moves.compute_effect_bundle(move, ag, rolling, rb, 2)
    ids = [e["effect_id"] for e in bundle]
    assert ids == sorted(ids)


def test_duplicate_bundle_commit_is_idempotent():
    rb = _rb("Marlene Cho")
    rolling = _rolling("Marlene Cho")
    move, _ = moves.select_npc_move(SEED, rb["npc_agendas"], rolling, rb, rb["identity"], 2)
    ag = agendas.get_agenda_by_npc_id(rb["npc_agendas"], move["npc_id"])
    moves.commit_npc_move(move, ag, rolling, rb, SEED, 2)
    again, prepared = moves.commit_npc_move(move, ag, rolling, rb, SEED, 2)
    assert prepared is None
    assert len(rb["npc_move_receipts"]) == 1


# --------------------------------------------------------------------------- §14
def test_receipt_cap_hard_bound_despite_echo_reference():
    rb = _rb("Marlene Cho")
    rb["consequence_echoes"]["scheduled"] = [
        {
            "id": "echo-1",
            "source_event_id": "npc-move-keep",
            "kind": "retaliation",
            "source_provenance": {
                "npc_id": "npc-x",
                "agenda_id": "agenda-x",
                "move_kind": "pressure",
                "target_type": "player",
                "target_id": "player",
            },
        }
    ]
    for i in range(moves.MAX_NPC_MOVE_RECEIPTS + 6):
        moves.append_npc_move_receipt(
            rb,
            {
                "version": 1,
                "receipt_id": f"npc-move-{i:03d}",
                "receipt_type": "npc_move_committed",
                "turn": 2,
                "npc_id": "npc-x",
                "agenda_id": "agenda-x",
                "move_kind": "pressure",
                "target_type": "player",
                "target_id": "player",
                "effect_ids": [],
            },
        )
    assert len(rb["npc_move_receipts"]) == moves.MAX_NPC_MOVE_RECEIPTS
    echo = rb["consequence_echoes"]["scheduled"][0]
    assert echo.get("source_provenance")


def test_malformed_receipt_version_still_dedupes_by_id():
    rb = _rb("Marlene Cho")
    receipt = {"version": 99, "receipt_id": "npc-move-bad", "receipt_type": "npc_move_committed"}
    assert moves.append_npc_move_receipt(rb, receipt) is True
    assert moves.append_npc_move_receipt(rb, receipt) is False


def test_player_payload_exposes_no_receipt_fields():
    rb = _rb("Marlene Cho")
    rb["npc_move_receipts"] = [{"receipt_id": "secret", "effects": [{"delta": -5}]}]
    session = {"state": {}, "replayability_state": rb}
    payload = player_api.build_player_session(session)
    dumped = json.dumps(payload)
    assert "receipt_id" not in dumped
    assert "npc_move_receipts" not in dumped


# --------------------------------------------------------------------------- §15
def test_unknown_source_kind_cannot_schedule_echo():
    assert not provenance.validate_provenance(
        {"source_kind": "raw_narrative_guess", "source_event_id": "evt-1"}
    )


def test_missing_source_id_rejected():
    assert not provenance.validate_provenance({"source_kind": "npc_world_move"})


def test_allowlisted_source_works_once():
    src = {
        "source_kind": "npc_world_move",
        "source_event_id": "npc-move-abc",
        "echo_kind": "retaliation",
        "label": "pressure",
    }
    assert provenance.validate_provenance(src)
    norm = provenance.normalize_provenance(src, 2)
    assert norm and norm["source_id"] == "npc-move-abc"


def test_provenance_rejects_narrative_payload():
    assert not provenance.validate_provenance(
        {
            "source_kind": "npc_world_move",
            "source_event_id": "evt-1",
            "narrative": "The player said hello",
        }
    )


# --------------------------------------------------------------------------- §16
def test_gateway_detects_dead_actor_in_narrative():
    prior = _rolling("Marlene Cho", deceased=["Marlene Cho"])
    parsed = _Parsed("Marlene Cho steps forward and speaks to you.")
    reasons = gateway.detect_prose_contradictions(prior, parsed, "wait")
    assert reasons


# --------------------------------------------------------------------------- §17
def test_npc_move_does_not_mutate_unrelated_state():
    rb = _rb("Marlene Cho")
    rolling = _rolling("Marlene Cho")
    rolling["secret_registry"] = [{"id": "sec-1", "status": "hidden"}]
    rolling["delayed_consequences"] = [{"description": "storm", "turns_remaining": 3}]
    secrets_before = json.dumps(rolling.get("secret_registry"), sort_keys=True)
    delayed_before = json.dumps(rolling.get("delayed_consequences"), sort_keys=True)
    move, _ = moves.select_npc_move(SEED, rb["npc_agendas"], rolling, rb, rb["identity"], 2)
    if move:
        ag = agendas.get_agenda_by_npc_id(rb["npc_agendas"], move["npc_id"])
        out, _ = moves.commit_npc_move(move, ag, rolling, rb, SEED, 2)
        assert json.dumps(out.get("secret_registry"), sort_keys=True) == secrets_before
        assert json.dumps(out.get("delayed_consequences"), sort_keys=True) == delayed_before


def test_living_cast_state_metrics_bounded():
    import living_cast_bounded_fixtures as cap_fixtures

    rb = cap_fixtures.build_replayability_state_at_all_caps()
    metrics = replayability.living_cast_state_metrics(rb)
    assert metrics["active_agendas"]["count"] == 12
    assert metrics["full_replayability_state"]["bytes"] <= replayability.REPLAYABILITY_STATE_BUDGET_BYTES