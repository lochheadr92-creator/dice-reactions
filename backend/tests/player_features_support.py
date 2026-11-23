"""Shared fixture for the branch, notebook and handover tests.

One story with two characters who own different items and know different facts:
the protagonist (a scout) and Mara Voss. Every marker phrase is distinctive so a test can
search a whole narrator request for it.
"""

from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from security import DEVICE_ID_HEADER
from reliability_support import FIXED_NOW, insert_session

MARA_ID = "npc-aaaaaaaaaaaa"
TOMAS_ID = "npc-bbbbbbbbbbbb"
HOB_ID = "npc-cccccccccccc"

PROTAG_SECRET = "PROTAG-ONLY the ferryman's ledger has a torn page"
MARA_FACT = "MARA-FACT the cellar door was already open"
TOMAS_FACT = "TOMAS-FACT the ledger was burned"
HOOK_TEXT = "PROTAG-HOOK avenge the lost brother"
ENGINE_ONLY = "ENGINE-ONLY-TEXT never shown to the player"

FERRYMAN_LINE = "The ferryman swears the toll was paid before dusk."
GUARD_LINE = "The guard insists no boat left the dock that night."


def device() -> str:
    return f"dev_{uuid.uuid4()}"


def headers(device_id: str) -> Dict[str, str]:
    return {DEVICE_ID_HEADER: device_id}


def story_rolling() -> Dict[str, Any]:
    return {
        "scene": "the ferry dock",
        "location": "the ferry dock",
        "character": "bruised but steady",
        "inventory_objects": [{"object": "iron crowbar", "location_state": "carried"}],
        "object_locations": [{"object": "iron crowbar", "status": "carried", "where": "on the scout"}],
        "injuries": ["cut hand"],
        "npcs": [
            {"name": "Mara Voss", "npc_id": MARA_ID, "stance": "ally", "last_seen": "the ferry dock",
             "inventory": ["brass key"], "condition": "winded"},
            {"name": "Tomas Reed", "npc_id": TOMAS_ID, "stance": "neutral", "last_seen": "the ferry dock",
             "inventory": ["storm lantern"]},
            {"name": "Old Hob", "npc_id": HOB_ID, "stance": "neutral", "last_seen": "the ferry dock"},
        ],
        "npc_memory": [
            {"name": "Mara Voss", "goal": "find her brother",
             "remembers": [{"event": MARA_FACT, "severity": "major", "since_turn": 2}]},
            {"name": "Tomas Reed", "remembers": [{"event": TOMAS_FACT, "since_turn": 2}]},
        ],
        "clues": [
            {"text": PROTAG_SECRET},
            {"text": "A shared map of the dock", "witnesses": ["Mara Voss"]},
        ],
        "unresolved": ["Who cut the ferry rope"],
        "relationship_vectors": [{"name": "Mara Voss", "trust": 40}],
        "character_hooks": {"desire": HOOK_TEXT},
        "deceased": [],
    }


def turn_paragraphs(n: int) -> List[str]:
    paras = [f"Turn {n} opens as Mara Voss watches the black water."]
    if n == 1:
        paras.append(FERRYMAN_LINE)
        paras.append("Old Hob coughs in the doorway.")
    if n >= 2:
        paras.append("Tomas Reed counts coins by lantern light.")
    if n == 3:
        paras.append(GUARD_LINE)
    return paras


def seed_story(sync_db, device_id: str, *, turns: int = 3, rolling: Optional[Dict[str, Any]] = None,
               title: str = "Dock Mystery") -> str:
    rolling = copy.deepcopy(rolling if rolling is not None else story_rolling())
    sid = insert_session(
        sync_db, device_id, turn_count=turns, rolling=rolling,
        extra={"title": title, "last_narrative_snippet": "snippet",
               "last_state": {"Health": "stable", "Position": "the ferry dock"}},
    )
    for n in range(1, turns + 1):
        paragraphs = turn_paragraphs(n)
        sync_db.turns.insert_one({
            "id": str(uuid.uuid4()),
            "session_id": sid,
            "turn_number": n,
            "player_action": None if n == 1 else f"action {n}",
            "narrative": "\n\n".join(paragraphs),
            "canonical_narrative": "\n\n".join(paragraphs),
            "paragraphs": paragraphs,
            "choices": [
                {"label": "A", "text": f"Seed choice A{n}"}, {"label": "B", "text": f"Seed choice B{n}"},
                {"label": "C", "text": f"Seed choice C{n}"}, {"label": "D", "text": f"Seed choice D{n}"},
            ],
            "state": {"Health": "stable", "Position": "the ferry dock"},
            "ledger": {},
            "rolling_state": rolling,
            "raw": ENGINE_ONLY,
            "debug": {"note": ENGINE_ONLY},
            "created_at": FIXED_NOW,
        })
    return sid


def session_doc(sync_db, sid: str) -> Dict[str, Any]:
    return sync_db.sessions.find_one({"id": sid}, {"_id": 0})


def turn_docs(sync_db, sid: str) -> List[Dict[str, Any]]:
    return list(sync_db.turns.find({"session_id": sid}, {"_id": 0}).sort("turn_number", 1))


def dump(messages: Any) -> str:
    return json.dumps(messages, ensure_ascii=False, default=str)
