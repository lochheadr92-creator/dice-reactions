"""
Private notebook: pinned passages and the player's own theories, per save.

Contract:
  * The notebook belongs to the player, not to any character. It lives in its own collection
    (``notebook_items``) and is never part of a session or turn document, so it cannot reach the
    default export, a branch copy, a debug payload or the narrator's request. Nothing in
    ``server._build_messages`` reads it; tests inspect the real request to prove that.
  * A pin is validated against the text the player was actually shown: the scrubbed
    ``player_api.build_player_paragraphs`` output of a stored turn. Hidden engine text
    (rolling state, debug, raw model output, the unscrubbed narrative) is never a pin source.
  * A pin keeps a durable reference (turn number, turn id, paragraph index, character offsets)
    and the exact quoted text, so it opens at the right passage however old the turn is.
  * Reads and writes require the owning device. Writing the notebook takes no turn, spends no
    credit and changes no world state: no lease, no revision bump, no narrator call.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument

from player_api import build_player_paragraphs

COLLECTION = "notebook_items"

MAX_PIN_TEXT = 600
MAX_NOTE = 400
MAX_THEORY_TITLE = 120
MAX_THEORY_BODY = 4000
MAX_PINS_PER_SAVE = 200
MAX_THEORIES_PER_SAVE = 100
MAX_PINS_PER_THEORY = 20


class NotebookError(Exception):
    """A request the notebook refuses. ``status`` maps to the HTTP answer."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _now() -> datetime:
    return datetime.now(timezone.utc)


def published_paragraphs(turn: Optional[Dict[str, Any]]) -> List[str]:
    """The paragraphs the player was shown for this turn, exactly as the play screen gets them."""
    if not turn:
        return []
    return build_player_paragraphs(turn.get("paragraphs"))


def resolve_quote(paragraphs: List[str], paragraph_index: int, quote: Optional[str], occurrence: int = 0) -> Dict[str, Any]:
    """Locate a pin inside published text. No quote means the whole paragraph."""
    if not isinstance(paragraph_index, int) or paragraph_index < 0 or paragraph_index >= len(paragraphs):
        raise NotebookError(422, "That passage is not in this turn")
    paragraph = paragraphs[paragraph_index]
    if quote is None or quote == "":
        start, end = 0, len(paragraph)
    else:
        start = -1
        cursor = 0
        for _ in range(max(0, int(occurrence)) + 1):
            start = paragraph.find(quote, cursor)
            if start < 0:
                break
            cursor = start + 1
        if start < 0:
            raise NotebookError(422, "That text is not in the passage you were shown")
        end = start + len(quote)
    text = paragraph[start:end]
    if not text.strip():
        raise NotebookError(422, "Pick some text to pin")
    if len(text) > MAX_PIN_TEXT:
        raise NotebookError(422, "That passage is too long to pin")
    return {"paragraph_index": paragraph_index, "start": start, "end": end, "text": text}


def serialize(item: Dict[str, Any]) -> Dict[str, Any]:
    """Player-facing shape: no device id, no storage id."""
    out = {k: v for k, v in item.items() if k not in ("_id", "device_id", "session_id")}
    for key in ("created_at", "updated_at"):
        if isinstance(out.get(key), datetime):
            out[key] = out[key].isoformat()
    return out


