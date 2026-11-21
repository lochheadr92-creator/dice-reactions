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
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_config  # noqa: E402
import ai_service  # noqa: E402


# --------------------------------------------------------------------------- #
# Routing — default stays OpenRouter
# --------------------------------------------------------------------------- #
def test_default_model_routes_to_openrouter():
    r = ai_service.resolve_provider_route(ai_service.DEFAULT_MODEL)
    assert r["provider"] == "openrouter"
    assert r["base_url"] == ai_service.OPENROUTER_BASE_URL
    assert r["api_model"] == ai_config.MODEL_SONNET
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


def test_default_and_fallback_models_use_curated_catalogue():
    assert ai_service.DEFAULT_MODEL == ai_config.MODEL_SONNET
    assert ai_service.FALLBACK_MODELS == [
        ai_config.MODEL_SONNET,
        ai_config.MODEL_DEEPSEEK,
    ]


def test_model_config_remains_env_overridable(monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL", "custom/default-model")
    monkeypatch.setenv("FALLBACK_MODELS", "custom/default-model,custom/fallback-model")
    reloaded = importlib.reload(ai_config)
    try:
        assert reloaded.DEFAULT_MODEL == "custom/default-model"
        assert reloaded.FALLBACK_MODELS == [
            "custom/default-model",
            "custom/fallback-model",
        ]
    finally:
        monkeypatch.delenv("DEFAULT_MODEL", raising=False)
        monkeypatch.delenv("FALLBACK_MODELS", raising=False)
        importlib.reload(ai_config)


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


def test_catalogue_stays_curated_when_openai_key_configured(monkeypatch):
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "sk-test-not-real")
    ids = {m["id"] for m in ai_service.get_supported_models()}
    assert len(ids) == 3
    assert not any(i.startswith(ai_service.OPENAI_PROVIDER_PREFIX) for i in ids)
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
                ai_service.DEFAULT_MODEL,
                [{"role": "user", "content": "hi"}],
                0.7,
                16,
            )
        )
    assert "OPENROUTER_API_KEY is not configured" in str(ei.value)
    assert ei.value.kind == ai_service.KIND_OTHER


# --------------------------------------------------------------------------- #
# Optional reasoning_effort on the direct route (local Ollama thinking models)
# --------------------------------------------------------------------------- #
class _CapturingClient:
    sent = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        import httpx

        _CapturingClient.sent.append({"url": url, "json": json})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})


def _send(monkeypatch, model_id, effort):
    _CapturingClient.sent = []
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", _CapturingClient)
    monkeypatch.setattr(ai_service, "OPENAI_DIRECT_REASONING_EFFORT", effort)
    monkeypatch.setattr(ai_service, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(ai_service, "NVIDIA_API_KEY", "")
    asyncio.run(
        ai_service._call_model_once(model_id, [{"role": "user", "content": "x"}], 0.5, 16)
    )
    return _CapturingClient.sent[0]["json"]


def test_direct_route_sends_configured_reasoning_effort(monkeypatch):
    payload = _send(monkeypatch, "openai-direct/dice-gemma4-12b", "none")
    assert payload["reasoning_effort"] == "none"
    assert payload["model"] == "dice-gemma4-12b"


def test_reasoning_effort_is_not_sent_when_unset(monkeypatch):
    payload = _send(monkeypatch, "openai-direct/dice-gemma4-12b", "")
    assert "reasoning_effort" not in payload


def test_reasoning_effort_never_reaches_openrouter(monkeypatch):
    payload = _send(monkeypatch, ai_config.MODEL_SONNET, "none")
    assert "reasoning_effort" not in payload


# --------------------------------------------------------------------------- #
# One leading system message on the direct route (Qwen templates in Ollama)
# --------------------------------------------------------------------------- #
def test_merge_leading_system_messages_keeps_order_and_later_messages():
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "system", "content": "pacing"},
        {"role": "system", "content": "scenario"},
        {"role": "user", "content": "act"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "retry note"},
    ]
    merged = ai_service.merge_leading_system_messages(messages)
    assert merged[0] == {"role": "system", "content": "rules\n\npacing\n\nscenario"}
    assert merged[1:] == messages[3:]
    assert messages[1]["content"] == "pacing"  # input not mutated


