"""Strict, no-network grader for test_live_20_turn_harness.py JSON evidence.

Exit codes: 0 AUTOMATED_PASS, 1 AUTOMATED_FAIL, 2 INCONCLUSIVE, 3 invalid input.
It never marks semantic truth, human UX, or overall beta acceptance as PASS.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    i = math.ceil(fraction * len(ordered)) - 1
    return round(ordered[max(0, min(i, len(ordered) - 1))], 2)


def grade(report: Mapping[str, Any], *, min_actions: int = 20, max_retry_rate: float = 0.20) -> dict:
    failures: list[str] = []
    inconclusive: list[str] = []
    observations: dict[str, Any] = {}
    summary = report.get("summary")
    per_turn = report.get("per_turn")

    if not isinstance(summary, Mapping):
        return {
            "verdict": "INCONCLUSIVE",
            "failures": [],
            "inconclusive": ["Missing summary object"],
            "observations": {},
            "human_story_review": "NOT_ASSESSED",
        }
    if not isinstance(per_turn, list):
        per_turn = []
        inconclusive.append("Missing per_turn evidence array")

    requested = summary.get("requested_turns")
    attempts = summary.get("attempted_turns")
    successful = summary.get("successful_turns")
    failed = summary.get("failed_turns")
    telemetry = summary.get("turns_with_telemetry")
    if not isinstance(requested, int) or requested < min_actions:
        inconclusive.append(f"Requested actions below {min_actions} or missing")
    else:
        for name, value, expected in (
            ("attempted_turns", attempts, requested),
            ("successful_turns", successful, requested),
            ("failed_turns", failed, 0),
            ("server_error_turns", summary.get("server_error_turns"), 0),
        ):
            if not isinstance(value, int):
                inconclusive.append(f"Missing {name}")
            elif value != expected:
                failures.append(f"{name}={value}, expected {expected}")
        if not isinstance(telemetry, int) or telemetry < requested:
            inconclusive.append(f"Telemetry covers {telemetry} of {requested} actions")
        if len(per_turn) != requested:
            inconclusive.append(f"Per-turn records {len(per_turn)} of {requested}")

    for key in ("telemetry_export_ok", "rolling_state_valid_every_turn",
                "context_growth_bounded", "protected_categories_not_capped",
                "replayability_state_present"):
        value = summary.get(key)
        if value is True:
            continue
        if value is False:
            if key in ("telemetry_export_ok", "replayability_state_present"):
                inconclusive.append(f"{key}=false; cannot assess complete run")
            else:
                failures.append(f"{key}=false")
        else:
            inconclusive.append(f"Missing {key}")

    retry_rate = _number(summary.get("validation_retry_rate"))
    observations["retry_rate"] = retry_rate
    if retry_rate is None:
        inconclusive.append("Missing validation_retry_rate")
    elif retry_rate > max_retry_rate:
        failures.append(f"validation_retry_rate={retry_rate:.3f} exceeds {max_retry_rate:.3f}")

    if (summary.get("context_over_budget_turns") or 0) > 0:
        if not summary.get("compressed_prior_state_turns"):
            failures.append("Context over budget without compression")
        if not summary.get("projected_registry_caps_turns"):
            failures.append("Context over budget without projected registry caps")

    numbers: list[int] = []
    latencies: list[float] = []
    seen_status = False
    for idx, entry in enumerate(per_turn):
        if not isinstance(entry, Mapping):
            inconclusive.append(f"Turn record {idx+1} is not an object")
            continue
        status = entry.get("http_status")
        if status is None:
            inconclusive.append(f"Turn {idx+1} missing HTTP status")
        else:
            seen_status = True
            if status != 200:
                failures.append(f"Turn {idx+1} HTTP {status} instead of 200")
        tn = entry.get("turn_number")
        if isinstance(tn, int):
            numbers.append(tn)
        else:
            inconclusive.append(f"Turn {idx+1} missing committed turn_number")
        if entry.get("rolling_state_valid") is not True:
            if entry.get("rolling_state_valid") is False:
                failures.append(f"Turn {idx+1} invalid rolling_state")
            else:
                inconclusive.append(f"Turn {idx+1} missing rolling_state validity evidence")
        n = _number(entry.get("http_latency_ms"))
        if n is not None:
            latencies.append(n)

    if len(numbers) == len(per_turn) and len(numbers) > 1:
        if len(set(numbers)) != len(numbers) or any(
            next_n != prev_n + 1 for prev_n, next_n in zip(numbers, numbers[1:])
        ):
            failures.append("Turn numbers duplicated, out of order, or skipped")
    elif not seen_status and not per_turn:
        inconclusive.append("No HTTP turn results")

    observations.update({
        "requested_actions": requested,
        "successful_actions": successful,
        "turns_with_telemetry": telemetry,
        "median_http_latency_ms": round(statistics.median(latencies), 2) if latencies else None,
        "p95_http_latency_ms": _percentile(latencies, 0.95),
        "median_target_ms": 25000,
        "p95_target_ms": 90000,
        "latency_review_required": (
            _percentile(latencies, 0.5) > 25000 or _percentile(latencies, 0.95) > 90000
        ) if latencies else None,
    })
    verdict = "AUTOMATED_FAIL" if failures else "INCONCLUSIVE" if inconclusive else "AUTOMATED_PASS"
    return {
        "verdict": verdict,
        "failures": failures,
        "inconclusive": inconclusive,
        "observations": observations,
        "human_story_review": "NOT_ASSESSED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="JSON report from live 20-turn harness")
    parser.add_argument("--min-actions", type=int, default=20)
    parser.add_argument("--max-retry-rate", type=float, default=0.20)
    args = parser.parse_args(argv)
    if args.min_actions < 1 or not 0 <= args.max_retry_rate <= 1:
        parser.error("min-actions must be positive and max-retry-rate must be between 0 and 1")
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ValueError("Expected a JSON object")
    except (OSError, ValueError) as exc:
        print(json.dumps({"verdict": "INVALID_INPUT", "error": str(exc)}))
        return 3
    result = grade(report, min_actions=args.min_actions, max_retry_rate=args.max_retry_rate)
    print(json.dumps(result, indent=2))
    return {"AUTOMATED_PASS": 0, "AUTOMATED_FAIL": 1, "INCONCLUSIVE": 2}[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
