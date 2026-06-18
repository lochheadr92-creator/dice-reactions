"""
Provider-selection unit tests for the optional, opt-in OpenAI route.

Hard guarantees verified here (no live/paid API calls are made — every test
either inspects pure routing logic or exercises the missing-key guard, which
raises BEFORE any network request):

  * OpenRouter remains the default provider for every existing model id,
    including OpenRouter's own "openai/..." catalogue ids.
  * Direct OpenAI is used ONLY for explicitly namespaced "openai-direct/..." ids.
  * OpenAI models are only offered (and only pass admin validation) when
    OPENAI_API_KEY is configured.
  * Missing-key behaviour raises a clear error for each provider.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_service  # noqa: E402


# --------------------------------------------------------------------------- #
# Routing — default stays OpenRouter
# --------------------------------------------------------------------------- #
def test_default_model_routes_to_openrouter():
    r = ai_service.resolve_provider_route("anthropic/claude-3-5-haiku")
    assert r["provider"] == "openrouter"
    assert r["base_url"] == ai_service.OPENROUTER_BASE_URL
    assert r["api_model"] == "anthropic/claude-3-5-haiku"
    assert r["key_env"] == "OPENROUTER_API_KEY"
    # OpenRouter-specific attribution headers must be preserved unchanged.
    assert "HTTP-Referer" in r["extra_headers"]
    assert "X-Title" in r["extra_headers"]


def test_openrouter_native_openai_namespace_is_not_direct_openai():
    # OpenRouter's own "openai/gpt-4o" id must continue routing to OpenRouter,
    # NOT to api.openai.com.
    r = ai_service.resolve_provider_route("openai/gpt-4o")
    assert r["provider"] == "openrouter"
    assert r["api_model"] == "openai/gpt-4o"
    assert r["base_url"] == ai_service.OPENROUTER_BASE_URL


def test_default_model_constant_is_openrouter():
    # Smallest-switch guarantee: the engine default is an OpenRouter model.
    assert not ai_service.DEFAULT_MODEL.startswith(ai_service.OPENAI_PROVIDER_PREFIX)


# --------------------------------------------------------------------------- #
# Routing — OpenAI only via explicit opt-in namespace
# --------------------------------------------------------------------------- #
def test_openai_direct_namespace_routes_to_openai(monkeypatch):
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "sk-test-not-real")
    r = ai_service.resolve_provider_route("openai-direct/gpt-4o")
    assert r["provider"] == "openai"
    assert r["base_url"] == ai_service.OPENAI_BASE_URL
    assert r["api_model"] == "gpt-4o"  # namespace stripped before sending upstream
    assert r["key_env"] == "OPENAI_API_KEY"
    # No OpenRouter attribution headers leak to OpenAI.
    assert r["extra_headers"] == {}


def test_openai_base_url_is_openai_domain():
    assert ai_service.OPENAI_BASE_URL.startswith("https://api.openai.com")


# --------------------------------------------------------------------------- #
# Catalogue gating — OpenAI is selectable only when configured
# --------------------------------------------------------------------------- #
def test_catalogue_excludes_openai_when_unconfigured(monkeypatch):
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "")
    ids = {m["id"] for m in ai_service.get_supported_models()}
    assert not any(i.startswith(ai_service.OPENAI_PROVIDER_PREFIX) for i in ids)
    # OpenRouter catalogue is unaffected.
    assert ai_service.DEFAULT_MODEL in ids


def test_catalogue_includes_openai_when_configured(monkeypatch):
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "sk-test-not-real")
    ids = {m["id"] for m in ai_service.get_supported_models()}
    assert any(i.startswith(ai_service.OPENAI_PROVIDER_PREFIX) for i in ids)
    # OpenRouter models remain present (default provider unchanged).
    assert ai_service.DEFAULT_MODEL in ids


# --------------------------------------------------------------------------- #
# Missing-key behaviour — raises before any network call
# --------------------------------------------------------------------------- #
def test_openai_missing_key_raises_clear_error(monkeypatch):
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "")
    with pytest.raises(ai_service.AIServiceError) as ei:
        asyncio.run(
            ai_service._call_model_once(
                "openai-direct/gpt-4o",
                [{"role": "user", "content": "hi"}],
                0.7,
                16,
            )
        )
    assert "OPENAI_API_KEY is not configured" in str(ei.value)
    assert ei.value.kind == ai_service.KIND_OTHER


def test_openrouter_missing_key_still_raises(monkeypatch):
    # Regression guard: the existing OpenRouter missing-key contract is preserved.
    monkeypatch.setattr(ai_service, "OPENROUTER_API_KEY", "")
    with pytest.raises(ai_service.AIServiceError) as ei:
        asyncio.run(
            ai_service._call_model_once(
                "anthropic/claude-3-5-haiku",
                [{"role": "user", "content": "hi"}],
                0.7,
                16,
            )
        )
    assert "OPENROUTER_API_KEY is not configured" in str(ei.value)
    assert ei.value.kind == ai_service.KIND_OTHER
