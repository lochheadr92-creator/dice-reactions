"""
Deterministic tests for onboarding hook seeding (Phase 1 + Stage 2A).

No live LLM calls. Exercises the pure seeding/prompt helpers in server.py,
creation_contract, and the player_api serializers. Covers:

  * Story hooks (want/fear/ghost/talent/flaw/line/whoMatters) → simulation_hooks
  * Blocker A (relationships): whoMatters raises the relationship floor to 'low'
    and seeds an unnamed archetype bond; 'nobody' seeds nothing.
  * Blocker B (secret): stored ONLY in engine-side secret_registry (unrevealed),
    absent from simulation_hooks / prompt-visible rolling state / custom-setup
    prompt block / player API output.
  * Stage 2A: dead controls excluded; location/stability/knowledge structured.
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
import player_api  # noqa: E402
import creation_contract  # noqa: E402

SECRET_TEXT = "I set the fire that killed the convoy."


def _setup(**over):
    s = {
        "want": "revenge",
        "fear": "losing-control",
        "ghost": "betrayal",
        "talent": "investigation",
        "flaw": "pride",
        "line": "kill-innocents",
        "whoMatters": "someone-depending",
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
    assert "desire:revenge" in hooks
    assert "fear:losing-control" in hooks or "fear:losing control" in hooks
    assert "ghost:betrayal" in hooks
    assert "talent:investigation" in hooks
    assert "flaw:pride" in hooks
    assert "moral_line:kill-innocents" in hooks
    assert "relationship_archetype:someone-depending" in hooks


def test_absent_hooks_are_not_seeded():
    out = server._seed_custom_setup_into_rolling({}, {"want": "freedom"})
    hooks = " | ".join(out.get("simulation_hooks") or [])
    assert "desire:freedom" in hooks
    assert "fear:" not in hooks
    assert "flaw:" not in hooks


def test_advanced_builder_starting_conditions_seed_existing_state_surfaces():
    setup = {
        "startingLocation": "remote_wilderness",
        "startingRole": "worker_or_specialist",
        "worldCondition": "collapsing",
        "recentChange": "resources_became_scarce",
        "characterKnowledge": "deeply_involved",
        "worldPace": "slow_burn",  # dead — must not seed
        "consequenceSeverity": "severe",
        "settingGroundedness": "realistic",
        "worldElements": "a mountain observatory",
        "worldExclusions": "zombies",
    }

    out = server._seed_custom_setup_into_rolling({}, setup)
    hooks = " | ".join(out.get("simulation_hooks") or [])
    instability = " | ".join(out.get("world_instability") or [])

    assert "starting_location:remote wilderness" in hooks or "remote wilderness" in hooks
    assert "role:worker or specialist" in hooks or "worker" in hooks
    assert "knowledge_scope:deeply_involved" in hooks or out.get("knowledge_scope") == "deeply_involved"
    assert "world pace" not in hooks.lower()
    assert "consequence_severity:severe" in hooks or "severe" in hooks
    assert "groundedness:realistic" in hooks
    assert "required_elements:a mountain observatory" in hooks
    assert "excluded_elements:zombies" in hooks
    assert "world_stability:collapsing" in instability
    assert "recent_disruption:" in instability or "resources" in instability
    assert "story_focus" not in out


def test_advanced_custom_location_role_and_change_are_seeded_as_resolved_text():
    out = server._seed_custom_setup_into_rolling(
        {},
        {
            "startingLocation": "custom_location",
            "customLocation": "an orbital salvage yard",
            "startingRole": "custom_role",
            "customRole": "union mediator",
            "recentChange": "custom_event",
            "customRecentChange": "the docking authority vanished",
        },
    )
    hooks = " | ".join(out.get("simulation_hooks") or [])
    instability = " | ".join(out.get("world_instability") or [])

    assert "orbital salvage yard" in hooks
    assert "union mediator" in hooks or "role:union mediator" in hooks
    assert "docking authority vanished" in hooks or "docking authority vanished" in instability


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
    assert any(n == "who_matters_floor" for n in names)
    assert any(n == "social ecosystem" for n in names)
    floor = next(t for t in threads if t.get("name") == "who_matters_floor")
    assert floor.get("archetype") == "someone-depending"
    assert floor.get("named") is False


def test_who_matters_nobody_seeds_no_relationship_thread():
    out = server._seed_custom_setup_into_rolling(
        {}, _setup(whoMatters="nobody", contentSettings={"relationships": "none"})
    )
    threads = out.get("relationship_threads") or []
    assert all(t.get("name") != "who_matters_floor" for t in threads)
    assert all(t.get("name") != "social ecosystem" for t in threads)


def test_explicit_relationships_preserved_when_no_who_matters():
    # When whoMatters is absent, contentSettings alone may still raise a floor
    # via legacy path — but Stage 2A only seeds archetype floors from whoMatters.
    out = server._seed_custom_setup_into_rolling(
        {}, {"contentSettings": {"relationships": "mature bonds"}}
    )
    # Without whoMatters, creation_contract does not invent relationship threads.
    threads = out.get("relationship_threads") or []
    assert all(t.get("name") != "who_matters_floor" for t in threads if isinstance(t, dict))


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


def test_normalize_preserves_guided_pressure_list():
    n = creation_contract.normalize_custom_world_setup(
        {"pressures": ["isolation"], "want": "knowledge", "whoMatters": "mentor"},
        source_path="guided",
    )
    assert n["pressures"] == ["isolation"]
    assert n["creationFlow"] == "guided"
