"""
Run Identity v1 — deterministic tests (spec items 1–16 + causal dimensions).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import run_identity  # noqa: E402

FIXED_SEED_CORPUS = (
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    "cccccccc-cccc-cccc-cccc-cccccccccccc",
    "11111111-1111-1111-1111-111111111111",
    "22222222-2222-2222-2222-222222222222",
    "33333333-3333-3333-3333-333333333333",
    "44444444-4444-4444-4444-444444444444",
    "55555555-5555-5555-5555-555555555555",
)


def _setup(**over):
    base = {
        "genre": "noir",
        "role": "detective",
        "tone": "gritty",
        "difficulty": "standard",
        "scenario_id": None,
        "custom_premise": "",
        "custom_world_setup": {},
    }
    base.update(over)
    return base


def test_same_seed_and_setup_yields_identical_identity():
    setup = _setup(genre="fantasy", role="knight")
    a = run_identity.derive_run_identity(FIXED_SEED_CORPUS[0], setup)
    b = run_identity.derive_run_identity(FIXED_SEED_CORPUS[0], setup)
    assert a == b


def test_different_seed_yields_different_identity():
    setup = _setup()
    a = run_identity.derive_run_identity(FIXED_SEED_CORPUS[0], setup)
    b = run_identity.derive_run_identity(FIXED_SEED_CORPUS[1], setup)
    assert (
        a["primary_pressure_kind"] != b["primary_pressure_kind"]
        or a["scarcity_axis"] != b["scarcity_axis"]
    )


def test_different_setup_yields_different_identity_for_same_seed():
    a = run_identity.derive_run_identity(FIXED_SEED_CORPUS[0], _setup(genre="noir"))
    b = run_identity.derive_run_identity(FIXED_SEED_CORPUS[0], _setup(genre="horror"))
    assert a != b


@pytest.mark.parametrize("namespace,options", [
    ("tension_profile", run_identity.TENSION_PROFILES),
    ("primary_pressure_kind", run_identity.PRESSURE_KINDS),
    ("scarcity_axis", run_identity.SCARCITY_AXES),
])
def test_select_from_namespace_returns_closed_enum(namespace, options):
    chosen = run_identity.select_from_namespace(FIXED_SEED_CORPUS[2], namespace, options)
    assert chosen in options


def test_select_from_namespace_is_stable():
    opts = ("alpha", "beta", "gamma")
    assert (
        run_identity.select_from_namespace("seed", "ns", opts)
        == run_identity.select_from_namespace("seed", "ns", opts)
    )


def test_unrelated_namespace_does_not_alter_existing_field():
    setup = _setup()
    base = run_identity.derive_run_identity(FIXED_SEED_CORPUS[0], setup)
    run_identity.select_from_namespace(FIXED_SEED_CORPUS[0], "new_future_namespace", ("x", "y"))
    again = run_identity.derive_run_identity(FIXED_SEED_CORPUS[0], setup)
    assert base["primary_pressure_kind"] == again["primary_pressure_kind"]
    assert base["scarcity_axis"] == again["scarcity_axis"]


def test_has_secret_true_when_custom_secret_present():
    setup = _setup(custom_world_setup={"secret": "I burned the ledger."})
    identity = run_identity.derive_run_identity(FIXED_SEED_CORPUS[0], setup)
    assert identity["has_secret"] is True
    assert "burned" not in str(identity)


def test_has_secret_true_when_scenario_hidden_threat():
    setup = _setup(hidden_threat="They are coming at dusk.")
    identity = run_identity.derive_run_identity(FIXED_SEED_CORPUS[0], setup)
    assert identity["has_secret"] is True
    assert "dusk" not in str(identity)


def test_has_secret_false_without_secret_sources():
    identity = run_identity.derive_run_identity(FIXED_SEED_CORPUS[0], _setup())
    assert identity["has_secret"] is False


def test_public_view_exposes_enums_and_has_secret_only():
    setup = _setup(custom_world_setup={"secret": "hidden truth"})
    identity = run_identity.derive_run_identity(FIXED_SEED_CORPUS[0], setup)
    public = run_identity.identity_public_view(identity)
    assert "has_secret" in public
    assert "primary_pressure_kind" in public
    assert "setup_fingerprint" not in public
    assert "hidden truth" not in str(public)


def test_identity_uses_only_closed_enums():
    identity = run_identity.derive_run_identity(FIXED_SEED_CORPUS[3], _setup())
    assert run_identity.is_closed_enum_identity(identity)


def test_corpus_produces_causal_variation():
    setup = _setup()
    archetypes = set()
    primary_kinds = set()
    scarcity_axes = set()
    fault_lines = set()
    for seed in FIXED_SEED_CORPUS:
        identity = run_identity.derive_run_identity(seed, setup)
        primary_kinds.add(identity["primary_pressure_kind"])
        scarcity_axes.add(identity["scarcity_axis"])
        fault_lines.add(identity["relationship_fault_line"])
    assert len(primary_kinds) >= 2
    assert len(scarcity_axes) >= 2
    assert len(fault_lines) >= 2


def test_difficulty_affects_severity_not_identity_enums():
    easy = run_identity.derive_run_identity(FIXED_SEED_CORPUS[0], _setup(difficulty="easy"))
    hard = run_identity.derive_run_identity(FIXED_SEED_CORPUS[0], _setup(difficulty="hard"))
    assert easy["primary_pressure_kind"] == hard["primary_pressure_kind"]
    assert easy["scarcity_axis"] == hard["scarcity_axis"]
    assert easy["severity_multiplier"] < hard["severity_multiplier"]


def test_invalid_identity_fails_closed_enum_check():
    assert not run_identity.is_closed_enum_identity({"tension_profile": "not_real"})
    assert not run_identity.is_closed_enum_identity(None)


def test_causal_fields_present():
    identity = run_identity.derive_run_identity(FIXED_SEED_CORPUS[0], _setup())
    for field in run_identity.CAUSAL_ENUM_FIELDS:
        assert identity[field] in run_identity.CAUSAL_ENUM_FIELDS[field]