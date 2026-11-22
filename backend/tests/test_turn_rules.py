"""Always-on turn rules, the 1-3 paragraph default, and paragraph-safe mature rendering.

Regression (session fd9e697b, 2026-11-23): three turns at one table on one
question, in unexplained invented terms, shown as a single block of text because
the mature renderer collapsed five paragraphs into one.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import creation_contract  # noqa: E402
import gateway  # noqa: E402
import mature_rendering  # noqa: E402
import prose_modes  # noqa: E402
import server  # noqa: E402
import turn_rules  # noqa: E402


def test_turn_rules_cover_stakes_words_movement_and_choices():
    rules = turn_rules.TURN_CLARITY_RULES
    assert "these win" in rules
    for heading in ("1. Plain stakes.", "2. Plain words.", "3. Movement.", "4. Choices."):
        assert heading in rules
    assert "what they stand to lose or gain" in rules
    assert "the same sentence says what it is" in rules
    assert "Never offer a choice that repeats what the player just did" in rules
    assert "three turns must be resolved or left" in rules


def _generated_user_text(monkeypatch, session_extra):
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

    async def fake_build_messages(session, user_text, memory_depth, history_window_fallback, **kwargs):
        captured["user_text"] = user_text
        return [{"role": "user", "content": user_text}]

    monkeypatch.setattr(gateway, "invoke_llm", fake_invoke_llm)
    monkeypatch.setattr(server, "get_ai_settings", fake_settings)
    monkeypatch.setattr(server, "_build_messages", fake_build_messages)
    session = {"id": str(uuid.uuid4()), "mode": "advanced", **session_extra}
    asyncio.run(server._generate_turn(session, "Continue"))
    return captured["user_text"]


def test_turn_rules_are_sent_on_every_turn_after_the_prose_directive(monkeypatch):
    for extra in ({"turn_count": 0}, {"turn_count": 7, "prose_mode": "story"}):
        text = _generated_user_text(monkeypatch, extra)
        assert turn_rules.TURN_CLARITY_RULES in text
        assert text.index("[PROSE MODE:") < text.index("[TURN RULES")


def test_paragraph_ranges_match_the_s_m_l_xl_setting():
    ranges = {
        name: (mode.min_paragraphs, mode.max_paragraphs)
        for name, mode in prose_modes.PROSE_MODES.items()
    }
    assert ranges == {"brief": (1, 2), "standard": (2, 4), "story": (4, 6), "cinematic": (6, 8)}
    for alias, name in (("S", "brief"), ("M", "standard"), ("L", "story"), ("XL", "cinematic")):
        assert prose_modes.resolve_prose_mode_name(alias) == name
        assert prose_modes.is_known_mode(alias)
    assert not prose_modes.is_known_mode("huge")
    assert not prose_modes.is_known_mode("")
    for mode in prose_modes.PROSE_MODES.values():
        assert f"{mode.min_paragraphs}-{mode.max_paragraphs}" in mode.directive


def test_system_prompt_puts_readability_first_and_limits_mystery():
    prompt = server.STORY_ENGINE_SYSTEM_PROMPT
    assert prompt.index("1. Readability") < prompt.index("3. Atmosphere")
    assert "Never be unclear about what is happening in front of them" in prompt
    assert "Preserve mystery and incomplete information." not in prompt


def test_premise_lines_say_the_premise_leads():
    contract = creation_contract.build_creation_contract(
        genre="post-apocalyptic",
        role="local resident",
        custom_world_setup={"creationFlow": "advanced", "premise": "creatures came through a rift"},
    )
    opening = "\n".join(creation_contract.build_opening_setup_lines(contract))
    later = creation_contract.build_later_turn_creation_directive(contract)
    assert "the premise wins" in opening
    assert "active in the first scene, not background" in opening
    assert "The premise decides what this story is about" in later
    assert "never replace the premise" in later


def test_mature_rendering_keeps_paragraph_breaks(monkeypatch):
    paragraphs = ["First paragraph.", "Second paragraph.", "Third paragraph."]
    seen = {}

    async def fake_render(session, canonical_narrative, rolling):
        seen["text"] = canonical_narrative
        parts = mature_rendering._paragraphs(canonical_narrative)
        rendered = [part + " Rendered." for part in parts]
        return mature_rendering.MatureRenderResult(
            "\n\n".join(rendered), rendered, {"last_status": "rendered_mature"}, rendered=True
        )

    monkeypatch.setattr(mature_rendering, "render_mature_presentation", fake_render)
    monkeypatch.setattr(server, "_full_validate", lambda *args, **kwargs: (True, "", ""))
    parsed = server.ParsedTurn(
        narrative="\n".join(paragraphs),
        paragraphs=list(paragraphs),
        choices=[{"label": c, "text": c} for c in "ABCD"],
        state={},
        ledger={},
        rolling_state={},
        raw="",
    )
    result, _policy = asyncio.run(server._apply_presentation_rendering({}, parsed, {}, "Wait"))

    assert seen["text"] == "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    assert len(result.paragraphs) == 3
    assert result.narrative == "\n".join(result.paragraphs)
    assert result.paragraphs[2] == "Third paragraph. Rendered."


# --- writing style and thinking effort (Settings page) -----------------------


def test_writing_style_directive_is_sent_for_plain_and_rich_only(monkeypatch):
    plain = _generated_user_text(monkeypatch, {"turn_count": 3, "prose_style": "plain"})
    assert "[WRITING STYLE: PLAIN]" in plain
    assert plain.index("[WRITING STYLE: PLAIN]") < plain.index("[TURN RULES")

    rich = _generated_user_text(monkeypatch, {"turn_count": 3, "prose_style": "rich"})
    assert "[WRITING STYLE: RICH]" in rich

    for extra in ({"turn_count": 3}, {"turn_count": 3, "prose_style": "balanced"}, {"turn_count": 3, "prose_style": "purple"}):
        assert "[WRITING STYLE:" not in _generated_user_text(monkeypatch, extra)


def test_unknown_style_resolves_to_balanced():
    assert prose_modes.resolve_prose_style("PLAIN") == "plain"
    assert prose_modes.resolve_prose_style(None) == "balanced"
    assert prose_modes.resolve_prose_style("purple") == "balanced"
    assert prose_modes.build_style_directive("balanced") == ""


def test_story_effort_applies_only_when_a_level_is_configured(monkeypatch):
    import ai_service

    def effort_in_fresh_context(configured, story):
        async def run():
            monkeypatch.setattr(ai_service, "OPENAI_DIRECT_REASONING_EFFORT", configured)
            ai_service.use_story_reasoning_effort(story)
            return ai_service.effective_direct_reasoning_effort()

        return asyncio.run(run())

    assert effort_in_fresh_context("low", "high") == "high"
    assert effort_in_fresh_context("low", None) == "low"
    assert effort_in_fresh_context("low", "nonsense") == "low"
    # Thinking switched off for a local model must stay off.
    assert effort_in_fresh_context("none", "high") == "none"
    # Not configured: the provider may not accept the parameter at all.
    assert effort_in_fresh_context("", "high") == ""


def test_story_effort_does_not_leak_between_requests(monkeypatch):
    import ai_service

    monkeypatch.setattr(ai_service, "OPENAI_DIRECT_REASONING_EFFORT", "low")

    async def first():
        ai_service.use_story_reasoning_effort("high")
        return ai_service.effective_direct_reasoning_effort()

    async def second():
        return ai_service.effective_direct_reasoning_effort()

    assert asyncio.run(first()) == "high"
    assert asyncio.run(second()) == "low"


def test_validated_turn_applies_the_story_effort(monkeypatch):
    import ai_service

    seen = {}

    async def fake_generate_turn(session, user_text, **kwargs):
        seen["effort"] = ai_service.effective_direct_reasoning_effort()
        raise RuntimeError("stop after the effort is read")

    monkeypatch.setattr(ai_service, "OPENAI_DIRECT_REASONING_EFFORT", "low")
    monkeypatch.setattr(server, "_generate_turn", fake_generate_turn)

    async def run():
        try:
            await server._generate_validated_turn({"turn_count": 2, "thinking_effort": "medium"}, "Continue")
        except RuntimeError:
            pass

    asyncio.run(run())
    assert seen["effort"] == "medium"
