"""
MongoDB-backed abuse controls for paid story work (POST /story/new, POST /story/action).

Limits are enforced before any session insert or LLM invocation.
Fails closed when the limiter backend is unavailable.

Environment variables (safe defaults):
  RATE_LIMIT_IP_MAX              — max creations per IP per window (default 10)
  RATE_LIMIT_IP_WINDOW_SEC       — IP window length in seconds (default 3600)
  RATE_LIMIT_DEVICE_MAX          — max creations per device_id per window (default 5)
  RATE_LIMIT_DEVICE_WINDOW_SEC   — device window length in seconds (default 3600)
  RATE_LIMIT_GLOBAL_MAX          — max total creations globally per fixed window (default 50)
  RATE_LIMIT_GLOBAL_WINDOW_SEC   — global fixed window length in seconds (default 3600)
  RATE_LIMIT_GLOBAL_CONCURRENT   — max in-flight story creations (default 3)
  RATE_LIMIT_ACTION_DEVICE_MAX   — max player actions per device_id per window (default 60)
  RATE_LIMIT_ACTION_DEVICE_WINDOW_SEC — action device window in seconds (default 3600)
  STORY_CREATION_LEASE_SEC       — creation concurrency lease lifetime (default 600)
  TRUSTED_PROXY_COUNT            — if >0, client IP from X-Forwarded-For (see below)

X-Forwarded-For selection (only when TRUSTED_PROXY_COUNT > 0):
  Deployment model: each trusted proxy appends its upstream hop to the RIGHT.
  XFF reads left-to-right as client → … → nearest proxy.
  1. Read the X-Forwarded-For header; if absent or blank, use the TCP peer host.
  2. Split on commas, strip whitespace, drop empty segments.
  3. If len(parts) < TRUSTED_PROXY_COUNT, ignore XFF and use the TCP peer host
     (chain shorter than the proxy depth: the deployment does not match).
  4. Otherwise return parts[-TRUSTED_PROXY_COUNT]. With N trusted proxies the
     honest chain has exactly N entries (client, proxy 1, ... proxy N-1), so
     this is the client address; anything a client prepends sits further left
     and is ignored.
  5. If the selected segment is not a plausible IP/hostname token, use the TCP peer host.

Mongo limiter mechanics:
  - Counter buckets use find_one_and_update with $inc + $setOnInsert expires_at (UTC datetime).
  - Bucket _id is the natural unique key (one document per bucket).
  - Fixed windows use wall-clock bucket ids (epoch // window_sec).
  - Partial quota reservations roll back when a later bucket or concurrency lease fails.
  - Concurrency pools are documents holding expiring leases ({token, owner,
    expires_at}). Acquire is a single atomic update guarded by a $expr count of
    unexpired leases, so concurrent workers cannot over-reserve. Only the exact
    token can renew or release its lease; a crashed worker's lease expires on
    its own and frees the capacity.
  - TTL index on expires_at (expireAfterSeconds=0) bounds collection growth; pool
    documents have no top-level expires_at and are not TTL-eligible.
"""

from __future__ import annotations

import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from starlette.requests import Request

logger = logging.getLogger(__name__)

_RATE_LIMIT_GENERIC_DETAIL = "Too many requests"
_LIMITER_UNAVAILABLE_DETAIL = "Service unavailable"
_CONCURRENT_SLOT_ID = "story_new_concurrent"
STORY_CREATION_POOL_ID = _CONCURRENT_SLOT_ID
_GLOBAL_FIXED_PREFIX = "global"

