"""VALIDATION_RETRY_STYLE: how a rejected reply is retried.

Offline evidence (2026-11-21, dice-qwen36): with the rejected reply shown,
2 of 19 retries were usable; with a fresh attempt carrying one short
correction line, 8 of 10.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gateway  # noqa: E402
import server  # noqa: E402
from reliability_support import ACTION_TURN  # noqa: E402

BAD_TURN = (
    "<rolling_state>{}</rolling_state>\n"
    "<narrative>UNIQUE-REJECTED-TEXT the corridor bends left.</narrative>\n"
    "<state>\nHealth: stable\nPressure: steady\nPosition: corridor\n</state>\n"
    "<ledger>\nCarried: torch\n</ledger>\n"
)


def _run_db(coro):
    async def wrapper():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        orig = server.db
        server.db = client[os.environ["DB_NAME"]]
        try:
            return await coro
        finally:
            server.db = orig
            client.close()

    return asyncio.run(wrapper())


def _run_turn(monkeypatch, style):
    calls = []

    async def fake_invoke_llm(**kwargs):
        calls.append([dict(m) for m in kwargs["messages"]])
        return {
            "content": BAD_TURN if len(calls) == 1 else ACTION_TURN,
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    monkeypatch.setattr(gateway, "invoke_llm", fake_invoke_llm)
    monkeypatch.setattr(server, "VALIDATION_RETRY_STYLE", style)
    session = {"id": str(uuid.uuid4()), "turn_count": 12, "mode": "advanced"}
    parsed, _raw, meta = _run_db(
        server._generate_validated_turn(session, "Player action: walk on", player_action="walk on")
    )
    return calls, parsed, meta


@pytest.mark.parametrize("value", [None, "", "  ", "show_rejected", " Show_Rejected "])
def test_default_style_shows_the_rejected_reply(value):
    assert server.resolve_retry_style(value) == "show_rejected"


def test_fresh_style_is_accepted_and_unknown_values_stop_startup():
    assert server.resolve_retry_style(" Fresh ") == "fresh"
    with pytest.raises(ValueError):
        server.resolve_retry_style("retry_harder")


def test_fresh_messages_add_one_line_to_the_last_user_turn_only():
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "earlier action"},
        {"role": "assistant", "content": "earlier turn"},
        {"role": "user", "content": "Player action: walk on"},
    ]
    out = server.fresh_retry_messages(messages, "missing required choice labels: A,B,C,D")
    assert [m["role"] for m in out] == [m["role"] for m in messages]
    assert out[:3] == messages[:3]
    assert out[3]["content"].startswith("Player action: walk on\n\n[Your previous attempt")
    assert "missing required choice labels: A,B,C,D" in out[3]["content"]
    assert messages[3]["content"] == "Player action: walk on"  # input not mutated


def test_fresh_style_retries_without_showing_the_rejected_reply(monkeypatch):
    calls, parsed, meta = _run_turn(monkeypatch, "fresh")
    assert len(calls) == 2
    first, retry = calls
    assert [m["role"] for m in retry] == [m["role"] for m in first]
    assert all("UNIQUE-REJECTED-TEXT" not in str(m.get("content")) for m in retry)
    assert retry[-1]["role"] == "user"
    assert "[Your previous attempt at this turn was rejected: missing required choice labels" in retry[-1]["content"]
    assert meta.get("validation_retried") is True
    assert len(parsed.choices) >= 4


def test_default_style_still_shows_the_rejected_reply(monkeypatch):
    calls, parsed, meta = _run_turn(monkeypatch, "show_rejected")
    assert len(calls) == 2
    retry = calls[1]
    assert retry[-2]["role"] == "assistant" and "UNIQUE-REJECTED-TEXT" in retry[-2]["content"]
    assert retry[-1]["role"] == "user" and retry[-1]["content"].startswith("[VALIDATION_RETRY")
    assert meta.get("validation_retried") is True
    assert len(parsed.choices) >= 4
