"""
Deterministic 20-turn LIVE endurance harness.

Purpose
-------
Drive a single story session through twenty sequential ``POST /story/action``
requests against a RUNNING backend and capture structured per-turn telemetry,
to measure steady-state endurance: latency, token usage, validation-retry rate,
context-budget growth, rolling-state validity, and the (shadow-only) Utility AI
Living-Cast diagnostics.

This harness changes NO production engine behaviour. It only exercises the
public HTTP surface and reads back the admin raw export for telemetry. It does
not import the ``server``/``security``/``motor`` packages.

Design constraints
------------------
* MANUAL / LIVE ONLY. Marked ``@pytest.mark.live`` (registered in
  ``backend/pytest.ini``) so it is excluded from the deterministic CI suite
  (``pytest -m "not live"``), and the autouse
  ``block_live_llm_in_deterministic_suite`` fixture short-circuits for it.
* No ``server`` / ``security`` / ``motor`` imports — the harness talks HTTP only
  via the shared ``api_client`` (``requests.Session``) and ``base_url`` fixtures,
  so it COLLECTS in any environment (including hermetic sandboxes) even though
  the server package cannot be imported there.
* DETERMINISTIC action selection: a fixed, ordered list of twenty neutral
  exploration actions (no randomness). Same inputs every run.
* RETRY-TOLERANT: a validation retry or a single failed turn is recorded as
  evidence and the loop CONTINUES; it never aborts the run.

Metrics source
--------------
``POST /story/action`` returns only the player-sanitised turn (no ``debug``,
no ``rolling_state`` — see ``player_api.build_player_turn``). The rich telemetry
lives on the persisted turn document and is read back once, after the loop, via
the admin-only ``GET /story/session/{id}/export/raw`` endpoint (returns every
turn's full ``debug`` + per-turn ``rolling_state``, plus the session
``replayability_state``). Per-turn HTTP status and client-side latency are
captured live during the loop and joined to the export by ``turn_number``.

Run
---
    cd backend
    EXPO_PUBLIC_BACKEND_URL=http://127.0.0.1:8001 \
    ADMIN_API_KEY=<server admin key> \
    python -m pytest tests/test_live_20_turn_harness.py -m live -s

The backend must be running, ``ADMIN_API_KEY`` must match the server, and the
admin debug panel (``ENABLE_DEBUG_PANEL``) must be enabled so the raw export is
reachable. Optional env overrides: ``HARNESS_TURNS`` (default 20),
``HARNESS_TURN_SLEEP`` (default 0.4s), ``HARNESS_HTTP_TIMEOUT`` (default 120s),
``HARNESS_REPORT_PATH`` (default a temp file), ``HARNESS_ROLLING_SIZE_CAP``.
"""

from __future__ import annotations

import ast
import json
import os
import statistics
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

import pytest

# Header contract — kept as literals to avoid importing the server package, so
# this module collects in environments where ``security``/``server`` cannot
# import. Mirrors security.ADMIN_API_KEY_HEADER / security.DEVICE_ID_HEADER.
DEVICE_ID_HEADER = "X-Device-Id"
ADMIN_API_KEY_HEADER = "X-Admin-Api-Key"

TURNS = int(os.environ.get("HARNESS_TURNS", "20"))
PER_TURN_SLEEP_S = float(os.environ.get("HARNESS_TURN_SLEEP", "0.4"))
HTTP_TIMEOUT_S = float(os.environ.get("HARNESS_HTTP_TIMEOUT", "120"))
# Fallback bound (chars) for rolling_state growth when the context-budget
# governor telemetry is unavailable from the export.
ROLLING_STATE_SIZE_CAP = int(os.environ.get("HARNESS_ROLLING_SIZE_CAP", "60000"))
PROMPT_REGISTRY_CAPS = {
    "object_locations": 48,
    "inventory_objects": 36,
    "known_rooms": 12,
    "npc_memory": 16,
}
PROTECTED_CATEGORY_KEYS = {
    "active_consequences",
    "delayed_consequences",
    "unresolved_threats",
    "active_threats",
    "promises",
    "clues",
    "active_pressures",
    "relationship_vectors",
    "relationship_threads",
    "objectives",
    "current_objective",
}

