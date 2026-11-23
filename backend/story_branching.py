"""
Branching: copy one committed state of a save into a new, independent save.

Contract:
  * A branch is made from the latest committed turn only (historical rewind is out of scope).
  * The source save's action lease is held for the whole copy, so no turn can commit
    while the copy is read, and an action in flight makes the branch fail with a conflict
    instead of mixing two turns.
  * The session row and every turn row are read and written inside ONE transaction, after
    re-checking the lease, turn_count and revision. Either the whole branch exists or none of it.
  * The branch id is derived from (source, device, request id). The same request id sent twice
    (double tap, retry after a lost response) returns the same branch and creates nothing new.
  * A branch makes no narrator call, spends no rate-limit or provider budget, and does not
    advance the simulation clock. Nothing in this module reads or writes those records.
  * Not copied: lease fields, session revision, idempotency/request records, rate-limit and
    provider-usage records, and the private notebook (a branch starts with an empty notebook).
"""

from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo.errors import DuplicateKeyError

import turn_commit
from action_concurrency import (
    ACTION_LOCK_FIELDS,
    ACTION_LOCK_TOKEN_FIELD,
    SESSION_REVISION_FIELD,
    ActionLeaseConflict,
    acquire_action_lease,
    release_action_lease_quietly,
)

logger = logging.getLogger(__name__)

BRANCH_ID_NAMESPACE = uuid.UUID("5b0f2a52-7d0e-4c1e-9a4f-d1ce0b2a7e11")
TURN_INSERT_BATCH = 100

# Session fields that belong to the source save's runtime and must not be copied.
NOT_COPIED_SESSION_FIELDS = frozenset(
    {"_id", "id", SESSION_REVISION_FIELD, "reset_at", "created_at", "updated_at"}
    | set(ACTION_LOCK_FIELDS)
)


class BranchStale(Exception):
    """The caller's view of the save is older than its latest committed turn."""


class BranchNotAllowed(Exception):
    """The save has no committed turn to branch from."""


class BranchInconsistent(Exception):
    """The stored turns do not match the session's turn count; nothing was copied."""


@dataclass
class BranchResult:
    session: Dict[str, Any]
    replayed: bool
    source_turn_count: int


def branch_session_id(source_session_id: str, device_id: str, request_id: str) -> str:
    """Deterministic id: one request id means at most one branch."""
    return str(uuid.uuid5(BRANCH_ID_NAMESPACE, f"{source_session_id}|{device_id}|{request_id}"))


async def _next_branch_path(db, source: Dict[str, Any]) -> List[int]:
    """Branch numbering: children of one save are numbered 1, 2, 3; a child of a branch extends the path."""
    taken = await db.sessions.count_documents(
        {
            "device_id": source.get("device_id"),
            "branched_from.session_id": source["id"],
        }
    )
    return list(source.get("branch_path") or []) + [taken + 1]


def _branch_label(path: List[int]) -> str:
    return "Branch " + ".".join(str(n) for n in path)


def _build_branch_session(
    source: Dict[str, Any],
    branch_id: str,
    path: List[int],
    now: datetime,
) -> Dict[str, Any]:
    doc = {k: copy.deepcopy(v) for k, v in source.items() if k not in NOT_COPIED_SESSION_FIELDS}
    root_title = source.get("branch_root_title") or source.get("title") or "Chronicle"
    doc.update(
        {
            "id": branch_id,
            "title": f"{root_title} · {_branch_label(path)}",
            "branch_root_title": root_title,
            "branch_path": path,
            "branch_label": _branch_label(path),
            "branched_from": {
                "session_id": source["id"],
                "title": source.get("title"),
                "turn_number": int(source.get("turn_count") or 0),
            },
            SESSION_REVISION_FIELD: 0,
            "created_at": now,
            "updated_at": now,
        }
    )
    return doc


