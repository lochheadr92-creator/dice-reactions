"""
Centralized AI service layer.

All AI requests in the application route through this module.
Currently backed by OpenRouter chat completions API. Designed to make
swapping providers or models trivial — just adjust ``chat_completion``.

Features:
    * OpenRouter chat completions over httpx (async)
    * Default model: anthropic/claude-3-5-haiku  (env-overridable)
    * Safe fallback chain: Haiku → Sonnet → Mythomax
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
    DEFAULT_MODEL,
    FALLBACK_MODELS,
    MAX_RETRIES,
    PROVIDER_TIMEOUT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read from environment with sensible defaults)
# ---------------------------------------------------------------------------
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/")

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
        "id": "anthropic/claude-3-5-haiku",
        "label": "Claude 3.5 Haiku",
        "context": 200000,
        "note": "Default · fast · low cost · strong format compliance",
    },
    {
        "id": "anthropic/claude-3-5-sonnet",
        "label": "Claude 3.5 Sonnet",
        "context": 200000,
        "note": "Fallback tier · higher fidelity Anthropic",
    },
    {
        "id": "gryphe/mythomax-l2-13b",
        "label": "Mythomax L2 13B",
        "context": 4096,
        "note": "Final fallback · cheap · loose format compliance",
    },
    {
        "id": "anthropic/claude-sonnet-4.5",
        "label": "Claude Sonnet 4.5",
        "context": 1000000,
        "note": "Top-tier reasoning · 1M context",
    },
    {
        "id": "anthropic/claude-opus-4.5",
        "label": "Claude Opus 4.5",
        "context": 200000,
        "note": "Highest fidelity · slower / pricier",
    },
    {
        "id": "anthropic/claude-haiku-4.5",
        "label": "Claude Haiku 4.5",
        "context": 200000,
        "note": "Fast & affordable Anthropic",
    },
    {
        "id": "openai/gpt-4o",
        "label": "GPT-4o",
        "context": 128000,
        "note": "Balanced quality / cost",
    },
    {
        "id": "openai/gpt-4o-mini",
        "label": "GPT-4o Mini",
        "context": 128000,
        "note": "Fast & cheap",
    },
    {
        "id": "openai/gpt-4.1",
        "label": "GPT-4.1",
        "context": 1047576,
        "note": "OpenAI flagship · 1M context",
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "label": "Llama 3.3 70B",
        "context": 131072,
        "note": "Open-weight workhorse",
    },
    {
        "id": "google/gemini-2.5-pro",
        "label": "Gemini 2.5 Pro",
        "context": 1048576,
        "note": "Massive context · top quality",
    },
    {
        "id": "google/gemini-2.5-flash",
        "label": "Gemini 2.5 Flash",
        "context": 1048576,
        "note": "Fast Gemini · 1M context",
    },
    {
        "id": "mistralai/mistral-large-2407",
        "label": "Mistral Large 2407",
        "context": 128000,
        "note": "Strong reasoning",
    },
    {
        "id": "sao10k/l3.3-euryale-70b",
        "label": "Euryale 70B (L3.3)",
        "context": 131072,
        "note": "Roleplay specialised",
    },
    {
        "id": "sao10k/l3.1-70b-hanami-x1",
        "label": "Hanami X1 70B",
        "context": 16384,
        "note": "Narrative storytelling specialist",
    },
    {
        "id": "thedrummer/cydonia-24b-v4.1",
        "label": "Cydonia 24B v4.1 · UNCENSORED",
        "context": 131072,
        "note": "Paid · uncensored creative · 128k ctx · cheap",
    },
    {
        "id": "anthracite-org/magnum-v4-72b",
        "label": "Magnum v4 72B · UNCENSORED",
        "context": 32768,
        "note": "Paid · top-tier uncensored prose · pricier",
    },
    {
        "id": "thedrummer/rocinante-12b",
        "label": "Rocinante 12B · UNCENSORED",
        "context": 32768,
        "note": "Paid · uncensored · ultra-cheap & fast",
    },
    {
        "id": "openai/gpt-oss-120b:free",
        "label": "GPT-OSS 120B · FREE",
        "context": 131072,
        "note": "OpenAI open-weights · free tier",
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct:free",
        "label": "Llama 3.3 70B · FREE",
        "context": 131072,
        "note": "Free tier · upstream rate-limited",
    },
    {
        "id": "nousresearch/hermes-3-llama-3.1-405b:free",
        "label": "Hermes 3 405B · FREE",
        "context": 131072,
        "note": "Free · creative writing strong",
    },
    {
        "id": "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        "label": "Dolphin Mistral 24B · FREE",
        "context": 32768,
        "note": "Free · uncensored creative",
    },
]


class AIServiceError(Exception):
    """Raised when the underlying AI provider call fails permanently."""

    def __init__(self, message: str, kind: str = "other"):
        super().__init__(message)
        self.kind = kind


def get_supported_models() -> List[Dict[str, Any]]:
    """Return the curated list of model options for the admin UI."""
    return SUPPORTED_MODELS


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
    """One HTTP call to OpenRouter for a single model. Returns (content, telemetry)."""
    if not OPENROUTER_API_KEY:
        raise AIServiceError("OPENROUTER_API_KEY is not configured", kind=KIND_OTHER)

    payload: Dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": APP_PUBLIC_URL,
        "X-Title": APP_TITLE,
    }
    if extra_headers:
        headers.update(extra_headers)

    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    started = time.monotonic()

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, json=payload, headers=headers)
    latency_ms = int((time.monotonic() - started) * 1000)

    if resp.status_code >= 400:
        kind = _classify_http(resp.status_code, resp.text)
        raise AIServiceError(
            f"OpenRouter HTTP {resp.status_code} [{kind}]: {resp.text[:400]}",
            kind=kind,
        )

    try:
        data = resp.json()
    except Exception as je:
        raise AIServiceError(
            f"OpenRouter returned non-JSON body: {je}", kind=KIND_MALFORMED
        ) from je

    choices = data.get("choices") or []
    if not choices:
        raise AIServiceError(
            f"OpenRouter response had no choices: {data.get('error') or data}",
            kind=KIND_MALFORMED,
        )

    content = (choices[0].get("message") or {}).get("content")
    if not content:
        raise AIServiceError(
            f"OpenRouter returned empty content: {data}", kind=KIND_MALFORMED
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
    # Build the ordered chain: requested first, then any fallback models not equal to it.
    chain_source = list(fallback_chain) if fallback_chain else list(FALLBACK_MODELS)
    chain: List[str] = [requested]
    for m in chain_source:
        if m and m not in chain:
            chain.append(m)

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
                    "OpenRouter completion ok · model=%s · attempt=%s · in_msgs=%s · out_chars=%s · latency=%sms · tokens=%s",
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