RATE_LIMIT_IP_MAX = int(os.environ.get("RATE_LIMIT_IP_MAX", "10"))
RATE_LIMIT_IP_WINDOW_SEC = int(os.environ.get("RATE_LIMIT_IP_WINDOW_SEC", "3600"))
RATE_LIMIT_DEVICE_MAX = int(os.environ.get("RATE_LIMIT_DEVICE_MAX", "5"))
RATE_LIMIT_DEVICE_WINDOW_SEC = int(os.environ.get("RATE_LIMIT_DEVICE_WINDOW_SEC", "3600"))
RATE_LIMIT_GLOBAL_MAX = int(os.environ.get("RATE_LIMIT_GLOBAL_MAX", "50"))
RATE_LIMIT_GLOBAL_WINDOW_SEC = int(os.environ.get("RATE_LIMIT_GLOBAL_WINDOW_SEC", "3600"))
RATE_LIMIT_GLOBAL_CONCURRENT = int(os.environ.get("RATE_LIMIT_GLOBAL_CONCURRENT", "3"))
RATE_LIMIT_ACTION_DEVICE_MAX = int(os.environ.get("RATE_LIMIT_ACTION_DEVICE_MAX", "60"))
RATE_LIMIT_ACTION_DEVICE_WINDOW_SEC = int(
    os.environ.get("RATE_LIMIT_ACTION_DEVICE_WINDOW_SEC", "3600")
)
STORY_CREATION_LEASE_SEC = int(os.environ.get("STORY_CREATION_LEASE_SEC", "600"))
TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", "0"))

_IP_TOKEN_RE = re.compile(r"^[a-zA-Z0-9.:_%\-]+$")


def _parse_xff_chain(xff: str) -> list[str]:
    return [p.strip() for p in xff.split(",") if p and p.strip()]


def _plausible_ip_token(token: str) -> bool:
    if not token or len(token) > 128:
        return False
    return bool(_IP_TOKEN_RE.match(token))


def select_xff_client_ip(parts: list[str], trusted_proxy_count: int) -> Optional[str]:
    """Pick client IP using the rightmost-N trusted-proxy deployment model."""
    if trusted_proxy_count <= 0 or not parts:
        return None
    if len(parts) < trusted_proxy_count:
        return None
    candidate = parts[-trusted_proxy_count]
    if not _plausible_ip_token(candidate):
        return None
    return candidate


def resolve_client_ip(request: Request) -> str:
    """Resolve client IP. Ignores X-Forwarded-For when TRUSTED_PROXY_COUNT is 0."""
    if TRUSTED_PROXY_COUNT > 0:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            parts = _parse_xff_chain(xff)
            selected = select_xff_client_ip(parts, TRUSTED_PROXY_COUNT)
            if selected:
                return selected
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _epoch_seconds() -> float:
    """Wall clock for fixed-window bucket ids (patched by tests to freeze windows)."""
    return time.time()


def _window_bucket(prefix: str, identifier: str, window_sec: int) -> str:
    window_id = int(_epoch_seconds()) // max(window_sec, 1)
    return f"{prefix}:{identifier}:{window_id}"


async def ensure_rate_limit_indexes(db) -> None:
    """Ensure TTL index for counter bucket expiry. Safe to call on startup."""
    try:
        await db.rate_limits.create_index(
            [("expires_at", 1)],
            name="rate_limits_expires_ttl",
            expireAfterSeconds=0,
            partialFilterExpression={"expires_at": {"$exists": True}},
        )
    except Exception:
        logger.exception("rate_limit index ensure failed")


async def _prune_expired_buckets(db) -> None:
    """Drop expired counter documents to bound collection growth (TTL backup)."""
    try:
        await db.rate_limits.delete_many(
            {
                "_id": {"$ne": _CONCURRENT_SLOT_ID},
                "leases": {"$exists": False},
                "expires_at": {"$lt": datetime.now(timezone.utc)},
            }
        )
    except Exception:
        logger.exception("rate_limit prune failed")


async def _rollback_bucket_reservations(db, bucket_ids: List[str]) -> None:
    """Undo quota reservations when a later limit check fails."""
    for bucket_id in reversed(bucket_ids):
        try:
            await db.rate_limits.update_one({"_id": bucket_id}, {"$inc": {"count": -1}})
        except Exception:
            logger.exception("rate_limit rollback failed for bucket %s", bucket_id)


