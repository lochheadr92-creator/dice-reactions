"""
Provider usage budget — bounds every paid model call.

Every logical paid request (story creation, player action) runs under exactly
one ``ProviderBudget``. The budget is installed in a context variable and the
shared provider boundary (``ai_service.chat_completion_with_meta``) refuses to
make a call without one, so alternate routes and future callers cannot bypass
it. The budget enforces, per logical request:

  * a provider-attempt budget shared across validation retries AND model
    fallbacks (``PROVIDER_ATTEMPTS_PER_ACTION``);
  * one total generation deadline (``ACTION_GENERATION_DEADLINE_SEC``), which
    also caps each HTTP call's timeout to the time remaining;
  * the global provider-attempt quota (``PROVIDER_GLOBAL_ATTEMPT_MAX`` per
    ``PROVIDER_GLOBAL_ATTEMPT_WINDOW_SEC``), reserved atomically before each
    attempt and failing closed when limiter storage is unavailable;
  * a usage record per attempt (model, status, token counts when reported,
    ``telemetry_missing`` when the provider reports none). Records are never
    deleted on uncertain outcomes.

Concurrency (``PROVIDER_GLOBAL_CONCURRENT``) is reserved at the route level
through an expiring lease pool (``rate_limit.acquire_concurrency_lease``) so a
crashed worker's capacity is released automatically.

These are hard request/attempt/concurrency caps plus token accounting. They
are NOT a guaranteed monetary spending ceiling: no provider pricing is
embedded here (see docs/reliability-release.md, "Remaining limitations").
"""

from __future__ import annotations

import contextvars
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)

PROVIDER_ATTEMPTS_PER_ACTION = int(os.environ.get("PROVIDER_ATTEMPTS_PER_ACTION", "8"))
ACTION_GENERATION_DEADLINE_SEC = int(os.environ.get("ACTION_GENERATION_DEADLINE_SEC", "240"))
PROVIDER_GLOBAL_ATTEMPT_MAX = int(os.environ.get("PROVIDER_GLOBAL_ATTEMPT_MAX", "500"))
PROVIDER_GLOBAL_ATTEMPT_WINDOW_SEC = int(
    os.environ.get("PROVIDER_GLOBAL_ATTEMPT_WINDOW_SEC", "3600")
)
PROVIDER_GLOBAL_CONCURRENT = int(os.environ.get("PROVIDER_GLOBAL_CONCURRENT", "4"))
PROVIDER_CONCURRENCY_POOL_ID = "provider_concurrent"
PROVIDER_USAGE_COLLECTION = "provider_usage"
USAGE_RETENTION_DAYS = int(os.environ.get("PROVIDER_USAGE_RETENTION_DAYS", "30"))

KIND_ACTION = "action"
KIND_STORY_CREATION = "story_creation"


class ProviderBudgetError(Exception):
    """Base class: the provider must not be called."""

    reason = "budget"


class ProviderBudgetMissing(ProviderBudgetError):
    """No budget is active for this call (fail closed)."""

    reason = "no_budget"


class ProviderBudgetExhausted(ProviderBudgetError):
    """Per-request attempt budget or deadline exhausted."""

    def __init__(self, message: str, reason: str):
        super().__init__(message)
        self.reason = reason


class ProviderQuotaExceeded(ProviderBudgetError):
    """Global provider-attempt quota exhausted (HTTP 429 for the route)."""

    reason = "global_quota"


class ProviderBudgetUnavailable(ProviderBudgetError):
    """Limiter storage unavailable (HTTP 503 for the route; fail closed)."""

    reason = "unavailable"


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------
class BudgetStore(Protocol):
    async def reserve_global_attempt(self) -> None: ...

    async def record_attempt_started(self, doc: Dict[str, Any]) -> str: ...

    async def record_attempt_finished(self, attempt_id: str, patch: Dict[str, Any]) -> None: ...


