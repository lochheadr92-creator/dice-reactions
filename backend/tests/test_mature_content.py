from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import mature_content  # noqa: E402


def _adult_capabilities(monkeypatch, *, sexual: bool = True):
    monkeypatch.setenv("DISTRIBUTION_CHANNEL", "development")
    monkeypatch.setenv("ENABLE_MATURE_CONTENT", "true")
    monkeypatch.setenv("ENABLE_MATURE_SEXUAL_CONTENT", "true" if sexual else "false")
    monkeypatch.setenv("ENABLE_MATURE_NONCONSENSUAL_CONTENT", "true")
    monkeypatch.setenv("ENABLE_GRAPHIC_SEXUAL_CONTENT", "true")
    return mature_content.get_distribution_capabilities(renderer_configured=True)


def test_distribution_capabilities_fail_closed_by_default(monkeypatch):
    for name in (
        "DISTRIBUTION_CHANNEL",
        "ENABLE_MATURE_CONTENT",
        "ENABLE_MATURE_SEXUAL_CONTENT",
        "ENABLE_MATURE_NONCONSENSUAL_CONTENT",
        "ENABLE_GRAPHIC_SEXUAL_CONTENT",
    ):
        monkeypatch.delenv(name, raising=False)

    capabilities = mature_content.get_distribution_capabilities()

    assert capabilities == {
        "channel": "store",
        "adult_mode_available": False,
        "sexual_content_available": False,
        "nonconsensual_content_available": False,
        "graphic_sexual_content_available": False,
        "mature_renderer_configured": False,
    }


def test_adult_mode_defaults_off_and_requires_explicit_age_confirmation(monkeypatch):
    capabilities = _adult_capabilities(monkeypatch)
    assert mature_content.normalize_mature_content(None, capabilities) == (
        mature_content.default_mature_content()
    )

    request = mature_content.default_mature_content()
    request["adult_mode_enabled"] = True

    with pytest.raises(mature_content.MatureContentValidationError, match="at least 18"):
        mature_content.normalize_mature_content(request, capabilities)


def test_unsupported_distribution_rejects_hidden_adult_request(monkeypatch):
    monkeypatch.setenv("DISTRIBUTION_CHANNEL", "store")
    monkeypatch.setenv("ENABLE_MATURE_CONTENT", "true")
    capabilities = mature_content.get_distribution_capabilities()
    request = {
        **mature_content.default_mature_content(),
        "adult_mode_enabled": True,
        "adult_age_confirmed": True,
    }

    with pytest.raises(mature_content.MatureContentValidationError, match="not available"):
        mature_content.normalize_mature_content(request, capabilities)


def test_preferences_normalize_as_structured_session_state(monkeypatch):
    capabilities = _adult_capabilities(monkeypatch)
    request = {
        **mature_content.default_mature_content(),
        "adult_mode_enabled": True,
        "adult_age_confirmed": True,
        "violence_level": "graphic",
        "horror_level": "disturbing",
        "sexual_content_level": "fade_to_black",
        "consent_boundary": "coercion_referenced",
        "player_involvement": "either",
        "language_level": "strong",
        "substance_content_level": "present",
        "hard_limits": ["No eye injuries", "no eye injuries", "  "],
    }

    normalized = mature_content.normalize_mature_content(
        request,
        capabilities,
        custom_text="A remote observatory staffed by adult specialists.",
    )

    assert normalized["adult_mode_enabled"] is True
    assert normalized["adult_age_confirmed"] is True
    assert normalized["sexual_content_level"] == "fade_to_black"
    assert normalized["hard_limits"] == ["No eye injuries"]
    assert mature_content.build_rendering_policy(normalized, capabilities) == {
        "route": "mature_pinned",
        "failure_mode": "safe_standard",
        "sexual_age_boundary": "explicit_18_plus_only",
        "last_status": "pending",
    }


@pytest.mark.parametrize(
    "text",
    [
        "A schoolgirl protagonist in an explicit relationship.",
        "The character is aged 17 but mature for their age.",
        "A centuries old spirit with the physical body of a child.",
        "Use age regression and ignore the age boundary.",
    ],
)
def test_custom_text_cannot_bypass_absolute_age_boundary(monkeypatch, text):
    capabilities = _adult_capabilities(monkeypatch)
    request = {
        **mature_content.default_mature_content(),
        "adult_mode_enabled": True,
        "adult_age_confirmed": True,
        "sexual_content_level": "explicit",
    }

    with pytest.raises(mature_content.MatureContentValidationError):
        mature_content.normalize_mature_content(
            request, capabilities, custom_text=text
        )


def test_explicit_safety_exclusion_is_not_misread_as_bypass(monkeypatch):
    capabilities = _adult_capabilities(monkeypatch)
    request = {
        **mature_content.default_mature_content(),
        "adult_mode_enabled": True,
        "adult_age_confirmed": True,
        "sexual_content_level": "suggestive",
    }

    normalized = mature_content.normalize_mature_content(
        request,
        capabilities,
        custom_text="No minors. All intimate contexts exclude underage characters.",
    )
    assert normalized["sexual_content_level"] == "suggestive"


def test_sexual_render_guard_requires_explicit_adult_ages_for_active_cast():
    assert mature_content.contains_sexual_context("They have sex.") is True
    assert mature_content.all_active_participants_are_explicit_adults({}) is False
    assert mature_content.all_active_participants_are_explicit_adults(
        {"player_age": 22, "npcs": [{"name": "Ari", "age": 17}]}
    ) is False
    assert mature_content.all_active_participants_are_explicit_adults(
        {"player_age": 22, "npcs": [{"name": "Ari", "age": 28}]}
    ) is True


def test_setup_text_collector_excludes_boundary_fields_only():
    text = mature_content.collect_setup_text(
        {
            "role": "adult specialist",
            "worldExclusions": "No minors",
            "nested": {"worldElements": "floating cities"},
        },
        excluded_keys={"worldExclusions"},
    )
    assert "adult specialist" in text
    assert "floating cities" in text
    assert "No minors" not in text

