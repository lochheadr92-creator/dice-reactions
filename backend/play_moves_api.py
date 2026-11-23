"""Reads for player moves: build the scene a move is checked against, list what is possible, preview.

The turn handler uses ``build_context`` too, so a preview and the real move see the same facts.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

import play_moves
from play_facts import Context, MoveError

RECENT_TURNS = 12


async def build_context(
    db, session: Dict[str, Any], device_id: str, move: Optional[play_moves.MoveRequest] = None, *, turn: Optional[int] = None
) -> Context:
    sid = session["id"]
    wanted = play_moves.referenced_turns(move)
    projection = {"_id": 0, "turn_number": 1, "paragraphs": 1, "ledger": 1}
    rows = await db.turns.find({"session_id": sid}, projection).sort("turn_number", -1).to_list(length=RECENT_TURNS)
    have = {int(r.get("turn_number") or 0) for r in rows}
    for number in wanted:
        if number not in have:
            row = await db.turns.find_one({"session_id": sid, "turn_number": number}, projection)
            if row:
                rows.append(row)
    newest = max(rows, key=lambda r: int(r.get("turn_number") or 0), default=None)
    ledger = (newest or {}).get("ledger") or {}
    pins: Dict[str, Dict[str, Any]] = {}
    ids = play_moves.pin_ids(move)
    if ids:
        found = await db["notebook_items"].find(
            {"session_id": sid, "device_id": device_id, "kind": "pin", "id": {"$in": ids}}, {"_id": 0}
        ).to_list(length=len(ids))
        pins = {str(p["id"]): p for p in found}
    return Context(
        session=session,
        rolling=session.get("rolling_state") or {},
        rows=rows,
        ledger=ledger if isinstance(ledger, dict) else {},
        pins=pins,
        turn=turn if turn is not None else int(session.get("turn_count") or 0) + 1,
        npc_ledger=session.get("npc_ledger") or {},
        play=session.get("play_state") or {},
    )


def register(router: APIRouter, *, get_db: Callable[[], Any], fetch_owned_session, require_device_id) -> None:
    @router.get("/story/session/{session_id}/moves")
    async def moves_available(session_id: str, device_id: str = Depends(require_device_id)):
        """What the scene allows right now, or why not. Reads only."""
        db = get_db()
        session = await fetch_owned_session(db, session_id, device_id)
        ctx = await build_context(db, session, device_id)
        opts = play_moves.all_options(ctx)
        return {"turn_count": int(session.get("turn_count") or 0), "moves": opts, "offers": play_moves.offers(opts)}

    @router.post("/story/session/{session_id}/moves/preview")
    async def moves_preview(session_id: str, move: play_moves.MoveRequest, device_id: str = Depends(require_device_id)):
        """What this move would do, as far as the player may know. No turn, no cost, nothing kept."""
        db = get_db()
        session = await fetch_owned_session(db, session_id, device_id)
        ctx = await build_context(db, session, device_id, move)
        try:
            return play_moves.preview(session.get("play_state"), ctx, move)
        except MoveError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail)
