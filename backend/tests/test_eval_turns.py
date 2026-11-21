"""Deterministic tests for the summary logic of tools/eval_turns.py.

The tool itself needs a running engine; these tests cover only the pure
functions, so they run in the "not live" suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import eval_turns  # noqa: E402


def _live(index, turn_number, seconds=10.0, status=200):
    return {
        "index": index,
        "action_text": "x",
        "turn_number": turn_number,
        "http_status": status,
        "http_latency_ms": seconds * 1000.0,
    }


def _real(retried=False, tokens="1000", latency="10000"):
    debug = {"model_used": "m", "tokens_completion": tokens, "latency_ms": latency}
    if retried:
        debug.update(
            {
                "validation_retried": "yes",
                "validation_first_kind": "coherence",
                "validation_first_fail": "coherence/unknown person 'Wardens' in choice",
            }
        )
    return {"debug": debug, "narrative": "A real turn.", "choices": []}


def _fallback(pressure="information debt", second_kind="format",
              second_fail="format/missing required choice labels: A,B,C,D"):
    narrative = "The moment holds without a clean resolution."
    choices = [{"label": "A", "text": "Survey the immediate surroundings carefully"}]
    if pressure:
        narrative += f"\n\n{pressure} still presses on the scene; nothing new is invented to escape it."
        choices.append({"label": "D", "text": f"Respond carefully to {pressure}"})
    return {
        "debug": {
            "model_used": "m",
            "validation_retried": "yes",
            "validation_hard_fallback": "yes",
            "validation_first_kind": "format",
            "validation_first_fail": "format/no narrative paragraphs",
            "validation_second_kind": second_kind,
            "validation_second_fail": second_fail,
        },
        "narrative": narrative,
        "choices": choices,
    }


def test_cause_bucket_groups_names_and_numbers():
    a = eval_turns.cause_bucket("coherence", "coherence/unknown person 'Wardens' in choice")
    b = eval_turns.cause_bucket("coherence", "coherence/unknown person 'Dust' in choice")
    assert a == b == "coherence: unknown person <name> in choice"
    assert eval_turns.cause_bucket("format", "format/missing required choice labels: A,B,C,D") == (
        "format: missing required choice labels"
    )
    assert eval_turns.cause_bucket(None, None) == "unknown"


def test_summary_counts_fallbacks_by_cause_and_leaks():
    live = [_live(1, 2), _live(2, 3), _live(3, 4), _live(4, 5), _live(5, None, status=502)]
    docs = {
        2: _real(),
        3: _real(retried=True),
        4: _fallback(),
        5: _fallback(pressure="", second_kind="coherence",
                     second_fail="coherence/unknown person 'Wardens' in choice"),
    }
    s = eval_turns.summarise(live, docs)
    assert s["turns_requested"] == 5
    assert s["turns_http_ok"] == 4 and s["turns_http_failed"] == 1
    assert s["real_turns"] == 2 and s["real_turns_after_retry"] == 1
    assert s["fallback_turns"] == 2 and s["fallback_rate"] == 0.5
    assert s["fallback_by_cause"] == {
        "format: missing required choice labels": 1,
        "coherence: unknown person <name> in choice": 1,
    }
    assert s["first_failure_by_cause"]["format: no narrative paragraphs"] == 2
    assert s["label_leak_turns"] == 1
    assert s["leaked_labels"] == {"information debt": 1}


def test_leak_label_is_only_the_clause_before_still_presses():
    for joiner in ("\n\n", "\n", " "):
        turn = {
            "narrative": "The moment holds. You remain as scout in a pass." + joiner
            + "trust duty still presses on the scene; nothing new is invented to escape it.",
            "choices": [],
        }
        assert eval_turns.leaked_labels(turn) == ["trust duty"]


def test_speed_uses_only_single_call_real_turns():
    live = [_live(1, 2, seconds=10.0), _live(2, 3, seconds=30.0)]
    docs = {2: _real(tokens="1000", latency="10000"), 3: _real(retried=True, tokens="900", latency="9000")}
    s = eval_turns.summarise(live, docs)
    assert s["completion_tokens_per_second"] == 100.0
    assert s["seconds_per_turn_mean"] == 20.0
    assert s["seconds_per_turn_max"] == 30.0


def test_summary_handles_no_telemetry():
    s = eval_turns.summarise([_live(1, None, status=None)], {})
    assert s["fallback_rate"] is None
    assert s["completion_tokens_per_second"] is None
    assert "fallback turns      : 0" in eval_turns.format_summary(s)
