from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ai_config  # noqa: E402
import server  # noqa: E402


class _FakeAdminSettings:
    def __init__(self, settings):
        self._settings = settings

    async def find_one(self, *_args, **_kwargs):
        return {"settings": dict(self._settings)}


def test_stale_haiku_admin_settings_normalize_to_sonnet(monkeypatch):
    fake_db = SimpleNamespace(
        admin_settings=_FakeAdminSettings(
            {
                "model": ai_config.MODEL_HAIKU,
                "fallback_models": [
                    ai_config.MODEL_SONNET,
                    ai_config.MODEL_HAIKU,
                    ai_config.MODEL_DEEPSEEK,
                ],
            }
        )
    )
    monkeypatch.setattr(server, "db", fake_db)

    settings = asyncio.run(server.get_ai_settings())

    assert settings["model"] == ai_config.MODEL_SONNET
    assert settings["fallback_models"] == [
        ai_config.MODEL_SONNET,
        ai_config.MODEL_DEEPSEEK,
    ]


def test_stale_haiku_session_lock_uses_current_settings_model():
    settings = {"model": ai_config.MODEL_SONNET}
    for haiku_id in (ai_config.MODEL_HAIKU, "anthropic/claude-3-5-haiku"):
        session = {
            "active_model": haiku_id,
            "fallback_chain": [
                ai_config.MODEL_SONNET,
                ai_config.MODEL_DEEPSEEK,
                haiku_id,
            ],
            "model_switches": [{"from_model": ai_config.MODEL_SONNET, "to_model": haiku_id}],
        }

        assert server._resolve_requested_model(session, settings) == ai_config.MODEL_SONNET


def test_admin_model_change_overrides_existing_session_lock():
    session = {
        "active_model": ai_config.MODEL_DEEPSEEK,
        "fallback_chain": [
            ai_config.MODEL_SONNET,
            ai_config.MODEL_DEEPSEEK,
        ],
        "model_switches": [{"from_model": ai_config.MODEL_SONNET, "to_model": ai_config.MODEL_DEEPSEEK}],
    }

    assert (
        server._resolve_requested_model(session, {"model": ai_config.MODEL_QWEN_UNCENSORED})
        == ai_config.MODEL_QWEN_UNCENSORED
    )


def test_valid_fallback_lock_survives_when_primary_unchanged():
    session = {
        "active_model": ai_config.MODEL_DEEPSEEK,
        "fallback_chain": [
            ai_config.MODEL_SONNET,
            ai_config.MODEL_DEEPSEEK,
        ],
        "model_switches": [{"from_model": ai_config.MODEL_SONNET, "to_model": ai_config.MODEL_DEEPSEEK}],
    }

    assert server._resolve_requested_model(session, {"model": ai_config.MODEL_SONNET}) == ai_config.MODEL_DEEPSEEK
