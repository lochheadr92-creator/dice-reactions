"""Seeded Living Cast scenario — deterministic turn-2 move preflight."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import living_cast_seeded_scenario as proof  # noqa: E402
import npc_world_moves as moves  # noqa: E402
import replayability  # noqa: E402


def test_proof_fixture_single_npc_and_stable_id():
    state = proof.build_proof_replayability_state()
    assert len(state["npc_agendas"]["active"]) == 1
    ag = state["npc_agendas"]["active"][0]
    assert ag["npc_id"] == proof.proof_canonical_npc_id()
    assert ag["agenda_id"] == proof.proof_agenda_id()
    assert ag["goal_kind"] == "secure_resources"


def test_preflight_passes_with_single_dominant_gather():
    report = proof.run_move_preflight(turn_number=2)
    assert report["preflight_pass"] is True
    assert report["candidate_count"] == 1
    assert report["winner"]["move_kind"] == "gather"
    assert report["winner"]["target_type"] == "pressure"
    assert report["winner"]["target_id"] == proof.PROOF_RESOURCE_PRESSURE_ID
    assert report["relationship_contributes_to_intended_score"] is False
    assert report["score_margin_over_runner_up"] >= 0
    assert report["expected_pressure_delta"] == -3
    assert report["intended_effect_direction"] == "decrease"
    assert report["drift_checks"]["winner_unchanged_under_drift"] is True


def test_preflight_score_table_documents_components():
    report = proof.run_move_preflight()
    row = report["candidate_score_table"][0]
    assert row["components"]["relationship_contributes"] is False
    assert row["components"]["total"] == row["score"]
    assert row["score"] == moves.TIER_PRIORITY["hero"] + 20


def test_turn2_prepare_commits_intended_move():
    rb = proof.build_proof_replayability_state()
    rolling = proof.build_proof_rolling_state()
    rb_out, _, diag, _, cast = replayability.prepare_action_turn(rb, 2, rolling_state=rolling)
    assert diag.get("npc_move_receipt_emitted") is True
    assert diag.get("npc_move_kind") == "gather"
    assert rb_out["npc_move_receipts"]
    assert rb_out["npc_move_receipts"][-1]["target_id"] == proof.PROOF_RESOURCE_PRESSURE_ID
    assert "engine_world_events" not in (cast or {})


def test_neutral_actions_not_required_for_selection():
    """Engine-owned state alone must dominate; keywords are not used."""
    report = proof.run_move_preflight()
    assert report["recommended_neutral_actions"]
    move, _ = moves.select_npc_move(
        proof.PROOF_RUN_SEED,
        proof.build_proof_replayability_state()["npc_agendas"],
        proof.build_proof_rolling_state(),
        proof.build_proof_replayability_state(),
        proof.build_proof_replayability_state()["identity"],
        2,
    )
    assert move and move["move_kind"] == "gather"


def test_deviation_taxonomy_classification():
    preflight = proof.run_move_preflight()
    cause, _ = proof.diagnose_move_selection_deviation(
        preflight,
        {"state_lineage_captured": False},
    )
    assert cause == proof.MoveSelectionDeviation.UNVERIFIED

    cause2, _ = proof.diagnose_move_selection_deviation(
        preflight,
        {
            "state_lineage_captured": True,
            "selection_inputs_hash": preflight["selection_inputs_hash"],
            "winner": {"move_kind": "pressure"},
        },
    )
    assert cause2 == proof.MoveSelectionDeviation.SELECTION_IMPLEMENTATION_DEFECT


def test_sampling_provenance_audit():
    rows = proof.collect_sampling_provenance()
    by_name = {r["parameter"]: r for r in rows}
    assert by_name["temperature"]["pinned"] == "PINNED_IN_CONFIG"
    assert by_name["temperature"]["env_var"] == "DEFAULT_TEMPERATURE"
    assert by_name["top_p"]["pinned"] == "INHERITED_PROVIDER_DEFAULT"
    assert by_name["provider_seed"]["pinned"] == "NOT_SENT"


def test_preflight_score_table_includes_all_candidates():
    report = proof.run_move_preflight()
    assert len(report["candidate_score_table"]) == report["candidate_count"]
    assert report["truncated_candidate_count"] <= report["candidate_count"]


def test_live_gate_manifest_engine_seed_not_sampling_seed():
    manifest = proof.live_gate_manifest()
    assert manifest["engine_run_seed"] == proof.PROOF_RUN_SEED
    assert manifest["model_sampling_seed"] is None
    assert manifest["preflight"]["preflight_pass"] is True


def test_relationship_shift_does_not_change_gather_winner():
    rb = proof.build_proof_replayability_state()
    rolling = proof.build_proof_rolling_state()
    rolling["relationship_vectors"][0]["trust"] = -40
    rolling["relationship_vectors"][0]["resentment"] = 90
    move, cands = moves.select_npc_move(
        proof.PROOF_RUN_SEED, rb["npc_agendas"], rolling, rb, rb["identity"], 2
    )
    assert len(cands) == 1
    assert move["move_kind"] == "gather"