"""
MongoDB-backed abuse controls for paid story creation (POST /story/new).

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
  TRUSTED_PROXY_COUNT            — if >0, client IP from X-Forwarded-For (see below)

X-Forwarded-For selection (only when TRUSTED_PROXY_COUNT > 0):
  Deployment model: each trusted proxy appends its upstream hop to the RIGHT.
  XFF reads left-to-right as client → … → nearest proxy.
  1. Read the X-Forwarded-For header; if absent or blank, use the TCP peer host.
  2. Split on commas, strip whitespace, drop empty segments.
  3. If len(parts) <= TRUSTED_PROXY_COUNT, ignore XFF and use the TCP peer host
     (chain too short — leftmost client-supplied hops are not trusted).
  4. Otherwise return parts[-TRUSTED_PROXY_COUNT] — the leftmost hop of the
     rightmost TRUSTED_PROXY_COUNT proxy hops (verified deployment model).
  5. If the selected segment is not a plausible IP/hostname token, use the TCP peer host.

Mongo limiter mechanics:
  - Counter buckets use find_one_and_update with $inc + $setOnInsert expires_at (UTC datetime).
  - Bucket _id is the natural unique key (one document per bucket).
  - Fixed windows use wall-clock bucket ids (epoch // window_sec).
  - Partial quota reservations roll back when a later bucket or concurrent slot fails.
  - Concurrent slots use a fixed _id document; release runs in finally and clamps count >= 0.
  - TTL index on expires_at (expireAfterSeconds=0) bounds collection growth; the concurrent
    slot document has no expires_at and is not TTL-eligible.
  - Concurrent acquire is best-effort under multi-worker races; a crashed worker can leak a
    slot until manual reset (no lease/TTL on the concurrent counter).
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import HTTPException
from pymongo import ReturnDocument
from starlette.requests import Request

logger = logging.getLogger(__name__)

_RATE_LIMIT_GENERIC_DETAIL = "Too many requests"
_LIMITER_UNAVAILABLE_DETAIL = "Service unavailable"
_CONCURRENT_SLOT_ID = "story_new_concurrent"
_GLOBAL_FIXED_PREFIX = "global"

RATE_LIMIT_IP_MAX = int(os.environ.get("RATE_LIMIT_IP_MAX", "10"))
RATE_LIMIT_IP_WINDOW_SEC = int(os.environ.get("RATE_LIMIT_IP_WINDOW_SEC", "3600"))
RATE_LIMIT_DEVICE_MAX = int(os.environ.get("RATE_LIMIT_DEVICE_MAX", "5"))
RATE_LIMIT_DEVICE_WINDOW_SEC = int(os.environ.get("RATE_LIMIT_DEVICE_WINDOW_SEC", "3600"))
RATE_LIMIT_GLOBAL_MAX = int(os.environ.get("RATE_LIMIT_GLOBAL_MAX", "50"))
RATE_LIMIT_GLOBAL_WINDOW_SEC = int(os.environ.get("RATE_LIMIT_GLOBAL_WINDOW_SEC", "3600"))
RATE_LIMIT_GLOBAL_CONCURRENT = int(os.environ.get("RATE_LIMIT_GLOBAL_CONCURRENT", "3"))
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
    if len(parts) <= trusted_proxy_count:
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


def _window_bucket(prefix: str, identifier: str, window_sec: int) -> str:
    window_id = int(time.time()) // max(window_sec, 1)
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


async def acquire_story_creation_slot(db) -> None:
    """Reserve a global concurrent creation slot before LLM work."""
    try:
        doc = await db.rate_limits.find_one_and_update(
            {
                "_id": _CONCURRENT_SLOT_ID,
                "$or": [
                    {"count": {"$lt": RATE_LIMIT_GLOBAL_CONCURRENT}},
                    {"count": {"$exists": False}},
                ],
            },
            {"$inc": {"count": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if not doc or doc.get("count", 0) > RATE_LIMIT_GLOBAL_CONCURRENT:
            if doc and doc.get("count", 0) > RATE_LIMIT_GLOBAL_CONCURRENT:
                await db.rate_limits.update_one(
                    {"_id": _CONCURRENT_SLOT_ID}, {"$inc": {"count": -1}}
                )
            raise HTTPException(status_code=429, detail=_RATE_LIMIT_GENERIC_DETAIL)
    except HTTPException:
        raise
    except Exception:
        logger.exception("concurrent slot acquire failure")
        raise HTTPException(status_code=503, detail=_LIMITER_UNAVAILABLE_DETAIL)


async def release_story_creation_slot(db) -> None:
    """Release a global concurrent slot after creation completes or aborts."""
    try:
        await db.rate_limits.update_one(
            {"_id": _CONCURRENT_SLOT_ID},
            {"$inc": {"count": -1}},
        )
        await db.rate_limits.update_one(
            {"_id": _CONCURRENT_SLOT_ID, "count": {"$lt": 0}},
            {"$set": {"count": 0}},
        )
    except Exception:
        logger.exception("concurrent slot release failure")


async def read_concurrent_slot_count(db) -> int:
    """Test/diagnostic helper — current concurrent slot counter."""
    doc = await db.rate_limits.find_one({"_id": _CONCURRENT_SLOT_ID})
    return int((doc or {}).get("count", 0))