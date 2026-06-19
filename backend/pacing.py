"""
Early-Game Pacing Governor v1 — pure, deterministic pacing helpers.

Does not access MongoDB, call an LLM, or own narrative truth. Stages 2–4
provide non-persisted guidance only; Stage 1 adds structural field-presence
validation after format checks.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Internal marker used in tests to locate the non-persisted system directive.
PACING_DIRECTIVE_MARKER = "[CHRONICLE_CONTINUITY]"

_BLANK_PRESSURE_VALUES = frozenset({"-", "—", "none", "nothing"})


def get_early_game_stage(turn_count: int) -> Optional[int]:
    """Map persisted pre-generation turn_count to pacing stage 1–4, or None."""
    if turn_count <= 0:
        return 1
    if turn_count == 1:
        return 2
    if turn_count == 2:
        return 3
    if turn_count == 3:
        return 4
    return None


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _non_empty_entry(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_non_empty_string(v) for v in value.values())
    return False


def _pressure_value(state: Optional[Dict[str, str]]) -> str:
    if not state:
        return ""
    for key, value in state.items():
        if (key or "").strip().lower() == "pressure":
            return str(value or "").strip()
    return ""


def has_engine_owned_development(rolling_state: Optional[Dict[str, Any]]) -> bool:
    """True when authoritative rolling_state already contains a concrete development."""
    if not isinstance(rolling_state, dict):
        return False

    for key in ("active_pressures", "unresolved", "faction_pressure"):
        items = rolling_state.get(key)
        if isinstance(items, list) and any(_non_empty_entry(x) for x in items):
            return True

    horizon = rolling_state.get("pressure_horizon")
    if isinstance(horizon, dict) and any(
        _non_empty_string(v) for v in horizon.values()
    ):
        return True

    for npc in rolling_state.get("npc_memory") or []:
        if not isinstance(npc, dict):
            continue
        if _non_empty_string(npc.get("next_move")):
            return True

    injuries = rolling_state.get("injuries")
    if isinstance(injuries, list) and any(_non_empty_entry(x) for x in injuries):
        return True

    for route_key in ("route_changes", "routes"):
        routes = rolling_state.get(route_key)
        if isinstance(routes, list) and any(_non_empty_entry(x) for x in routes):
            return True

    for rumour_key in ("rumours", "rumors"):
        rumours = rolling_state.get(rumour_key)
        if isinstance(rumours, list) and any(_non_empty_entry(x) for x in rumours):
            return True

    if _non_empty_string(rolling_state.get("world_instability")):
        return True

    unresolved_text = " ".join(
        str(x) for x in (rolling_state.get("unresolved") or []) if x
    ).lower()
    if "fired consequence" in unresolved_text:
        return True

    return False


def build_early_game_directive(
    stage: Optional[int],
    prior_rolling_state: Optional[Dict[str, Any]] = None,
) -> str:
    """Return a non-persisted internal system directive, or empty string."""
    if stage is None:
        return ""

    if stage == 1:
        return (
            f"{PACING_DIRECTIVE_MARKER}\n"
            "Opening genesis contract (no prior Chronicle truth exists yet):\n"
            "- Begin in medias res.\n"
            "- Something specific is already wrong, changing, needed, missing, arriving, "
            "breaking, threatened, exposed, contested, or being concealed.\n"
            "- Pure atmosphere, routine activity, location description, generic unease, "
            "or optional sightseeing is insufficient by itself.\n"
            "- Give the player an actionable reason to decide immediately.\n"
            "- Store the immediate situation in state Pressure.\n"
            "- Store at least one concrete pressure in rolling_state.active_pressures.\n"
            "- Store at least one forward route, stake, unresolved consequence, obligation, "
            "opportunity, or immediate objective in rolling_state.objectives or "
            "rolling_state.unresolved.\n"
            "- First choices must engage with the situation, not merely tour the setting.\n"
            "- Do not reveal a hidden scenario threat merely to satisfy pace; a visible "
            "symptom, clue, consequence, disturbance, demand, opportunity, or separate "
            "immediate problem is acceptable.\n"
            "- Quiet openings are valid when stakes are visible (waiting answer, favour due, "
            "opportunity expiring, evidence disappearing, moral choice with visible stakes).\n"
            "- Do not force combat or disaster."
        )

    if stage == 2:
        return (
            f"{PACING_DIRECTIVE_MARKER}\n"
            "Turn-2 continuity guidance (guidance only — do not invent unrelated world truth):\n"
            "- Resolve the player's first action with a visible result.\n"
            "- Advance, redirect, worsen, improve, expose, complicate, or partially resolve "
            "the established opening situation.\n"
            "- Treat prior rolling_state as authoritative.\n"
            "- Avoid returning to setup exposition or repeating the opening choices.\n"
            "- Make movement legible through prose and updated state.\n"
            "- Movement may be favourable or harmful; positive momentum is not required.\n"
            "- Do not invent an unrelated threat merely to make the scene feel busy."
        )

    if stage == 3:
        engine_note = ""
        if not has_engine_owned_development(prior_rolling_state):
            engine_note = (
                "\n- No engine-owned development is currently stored. Do not fabricate "
                "autonomous faction movement, NPC plans, environmental events, or delayed "
                "consequences. Continue resolving the player's action, preserve the existing "
                "pressure, and make any player-caused change visible."
            )
        return (
            f"{PACING_DIRECTIVE_MARKER}\n"
            "Turn-3 surfacing guidance (surface existing state — do not author autonomous "
            "world movement unless engine state already represents it):\n"
            "- Inspect engine-authoritative rolling_state for: active_pressures, "
            "pressure_horizon, unresolved, faction_pressure, npc_memory next moves, injuries, "
            "resource decline, route changes, delayed consequences already marked as fired, "
            "rumours already propagated, and existing world_instability.\n"
            "- If one contains a concrete development, surface it naturally in the scene.\n"
            "- You may also narrate a consequence causally produced by the player's action.\n"
            "- Do not invent a new autonomous faction movement, NPC plan, environmental event, "
            "or delayed consequence solely to satisfy this guidance."
            f"{engine_note}"
        )

    if stage == 4:
        return (
            f"{PACING_DIRECTIVE_MARKER}\n"
            "Turn-4 direction guidance (derive from established state — guidance only):\n"
            "- Consolidate an immediate direction, obstacle, stake, obligation, or meaningful "
            "fork from established state.\n"
            "- Use existing objectives, unresolved consequences, pressures, NPC goals, "
            "relationships, routes, and resources.\n"
            "- Give the player a choice that materially changes what happens next.\n"
            "- Allow movement toward worse outcomes.\n"
            "- Avoid resolving the entire Chronicle.\n"
            "- Do not invent a new unrelated crisis merely to create urgency."
        )

    return ""


def validate_opening_structure(parsed: Any) -> Optional[str]:
    """Stage-1 structural validation. Returns error reason or None if acceptable."""
    pressure = _pressure_value(getattr(parsed, "state", None) or {})
    if not pressure:
        return "missing Pressure in state"
    if pressure.lower() in _BLANK_PRESSURE_VALUES:
        return f"blank or placeholder Pressure: {pressure!r}"

    rolling = getattr(parsed, "rolling_state", None)
    if not isinstance(rolling, dict):
        return "missing rolling_state"

    active = rolling.get("active_pressures")
    if not isinstance(active, list) or not any(_non_empty_string(x) for x in active):
        return "missing active_pressures"

    objectives = rolling.get("objectives") if isinstance(rolling.get("objectives"), list) else []
    unresolved = rolling.get("unresolved") if isinstance(rolling.get("unresolved"), list) else []
    has_stake = any(_non_empty_entry(x) for x in objectives) or any(
        _non_empty_entry(x) for x in unresolved
    )
    if not has_stake:
        return "missing objectives and unresolved stake"

    return None


def build_pacing_retry_instruction(reason: str, debug_clause: str) -> str:
    """Correction note for Stage-1 structural failures (single shared retry budget)."""
    return (
        f"[SCENE_CORRECTION: {reason}]\n"
        "Rewrite the opening response while preserving all established generated facts "
        "that do not conflict with this correction: keep the same location, role, tone, "
        "inventory, named NPCs, and scenario seed.\n"
        "Supply a concrete state Pressure, at least one active_pressures entry, and at "
        "least one objectives or unresolved stake in rolling_state.\n"
        "Preserve hidden-threat secrecy. Output ONLY the required tag blocks "
        f"(<narrative>, <choices>, <state>, <ledger>, <rolling_state>{debug_clause}). "
        "Do NOT echo <prior_state>."
    )


def directive_present_in_messages(messages: List[Dict[str, str]]) -> bool:
    """Test helper: True when the internal pacing directive is a separate system message."""
    for msg in messages:
        if msg.get("role") == "system" and PACING_DIRECTIVE_MARKER in (msg.get("content") or ""):
            return True
    return False


def extract_directive_from_messages(messages: List[Dict[str, str]]) -> str:
    """Test helper: return pacing directive content if present."""
    for msg in messages:
        if msg.get("role") == "system" and PACING_DIRECTIVE_MARKER in (msg.get("content") or ""):
            return msg.get("content") or ""
    return ""