def test_merge_is_a_no_op_with_one_or_no_system_message():
    one = [{"role": "system", "content": "rules"}, {"role": "user", "content": "act"}]
    none = [{"role": "user", "content": "act"}]
    assert ai_service.merge_leading_system_messages(one) == one
    assert ai_service.merge_leading_system_messages(none) == none


def _send_messages(monkeypatch, model_id, messages):
    _CapturingClient.sent = []
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", _CapturingClient)
    monkeypatch.setattr(ai_service, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(ai_service, "NVIDIA_API_KEY", "")
    asyncio.run(ai_service._call_model_once(model_id, messages, 0.5, 16))
    return _CapturingClient.sent[0]["json"]["messages"]


def test_direct_route_sends_one_system_message_and_openrouter_is_unchanged(monkeypatch):
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "system", "content": "pacing"},
        {"role": "user", "content": "act"},
    ]
    direct = _send_messages(monkeypatch, "openai-direct/dice-qwen122", messages)
    assert [m["role"] for m in direct] == ["system", "user"]
    openrouter = _send_messages(monkeypatch, ai_config.MODEL_SONNET, messages)
    assert openrouter == messages


# --------------------------------------------------------------------------- #
# Assistant prefill on the direct route (forces rolling_state first on Ollama)
# --------------------------------------------------------------------------- #
class _ReplyClient(_CapturingClient):
    reply = "ok"

    async def post(self, url, json=None, headers=None):
        import httpx

        _CapturingClient.sent.append({"url": url, "json": json})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": _ReplyClient.reply}}]}
        )


