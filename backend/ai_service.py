"""
Centralized AI service layer.

All AI requests in the application route through this module.
Currently backed by OpenRouter chat completions API. Designed to make
swapping providers or models trivial — just adjust ``chat_completion``.

Features:
    * OpenRouter chat completions over httpx (async)
    * Default model: gryphe/mythomax-l2-13b
    * Adjustable model / temperature / max_tokens per call
    * Retry with exponential backoff on transient failures (5xx, 408, 429)
    * Curated list of supported models exposed to the admin UI
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read from environment with sensible defaults)
# ---------------------------------------------------------------------------
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/")

DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "gryphe/mythomax-l2-13b")
DEFAULT_TEMPERATURE = float(os.environ.get("DEFAULT_TEMPERATURE", "0.85"))
DEFAULT_MAX_TOKENS = int(os.environ.get("DEFAULT_MAX_TOKENS", "2048"))
DEFAULT_HISTORY_WINDOW = int(os.environ.get("DEFAULT_HISTORY_WINDOW", "40"))
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("DEFAULT_TIMEOUT_SECONDS", "180"))

APP_PUBLIC_URL = os.environ.get(
    "APP_PUBLIC_URL", "https://dice-reaction-story-engine.example"
)
APP_TITLE = os.environ.get("APP_TITLE", "Dice Reaction Story Engine")

# ---------------------------------------------------------------------------
# Supported model catalogue — surfaced to admin UI for switching
# ---------------------------------------------------------------------------
SUPPORTED_MODELS: List[Dict[str, Any]] = [
    {
        "id": "gryphe/mythomax-l2-13b",
        "label": "Mythomax L2 13B",
        "context": 4096,
        "note": "Default · strong creative writing · paid (cheap)",
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


def get_supported_models() -> List[Dict[str, Any]]:
    """Return the curated list of model options for the admin UI."""
    return SUPPORTED_MODELS


def get_default_settings() -> Dict[str, Any]:
    return {
        "model": DEFAULT_MODEL,
        "temperature": DEFAULT_TEMPERATURE,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "history_window": DEFAULT_HISTORY_WINDOW,
    }


def is_configured() -> bool:
    return bool(OPENROUTER_API_KEY)


# ---------------------------------------------------------------------------
# Core entry point
# ---------------------------------------------------------------------------
async def chat_completion(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    max_retries: int = 3,
    extra_headers: Optional[Dict[str, str]] = None,
) -> str:
    """Run a chat completion through OpenRouter and return the assistant text.

    Args:
        messages: OpenAI-style message list ``[{role, content}, ...]``.
        model: Optional model override (e.g. ``"openai/gpt-4o"``).
        temperature: Optional sampling temperature override.
        max_tokens: Optional output cap override.
        max_retries: Total attempts on transient failures.
        extra_headers: Optional headers to merge.

    Returns:
        Plain string content of the first choice.

    Raises:
        AIServiceError on permanent failure.
    """
    if not OPENROUTER_API_KEY:
        raise AIServiceError("OPENROUTER_API_KEY is not configured")

    model_id = model or DEFAULT_MODEL
    temp = float(temperature) if temperature is not None else DEFAULT_TEMPERATURE
    mt = int(max_tokens) if max_tokens is not None else DEFAULT_MAX_TOKENS

    payload: Dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "temperature": temp,
        "max_tokens": mt,
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

    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, json=payload, headers=headers)

            # 5xx, 408, 429 — retryable
            if resp.status_code >= 500 or resp.status_code in (408, 429):
                raise AIServiceError(
                    f"OpenRouter HTTP {resp.status_code}: {resp.text[:300]}"
                )

            # other 4xx — not retryable
            if resp.status_code >= 400:
                logger.error(
                    "OpenRouter returned non-retryable HTTP %s: %s",
                    resp.status_code,
                    resp.text[:500],
                )
                raise AIServiceError(
                    f"OpenRouter HTTP {resp.status_code}: {resp.text[:500]}"
                ) from None

            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                err = data.get("error") or data
                raise AIServiceError(f"OpenRouter response had no choices: {err}")

            content = (choices[0].get("message") or {}).get("content")
            if not content:
                raise AIServiceError(f"OpenRouter returned empty content: {data}")

            logger.info(
                "OpenRouter completion ok · model=%s · attempt=%s · in_msgs=%s · out_chars=%s",
                model_id,
                attempt,
                len(messages),
                len(content),
            )
            return content

        except httpx.HTTPError as e:
            last_exc = e
            logger.warning(
                "OpenRouter transport error (attempt %s/%s): %s",
                attempt,
                max_retries,
                e,
            )
        except AIServiceError as e:
            last_exc = e
            # Only retry for transient-looking AIServiceErrors
            msg = str(e)
            transient = (
                "HTTP 5" in msg
                or "HTTP 408" in msg
                or "HTTP 429" in msg
                or "no choices" in msg
                or "empty content" in msg
            )
            if not transient:
                raise
            logger.warning(
                "OpenRouter transient error (attempt %s/%s): %s",
                attempt,
                max_retries,
                e,
            )

        if attempt < max_retries:
            backoff = min(2 ** (attempt - 1), 8)
            await asyncio.sleep(backoff)

    raise AIServiceError(
        f"OpenRouter request failed after {max_retries} attempts: {last_exc}"
    )
