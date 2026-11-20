"""
Centralized AI service layer.

All AI requests in the application route through this module.
Currently backed by OpenRouter chat completions API. Designed to make
swapping providers or models trivial — just adjust ``chat_completion``.

Features:
    * OpenRouter chat completions over httpx (async)
    * Default model: anthropic/claude-sonnet-4.5  (env-overridable)
    * Safe fallback chain: Sonnet → DeepSeek
    * Adjustable model / temperature / max_tokens per call
    * Retry with exponential backoff on transient failures (5xx, 408, 429)
    * Error classification for fallback decisions
    * Per-call telemetry (latency, tokens, provider status, fallback events)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

import provider_budget

from ai_config import (
    AUTOMATIC_FALLBACK_MODELS,
    DEFAULT_MODEL,
    FALLBACK_MODELS,
    MODEL_QWEN_UNCENSORED,
    MAX_RETRIES,
    PROVIDER_TIMEOUT,
    build_automatic_fallback_chain,
    normalize_runtime_model,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read from environment with sensible defaults)
# ---------------------------------------------------------------------------
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/")

# Optional direct OpenAI provider key (backend-only secret). Read here so the
# variable is a recognised configuration value, but it is NOT wired into any
# LLM call path — OpenRouter remains the sole active provider. The value is
# never returned in API responses, logged, or exposed to the Expo client.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# Base URL for the optional direct-OpenAI provider (OpenAI-compatible /chat/completions).
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
# Optional NVIDIA NIM key (also OpenAI-compatible). Used for openai-direct/* models
# when OPENAI_API_KEY is empty, or as an explicit alternate credential.
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "").strip()
NVIDIA_BASE_URL = os.environ.get(
    "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
).rstrip("/")
# A model is routed to direct OpenAI ONLY when its id carries this explicit,
# opt-in namespace (e.g. "openai-direct/gpt-4o"). Every other id stays on OpenRouter,
# including OpenRouter's own "openai/..." catalogue ids.
OPENAI_PROVIDER_PREFIX = "openai-direct/"
# Optional "reasoning_effort" sent ONLY on the direct OpenAI-compatible route
# (openai-direct/* ids). Local Ollama thinking models answer with an empty
# content field when their thinking uses up max_tokens; "none" turns thinking
# off there. Unset (the default) sends nothing, so OpenRouter and real OpenAI
# requests are unchanged.
OPENAI_DIRECT_REASONING_EFFORT = os.environ.get("OPENAI_DIRECT_REASONING_EFFORT", "").strip()
# Sent as OpenRouter's unified ``reasoning: {"effort": ...}`` on the OpenRouter
# route only (e.g. "low" for Grok 4.x, which otherwise spends many billed
# thinking tokens and seconds per turn). Unset: OpenRouter/model default.
OPENROUTER_REASONING_EFFORT = os.environ.get("OPENROUTER_REASONING_EFFORT", "").strip()
# When on, callers' ``assistant_prefill`` is sent on the openai-direct route as
# a trailing assistant message that the server continues (Ollama does; real
# OpenAI does not, so this stays off by default). The prefill is put back on
# the front of the returned content.
# Antivirus / corporate TLS inspection (e.g. Norton Web Shield) re-signs HTTPS
# with a root certificate only the OS trust store holds, so certifi-based
# verification fails with CERTIFICATE_VERIFY_FAILED. When on, provider calls
# verify against the OS trust store (truststore). Off: httpx default (certifi).
SSL_USE_SYSTEM_TRUST_STORE = os.environ.get(
    "SSL_USE_SYSTEM_TRUST_STORE", ""
).strip().lower() in ("1", "true", "yes", "on")


def _build_tls_verify(use_system_store: bool):
    """httpx ``verify`` value. Raises ImportError if the store is requested
    but truststore is missing, so a misconfiguration fails at startup."""
    if not use_system_store:
        return True
    import ssl

    import truststore

    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


_TLS_VERIFY = _build_tls_verify(SSL_USE_SYSTEM_TRUST_STORE)

OPENAI_DIRECT_ASSISTANT_PREFILL = os.environ.get(
    "OPENAI_DIRECT_ASSISTANT_PREFILL", ""
).strip().lower() in ("1", "true", "yes", "on")

DEFAULT_TEMPERATURE = float(os.environ.get("DEFAULT_TEMPERATURE", "0.85"))
DEFAULT_MAX_TOKENS = int(os.environ.get("DEFAULT_MAX_TOKENS", "2048"))
DEFAULT_HISTORY_WINDOW = int(os.environ.get("DEFAULT_HISTORY_WINDOW", "40"))
DEFAULT_TIMEOUT_SECONDS = PROVIDER_TIMEOUT

APP_PUBLIC_URL = os.environ.get(
    "APP_PUBLIC_URL", "https://dice-reaction-story-engine.example"
)
APP_TITLE = os.environ.get("APP_TITLE", "Dice Reaction Story Engine")

# ---------------------------------------------------------------------------
# Supported model catalogue — surfaced to admin UI for switching
# ---------------------------------------------------------------------------
SUPPORTED_MODELS: List[Dict[str, Any]] = [
    {
        "id": "anthropic/claude-sonnet-4.5",
        "label": "Claude Sonnet 4.5",
        "context": 1000000,
        "note": "Default · primary quality model · 1M context",
    },
    {
        "id": "deepseek/deepseek-chat-v3-0324",
        "label": "DeepSeek V3",
        "context": 164000,
        "note": "First automatic fallback · cost-saving rescue",
    },
    {
        "id": "anthracite-org/magnum-v4-72b",
        "label": "Magnum v4 72B · Qwen UNCENSORED",
        "context": 32768,
        "note": "Explicit selection only · Qwen2.5 creative · never auto-fallback",
    },
]


class AIServiceError(Exception):
    """Raised when the underlying AI provider call fails permanently."""

    def __init__(self, message: str, kind: str = "other"):
        super().__init__(message)
        self.kind = kind


def get_supported_models() -> List[Dict[str, Any]]:
    """Return the curated admin model catalogue."""
    return list(SUPPORTED_MODELS)


def get_default_settings() -> Dict[str, Any]:
    return {
        "model": DEFAULT_MODEL,
        "temperature": DEFAULT_TEMPERATURE,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "history_window": DEFAULT_HISTORY_WINDOW,
        "fallback_models": list(FALLBACK_MODELS),
    }


def is_configured() -> bool:
    return bool(OPENROUTER_API_KEY or OPENAI_API_KEY or NVIDIA_API_KEY)


def openai_is_configured() -> bool:
    """Report whether a direct OpenAI-compatible key is present (boolean only —
    never returns or logs the value). Includes NVIDIA NIM when configured."""
    return bool(OPENAI_API_KEY or NVIDIA_API_KEY)


def _direct_openai_compatible_credentials() -> Tuple[str, str, str]:
    """Return (api_key, base_url, key_env) for openai-direct/* models.

    Prefer NVIDIA_API_KEY when set (including over a local Ollama placeholder).
    Otherwise use OPENAI_API_KEY + OPENAI_BASE_URL (Ollama or real OpenAI).
    """
    if NVIDIA_API_KEY:
        return NVIDIA_API_KEY, NVIDIA_BASE_URL, "NVIDIA_API_KEY"
    if OPENAI_API_KEY:
        return OPENAI_API_KEY, OPENAI_BASE_URL, "OPENAI_API_KEY"
    return "", OPENAI_BASE_URL, "OPENAI_API_KEY"


def model_is_configured(model_id: str) -> bool:
    """Boolean-only provider readiness check for one configured model route."""

    return bool(model_id and resolve_provider_route(model_id).get("api_key"))


def resolve_provider_route(model_id: str) -> Dict[str, Any]:
    """Resolve which provider serves a given model id.

    Default is OpenRouter — unchanged for every existing model id, including
    OpenRouter's own "openai/..." catalogue. A request is routed to direct
    OpenAI ONLY when the id carries the explicit opt-in OPENAI_PROVIDER_PREFIX.

    The returned dict carries the api_key for the caller to build the request
    locally; the value is never logged or returned in any API response.
    """
    mid = model_id or ""
    if mid.startswith(OPENAI_PROVIDER_PREFIX):
        api_key, base_url, key_env = _direct_openai_compatible_credentials()
        label = "NVIDIA NIM" if key_env == "NVIDIA_API_KEY" else "OpenAI"
        provider = "nvidia" if key_env == "NVIDIA_API_KEY" else "openai"
        return {
            "provider": provider,
            "label": label,
            "base_url": base_url,
            "api_key": api_key,
            "api_model": mid[len(OPENAI_PROVIDER_PREFIX):],
            "key_env": key_env,
            "extra_headers": {},
        }
    return {
        "provider": "openrouter",
        "label": "OpenRouter",
        "base_url": OPENROUTER_BASE_URL,
        "api_key": OPENROUTER_API_KEY,
        "api_model": mid,
        "key_env": "OPENROUTER_API_KEY",
        "extra_headers": {"HTTP-Referer": APP_PUBLIC_URL, "X-Title": APP_TITLE},
    }


# ---------------------------------------------------------------------------
# Error classification (drives the fallback decision)
# ---------------------------------------------------------------------------
KIND_TIMEOUT = "timeout"
KIND_RATE_LIMIT = "rate_limit"
KIND_PROVIDER_UNAVAILABLE = "provider_unavailable"
KIND_INSUFFICIENT_CREDITS = "insufficient_credits"
KIND_MALFORMED = "malformed"
KIND_BAD_REQUEST = "bad_request"
KIND_OTHER = "other"
KIND_OK = "ok"

# Failure kinds that warrant trying the next model in the fallback chain.
FALLBACK_TRIGGERS = frozenset(
    {
        KIND_TIMEOUT,
        KIND_RATE_LIMIT,
        KIND_PROVIDER_UNAVAILABLE,
        KIND_INSUFFICIENT_CREDITS,
        KIND_MALFORMED,
    }
)


def _classify_http(status: int, body: str) -> str:
    blow = body.lower() if body else ""
    if status == 408:
        return KIND_TIMEOUT
    if status == 429:
        return KIND_RATE_LIMIT
    if status == 402 or "insufficient" in blow or "credit" in blow or "balance" in blow:
        return KIND_INSUFFICIENT_CREDITS
    if 500 <= status <= 599:
        return KIND_PROVIDER_UNAVAILABLE
    # 404 (model not found) or 400 referring to invalid model — treat as
    # provider-unavailable so the fallback chain can rescue config errors.
    if status == 404 or (
        status == 400
        and ("not a valid model" in blow or "model" in blow and "not found" in blow)
    ):
        return KIND_PROVIDER_UNAVAILABLE
    if 400 <= status <= 499:
        return KIND_BAD_REQUEST
    return KIND_OTHER


def _classify_exc(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return KIND_TIMEOUT
    if isinstance(exc, httpx.HTTPError):
        return KIND_PROVIDER_UNAVAILABLE
    if isinstance(exc, AIServiceError):
        return getattr(exc, "kind", KIND_OTHER)
    return KIND_OTHER


def merge_leading_system_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Join consecutive leading system messages into one, in order.

    The engine sends its rules and per-turn directives as several system
    messages at the start. Some local chat templates (Qwen family in Ollama)
    accept only one system message and answer HTTP 500 otherwise. Joining them
    with blank lines keeps the same text in the same order. Messages after the
    first non-system message are left untouched.
    """
    leading: List[str] = []
    index = 0
    while index < len(messages) and messages[index].get("role") == "system":
        leading.append(str(messages[index].get("content") or ""))
        index += 1
    if len(leading) <= 1:
        return list(messages)
    merged = {"role": "system", "content": "\n\n".join(part for part in leading if part)}
    return [merged] + list(messages[index:])


# ---------------------------------------------------------------------------
# Core single-model call — returns (content, telemetry)
# ---------------------------------------------------------------------------
async def _call_model_once(
    model_id: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    extra_headers: Optional[Dict[str, str]] = None,
    timeout_seconds: Optional[float] = None,
    assistant_prefill: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """One HTTP call to the resolved provider for a single model. Returns (content, telemetry).

    OpenRouter is the default route for every existing model id (behaviour
    unchanged). Direct OpenAI is used only for explicitly namespaced ids.
    ``timeout_seconds`` lets the caller cap the call at the time left in the
    active generation deadline.
    """
    route = resolve_provider_route(model_id)
    label = route["label"]
    if not route["api_key"]:
        raise AIServiceError(f"{route['key_env']} is not configured", kind=KIND_OTHER)

    if model_id.startswith(OPENAI_PROVIDER_PREFIX):
        # Direct OpenAI-compatible route (real OpenAI, NVIDIA NIM, local
        # Ollama): send one leading system message. OpenRouter is unchanged.
        messages = merge_leading_system_messages(messages)
    prefill = ""
    if (
        assistant_prefill
        and OPENAI_DIRECT_ASSISTANT_PREFILL
        and model_id.startswith(OPENAI_PROVIDER_PREFIX)
    ):
        prefill = assistant_prefill
        messages = list(messages) + [{"role": "assistant", "content": prefill}]
    payload: Dict[str, Any] = {
        "model": route["api_model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if OPENAI_DIRECT_REASONING_EFFORT and model_id.startswith(OPENAI_PROVIDER_PREFIX):
        payload["reasoning_effort"] = OPENAI_DIRECT_REASONING_EFFORT
    if OPENROUTER_REASONING_EFFORT and route["provider"] == "openrouter":
        payload["reasoning"] = {"effort": OPENROUTER_REASONING_EFFORT}
    headers = {
        "Authorization": f"Bearer {route['api_key']}",
        "Content-Type": "application/json",
    }
    headers.update(route["extra_headers"])
    if extra_headers:
        headers.update(extra_headers)

    url = f"{route['base_url']}/chat/completions"
    started = time.monotonic()
    timeout = DEFAULT_TIMEOUT_SECONDS
    if timeout_seconds is not None:
        timeout = max(1.0, min(float(DEFAULT_TIMEOUT_SECONDS), float(timeout_seconds)))

    async with httpx.AsyncClient(timeout=timeout, verify=_TLS_VERIFY) as client:
        try:
            # httpx timeouts bound each wait between bytes, not the whole call:
            # a slow, steady response could outlive the generation deadline and
            # the action lease. wait_for makes the cap a wall-clock limit.
            resp = await asyncio.wait_for(
                client.post(url, json=payload, headers=headers), timeout=timeout
            )
        except asyncio.TimeoutError as exc:
            raise AIServiceError(
                f"{label} call exceeded its {timeout:.0f}s wall-clock limit",
                kind=KIND_TIMEOUT,
            ) from exc
    latency_ms = int((time.monotonic() - started) * 1000)

    if resp.status_code >= 400:
        kind = _classify_http(resp.status_code, resp.text)
        raise AIServiceError(
            f"{label} HTTP {resp.status_code} [{kind}]: {resp.text[:400]}",
            kind=kind,
        )

    try:
        data = resp.json()
    except Exception as je:
        raise AIServiceError(
            f"{label} returned non-JSON body: {je}", kind=KIND_MALFORMED
        ) from je

    choices = data.get("choices") or []
    if not choices:
        raise AIServiceError(
            f"{label} response had no choices: {data.get('error') or data}",
            kind=KIND_MALFORMED,
        )

    content = (choices[0].get("message") or {}).get("content")
    if not content:
        raise AIServiceError(
            f"{label} returned empty content: {data}", kind=KIND_MALFORMED
        )
    # The server returns only the continuation; restore the prefill unless it
    # echoed the whole message.
    if prefill and not content.lstrip().startswith(prefill.strip()):
        content = prefill + content

    usage = data.get("usage") or {}
    telemetry = {
        "model": model_id,
        "latency_ms": latency_ms,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "provider": (data.get("provider") or {}).get("name")
        if isinstance(data.get("provider"), dict)
        else data.get("provider"),
        "provider_route": route["provider"],
        "status": KIND_OK,
        "assistant_prefill": bool(prefill),
    }
    return content, telemetry


# ---------------------------------------------------------------------------
# Public: fallback-aware chat completion with full telemetry
# ---------------------------------------------------------------------------
async def chat_completion_with_meta(
    messages: List[Dict[str, str]],
    primary_model: Optional[str] = None,
    fallback_chain: Optional[List[str]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    max_retries_per_model: Optional[int] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    allow_fallback: bool = True,
    assistant_prefill: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a completion, retrying within a model then falling back to the next.

    Returns a dict::

        {
          "content": str,
          "model_used": str,
          "model_requested": str,
          "telemetry": {model, latency_ms, prompt_tokens, ...},
          "fallback_events": [
              {"from": model, "to": model, "reason": kind, "message": str},
              ...
          ],
          "attempts_per_model": {model: int},
        }

    Raises AIServiceError only if EVERY model in the chain exhausts retries on
    a fallback-trigger error, OR a non-fallback-trigger error (bad_request) is
    raised by the primary call.

    Budget contract (reliability release): an active ``provider_budget`` is
    REQUIRED. Every attempt — per-model retries and fallback models alike —
    reserves one unit of the shared per-request attempt budget, honours the
    request deadline, and is recorded as a usage row. Budget exhaustion raises
    ``ProviderBudgetError`` immediately (no further retries or fallbacks).
    """
    budget = provider_budget.require_active()
    temp = float(temperature) if temperature is not None else DEFAULT_TEMPERATURE
    mt = int(max_tokens) if max_tokens is not None else DEFAULT_MAX_TOKENS
    per_model_retries = (
        int(max_retries_per_model)
        if max_retries_per_model is not None
        else MAX_RETRIES
    )

    requested = normalize_runtime_model(primary_model or DEFAULT_MODEL)
    # Build ordered chain: primary first, then automatic fallbacks (never uncensored).
    if not allow_fallback:
        chain_source = []
    elif fallback_chain:
        chain_source = [
            m for m in fallback_chain
            if m and m != MODEL_QWEN_UNCENSORED and m in AUTOMATIC_FALLBACK_MODELS
        ]
    else:
        chain_source = build_automatic_fallback_chain(requested)
    chain: List[str] = [requested]
    for m in chain_source:
        if m and m not in chain and m != MODEL_QWEN_UNCENSORED:
            chain.append(m)
    if requested == MODEL_QWEN_UNCENSORED:
        chain = [requested]

    fallback_events: List[Dict[str, Any]] = []
    attempts_per_model: Dict[str, int] = {}
    last_error: Optional[AIServiceError] = None

    for idx, model_id in enumerate(chain):
        attempts_per_model[model_id] = 0
        for attempt in range(1, per_model_retries + 1):
            attempts_per_model[model_id] = attempt
            # Budget reservation sits OUTSIDE the retry handler: an exhausted
            # budget must stop the whole chain, never trigger another model.
            attempt_id = await budget.reserve_attempt(model_id)
            try:
                content, telem = await _call_model_once(
                    model_id,
                    messages,
                    temp,
                    mt,
                    extra_headers=extra_headers,
                    timeout_seconds=budget.remaining_seconds(),
                    assistant_prefill=assistant_prefill,
                )
                await budget.record_result(attempt_id, telemetry=telem)
                logger.info(
                    "LLM completion ok · provider=%s · model=%s · attempt=%s · in_msgs=%s · out_chars=%s · latency=%sms · tokens=%s",
                    telem.get("provider_route"),
                    model_id,
                    attempt,
                    len(messages),
                    len(content),
                    telem.get("latency_ms"),
                    telem.get("total_tokens"),
                )
                return {
                    "content": content,
                    "model_used": model_id,
                    "model_requested": requested,
                    "telemetry": telem,
                    "fallback_events": fallback_events,
                    "attempts_per_model": attempts_per_model,
                }
            except Exception as exc:
                kind = _classify_exc(exc)
                last_error = (
                    exc
                    if isinstance(exc, AIServiceError)
                    else AIServiceError(str(exc), kind=kind)
                )
                await budget.record_result(attempt_id, error=last_error)
                logger.warning(
                    "Model %s attempt %s/%s failed [%s]: %s",
                    model_id,
                    attempt,
                    per_model_retries,
                    kind,
                    exc,
                )
                # Non-fallback-trigger errors stop everything (e.g. bad_request,
                # auth, malformed request) — no point trying other models.
                if kind not in FALLBACK_TRIGGERS:
                    raise last_error
                # Retry within the same model with backoff before moving on.
                if attempt < per_model_retries:
                    await asyncio.sleep(min(2 ** (attempt - 1), 4))

        # Exhausted retries on this model. Step to next in chain if available.
        if idx + 1 < len(chain):
            next_model = chain[idx + 1]
            reason = (
                getattr(last_error, "kind", KIND_OTHER) if last_error else KIND_OTHER
            )
            fallback_events.append(
                {
                    "from": model_id,
                    "to": next_model,
                    "reason": reason,
                    "message": str(last_error)[:240] if last_error else "",
                }
            )
            logger.warning(
                "Falling back: %s → %s (reason=%s)", model_id, next_model, reason
            )

    raise AIServiceError(
        f"All models in fallback chain exhausted: {last_error}",
        kind=getattr(last_error, "kind", KIND_OTHER) if last_error else KIND_OTHER,
    )


async def chat_completion_strict_with_meta(
    messages: List[Dict[str, str]],
    model: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    max_retries: int = 1,
) -> Dict[str, Any]:
    """Call exactly one configured model; never step to an automatic fallback."""

    return await chat_completion_with_meta(
        messages=messages,
        primary_model=model,
        fallback_chain=[],
        temperature=temperature,
        max_tokens=max_tokens,
        max_retries_per_model=max_retries,
        allow_fallback=False,
    )


# ---------------------------------------------------------------------------
# Backward-compatible thin wrapper — returns just the content string
# ---------------------------------------------------------------------------
async def chat_completion(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    max_retries: int = 2,
    extra_headers: Optional[Dict[str, str]] = None,
) -> str:
    """Legacy entry point that returns the assistant content as a plain string.

    Internally routes through ``chat_completion_with_meta`` for fallback + telemetry.
    Prefer ``chat_completion_with_meta`` when the caller needs diagnostics.
    """
    result = await chat_completion_with_meta(
        messages=messages,
        primary_model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        max_retries_per_model=max_retries,
        extra_headers=extra_headers,
    )
    return result["content"]