class MongoBudgetStore:
    """Mongo-backed global quota + usage records (production store)."""

    def __init__(self, db):
        self.db = db

    async def reserve_global_attempt(self) -> None:
        # Imported lazily to keep this module importable without FastAPI deps
        # in tools; rate_limit raises HTTPException(429/503) which we translate.
        from fastapi import HTTPException

        import rate_limit

        bucket_id = rate_limit._window_bucket(
            "provider-attempts", "all", PROVIDER_GLOBAL_ATTEMPT_WINDOW_SEC
        )
        try:
            await rate_limit._consume_bucket(
                self.db,
                bucket_id,
                PROVIDER_GLOBAL_ATTEMPT_MAX,
                PROVIDER_GLOBAL_ATTEMPT_WINDOW_SEC,
            )
        except HTTPException as exc:
            if exc.status_code == 429:
                raise ProviderQuotaExceeded("global provider attempt quota exhausted") from exc
            raise ProviderBudgetUnavailable("limiter storage unavailable") from exc
        except Exception as exc:
            logger.exception("global provider attempt reservation failed")
            raise ProviderBudgetUnavailable("limiter storage unavailable") from exc

    async def record_attempt_started(self, doc: Dict[str, Any]) -> str:
        attempt_id = str(uuid.uuid4())
        record = {
            "_id": attempt_id,
            **doc,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=USAGE_RETENTION_DAYS),
        }
        try:
            await self.db[PROVIDER_USAGE_COLLECTION].insert_one(record)
        except Exception as exc:
            # Usage accounting must exist before paid work starts: fail closed.
            logger.exception("provider usage record insert failed")
            raise ProviderBudgetUnavailable("usage storage unavailable") from exc
        return attempt_id

    async def record_attempt_finished(self, attempt_id: str, patch: Dict[str, Any]) -> None:
        try:
            await self.db[PROVIDER_USAGE_COLLECTION].update_one(
                {"_id": attempt_id}, {"$set": patch}
            )
        except Exception:
            # The started record stays in place (status "started" = uncertain);
            # never erase usage because the final write failed.
            logger.exception("provider usage record update failed for %s", attempt_id)


class MemoryBudgetStore:
    """In-memory store for offline tools and tests. Never used by the server."""

    def __init__(self, global_limit: Optional[int] = None):
        self.global_limit = global_limit
        self.global_attempts = 0
        self.records: Dict[str, Dict[str, Any]] = {}

    async def reserve_global_attempt(self) -> None:
        if self.global_limit is not None and self.global_attempts >= self.global_limit:
            raise ProviderQuotaExceeded("global provider attempt quota exhausted")
        self.global_attempts += 1

    async def record_attempt_started(self, doc: Dict[str, Any]) -> str:
        attempt_id = str(uuid.uuid4())
        self.records[attempt_id] = dict(doc)
        return attempt_id

    async def record_attempt_finished(self, attempt_id: str, patch: Dict[str, Any]) -> None:
        self.records.setdefault(attempt_id, {}).update(patch)


