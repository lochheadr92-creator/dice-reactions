"""Acceptance grader contract tests; pure Python, no provider or database usage."""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from grade_acceptance import grade  # noqa: E402


def _report(n=20):
    return {
        "summary": {
            "requested_turns": n,
            "attempted_turns": n,
            "successful_turns": n,
            "failed_turns": 0,
            "server_error_turns": 0,
            "turns_with_telemetry": n,
            "telemetry_export_ok": True,
            "rolling_state_valid_every_turn": True,
            "context_growth_bounded": True,
            "protected_categories_not_capped": True,
            "replayability_state_present": True,
            "validation_retry_rate": 0.10,
            "context_over_budget_turns": 0,
        },
        "per_turn": [
            {
                "index": i + 1, "http_status": 200,
                "turn_number": i + 2,
                "rolling_state_valid": True, "http_latency_ms": 6000 + i * 100,
            } for i in range(n)
        ],
    }


def test_all_complete_pass_automated_only():
    result = grade(_report())
    assert result["verdict"] == "AUTOMATED_PASS", result
    assert result["human_story_review"] == "NOT_ASSESSED"
    assert result["observations"]["median_http_latency_ms"] is not None


def test_failed_turn_overrules_ordinary_harness_tolerance():
    report = _report()
    report["summary"]["successful_turns"] = 19
    report["summary"]["failed_turns"] = 1
    report["per_turn"][10]["http_status"] = 502
    result = grade(report)
    assert result["verdict"] == "AUTOMATED_FAIL"
    assert any("HTTP 502" in s for s in result["failures"])


def test_missing_export_or_telemetry_is_inconclusive_not_pass():
    report = _report()
    report["summary"]["telemetry_export_ok"] = False
    report["summary"]["turns_with_telemetry"] = 0
    report["per_turn"][0].pop("rolling_state_valid")
    result = grade(report)
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["inconclusive"]


def test_duplicate_or_missing_turn_number_blocks_pass():
    report = _report()
    report["per_turn"][5]["turn_number"] = report["per_turn"][4]["turn_number"]
    assert grade(report)["verdict"] == "AUTOMATED_FAIL"
    report = _report()
    del report["per_turn"][5]["turn_number"]
    assert grade(report)["verdict"] == "INCONCLUSIVE"


def test_retry_budget_and_context_violation_fail():
    report = _report()
    report["summary"]["validation_retry_rate"] = 0.25
    assert grade(report)["verdict"] == "AUTOMATED_FAIL"
    report = _report()
    report["summary"]["context_over_budget_turns"] = 1
    assert "without compression" in " ".join(grade(report)["failures"])
    report = _report()
    report["summary"]["protected_categories_not_capped"] = False
    assert grade(report)["verdict"] == "AUTOMATED_FAIL"


def test_short_run_does_not_pass_as_20_turn_acceptance():
    report = _report(5)
    result = grade(report)
    assert result["verdict"] == "INCONCLUSIVE"
    assert "below 20" in " ".join(result["inconclusive"])


def test_latency_over_target_reported_without_false_invariant_failure():
    report = _report()
    for row in report["per_turn"]:
        row["http_latency_ms"] = 120000
    result = grade(report)
    assert result["verdict"] == "AUTOMATED_PASS"
    assert result["observations"]["latency_review_required"] is True


def test_missing_summary_is_inconclusive():
    assert grade({})["verdict"] == "INCONCLUSIVE"
