"""
Access-control primitives for Dice Reaction (device-scoped ownership + admin API key).

Admin authentication uses ADMIN_API_KEY from the environment and the
X-Admin-Api-Key request header. Fails closed when the variable is unset.

Session ownership compares the caller-supplied device_id (X-Device-Id header)
against the persisted session record — never trusts client state without a
database lookup. Wrong-owner and missing-session failures are indistinguishable.
"""

from __future__ import annotations

import hmac
import os
from typing import Any, Dict, Optional

from fastapi import Header, HTTPException

ADMIN_API_KEY_ENV = "ADMIN_API_KEY"
ADMIN_API_KEY_HEADER = "X-Admin-Api-Key"
DEVICE_ID_HEADER = "X-Device-Id"

_SESSION_NOT_FOUND_DETAIL = "Session not found"
_DEVICE_ID_REQUIRED_DETAIL = "device_id is required"


def configured_admin_api_key() -> Optional[str]:
    value = os.environ.get(ADMIN_API_KEY_ENV, "")
    return value if value else None


async def require_admin(
    x_admin_api_key: Optional[str] = Header(None, alias=ADMIN_API_KEY_HEADER),
) -> None:
    """FastAPI dependency — reject unless a valid admin API key is supplied."""
    expected = configured_admin_api_key()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API not configured")
    provided = x_admin_api_key or ""
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def require_device_id(
    x_device_id: Optional[str] = Header(None, alias=DEVICE_ID_HEADER),
) -> str:
    """FastAPI dependency — require the device possession credential header."""
    if not x_device_id or not str(x_device_id).strip():
        raise HTTPException(status_code=400, detail=_DEVICE_ID_REQUIRED_DETAIL)
    return str(x_device_id).strip()


async def fetch_owned_session(
    db,
    session_id: str,
    device_id: Optional[str],
) -> Dict[str, Any]:
    """Load a session and verify device ownership.

    Returns the session document on success.
    Raises HTTP 400 when device_id is missing, 404 when the session does not
    exist or the device does not own it. Error bodies are generic and never
    include session payloads.
    """
    if not device_id or not str(device_id).strip():
        raise HTTPException(status_code=400, detail=_DEVICE_ID_REQUIRED_DETAIL)

    session = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail=_SESSION_NOT_FOUND_DETAIL)

    stored = str(session.get("device_id") or "")
    provided = str(device_id)
    if not stored or not hmac.compare_digest(stored, provided):
        raise HTTPException(status_code=404, detail=_SESSION_NOT_FOUND_DETAIL)

    return session