async def _find_replay(db, branch_id: str, device_id: str, source_id: str) -> Optional[Dict[str, Any]]:
    existing = await db.sessions.find_one(
        {"id": branch_id, "device_id": device_id, "branched_from.session_id": source_id},
        {"_id": 0},
    )
    return existing


async def create_branch(
    db,
    *,
    source_session_id: str,
    device_id: str,
    request_id: str,
    expected_turn_count: Optional[int] = None,
    now: Optional[datetime] = None,
) -> BranchResult:
    """Create (or replay) a branch of ``source_session_id`` at its latest committed turn.

    Raises ActionLeaseConflict (an action or another maintenance call holds the save),
    BranchStale, BranchNotAllowed, BranchInconsistent, turn_commit.TransactionSupportUnavailable
    and HTTPException 404 for an unknown or foreign save. Nothing is written on any of them.
    """
    branch_id = branch_session_id(source_session_id, device_id, request_id)

    # A repeated request id returns the branch it already made, even if the source
    # has moved on or been deleted since.
    replay = await _find_replay(db, branch_id, device_id, source_session_id)
    if replay:
        return BranchResult(replay, True, int((replay.get("branched_from") or {}).get("turn_number") or 0))

    lease_token: Optional[str] = None
    try:
        source, lease_token = await acquire_action_lease(
            db, source_session_id, device_id, purpose="branch"
        )
        turn_count = int(source.get("turn_count") or 0)
        revision = int(source.get(SESSION_REVISION_FIELD) or 0)
        if turn_count < 1:
            raise BranchNotAllowed("the save has no committed turn")
        if expected_turn_count is not None and int(expected_turn_count) != turn_count:
            raise BranchStale("the save has moved past the turn the caller was looking at")

        moment = now or datetime.now(timezone.utc)
        path = await _next_branch_path(db, source)
        branch_doc: Dict[str, Any] = {}

        async def callback(mongo_session):
            locked = await db.sessions.find_one(
                {
                    "id": source_session_id,
                    "device_id": device_id,
                    ACTION_LOCK_TOKEN_FIELD: lease_token,
                    "turn_count": turn_count,
                    SESSION_REVISION_FIELD: revision,
                },
                {"_id": 0},
                session=mongo_session,
            )
            if not locked:
                raise turn_commit.CommitPreconditionFailed("source changed during branch")
            rows = await db.turns.find(
                {"session_id": source_session_id}, session=mongo_session
            ).sort("turn_number", 1).to_list(length=None)
            numbers = [int(r.get("turn_number") or 0) for r in rows]
            if numbers != list(range(1, turn_count + 1)):
                raise BranchInconsistent("stored turns do not match the turn count")
            branch_doc.clear()
            branch_doc.update(_build_branch_session(locked, branch_id, path, moment))
            try:
                await db.sessions.insert_one(copy.deepcopy(branch_doc), session=mongo_session)
            except DuplicateKeyError as exc:
                raise turn_commit.CommitPreconditionFailed("branch already exists") from exc
            copies: List[Dict[str, Any]] = []
            for row in rows:
                turn = {k: copy.deepcopy(v) for k, v in row.items() if k not in ("_id", "action_request_key")}
                turn["id"] = str(uuid.uuid4())
                turn["session_id"] = branch_id
                copies.append(turn)
            for start in range(0, len(copies), TURN_INSERT_BATCH):
                await db.turns.insert_many(copies[start:start + TURN_INSERT_BATCH], session=mongo_session)
            return True

        try:
            await turn_commit._run_transaction(db, callback)
        except turn_commit.CommitPreconditionFailed:
            # Lost a race with the same request id (it won) or the source changed.
            replay = await _find_replay(db, branch_id, device_id, source_session_id)
            if replay:
                return BranchResult(replay, True, turn_count)
            raise
        logger.info("branch %s created from %s at turn %s", branch_id, source_session_id, turn_count)
        return BranchResult(branch_doc, False, turn_count)
    finally:
        if lease_token:
            await release_action_lease_quietly(db, source_session_id, lease_token)
