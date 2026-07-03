"""
Prose Length System v2 — deterministic regression tests.

Proves:
  • legacy S/M/L values map onto the new modes (S→brief, M/default→standard,
    L→story) and cinematic resolves as the explicit fourth mode
  • prose mode changes presentation ONLY — canonical state (rolling_state,
    state, ledger, choices) is byte-identical across modes
  • over-budget narration is trimmed LOCALLY at a sentence boundary
  • over-budget narration does NOT trigger a second LLM call
  • telemetry records returned vs final character counts + trimming flag
  • each mode's prompt directive contains structural instructions
"""

from __future__ import annotations

import asyncio
import copy
import json
import uuid
from pathlib import Path

import pytest

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import gateway  # noqa: E402
import prose_modes  # noqa: E402
import server  # noqa: E402


# ---------------------------------------------------------------------------
# Mode resolution + legacy S/M/L compatibility
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "legacy,expected",
    [
        ("S", "brief"),
        ("s", "brief"),
        ("short", "brief"),
        ("M", "standard"),
        ("medium", "standard"),
        ("default", "standard"),
        ("L", "story"),
        ("long", "story"),
        ("xl", "cinematic"),
    ],
)
def test_legacy_sml_values_map_correctly(legacy, expected):
    assert prose_modes.resolve_prose_mode_name(legacy) == expected


@pytest.mark.parametrize("name", ["brief", "standard", "story", "cinematic"])
def test_new_mode_names_resolve_to_themselves(name):
    mode = prose_modes.resolve_prose_mode(name)
    assert mode.name == name


@pytest.mark.parametrize("value", [None, "", "  ", "garbage", "epic", 42])
def test_unknown_or_missing_values_fail_safe_to_standard(value):
    assert prose_modes.resolve_prose_mode(value).name == "standard"


def test_mode_budgets_match_specification():
    b = prose_modes.PROSE_MODES["brief"]
    assert (b.min_paragraphs, b.max_paragraphs) == (1, 1)
    assert (b.min_sentences, b.max_sentences) == (2, 4)
    assert (b.min_chars, b.max_chars) == (300, 600)

    s = prose_modes.PROSE_MODES["standard"]
    assert (s.min_paragraphs, s.max_paragraphs) == (2, 3)
    assert (s.min_sentences, s.max_sentences) == (5, 9)
    assert (s.min_chars, s.max_chars) == (700, 1200)

    st = prose_modes.PROSE_MODES["story"]
    assert (st.min_paragraphs, st.max_paragraphs) == (4, 6)
    assert (st.min_sentences, st.max_sentences) == (10, 18)
    assert (st.min_chars, st.max_chars) == (1800, 2400)

    c = prose_modes.PROSE_MODES["cinematic"]
    assert (c.min_paragraphs, c.max_paragraphs) == (6, 10)
    assert (c.min_chars, c.max_chars) == (3000, 4000)


# ---------------------------------------------------------------------------
# Structural prompt instructions per mode
# ---------------------------------------------------------------------------
def test_prompt_directives_contain_structural_instructions():
    d_brief = prose_modes.PROSE_MODES["brief"].directive
    assert "[PROSE MODE: BRIEF]" in d_brief
    assert "1 paragraph" in d_brief and "2-4 sentences" in d_brief
    assert "immediate outcome" in d_brief

    d_std = prose_modes.PROSE_MODES["standard"].directive
    assert "[PROSE MODE: STANDARD]" in d_std
    assert "2-3 paragraphs" in d_std and "5-9 sentences" in d_std
    assert "consequences" in d_std

    d_story = prose_modes.PROSE_MODES["story"].directive
    assert "[PROSE MODE: STORY]" in d_story
    assert "4-6 paragraphs" in d_story and "10-18 sentences" in d_story
    assert "continuous scene" in d_story
    assert "End naturally" in d_story and "Do not summarise" in d_story

    d_cin = prose_modes.PROSE_MODES["cinematic"].directive
    assert "[PROSE MODE: CINEMATIC]" in d_cin
    assert "6-10 paragraphs" in d_cin
    assert "emotional pacing" in d_cin
    assert "Do not summarise" in d_cin


def test_system_prompt_defers_to_prose_mode_directive():
    prompt = server.STORY_ENGINE_SYSTEM_PROMPT
    assert "[PROSE MODE:" in prompt
    assert "750-900 characters" not in prompt
    assert "hard max 1200 after formatting" not in prompt


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------
def test_measure_narration_counts():
    paragraphs = [
        "First sentence. Second sentence! Third?",
        'He said, "Run." Then silence.',
    ]
    m = prose_modes.measure_narration(paragraphs)
    assert m["paragraph_count"] == 2
    assert m["sentence_count"] == 5
    assert m["character_count"] == sum(len(p) for p in paragraphs)


