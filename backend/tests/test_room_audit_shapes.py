"""
_apply_room_audit tolerates model-written known_rooms rows (regression:
Qwen3.6 2026-11-21 wrote objects as dicts; set() raised TypeError and the
action returned 502).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


def _parsed(position):
    return server.parse_turn(
        "<rolling_state>{}</rolling_state><narrative>You look around.</narrative>"
        f"<choices>A. Wait.</choices><state>Position: {position}</state><ledger></ledger>"
    )


def test_dict_object_rows_in_known_rooms_do_not_crash():
    rolling = {
        "known_rooms": [
            {"key": "basement", "objects": [{"object": "Crowbar"}, {"name": "Crate"}, "sofa", 7]}
        ],
        "object_locations": [{"object": "Crowbar", "where": "basement", "status": "here"}],
    }
    adjustments = server._apply_room_audit(_parsed("Basement, by the stairs"), rolling)
    # Crate and sofa vanished with no truth row: flagged as drift, not a crash.
    drift = [a for a in adjustments if a.startswith("room_audit_drift:basement:")]
    assert drift and "crate" in drift[0] and "sofa" in drift[0]
    assert rolling["known_rooms"][-1]["objects"] == ["crowbar"]


def test_string_object_rows_behave_as_before():
    rolling = {
        "known_rooms": [{"key": "basement", "objects": ["crowbar"]}],
        "object_locations": [{"object": "Crowbar", "where": "basement", "status": "here"}],
    }
    assert server._apply_room_audit(_parsed("Basement"), rolling) == []
