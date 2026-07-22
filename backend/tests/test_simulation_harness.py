"""
Stage 6A — Headless Simulation Harness & Telemetry tests.

Deterministic-only (no `live` marker anywhere): the harness must never reach
an LLM provider, never consult unseeded randomness, and must emit valid,
bounded, reproducible telemetry.
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = BACKEND_DIR / "tools"
HARNESS_PATH = TOOLS_DIR / "simulate_world.py"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import simulate_world  # noqa: E402

OUTPUT_FILES = (
    "metrics.jsonl",
    "timeline.jsonl",
    "final_snapshot.json",
    "summary.json",
    "anomalies.json",
)

REQUIRED_METRIC_FIELDS = {
    "turn",
    "pressure_nodes_active",
    "pressure_created_cum",
    "pressure_resolved_cum",
    "pressure_creation_rate",
    "pressure_resolution_rate",
    "situations_active",
    "situations_resolved_cum",
    "situations_failed_cum",
    "situations_archived_cum",
    "situation_archive_count",
    "avg_situation_age",
    "avg_situation_lifetime",
    "active_world_events",
    "world_event_creation_rate",
    "world_event_resolution_rate",
    "average_world_event_age",
    "average_world_event_lifetime",
    "world_event_merge_count",
    "world_event_archive_count",
    "world_event_category_counts",
    "active_investigations",
    "active_evidence",
    "average_evidence_age",
    "case_completion_rate",
    "average_investigation_lifetime",
    "average_confidence",
    "unsolved_investigations",
    "cold_cases",
    "goals_active",
    "goals_completed_cum",
    "goals_failed_cum",
    "goals_abandoned_cum",
    "avg_goal_age",
    "avg_goal_lifetime",
    "goal_recreation_count",
    "npc_actions_active",
    "world_events_total",
    "world_events_appended_turn",
    "echoes_scheduled",
    "npc_memory_entries",
    "orphaned_goals",
    "orphaned_situations",
    "orphaned_world_events",
    "orphaned_evidence",
    "orphaned_investigations",
    "impossible_confidence_rows",
    "evidence_cycles",
    "duplicate_id_collections",
    "missing_source_event_id_rows",
    "prompt_leakage_hits",
    "state_bytes",
    "state_size_bytes",
    "state_within_budget",
    "budget_warnings",
    "collections_over_cap",
    "avg_pressure_lifetime",
    "pressure_decay_count",
}


# ---------------------------------------------------------------------------
# Shared 100-turn deterministic run (test mode).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def sim_run(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("sim_run_100")
    summary = simulate_world.run_simulation(
        turns=100, seed="harness-ci", out_dir=out_dir
    )
    return out_dir, summary


def _metrics_rows(out_dir: Path):
    lines = (out_dir / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# ---------------------------------------------------------------------------
# CLI + no-provider guarantees.
# ---------------------------------------------------------------------------
def test_cli_runs_and_writes_all_outputs(tmp_path):
    out_dir = tmp_path / "cli_run"
    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS_PATH),
            "--turns",
            "5",
            "--seed",
            "cli-seed",
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    for name in OUTPUT_FILES:
        assert (out_dir / name).exists(), f"missing output {name}"
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    # Fresh interpreter: the engine import chain must not have loaded any
    # provider/app module at all.
    assert summary["forbidden_modules_preloaded"] == []
    assert summary["forbidden_modules_imported_by_engine"] == []
    assert len(_metrics_rows(out_dir)) == 5


def test_no_llm_or_provider_calls(tmp_path):
    # conftest's autouse fixture patches gateway.invoke_llm to raise on ANY
    # call in the deterministic suite; a completed run therefore proves the
    # harness never reaches the provider seam.
    summary = simulate_world.run_simulation(
        turns=10, seed="no-llm", out_dir=tmp_path / "no_llm"
    )
    assert summary["config"]["turns"] == 10
    # The harness's own import-chain audit found nothing.
    assert simulate_world._FORBIDDEN_IMPORTED_BY_ENGINE == []


# ---------------------------------------------------------------------------
# Determinism.
# ---------------------------------------------------------------------------
def test_same_seed_produces_identical_outputs(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    summary_a = simulate_world.run_simulation(turns=30, seed="det", out_dir=dir_a)
    summary_b = simulate_world.run_simulation(turns=30, seed="det", out_dir=dir_b)
    assert summary_a["fingerprint"] == summary_b["fingerprint"]
    for name in ("summary.json", "metrics.jsonl", "timeline.jsonl",
                 "final_snapshot.json", "anomalies.json"):
        assert (dir_a / name).read_bytes() == (dir_b / name).read_bytes(), (
            f"{name} not byte-identical for identical seeds"
        )


def test_different_seed_allowed_without_ambient_randomness(tmp_path, monkeypatch):
    # Any consultation of process-global randomness or uuid4 is a
    # determinism violation — the engine must draw only from seeded hashes.
    def _forbidden(*_a, **_k):  # pragma: no cover - failure path
        raise AssertionError("unseeded randomness consulted during simulation")

    for name in ("random", "randint", "choice", "uniform", "shuffle", "randrange"):
        monkeypatch.setattr(random, name, _forbidden)
    monkeypatch.setattr(uuid, "uuid4", _forbidden)

    summary_a = simulate_world.run_simulation(
        turns=15, seed="seed-a", out_dir=tmp_path / "sa"
    )
    summary_b = simulate_world.run_simulation(
        turns=15, seed="seed-b", out_dir=tmp_path / "sb"
    )
    assert summary_a["config"]["run_seed"] == "sim-seed-a"
    assert summary_b["config"]["run_seed"] == "sim-seed-b"
    assert summary_a["fingerprint"] != summary_b["fingerprint"]


# ---------------------------------------------------------------------------
# Output validity (100-turn test-mode run).
# ---------------------------------------------------------------------------
def test_runs_100_turns_in_test_mode(sim_run):
    _out_dir, summary = sim_run
    assert summary["config"]["turns"] == 100
    assert summary["config"]["start_turn"] == 2
    assert summary["config"]["end_turn"] == 101


def test_outputs_are_valid_json_and_jsonl(sim_run):
    out_dir, _summary = sim_run
    rows = _metrics_rows(out_dir)
    assert len(rows) == 100
    assert [row["turn"] for row in rows] == list(range(2, 102))
    for line in (out_dir / "timeline.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            event = json.loads(line)
            assert "turn" in event and "kind" in event
    for name in ("summary.json", "final_snapshot.json", "anomalies.json"):
        parsed = json.loads((out_dir / name).read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)
    snapshot = json.loads((out_dir / "final_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["end_turn"] == 101
    assert isinstance(snapshot["replayability_state"], dict)
    assert isinstance(snapshot["rolling_state"], dict)


def test_metrics_rows_have_required_fields(sim_run):
    out_dir, _summary = sim_run
    rows = _metrics_rows(out_dir)
    for row in (rows[0], rows[-1]):
        missing = REQUIRED_METRIC_FIELDS - set(row)
        assert not missing, f"metrics row missing fields: {sorted(missing)}"
        assert row["state_size_bytes"] == row["state_bytes"]


def test_summary_reports_stage_6b_lifecycle_metrics(sim_run):
    _out_dir, summary = sim_run
    aggregates = summary["aggregates"]
    for key in (
        "avg_goal_lifetime",
        "avg_pressure_lifetime",
        "avg_situation_lifetime",
        "goal_recreation_count",
        "pressure_decay_count",
        "situation_archive_count",
        "budget_warnings",
        "world_event_merge_count",
        "world_event_archive_count",
        "world_event_category_counts",
        "investigations_terminal",
        "average_investigation_lifetime",
    ):
        assert key in aggregates


# ---------------------------------------------------------------------------
# Caps / bounded growth.
# ---------------------------------------------------------------------------
def test_respects_output_caps_and_bounded_collections(sim_run):
    out_dir, summary = sim_run
    # Every bounded engine collection stays within its documented cap.
    assert summary["bounded_collections"]["over_cap"] == []
    rows = _metrics_rows(out_dir)
    assert all(row["collections_over_cap"] == 0 for row in rows)
    # Byte-budget status is reported truthfully and, when breached, flagged
    # as an anomaly (whether long headless runs exceed the 64KiB production
    # budget is an engine property the harness reports, not asserts).
    budget = simulate_world.STATE_BUDGET_BYTES
    for row in rows:
        assert row["state_within_budget"] == (row["state_bytes"] <= budget)
    final = summary["final_metrics"]
    if not final["state_within_budget"]:
        assert "state_budget_exceeded" in summary["anomaly_counts"]
    # Timeline stays within the per-turn cap.
    per_turn = {}
    for line in (out_dir / "timeline.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            turn = json.loads(line)["turn"]
            per_turn[turn] = per_turn.get(turn, 0) + 1
    assert all(
        count <= simulate_world.TIMELINE_EVENTS_PER_TURN_CAP
        for count in per_turn.values()
    )


def test_repeated_500_turn_runs_clear_stage_6b_anomalies(tmp_path):
    dir_a = tmp_path / "stage6b_a"
    dir_b = tmp_path / "stage6b_b"

    summary_a = simulate_world.run_simulation(turns=500, seed="stage6b", out_dir=dir_a)
    summary_b = simulate_world.run_simulation(turns=500, seed="stage6b", out_dir=dir_b)

    assert summary_a["fingerprint"] == summary_b["fingerprint"]
    assert (dir_a / "summary.json").read_bytes() == (dir_b / "summary.json").read_bytes()
    for code in (
        "duplicate_id",
        "pressure_never_decays",
        "situation_stuck",
        "state_budget_exceeded",
        "world_event_immortal",
        "runaway_world_event_creation",
        "orphaned_world_event",
        "world_event_loop",
        "orphan_evidence",
        "orphan_investigation",
        "impossible_confidence",
        "evidence_cycle",
    ):
        assert summary_a["anomaly_counts"].get(code, 0) == 0
    assert summary_a["final_metrics"]["state_within_budget"] is True


def test_unbounded_growth_detection_unit():
    crafted = {"goals": [{} for _ in range(simulate_world._collection_caps()[0][1] + 1)]}
    report = simulate_world.bounded_collection_report(crafted)
    assert "goals" in report["over_cap"]

    echo_overflow = {
        "consequence_echoes": {
            "pending": [{} for _ in range(simulate_world.ECHO_PENDING_CAP + 1)]
        }
    }
    echo_report = simulate_world.bounded_collection_report(echo_overflow)
    assert "echoes_pending" in echo_report["over_cap"]


# ---------------------------------------------------------------------------
# Anomaly detectors (unit-level, crafted states).
# ---------------------------------------------------------------------------
def test_detects_duplicate_ids():
    crafted = {
        "goals": [
            {"goal_id": "g1", "status": "active", "source_event_ids": ["e1"]},
            {"goal_id": "g1", "status": "failed", "source_event_ids": ["e1"]},
        ],
        "world_events": [
            {"world_event_id": "we1", "event_type": "resource_shortage", "status": "active", "source_event_ids": ["p1"]},
            {"world_event_id": "we1", "event_type": "resource_shortage", "status": "failed", "source_event_ids": ["p1"]},
        ],
        "evidence": [
            {"evidence_id": "ev1", "confidence": 50, "reliability": 50, "source_event_ids": ["we1"]},
            {"evidence_id": "ev1", "confidence": 60, "reliability": 60, "source_event_ids": ["we1"]},
        ],
        "investigations": [
            {"investigation_id": "i1", "status": "active", "confidence": 50, "progress": 10},
            {"investigation_id": "i1", "status": "failed", "confidence": 50, "progress": 10},
        ],
    }
    report = simulate_world.duplicate_id_report(crafted)
    assert report == {"goals": ["g1"], "world_events": ["we1"], "evidence": ["ev1"], "investigations": ["i1"]}

    collector = simulate_world.TelemetryCollector()
    collector.observe_turn(2, crafted, {}, {}, [])
    assert ("duplicate_id", "goals:g1") in collector.anomalies
    assert ("duplicate_id", "world_events:we1") in collector.anomalies
    assert ("duplicate_id", "evidence:ev1") in collector.anomalies
    assert ("duplicate_id", "investigations:i1") in collector.anomalies


def test_detects_missing_source_event_ids():
    crafted = {
        "situations": [
            {"situation_id": "s1", "status": "active", "source_event_ids": []},
        ]
    }
    missing = simulate_world.missing_source_event_ids(crafted)
    assert missing == {"situations": ["s1"]}


def test_detects_prompt_leakage():
    leaky_rolling = {
        "active_goals": [
            {
                "title": "leaky goal",
                "status": "active",
                "priority": 5,
                "progress": 10,
                "next_step_summary": "step",
                "source_event_ids": ["evt-1"],
                "goal_receipts": [{"receipt_id": "r-1"}],
            }
        ],
        "active_world_events": [
            {
                "world_event_id": "hidden",
                "title": "Bad",
                "severity": 5,
                "status": "active",
                "source_event_ids": ["evt-1"],
            }
        ],
        "active_investigations": [
            {
                "investigation_id": "hidden",
                "status": "active",
                "priority": 5,
                "confidence": 70,
                "known_evidence_count": 1,
                "case_status": "active",
                "progress": 30,
            }
        ],
        "transition_receipts": [{"source_event_id": "evt-1"}],
    }
    violations = simulate_world.prompt_safety_violations(leaky_rolling)
    assert violations, "crafted leakage was not detected"
    joined = "\n".join(violations)
    assert "transition_receipts:authoritative_key_in_rolling" in joined

    collector = simulate_world.TelemetryCollector()
    collector.observe_turn(2, {}, leaky_rolling, {}, [])
    assert any(code == "prompt_leakage" for code, _ in collector.anomalies)


def test_detects_world_event_anomalies():
    crafted = {
        "world_events": [
            {
                "world_event_id": "we-orphan",
                "event_type": "resource_shortage",
                "status": "active",
                "severity": 8,
                "created_turn": 1,
                "originating_pressure_ids": ["missing-pressure"],
                "source_event_ids": ["missing-pressure"],
            }
        ],
        "engine_world_events": [
            {
                "event_id": f"evt-we-{idx}",
                "event_type": "world_event",
                "world_event_id": "we-orphan",
                "world_event_type": "resource_shortage",
                "world_event_status": "active",
                "turn": 2 + idx,
            }
            for idx in range(simulate_world.WORLD_EVENT_LOOP_EVENT_COUNT + 1)
        ],
    }
    collector = simulate_world.TelemetryCollector()
    collector.observe_turn(
        simulate_world.STUCK_WORLD_EVENT_TURNS + 2,
        crafted,
        {},
        {},
        [],
    )
    codes = {code for code, _ in collector.anomalies}
    assert "orphaned_world_event" in codes
    assert "world_event_immortal" in codes
    assert "world_event_loop" in codes


def test_detects_investigation_anomalies():
    crafted = {
        "evidence": [
            {
                "evidence_id": "ev-a",
                "evidence_type": "lead",
                "source_event_ids": ["missing-source"],
                "source_action_ids": [],
                "discovered_turn": 2,
                "discovered_by": ["guard"],
                "location_id": "market",
                "actor_ids": ["guard"],
                "reliability": 120,
                "confidence": 50,
                "related_case_ids": ["missing-case"],
                "related_evidence_ids": ["ev-b"],
                "tags": ["test"],
                "archived": False,
            },
            {
                "evidence_id": "ev-b",
                "evidence_type": "trace",
                "source_event_ids": ["missing-source"],
                "source_action_ids": [],
                "discovered_turn": 2,
                "discovered_by": ["guard"],
                "location_id": "market",
                "actor_ids": ["guard"],
                "reliability": 50,
                "confidence": 50,
                "related_case_ids": ["missing-case"],
                "related_evidence_ids": ["ev-a"],
                "tags": ["test"],
                "archived": False,
            },
        ],
        "investigations": [
            {
                "investigation_id": "case-a",
                "world_event_id": "missing-world-event",
                "situation_id": "",
                "status": "active",
                "priority": 5,
                "assigned_actor_ids": ["guard"],
                "suspect_ids": [],
                "evidence_ids": ["missing-evidence"],
                "confidence": 200,
                "progress": 20,
                "created_turn": 2,
                "updated_turn": 2,
                "solved": False,
                "archived": False,
            }
        ],
    }
    collector = simulate_world.TelemetryCollector()
    collector.observe_turn(2, crafted, {}, {}, [])
    codes = {code for code, _ in collector.anomalies}
    assert "orphan_evidence" in codes
    assert "orphan_investigation" in codes
    assert "impossible_confidence" in codes
    assert "evidence_cycle" in codes


def test_detects_dangling_references():
    crafted = {
        "goals": [
            {
                "goal_id": "g1",
                "status": "active",
                "source_event_ids": ["e1"],
                "parent_situation_ids": ["missing-situation"],
            }
        ],
        "npc_actions": [
            {
                "action_id": "a1",
                "status": "selected",
                "source_event_ids": ["e1"],
                "goal_id": "missing-goal",
                "situation_id": "",
            }
        ],
        "situations": [
            {
                "situation_id": "s1",
                "status": "active",
                "source_event_ids": ["e1"],
                "originating_pressure_ids": ["missing-pressure"],
                "originating_world_event_ids": [],
            }
        ],
    }
    collector = simulate_world.TelemetryCollector()
    collector.observe_turn(2, crafted, {}, {}, [])
    codes = {code for code, _ in collector.anomalies}
    assert "goal_missing_situation" in codes
    assert "npc_action_missing_ref" in codes
    assert "situation_missing_source" in codes


# ---------------------------------------------------------------------------
# Real-run hygiene: the engine's own projections stay prompt-safe.
# ---------------------------------------------------------------------------
def test_clean_run_has_no_prompt_leakage(sim_run):
    out_dir, summary = sim_run
    assert "prompt_leakage" not in summary["anomaly_counts"]
    rows = _metrics_rows(out_dir)
    assert all(row["prompt_leakage_hits"] == 0 for row in rows)