def test_measure_narration_empty():
    assert prose_modes.measure_narration([]) == {
        "paragraph_count": 0,
        "sentence_count": 0,
        "character_count": 0,
    }


# ---------------------------------------------------------------------------
# Local trimming
# ---------------------------------------------------------------------------
def test_trim_noop_when_within_budget():
    paragraphs = ["Short scene.", "It ends."]
    out, trimmed = prose_modes.trim_narration(paragraphs, 600)
    assert out == paragraphs
    assert trimmed is False


def test_trim_cuts_at_sentence_boundary():
    sentence = "The lantern gutters in the wind. "
    paragraph = (sentence * 30).strip()  # ~1000 chars, sentences of ~33
    out, trimmed = prose_modes.trim_narration([paragraph], 200)
    assert trimmed is True
    joined = " ".join(out)
    assert len(joined) <= 200
    # Ends on a complete sentence, never mid-word.
    assert joined.endswith("wind.")
    # Output is a prefix of the input narration (never rewritten).
    assert paragraph.startswith(joined)


def test_trim_keeps_whole_paragraphs_then_partial():
    p1 = "A" * 100 + "."
    p2 = "Second paragraph one. Second paragraph two. Second paragraph three."
    out, trimmed = prose_modes.trim_narration([p1, p2], 150)
    assert trimmed is True
    assert out[0] == p1
    assert len(out) == 2
    assert out[1].startswith("Second paragraph one.")
    assert sum(len(p) for p in out) <= 150


def test_trim_never_returns_empty_narration():
    # Single sentence longer than the budget: word-boundary hard cut fallback.
    paragraph = "word " * 100  # one 'sentence', no terminal punctuation
    out, trimmed = prose_modes.trim_narration([paragraph.strip()], 50)
    assert trimmed is True
    assert out and out[0]
    assert len(out[0]) <= 50
    assert out[0].endswith("…")


def test_trim_is_deterministic():
    paragraphs = [("The rain falls. " * 40).strip(), ("He waits. " * 40).strip()]
    first = prose_modes.trim_narration(paragraphs, 300)
    for _ in range(5):
        assert prose_modes.trim_narration(paragraphs, 300) == first


# ---------------------------------------------------------------------------
# Finalize: presentation-only trim + telemetry (no canonical state changes)
# ---------------------------------------------------------------------------
def _parsed_turn(paragraphs):
    return server.ParsedTurn(
        narrative="\n\n".join(paragraphs),
        paragraphs=list(paragraphs),
        choices=[
            {"label": "A", "text": "Act"},
            {"label": "B", "text": "Wait"},
            {"label": "C", "text": "Look"},
            {"label": "D", "text": "Speak"},
        ],
        state={"Health": "stable", "Pressure": "Nightfall approaching"},
        ledger={"Carried": "torch (1, good)"},
        rolling_state={
            "scene": "a ruined chapel",
            "objectives": ["reach the pass"],
            "npcs": [{"name": "Maren", "state": "wary"}],
        },
        debug=None,
        raw="raw",
    )


def _long_paragraphs():
    sentence = "The corridor stretches on and the dust hangs in the light. "
    return [(sentence * 8).strip() for _ in range(4)]  # ~1900 chars total


def test_finalize_trims_over_budget_narration_locally():
    parsed = _parsed_turn(_long_paragraphs())
    meta = {"prose_mode": "standard", "prose_budget": 1200}
    out, _raw, out_meta = server._finalize_validated_turn(parsed, parsed.raw, meta)
    prose = out_meta["prose"]
    assert prose["trimming_occurred"] is True
    assert prose["returned_character_count"] > 1200
    assert prose["final_character_count"] <= 1200
    assert sum(len(p) for p in out.paragraphs) <= 1200
    # narrative string is kept consistent with the trimmed paragraphs
    assert out.narrative == "\n\n".join(out.paragraphs)


def test_finalize_no_trim_within_budget():
    parsed = _parsed_turn(["A calm scene unfolds. Nothing is lost."])
    out, _raw, out_meta = server._finalize_validated_turn(
        parsed, parsed.raw, {"prose_mode": "standard"}
    )
    prose = out_meta["prose"]
    assert prose["trimming_occurred"] is False
    assert prose["returned_character_count"] == prose["final_character_count"]
    assert out.paragraphs == parsed.paragraphs


