"""
Rate-limit tests for POST /story/new — must block before LLM and session insert.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from starlette.requests import Request
from starlette.testclient import TestClient

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import gateway  # noqa: E402
import rate_limit  # noqa: E402
import server  # noqa: E402
from ai_service import AIServiceError  # noqa: E402

FAKE_TURN = (
    "<narrative>The gate creaks.</narrative>"
    "<paragraphs><p>The gate creaks.</p><p>Dust hangs in the air.</p></paragraphs>"
    "<choices>"
    "<choice label=\"A\">Enter</choice>"
    "<choice label=\"B\">Listen</choice>"
    "<choice label=\"C\">Retreat</choice>"
    "<choice label=\"D\">Call out</choice>"
    "</choices>"
    "<state><Health>stable</Health><Stress>clear</Stress><Fatigue>rested</Fatigue>"
    "<Position>at the gate</Position><Inventory Summary>torch</Inventory Summary></state>"
    "<ledger><Carried>torch</Carried><Load>light</Load></ledger>"
    "<rolling_state>{}</rolling_state>"
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def mongo_env(monkeypatch):
    motor_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    sync_client = MongoClient(os.environ["MONGO_URL"])
    db_name = os.environ["DB_NAME"]
    original_db = server.db
    server.db = motor_client[db_name]
    sync_db = sync_client[db_name]
    sync_db.rate_limits.delete_many({})
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_IP_MAX", 3)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_DEVICE_MAX", 2)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_IP_WINDOW_SEC", 60)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_DEVICE_WINDOW_SEC", 60)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_MAX", 100)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_WINDOW_SEC", 60)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_CONCURRENT", 10)
    monkeypatch.setattr(rate_limit, "TRUSTED_PROXY_COUNT", 0)
    yield sync_db
    server.db = original_db
    motor_client.close()
    sync_client.close()


@pytest.fixture()
def client(mongo_env):
    llm_calls = {"n": 0}

    async def fake_chat(**kwargs):
        llm_calls["n"] += 1
        return {
            "content": FAKE_TURN,
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {"provider": "test"},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat
    with TestClient(server.app) as c:
        c.llm_calls = llm_calls  # type: ignore[attr-defined]
        yield c
    gateway.invoke_llm = original


def _new_payload(device_id: str | None = None) -> dict:
    return {
        "device_id": device_id or f"rate-{uuid.uuid4()}",
        "genre": "fantasy",
        "difficulty": "standard",
        "debug_mode": False,
    }


class TestStoryCreationRateLimit:
    def test_normal_creation_succeeds(self, client, mongo_env):
        device = f"ok-{uuid.uuid4()}"
        r = client.post("/api/story/new", json=_new_payload(device))
        assert r.status_code == 200, r.text
        assert r.json()["session_id"]
        assert client.llm_calls["n"] >= 1  # type: ignore[attr-defined]
        assert mongo_env.sessions.count_documents({"device_id": device}) == 1

    def test_device_limit_throttles_before_llm(self, client, mongo_env):
        device = f"dev-limit-{uuid.uuid4()}"
        for _ in range(2):
            assert client.post("/api/story/new", json=_new_payload(device)).status_code == 200
        calls_before = client.llm_calls["n"]  # type: ignore[attr-defined]
        blocked = client.post("/api/story/new", json=_new_payload(device))
        assert blocked.status_code == 429
        assert blocked.json()["detail"] == "Too many requests"
        assert client.llm_calls["n"] == calls_before  # type: ignore[attr-defined]
        assert mongo_env.sessions.count_documents({"device_id": device}) == 2

    def test_ip_limit_throttles_rotating_devices(self, client, mongo_env):
        before_count = mongo_env.sessions.count_documents({})
        for _ in range(3):
            assert client.post("/api/story/new", json=_new_payload()).status_code == 200
        calls_before = client.llm_calls["n"]  # type: ignore[attr-defined]
        blocked = client.post("/api/story/new", json=_new_payload())
        assert blocked.status_code == 429
        assert client.llm_calls["n"] == calls_before  # type: ignore[attr-defined]
        assert mongo_env.sessions.count_documents({}) == before_count + 3

    def test_global_fixed_limit_blocks_rotating_devices(self, client, mongo_env, monkeypatch):
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_MAX", 3)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_IP_MAX", 100)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_DEVICE_MAX", 100)
        for _ in range(3):
            assert client.post("/api/story/new", json=_new_payload()).status_code == 200
        calls_before = client.llm_calls["n"]  # type: ignore[attr-defined]
        blocked = client.post("/api/story/new", json=_new_payload())
        assert blocked.status_code == 429
        assert client.llm_calls["n"] == calls_before  # type: ignore[attr-defined]

    def test_global_fixed_limit_blocks_rotating_ips(self, client, mongo_env, monkeypatch):
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_MAX", 3)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_IP_MAX", 100)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_DEVICE_MAX", 100)
        monkeypatch.setattr(rate_limit, "TRUSTED_PROXY_COUNT", 1)
        for i in range(3):
            headers = {"X-Forwarded-For": f"spoof-{i}, client-{i}"}
            assert (
                client.post("/api/story/new", json=_new_payload(), headers=headers).status_code
                == 200
            )
        calls_before = client.llm_calls["n"]  # type: ignore[attr-defined]
        blocked = client.post(
            "/api/story/new",
            json=_new_payload(),
            headers={"X-Forwarded-For": "spoof-9, client-9"},
        )
        assert blocked.status_code == 429
        assert client.llm_calls["n"] == calls_before  # type: ignore[attr-defined]

    def test_throttled_request_does_not_insert_session(self, client, mongo_env):
        device = f"no-insert-{uuid.uuid4()}"
        for _ in range(2):
            client.post("/api/story/new", json=_new_payload(device))
        before = mongo_env.sessions.count_documents({})
        client.post("/api/story/new", json=_new_payload(device))
        assert mongo_env.sessions.count_documents({}) == before

    def test_window_reset_allows_creation(self, client, mongo_env, monkeypatch):
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_DEVICE_WINDOW_SEC", 1)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_IP_WINDOW_SEC", 1)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_WINDOW_SEC", 1)
        device = f"reset-{uuid.uuid4()}"
        for _ in range(2):
            assert client.post("/api/story/new", json=_new_payload(device)).status_code == 200
        assert client.post("/api/story/new", json=_new_payload(device)).status_code == 429
        time.sleep(1.1)
        assert client.post("/api/story/new", json=_new_payload(device)).status_code == 200

    def test_limiter_backend_failure_fails_closed(self, client, monkeypatch):
        async def boom(*_a, **_k):
            raise RuntimeError("mongo down")

        monkeypatch.setattr(rate_limit, "_consume_bucket", boom)
        r = client.post("/api/story/new", json=_new_payload())
        assert r.status_code == 503
        assert r.json()["detail"] == "Service unavailable"
        assert client.llm_calls["n"] == 0  # type: ignore[attr-defined]


class TestTrustedProxyExtraction:
    def _request(self, xff: str | None = None, host: str = "10.0.0.5") -> Request:
        headers = []
        if xff is not None:
            headers.append((b"x-forwarded-for", xff.encode()))
        scope = {
            "type": "http",
            "headers": headers,
            "client": (host, 12345),
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "server": ("test", 80),
            "scheme": "http",
            "root_path": "",
        }
        return Request(scope)

    def test_zero_trusted_proxies_ignores_xff(self, monkeypatch):
        monkeypatch.setattr(rate_limit, "TRUSTED_PROXY_COUNT", 0)
        req = self._request("evil, 1.2.3.4", host="10.0.0.5")
        assert rate_limit.resolve_client_ip(req) == "10.0.0.5"

    def test_single_proxy_uses_rightmost_hop(self, monkeypatch):
        monkeypatch.setattr(rate_limit, "TRUSTED_PROXY_COUNT", 1)
        req = self._request("spoofed, 203.0.113.9", host="10.0.0.5")
        assert rate_limit.resolve_client_ip(req) == "203.0.113.9"

    def test_spoofed_only_chain_falls_back_to_peer(self, monkeypatch):
        monkeypatch.setattr(rate_limit, "TRUSTED_PROXY_COUNT", 1)
        req = self._request("spoofed-only", host="10.0.0.5")
        assert rate_limit.resolve_client_ip(req) == "10.0.0.5"

    def test_two_proxies_use_rightmost_second_hop(self, monkeypatch):
        monkeypatch.setattr(rate_limit, "TRUSTED_PROXY_COUNT", 2)
        req = self._request("client, proxy1, proxy2", host="10.0.0.5")
        assert rate_limit.resolve_client_ip(req) == "proxy1"

    def test_three_proxies_use_rightmost_third_hop(self, monkeypatch):
        monkeypatch.setattr(rate_limit, "TRUSTED_PROXY_COUNT", 3)
        req = self._request("client, hop1, hop2, hop3", host="10.0.0.5")
        assert rate_limit.resolve_client_ip(req) == "hop1"

    def test_two_proxies_rejects_spoofed_prefix(self, monkeypatch):
        monkeypatch.setattr(rate_limit, "TRUSTED_PROXY_COUNT", 2)
        req = self._request("evil, only-proxy", host="10.0.0.5")
        assert rate_limit.resolve_client_ip(req) == "10.0.0.5"

    def test_two_proxies_lb_appended_chain(self, monkeypatch):
        monkeypatch.setattr(rate_limit, "TRUSTED_PROXY_COUNT", 2)
        req = self._request("spoofed, 198.51.100.7, 203.0.113.44", host="10.0.0.5")
        assert rate_limit.resolve_client_ip(req) == "198.51.100.7"

    def test_short_chain_falls_back(self, monkeypatch):
        monkeypatch.setattr(rate_limit, "TRUSTED_PROXY_COUNT", 2)
        req = self._request("only-one", host="10.0.0.5")
        assert rate_limit.resolve_client_ip(req) == "10.0.0.5"

    def test_malformed_xff_tokens_fall_back(self, monkeypatch):
        monkeypatch.setattr(rate_limit, "TRUSTED_PROXY_COUNT", 1)
        req = self._request("bad token!, 1.2.3.4", host="10.0.0.5")
        assert rate_limit.resolve_client_ip(req) == "1.2.3.4"
        req2 = self._request("bad token!", host="10.0.0.5")
        assert rate_limit.resolve_client_ip(req2) == "10.0.0.5"

    def test_empty_and_whitespace_segments_ignored(self, monkeypatch):
        monkeypatch.setattr(rate_limit, "TRUSTED_PROXY_COUNT", 1)
        req = self._request(" , , 198.51.100.2 , ", host="10.0.0.5")
        assert rate_limit.resolve_client_ip(req) == "10.0.0.5"


@pytest.fixture()
def async_db(mongo_env):
    """Fresh Motor client per test — avoids TestClient closing the shared event loop."""
    motor_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = motor_client[os.environ["DB_NAME"]]
    yield db
    motor_client.close()


class TestMongoLimiterMechanics:
    def test_atomic_consume_increments_single_bucket(self, mongo_env, async_db):
        bucket = f"test:{uuid.uuid4()}"
        _run(rate_limit._consume_bucket(async_db, bucket, 5, 60))
        doc = mongo_env.rate_limits.find_one({"_id": bucket})
        assert doc["count"] == 1
        assert isinstance(doc["expires_at"], datetime)

    def test_duplicate_bucket_upsert_prevents_second_document(self, mongo_env, async_db):
        bucket = f"dup:{uuid.uuid4()}"

        async def consume_twice():
            await rate_limit._consume_bucket(async_db, bucket, 5, 60)
            await rate_limit._consume_bucket(async_db, bucket, 5, 60)

        _run(consume_twice())
        assert mongo_env.rate_limits.count_documents({"_id": bucket}) == 1
        assert mongo_env.rate_limits.find_one({"_id": bucket})["count"] == 2

    def test_exceed_rolls_back_count(self, mongo_env, async_db):
        bucket = f"rollback:{uuid.uuid4()}"

        async def exceed_once():
            await rate_limit._consume_bucket(async_db, bucket, 1, 60)
            with pytest.raises(HTTPException) as exc:
                await rate_limit._consume_bucket(async_db, bucket, 1, 60)
            assert exc.value.status_code == 429

        _run(exceed_once())
        assert mongo_env.rate_limits.find_one({"_id": bucket})["count"] == 1

    def test_concurrent_slot_released_in_finally(self, client, mongo_env):
        secret = "OpenRouter secret failure XYZ-999"

        async def boom(**_kwargs):
            raise AIServiceError(secret)

        original = gateway.invoke_llm
        gateway.invoke_llm = boom
        try:
            r = client.post("/api/story/new", json=_new_payload())
            assert r.status_code == 502
            doc = mongo_env.rate_limits.find_one({"_id": "story_new_concurrent"})
            assert (doc or {}).get("count", 0) == 0
        finally:
            gateway.invoke_llm = original

    def test_provider_failure_leaves_no_session_or_turn(self, client, mongo_env):
        secret = "OpenRouter secret failure XYZ-999"

        async def boom(**_kwargs):
            raise AIServiceError(secret)

        original = gateway.invoke_llm
        gateway.invoke_llm = boom
        try:
            before_sessions = mongo_env.sessions.count_documents({})
            before_turns = mongo_env.turns.count_documents({})
            r = client.post("/api/story/new", json=_new_payload())
            assert r.status_code == 502
            assert r.json()["detail"] == "Story engine unavailable"
            assert secret not in r.text
            assert mongo_env.sessions.count_documents({}) == before_sessions
            assert mongo_env.turns.count_documents({}) == before_turns
        finally:
            gateway.invoke_llm = original

    def test_ensure_ttl_index_created(self, mongo_env, async_db):
        _run(rate_limit.ensure_rate_limit_indexes(async_db))
        indexes = {idx["name"] for idx in mongo_env.rate_limits.list_indexes()}
        assert "rate_limits_expires_ttl" in indexes

    def test_prune_drops_expired_buckets(self, mongo_env, async_db):
        bucket = f"expired:{uuid.uuid4()}"
        mongo_env.rate_limits.insert_one(
            {
                "_id": bucket,
                "count": 1,
                "expires_at": datetime(2000, 1, 1, tzinfo=timezone.utc),
            }
        )
        _run(rate_limit._prune_expired_buckets(async_db))
        assert mongo_env.rate_limits.find_one({"_id": bucket}) is None

    def test_quota_rollback_when_device_bucket_exceeds(self, mongo_env, async_db, monkeypatch):
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_MAX", 100)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_IP_MAX", 100)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_DEVICE_MAX", 0)
        device = f"rollback-dev-{uuid.uuid4()}"
        ip = "203.0.113.55"

        async def attempt():
            with pytest.raises(HTTPException) as exc:
                await rate_limit.check_story_creation_limits(async_db, ip, device)
            assert exc.value.status_code == 429

        _run(attempt())
        active = list(mongo_env.rate_limits.find({"count": {"$gt": 0}}))
        assert active == []

    def test_concurrent_acquire_failure_rolls_back_quota_buckets(
        self, client, mongo_env, monkeypatch
    ):
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_CONCURRENT", 0)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_MAX", 100)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_IP_MAX", 100)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_DEVICE_MAX", 100)
        r = client.post("/api/story/new", json=_new_payload())
        assert r.status_code == 429
        active = list(mongo_env.rate_limits.find({"count": {"$gt": 0}}))
        assert active == []
        assert client.llm_calls["n"] == 0  # type: ignore[attr-defined]