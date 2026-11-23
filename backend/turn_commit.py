"""
Transactional commit of gameplay mutations (turn + session + request record).

Contract (reliability release):
  * Provider generation always happens OUTSIDE the transaction. The callbacks
    below are database-only and idempotent, so the driver may re-run them on a
    transient transaction error without repeating paid work.
  * One multi-document transaction makes the turn row, the session state, the
    lease release, and the action-request record visible together, or not at
    all. There is no split-write fallback.
  * Every commit re-verifies the session precondition (lease ownership,
    expected turn_count, expected session_revision) inside the transaction.
  * Ambiguous commit acknowledgements are resolved by looking for the committed
    turn id — never by re-running the mutation.
  * Transaction support is required (replica set or mongos). When it is
    missing the write paths fail closed with a clear error.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError

from action_concurrency import (
    ACTION_LOCK_TOKEN_FIELD,
    SESSION_REVISION_FIELD,
    build_model_lock_patch,
    build_persist_cas_filter,
    lease_release_unset,
    utc_now,
)

logger = logging.getLogger(__name__)

ACTION_REQUESTS_COLLECTION = "action_requests"
NOTEBOOK_COLLECTION = "notebook_items"  # see notebook.py; cleared with its save
TURN_REQUEST_KEY_FIELD = "action_request_key"

# MongoDB error codes that mean "transactions are not available on this topology".
_NO_TRANSACTION_CODES = {20, 263}  # IllegalOperation, OperationNotSupportedInTransaction


class CommitPreconditionFailed(Exception):
    """The session lease, turn_count, or revision no longer match; nothing was written."""


class TransactionSupportUnavailable(Exception):
    """The connected MongoDB deployment cannot run multi-document transactions."""


class CommitOutcomeUnknown(Exception):
    """Commit acknowledgement was lost and the outcome could not be verified."""


@dataclass
class CommitResult:
    committed: bool
    turn_id: str
    turn_number: int
    verified_after_ambiguity: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Topology / support checks
# ---------------------------------------------------------------------------
async def check_transaction_support(db) -> Dict[str, Any]:
    """Return topology facts or raise TransactionSupportUnavailable."""
    try:
        hello = await db.command("hello")
    except OperationFailure as exc:
        # MongoDB < 4.4.2 has no `hello`; fall back to the legacy command.
        if "no such command" not in str(exc).lower() and getattr(exc, "code", None) != 59:
            raise TransactionSupportUnavailable(f"hello failed: {type(exc).__name__}") from exc
        try:
            hello = await db.command("isMaster")
        except PyMongoError as legacy_exc:
            raise TransactionSupportUnavailable(
                f"isMaster failed: {type(legacy_exc).__name__}"
            ) from legacy_exc
    except PyMongoError as exc:
        raise TransactionSupportUnavailable(f"hello failed: {type(exc).__name__}") from exc
    set_name = hello.get("setName")
    is_mongos = hello.get("msg") == "isdbgrid"
    if not set_name and not is_mongos:
        raise TransactionSupportUnavailable(
            "MongoDB must run as a replica set or sharded cluster; a standalone server "
            "cannot provide the transactional turn commit this release requires"
        )
    return {
        "topology": "mongos" if is_mongos else "replica_set",
        "set_name": set_name,
        "writable_primary": bool(hello.get("isWritablePrimary") or hello.get("ismaster")),
    }


def _is_no_transaction_error(exc: BaseException) -> bool:
    if isinstance(exc, OperationFailure):
        code = getattr(exc, "code", None)
        if code in _NO_TRANSACTION_CODES:
            return True
        message = str(exc).lower()
        return (
            "transaction numbers are only allowed" in message
            or "replica set member or mongos" in message
        )
    return False


# ---------------------------------------------------------------------------
# Interruption checkpoints (test seam only — no-op in production)
# ---------------------------------------------------------------------------
_checkpoint_hook: Optional[Callable[[str], Any]] = None

CHECKPOINTS = (
    "before_session_update",
    "after_session_update",
    "after_turn_insert",
    "after_request_update",
    "before_commit",
    "after_commit",
)


def set_checkpoint_hook_for_tests(hook: Optional[Callable[[str], Any]]) -> None:
    """Install a hook invoked at each persistence boundary (tests simulate interruption)."""
    global _checkpoint_hook
    _checkpoint_hook = hook


async def _checkpoint(name: str) -> None:
    if _checkpoint_hook is None:
        return
    result = _checkpoint_hook(name)
    if hasattr(result, "__await__"):
        await result


# ---------------------------------------------------------------------------
# Transaction runner (patchable seam for tests)
# ---------------------------------------------------------------------------
async def _run_transaction(db, callback: Callable[[Any], Awaitable[Any]]) -> Any:
    """Run ``callback(session)`` inside a driver-managed transaction.

    Motor's ``with_transaction`` retries the callback on TransientTransactionError
    and retries the commit on UnknownTransactionCommitResult. Because callbacks
    are database-only, re-running them never repeats provider work.
    """
    client = db.client
    try:
        async with await client.start_session() as mongo_session:
            return await mongo_session.with_transaction(callback)
    except PyMongoError as exc:
        if _is_no_transaction_error(exc):
            raise TransactionSupportUnavailable(str(exc)) from exc
        raise


# ---------------------------------------------------------------------------
# Action turn commit
# ---------------------------------------------------------------------------
def _session_commit_ops(
    update_set: Dict[str, Any], meta: Dict[str, Any], turn_number: int
) -> Dict[str, Any]:
    model_set, model_push = build_model_lock_patch(meta or {}, turn_number)
    ops: Dict[str, Any] = {
        "$set": {**update_set, **model_set},
        "$inc": {SESSION_REVISION_FIELD: 1},
        "$unset": lease_release_unset(),
    }
    if model_push:
        ops["$push"] = model_push
    return ops


async def _verify_turn_committed(db, turn_doc: Dict[str, Any]) -> bool:
    found = await db.turns.find_one(
        {"id": turn_doc["id"], "session_id": turn_doc["session_id"]}, {"_id": 1}
    )
    return found is not None


async def commit_action_turn(
    db,
    *,
    session_id: str,
    lease_token: str,
    expected_turn_count: int,
    expected_revision: Optional[int],
    turn_doc: Dict[str, Any],
    update_set: Dict[str, Any],
    meta: Dict[str, Any],
    request_key: Optional[str] = None,
) -> CommitResult:
    """Atomically commit one player action.

    Raises CommitPreconditionFailed when the lease/turn_count/revision check
    fails (nothing is written), TransactionSupportUnavailable when the
    deployment cannot run transactions, and CommitOutcomeUnknown when the
    acknowledgement was lost and verification itself failed.
    """
    turn_number = int(turn_doc["turn_number"])
    if request_key:
        turn_doc = {**turn_doc, TURN_REQUEST_KEY_FIELD: request_key}
    cas_filter = build_persist_cas_filter(
        session_id, lease_token, expected_turn_count, expected_revision
    )
    ops = _session_commit_ops(update_set, meta, turn_number)

    async def callback(mongo_session):
        await _checkpoint("before_session_update")
        result = await db.sessions.update_one(cas_filter, ops, session=mongo_session)
        if result.matched_count == 0:
            raise CommitPreconditionFailed("session lease, turn_count, or revision changed")
        await _checkpoint("after_session_update")
        try:
            await db.turns.insert_one(turn_doc, session=mongo_session)
        except DuplicateKeyError as exc:
            raise CommitPreconditionFailed("turn number already committed") from exc
        await _checkpoint("after_turn_insert")
        if request_key:
            now = utc_now()
            await db[ACTION_REQUESTS_COLLECTION].update_one(
                {"_id": request_key},
                {
                    "$set": {
                        "status": "completed",
                        "turn_id": turn_doc["id"],
                        "turn_number": turn_number,
                        "completed_at": now,
                        "updated_at": now,
                        "claim_token": None,
                        "claim_expires_at": None,
                    }
                },
                session=mongo_session,
            )
            await _checkpoint("after_request_update")
        await _checkpoint("before_commit")
        return True

    try:
        await _run_transaction(db, callback)
        await _checkpoint("after_commit")
    except (CommitPreconditionFailed, TransactionSupportUnavailable):
        raise
    except PyMongoError as exc:
        # Acknowledgement lost (or the driver gave up retrying). Verify by turn
        # id — never by replaying the mutation.
        logger.warning(
            "action commit acknowledgement uncertain for session %s turn %s: %s",
            session_id,
            turn_number,
            type(exc).__name__,
        )
        try:
            if await _verify_turn_committed(db, turn_doc):
                return CommitResult(
                    True, turn_doc["id"], turn_number, verified_after_ambiguity=True
                )
        except PyMongoError as verify_exc:
            raise CommitOutcomeUnknown(
                f"commit verification failed: {type(verify_exc).__name__}"
            ) from verify_exc
        raise CommitOutcomeUnknown(f"commit failed: {type(exc).__name__}") from exc
    return CommitResult(True, turn_doc["id"], turn_number)


# ---------------------------------------------------------------------------
# Opening turn commit (story creation)
# ---------------------------------------------------------------------------
async def commit_opening_turn(
    db,
    *,
    session_id: str,
    turn_doc: Dict[str, Any],
    update_set: Dict[str, Any],
    meta: Dict[str, Any],
) -> CommitResult:
    """Atomically commit turn 1 and the provisional session's completion."""
    cas_filter = {"id": session_id, "turn_count": 0}
    ops = _session_commit_ops(update_set, meta, 1)
    ops.pop("$unset", None)

    async def callback(mongo_session):
        result = await db.sessions.update_one(cas_filter, ops, session=mongo_session)
        if result.matched_count == 0:
            raise CommitPreconditionFailed("provisional session missing or already completed")
        try:
            await db.turns.insert_one(turn_doc, session=mongo_session)
        except DuplicateKeyError as exc:
            raise CommitPreconditionFailed("opening turn already committed") from exc
        return True

    try:
        await _run_transaction(db, callback)
    except (CommitPreconditionFailed, TransactionSupportUnavailable):
        raise
    except PyMongoError as exc:
        try:
            if await _verify_turn_committed(db, turn_doc):
                return CommitResult(True, turn_doc["id"], 1, verified_after_ambiguity=True)
        except PyMongoError as verify_exc:
            raise CommitOutcomeUnknown(
                f"opening commit verification failed: {type(verify_exc).__name__}"
            ) from verify_exc
        raise CommitOutcomeUnknown(f"opening commit failed: {type(exc).__name__}") from exc
    return CommitResult(True, turn_doc["id"], 1)