def test_prose_mode_is_presentation_only():
    """Same model output finalized under every mode: canonical fields are
    byte-identical; only narration presentation may differ."""
    canonical = {}
    for mode in ("brief", "standard", "story", "cinematic"):
        parsed = _parsed_turn(_long_paragraphs())
        before_rolling = copy.deepcopy(parsed.rolling_state)
        out, _raw, _meta = server._finalize_validated_turn(
            parsed, parsed.raw, {"prose_mode": mode}
        )
        canonical[mode] = (
            json.dumps(out.rolling_state, sort_keys=True),
            json.dumps(out.state, sort_keys=True),
            json.dumps(out.ledger, sort_keys=True),
            json.dumps(out.choices, sort_keys=True),
        )
        # Input canonical state never mutated
        assert parsed.rolling_state == before_rolling
    assert len(set(canonical.values())) == 1


def test_finalize_telemetry_fields_present():
    parsed = _parsed_turn(_long_paragraphs())
    meta = {
        "prose_mode": "brief",
        "prose_mode_requested": "s",
        "model_used": "test-model",
        "telemetry": {"latency_ms": 123},
        "validation_retried": True,
    }
    _out, _raw, out_meta = server._finalize_validated_turn(parsed, parsed.raw, meta)
    prose = out_meta["prose"]
    assert prose["requested_prose_mode"] == "s"
    assert prose["effective_prose_mode"] == "brief"
    assert prose["requested_budget"] == 600
    assert prose["trimming_occurred"] is True
    assert prose["retry_occurred"] is True
    assert prose["model_used"] == "test-model"
    assert prose["latency_ms"] == 123


def test_meta_into_debug_surfaces_prose_telemetry():
    debug = server._meta_into_debug(
        None,
        {
            "prose": {
                "requested_prose_mode": "story",
                "effective_prose_mode": "story",
                "requested_budget": 2400,
                "returned_character_count": 2600,
                "final_character_count": 2380,
                "trimming_occurred": True,
                "retry_occurred": False,
            }
        },
    )
    assert debug["prose_requested_prose_mode"] == "story"
    assert debug["prose_requested_budget"] == "2400"
    assert debug["prose_returned_character_count"] == "2600"
    assert debug["prose_final_character_count"] == "2380"
    assert debug["prose_trimming_occurred"] == "True"
    assert debug["prose_retry_occurred"] == "False"


# ---------------------------------------------------------------------------
# Over-budget narration never triggers a second LLM call
# ---------------------------------------------------------------------------
def test_validator_accepts_over_budget_narration():
    parsed = _parsed_turn(["x" * 5000])
    ok, reason = server._validate_parsed(parsed)
    assert ok, f"length must not be a validation failure: {reason}"


