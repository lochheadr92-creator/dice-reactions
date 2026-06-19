"""
Session Action Concurrency Guard v1 — Mongo-backed per-session leases.

Prevents overlapping POST /story/action requests from racing on turn numbers,
rolling state, secret reveals, and provider calls across workers.
"""

from __future__ import annotations

import hmac
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from pymongo import ReturnDocument

logger = logging.getLogger(__name__)

ACTION_LOCK_TOKEN_FIELD = "action_lock_token"
ACTION_LOCK_ACQUIRED_AT_FIELD = "action_lock_acquired_at"
ACTION_LOCK_EXPIRES_AT_FIELD = "action_lock_expires_at"
ACTION_LOCK_FIELDS = (
    ACTION_LOCK_TOKEN_FIELD,
    ACTION_LOCK_ACQUIRED_AT_FIELD,
    ACTION_LOCK_EXPIRES_AT_FIELD,
)

ACTION_CONFLICT_DETAIL = "An action is already in progress for this chronicle"
_SESSION_NOT_FOUND_DETAIL = "Session not found"
_DEVICE_ID_REQUIRED_DETAIL = "device_id is required"

DEFAULT_LEASE_SECONDS = 600
MIN_LEASE_SECONDS = 60
MAX_LEASE_SECONDS = 3600
LEASE_ENV_VAR = "ACTION_LOCK_LEASE_SEC"

_clock_override: Optional[datetime] = None


class ActionLeaseConflict(Exception):
    """Another unexpired action owns this session."""


class ActionLeaseLost(Exception):
    """Lease or expected turn_count no longer matches before final persistence."""


def utc_now() -> datetime:
    if _clock_override is not None:
        return _clock_override
    return datetime.now(timezone.utc)


def set_clock_for_tests(moment: Optional[datetime]) -> None:
    """Inject deterministic time for lease expiry tests."""
    global _clock_override
    _clock_override = moment


def resolve_lease_seconds() -> int:
    raw = os.environ.get(LEASE_ENV_VAR)
    if raw is None or str(raw).strip() == "":
        return DEFAULT_LEASE_SECONDS
    try:
        value = int(str(raw).strip())
    except ValueError:
        return DEFAULT_LEASE_SECONDS
    return max(MIN_LEASE_SECONDS, min(MAX_LEASE_SECONDS, value))


def _lease_available_filter(now: datetime) -> Dict[str, Any]:
    return {
        "$or": [
            {ACTION_LOCK_TOKEN_FIELD: {"$exists": False}},
            {ACTION_LOCK_TOKEN_FIELD: None},
            {ACTION_LOCK_EXPIRES_AT_FIELD: {"$lte": now}},
        ]
    }


async def _verify_session_owner(
    db,
    session_id: str,
    device_id: str,
) -> None:
    if not device_id or not str(device_id).strip():
        raise HTTPException(status_code=400, detail=_DEVICE_ID_REQUIRED_DETAIL)
    session = await db.sessions.find_one({"id": session_id}, {"_id": 0, "device_id": 1})
    if not session:
        raise HTTPException(status_code=404, detail=_SESSION_NOT_FOUND_DETAIL)
    stored = str(session.get("device_id") or "")
    provided = str(device_id)
    if not stored or not hmac.compare_digest(stored, provided):
        raise HTTPException(status_code=404, detail=_SESSION_NOT_FOUND_DETAIL)


async def acquire_action_lease(
    db,
    session_id: str,
    device_id: str,
    *,
    now: Optional[datetime] = None,
) -> Tuple[Dict[str, Any], str]:
    """Atomically acquire a per-session action lease. Returns (session, token)."""
    await _verify_session_owner(db, session_id, device_id)
    moment = now or utc_now()
    token = str(uuid.uuid4())
    expires_at = moment + timedelta(seconds=resolve_lease_seconds())
    acquire_filter = {
        "id": session_id,
        "device_id": device_id,
        **_lease_available_filter(moment),
    }
    locked = await db.sessions.find_one_and_update(
        acquire_filter,
        {
            "$set": {
                ACTION_LOCK_TOKEN_FIELD: token,
                ACTION_LOCK_ACQUIRED_AT_FIELD: moment,
                ACTION_LOCK_EXPIRES_AT_FIELD: expires_at,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if not locked:
        logger.info("action lease conflict for session %s", session_id)
        raise ActionLeaseConflict()
    logger.info("action lease acquired for session %s", session_id)
    locked.pop("_id", None)
    return locked, token


async def release_action_lease(
    db,
    session_id: str,
    token: str,
) -> bool:
    """Release only when the exact token still owns the lease."""
    if not token:
        return False
    result = await db.sessions.update_one(
        {"id": session_id, ACTION_LOCK_TOKEN_FIELD: token},
        {
            "$unset": {
                ACTION_LOCK_TOKEN_FIELD: "",
                ACTION_LOCK_ACQUIRED_AT_FIELD: "",
                ACTION_LOCK_EXPIRES_AT_FIELD: "",
            }
        },
    )
    if result.matched_count:
        logger.info("action lease released for session %s", session_id)
        return True
    logger.warning("action lease release skipped for session %s", session_id)
    return False


def build_persist_cas_filter(
    session_id: str,
    lease_token: str,
    expected_turn_count: int,
) -> Dict[str, Any]:
    return {
        "id": session_id,
        ACTION_LOCK_TOKEN_FIELD: lease_token,
        "turn_count": expected_turn_count,
    }


def build_model_lock_patch(
    meta: Dict[str, Any], at_turn: int
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return ($set fields, $push ops) for model-lock fields."""
    update_set: Dict[str, Any] = {}
    push_ops: Dict[str, Any] = {}
    if meta.get("model_used"):
        update_set["active_model"] = meta["model_used"]
    fe = list(meta.get("fallback_events") or [])
    if fe:
        now = utc_now().isoformat()
        entries = [
            {
                "from_model": e.get("from"),
                "to_model": e.get("to"),
                "reason": e.get("reason"),
                "message": e.get("message"),
                "at_turn": at_turn,
                "ts": now,
            }
            for e in fe
        ]
        push_ops["model_switches"] = {"$each": entries}
    return update_set, push_ops


async def find_duplicate_turn_numbers(db) -> List[Dict[str, Any]]:
    pipeline = [
        {
            "$group": {
                "_id": {"session_id": "$session_id", "turn_number": "$turn_number"},
                "count": {"$sum": 1},
            }
        },
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 20},
    ]
    return await db.turns.aggregate(pipeline).to_list(length=20)


async def ensure_action_concurrency_indexes(db) -> None:
    """Create idempotent indexes; skip unique (session_id, turn_number) if duplicates exist."""
    duplicates = await find_duplicate_turn_numbers(db)
    if duplicates:
        logger.error(
            "action concurrency indexes deferred: duplicate turn rows detected (%s groups)",
            len(duplicates),
        )
        return
    await db.sessions.create_index("id", unique=True, name="sessions_id_unique")
    await db.turns.create_index("id", unique=True, name="turns_id_unique")
    await db.turns.create_index(
        [("session_id", 1), ("turn_number", 1)],
        unique=True,
        name="turns_session_turn_unique",
    )