"""
Centralized AI service layer.

All AI requests in the application route through this module.
Currently backed by OpenRouter chat completions API. Designed to make
swapping providers or models trivial — just adjust ``chat_completion``.

Features:
    * OpenRouter chat completions over httpx (async)
    * Default model: anthropic/claude-sonnet-4.5  (env-overridable)
    * Safe fallback chain: Sonnet → DeepSeek → Haiku
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

from ai_config import (
    AUTOMATIC_FALLBACK_MODELS,
    DEFAULT_MODEL,
    FALLBACK_MODELS,
    MODEL_QWEN_UNCENSORED,
    MAX_RETRIES,
    PROVIDER_TIMEOUT,
    build_automatic_fallback_chain,
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
# A model is routed to direct OpenAI ONLY when its id carries this explicit,
# opt-in namespace (e.g. "openai-direct/gpt-4o"). Every other id stays on OpenRouter,
# including OpenRouter's own "openai/..." catalogue ids.
OPENAI_PROVIDER_PREFIX = "openai-direct/"

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
        "id": "anthropic/claude-haiku-4.5",
        "label": "Claude Haiku 4.5",
        "context": 200000,
        "note": "Fast lightweight fallback · explicit cheap mode",
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
    """Return the curated four-model catalogue for admin selection."""
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
    return bool(OPENROUTER_API_KEY)


def openai_is_configured() -> bool:
    """Report whether a direct OpenAI key is present (boolean only — never returns
    or logs the value)."""
    return bool(OPENAI_API_KEY)


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
        return {
            "provider": "openai",
            "label": "OpenAI",
            "base_url": OPENAI_BASE_URL,
            "api_key": OPENAI_API_KEY,
            "api_model": mid[len(OPENAI_PROVIDER_PREFIX):],
            "key_env": "OPENAI_API_KEY",
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


# ---------------------------------------------------------------------------
# Core single-model call — returns (content, telemetry)
# ---------------------------------------------------------------------------
async def _call_model_once(
    model_id: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """One HTTP call to the resolved provider for a single model. Returns (content, telemetry).

    OpenRouter is the default route for every existing model id (behaviour
    unchanged). Direct OpenAI is used only for explicitly namespaced ids.
    """
    route = resolve_provider_route(model_id)
    label = route["label"]
    if not route["api_key"]:
        raise AIServiceError(f"{route['key_env']} is not configured", kind=KIND_OTHER)

    payload: Dict[str, Any] = {
        "model": route["api_model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {route['api_key']}",
        "Content-Type": "application/json",
    }
    headers.update(route["extra_headers"])
    if extra_headers:
        headers.update(extra_headers)

    url = f"{route['base_url']}/chat/completions"
    started = time.monotonic()

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, json=payload, headers=headers)
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
    """
    temp = float(temperature) if temperature is not None else DEFAULT_TEMPERATURE
    mt = int(max_tokens) if max_tokens is not None else DEFAULT_MAX_TOKENS
    per_model_retries = (
        int(max_retries_per_model)
        if max_retries_per_model is not None
        else MAX_RETRIES
    )

    requested = primary_model or DEFAULT_MODEL
    # Build ordered chain: primary first, then automatic fallbacks (never uncensored).
    if fallback_chain:
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
            try:
                content, telem = await _call_model_once(
                    model_id, messages, temp, mt, extra_headers=extra_headers
                )
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
