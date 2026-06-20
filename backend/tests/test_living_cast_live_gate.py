"""Deterministic tests for Living Cast live-gate harness policy."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import living_cast_live_gate as gate  # noqa: E402
import living_cast_seeded_scenario as proof  # noqa: E402
import scenarios  # noqa: E402
import server  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_live_gate_env(monkeypatch):
    monkeypatch.delenv(gate.LIVE_GATE_ENV_VAR, raising=False)


def test_proof_scenario_hidden_when_gate_disabled(monkeypatch):
    monkeypatch.delenv(gate.LIVE_GATE_ENV_VAR, raising=False)
    assert scenarios.get_scenario(proof.PROOF_SCENARIO_ID) is None
    ids = {s["id"] for s in scenarios.get_scenarios()}
    assert proof.PROOF_SCENARIO_ID not in ids


def test_proof_scenario_loadable_when_gate_enabled(monkeypatch):
    monkeypatch.setenv(gate.LIVE_GATE_ENV_VAR, "true")
    loaded = scenarios.get_scenario(proof.PROOF_SCENARIO_ID)
    assert loaded is not None
    assert loaded["id"] == proof.PROOF_SCENARIO_ID
    fixture = gate.load_proof_fixture()
    assert fixture["run_seed"] == proof.PROOF_RUN_SEED


def test_public_scenario_list_never_includes_proof(monkeypatch):
    monkeypatch.setenv(gate.LIVE_GATE_ENV_VAR, "true")
    ids = {s["id"] for s in scenarios.get_scenarios()}
    assert proof.PROOF_SCENARIO_ID not in ids


def test_new_story_request_has_no_run_seed_field():
    fields = set(server.NewStoryRequest.model_fields.keys())
    assert "run_seed" not in fields


def test_public_story_creation_cannot_select_proof_scenario(monkeypatch):
    monkeypatch.delenv(gate.LIVE_GATE_ENV_VAR, raising=False)
    assert scenarios.get_scenario(proof.PROOF_SCENARIO_ID) is None


def test_haiku_primary_response_accepted():
    meta = {
        "model_used": gate.LIVE_GATE_PRIMARY_MODEL,
        "model_requested": gate.LIVE_GATE_PRIMARY_MODEL,
        "fallback_events": [],
        "attempts_per_model": {gate.LIVE_GATE_PRIMARY_MODEL: 1},
    }
    result = gate.classify_generation_meta(meta)
    assert result["verdict"] == "PRIMARY_OBSERVED"
    assert result["primary_observed"] is True
    assert result["fallback_triggered"] is False


def test_fallback_attempt_detected_and_cannot_pass():
    meta = {
        "model_used": "anthropic/claude-3-5-sonnet",
        "model_requested": gate.LIVE_GATE_PRIMARY_MODEL,
        "fallback_events": [
            {"from": gate.LIVE_GATE_PRIMARY_MODEL, "to": "anthropic/claude-3-5-sonnet", "reason": "timeout"}
        ],
        "attempts_per_model": {
            gate.LIVE_GATE_PRIMARY_MODEL: 2,
            "anthropic/claude-3-5-sonnet": 1,
        },
    }
    result = gate.classify_generation_meta(meta)
    assert result["verdict"] == "INCONCLUSIVE"
    assert gate.INCONCLUSIVE_FALLBACK in result["detail"]
    aggregate = gate.evaluate_haiku_gate([meta])
    assert aggregate["gate_pass"] is False


def test_fallback_output_cannot_produce_pass():
    sonnet_meta = {
        "model_used": "gryphe/mythomax-l2-13b",
        "model_requested": gate.LIVE_GATE_PRIMARY_MODEL,
        "fallback_events": [{"from": "anthropic/claude-3-5-sonnet", "to": "gryphe/mythomax-l2-13b"}],
        "attempts_per_model": {"gryphe/mythomax-l2-13b": 1},
    }
    assert gate.evaluate_haiku_gate([sonnet_meta])["gate_pass"] is False


def test_model_identifier_persisted_in_diagnostic_manifest():
    ledger = gate.AttemptLedger()
    ledger.record_logical_generation(
        {
            "model_used": gate.LIVE_GATE_PRIMARY_MODEL,
            "attempts_per_model": {gate.LIVE_GATE_PRIMARY_MODEL: 1},
            "fallback_events": [],
        }
    )
    manifest = gate.build_diagnostic_manifest(ledger)
    assert manifest["attempt_ledger"]["models_observed"] == [gate.LIVE_GATE_PRIMARY_MODEL]
    assert manifest["primary_model_gate"] == gate.LIVE_GATE_PRIMARY_MODEL


def test_no_fallback_model_mislabeled_as_haiku():
    meta = {
        "model_used": gate.LIVE_GATE_PRIMARY_MODEL,
        "model_requested": gate.LIVE_GATE_PRIMARY_MODEL,
        "fallback_events": [
            {"from": gate.LIVE_GATE_PRIMARY_MODEL, "to": "anthropic/claude-3-5-sonnet", "reason": "rate_limit"}
        ],
        "attempts_per_model": {
            gate.LIVE_GATE_PRIMARY_MODEL: 2,
            "anthropic/claude-3-5-sonnet": 1,
        },
    }
    result = gate.classify_generation_meta(meta)
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["fallback_triggered"] is True


def test_retry_counters_distinguish_logical_and_physical():
    ledger = gate.AttemptLedger(budget=20)
    ledger.record_logical_generation(
        {
            "attempts_per_model": {gate.LIVE_GATE_PRIMARY_MODEL: 2},
            "fallback_events": [],
        }
    )
    ledger.record_logical_generation(
        {
            "attempts_per_model": {gate.LIVE_GATE_PRIMARY_MODEL: 1},
            "fallback_events": [],
        },
        validation_retry=True,
    )
    summary = ledger.to_dict()
    assert summary["logical_generations"] == 2
    assert summary["validation_retries"] == 1
    assert summary["physical_outbound_attempts"] == 3


def test_provider_seed_reports_not_sent():
    rows = proof.collect_sampling_provenance()
    by_name = {r["parameter"]: r for r in rows}
    assert by_name["provider_seed"]["pinned"] == "NOT_SENT"
    assert by_name["top_p"]["pinned"] == "INHERITED_PROVIDER_DEFAULT"


def test_score_preflight_still_proves_turn2_gather():
    report = proof.run_move_preflight(turn_number=2)
    assert report["preflight_pass"] is True
    assert report["winner"]["move_kind"] == "gather"
    assert report["candidate_count"] >= 1
    assert len(report["candidate_score_table"]) == report["candidate_count"]


def test_production_scoring_unchanged_for_fixture():
    """Fixture uses production enumerate/select paths — no parallel scorer."""
    report = proof.run_move_preflight()
    rb = proof.build_proof_replayability_state()
    rolling = proof.build_proof_rolling_state()
    import npc_world_moves as moves  # noqa: E402

    production_all = moves.enumerate_move_candidates(
        proof.PROOF_RUN_SEED,
        rb["npc_agendas"],
        rolling,
        rb,
        rb["identity"],
        2,
    )
    assert len(report["candidate_score_table"]) == len(production_all)
    assert report["winner"]["score"] == production_all[0]["score"]


def test_outbound_budget_aborts_before_exceeding():
    ledger = gate.AttemptLedger(budget=3)
    ledger.record_logical_generation(
        {"attempts_per_model": {gate.LIVE_GATE_PRIMARY_MODEL: 2}, "fallback_events": []}
    )
    ledger.record_logical_generation(
        {"attempts_per_model": {gate.LIVE_GATE_PRIMARY_MODEL: 2}, "fallback_events": []}
    )
    assert ledger.aborted is True
    assert ledger.physical_outbound_attempts == 4


def test_load_proof_fixture_requires_gate(monkeypatch):
    with pytest.raises(PermissionError):
        gate.load_proof_fixture()
    monkeypatch.setenv(gate.LIVE_GATE_ENV_VAR, "1")
    assert gate.load_proof_fixture()["scenario_id"] == proof.PROOF_SCENARIO_ID