"""Fixed-scenario turn evaluation against a RUNNING engine.

Creates one story from a fixed premise, plays a fixed list of player actions,
then reads the admin raw export and prints:

  * how many turns were real, retried, or replaced by fallback text
  * fallback and retry counts by cause
  * internal pressure labels that reached the player in fallback text
  * speed (seconds per turn, completion tokens per second)

It talks HTTP only and changes no engine behaviour. The same inputs are sent
on every run, so two runs differ only by the model and the engine code.

Run (engine up, ENABLE_DEBUG_PANEL on):

    cd backend
    python tools/eval_turns.py --turns 30 --out ../docs/eval/<name>.json

ADMIN_API_KEY is read from the environment, else from backend/.env. It is
never printed. Exit codes: 0 run completed, 2 engine unreachable or story
creation failed, 3 telemetry export unavailable.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEVICE_ID_HEADER = "X-Device-Id"
ADMIN_API_KEY_HEADER = "X-Admin-Api-Key"

FIXED_STORY: Dict[str, Any] = {
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
}

FIXED_ACTIONS: List[str] = [
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
    "I climb to higher ground for a better view.",
    "I mark my route so I can find my way back.",
    "I approach the nearest person I can see and greet them.",
    "I ask what they know about the road ahead.",
    "I offer to trade something I carry for food.",
    "I thank them and step back to think.",
    "I build a small fire and warm my hands.",
    "I eat a little of my food and save the rest.",
    "I check my feet and boots for damage.",
    "I look for a place to sleep that is hard to see from the path.",
    "I keep watch for a while before settling down.",
    "I wake early and pack my things quietly.",
    "I set off again toward the refuge.",
]

# The fallback turn builds two player-facing lines from the first active
# pressure label (server._build_fail_forward_parsed_turn and
# server._grounded_fail_forward_choices). A label found there is an internal
# mechanic name shown to the player.
# The label is the clause right before "still presses"; paragraphs may be
# joined by a blank line, a newline or a space depending on the store.
_LEAK_NARRATIVE_RE = re.compile(r"(?:^|[.!?]\s+|\n)([^.!?\n]+?) still presses on the scene;")
_LEAK_CHOICE_RE = re.compile(r"^Respond carefully to (.+)$")
_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_NUMBER_RE = re.compile(r"\d+")


def _flag(value: Any) -> bool:
    return str(value).strip().lower() in ("yes", "true", "1")


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def cause_bucket(kind: Any, reason: Any) -> str:
    """Group failures that differ only by a quoted name or a number."""
    kind_text = str(kind or "unknown").strip() or "unknown"
    reason_text = str(reason or "").strip()
    if "/" in reason_text and reason_text.split("/", 1)[0] == kind_text:
        reason_text = reason_text.split("/", 1)[1]
    reason_text = _QUOTED_RE.sub("<name>", reason_text)
    reason_text = _NUMBER_RE.sub("<n>", reason_text)
    reason_text = reason_text.split(":", 1)[0].strip()[:80]
    return f"{kind_text}: {reason_text}" if reason_text else kind_text


def leaked_labels(turn: Dict[str, Any]) -> List[str]:
    """Internal pressure labels shown in a fallback turn's player text."""
    found: List[str] = []
    match = _LEAK_NARRATIVE_RE.search(str(turn.get("narrative") or ""))
    if match:
        found.append(match.group(1).strip())
    for choice in turn.get("choices") or []:
        if isinstance(choice, dict):
            hit = _LEAK_CHOICE_RE.match(str(choice.get("text") or "").strip())
            if hit:
                found.append(hit.group(1).strip())
    return sorted(set(found))