def test_over_budget_narration_makes_exactly_one_llm_call(monkeypatch):
    """End-to-end through _generate_validated_turn: a valid but over-budget
    response is accepted, trimmed locally, and never re-prompted."""
    long_narrative = "\n\n".join(_long_paragraphs())
    raw_response = (
        '<rolling_state>\n{"scene": "a ruined chapel"}\n</rolling_state>\n'
        f"<narrative>\n{long_narrative}\n</narrative>\n"
        "<choices>\nA. Press on\nB. Hold position\nC. Search the rubble\nD. Call out\n</choices>\n"
        "<state>\nHealth: stable\nPressure: Nightfall approaching\n</state>\n"
        "<ledger>\nCarried: torch\n</ledger>\n"
    )
    calls = {"n": 0}

    async def fake_invoke_llm(**kwargs):
        calls["n"] += 1
        return {
            "content": raw_response,
            "model_used": "test-model",
            "model_requested": "test-model",
            "telemetry": {"latency_ms": 5},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    async def fake_settings():
        return {"max_tokens": 2048, "memory_depth": 3, "history_window": 30}

    async def fake_build_messages(session, user_text, memory_depth,
                                  history_window_fallback, **kwargs):
        return [
            {"role": "system", "content": server.STORY_ENGINE_SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]

    monkeypatch.setattr(gateway, "invoke_llm", fake_invoke_llm)
    monkeypatch.setattr(server, "get_ai_settings", fake_settings)
    monkeypatch.setattr(server, "_build_messages", fake_build_messages)

    session = {
        "id": str(uuid.uuid4()),
        "turn_count": 5,  # past early-game pacing stages
        "mode": "advanced",
        "prose_mode": "standard",
    }
    parsed, _raw, meta = asyncio.run(
        server._generate_validated_turn(session, "Continue")
    )

    assert calls["n"] == 1, "over-budget narration must not re-call the LLM"
    prose = meta["prose"]
    assert prose["trimming_occurred"] is True
    assert prose["returned_character_count"] > 1200
    assert prose["final_character_count"] <= 1200
    assert prose["retry_occurred"] is False
    assert sum(len(p) for p in parsed.paragraphs) <= 1200
    # Canonical fields untouched by the trim
    assert parsed.rolling_state == {"scene": "a ruined chapel"}
    assert [c["label"] for c in parsed.choices] == ["A", "B", "C", "D"]


def test_prose_directive_included_in_generated_user_message(monkeypatch):
    """_generate_turn embeds the structural prose directive as an engine-only
    hint, and meta carries the requested mode + budget."""
    captured = {}

    async def fake_invoke_llm(**kwargs):
        return {
            "content": "irrelevant",
            "model_used": "test-model",
            "model_requested": "test-model",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    async def fake_settings():
        return {"max_tokens": 2048, "memory_depth": 3, "history_window": 30}

    async def fake_build_messages(session, user_text, memory_depth,
                                  history_window_fallback, **kwargs):
        captured["user_text"] = user_text
        return [{"role": "user", "content": user_text}]

    monkeypatch.setattr(gateway, "invoke_llm", fake_invoke_llm)
    monkeypatch.setattr(server, "get_ai_settings", fake_settings)
    monkeypatch.setattr(server, "_build_messages", fake_build_messages)

    session = {
        "id": str(uuid.uuid4()),
        "turn_count": 5,
        "mode": "advanced",
        "prose_mode": "L",  # legacy value → story
    }
    _content, meta = asyncio.run(server._generate_turn(session, "Continue"))

    assert "[PROSE MODE: STORY]" in captured["user_text"]
    assert meta["prose_mode_requested"] == "story"
    assert meta["prose_mode"] == "story"
    assert meta["prose_budget"] == 2400


def test_low_cost_mode_caps_effective_mode_at_standard(monkeypatch):
    captured = {}

    async def fake_invoke_llm(**kwargs):
        captured["max_tokens"] = kwargs.get("max_tokens")
        return {
            "content": "irrelevant",
            "model_used": "test-model",
            "model_requested": "test-model",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    async def fake_settings():
        return {"max_tokens": 2048, "memory_depth": 3, "history_window": 30}

    async def fake_build_messages(session, user_text, memory_depth,
                                  history_window_fallback, **kwargs):
        captured["user_text"] = user_text
        return [{"role": "user", "content": user_text}]

    monkeypatch.setattr(gateway, "invoke_llm", fake_invoke_llm)
    monkeypatch.setattr(server, "get_ai_settings", fake_settings)
    monkeypatch.setattr(server, "_build_messages", fake_build_messages)

    session = {
        "id": str(uuid.uuid4()),
        "turn_count": 5,
        "mode": "advanced",
        "cost_mode": "low",
        "prose_mode": "cinematic",
    }
    _content, meta = asyncio.run(server._generate_turn(session, "Continue"))

    assert meta["prose_mode"] == "standard"
    assert "[PROSE MODE: STANDARD]" in captured["user_text"]
    # Low-cost token cap always wins over prose-mode floors.
    assert captured["max_tokens"] <= server.LOW_COST_MAX_TOKENS


def test_story_mode_raises_token_floor_under_normal_cost(monkeypatch):
    captured = {}

    async def fake_invoke_llm(**kwargs):
        captured["max_tokens"] = kwargs.get("max_tokens")
        return {
            "content": "irrelevant",
            "model_used": "test-model",
            "model_requested": "test-model",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    async def fake_settings():
        return {"max_tokens": 2048, "memory_depth": 3, "history_window": 30}

    async def fake_build_messages(session, user_text, memory_depth,
                                  history_window_fallback, **kwargs):
        return [{"role": "user", "content": user_text}]

    monkeypatch.setattr(gateway, "invoke_llm", fake_invoke_llm)
    monkeypatch.setattr(server, "get_ai_settings", fake_settings)
    monkeypatch.setattr(server, "_build_messages", fake_build_messages)

    session = {
        "id": str(uuid.uuid4()),
        "turn_count": 5,
        "mode": "advanced",
        "prose_mode": "story",
    }
    asyncio.run(server._generate_turn(session, "Continue"))
    assert captured["max_tokens"] == 3072


# ---------------------------------------------------------------------------
# Retry note (for non-length failures) carries the mode budget
# ---------------------------------------------------------------------------
def test_format_retry_note_uses_mode_budget():
    note = server._build_format_retry_instruction(
        "missing required choice labels: D", "", prose_mode="cinematic"
    )
    assert "(6-10 paragraphs, approx 3000-4000 characters)" in note
    note_default = server._build_format_retry_instruction(
        "missing required choice labels: D", ""
    )
    assert "(2-3 paragraphs, approx 700-1200 characters)" in note_default
