from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import ai_service  # noqa: E402
import mature_content  # noqa: E402
import mature_rendering  # noqa: E402


def _enable_adult_env(monkeypatch):
    monkeypatch.setenv("DISTRIBUTION_CHANNEL", "development")
    monkeypatch.setenv("ENABLE_MATURE_CONTENT", "true")
    monkeypatch.setenv("ENABLE_MATURE_SEXUAL_CONTENT", "true")
    monkeypatch.setenv("ENABLE_MATURE_NONCONSENSUAL_CONTENT", "true")
    monkeypatch.setenv("ENABLE_GRAPHIC_SEXUAL_CONTENT", "true")


def _session():
    preferences = {
        **mature_content.default_mature_content(),
        "adult_mode_enabled": True,
        "adult_age_confirmed": True,
        "violence_level": "graphic",
    }
    return {
        "mature_content": preferences,
        "rendering_policy": {
            "route": "mature_pinned",
            "failure_mode": "safe_standard",
            "sexual_age_boundary": "explicit_18_plus_only",
        },
    }


def test_strict_model_call_never_steps_to_automatic_fallback(monkeypatch):
    calls = []

    async def fail_once(model_id, *_args, **_kwargs):
        calls.append(model_id)
        raise ai_service.AIServiceError(
            "unavailable", kind=ai_service.KIND_PROVIDER_UNAVAILABLE
        )

    monkeypatch.setattr(ai_service, "_call_model_once", fail_once)

    with pytest.raises(ai_service.AIServiceError):
        asyncio.run(
            ai_service.chat_completion_with_meta(
                messages=[{"role": "user", "content": "render"}],
                primary_model="x-ai/grok-pinned-2026-01",
                fallback_chain=[ai_service.DEFAULT_MODEL],
                max_retries_per_model=1,
                allow_fallback=False,
            )
        )

    assert calls == ["x-ai/grok-pinned-2026-01"]


def test_configured_mature_route_rerenders_prose_only(monkeypatch):
    _enable_adult_env(monkeypatch)
    monkeypatch.setattr(
        mature_rendering, "get_mature_model_id", lambda: "x-ai/grok-pinned-2026-01"
    )
    monkeypatch.setattr(mature_rendering, "model_is_configured", lambda _model: True)
    captured = {}

    async def fake_completion(**kwargs):
        captured.update(kwargs)
        return {"content": "<narrative>The rain struck harder against the broken gate.</narrative>"}

    monkeypatch.setattr(
        mature_rendering, "chat_completion_strict_with_meta", fake_completion
    )

    result = asyncio.run(
        mature_rendering.render_mature_presentation(
            _session(),
            "The rain struck the broken gate.",
            {"player_age": 30, "npcs": []},
        )
    )

    assert result.rendered is True
    assert result.narrative == "The rain struck harder against the broken gate."
    assert result.rendering_policy["last_status"] == "rendered_mature"
    assert captured["model"] == "x-ai/grok-pinned-2026-01"
    assert "Permissions are ceilings, never instructions" in captured["messages"][0]["content"]


def test_missing_or_unpinned_mature_model_falls_back_without_call(monkeypatch):
    _enable_adult_env(monkeypatch)
    monkeypatch.setattr(mature_rendering, "get_mature_model_id", lambda: "x-ai/grok/latest")
    called = False

    async def should_not_call(**_kwargs):
        nonlocal called
        called = True
        return {"content": "unexpected"}

    monkeypatch.setattr(
        mature_rendering, "chat_completion_strict_with_meta", should_not_call
    )

    result = asyncio.run(
        mature_rendering.render_mature_presentation(
            _session(), "Canonical safe prose.", {"player_age": 30, "npcs": []}
        )
    )

    assert called is False
    assert result.rendered is False
    assert result.narrative == "Canonical safe prose."
    assert result.rendering_policy["last_status"] == "safe_fallback_renderer_unavailable"


def test_provider_failure_keeps_canonical_prose(monkeypatch):
    _enable_adult_env(monkeypatch)
    monkeypatch.setattr(
        mature_rendering, "get_mature_model_id", lambda: "x-ai/grok-pinned-2026-01"
    )
    monkeypatch.setattr(mature_rendering, "model_is_configured", lambda _model: True)

    async def fail(**_kwargs):
        raise ai_service.AIServiceError("provider down")

    monkeypatch.setattr(mature_rendering, "chat_completion_strict_with_meta", fail)
    result = asyncio.run(
        mature_rendering.render_mature_presentation(
            _session(), "Canonical safe prose.", {"player_age": 30, "npcs": []}
        )
    )

    assert result.rendered is False
    assert result.narrative == "Canonical safe prose."
    assert result.rendering_policy["last_status"] == "safe_fallback_provider_error"


def test_renderer_output_cannot_introduce_sexual_context_with_ambiguous_ages(monkeypatch):
    _enable_adult_env(monkeypatch)
    monkeypatch.setattr(
        mature_rendering, "get_mature_model_id", lambda: "x-ai/grok-pinned-2026-01"
    )
    monkeypatch.setattr(mature_rendering, "model_is_configured", lambda _model: True)

    async def unsafe_output(**_kwargs):
        return {"content": "<narrative>They had sex beside the fire.</narrative>"}

    monkeypatch.setattr(
        mature_rendering, "chat_completion_strict_with_meta", unsafe_output
    )
    result = asyncio.run(
        mature_rendering.render_mature_presentation(
            _session(), "They sat beside the fire.", {"npcs": []}
        )
    )

    assert result.rendered is False
    assert result.narrative == "They sat beside the fire."
    assert result.rendering_policy["last_status"] == "safe_fallback_age_boundary"
