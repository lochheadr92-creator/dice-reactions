"""
Paid-provider usage bounds: per-request attempt budget + deadline, global
attempt quota, per-device action quota, global concurrency leases, input
limits, usage records, and fail-closed limiter behaviour.

Real disposable MongoDB; provider HTTP calls are mocked at _call_model_once.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import ai_config  # noqa: E402
import ai_service  # noqa: E402
import gateway  # noqa: E402
import provider_budget  # noqa: E402
import rate_limit  # noqa: E402
import server  # noqa: E402
from security import DEVICE_ID_HEADER  # noqa: E402
from reliability_support import (  # noqa: E402
    ACTION_TURN,
    OPENING_TURN,
    FakeGateway,
    MongoEnv,
    insert_session,
    make_client,
    relax_rate_limits,
    run_db,
)


@pytest.fixture()
def env(monkeypatch):
    mongo = MongoEnv()
    relax_rate_limits(monkeypatch)
    monkeypatch.setattr(provider_budget, "PROVIDER_GLOBAL_ATTEMPT_MAX", 1000)
    monkeypatch.setattr(provider_budget, "PROVIDER_GLOBAL_CONCURRENT", 10)
    yield mongo
    mongo.close()


def _telemetry(model_id, **extra):
    base = {
        "model": model_id,
        "latency_ms": 1,
        "prompt_tokens": 5,
        "completion_tokens": 7,
        "total_tokens": 12,
        "provider": "test",
        "provider_route": "openrouter",
        "status": ai_service.KIND_OK,
    }
    base.update(extra)
    return base


def _run_with(budget, coro):
    async def inner():
        async with provider_budget.active_budget(budget):
            return await coro

    return asyncio.run(inner())


# ---------------------------------------------------------------------------
# Shared per-request attempt budget / deadline (ai_service boundary)
# ---------------------------------------------------------------------------
def test_attempt_budget_is_shared_across_retries_and_fallbacks(monkeypatch):
    calls = []

    async def always_unavailable(model_id, *_a, **_k):
        calls.append(model_id)
        raise ai_service.AIServiceError("down", kind=ai_service.KIND_PROVIDER_UNAVAILABLE)

    monkeypatch.setattr(ai_service, "_call_model_once", always_unavailable)
    budget = provider_budget.offline_budget(max_attempts=3)
    with pytest.raises(provider_budget.ProviderBudgetExhausted) as exc:
        _run_with(
            budget,
            ai_service.chat_completion_with_meta(
                messages=[{"role": "user", "content": "hi"}],
                primary_model=ai_config.MODEL_SONNET,
                max_retries_per_model=2,
            ),
        )
    assert exc.value.reason == "attempts"
    # 2 retries on the primary + 1 on the first fallback = 3 attempts, then stop.
    assert len(calls) == 3
    assert calls[0] == calls[1] == ai_config.MODEL_SONNET
    assert calls[2] != ai_config.MODEL_SONNET
    assert budget.attempts_used == 3
    assert all(r["status"] == "uncertain" for r in budget.usage)


def test_budget_exhaustion_is_not_retried_by_a_second_generation_pass(monkeypatch):
    """A validation retry (second invoke) must share the same exhausted budget."""
    calls = []

    async def ok(model_id, *_a, **_k):
        calls.append(model_id)
        return "ok", _telemetry(model_id)

    monkeypatch.setattr(ai_service, "_call_model_once", ok)
    budget = provider_budget.offline_budget(max_attempts=1)

    async def two_passes():
        async with provider_budget.active_budget(budget):
            await ai_service.chat_completion_with_meta(
                messages=[{"role": "user", "content": "first"}],
                primary_model=ai_config.MODEL_SONNET,
                max_retries_per_model=1,
            )
            with pytest.raises(provider_budget.ProviderBudgetExhausted):
                await ai_service.chat_completion_with_meta(
                    messages=[{"role": "user", "content": "retry"}],
                    primary_model=ai_config.MODEL_SONNET,
                    max_retries_per_model=1,
                )

    asyncio.run(two_passes())
    assert len(calls) == 1


def test_deadline_blocks_before_any_call(monkeypatch):
    calls = []

    async def never(model_id, *_a, **_k):
        calls.append(model_id)
        return "ok", _telemetry(model_id)

    monkeypatch.setattr(ai_service, "_call_model_once", never)
    budget = provider_budget.offline_budget(deadline_seconds=0)
    with pytest.raises(provider_budget.ProviderBudgetExhausted) as exc:
        _run_with(
            budget,
            ai_service.chat_completion_with_meta(
                messages=[{"role": "user", "content": "hi"}],
                primary_model=ai_config.MODEL_SONNET,
            ),
        )
    assert exc.value.reason == "deadline"
    assert calls == []


def test_each_call_timeout_is_capped_by_remaining_deadline(monkeypatch):
    seen = {}

    async def capture(model_id, messages, temp, mt, extra_headers=None, timeout_seconds=None):
        seen["timeout"] = timeout_seconds
        return "ok", _telemetry(model_id)

    monkeypatch.setattr(ai_service, "_call_model_once", capture)
    budget = provider_budget.offline_budget(deadline_seconds=5)
    _run_with(
        budget,
        ai_service.chat_completion_with_meta(
            messages=[{"role": "user", "content": "hi"}], primary_model=ai_config.MODEL_SONNET
        ),
    )
    assert seen["timeout"] is not None and 0 < seen["timeout"] <= 5


def test_provider_boundary_fails_closed_without_budget(monkeypatch):
    calls = []

    async def never(model_id, *_a, **_k):
        calls.append(model_id)
        return "ok", _telemetry(model_id)

    monkeypatch.setattr(ai_service, "_call_model_once", never)
    with pytest.raises(provider_budget.ProviderBudgetMissing):
        asyncio.run(
            ai_service.chat_completion_with_meta(
                messages=[{"role": "user", "content": "hi"}], primary_model=ai_config.MODEL_SONNET
            )
        )
    with pytest.raises(provider_budget.ProviderBudgetMissing):
        asyncio.run(
            ai_service.chat_completion_strict_with_meta(
                messages=[{"role": "user", "content": "hi"}], model=ai_config.MODEL_SONNET
            )
        )
    assert calls == []


def test_missing_token_telemetry_is_recorded_explicitly(monkeypatch):
    async def no_usage(model_id, *_a, **_k):
        return "ok", _telemetry(model_id, prompt_tokens=None, completion_tokens=None, total_tokens=None)

    monkeypatch.setattr(ai_service, "_call_model_once", no_usage)
    budget = provider_budget.offline_budget()
    _run_with(
        budget,
        ai_service.chat_completion_with_meta(
            messages=[{"role": "user", "content": "hi"}], primary_model=ai_config.MODEL_SONNET
        ),
    )
    assert budget.usage[0]["status"] == "ok"
    assert budget.usage[0]["telemetry_missing"] is True
    assert budget.summary()["attempts_without_token_telemetry"] == 1
    assert budget.summary()["tokens_total"] == 0


# ---------------------------------------------------------------------------
# Global attempt quota + usage records (Mongo store)
# ---------------------------------------------------------------------------
def test_global_attempt_quota_blocks_and_usage_records_survive(env, monkeypatch):
    monkeypatch.setattr(provider_budget, "PROVIDER_GLOBAL_ATTEMPT_MAX", 1)
    calls = []

    async def timeout_then_ok(model_id, *_a, **_k):
        calls.append(model_id)
        raise ai_service.AIServiceError("slow", kind=ai_service.KIND_TIMEOUT)

    monkeypatch.setattr(ai_service, "_call_model_once", timeout_then_ok)
    budget = provider_budget.for_request(
        env.async_db, request_key="req-1", kind="action", device_id="d", session_id="s"
    )
    with pytest.raises(provider_budget.ProviderQuotaExceeded):
        _run_with(
            budget,
            ai_service.chat_completion_with_meta(
                messages=[{"role": "user", "content": "hi"}],
                primary_model=ai_config.MODEL_SONNET,
                max_retries_per_model=2,
            ),
        )
    assert len(calls) == 1
    rows = list(env.sync_db.provider_usage.find({"request_key": "req-1"}))
    assert len(rows) == 1
    # Timeout = uncertain usage; the record is kept, never erased.
    assert rows[0]["status"] == "uncertain"
    assert rows[0]["telemetry_missing"] is True


def test_usage_record_exists_before_call_and_is_finalised_after(env, monkeypatch):
    observed = {}

    async def inspect_then_ok(model_id, *_a, **_k):
        observed["during"] = env.sync_db.provider_usage.find_one({"request_key": "req-2"})
        return "ok", _telemetry(model_id)

    monkeypatch.setattr(ai_service, "_call_model_once", inspect_then_ok)
    budget = provider_budget.for_request(env.async_db, request_key="req-2", kind="action")
    _run_with(
        budget,
        ai_service.chat_completion_with_meta(
            messages=[{"role": "user", "content": "hi"}], primary_model=ai_config.MODEL_SONNET
        ),
    )
    assert observed["during"]["status"] == "started"
    final = env.sync_db.provider_usage.find_one({"request_key": "req-2"})
    assert final["status"] == "ok"
    assert final["total_tokens"] == 12


def test_unavailable_usage_storage_fails_closed(env, monkeypatch):
    calls = []

    async def never(model_id, *_a, **_k):
        calls.append(model_id)
        return "ok", _telemetry(model_id)

    monkeypatch.setattr(ai_service, "_call_model_once", never)

    class BrokenStore(provider_budget.MongoBudgetStore):
        async def record_attempt_started(self, doc):
            raise RuntimeError("storage down")

    budget = provider_budget.ProviderBudget(
        BrokenStore(env.async_db), request_key="req-3", kind="action"
    )
    with pytest.raises(provider_budget.ProviderBudgetError):
        _run_with(
            budget,
            ai_service.chat_completion_with_meta(
                messages=[{"role": "user", "content": "hi"}], primary_model=ai_config.MODEL_SONNET
            ),
        )
    assert calls == []


# ---------------------------------------------------------------------------
# Concurrency lease pool
# ---------------------------------------------------------------------------
def test_concurrency_pool_atomic_reservation_under_parallel_acquire(env):
    pool = f"pool-{uuid.uuid4()}"

    async def race():
        results = await asyncio.gather(
            *[
                _try_acquire(env.async_db, pool, limit=3, ttl=60)
                for _ in range(12)
            ]
        )
        return results

    results = run_db(race())
    tokens = [t for t in results if t]
    assert len(tokens) == 3
    assert run_db(rate_limit.count_active_leases(env.async_db, pool)) == 3


async def _try_acquire(db, pool, *, limit, ttl):
    try:
        return await rate_limit.acquire_concurrency_lease(db, pool, limit, ttl)
    except rate_limit.ConcurrencyPoolFull:
        return None


def test_only_owner_can_release_or_renew_and_expiry_frees_capacity(env):
    pool = f"pool-{uuid.uuid4()}"

    async def scenario():
        token = await rate_limit.acquire_concurrency_lease(env.async_db, pool, 1, 60)
        with pytest.raises(rate_limit.ConcurrencyPoolFull):
            await rate_limit.acquire_concurrency_lease(env.async_db, pool, 1, 60)
        assert await rate_limit.release_concurrency_lease(env.async_db, pool, "wrong") is False
        assert await rate_limit.renew_concurrency_lease(env.async_db, pool, "wrong", 60) is False
        assert await rate_limit.count_active_leases(env.async_db, pool) == 1
        assert await rate_limit.renew_concurrency_lease(env.async_db, pool, token, 60) is True
        # Crash simulation: owner never releases; the lease expires.
        env.sync_db.rate_limits.update_one(
            {"_id": pool, "leases.token": token},
            {"$set": {"leases.$.expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
        )
        assert await rate_limit.count_active_leases(env.async_db, pool) == 0
        other = await rate_limit.acquire_concurrency_lease(env.async_db, pool, 1, 60)
        assert other and other != token
        # The crashed worker's late release must not free the new owner's slot.
        assert await rate_limit.release_concurrency_lease(env.async_db, pool, token) is False
        assert await rate_limit.count_active_leases(env.async_db, pool) == 1
        assert await rate_limit.release_concurrency_lease(env.async_db, pool, other) is True
        assert await rate_limit.count_active_leases(env.async_db, pool) == 0

    run_db(scenario())


def test_story_creation_slot_uses_expiring_leases(env, monkeypatch):
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_GLOBAL_CONCURRENT", 1)

    async def scenario():
        token = await rate_limit.acquire_story_creation_slot(env.async_db, owner="a")
        with pytest.raises(HTTPException) as exc:
            await rate_limit.acquire_story_creation_slot(env.async_db, owner="b")
        assert exc.value.status_code == 429
        assert await rate_limit.read_concurrent_slot_count(env.async_db) == 1
        await rate_limit.release_story_creation_slot(env.async_db, token)
        assert await rate_limit.read_concurrent_slot_count(env.async_db) == 0

    run_db(scenario())


# ---------------------------------------------------------------------------
# Route-level enforcement (all before provider invocation)
# ---------------------------------------------------------------------------
def _action(client, sid, device, text="wait"):
    return client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": text, "action_request_id": f"act-{uuid.uuid4()}"},
        headers={DEVICE_ID_HEADER: device},
    )


def test_per_device_action_quota_blocks_before_provider(env, monkeypatch):
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_ACTION_DEVICE_MAX", 1)
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    fake = FakeGateway(ACTION_TURN).install()
    try:
        with make_client() as client:
            assert _action(client, sid, device).status_code == 200
            blocked = _action(client, sid, device)
            assert blocked.status_code == 429
            assert blocked.json()["detail"] == "Too many requests"
            # A different device is unaffected.
            other = f"dev_{uuid.uuid4()}"
            sid2 = insert_session(env.sync_db, other)
            assert _action(client, sid2, other).status_code == 200
    finally:
        fake.restore()
    assert fake.calls == 2
    assert env.sync_db.sessions.find_one({"id": sid})["turn_count"] == 2
    assert env.sync_db.sessions.find_one({"id": sid}).get("action_lock_token") is None


def test_global_provider_concurrency_blocks_before_provider_and_rolls_back_quota(env, monkeypatch):
    monkeypatch.setattr(provider_budget, "PROVIDER_GLOBAL_CONCURRENT", 0)
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    fake = FakeGateway(ACTION_TURN).install()
    try:
        with make_client() as client:
            blocked = _action(client, sid, device)
            assert blocked.status_code == 429
            creation = client.post(
                "/api/story/new",
                json={"device_id": device, "genre": "fantasy", "creation_request_id": "c1"},
            )
            assert creation.status_code == 429
    finally:
        fake.restore()
    assert fake.calls == 0
    active = list(env.sync_db.rate_limits.find({"count": {"$gt": 0}}))
    assert active == []
    assert env.sync_db.sessions.count_documents({"device_id": device, "turn_count": 0}) == 0


def test_global_attempt_quota_blocks_full_route_before_http_call(env, monkeypatch):
    """Real gateway → ai_service path with the HTTP call mocked at _call_model_once."""
    monkeypatch.setattr(provider_budget, "PROVIDER_GLOBAL_ATTEMPT_MAX", 0)
    calls = []

    async def never(model_id, *_a, **_k):
        calls.append(model_id)
        return ACTION_TURN, _telemetry(model_id)

    monkeypatch.setattr(ai_service, "_call_model_once", never)

    async def real_invoke(**kwargs):
        provider_budget.require_active()
        return await ai_service.chat_completion_with_meta(**kwargs)

    monkeypatch.setattr(gateway, "invoke_llm", real_invoke)
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    with make_client() as client:
        blocked = _action(client, sid, device)
        assert blocked.status_code == 429
    assert calls == []
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 0


def test_full_route_records_usage_and_turn_with_real_provider_loop(env, monkeypatch):
    calls = []

    async def ok(model_id, *_a, **_k):
        calls.append(model_id)
        return ACTION_TURN, _telemetry(model_id)

    monkeypatch.setattr(ai_service, "_call_model_once", ok)

    async def real_invoke(**kwargs):
        provider_budget.require_active()
        return await ai_service.chat_completion_with_meta(**kwargs)

    monkeypatch.setattr(gateway, "invoke_llm", real_invoke)
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    rid = f"act-{uuid.uuid4()}"
    with make_client() as client:
        res = client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "wait", "action_request_id": rid},
            headers={DEVICE_ID_HEADER: device},
        )
        assert res.status_code == 200, res.text
        assert "provider_usage" not in res.text
        assert "attempts" not in res.text
    rows = list(env.sync_db.provider_usage.find({"request_key": f"{sid}|{rid}"}))
    assert len(rows) == len(calls) == 1
    assert rows[0]["status"] == "ok" and rows[0]["total_tokens"] == 12


def test_per_action_budget_exhaustion_returns_engine_unavailable_without_commit(env, monkeypatch):
    monkeypatch.setattr(provider_budget, "PROVIDER_ATTEMPTS_PER_ACTION", 1)
    calls = []

    async def unavailable(model_id, *_a, **_k):
        calls.append(model_id)
        raise ai_service.AIServiceError("down", kind=ai_service.KIND_PROVIDER_UNAVAILABLE)

    monkeypatch.setattr(ai_service, "_call_model_once", unavailable)

    async def real_invoke(**kwargs):
        provider_budget.require_active()
        return await ai_service.chat_completion_with_meta(**kwargs)

    monkeypatch.setattr(gateway, "invoke_llm", real_invoke)
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    with make_client() as client:
        res = _action(client, sid, device)
        assert res.status_code == 502
        assert res.json()["detail"] == "Story engine unavailable"
    assert len(calls) == 1  # fallbacks were NOT given extra attempts beyond the budget
    assert env.sync_db.turns.count_documents({"session_id": sid}) == 0
    assert env.sync_db.sessions.find_one({"id": sid})["turn_count"] == 1


def test_limiter_storage_failure_fails_closed_for_actions(env, monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("limiter storage down")

    monkeypatch.setattr(rate_limit, "_consume_bucket", boom)
    device = f"dev_{uuid.uuid4()}"
    sid = insert_session(env.sync_db, device)
    fake = FakeGateway(ACTION_TURN).install()
    try:
        with make_client() as client:
            res = _action(client, sid, device)
            assert res.status_code == 503
            assert res.json()["detail"] == "Service unavailable"
            # Read-only access keeps working.
            read = client.get(f"/api/story/session/{sid}", headers={DEVICE_ID_HEADER: device})
            assert read.status_code == 200
    finally:
        fake.restore()
    assert fake.calls == 0


def test_creation_input_limits_reject_before_paid_work(env, monkeypatch):
    monkeypatch.setattr(server, "CREATION_TEXT_FIELD_MAX_CHARS", 30)
    monkeypatch.setattr(server, "CREATION_SETUP_TOTAL_MAX_CHARS", 50)
    device = f"dev_{uuid.uuid4()}"
    fake = FakeGateway(OPENING_TURN).install()
    try:
        with make_client() as client:
            premise = client.post(
                "/api/story/new",
                json={"device_id": device, "genre": "fantasy", "custom_premise": "p" * 31},
            )
            assert premise.status_code == 422
            assert "custom_premise" in premise.json()["detail"]
            setup_total = client.post(
                "/api/story/new",
                json={
                    "device_id": device,
                    "genre": "fantasy",
                    "custom_world_setup": {"worldConcept": "a" * 30, "danger": "b" * 25},
                },
            )
            assert setup_total.status_code == 422
            assert "custom_world_setup" in setup_total.json()["detail"]
    finally:
        fake.restore()
    assert fake.calls == 0
    assert env.sync_db.sessions.count_documents({"device_id": device}) == 0
    assert list(env.sync_db.rate_limits.find({"count": {"$gt": 0}})) == []


def test_story_creation_budget_failure_cleans_provisional_session(env, monkeypatch):
    monkeypatch.setattr(provider_budget, "PROVIDER_GLOBAL_ATTEMPT_MAX", 0)

    async def never(model_id, *_a, **_k):
        raise AssertionError("must not be called")

    monkeypatch.setattr(ai_service, "_call_model_once", never)

    async def real_invoke(**kwargs):
        provider_budget.require_active()
        return await ai_service.chat_completion_with_meta(**kwargs)

    monkeypatch.setattr(gateway, "invoke_llm", real_invoke)
    device = f"dev_{uuid.uuid4()}"
    with make_client() as client:
        res = client.post("/api/story/new", json={"device_id": device, "genre": "fantasy"})
        assert res.status_code == 429
    assert env.sync_db.sessions.count_documents({"device_id": device}) == 0
    assert run_db(rate_limit.read_concurrent_slot_count(env.async_db)) == 0