async def ensure_provider_usage_indexes(db) -> None:
    coll = db[PROVIDER_USAGE_COLLECTION]
    await coll.create_index(
        [("expires_at", 1)], name="provider_usage_expires_ttl", expireAfterSeconds=0
    )
    await coll.create_index([("request_key", 1)], name="provider_usage_request_key")


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------
class ProviderBudget:
    def __init__(
        self,
        store: BudgetStore,
        *,
        request_key: str,
        kind: str,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
        max_attempts: Optional[int] = None,
        deadline_seconds: Optional[float] = None,
    ):
        self.store = store
        self.request_key = request_key
        self.kind = kind
        self.device_id = device_id
        self.session_id = session_id
        self.max_attempts = int(
            max_attempts if max_attempts is not None else PROVIDER_ATTEMPTS_PER_ACTION
        )
        self.deadline_seconds = float(
            deadline_seconds if deadline_seconds is not None else ACTION_GENERATION_DEADLINE_SEC
        )
        self.started_monotonic = time.monotonic()
        self.attempts_used = 0
        self.attempt_ids: List[str] = []
        self.usage: List[Dict[str, Any]] = []

    # -- time ---------------------------------------------------------------
    def remaining_seconds(self) -> float:
        return self.deadline_seconds - (time.monotonic() - self.started_monotonic)

    def deadline_passed(self) -> bool:
        return self.remaining_seconds() <= 0

    # -- attempts -----------------------------------------------------------
    async def reserve_attempt(self, model_id: str) -> str:
        """Reserve one provider attempt or raise. Must be called before each call."""
        if self.deadline_passed():
            raise ProviderBudgetExhausted(
                f"generation deadline of {int(self.deadline_seconds)}s exceeded", "deadline"
            )
        if self.attempts_used >= self.max_attempts:
            raise ProviderBudgetExhausted(
                f"provider attempt budget of {self.max_attempts} exhausted", "attempts"
            )
        try:
            await self.store.reserve_global_attempt()
            self.attempts_used += 1
            attempt_id = await self.store.record_attempt_started(
                {
                    "request_key": self.request_key,
                    "kind": self.kind,
                    "device_id": self.device_id,
                    "session_id": self.session_id,
                    "model": model_id,
                    "attempt_index": self.attempts_used,
                    "status": "started",
                    "started_at": datetime.now(timezone.utc),
                }
            )
        except ProviderBudgetError:
            raise
        except Exception as exc:
            # Any limiter/usage storage failure must stop paid work (fail closed).
            logger.exception("provider budget store failure")
            raise ProviderBudgetUnavailable("budget storage unavailable") from exc
        self.attempt_ids.append(attempt_id)
        return attempt_id

    async def record_result(
        self,
        attempt_id: str,
        *,
        telemetry: Optional[Dict[str, Any]] = None,
        error: Optional[BaseException] = None,
    ) -> None:
        """Persist the attempt outcome. Missing token telemetry is recorded explicitly."""
        finished_at = datetime.now(timezone.utc)
        if error is not None:
            kind = getattr(error, "kind", None) or type(error).__name__
            # A timeout or transport failure may still have incurred provider
            # usage we cannot observe: keep it as an uncertain-usage record.
            status = "uncertain" if kind in ("timeout", "provider_unavailable") else "error"
            patch: Dict[str, Any] = {
                "status": status,
                "error_kind": str(kind)[:64],
                "finished_at": finished_at,
                "telemetry_missing": True,
            }
        else:
            telemetry = telemetry or {}
            prompt_tokens = telemetry.get("prompt_tokens")
            completion_tokens = telemetry.get("completion_tokens")
            total_tokens = telemetry.get("total_tokens")
            if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
                total_tokens = int(prompt_tokens) + int(completion_tokens)
            patch = {
                "status": "ok",
                "finished_at": finished_at,
                "latency_ms": telemetry.get("latency_ms"),
                "provider_route": telemetry.get("provider_route"),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "telemetry_missing": total_tokens is None,
            }
        self.usage.append({"attempt_id": attempt_id, **patch})
        await self.store.record_attempt_finished(attempt_id, patch)

    def summary(self) -> Dict[str, Any]:
        """Engine-only telemetry summary (never player-facing)."""
        total = 0
        missing = 0
        for row in self.usage:
            if row.get("total_tokens") is None:
                missing += 1
            else:
                total += int(row["total_tokens"])
        return {
            "attempts_used": self.attempts_used,
            "attempts_budget": self.max_attempts,
            "tokens_total": total,
            "attempts_without_token_telemetry": missing,
            "deadline_seconds": self.deadline_seconds,
        }


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------
_ACTIVE: contextvars.ContextVar[Optional[ProviderBudget]] = contextvars.ContextVar(
    "provider_budget", default=None
)


def current() -> Optional[ProviderBudget]:
    return _ACTIVE.get()


def require_active() -> ProviderBudget:
    budget = _ACTIVE.get()
    if budget is None:
        raise ProviderBudgetMissing(
            "provider call attempted without an active provider budget"
        )
    return budget


@asynccontextmanager
async def active_budget(budget: ProviderBudget):
    token = _ACTIVE.set(budget)
    try:
        yield budget
    finally:
        _ACTIVE.reset(token)


def for_request(
    db,
    *,
    request_key: str,
    kind: str,
    device_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> ProviderBudget:
    return ProviderBudget(
        MongoBudgetStore(db),
        request_key=request_key,
        kind=kind,
        device_id=device_id,
        session_id=session_id,
    )


def offline_budget(
    *,
    max_attempts: Optional[int] = None,
    deadline_seconds: Optional[float] = None,
    global_limit: Optional[int] = None,
    request_key: str = "offline",
) -> ProviderBudget:
    """Budget backed by memory — for tests and offline tooling only."""
    return ProviderBudget(
        MemoryBudgetStore(global_limit=global_limit),
        request_key=request_key,
        kind="offline",
        max_attempts=max_attempts,
        deadline_seconds=deadline_seconds,
    )