# Fixed, deterministic action script — neutral exploration, no randomness, no
# adversarial probing. Twenty distinct actions so the run never repeats verbatim
# while staying engine-neutral (this harness measures endurance, not edge cases).
DETERMINISTIC_ACTIONS: List[str] = [
    "I look around carefully and take in my surroundings.",
    "I listen for any sounds nearby and stay still for a moment.",
    "I check my belongings and take stock of what I carry.",
    "I walk forward along the clearest path ahead of me.",
    "I examine the ground for tracks or signs of recent passage.",
    "I look for a source of water and note its direction.",
    "I search for shelter that could keep out the weather.",
    "I gather anything useful within easy reach.",
    "I study the horizon and judge how much daylight remains.",
    "I move toward the nearest landmark I can see.",
    "I rest briefly and steady my breathing.",
    "I inspect my supplies and set aside what I might need soon.",
    "I continue along the path, keeping a steady pace.",
    "I pause to check whether anyone is following me.",
    "I look for a safe place to cross the ground ahead.",
    "I take note of the weather and how it is changing.",
    "I check the contents of my pack one more time.",
    "I press onward toward higher ground for a better view.",
    "I survey the area from the high ground and plan my route.",
    "I settle in a sheltered spot and prepare to wait out the night.",
]


# --------------------------------------------------------------------------- #
# Coercion helpers — debug payload values are all stringified by the server.
# --------------------------------------------------------------------------- #
def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return None


