"""
Action request idempotency records (POST /story/action).

One client-generated ``action_request_id`` maps to at most one committed game
transition. The record is bound to the owner device, the session, and a
fingerprint of the meaningful request contents.

Record lifecycle (``status``):
  in_progress  — a worker holds the claim (``claim_token`` / ``claim_expires_at``)
  completed    — the turn committed; ``turn_id`` / ``turn_number`` identify it
  failed       — no transition happened; ``error_kind`` says why; retryable
  uncertain    — the worker could not learn the commit outcome; resolved on
                 the next claim/status read by looking for the committed turn

Privacy: records hold identifiers and a hash only — never narrative, state,
raw provider output, or response bytes. Replays are rebuilt from the turn
document through the current ownership check and player-safe serializers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure

from action_concurrency import resolve_lease_seconds, utc_now
from security import constant_time_equals
from turn_commit import ACTION_REQUESTS_COLLECTION, TURN_REQUEST_KEY_FIELD

logger = logging.getLogger(__name__)

STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_UNCERTAIN = "uncertain"

# Player-safe error kinds persisted on failed records.
ERROR_PROVIDER = "provider_unavailable"
ERROR_CONFLICT = "conflict"
ERROR_RATE_LIMITED = "rate_limited"
ERROR_VALIDATION = "validation"
ERROR_STORAGE = "storage"
ERROR_SUPERSEDED = "superseded"
ERROR_INTERRUPTED = "interrupted"

REQUEST_ID_MAX_LENGTH = 128
TURN_REQUEST_KEY_UNIQUE_INDEX = "turns_action_request_key_unique"
RECORD_RETENTION_DAYS = 7

REQUEST_MISMATCH_DETAIL = "action_request_id was already used for a different action"


class ActionRequestMismatch(Exception):
    """The request id exists with different meaningful contents."""


@dataclass
class ClaimResult:
    kind: str  # new | reclaimed | completed | in_progress
    record: Dict[str, Any]
    claim_token: Optional[str] = None


def normalize_request_id(value: Optional[str]) -> Optional[str]:
    text = (value or "").strip()
    if not text:
        return None
    if len(text) > REQUEST_ID_MAX_LENGTH:
        return None
    return text


def request_key(session_id: str, request_id: str) -> str:
    return f"{session_id}|{request_id}"


def fingerprint(session_id: str, action_text: str, debug_mode: bool) -> str:
    canonical = json.dumps(
        {
            "session_id": session_id,
            "action_text": (action_text or "").strip(),
            "debug_mode": bool(debug_mode),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def claim_ttl_seconds() -> int:
    # Same lifetime as the session lease: both are floored by the generation
    # deadline (+60s commit slack) so a running action cannot be taken over.
    return resolve_lease_seconds()


async def ensure_action_request_indexes(db) -> None:
    coll = db[ACTION_REQUESTS_COLLECTION]
    await coll.create_index(
        [("expires_at", 1)],
        name="action_requests_expires_ttl",
        expireAfterSeconds=0,
    )
    await coll.create_index([("session_id", 1)], name="action_requests_session")
    # One request key => at most one turn, enforced by the database and not
    # only by claim logic. Databases created by the first reliability build
    # also hold a non-unique "turns_action_request_key" index; MongoDB allows
    # both side by side, and dropping the old one is left to the operator.
    try:
        await db.turns.create_index(
            [(TURN_REQUEST_KEY_FIELD, 1)],
            name=TURN_REQUEST_KEY_UNIQUE_INDEX,
            unique=True,
            partialFilterExpression={TURN_REQUEST_KEY_FIELD: {"$type": "string"}},
        )
    except OperationFailure as exc:
        # Existing duplicate keys block the unique index. Never delete data
        # here: report it (GET /admin/consistency) and keep serving.
        logger.error(
            "unique index %s not created (%s); duplicate request keys need operator review",
            TURN_REQUEST_KEY_UNIQUE_INDEX,
            getattr(exc, "code", type(exc).__name__),
        )


def _owner_matches(record: Dict[str, Any], device_id: str) -> bool:
    stored = str(record.get("device_id") or "")
    return bool(stored) and constant_time_equals(stored, device_id)


async def _find_committed_turn(db, key: str) -> Optional[Dict[str, Any]]:
    return await db.turns.find_one(
        {TURN_REQUEST_KEY_FIELD: key}, {"_id": 0, "id": 1, "turn_number": 1, "session_id": 1}
    )


async def resolve_record(db, record: Dict[str, Any]) -> Dict[str, Any]:
    """Repair a record whose worker stopped before writing its final status.

    Looks for the committed turn carrying this request key. Only the request
    record is corrected — gameplay data is never rewritten.
    """
    if record.get("status") not in (STATUS_UNCERTAIN, STATUS_IN_PROGRESS):
        return record
    if record.get("status") == STATUS_IN_PROGRESS:
        expires = record.get("claim_expires_at")
        if expires is not None and _as_aware(expires) > utc_now():
            return record
    turn = await _find_committed_turn(db, record["_id"])
    now = utc_now()
    if turn:
        updated = await db[ACTION_REQUESTS_COLLECTION].find_one_and_update(
            {"_id": record["_id"], "status": {"$in": [STATUS_UNCERTAIN, STATUS_IN_PROGRESS]}},
            {
                "$set": {
                    "status": STATUS_COMPLETED,
                    "turn_id": turn["id"],
                    "turn_number": turn["turn_number"],
                    "completed_at": now,
                    "updated_at": now,
                    "claim_token": None,
                    "claim_expires_at": None,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return updated or record
    # No committed turn: the worker stopped before commit. Make the record
    # retryable (uncertain → storage failure; expired claim → interrupted).
    error_kind = ERROR_STORAGE if record.get("status") == STATUS_UNCERTAIN else ERROR_INTERRUPTED
    updated = await db[ACTION_REQUESTS_COLLECTION].find_one_and_update(
        {
            "_id": record["_id"],
            "$or": [
                {"status": STATUS_UNCERTAIN},
                {"status": STATUS_IN_PROGRESS, "claim_expires_at": {"$lte": now}},
            ],
        },
        {
            "$set": {
                "status": STATUS_FAILED,
                "error_kind": error_kind,
                "updated_at": now,
                "claim_token": None,
                "claim_expires_at": None,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    return updated or record


def _as_aware(value):
    if getattr(value, "tzinfo", None) is None:
        from datetime import timezone

        return value.replace(tzinfo=timezone.utc)
    return value


async def claim(
    db,
    *,
    session_id: str,
    device_id: str,
    request_id: str,
    request_fingerprint: str,
    debug_mode: bool = False,
) -> ClaimResult:
    """Claim the request for this worker, or report its existing outcome.

    Raises ActionRequestMismatch when the id exists with different contents.
    """
    coll = db[ACTION_REQUESTS_COLLECTION]
    key = request_key(session_id, request_id)
    now = utc_now()
    token = str(uuid.uuid4())
    ttl = timedelta(seconds=claim_ttl_seconds())
    doc = {
        "_id": key,
        "session_id": session_id,
        "device_id": device_id,
        "request_id": request_id,
        "fingerprint": request_fingerprint,
        "debug_mode": bool(debug_mode),
        "status": STATUS_IN_PROGRESS,
        "claim_token": token,
        "claim_expires_at": now + ttl,
        "attempts": 1,
        "created_at": now,
        "updated_at": now,
        "expires_at": now + timedelta(days=RECORD_RETENTION_DAYS),
    }
    try:
        await coll.insert_one(doc)
        return ClaimResult("new", doc, token)
    except DuplicateKeyError:
        pass

    for _ in range(2):
        existing = await coll.find_one({"_id": key})
        if existing is None:
            # Raced with a deletion (session delete); try to insert again.
            try:
                await coll.insert_one(doc)
                return ClaimResult("new", doc, token)
            except DuplicateKeyError:
                continue
        if not _owner_matches(existing, device_id):
            raise ActionRequestMismatch("request belongs to another owner")
        if existing.get("fingerprint") != request_fingerprint:
            raise ActionRequestMismatch("request contents differ")
        existing = await resolve_record(db, existing)
        status = existing.get("status")
        if status == STATUS_COMPLETED:
            return ClaimResult("completed", existing)
        if status == STATUS_IN_PROGRESS:
            expires = existing.get("claim_expires_at")
            if expires is not None and _as_aware(expires) > utc_now():
                return ClaimResult("in_progress", existing)
        # failed, or in_progress with an expired claim: take it over.
        reclaimed = await coll.find_one_and_update(
            {
                "_id": key,
                "fingerprint": request_fingerprint,
                "$or": [
                    {"status": STATUS_FAILED},
                    {"status": STATUS_UNCERTAIN},
                    {"status": STATUS_IN_PROGRESS, "claim_expires_at": {"$lte": utc_now()}},
                ],
            },
            {
                "$set": {
                    "status": STATUS_IN_PROGRESS,
                    "claim_token": token,
                    "claim_expires_at": utc_now() + ttl,
                    "updated_at": utc_now(),
                    "error_kind": None,
                },
                "$inc": {"attempts": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if reclaimed:
            return ClaimResult("reclaimed", reclaimed, token)
        # Someone else re-claimed between our read and update; loop once more.
    final = await coll.find_one({"_id": key})
    if final and final.get("status") == STATUS_COMPLETED:
        return ClaimResult("completed", final)
    return ClaimResult("in_progress", final or doc)


async def mark_failed(db, key: str, claim_token: Optional[str], error_kind: str) -> None:
    """Record a retryable failure. Only the claim owner may change the record."""
    if not claim_token:
        return
    try:
        await db[ACTION_REQUESTS_COLLECTION].update_one(
            {"_id": key, "claim_token": claim_token, "status": STATUS_IN_PROGRESS},
            {
                "$set": {
                    "status": STATUS_FAILED,
                    "error_kind": error_kind,
                    "claim_token": None,
                    "claim_expires_at": None,
                    "updated_at": utc_now(),
                }
            },
        )
    except Exception:
        logger.exception("action request mark_failed failed for %s", key)


async def mark_uncertain(db, key: str, claim_token: Optional[str]) -> None:
    """Record that the commit outcome could not be determined by this worker."""
    if not claim_token:
        return
    try:
        await db[ACTION_REQUESTS_COLLECTION].update_one(
            {"_id": key, "claim_token": claim_token, "status": STATUS_IN_PROGRESS},
            {
                "$set": {
                    "status": STATUS_UNCERTAIN,
                    "claim_token": None,
                    "claim_expires_at": None,
                    "updated_at": utc_now(),
                }
            },
        )
    except Exception:
        logger.exception("action request mark_uncertain failed for %s", key)


async def read_status(db, *, session_id: str, device_id: str, request_id: str) -> Dict[str, Any]:
    """Player-safe status projection for one request id (owner-verified)."""
    record = await db[ACTION_REQUESTS_COLLECTION].find_one(
        {"_id": request_key(session_id, request_id)}
    )
    if not record or not _owner_matches(record, device_id):
        return {"status": "unknown"}
    record = await resolve_record(db, record)
    status = record.get("status")
    if status == STATUS_COMPLETED:
        return {
            "status": STATUS_COMPLETED,
            "turn_id": record.get("turn_id"),
            "turn_number": record.get("turn_number"),
            "debug_mode": bool(record.get("debug_mode")),
        }
    if status == STATUS_IN_PROGRESS:
        return {"status": STATUS_IN_PROGRESS}
    if status == STATUS_FAILED:
        return {"status": STATUS_FAILED, "error_kind": record.get("error_kind") or ERROR_STORAGE}
    # uncertain with no turn found and no repair possible — treat as retryable.
    return {"status": STATUS_FAILED, "error_kind": ERROR_STORAGE}


def error_kind_for_status(status_code: int) -> str:
    if status_code == 409:
        return ERROR_CONFLICT
    if status_code == 429:
        return ERROR_RATE_LIMITED
    if status_code in (400, 404, 422):
        return ERROR_VALIDATION
    if status_code == 503:
        return ERROR_STORAGE
    return ERROR_PROVIDER
