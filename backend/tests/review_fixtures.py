"""Recorded turns from the three review stories played on 2026-11-23.

Exported read-only from the local game database. The stories themselves are
left in that database as evidence. These fixtures let the recorded bad outputs
be replayed through the real acceptance path without a model call.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

_PATH = Path(__file__).resolve().parent / "fixtures" / "review_2026_11_23_turns.json"
_DATA = json.loads(_PATH.read_text(encoding="utf-8"))


def story(name: str) -> Dict[str, Any]:
    return copy.deepcopy(_DATA["stories"][name])


def turn(name: str, number: int) -> Dict[str, Any]:
    return copy.deepcopy(_DATA["stories"][name]["turns"][str(number)])


def session_after(name: str, number: int) -> Dict[str, Any]:
    """The session as it stood after the given recorded turn was accepted."""
    recorded = story(name)
    accepted = recorded["turns"][str(number)]
    session = dict(recorded["session"])
    session["id"] = f"fixture-{name}-{number}"
    session["turn_count"] = number
    session["last_state"] = dict(accepted["state"] or {})
    session["last_narrative_snippet"] = (accepted["narrative"] or "")[:240]
    if accepted.get("rolling_state") is not None:
        session["rolling_state"] = accepted["rolling_state"]
    return session


def seed_story(mongo_env, name: str, upto: int, owner: str) -> str:
    """Store the recorded story, up to and including turn `upto`, in the guarded test database."""
    import uuid
    from datetime import datetime, timedelta, timezone

    recorded = story(name)
    now = datetime.now(timezone.utc)
    sid = str(uuid.uuid4())
    session = session_after(name, upto)
    session.update(
        {
            "id": sid,
            "device_id": owner,
            "debug_mode": True,
            "active_model": "anthropic/claude-3-5-haiku",
            "fallback_chain": [],
            "cost_mode": "normal",
            "created_at": now - timedelta(hours=1),
            "updated_at": now - timedelta(minutes=30),
        }
    )
    mongo_env.sessions.insert_one(session)
    for key in sorted(recorded["turns"], key=int):
        number = int(key)
        if number > upto:
            continue
        rec = recorded["turns"][key]
        mongo_env.turns.insert_one(
            {
                "id": str(uuid.uuid4()),
                "session_id": sid,
                "turn_number": number,
                "player_action": rec.get("player_action"),
                "narrative": rec.get("narrative") or "",
                "paragraphs": rec.get("paragraphs") or [],
                "choices": rec.get("choices") or [],
                "state": rec.get("state") or {},
                "ledger": rec.get("ledger") or {},
                "rolling_state": rec.get("rolling_state") or session.get("rolling_state") or {},
                "created_at": now - timedelta(minutes=60 - number),
            }
        )
    return sid
