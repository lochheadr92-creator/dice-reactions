"""Mature renderer — reliability release: second-pass rendering is DISABLED.

The strict single-model provider path is still exercised (it must never step
to an automatic fallback), but ``render_mature_presentation`` must serve the
validated canonical narrative without any provider call, for every session
including those whose stored policy route is ``mature_pinned``.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import ai_service  # noqa: E402
import mature_content  # noqa: E402
import mature_rendering  # noqa: E402
import provider_budget  # noqa: E402


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


def _configure_renderer(monkeypatch):
    """Simulate a fully configured pinned renderer; the release switch must still win."""
    _enable_adult_env(monkeypatch)
    monkeypatch.setattr(
        mature_rendering, "get_mature_model_id", lambda: "x-ai/grok-pinned-2026-01"
    )
    monkeypatch.setattr(mature_rendering, "model_is_configured", lambda _model: True)


def _run_with_budget(coro):
    async def inner():
        async with provider_budget.active_budget(provider_budget.offline_budget()):
            return await coro

    return asyncio.run(inner())


def test_strict_model_call_never_steps_to_automatic_fallback(monkeypatch):
    calls = []

    async def fail_once(model_id, *_args, **_kwargs):
        calls.append(model_id)
        raise ai_service.AIServiceError(
            "unavailable", kind=ai_service.KIND_PROVIDER_UNAVAILABLE
        )

    monkeypatch.setattr(ai_service, "_call_model_once", fail_once)

    with pytest.raises(ai_service.AIServiceError):
        _run_with_budget(
            ai_service.chat_completion_with_meta(
                messages=[{"role": "user", "content": "render"}],
                primary_model="x-ai/grok-pinned-2026-01",
                fallback_chain=[ai_service.DEFAULT_MODEL],
                max_retries_per_model=1,
                allow_fallback=False,
            )
        )

    assert calls == ["x-ai/grok-pinned-2026-01"]


def test_release_switch_is_off():
    assert mature_rendering.MATURE_RENDERER_ENABLED is False


def test_renderer_reports_unavailable_even_when_fully_configured(monkeypatch):
    _configure_renderer(monkeypatch)
    assert mature_rendering.mature_renderer_is_configured() is False
    capabilities = mature_content.get_distribution_capabilities(
        renderer_configured=mature_rendering.mature_renderer_is_configured()
    )
    assert capabilities["mature_renderer_configured"] is False
    # Unrelated content capabilities are untouched by the renderer switch.
    assert capabilities["adult_mode_available"] is True


def test_configured_mature_route_serves_canonical_prose_without_provider_call(monkeypatch):
    _configure_renderer(monkeypatch)
    called = {"n": 0}

    async def rewrite_that_changes_events(**_kwargs):
        called["n"] += 1
        return {"content": "<narrative>Mara opens the gate with your key and escapes.</narrative>"}

    monkeypatch.setattr(
        mature_rendering, "chat_completion_strict_with_meta", rewrite_that_changes_events
    )

    canonical = "Mara waits outside the locked gate. The key remains in your pocket."
    result = asyncio.run(
        mature_rendering.render_mature_presentation(
            _session(), canonical, {"player_age": 30, "npcs": [{"name": "Mara", "age": 30}]}
        )
    )

    assert called["n"] == 0
    assert result.rendered is False
    assert result.narrative == canonical
    assert result.paragraphs == [canonical]
    assert result.rendering_policy["last_status"] == mature_rendering.RENDERER_DISABLED_STATUS
    assert result.rendering_policy["last_renderer"] == "standard"
    # Stored route preference is preserved, not rewritten.
    assert result.rendering_policy["route"] == "mature_pinned"


def test_standard_sessions_are_unchanged(monkeypatch):
    _configure_renderer(monkeypatch)
    session = {"mature_content": mature_content.default_mature_content(), "rendering_policy": {}}
    result = asyncio.run(
        mature_rendering.render_mature_presentation(session, "Canonical safe prose.", {})
    )
    assert result.rendered is False
    assert result.narrative == "Canonical safe prose."
    assert result.rendering_policy["last_status"] == "standard"


def test_disabled_renderer_never_reaches_provider_even_without_budget(monkeypatch):
    """No active provider budget exists here; a provider call would fail closed.

    The renderer must return before that point, proving it never attempts one.
    """
    _configure_renderer(monkeypatch)
    result = asyncio.run(
        mature_rendering.render_mature_presentation(
            _session(), "They sat beside the fire.", {"npcs": []}
        )
    )
    assert result.rendered is False
    assert result.narrative == "They sat beside the fire."
