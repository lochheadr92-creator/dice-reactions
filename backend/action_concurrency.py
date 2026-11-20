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
# Monotonic per-session revision. Every committed gameplay mutation (action
# commit, reset) increments it, so a stale worker can never commit against a
# revision that reset/delete has already superseded — even when turn_count
# happens to return to the same value. Legacy sessions without the field are
# normalised to 0 on their next lease acquisition.
SESSION_REVISION_FIELD = "session_revision"

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


def utc_now() -> datetime:
    if _clock_override is not None:
        return _clock_override
    return datetime.now(timezone.utc)


def set_clock_for_tests(moment: Optional[datetime]) -> None:
    """Inject deterministic time for lease expiry tests."""
    global _clock_override
    _clock_override = moment


def _lease_floor_seconds() -> int:
    """A lease (and request claim) must outlive one full generation + commit.

    Otherwise a retry could take over a still-running action and pay for a
    second generation. Imported lazily to avoid an import cycle.
    """
    import provider_budget

    return int(provider_budget.ACTION_GENERATION_DEADLINE_SEC) + 60


def resolve_lease_seconds() -> int:
    raw = os.environ.get(LEASE_ENV_VAR)
    if raw is None or str(raw).strip() == "":
        value = DEFAULT_LEASE_SECONDS
    else:
        try:
            value = int(str(raw).strip())
        except ValueError:
            value = DEFAULT_LEASE_SECONDS
        value = max(MIN_LEASE_SECONDS, min(MAX_LEASE_SECONDS, value))
    return max(value, _lease_floor_seconds())


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
    purpose: str = "action",
) -> Tuple[Dict[str, Any], str]:
    """Atomically acquire a per-session lease. Returns (session, token).

    The same lease guards player actions, reset, and delete so none of them can
    overlap. The returned session always carries ``session_revision`` (legacy
    documents are normalised to 0 in the same atomic update).
    """
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
        [
            {
                "$set": {
                    ACTION_LOCK_TOKEN_FIELD: token,
                    ACTION_LOCK_ACQUIRED_AT_FIELD: moment,
                    ACTION_LOCK_EXPIRES_AT_FIELD: expires_at,
                    SESSION_REVISION_FIELD: {
                        "$ifNull": [f"${SESSION_REVISION_FIELD}", 0]
                    },
                }
            }
        ],
        return_document=ReturnDocument.AFTER,
    )
    if not locked:
        logger.info("%s lease conflict for session %s", purpose, session_id)
        raise ActionLeaseConflict()
    logger.info("%s lease acquired for session %s", purpose, session_id)
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
        {"$unset": lease_release_unset()},
    )
    if result.matched_count:
        logger.info("action lease released for session %s", session_id)
        return True
    # Normal after a committed transaction (the commit already cleared the
    # lease) or after expiry; never an error for the caller.
    logger.info("action lease release skipped for session %s", session_id)
    return False


async def release_action_lease_quietly(db, session_id: str, token: str) -> None:
    """Release a lease without letting a storage error mask the request outcome."""
    try:
        await release_action_lease(db, session_id, token)
    except Exception:
        logger.exception("lease release failed for session %s (lease will expire)", session_id)


def build_persist_cas_filter(
    session_id: str,
    lease_token: str,
    expected_turn_count: int,
    expected_revision: Optional[int] = None,
) -> Dict[str, Any]:
    """Compare-and-set filter for the final session write of one gameplay mutation.

    Matches only when the caller still owns the lease, the turn count is the one
    generation started from, and (when supplied) the session revision has not
    been superseded by a reset/delete or competing commit.
    """
    cas: Dict[str, Any] = {
        "id": session_id,
        ACTION_LOCK_TOKEN_FIELD: lease_token,
        "turn_count": expected_turn_count,
    }
    if expected_revision is not None:
        cas[SESSION_REVISION_FIELD] = expected_revision
    return cas


def lease_release_unset() -> Dict[str, Any]:
    """``$unset`` payload that clears the lease fields (used inside commits)."""
    return {
        ACTION_LOCK_TOKEN_FIELD: "",
        ACTION_LOCK_ACQUIRED_AT_FIELD: "",
        ACTION_LOCK_EXPIRES_AT_FIELD: "",
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