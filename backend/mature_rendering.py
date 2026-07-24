"""Presentation-only mature renderer.

The authoritative turn has already been generated and validated before this
module runs.  Only prose may be replaced; state, choices, events, model locks,
and replay inputs remain untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping

from ai_config import get_mature_model_id
from ai_service import (
    AIServiceError,
    chat_completion_strict_with_meta,
    model_is_configured,
)
from mature_content import (
    all_active_participants_are_explicit_adults,
    contains_sexual_context,
    default_mature_content,
    get_distribution_capabilities,
    normalize_mature_content,
)


@dataclass(frozen=True)
class MatureRenderResult:
    narrative: str
    paragraphs: list[str]
    rendering_policy: Dict[str, Any]
    rendered: bool = False


def _is_pinned_model_id(model_id: str) -> bool:
    value = str(model_id or "").strip().lower()
    return bool(value) and not (
        value.endswith("/latest")
        or value.endswith(":latest")
        or value.endswith("-latest")
    )


def mature_renderer_is_configured() -> bool:
    model_id = get_mature_model_id()
    return _is_pinned_model_id(model_id) and model_is_configured(model_id)


def _paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def _policy(session: Mapping[str, Any], status: str, *, renderer: str = "standard") -> Dict[str, Any]:
    policy = dict(session.get("rendering_policy") or {})
    policy.setdefault("route", "standard")
    policy.setdefault("failure_mode", "safe_standard")
    policy.setdefault("sexual_age_boundary", "explicit_18_plus_only")
    policy["last_status"] = status
    policy["last_renderer"] = renderer
    return policy


def _extract_narrative(content: str) -> str:
    text = str(content or "").strip()
    match = re.fullmatch(r"\s*<narrative>\s*(.*?)\s*</narrative>\s*", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    if not text or re.search(r"</?(?:rolling_state|choices|state|ledger|debug)>", text):
        return ""
    return text


def _permission_summary(preferences: Mapping[str, Any]) -> str:
    hard_limits = preferences.get("hard_limits") or []
    limits_text = "; ".join(str(item) for item in hard_limits) if hard_limits else "none supplied"
    return (
        f"Violence maximum: {preferences.get('violence_level')}.\n"
        f"Horror maximum: {preferences.get('horror_level')}.\n"
        f"Sexual-content maximum: {preferences.get('sexual_content_level')}.\n"
        f"Consent boundary: {preferences.get('consent_boundary')}.\n"
        f"Player involvement: {preferences.get('player_involvement')}.\n"
        f"Language maximum: {preferences.get('language_level')}.\n"
        f"Drug/alcohol maximum: {preferences.get('substance_content_level')}.\n"
        f"Hard limits: {limits_text}."
    )


async def render_mature_presentation(
    session: Mapping[str, Any],
    canonical_narrative: str,
    authoritative_rolling_state: Mapping[str, Any] | None,
) -> MatureRenderResult:
    """Attempt one strict mature-model rerender, otherwise return safe prose."""

    original = str(canonical_narrative or "")
    original_paragraphs = _paragraphs(original)
    raw_preferences = session.get("mature_content") or default_mature_content()
    model_id = get_mature_model_id()
    configured = mature_renderer_is_configured()
    capabilities = get_distribution_capabilities(renderer_configured=configured)

    try:
        preferences = normalize_mature_content(raw_preferences, capabilities)
    except ValueError:
        return MatureRenderResult(
            original,
            original_paragraphs,
            _policy(session, "safe_fallback_policy_rejected"),
        )

    if not preferences.get("adult_mode_enabled"):
        return MatureRenderResult(
            original, original_paragraphs, _policy(session, "standard")
        )
    if not configured:
        return MatureRenderResult(
            original,
            original_paragraphs,
            _policy(session, "safe_fallback_renderer_unavailable"),
        )
    if contains_sexual_context(original) and not all_active_participants_are_explicit_adults(
        authoritative_rolling_state
    ):
        return MatureRenderResult(
            original,
            original_paragraphs,
            _policy(session, "safe_fallback_age_boundary"),
        )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a presentation-only narrative renderer. Rewrite only the supplied prose. "
                "Preserve every factual event, participant, action, consequence, order, location, object, "
                "injury, relationship, and uncertainty exactly. Do not add facts, choices, dialogue events, "
                "or future developments. Permissions are ceilings, never instructions: do not introduce a "
                "content category that is absent from the source and do not increase its frequency. Return "
                "exactly one <narrative> block and no other tags. Every sexual participant must be explicitly "
                "established as at least 18; if that cannot be verified, keep the passage non-sexual."
            ),
        },
        {
            "role": "user",
            "content": (
                "Presentation permissions:\n"
                + _permission_summary(preferences)
                + "\n\nCanonical prose to render without changing facts:\n<narrative>\n"
                + original
                + "\n</narrative>"
            ),
        },
    ]

    try:
        response = await chat_completion_strict_with_meta(
            messages=messages,
            model=model_id,
            temperature=0.35,
            max_tokens=max(512, min(4096, len(original) * 2)),
        )
    except AIServiceError:
        return MatureRenderResult(
            original,
            original_paragraphs,
            _policy(session, "safe_fallback_provider_error"),
        )

    rendered = _extract_narrative(response.get("content") or "")
    rendered_paragraphs = _paragraphs(rendered)
    if (
        not rendered
        or not rendered_paragraphs
        or len(rendered) > max(5000, int(len(original) * 1.6))
        or len(rendered_paragraphs) != len(original_paragraphs)
    ):
        return MatureRenderResult(
            original,
            original_paragraphs,
            _policy(session, "safe_fallback_invalid_render"),
        )
    if contains_sexual_context(rendered) and not all_active_participants_are_explicit_adults(
        authoritative_rolling_state
    ):
        return MatureRenderResult(
            original,
            original_paragraphs,
            _policy(session, "safe_fallback_age_boundary"),
        )

    return MatureRenderResult(
        rendered,
        rendered_paragraphs,
        _policy(session, "rendered_mature", renderer="mature_pinned"),
        rendered=True,
    )
