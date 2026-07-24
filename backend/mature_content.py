"""Structured mature-content preferences and fail-closed distribution policy.

This module owns setup validation only.  The values are presentation permissions,
not simulation inputs, and must never be mixed into replay or decision state.
"""

from __future__ import annotations

import os
import re
from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping, Optional


VIOLENCE_LEVELS = ("mild", "realistic", "graphic", "extreme_gore")
HORROR_LEVELS = (
    "atmospheric",
    "disturbing",
    "graphic",
    "extreme_psychological_or_body_horror",
)
SEXUAL_CONTENT_LEVELS = (
    "off",
    "romance_only",
    "suggestive",
    "fade_to_black",
    "explicit",
    "graphic",
)
CONSENT_BOUNDARIES = (
    "consensual_only",
    "coercion_referenced",
    "nonconsensual_implied",
    "nonconsensual_on_screen",
    "graphic_nonconsensual",
)
PLAYER_INVOLVEMENT_LEVELS = ("npcs_only", "player_character", "either")
LANGUAGE_LEVELS = ("mild", "strong", "unrestricted")
SUBSTANCE_LEVELS = ("mentioned", "present", "graphic_and_consequential")

_DEFAULT_MATURE_CONTENT: Dict[str, Any] = {
    "adult_mode_enabled": False,
    "adult_age_confirmed": False,
    "violence_level": "mild",
    "horror_level": "atmospheric",
    "sexual_content_level": "off",
    "consent_boundary": "consensual_only",
    "player_involvement": "npcs_only",
    "language_level": "mild",
    "substance_content_level": "mentioned",
    "hard_limits": [],
}


class MatureContentValidationError(ValueError):
    """Raised when a setup requests content the current policy cannot allow."""


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def default_mature_content() -> Dict[str, Any]:
    return deepcopy(_DEFAULT_MATURE_CONTENT)


def get_distribution_capabilities(*, renderer_configured: bool = False) -> Dict[str, Any]:
    """Return the current deployment's player-safe mature-content capability map.

    All mature capabilities default off.  Deployments must opt in explicitly and
    identify themselves as either an adult-enabled web or development channel.
    """

    channel = (os.environ.get("DISTRIBUTION_CHANNEL") or "store").strip().lower()
    channel_allows_adult = channel in {"adult_web", "development"}
    adult_mode_available = channel_allows_adult and _bool_env("ENABLE_MATURE_CONTENT")
    sexual_content_available = adult_mode_available and _bool_env(
        "ENABLE_MATURE_SEXUAL_CONTENT"
    )
    nonconsensual_content_available = sexual_content_available and _bool_env(
        "ENABLE_MATURE_NONCONSENSUAL_CONTENT"
    )
    graphic_sexual_content_available = sexual_content_available and _bool_env(
        "ENABLE_GRAPHIC_SEXUAL_CONTENT"
    )
    return {
        "channel": channel,
        "adult_mode_available": adult_mode_available,
        "sexual_content_available": sexual_content_available,
        "nonconsensual_content_available": nonconsensual_content_available,
        "graphic_sexual_content_available": graphic_sexual_content_available,
        "mature_renderer_configured": bool(renderer_configured),
    }


def _require_choice(field: str, value: Any, allowed: Iterable[str]) -> str:
    text = str(value or "").strip().lower()
    allowed_values = tuple(allowed)
    if text not in allowed_values:
        raise MatureContentValidationError(
            f"Invalid {field}; choose one of: {', '.join(allowed_values)}"
        )
    return text