async def list_notebook(db, session_id: str, device_id: str) -> Dict[str, Any]:
    rows = await db[COLLECTION].find(
        {"session_id": session_id, "device_id": device_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(length=MAX_PINS_PER_SAVE + MAX_THEORIES_PER_SAVE)
    return {
        "pins": [serialize(r) for r in rows if r.get("kind") == "pin"],
        "theories": [serialize(r) for r in rows if r.get("kind") == "theory"],
    }


def _clean(text: Any, limit: int, field: str, *, required: bool = False) -> str:
    value = str(text or "").strip()
    if required and not value:
        raise NotebookError(422, f"{field} is required")
    if len(value) > limit:
        raise NotebookError(422, f"{field} is too long")
    return value


async def create_pin(
    db,
    session: Dict[str, Any],
    device_id: str,
    *,
    turn_number: int,
    paragraph_index: int,
    quote: Optional[str] = None,
    occurrence: int = 0,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Pin a passage of a turn the player has read. Returns ``{"pin": ..., "created": bool}``."""
    session_id = session["id"]
    if not isinstance(turn_number, int) or turn_number < 1 or turn_number > int(session.get("turn_count") or 0):
        raise NotebookError(404, "That turn is not in this chronicle")
    turn = await db.turns.find_one(
        {"session_id": session_id, "turn_number": turn_number},
        {"_id": 0, "id": 1, "turn_number": 1, "paragraphs": 1},
    )
    if not turn:
        raise NotebookError(404, "That turn is not in this chronicle")
    located = resolve_quote(published_paragraphs(turn), paragraph_index, quote, occurrence)
    note_text = _clean(note, MAX_NOTE, "note")
    key = {
        "session_id": session_id,
        "device_id": device_id,
        "kind": "pin",
        "turn_number": turn_number,
        "paragraph_index": located["paragraph_index"],
        "start": located["start"],
        "end": located["end"],
    }
    existing = await db[COLLECTION].find_one(key, {"_id": 0})
    if existing:
        return {"pin": serialize(existing), "created": False}
    if await db[COLLECTION].count_documents(
        {"session_id": session_id, "device_id": device_id, "kind": "pin"}
    ) >= MAX_PINS_PER_SAVE:
        raise NotebookError(409, "The notebook is full of pins")
    doc = {
        **key,
        "id": str(uuid.uuid4()),
        "turn_id": turn.get("id"),
        "text": located["text"],
        "note": note_text,
        "created_at": _now(),
    }
    await db[COLLECTION].insert_one(dict(doc))
    return {"pin": serialize(doc), "created": True}


async def _validated_pin_ids(db, session_id: str, device_id: str, pin_ids: Any) -> List[str]:
    if pin_ids is None:
        return []
    if not isinstance(pin_ids, list):
        raise NotebookError(422, "pin_ids must be a list")
    ordered: List[str] = []
    for pid in pin_ids:
        pid = str(pid)
        if pid not in ordered:
            ordered.append(pid)
    if len(ordered) > MAX_PINS_PER_THEORY:
        raise NotebookError(422, "Too many pins on one theory")
    if ordered:
        found = await db[COLLECTION].count_documents(
            {"session_id": session_id, "device_id": device_id, "kind": "pin", "id": {"$in": ordered}}
        )
        if found != len(ordered):
            raise NotebookError(422, "One of those pins is not in this notebook")
    return ordered


async def create_theory(
    db,
    session_id: str,
    device_id: str,
    *,
    title: str,
    body: str = "",
    pin_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    title_text = _clean(title, MAX_THEORY_TITLE, "title", required=True)
    body_text = _clean(body, MAX_THEORY_BODY, "body")
    if await db[COLLECTION].count_documents(
        {"session_id": session_id, "device_id": device_id, "kind": "theory"}
    ) >= MAX_THEORIES_PER_SAVE:
        raise NotebookError(409, "The notebook is full of theories")
    now = _now()
    doc = {
        "id": str(uuid.uuid4()),
        "kind": "theory",
        "session_id": session_id,
        "device_id": device_id,
        "title": title_text,
        "body": body_text,
        "pin_ids": await _validated_pin_ids(db, session_id, device_id, pin_ids),
        "created_at": now,
        "updated_at": now,
    }
    await db[COLLECTION].insert_one(dict(doc))
    return serialize(doc)


async def update_theory(
    db,
    session_id: str,
    device_id: str,
    theory_id: str,
    *,
    title: Optional[str] = None,
    body: Optional[str] = None,
    pin_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    scope = {"session_id": session_id, "device_id": device_id, "kind": "theory", "id": theory_id}
    patch: Dict[str, Any] = {}
    if title is not None:
        patch["title"] = _clean(title, MAX_THEORY_TITLE, "title", required=True)
    if body is not None:
        patch["body"] = _clean(body, MAX_THEORY_BODY, "body")
    if pin_ids is not None:
        patch["pin_ids"] = await _validated_pin_ids(db, session_id, device_id, pin_ids)
    patch["updated_at"] = _now()
    updated = await db[COLLECTION].find_one_and_update(
        scope, {"$set": patch}, projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    if not updated:
        raise NotebookError(404, "Theory not found")
    return serialize(updated)


async def delete_theory(db, session_id: str, device_id: str, theory_id: str) -> None:
    result = await db[COLLECTION].delete_one(
        {"session_id": session_id, "device_id": device_id, "kind": "theory", "id": theory_id}
    )
    if result.deleted_count == 0:
        raise NotebookError(404, "Theory not found")


async def delete_pin(db, session_id: str, device_id: str, pin_id: str) -> None:
    """Remove a pin and detach it from any theory; the theories keep their other pins and text."""
    result = await db[COLLECTION].delete_one(
        {"session_id": session_id, "device_id": device_id, "kind": "pin", "id": pin_id}
    )
    if result.deleted_count == 0:
        raise NotebookError(404, "Pin not found")
    await db[COLLECTION].update_many(
        {"session_id": session_id, "device_id": device_id, "kind": "theory", "pin_ids": pin_id},
        {"$pull": {"pin_ids": pin_id}},
    )


async def delete_for_session(db, session_id: str, *, mongo_session=None) -> None:
    """Remove a save's whole notebook. Called by session delete and reset, in their transaction."""
    await db[COLLECTION].delete_many({"session_id": session_id}, session=mongo_session)