def summarise(
    live: List[Dict[str, Any]], turns_by_number: Dict[int, Dict[str, Any]]
) -> Dict[str, Any]:
    """Pure summary of one run. ``live`` holds the HTTP result of each action;
    ``turns_by_number`` holds the exported turn documents."""
    per_turn: List[Dict[str, Any]] = []
    fallback_causes: Dict[str, int] = {}
    retry_causes: Dict[str, int] = {}
    leak_labels: Dict[str, int] = {}
    for rec in live:
        row = dict(rec)
        doc = turns_by_number.get(rec.get("turn_number")) if rec.get("turn_number") else None
        debug = (doc or {}).get("debug") or {}
        row["has_telemetry"] = bool(doc)
        row["hard_fallback"] = _flag(debug.get("validation_hard_fallback"))
        row["retried"] = _flag(debug.get("validation_retried"))
        row["model_used"] = debug.get("model_used")
        row["provider_latency_ms"] = _num(debug.get("latency_ms"))
        row["completion_tokens"] = _num(debug.get("tokens_completion"))
        if row["retried"] or row["hard_fallback"]:
            row["first_cause"] = cause_bucket(
                debug.get("validation_first_kind") or debug.get("validation_retry_kind"),
                debug.get("validation_first_fail"),
            )
            retry_causes[row["first_cause"]] = retry_causes.get(row["first_cause"], 0) + 1
        if row["hard_fallback"]:
            row["fallback_cause"] = cause_bucket(
                debug.get("validation_second_kind") or debug.get("validation_first_kind"),
                debug.get("validation_second_fail") or debug.get("validation_first_fail"),
            )
            fallback_causes[row["fallback_cause"]] = fallback_causes.get(row["fallback_cause"], 0) + 1
            row["leaked_labels"] = leaked_labels(doc or {})
            for label in row["leaked_labels"]:
                leak_labels[label] = leak_labels.get(label, 0) + 1
        per_turn.append(row)

    ok = [r for r in per_turn if r.get("http_status") == 200]
    seen = [r for r in ok if r["has_telemetry"]]
    fallbacks = [r for r in seen if r["hard_fallback"]]
    real = [r for r in seen if not r["hard_fallback"]]
    http_seconds = [r["http_latency_ms"] / 1000.0 for r in ok if r.get("http_latency_ms")]
    speed_rows = [
        r for r in real
        if r["completion_tokens"] and r["provider_latency_ms"] and not r["retried"]
    ]
    tokens = sum(r["completion_tokens"] for r in speed_rows)
    seconds = sum(r["provider_latency_ms"] for r in speed_rows) / 1000.0

    def rate(part: int, whole: int) -> Optional[float]:
        return round(part / whole, 4) if whole else None

    return {
        "turns_requested": len(live),
        "turns_http_ok": len(ok),
        "turns_http_failed": len(per_turn) - len(ok),
        "turns_with_telemetry": len(seen),
        "real_turns": len(real),
        "real_turns_after_retry": sum(1 for r in real if r["retried"]),
        "fallback_turns": len(fallbacks),
        "fallback_rate": rate(len(fallbacks), len(seen)),
        "fallback_by_cause": dict(sorted(fallback_causes.items(), key=lambda kv: -kv[1])),
        "first_failure_by_cause": dict(sorted(retry_causes.items(), key=lambda kv: -kv[1])),
        "label_leak_turns": sum(1 for r in fallbacks if r.get("leaked_labels")),
        "leaked_labels": dict(sorted(leak_labels.items(), key=lambda kv: -kv[1])),
        "seconds_per_turn_mean": round(statistics.fmean(http_seconds), 1) if http_seconds else None,
        "seconds_per_turn_median": round(statistics.median(http_seconds), 1) if http_seconds else None,
        "seconds_per_turn_max": round(max(http_seconds), 1) if http_seconds else None,
        "completion_tokens_per_second": round(tokens / seconds, 1) if seconds else None,
        "models_used": sorted({str(r["model_used"]) for r in seen if r.get("model_used")}),
        "per_turn": per_turn,
    }


def format_summary(summary: Dict[str, Any]) -> str:
    lines = [
        "=== eval_turns summary ===",
        f"model(s)            : {', '.join(summary['models_used']) or 'unknown'}",
        f"turns requested     : {summary['turns_requested']}",
        f"http ok / failed    : {summary['turns_http_ok']} / {summary['turns_http_failed']}",
        f"real turns          : {summary['real_turns']} "
        f"({summary['real_turns_after_retry']} needed the retry)",
        f"fallback turns      : {summary['fallback_turns']} (rate {summary['fallback_rate']})",
    ]
    for cause, count in summary["fallback_by_cause"].items():
        lines.append(f"  fallback cause    : {count} x {cause}")
    for cause, count in summary["first_failure_by_cause"].items():
        lines.append(f"  first failure     : {count} x {cause}")
    lines.append(f"label leak turns    : {summary['label_leak_turns']}")
    for label, count in summary["leaked_labels"].items():
        lines.append(f"  leaked label      : {count} x {label!r}")
    lines.append(
        f"seconds per turn    : mean {summary['seconds_per_turn_mean']}, "
        f"median {summary['seconds_per_turn_median']}, max {summary['seconds_per_turn_max']}"
    )
    lines.append(f"completion tokens/s : {summary['completion_tokens_per_second']}")
    return "\n".join(lines)