def _as_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"yes", "true", "1", "on"}:
        return True
    if s in {"no", "false", "0", "off", ""}:
        return False
    return None


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = ast.literal_eval(str(value))
    except (SyntaxError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _rolling_state_valid(rolling: Any) -> bool:
    """Structural validity: a non-empty JSON object that round-trips.

    Intentionally dependency-free (no server hygiene regexes) so the harness
    stays collectable without importing the server package. Confirms the engine
    persisted a usable compression packet for the turn.
    """
    if not isinstance(rolling, dict) or not rolling:
        return False
    try:
        json.dumps(rolling, default=str)
    except (TypeError, ValueError):
        return False
    return True


def _rolling_state_size(rolling: Any) -> int:
    try:
        return len(json.dumps(rolling, default=str))
    except (TypeError, ValueError):
        return 0


def _rolling_registry_counts(rolling: Any) -> Dict[str, int]:
    if not isinstance(rolling, dict):
        return {}
    counts: Dict[str, int] = {}
    for key in PROMPT_REGISTRY_CAPS:
        value = rolling.get(key)
        counts[key] = len(value) if isinstance(value, list) else 0
    return counts


def _protected_category_presence(rolling: Any) -> Dict[str, bool]:
    if not isinstance(rolling, dict):
        return {key: False for key in sorted(PROTECTED_CATEGORY_KEYS)}
    return {key: bool(rolling.get(key)) for key in sorted(PROTECTED_CATEGORY_KEYS)}


def _mean(values: List[Any]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return round(statistics.fmean(vals), 2)


def _extract_debug_metrics(
    turn_number: Optional[int], debug: Dict[str, Any], rolling: Any
) -> Dict[str, Any]:
    """Project a persisted turn's ``debug`` dict + ``rolling_state`` into metrics."""
    util = {k: debug[k] for k in debug if k.startswith("replayability_utility_ai_")}
    compression = {
        k: (_as_int(v) if _as_int(v) is not None else v)
        for k, v in debug.items()
        if k.startswith("compression_")
    }
    return {
        "turn_number": turn_number,
        "model_requested": debug.get("model_requested"),
        "model_used": debug.get("model_used"),
        "provider": debug.get("provider"),
        "provider_status": debug.get("provider_status"),
        "provider_latency_ms": _as_int(debug.get("latency_ms")),
        "prompt_tokens": _as_int(debug.get("tokens_prompt")),
        "completion_tokens": _as_int(debug.get("tokens_completion")),
        "total_tokens": _as_int(debug.get("tokens_total")),
        "validation_retried": _as_bool(debug.get("validation_retried")) or False,
        "validation_retry_kind": debug.get("validation_retry_kind"),
        "validation_first_fail": debug.get("validation_first_fail"),
        "validation_second_fail": debug.get("validation_second_fail"),
        "context_budget_tokens": _as_int(debug.get("context_budget_tokens")),
        "estimated_prompt_tokens": _as_int(debug.get("estimated_prompt_tokens")),
        "context_over_budget": _as_bool(debug.get("context_over_budget")),
        "context_trimmed": _as_bool(debug.get("context_trimmed")),
        "compressed_prior_state": _as_bool(debug.get("compressed_prior_state")) or False,
        "projected_registry_caps": _as_dict(debug.get("projected_registry_caps")),
        "trim_reason": debug.get("trim_reason"),
        "estimated_tokens_removed": _as_int(debug.get("estimated_tokens_removed")),
        "compression": compression,
        "rolling_state_valid": _rolling_state_valid(rolling),
        "rolling_state_size_chars": _rolling_state_size(rolling),
        "persisted_registry_counts": _rolling_registry_counts(rolling),
        "protected_category_presence": _protected_category_presence(rolling),
        # Replayability ran this turn iff it emitted utility-AI diagnostics.
        "replayability_active": bool(util),
        "candidate_count": _as_int(
            debug.get("replayability_utility_ai_shadow_candidate_count")
        ),
        "live_selection_enabled": _as_bool(
            debug.get("replayability_utility_ai_live_selection_enabled")
        ),
        "live_selection_applied": _as_bool(
            debug.get("replayability_utility_ai_live_selection_applied")
        ),
        "selected_live_winner_source": debug.get(
            "replayability_utility_ai_selected_live_winner_source"
        ),
        "utility_ai_diagnostics": util,
    }


def _print_human_report(
    summary: Dict[str, Any], per_turn: List[Dict[str, Any]], report_path: str
) -> None:
    rr = summary["validation_retry_rate"]
    lines: List[str] = []
    lines.append("")
    lines.append("=" * 74)
    lines.append("LIVE 20-TURN ENDURANCE HARNESS — SUMMARY")
    lines.append("=" * 74)
    lines.append(f"session_id            : {summary['session_id']}")
    lines.append(f"requested turns       : {summary['requested_turns']}")
    lines.append(f"attempted turns       : {summary['attempted_turns']}")
    lines.append(f"successful turns      : {summary['successful_turns']}")
    lines.append(
        f"failed turns          : {summary['failed_turns']} "
        f"(5xx: {summary['server_error_turns']})"
    )
    lines.append(f"turns with telemetry  : {summary['turns_with_telemetry']}")
    if rr is not None:
        lines.append(
            f"validation retries    : {summary['validation_retry_count']} "
            f"({rr * 100:.1f}% of telemetry turns)"
        )
    else:
        lines.append(f"validation retries    : {summary['validation_retry_count']}")
    lines.append(f"avg provider latency  : {summary['avg_provider_latency_ms']} ms")
    lines.append(f"avg http latency      : {summary['avg_http_latency_ms']} ms")
    lines.append(
        f"avg total tokens      : {summary['avg_total_tokens']} "
        f"(max {summary['max_total_tokens']})"
    )
    lines.append(f"avg prompt tokens     : {summary['avg_prompt_tokens']}")
    lines.append(f"avg completion tokens : {summary['avg_completion_tokens']}")
    lines.append(f"avg est. prompt tokens: {summary['avg_estimated_prompt_tokens']}")
    lines.append(
        f"avg rolling_state     : {summary['avg_rolling_state_size_chars']} chars "
        f"(max {summary['max_rolling_state_size_chars']})"
    )
    lines.append(
        f"context growth bounded: {summary['context_growth_bounded']} "
        f"(via {summary['context_growth_method']})"
    )
    lines.append(f"context over-budget   : {summary['context_over_budget_turns']} turns")
    lines.append(f"compressed prior     : {summary['compressed_prior_state_turns']} turns")
    lines.append(f"projected cap turns  : {summary['projected_registry_caps_turns']}")
    lines.append(
        f"persisted not capped : {summary['persisted_registry_counts_exceed_projection_caps']}"
    )
    lines.append(
        f"protected caps absent: {summary['protected_categories_not_capped']}"
    )
    lines.append(
        f"rolling_state valid   : {summary['rolling_state_valid_every_turn']} "
        f"(every telemetry turn)"
    )
    lines.append(f"replayability active  : {summary['replayability_state_present']}")
    lines.append(f"total runtime         : {summary['total_runtime_s']} s")
    lines.append(
        f"telemetry export ok   : {summary['telemetry_export_ok']}  "
        f"{summary['telemetry_export_error'] or ''}"
    )
    lines.append("-" * 74)
    lines.append("per-turn:")
    for t in per_turn:
        lines.append(
            f"  T{t['index']:02d} status={t.get('http_status')} "
            f"turn#={t.get('turn_number')} "
            f"prov={t.get('provider_latency_ms')}ms "
            f"http={t.get('http_latency_ms')}ms "
            f"tok={t.get('total_tokens')} "
            f"est={t.get('estimated_prompt_tokens')}/{t.get('context_budget_tokens')} "
            f"retry={t.get('validation_retried')} "
            f"proj={t.get('compressed_prior_state')} "
            f"rs_valid={t.get('rolling_state_valid')} "
            f"rs_sz={t.get('rolling_state_size_chars')} "
            f"cand={t.get('candidate_count')} "
            f"live_sel={t.get('live_selection_applied')}"
        )
    lines.append("-" * 74)
    lines.append(f"JSON report written to: {report_path}")
    lines.append("=" * 74)
    print("\n".join(lines))


@pytest.mark.live
def test_live_20_turn_endurance(base_url, api_client):
    """Deterministic 20-turn live endurance run with structured telemetry."""
    admin_key = os.environ.get("ADMIN_API_KEY", "")
    device_id = f"live-20turn-{uuid.uuid4().hex[:8]}"
    report_path = os.environ.get(
        "HARNESS_REPORT_PATH",
        os.path.join(tempfile.gettempdir(), "live_20turn_harness_report.json"),
    )

    run_started = time.perf_counter()

    # --- Create the story session (boot turn = turn_number 1) ---------------- #
    new_resp = api_client.post(
        f"{base_url}/api/story/new",
        json={
            "device_id": device_id,
            "genre": "low fantasy survival",
            "role": "Wandering scout",
            "tone": "grim, intimate, consequential",
            "difficulty": "standard",
            "debug_mode": True,
            "mode": "advanced",
            "custom_premise": (
                "You are a wandering scout crossing cold country toward a "
                "half-remembered refuge. Resources are thin and the land is unkind."
            ),
        },
        headers={DEVICE_ID_HEADER: device_id},
        timeout=HTTP_TIMEOUT_S,
    )
    assert new_resp.status_code == 200, (
        f"/story/new failed: {new_resp.status_code} {new_resp.text[:300]}"
    )
    new_data = new_resp.json()
    session_id = new_data.get("session_id") or (new_data.get("session") or {}).get("id")
    assert session_id, f"no session_id in /story/new response: {new_data}"

    # --- Deterministic 20-turn action loop (retry-tolerant) ------------------ #
    live_turns: List[Dict[str, Any]] = []
    for i in range(TURNS):
        action_text = DETERMINISTIC_ACTIONS[i % len(DETERMINISTIC_ACTIONS)]
        rec: Dict[str, Any] = {
            "index": i + 1,
            "action_text": action_text,
            "http_status": None,
            "http_latency_ms": None,
            "turn_number": None,
            "error": None,
        }
        t0 = time.perf_counter()
        try:
            resp = api_client.post(
                f"{base_url}/api/story/action",
                json={
                    "session_id": session_id,
                    "action_text": action_text,
                    "debug_mode": True,
                },
                headers={DEVICE_ID_HEADER: device_id},
                timeout=HTTP_TIMEOUT_S,
            )
            rec["http_latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
            rec["http_status"] = resp.status_code
            if resp.status_code == 200:
                turn = (resp.json() or {}).get("turn") or {}
                rec["turn_number"] = turn.get("turn_number")
            else:
                rec["error"] = resp.text[:300]
        except Exception as exc:  # noqa: BLE001 — record & continue (endurance)
            rec["http_latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
            rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
        live_turns.append(rec)
        time.sleep(PER_TURN_SLEEP_S)

    total_runtime_s = round(time.perf_counter() - run_started, 2)

    # --- Read back full telemetry via the admin raw export (once) ------------ #
    export_ok = False
    export_error: Optional[str] = None
    turns_by_number: Dict[int, Dict[str, Any]] = {}
    replayability_state_present = False
    try:
        exp = api_client.get(
            f"{base_url}/api/story/session/{session_id}/export/raw",
            headers={ADMIN_API_KEY_HEADER: admin_key},
            timeout=HTTP_TIMEOUT_S,
        )
        if exp.status_code == 200:
            export_ok = True
            body = exp.json() or {}
            for tdoc in body.get("turns") or []:
                tn = tdoc.get("turn_number")
                if isinstance(tn, int):
                    turns_by_number[tn] = tdoc
            replayability_state_present = bool(
                (body.get("session") or {}).get("replayability_state")
            )
        else:
            export_error = f"{exp.status_code}: {exp.text[:200]}"
    except Exception as exc:  # noqa: BLE001
        export_error = f"{type(exc).__name__}: {exc}"[:200]

    # --- Join live records with exported debug + rolling_state --------------- #
    per_turn: List[Dict[str, Any]] = []
    for rec in live_turns:
        merged = dict(rec)
        tn = rec.get("turn_number")
        tdoc = turns_by_number.get(tn) if isinstance(tn, int) else None
        debug = (tdoc or {}).get("debug") or {}
        rolling = (tdoc or {}).get("rolling_state")
        if debug:
            merged.update(_extract_debug_metrics(tn, debug, rolling))
        else:
            merged["telemetry_available"] = False
        per_turn.append(merged)

    # --- Aggregates ---------------------------------------------------------- #
    successful = [t for t in per_turn if t.get("http_status") == 200]
    failed = [t for t in per_turn if t.get("http_status") != 200]
    server_errors = [
        t for t in per_turn
        if isinstance(t.get("http_status"), int) and 500 <= t["http_status"] < 600
    ]
    # Turns with debug telemetry have the rolling_state_valid key set.
    with_debug = [t for t in successful if "rolling_state_valid" in t]

    retry_count = sum(1 for t in with_debug if t.get("validation_retried"))
    provider_latencies = [t.get("provider_latency_ms") for t in with_debug]
    http_latencies = [t.get("http_latency_ms") for t in successful]
    total_tokens = [t.get("total_tokens") for t in with_debug]
    prompt_tokens = [t.get("prompt_tokens") for t in with_debug]
    completion_tokens = [t.get("completion_tokens") for t in with_debug]
    est_prompt = [t.get("estimated_prompt_tokens") for t in with_debug]
    rolling_sizes = [
        t.get("rolling_state_size_chars")
        for t in with_debug
        if t.get("rolling_state_size_chars")
    ]
    context_over_budget_turns = sum(
        1 for t in with_debug if t.get("context_over_budget") is True
    )
    compressed_prior_state_turns = sum(
        1 for t in with_debug if t.get("compressed_prior_state") is True
    )
    projected_registry_caps_turns = sum(
        1 for t in with_debug if t.get("projected_registry_caps")
    )

    protected_categories_not_capped = all(
        not (set((t.get("projected_registry_caps") or {}).keys()) & PROTECTED_CATEGORY_KEYS)
        for t in with_debug
    )
    persisted_registry_counts_exceed_projection_caps = any(
        any(
            (t.get("persisted_registry_counts") or {}).get(key, 0)
            > int((meta or {}).get("kept") or 0)
            for key, meta in (t.get("projected_registry_caps") or {}).items()
        )
        for t in with_debug
    )
    protected_category_presence_any = {
        key: any(
            (t.get("protected_category_presence") or {}).get(key) for t in with_debug
        )
        for key in sorted(PROTECTED_CATEGORY_KEYS)
    }

    # Context growth bounded: prefer the engine's context-budget governor signal
    # (estimated_prompt_tokens never exceeds the budget);
    # fall back to a rolling_state size cap when budget telemetry is absent.
    budget_checks: List[bool] = []
    for t in with_debug:
        ep = t.get("estimated_prompt_tokens")
        cb = t.get("context_budget_tokens")
        if ep is not None and cb:
            budget_checks.append(ep <= cb)
    if budget_checks:
        context_growth_bounded: Optional[bool] = all(budget_checks)
        growth_method = "context_budget_governor"
    elif rolling_sizes:
        context_growth_bounded = max(rolling_sizes) <= ROLLING_STATE_SIZE_CAP
        growth_method = f"rolling_state_size<={ROLLING_STATE_SIZE_CAP}chars"
    else:
        context_growth_bounded = None
        growth_method = "unavailable"

    rolling_state_valid_every_turn = bool(with_debug) and all(
        t.get("rolling_state_valid") for t in with_debug
    )

    summary: Dict[str, Any] = {
        "session_id": session_id,
        "device_id": device_id,
        "requested_turns": TURNS,
        "attempted_turns": len(per_turn),
        "successful_turns": len(successful),
        "failed_turns": len(failed),
        "server_error_turns": len(server_errors),
        "turns_with_telemetry": len(with_debug),
        "validation_retry_count": retry_count,
        "validation_retry_rate": (
            round(retry_count / len(with_debug), 4) if with_debug else None
        ),
        "avg_provider_latency_ms": _mean(provider_latencies),
        "avg_http_latency_ms": _mean(http_latencies),
        "avg_total_tokens": _mean(total_tokens),
        "max_total_tokens": max(
            [v for v in total_tokens if v is not None], default=None
        ),
        "avg_prompt_tokens": _mean(prompt_tokens),
        "avg_completion_tokens": _mean(completion_tokens),
        "avg_estimated_prompt_tokens": _mean(est_prompt),
        "avg_rolling_state_size_chars": _mean(rolling_sizes),
        "max_rolling_state_size_chars": max(rolling_sizes, default=None),
        "context_growth_bounded": context_growth_bounded,
        "context_growth_method": growth_method,
        "context_over_budget_turns": context_over_budget_turns,
        "compressed_prior_state_turns": compressed_prior_state_turns,
        "projected_registry_caps_turns": projected_registry_caps_turns,
        "persisted_registry_counts_exceed_projection_caps": (
            persisted_registry_counts_exceed_projection_caps
        ),
        "protected_categories_not_capped": protected_categories_not_capped,
        "protected_category_presence_any": protected_category_presence_any,
        "rolling_state_valid_every_turn": rolling_state_valid_every_turn,
        "replayability_state_present": replayability_state_present,
        "total_runtime_s": total_runtime_s,
        "telemetry_export_ok": export_ok,
        "telemetry_export_error": export_error,
    }

    report = {"summary": summary, "per_turn": per_turn}

    # Always persist + print the report BEFORE asserting, so evidence survives
    # even when an endurance invariant fails.
    try:
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)
    except OSError:
        pass
    _print_human_report(summary, per_turn, report_path)

    # --- Endurance gates ----------------------------------------------------- #
    # Failures and validation retries are recorded as evidence (above), not
    # aborted on. These gates assert only the steady-state invariants the run
    # exists to prove.
    assert len(per_turn) == TURNS, "harness did not attempt every turn"
    assert successful, (
        "no successful turns — backend unreachable or misconfigured "
        f"(base_url={base_url})"
    )
    assert export_ok, (
        "admin raw export unavailable — telemetry could not be verified. "
        "Ensure the backend is running with the debug panel enabled and "
        f"ADMIN_API_KEY matches the server. error={export_error}"
    )
    assert with_debug, (
        "export succeeded but no turn carried debug telemetry — cannot verify "
        "endurance invariants"
    )
    assert rolling_state_valid_every_turn, (
        "rolling_state was invalid (missing/empty) on at least one telemetry turn"
    )
    if context_over_budget_turns:
        assert compressed_prior_state_turns > 0, (
            "prompt context went over budget but compressed_prior_state never appeared"
        )
        assert projected_registry_caps_turns > 0, (
            "prompt context went over budget but projected_registry_caps never reported applied caps"
        )
        assert persisted_registry_counts_exceed_projection_caps, (
            "projected caps appeared, but persisted rolling_state registry counts never exceeded "
            "the prompt cap evidence; cannot prove projection stayed prompt-only"
        )
    assert protected_categories_not_capped, (
        "projected_registry_caps included protected consequence/threat/relationship/objective keys"
    )
    assert context_growth_bounded is True, (
        f"context growth not bounded (method={growth_method})"
    )
