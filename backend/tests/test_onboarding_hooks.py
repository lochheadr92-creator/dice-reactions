"""
Deterministic tests for onboarding hook seeding (Phase 1 checkpoint).

No live LLM calls. Exercises the pure seeding/prompt helpers in server.py and
the player_api serializers. Covers:

  * Story hooks (want/fear/ghost/talent/flaw/line/whoMatters) → simulation_hooks
  * Blocker A (relationships): whoMatters raises the relationship floor to 'low'
    and seeds a "who matters most" bond; 'nobody' seeds nothing.
  * Blocker B (secret): stored ONLY in engine-side secret_registry (unrevealed),
    absent from simulation_hooks / prompt-visible rolling state / custom-setup
    prompt block / player API output.
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
import player_api  # noqa: E402

SECRET_TEXT = "I set the fire that killed the convoy."


def _setup(**over):
    s = {
        "want": "revenge",
        "fear": "losing-control",
        "ghost": "betrayal",
        "talent": "investigation",
        "flaw": "pride",
        "line": "kill-innocents",
        "whoMatters": "child",
        "secret": SECRET_TEXT,
        "contentSettings": {"relationships": "none"},
    }
    s.update(over)
    return s


# --------------------------------------------------------------------------- #
# Hooks → simulation_hooks (prompt-visible, intended)
# --------------------------------------------------------------------------- #
def test_hooks_seeded_into_simulation_hooks_humanized():
    out = server._seed_custom_setup_into_rolling({}, _setup())
    hooks = " | ".join(out.get("simulation_hooks") or [])
    assert "core desire: revenge" in hooks
    assert "core fear: losing control" in hooks  # slug humanized
    assert "buried past (the ghost): betrayal" in hooks
    assert "signature talent: investigation" in hooks
    assert "fatal flaw: pride" in hooks
    assert "moral line never to cross: kill innocents" in hooks
    assert "person who matters most: child" in hooks


def test_absent_hooks_are_not_seeded():
    out = server._seed_custom_setup_into_rolling({}, {"want": "freedom"})
    hooks = " | ".join(out.get("simulation_hooks") or [])
    assert "core desire: freedom" in hooks
    assert "core fear" not in hooks
    assert "fatal flaw" not in hooks


# --------------------------------------------------------------------------- #
# Blocker A — relationship floor (Option A)
# --------------------------------------------------------------------------- #
def test_effective_relationship_level_raised_by_who_matters():
    assert server._effective_relationships_level(_setup()) == "low"


def test_who_matters_nobody_does_not_raise_floor():
    s = _setup(whoMatters="nobody")
    assert server._effective_relationships_level(s) == "none"


def test_who_matters_seeds_bond_and_social_ecosystem():
    out = server._seed_custom_setup_into_rolling({}, _setup())
    threads = out.get("relationship_threads") or []
    names = [t.get("name", "") for t in threads]
    assert any("who matters most" in n for n in names)
    assert any(n == "social ecosystem" for n in names)


def test_who_matters_nobody_seeds_no_relationship_thread():
    out = server._seed_custom_setup_into_rolling(
        {}, _setup(whoMatters="nobody", contentSettings={"relationships": "none"})
    )
    threads = out.get("relationship_threads") or []
    assert all("who matters most" not in t.get("name", "") for t in threads)
    assert all(t.get("name") != "social ecosystem" for t in threads)


def test_explicit_relationships_preserved_when_no_who_matters():
    # Regression: existing behaviour unchanged when whoMatters absent.
    out = server._seed_custom_setup_into_rolling(
        {}, {"contentSettings": {"relationships": "mature bonds"}}
    )
    threads = out.get("relationship_threads") or []
    assert any(t.get("dynamic") == "mature bonds" for t in threads)


def test_custom_setup_block_surfaces_raised_floor():
    block = server._build_custom_world_setup_block(_setup())
    assert '"relationships": "low"' in block


# --------------------------------------------------------------------------- #
# Blocker B — secret is engine-only and never prompt/player visible
# --------------------------------------------------------------------------- #
def test_secret_stored_unrevealed_in_registry():
    out = server._seed_custom_setup_into_rolling({}, _setup())
    reg = out.get("secret_registry")
    assert isinstance(reg, list) and len(reg) == 1
    assert reg[0]["revealed"] is False
    assert reg[0]["turn_added"] == 1
    assert SECRET_TEXT in reg[0]["secret"]


def test_secret_absent_from_simulation_hooks_and_other_visible_fields():
    out = server._seed_custom_setup_into_rolling({}, _setup())
    # Everything EXCEPT the hidden registry must not contain the secret text.
    visible = {k: v for k, v in out.items() if k != "secret_registry"}
    assert SECRET_TEXT not in json.dumps(visible)
    assert all(SECRET_TEXT not in h for h in (out.get("simulation_hooks") or []))


def test_secret_absent_from_prompt_safe_rolling():
    out = server._seed_custom_setup_into_rolling({}, _setup())
    safe = server._prompt_safe_rolling(out)
    assert "secret_registry" not in safe
    assert SECRET_TEXT not in json.dumps(safe)


def test_secret_absent_from_custom_setup_prompt_block():
    block = server._build_custom_world_setup_block(_setup())
    assert SECRET_TEXT not in block
    assert '"secret"' not in block  # the key itself is not dumped
    # Non-secret setup still flows through.
    assert "revenge" in block


def test_secret_absent_from_player_session_export():
    session = {
        "id": "s1",
        "genre": "horror",
        "rolling_state": {"secret_registry": [{"secret": SECRET_TEXT, "revealed": False}]},
    }
    ps = player_api.build_player_session(session)
    dumped = json.dumps(ps)
    assert "secret_registry" not in dumped
    assert SECRET_TEXT not in dumped


def test_secret_absent_from_player_state_nested_block():
    state = {"Health": "wounded", "secret_registry": [{"secret": SECRET_TEXT}]}
    pstate = player_api.build_player_state(state)
    dumped = json.dumps(pstate)
    assert "secret_registry" not in dumped
    assert SECRET_TEXT not in dumped
    assert pstate.get("Health") == "wounded"  # legitimate field preserved


# --------------------------------------------------------------------------- #
# Purity / no-mutation guarantees
# --------------------------------------------------------------------------- #
def test_seeding_does_not_mutate_input_setup():
    s = _setup()
    snapshot = json.dumps(s, sort_keys=True)
    server._seed_custom_setup_into_rolling({}, s)
    assert json.dumps(s, sort_keys=True) == snapshot


def test_prompt_safe_rolling_does_not_mutate_input():
    rolling = {"secret_registry": [{"secret": SECRET_TEXT}], "active_pressures": ["dusk"]}
    server._prompt_safe_rolling(rolling)
    assert "secret_registry" in rolling  # original untouched
