"""
Model catalogue and automatic fallback ordering regression tests.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ai_config  # noqa: E402
import ai_service  # noqa: E402


def test_supported_models_catalogue_is_four_models_only():
    models = ai_service.get_supported_models()
    ids = [m["id"] for m in models]
    assert len(ids) == 4
    assert ids == [
        ai_config.MODEL_SONNET,
        ai_config.MODEL_DEEPSEEK,
        ai_config.MODEL_HAIKU,
        ai_config.MODEL_QWEN_UNCENSORED,
    ]


def test_default_model_is_sonnet():
    assert ai_config.DEFAULT_MODEL == ai_config.MODEL_SONNET


def test_fallback_models_order_sonnet_deepseek_haiku():
    assert ai_config.FALLBACK_MODELS == [
        ai_config.MODEL_SONNET,
        ai_config.MODEL_DEEPSEEK,
        ai_config.MODEL_HAIKU,
    ]


def test_automatic_fallback_chain_from_sonnet():
    chain = ai_config.build_automatic_fallback_chain(ai_config.MODEL_SONNET)
    assert chain == [
        ai_config.MODEL_SONNET,
        ai_config.MODEL_DEEPSEEK,
        ai_config.MODEL_HAIKU,
    ]


def test_automatic_fallback_chain_from_haiku_explicit():
    chain = ai_config.build_automatic_fallback_chain(ai_config.MODEL_HAIKU)
    assert chain == [ai_config.MODEL_HAIKU, ai_config.MODEL_DEEPSEEK]


def test_uncensored_never_in_automatic_chain():
    chain = ai_config.build_automatic_fallback_chain(ai_config.MODEL_QWEN_UNCENSORED)
    assert chain == [ai_config.MODEL_QWEN_UNCENSORED]


def test_chat_completion_deepseek_before_haiku_on_sonnet_failure():
    calls: list[str] = []

    async def fake_once(model_id, messages, temp, mt, extra_headers=None):
        calls.append(model_id)
        if model_id == ai_config.MODEL_SONNET:
            raise ai_service.AIServiceError("credits", kind=ai_service.KIND_INSUFFICIENT_CREDITS)
        return "ok", {
            "model": model_id,
            "latency_ms": 1,
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
            "provider": "test",
            "provider_route": "openrouter",
            "status": ai_service.KIND_OK,
        }

    with patch.object(ai_service, "_call_model_once", new=AsyncMock(side_effect=fake_once)):
        result = asyncio.run(
            ai_service.chat_completion_with_meta(
                messages=[{"role": "user", "content": "hi"}],
                primary_model=ai_config.MODEL_SONNET,
                max_retries_per_model=1,
            )
        )

    assert result["model_used"] == ai_config.MODEL_DEEPSEEK
    assert calls[:2] == [ai_config.MODEL_SONNET, ai_config.MODEL_DEEPSEEK]
    assert ai_config.MODEL_HAIKU not in calls[:2]