def _send_prefill(monkeypatch, model_id, *, enabled, reply, prefill="<rolling_state>\n{"):
    _CapturingClient.sent = []
    _ReplyClient.reply = reply
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", _ReplyClient)
    monkeypatch.setattr(ai_service, "OPENAI_DIRECT_ASSISTANT_PREFILL", enabled)
    monkeypatch.setattr(ai_service, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(ai_service, "NVIDIA_API_KEY", "")
    content, telem = asyncio.run(
        ai_service._call_model_once(
            model_id,
            [{"role": "system", "content": "rules"}, {"role": "user", "content": "act"}],
            0.5,
            16,
            assistant_prefill=prefill,
        )
    )
    return _CapturingClient.sent[0]["json"]["messages"], content, telem


def test_prefill_sent_and_restored_on_direct_route_when_enabled(monkeypatch):
    sent, content, telem = _send_prefill(
        monkeypatch,
        "openai-direct/dice-qwen36",
        enabled=True,
        reply='\n  "scene": "petrol station"\n}\n</rolling_state>\n<narrative>x</narrative>',
    )
    assert sent[-1] == {"role": "assistant", "content": "<rolling_state>\n{"}
    assert content.startswith('<rolling_state>\n{\n  "scene"')
    assert telem["assistant_prefill"] is True


def test_prefill_not_doubled_when_server_echoes_whole_message(monkeypatch):
    echoed = '<rolling_state>\n{"scene": "x"}</rolling_state>'
    _sent, content, _telem = _send_prefill(
        monkeypatch, "openai-direct/dice-qwen36", enabled=True, reply=echoed
    )
    assert content == echoed


def test_prefill_not_sent_when_disabled(monkeypatch):
    sent, content, telem = _send_prefill(
        monkeypatch, "openai-direct/dice-qwen36", enabled=False, reply="plain"
    )
    assert [m["role"] for m in sent] == ["system", "user"]
    assert content == "plain"
    assert telem["assistant_prefill"] is False


def test_prefill_never_reaches_openrouter(monkeypatch):
    sent, content, _telem = _send_prefill(
        monkeypatch, ai_config.MODEL_SONNET, enabled=True, reply="plain"
    )
    assert [m["role"] for m in sent] == ["system", "user"]
    assert content == "plain"


def test_turn_generation_requests_rolling_state_prefill(monkeypatch):
    import uuid

    import gateway
    import server

    captured = {}

    async def fake_invoke_llm(**kwargs):
        captured.update(kwargs)
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
    session = {"id": str(uuid.uuid4()), "turn_count": 5, "mode": "advanced"}
    asyncio.run(server._generate_turn(session, "Continue"))
    assert captured["assistant_prefill"] == server.TURN_REPLY_PREFILL
    assert server.TURN_REPLY_PREFILL.startswith("<rolling_state>")
    # Minified start at the first key of the required shape: no newline or
    # indentation for the model to continue as pretty-printed JSON.
    assert server.TURN_REPLY_PREFILL == '<rolling_state>{"scene":"'
    assert "\n" not in server.TURN_REPLY_PREFILL


def test_prefilled_reply_parses_as_a_normal_turn():
    import server

    reply = (
        server.TURN_REPLY_PREFILL
        + 'ridge","character":"cold","objectives":["reach shelter"]}</rolling_state>\n'
        "<narrative>Wind scours the ridge.</narrative>\n"
        "<choices>\nA. Climb down\nB. Wait\nC. Call out\nD. Turn back\n</choices>\n"
        "<state>\nHealth: stable\nPressure: cold\nPosition: ridge\n</state>\n"
        "<ledger>\nCarried: staff\n</ledger>\n"
    )
    parsed = server.parse_turn(reply)
    assert parsed.rolling_state["scene"] == "ridge"
    assert [c["label"] for c in parsed.choices] == ["A", "B", "C", "D"]


# --------------------------------------------------------------------------- #
# OS trust store for TLS (antivirus HTTPS inspection, e.g. Norton)
# --------------------------------------------------------------------------- #
def test_tls_verify_defaults_to_httpx_certifi():
    assert ai_service._build_tls_verify(False) is True


def test_tls_verify_uses_os_trust_store_when_enabled():
    import ssl

    pytest.importorskip("truststore")
    ctx = ai_service._build_tls_verify(True)
    assert isinstance(ctx, ssl.SSLContext)
    assert type(ctx).__module__.startswith("truststore")


def test_provider_client_receives_configured_tls_verify(monkeypatch):
    seen = {}

    class _Client(_CapturingClient):
        def __init__(self, *args, **kwargs):
            seen.update(kwargs)

    sentinel = object()
    monkeypatch.setattr(ai_service, "_TLS_VERIFY", sentinel)
    _CapturingClient.sent = []
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "test-key")
    asyncio.run(
        ai_service._call_model_once("openai-direct/gpt-4o", [{"role": "user", "content": "x"}], 0.5, 16)
    )
    assert seen["verify"] is sentinel


# --------------------------------------------------------------------------- #
# OpenRouter reasoning effort (Grok 4.x thinking cost/latency)
# --------------------------------------------------------------------------- #
def _send_openrouter_effort(monkeypatch, model_id, effort):
    monkeypatch.setattr(ai_service, "OPENROUTER_REASONING_EFFORT", effort)
    return _send(monkeypatch, model_id, "")


def test_openrouter_route_sends_configured_reasoning_effort(monkeypatch):
    payload = _send_openrouter_effort(monkeypatch, "x-ai/grok-4.7", "low")
    assert payload["reasoning"] == {"effort": "low"}
    assert "reasoning_effort" not in payload


def test_openrouter_reasoning_not_sent_when_unset(monkeypatch):
    payload = _send_openrouter_effort(monkeypatch, "x-ai/grok-4.7", "")
    assert "reasoning" not in payload


def test_openrouter_reasoning_never_reaches_direct_route(monkeypatch):
    payload = _send_openrouter_effort(monkeypatch, "openai-direct/gpt-4o", "low")
    assert "reasoning" not in payload