def _normalise_hard_limits(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise MatureContentValidationError("Hard limits must be a list of exclusions")
    result: list[str] = []
    seen: set[str] = set()
    for raw in value[:20]:
        text = str(raw or "").strip()
        if not text:
            continue
        text = text[:120]
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


_MINOR_CODED_RE = re.compile(
    r"\b(?:minor|underage|child|preteen|schoolgirl|schoolboy|little\s+girl|"
    r"little\s+boy|teen(?:ager)?|barely\s+legal|young-looking)\b",
    re.IGNORECASE,
)
_UNDER_18_RE = re.compile(
    r"\b(?:age(?:d)?\s*(?:[0-9]|1[0-7])|"
    r"(?:[0-9]|1[0-7])\s*(?:years?\s*old|y/?o|-year-old))\b",
    re.IGNORECASE,
)
_AGE_BYPASS_RE = re.compile(
    r"(?:age\s*regress|de-?age|ignore\s+(?:the\s+)?age|age\s+doesn['’]?t\s+matter|"
    r"centur(?:y|ies)\s+old.{0,40}(?:body|look|physical|appearance).{0,20}(?:child|teen|underage)|"
    r"(?:body|look|physical|appearance).{0,20}(?:child|teen|underage).{0,40}centur(?:y|ies)\s+old|"
    r"physically\s+(?:a\s+)?(?:child|teen|underage)|"
    r"legal\s+despite\s+(?:being\s+)?(?:a\s+)?(?:minor|underage))",
    re.IGNORECASE | re.DOTALL,
)
_NEGATED_MINOR_LIMIT_RE = re.compile(
    r"\b(?:no|never|exclude|excluding|without|ban|blocked?)\s+"
    r"(?:minors?|underage|children|teens?|schoolgirls?|schoolboys?)\b",
    re.IGNORECASE,
)


def validate_custom_text_age_boundary(text: str) -> None:
    """Reject attempts to make sexual permissions apply to non-adult characters."""

    candidate = str(text or "")
    if not candidate.strip():
        return
    without_explicit_limits = _NEGATED_MINOR_LIMIT_RE.sub("", candidate)
    if _AGE_BYPASS_RE.search(candidate):
        raise MatureContentValidationError(
            "Age-regression and physically underage sexual scenarios are not permitted"
        )
    if _MINOR_CODED_RE.search(without_explicit_limits) or _UNDER_18_RE.search(
        without_explicit_limits
    ):
        raise MatureContentValidationError(
            "Sexual-content setups cannot include minors, minor-coded characters, or ambiguous under-18 ages"
        )


def collect_setup_text(value: Any, *, excluded_keys: Optional[set[str]] = None) -> str:
    """Collect user-authored setup text for age-boundary validation.

    Exclusion fields are omitted because saying "no minors" is a valid safety
    boundary and cannot weaken the structured renderer guard.
    """

    excluded = {key.casefold() for key in (excluded_keys or set())}
    parts: list[str] = []

    def visit(item: Any, key: str = "") -> None:
        if key.casefold() in excluded:
            return
        if isinstance(item, Mapping):
            for child_key, child in item.items():
                visit(child, str(child_key))
        elif isinstance(item, (list, tuple, set)):
            for child in item:
                visit(child, key)
        elif isinstance(item, str):
            parts.append(item)

    visit(value)
    return "\n".join(parts)


def normalize_mature_content(
    value: Any,
    capabilities: Mapping[str, Any],
    *,
    custom_text: str = "",
) -> Dict[str, Any]:
    """Validate and normalize mature preferences against current capabilities."""

    if value in (None, {}):
        return default_mature_content()
    if not isinstance(value, Mapping):
        raise MatureContentValidationError("Mature-content settings must be an object")

    enabled = bool(value.get("adult_mode_enabled", False))
    if not enabled:
        return default_mature_content()
    if not capabilities.get("adult_mode_available"):
        raise MatureContentValidationError(
            "Adult mode is not available in this distribution channel"
        )
    if value.get("adult_age_confirmed") is not True:
        raise MatureContentValidationError(
            "You must explicitly confirm that you are at least 18 to enable adult mode"
        )

    normalized = {
        "adult_mode_enabled": True,
        "adult_age_confirmed": True,
        "violence_level": _require_choice(
            "violence level", value.get("violence_level", "mild"), VIOLENCE_LEVELS
        ),
        "horror_level": _require_choice(
            "horror level", value.get("horror_level", "atmospheric"), HORROR_LEVELS
        ),
        "sexual_content_level": _require_choice(
            "sexual-content level",
            value.get("sexual_content_level", "off"),
            SEXUAL_CONTENT_LEVELS,
        ),
        "consent_boundary": _require_choice(
            "consent boundary",
            value.get("consent_boundary", "consensual_only"),
            CONSENT_BOUNDARIES,
        ),
        "player_involvement": _require_choice(
            "player involvement",
            value.get("player_involvement", "npcs_only"),
            PLAYER_INVOLVEMENT_LEVELS,
        ),
        "language_level": _require_choice(
            "language level", value.get("language_level", "mild"), LANGUAGE_LEVELS
        ),
        "substance_content_level": _require_choice(
            "drug and alcohol level",
            value.get("substance_content_level", "mentioned"),
            SUBSTANCE_LEVELS,
        ),
        "hard_limits": _normalise_hard_limits(value.get("hard_limits")),
    }

    sexual_level = normalized["sexual_content_level"]
    if sexual_level != "off" and not capabilities.get("sexual_content_available"):
        raise MatureContentValidationError(
            "Sexual-content settings are not available in this distribution channel"
        )
    if sexual_level == "graphic" and not capabilities.get(
        "graphic_sexual_content_available"
    ):
        raise MatureContentValidationError(
            "Graphic sexual content is not available in this distribution channel"
        )

    consent = normalized["consent_boundary"]
    if consent != "consensual_only" and not capabilities.get(
        "nonconsensual_content_available"
    ):
        raise MatureContentValidationError(
            "Non-consensual sexual-content settings are not available in this distribution channel"
        )
    if consent == "graphic_nonconsensual" and not capabilities.get(
        "graphic_sexual_content_available"
    ):
        raise MatureContentValidationError(
            "Graphic non-consensual content is not available in this distribution channel"
        )

    if sexual_level != "off":
        validate_custom_text_age_boundary(custom_text)
    return normalized


def build_rendering_policy(
    preferences: Mapping[str, Any], capabilities: Mapping[str, Any]
) -> Dict[str, Any]:
    enabled = bool(
        preferences.get("adult_mode_enabled")
        and preferences.get("adult_age_confirmed")
        and capabilities.get("adult_mode_available")
    )
    return {
        "route": "mature_pinned" if enabled else "standard",
        "failure_mode": "safe_standard",
        "sexual_age_boundary": "explicit_18_plus_only",
        "last_status": "pending" if enabled else "standard",
    }


_SEXUAL_CONTEXT_RE = re.compile(
    r"\b(?:sex(?:ual)?|intercourse|oral\s+sex|penetrat(?:e|ed|ion)|genitals?|"
    r"naked|nude|orgasm|arous(?:al|ed)|masturbat|explicit\s+intimacy)\b",
    re.IGNORECASE,
)


def contains_sexual_context(text: str) -> bool:
    return bool(_SEXUAL_CONTEXT_RE.search(str(text or "")))


def _explicit_age(row: Mapping[str, Any]) -> Optional[int]:
    for key in ("age", "age_years", "explicit_age"):
        raw = row.get(key)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, (int, float)):
            return int(raw)
        if isinstance(raw, str) and raw.strip().isdigit():
            return int(raw.strip())
    return None


def all_active_participants_are_explicit_adults(rolling_state: Any) -> bool:
    """Conservative render guard: unknown or ambiguous ages fail closed."""

    if not isinstance(rolling_state, Mapping):
        return False

    player_age: Optional[int] = None
    for key in ("player_age", "character_age"):
        raw = rolling_state.get(key)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            player_age = int(raw)
            break
    player = rolling_state.get("player")
    if player_age is None and isinstance(player, Mapping):
        player_age = _explicit_age(player)
    if player_age is None or player_age < 18:
        return False

    npcs = rolling_state.get("npcs") or []
    if not isinstance(npcs, list):
        return False
    for npc in npcs:
        if not isinstance(npc, Mapping):
            return False
        if npc.get("alive") is False or npc.get("absent") is True:
            continue
        age = _explicit_age(npc)
        if age is None or age < 18:
            return False
        life_stage = str(npc.get("life_stage") or "").strip().lower()
        if life_stage in {"child", "adolescent", "teen", "minor"}:
            return False
    return True