# ---------------------------------------------------------------------------
# Reset / delete (same lease + revision contract)
# ---------------------------------------------------------------------------
def reset_session_fields(now: Optional[datetime] = None) -> Dict[str, Any]:
    moment = now or datetime.now(timezone.utc)
    return {
        "turn_count": 0,
        "last_narrative_snippet": "",
        "last_state": {},
        "rolling_state": None,
        "replayability_state": None,
        "updated_at": moment,
        # Marks a deliberate reset shell, so it is never mistaken for a
        # provisional session left by a dead creation.
        "reset_at": moment,
    }


async def commit_session_reset(db, *, session_id: str, lease_token: str) -> None:
    """Delete turns and clear gameplay state atomically under the caller's lease.

    Request records are deleted with the turns they point to, the same as a
    session delete. A completed record would otherwise point at a deleted turn
    (replay 404 while status said "superseded", and a false
    completed_without_turn anomaly). An old request id sent again after a
    reset is a new request for the reset session.
    """
    ops = {
        "$set": reset_session_fields(),
        "$inc": {SESSION_REVISION_FIELD: 1},
        "$unset": lease_release_unset(),
    }

    async def callback(mongo_session):
        result = await db.sessions.update_one(
            {"id": session_id, ACTION_LOCK_TOKEN_FIELD: lease_token},
            ops,
            session=mongo_session,
        )
        if result.matched_count == 0:
            raise CommitPreconditionFailed("reset lease lost")
        await db.turns.delete_many({"session_id": session_id}, session=mongo_session)
        await db[ACTION_REQUESTS_COLLECTION].delete_many(
            {"session_id": session_id}, session=mongo_session
        )
        # Pins point at turns that no longer exist; the private notebook goes with them.
        await db[NOTEBOOK_COLLECTION].delete_many({"session_id": session_id}, session=mongo_session)
        return True

    await _run_transaction(db, callback)


