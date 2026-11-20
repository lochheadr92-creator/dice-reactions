"""Shared helpers for the reliability-release test files (not collected by pytest)."""

from __future__ import annotations

import asyncio
import copy
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from starlette.testclient import TestClient

import gateway
import rate_limit
import server

FIXED_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)

OPENING_TURN = (
    "<rolling_state>{}</rolling_state>\n"
    "<narrative>The gate creaks.</narrative>\n"
    "<choices>\nA. Enter\nB. Listen\nC. Retreat\nD. Call out\n</choices>\n"
    "<state>\nHealth: stable\nStress: clear\nFatigue: rested\nPosition: at the gate\n"
    "Inventory Summary: torch\nPressure: wind rising\n</state>\n"
    "<ledger>\nCarried: torch\nLoad: light\n</ledger>\n"
)

ACTION_TURN = (
    "<rolling_state>{}</rolling_state>\n"
    "<narrative>You step forward.</narrative>\n"
    "<choices>\nA. Continue\nB. Look around\nC. Listen carefully\nD. Hold position\n</choices>\n"
    "<state>\nHealth: stable\nPressure: steady\nPosition: forward\n</state>\n"
    "<ledger>\nCarried: torch\n</ledger>\n"
)


def fake_llm_result(content: str) -> Dict[str, Any]:
    return {
        "content": content,
        "model_used": "test",
        "model_requested": "test",
        "telemetry": {"provider": "test", "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        "fallback_events": [],
        "attempts_per_model": {"test": 1},
    }


class _LazyDb:
    """Forwards to ``server.db`` at call time so coroutines built before an
    event loop exists still use the client bound to the running loop."""

    def __getattr__(self, name):
        return getattr(server.db, name)

    def __getitem__(self, name):
        return server.db[name]


LAZY_DB = _LazyDb()


class MongoEnv:
    """Fresh database handles + cleared gameplay/limiter collections."""

    def __init__(self):
        self.motor_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        self.sync_client = MongoClient(os.environ["MONGO_URL"])
        self.db_name = os.environ["DB_NAME"]
        self.original_db = server.db
        server.db = self.motor_client[self.db_name]
        self.async_db = LAZY_DB
        self.sync_db = self.sync_client[self.db_name]
        for name in ("sessions", "turns", "rate_limits", "action_requests", "provider_usage"):
            self.sync_db[name].delete_many({})

    def close(self):
        server.db = self.original_db
        self.motor_client.close()
        self.sync_client.close()


def relax_rate_limits(monkeypatch) -> None:
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_IP_MAX", 200)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_DEVICE_MAX", 200)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_MAX", 2000)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_CONCURRENT", 10)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_ACTION_DEVICE_MAX", 500)
    monkeypatch.setattr(rate_limit, "TRUSTED_PROXY_COUNT", 0)


def run_db(coro):
    """Run a coroutine on a fresh loop with a loop-bound Motor client as server.db.

    Pass coroutines that resolve the database lazily (``LAZY_DB`` /
    ``env.async_db`` / ``server.db`` read inside the coroutine body).
    """

    async def wrapper():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        original = server.db
        server.db = client[os.environ["DB_NAME"]]
        try:
            return await coro
        finally:
            server.db = original
            client.close()

    return asyncio.run(wrapper())


def insert_session(
    sync_db,
    device_id: str,
    *,
    turn_count: int = 1,
    rolling: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    sid = str(uuid.uuid4())
    doc = {
        "id": sid,
        "device_id": device_id,
        "genre": "horror",
        "role": "scout",
        "tone": "grim",
        "difficulty": "standard",
        "mode": "advanced",
        "turn_count": turn_count,
        "rolling_state": copy.deepcopy(rolling or {}),
        "last_state": {"Health": "stable"},
        "created_at": FIXED_NOW.isoformat(),
        "updated_at": FIXED_NOW.isoformat(),
    }
    if extra:
        doc.update(extra)
    sync_db.sessions.insert_one(doc)
    return sid


class FakeGateway:
    """Replace gateway.invoke_llm with a scripted, countable fake."""

    def __init__(
        self,
        content: str = ACTION_TURN,
        on_call: Optional[Callable[[int], Any]] = None,
        on_request: Optional[Callable[[int, Dict[str, Any]], Any]] = None,
    ):
        self.calls = 0
        self.content = content
        self.on_call = on_call
        self.on_request = on_request
        self._original = None

    async def __call__(self, **kwargs):
        self.calls += 1
        if self.on_request is not None:
            result = self.on_request(self.calls, kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            if isinstance(result, dict):
                return result
            if isinstance(result, str):
                return fake_llm_result(result)
        if self.on_call is not None:
            result = self.on_call(self.calls)
            if asyncio.iscoroutine(result):
                result = await result
            if isinstance(result, dict):
                return result
            if isinstance(result, str):
                return fake_llm_result(result)
        return fake_llm_result(self.content)

    def install(self):
        self._original = gateway.invoke_llm
        gateway.invoke_llm = self
        return self

    def restore(self):
        if self._original is not None:
            gateway.invoke_llm = self._original


def make_client() -> TestClient:
    return TestClient(server.app)