async def _consume_bucket(
    db,
    bucket_id: str,
    limit: int,
    window_sec: int,
) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=window_sec * 2)
    doc = await db.rate_limits.find_one_and_update(
        {"_id": bucket_id},
        {
            "$inc": {"count": 1},
            "$setOnInsert": {"expires_at": expires_at},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if (doc or {}).get("count", 0) > limit:
        await db.rate_limits.update_one({"_id": bucket_id}, {"$inc": {"count": -1}})
        raise HTTPException(status_code=429, detail=_RATE_LIMIT_GENERIC_DETAIL)


async def check_story_creation_limits(db, client_ip: str, device_id: str) -> List[str]:
    """Reserve quota buckets; return consumed ids for caller rollback on concurrent failure."""
    consumed: List[str] = []
    try:
        await _prune_expired_buckets(db)
        reservations = (
            (
                _window_bucket(_GLOBAL_FIXED_PREFIX, "all", RATE_LIMIT_GLOBAL_WINDOW_SEC),
                RATE_LIMIT_GLOBAL_MAX,
                RATE_LIMIT_GLOBAL_WINDOW_SEC,
            ),
            (
                _window_bucket("ip", client_ip, RATE_LIMIT_IP_WINDOW_SEC),
                RATE_LIMIT_IP_MAX,
                RATE_LIMIT_IP_WINDOW_SEC,
            ),
            (
                _window_bucket("device", device_id, RATE_LIMIT_DEVICE_WINDOW_SEC),
                RATE_LIMIT_DEVICE_MAX,
                RATE_LIMIT_DEVICE_WINDOW_SEC,
            ),
        )
        for bucket_id, limit, window_sec in reservations:
            await _consume_bucket(db, bucket_id, limit, window_sec)
            consumed.append(bucket_id)
        return consumed
    except HTTPException:
        await _rollback_bucket_reservations(db, consumed)
        raise
    except Exception:
        await _rollback_bucket_reservations(db, consumed)
        logger.exception("rate_limit backend failure")
        raise HTTPException(status_code=503, detail=_LIMITER_UNAVAILABLE_DETAIL)


async def check_action_limits(db, device_id: str) -> List[str]:
    """Reserve the per-device action quota; return consumed ids for rollback."""
    consumed: List[str] = []
    try:
        await _prune_expired_buckets(db)
        bucket_id = _window_bucket(
            "action-device", device_id, RATE_LIMIT_ACTION_DEVICE_WINDOW_SEC
        )
        await _consume_bucket(
            db, bucket_id, RATE_LIMIT_ACTION_DEVICE_MAX, RATE_LIMIT_ACTION_DEVICE_WINDOW_SEC
        )
        consumed.append(bucket_id)
        return consumed
    except HTTPException:
        await _rollback_bucket_reservations(db, consumed)
        raise
    except Exception:
        await _rollback_bucket_reservations(db, consumed)
        logger.exception("rate_limit backend failure (action)")
        raise HTTPException(status_code=503, detail=_LIMITER_UNAVAILABLE_DETAIL)


# ---------------------------------------------------------------------------
# Expiring concurrency leases (atomic reservation, ownership-safe release)
# ---------------------------------------------------------------------------
class ConcurrencyPoolFull(Exception):
    """No free slot in the pool right now."""


class ConcurrencyPoolUnavailable(Exception):
    """Limiter storage failed; callers must fail closed."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: Any) -> datetime:
    if not isinstance(value, datetime):
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def acquire_concurrency_lease(
    db,
    pool_id: str,
    limit: int,
    ttl_seconds: int,
    *,
    owner: str = "",
) -> str:
    """Atomically reserve one slot in ``pool_id``; return the lease token.

    The reservation update only matches when fewer than ``limit`` unexpired
    leases exist, so concurrent workers cannot over-reserve. Expired leases are
    pruned first so a crashed worker's capacity is reclaimed automatically.
    """
    if limit <= 0:
        raise ConcurrencyPoolFull()
    token = str(uuid.uuid4())
    now = _now()
    lease = {
        "token": token,
        "owner": owner or token,
        "acquired_at": now,
        "expires_at": now + timedelta(seconds=max(1, int(ttl_seconds))),
    }
    try:
        try:
            await db.rate_limits.update_one(
                {"_id": pool_id},
                {"$setOnInsert": {"leases": []}},
                upsert=True,
            )
        except DuplicateKeyError:
            pass  # two workers created the pool document at the same instant
        await db.rate_limits.update_one(
            {"_id": pool_id},
            {"$pull": {"leases": {"expires_at": {"$lte": now}}}},
        )
        result = await db.rate_limits.update_one(
            {
                "_id": pool_id,
                "$expr": {
                    "$lt": [
                        {
                            "$size": {
                                "$filter": {
                                    "input": {"$ifNull": ["$leases", []]},
                                    "cond": {"$gt": ["$$this.expires_at", now]},
                                }
                            }
                        },
                        int(limit),
                    ]
                },
            },
            {"$push": {"leases": lease}},
        )
    except Exception as exc:
        logger.exception("concurrency lease acquire failed for pool %s", pool_id)
        raise ConcurrencyPoolUnavailable(str(exc)) from exc
    if result.matched_count == 0:
        raise ConcurrencyPoolFull()
    return token


async def renew_concurrency_lease(db, pool_id: str, token: str, ttl_seconds: int) -> bool:
    """Extend only the lease owned by ``token``."""
    try:
        result = await db.rate_limits.update_one(
            {"_id": pool_id, "leases.token": token},
            {
                "$set": {
                    "leases.$.expires_at": _now() + timedelta(seconds=max(1, int(ttl_seconds)))
                }
            },
        )
    except Exception:
        logger.exception("concurrency lease renew failed for pool %s", pool_id)
        return False
    return bool(result.matched_count)


async def release_concurrency_lease(db, pool_id: str, token: str) -> bool:
    """Release only the lease owned by ``token`` (never another worker's)."""
    if not token:
        return False
    try:
        result = await db.rate_limits.update_one(
            {"_id": pool_id, "leases.token": token},
            {"$pull": {"leases": {"token": token}}},
        )
    except Exception:
        logger.exception("concurrency lease release failed for pool %s", pool_id)
        return False
    return bool(result.matched_count)


async def clear_concurrency_pool(db, pool_id: str) -> int:
    """Drop every lease in one pool (single-process startup only). Returns count removed."""
    doc = await db.rate_limits.find_one({"_id": pool_id}, {"leases": 1})
    removed = len((doc or {}).get("leases") or [])
    if removed:
        await db.rate_limits.update_one({"_id": pool_id}, {"$set": {"leases": []}})
    return removed


async def count_active_leases(db, pool_id: str) -> int:
    doc = await db.rate_limits.find_one({"_id": pool_id})
    now = _now()
    leases = (doc or {}).get("leases") or []
    return sum(1 for lease in leases if _as_aware(lease.get("expires_at")) > now)


async def acquire_story_creation_slot(db, *, owner: str = "") -> str:
    """Reserve a global concurrent creation lease before LLM work; return token."""
    try:
        return await acquire_concurrency_lease(
            db,
            _CONCURRENT_SLOT_ID,
            RATE_LIMIT_GLOBAL_CONCURRENT,
            STORY_CREATION_LEASE_SEC,
            owner=owner,
        )
    except ConcurrencyPoolFull:
        raise HTTPException(status_code=429, detail=_RATE_LIMIT_GENERIC_DETAIL)
    except ConcurrencyPoolUnavailable:
        raise HTTPException(status_code=503, detail=_LIMITER_UNAVAILABLE_DETAIL)


async def release_story_creation_slot(db, token: str) -> None:
    """Release this worker's creation lease after creation completes or aborts."""
    await release_concurrency_lease(db, _CONCURRENT_SLOT_ID, token)


async def read_concurrent_slot_count(db) -> int:
    """Test/diagnostic helper — number of unexpired creation leases."""
    return await count_active_leases(db, _CONCURRENT_SLOT_ID)