async def commit_session_delete(db, *, session_id: str, lease_token: str) -> None:
    """Delete session, turns, and request records atomically under the caller's lease."""

    async def callback(mongo_session):
        result = await db.sessions.delete_one(
            {"id": session_id, ACTION_LOCK_TOKEN_FIELD: lease_token}, session=mongo_session
        )
        if result.deleted_count == 0:
            raise CommitPreconditionFailed("delete lease lost")
        await db.turns.delete_many({"session_id": session_id}, session=mongo_session)
        await db[ACTION_REQUESTS_COLLECTION].delete_many(
            {"session_id": session_id}, session=mongo_session
        )
        await db[NOTEBOOK_COLLECTION].delete_many({"session_id": session_id}, session=mongo_session)
        return True

    await _run_transaction(db, callback)


# ---------------------------------------------------------------------------
# Read-only consistency diagnostics for existing data
# ---------------------------------------------------------------------------
async def consistency_report(db, *, sample_limit: int = 20) -> Dict[str, Any]:
    """Describe mismatched turn counts, orphaned turns, and incomplete requests.

    Read-only: never deletes or rewrites ambiguous historical data. Samples
    contain identifiers only (no narrative, state, or device ids).
    """
    sample_limit = max(1, min(int(sample_limit), 200))
    now = utc_now()

    def _facet() -> Dict[str, Any]:
        # Count and sample server-side so large deployments never stream every
        # anomaly row into memory.
        return {"$facet": {"count": [{"$count": "n"}], "sample": [{"$limit": sample_limit}]}}

    async def _counted(collection, pipeline: List[Dict[str, Any]]) -> Dict[str, Any]:
        rows = await collection.aggregate(pipeline + [_facet()]).to_list(length=1)
        facet = rows[0] if rows else {"count": [], "sample": []}
        count = facet["count"][0]["n"] if facet.get("count") else 0
        return {"count": int(count), "sample": facet.get("sample") or []}

    mismatched = await _counted(
        db.sessions,
        [
            {
                # Only the turn numbers are joined, never narrative/raw payloads.
                "$lookup": {
                    "from": "turns",
                    "let": {"sid": "$id"},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$session_id", "$$sid"]}}},
                        {"$project": {"_id": 0, "turn_number": 1}},
                    ],
                    "as": "turn_rows",
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "id": 1,
                    "turn_count": {"$ifNull": ["$turn_count", 0]},
                    "stored_turns": {"$size": "$turn_rows"},
                    "max_turn_number": {"$ifNull": [{"$max": "$turn_rows.turn_number"}, 0]},
                }
            },
            {
                "$match": {
                    "$expr": {
                        "$or": [
                            {"$ne": ["$turn_count", "$stored_turns"]},
                            {"$ne": ["$turn_count", "$max_turn_number"]},
                        ]
                    }
                }
            },
        ],
    )

    orphaned = await _counted(
        db.turns,
        [
            {"$project": {"_id": 0, "id": 1, "session_id": 1, "turn_number": 1}},
            {
                "$lookup": {
                    "from": "sessions",
                    "let": {"sid": "$session_id"},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$id", "$$sid"]}}},
                        {"$project": {"_id": 1}},
                        {"$limit": 1},
                    ],
                    "as": "owner",
                }
            },
            {"$match": {"owner": {"$size": 0}}},
            {"$project": {"owner": 0}},
        ],
    )

    duplicate_turn_numbers = await _counted(
        db.turns,
        [
            {
                "$group": {
                    "_id": {"session_id": "$session_id", "turn_number": "$turn_number"},
                    "count": {"$sum": 1},
                }
            },
            {"$match": {"count": {"$gt": 1}}},
            {
                "$project": {
                    "_id": 0,
                    "session_id": "$_id.session_id",
                    "turn_number": "$_id.turn_number",
                    "count": 1,
                }
            },
        ],
    )

    requests = db[ACTION_REQUESTS_COLLECTION]
    stale_in_progress = await requests.count_documents(
        {"status": "in_progress", "claim_expires_at": {"$lte": now}}
    )
    active_in_progress = await requests.count_documents(
        {"status": "in_progress", "claim_expires_at": {"$gt": now}}
    )
    uncertain = await requests.count_documents({"status": "uncertain"})
    failed = await requests.count_documents({"status": "failed"})
    completed_without_turn: List[Dict[str, Any]] = []
    async for row in requests.aggregate(
        [
            {"$match": {"status": "completed"}},
            {
                "$lookup": {
                    "from": "turns",
                    "localField": "turn_id",
                    "foreignField": "id",
                    "as": "turn_rows",
                }
            },
            {"$match": {"turn_rows": {"$size": 0}}},
            {"$project": {"_id": 0, "session_id": 1, "request_id": 1, "turn_number": 1}},
            {"$limit": sample_limit},
        ]
    ):
        completed_without_turn.append(row)

    provisional_sessions = await db.sessions.count_documents(
        {"turn_count": {"$in": [0, None]}, "reset_at": {"$exists": False}}
    )
    reset_sessions = await db.sessions.count_documents(
        {"turn_count": {"$in": [0, None]}, "reset_at": {"$exists": True}}
    )

    return {
        "generated_at": now.isoformat(),
        "read_only": True,
        "sessions_with_turn_count_mismatch": mismatched,
        "orphaned_turns": orphaned,
        "duplicate_turn_numbers": duplicate_turn_numbers,
        "provisional_sessions_without_opening_turn": provisional_sessions,
        "reset_sessions_without_turns": reset_sessions,
        "action_requests": {
            "in_progress_active": active_in_progress,
            "in_progress_stale_claim": stale_in_progress,
            "uncertain": uncertain,
            "failed": failed,
            "completed_without_turn": {
                "count": len(completed_without_turn),
                "sample": completed_without_turn,
            },
        },
    }
