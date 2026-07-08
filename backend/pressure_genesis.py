"""
Stage 6C-0 — Pressure Genesis: flag + state-block scaffold.

Architecture: docs/stage-6c-pressure-genesis-brief.md. Motivating problem:
burn-in data shows the world reaching total equilibrium (no active
pressures/situations/goals) a few dozen turns in, because nothing re-seeds
pressure roots without player input. Genesis is the future subsystem that
will derive new pressure roots from existing state.

This module intentionally contains no rule table, candidate derivation, or
commit path yet -- those are Stage 6C-1 (shadow-mode candidate derivation)
and Stage 6C-2 (live commit behind a second flag). 6C-0's only job is to
prove the flag and state-block seam are wired into the turn pipeline without
changing behaviour:

    - ai_config.ENABLE_PRESSURE_GENESIS defaults OFF.
    - With the flag OFF, replayability.prepare_action_turn must not touch
      replayability_state at all -- the flag-off byte-identity fingerprint
      gate (backend/tools/simulate_world.py) is the acceptance test for this
      stage, not a unit test mock.
    - With the flag ON, the only observable effect is that
      replayability_state gains an empty, inert "pressure_genesis" block.

Engine authority (unchanged by this scaffold, restated for the reader):
genesis will write pressure roots ONLY via pressure_graph.upsert_pressure_node
once 6C-2 lands; it will never author situations/goals/events directly, and
the LLM never authors or observes this block. State is truth; narrative is
output.
"""

from __future__ import annotations

from typing import Any, Dict

import ai_config

GENESIS_VERSION = 1


def genesis_enabled() -> bool:
    """Call-time flag read (matches the foundation_promotion reader pattern)."""
    return bool(ai_config.ENABLE_PRESSURE_GENESIS)


def empty_genesis_state() -> Dict[str, Any]:
    """Minimal state-block shape for Stage 6C-0.

    Later stages will extend this shape (ledger, recent_kinds, receipts,
    process_register, ...) -- 6C-0 only proves the seam exists and is inert.
    """
    return {
        "version": GENESIS_VERSION,
    }
