"""
Explicit allowlist serializers for player-facing API responses.

Builds responses from known-safe field sets only — unknown/internal fields
never pass through by default. Nested dicts and lists are scrubbed recursively.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from mature_content import default_mature_content

# Session fields exposed to players (device_id and engine metadata excluded).
PLAYER_SESSION_FIELDS = frozenset({
    "id",
    "genre",
    "role",
    "tone",
    "difficulty",
    "debug_mode",
    "title",
    "turn_count",
    "last_narrative_snippet",
    "last_state",
    "mode",
    "scenario_id",
    "mature_content",
    "distribution_capabilities",
    "rendering_policy",
    "created_at",
    "updated_at",
})

# Turn fields exposed to players.
PLAYER_TURN_FIELDS = frozenset({
    "id",
    "session_id",
    "turn_number",
    "player_action",
    "narrative",
    "paragraphs",
    "choices",
    "state",
    "ledger",
    "created_at",
})

# Visible simulation state keys (Objective/Goal stripped by HUD; not player-visible).
PLAYER_STATE_KEYS = frozenset({
    "Health",
    "Stress",
    "Fatigue",
    "Position",
    "Inventory Summary",
    "Conditions",
    "Notable Conditions",
    "Danger",
    "Momentum",
    "Pressure",
})

# Ledger categories shown in play UI.
PLAYER_LEDGER_KEYS = frozenset({
    "Carried",
    "Worn",
    "Stored",
    "Weapons",
    "Supplies",
    "Uncertain",
    "Load",
    "Ammo",
    "Tools",
    "Currency",
    "Notes",
})

PLAYER_CHOICE_KEYS = frozenset({"label", "text"})

_BLOCKED_STATE_KEYS = frozenset({
    "objective",
    "goal",
    "goals",
    "latent",
    "delayed trigger",
    "delayed",
    "active systems",
    "consequence budget",
    "scale",
    "pressure horizon",
    "rolling state",
    "trigger",
    "system",
})

_BLOCKED_NESTED_KEYS = _BLOCKED_STATE_KEYS | frozenset({
    "secret_registry",
    "rolling_state",
    "debug",
    "raw",
    "telemetry",
    "engine_dump",
    "engine_meta",
    "engine_hint",
    "internal",
})


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


# Established UTF-8→cp1252 mojibake sequences only (presentation repair).
# Used for historic turns already stored with corrupted punctuation. Does not
# mutate Mongo documents — applied only when building player-facing strings.
_MOJIBAKE_REPAIRS: tuple[tuple[str, str], ...] = (
    ("\u00e2\u20ac\u00a6", "\u2026"),  # â€¦ → …
    ("\u00e2\u20ac\u201d", "\u2014"),  # â€” → —
    ("\u00e2\u20ac\u201c", "\u2013"),  # â€“ → –
    ("\u00e2\u20ac\u2122", "\u2019"),  # â€™ → ’
    ("\u00e2\u20ac\u0153", "\u201c"),  # â€œ → “
    ("\u00e2\u0080\u009d", "\u201d"),  # â\x80\x9d → ”
    ("\u00e2\u20ac\u00a2", "\u2022"),  # â€¢ → •
)


def repair_player_mojibake(text: str) -> str:
    """Deterministic presentation repair for known mojibake sequences only.

    Idempotent: running twice leaves already-correct text unchanged.
    Valid Unicode and ordinary ASCII are never altered.
    """
    if not text or not isinstance(text, str):
        return text if isinstance(text, str) else str(text or "")
    out = text
    for bad, good in _MOJIBAKE_REPAIRS:
        if bad in out:
            out = out.replace(bad, good)
    return out


def _scrub_player_string(value: Any) -> str:
    from server import _scrub_meta_from_text  # noqa: WPS433 — avoid circular import at load

    text = str(value or "")
    scrubbed, _hits = _scrub_meta_from_text(text)
    return repair_player_mojibake(scrubbed)


def _state_key_allowed(key: str) -> bool:
    kl = (key or "").strip().lower()
    if kl in _BLOCKED_STATE_KEYS:
        return False
    return key in PLAYER_STATE_KEYS


def _nested_key_blocked(key: str) -> bool:
    kl = (key or "").strip().lower()
    return kl in _BLOCKED_NESTED_KEYS


def _sanitize_nested_value(value: Any) -> Any:
    """Recursively drop blocked/internal keys; strings are meta-scrubbed."""
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, nested in value.items():
            if _nested_key_blocked(key):
                continue
            cleaned = _sanitize_nested_value(nested)
            if cleaned is None:
                continue
            out[key] = cleaned
        return out
    if isinstance(value, list):
        items = [_sanitize_nested_value(item) for item in value]
        return [item for item in items if item is not None]
    if isinstance(value, (str, int, float, bool)):
        return _scrub_player_string(value)
    return None


def build_player_state(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not state:
        return {}
    out: Dict[str, Any] = {}
    for key, value in state.items():
        if not _state_key_allowed(key):
            continue
        if isinstance(value, dict):
            nested = _sanitize_nested_value(value)
            if nested:
                out[key] = nested
            continue
        if isinstance(value, list):
            nested = _sanitize_nested_value(value)
            if nested:
                out[key] = nested
            continue
        vl = str(value or "").lower()
        if "latent" in vl or "delayed trigger" in vl or "active systems" in vl:
            continue
        out[key] = _scrub_player_string(value)
    return out


def build_player_ledger(ledger: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not ledger:
        return {}
    out: Dict[str, Any] = {}
    for key, value in ledger.items():
        if key not in PLAYER_LEDGER_KEYS:
            continue
        if isinstance(value, dict):
            nested = _sanitize_nested_value(value)
            if nested:
                out[key] = nested
        elif isinstance(value, list):
            nested = _sanitize_nested_value(value)
            if nested:
                out[key] = nested
        elif value is not None:
            out[key] = _scrub_player_string(value)
    return out


def build_player_paragraphs(paragraphs: Any) -> List[str]:
    if not paragraphs:
        return []
    if isinstance(paragraphs, list):
        out: List[str] = []
        for item in paragraphs:
            if isinstance(item, str):
                out.append(_scrub_player_string(item))
            elif isinstance(item, dict):
                for key in item:
                    if key not in {"p", "text", "content"}:
                        continue
                    cleaned = _sanitize_nested_value(item.get(key))
                    if isinstance(cleaned, str):
                        out.append(cleaned)
            elif item is not None:
                cleaned = _sanitize_nested_value(item)
                if isinstance(cleaned, str):
                    out.append(cleaned)
        return out
    if isinstance(paragraphs, str):
        return [_scrub_player_string(paragraphs)]
    return []


def build_player_choices(choices: Any) -> List[Dict[str, str]]:
    if not choices or not isinstance(choices, list):
        return []
    out: List[Dict[str, str]] = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        row: Dict[str, str] = {}
        for key in PLAYER_CHOICE_KEYS:
            if key not in choice:
                continue
            value = choice[key]
            if isinstance(value, dict):
                nested = _sanitize_nested_value(value)
                if isinstance(nested, str):
                    row[key] = nested
            elif value is not None:
                row[key] = _scrub_player_string(value)
        if row:
            out.append(row)
    return out


def build_player_debug(debug: Any) -> Dict[str, str]:
    """Sanitized per-turn debug KV for dev-mode play UI only."""
    if not debug or not isinstance(debug, dict):
        return {}
    out: Dict[str, str] = {}
    for key, value in debug.items():
        if _nested_key_blocked(key):
            continue
        if value is None:
            continue
        if isinstance(value, dict):
            nested = _sanitize_nested_value(value)
            if nested:
                out[key] = _scrub_player_string(json.dumps(nested))
            continue
        if isinstance(value, list):
            nested = _sanitize_nested_value(value)
            if nested:
                out[key] = _scrub_player_string(json.dumps(nested))
            continue
        out[key] = _scrub_player_string(value)
    return out


def build_player_turn(
    turn: Dict[str, Any],
    *,
    include_debug: bool = False,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for field in PLAYER_TURN_FIELDS:
        if field not in turn:
            continue
        value = turn[field]
        if field == "state":
            out[field] = build_player_state(value if isinstance(value, dict) else None)
        elif field == "ledger":
            out[field] = build_player_ledger(value if isinstance(value, dict) else None)
        elif field == "paragraphs":
            out[field] = build_player_paragraphs(value)
        elif field == "choices":
            out[field] = build_player_choices(value)
        elif field == "created_at":
            out[field] = _iso(value)
        elif field == "narrative":
            out[field] = _scrub_player_string(value)
        else:
            out[field] = value
    if include_debug:
        debug_out = build_player_debug(turn.get("debug"))
        if debug_out:
            out["debug"] = debug_out
    return out


def build_player_session(session: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for field in PLAYER_SESSION_FIELDS:
        if field not in session:
            continue
        value = session[field]
        if field == "last_state":
            out[field] = build_player_state(value if isinstance(value, dict) else None)
        elif field in ("created_at", "updated_at"):
            out[field] = _iso(value)
        else:
            out[field] = value
    out.setdefault("mature_content", default_mature_content())
    out.setdefault("distribution_capabilities", {})
    out.setdefault(
        "rendering_policy",
        {
            "route": "standard",
            "failure_mode": "safe_standard",
            "sexual_age_boundary": "explicit_18_plus_only",
            "last_status": "standard",
        },
    )
    return out


def build_new_story_session_payload(session: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal session summary returned from POST /story/new."""
    allowed = {
        "id",
        "genre",
        "role",
        "difficulty",
        "debug_mode",
        "title",
        "turn_count",
        "mode",
        "scenario_id",
        "mature_content",
        "distribution_capabilities",
        "rendering_policy",
    }
    out = {k: session[k] for k in allowed if k in session}
    out.setdefault("mature_content", default_mature_content())
    out.setdefault("distribution_capabilities", {})
    out.setdefault(
        "rendering_policy",
        {
            "route": "standard",
            "failure_mode": "safe_standard",
            "sexual_age_boundary": "explicit_18_plus_only",
            "last_status": "standard",
        },
    )
    return out