def _admin_key() -> str:
    key = os.environ.get("ADMIN_API_KEY", "").strip()
    if key:
        return key
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.is_file():
        for line in env_file.read_text("utf-8", "ignore").splitlines():
            if line.startswith("ADMIN_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _request(
    method: str, url: str, headers: Dict[str, str], body: Optional[Dict[str, Any]], timeout: float
) -> Tuple[int, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "ignore")[:300]


def run(base_url: str, turns: int, timeout: float) -> Tuple[int, Dict[str, Any]]:
    device_id = f"eval-turns-{uuid.uuid4().hex[:8]}"
    headers = {DEVICE_ID_HEADER: device_id}
    started = time.perf_counter()
    try:
        status, body = _request(
            "POST", f"{base_url}/api/story/new", headers, {**FIXED_STORY, "device_id": device_id}, timeout
        )
    except OSError as exc:
        return 2, {"error": f"engine unreachable: {exc}"}
    if status != 200 or not isinstance(body, dict):
        return 2, {"error": f"story creation failed: {status} {str(body)[:200]}"}
    session_id = body.get("session_id") or (body.get("session") or {}).get("id")
    opening_seconds = round(time.perf_counter() - started, 1)
    print(f"story {session_id} created in {opening_seconds}s", flush=True)

    live: List[Dict[str, Any]] = []
    for index in range(turns):
        action = FIXED_ACTIONS[index % len(FIXED_ACTIONS)]
        rec: Dict[str, Any] = {"index": index + 1, "action_text": action, "turn_number": None}
        t0 = time.perf_counter()
        try:
            status, body = _request(
                "POST",
                f"{base_url}/api/story/action",
                headers,
                {"session_id": session_id, "action_text": action, "debug_mode": True},
                timeout,
            )
            rec["http_status"] = status
            if status == 200 and isinstance(body, dict):
                rec["turn_number"] = (body.get("turn") or {}).get("turn_number")
            else:
                rec["error"] = str(body)[:300]
        except OSError as exc:
            rec["http_status"] = None
            rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
        rec["http_latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        live.append(rec)
        print(f"turn {index + 1}/{turns}: http {rec['http_status']} in {rec['http_latency_ms'] / 1000:.0f}s", flush=True)

    # The export is one local read; a dropped connection is retried so a long
    # run is not lost at the last step.
    status, body = None, None
    for _attempt in range(3):
        try:
            status, body = _request(
                "GET",
                f"{base_url}/api/story/session/{session_id}/export/raw",
                {ADMIN_API_KEY_HEADER: _admin_key()},
                None,
                timeout,
            )
            break
        except OSError as exc:
            status, body = None, f"{type(exc).__name__}: {exc}"
            time.sleep(2.0)
    if status != 200 or not isinstance(body, dict):
        detail = "" if isinstance(body, dict) else str(body)[:200]
        return 3, {
            "error": f"raw export unavailable: {status} {detail}".strip(),
            "session_id": session_id,
            "live": live,
        }
    turns_by_number = {
        t["turn_number"]: t for t in body.get("turns") or [] if isinstance(t.get("turn_number"), int)
    }
    summary = summarise(live, turns_by_number)
    opening = turns_by_number.get(1) or {}
    summary.update(
        {
            "session_id": session_id,
            "base_url": base_url,
            "opening_seconds": opening_seconds,
            "opening_hard_fallback": _flag((opening.get("debug") or {}).get("validation_hard_fallback")),
            "total_seconds": round(time.perf_counter() - started, 1),
            "fixed_story": FIXED_STORY,
        }
    )
    return 0, summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default=os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--turns", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=600.0, help="seconds per HTTP request")
    parser.add_argument("--out", default="", help="write the JSON report here")
    args = parser.parse_args(argv)

    code, result = run(args.base_url.rstrip("/"), args.turns, args.timeout)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    if code != 0:
        print(result.get("error"), file=sys.stderr)
        return code
    print(format_summary(result))
    print(f"opening turn        : {result['opening_seconds']}s, fallback: {result['opening_hard_fallback']}")
    print(f"total run           : {result['total_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
