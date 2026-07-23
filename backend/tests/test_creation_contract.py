"""Stage 2A — creation contract projection, persistence seeding, later-turn bounds."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import creation_contract  # noqa: E402
import replayability  # noqa: E402
import server  # noqa: E402
from memory import consolidate_rolling_state  # noqa: E402


# ---------------------------------------------------------------------------
# Normalize / contract projection
# ---------------------------------------------------------------------------


def test_normalize_strips_dead_controls_and_empties():
    setup = {
        "want": "safety",
        "fear": "failure",
        "whoMatters": "family-member",
        "worldPace": "slow_burn",
        "storyFocus": ["combat"],
        "secret": "I did it",
        "ghost": "",
        "talent": "investigation",
        "worldElements": "  ",
    }
    out = creation_contract.normalize_custom_world_setup(setup, source_path="advanced")
    assert out is not None
    assert "worldPace" not in out
    assert "storyFocus" not in out
    assert "secret" not in out
    assert "ghost" not in out
    assert "worldElements" not in out
    assert out["talent"] == "investigation"
    assert out["creationFlow"] == "advanced"
    assert out["whoMatters"] == "family-member"


def test_who_matters_aliases_do_not_become_parent_or_child():
    assert creation_contract.normalize_who_matters("family-member") == "family-member"
    assert creation_contract.normalize_who_matters("family-member") != "parent"
    assert creation_contract.normalize_who_matters("someone-depending") == "someone-depending"
    assert creation_contract.normalize_who_matters("someone-depending") != "child"
    # Legacy catalog slug remaps to dependant archetype, not a cast role.
    assert creation_contract.normalize_who_matters("child") == "someone-depending"


def test_guided_contract_projection():
    setup = {
        "creationFlow": "guided",
        "want": "knowledge",
        "fear": "becoming-a-monster",
        "whoMatters": "mentor",
        "pressures": ["isolation"],
    }
    contract = creation_contract.build_creation_contract(
        genre="science fiction",
        role="a scholar",
        tone="grim",
        difficulty="hard",
        custom_world_setup=setup,
    )
    assert contract["source_path"] == "guided"
    assert contract["genre"] == "science fiction"
    assert contract["role"] == "a scholar"
    assert contract["tone"] == "grim"
    assert contract["difficulty"] == "hard"
    assert contract["active_pressures"] == ["isolation"]
    assert contract["desire"] == "knowledge"
    assert contract["fear"] == "becoming-a-monster"
    assert contract["relationship_archetype"] == "mentor"
    # SF world frame must not auto-become cyberpunk.
    assert contract["world_frame"]["setting"] == "general_science_fiction"
    assert contract["world_frame"]["technology"] != "cybernetic"


def test_advanced_contract_fields():
    setup = {
        "creationFlow": "advanced",
        "startingLocation": "remote_wilderness",
        "worldCondition": "collapsing",
        "recentChange": "resources_became_scarce",
        "settingGroundedness": "realistic",
        "characterKnowledge": "basic_local_knowledge",
        "worldElements": "mountain observatory",
        "worldExclusions": "zombies",
        "want": "safety",
        "fear": "failure",
        "whoMatters": "nobody",
        "ghost": "betrayal",
        "talent": "survival",
        "flaw": "pride",
        "line": "kill-innocents",
        "consequenceSeverity": "severe",
    }
    contract = creation_contract.build_creation_contract(
        genre="horror",
        role="outsider",
        tone="grim",
        difficulty="hard",
        custom_world_setup=setup,
    )
    assert contract["starting_location"] == "remote wilderness"
    assert contract["world_stability"] == "collapsing"
    assert contract["recent_disruption"]
    assert contract["groundedness"] == "realistic"
    assert contract["knowledge_scope"] == "basic_local_knowledge"
    assert contract["required_elements"] == "mountain observatory"
    assert contract["excluded_elements"] == "zombies"
    assert contract["ghost"] == "betrayal"
    assert contract["talent"] == "survival"
    assert contract["flaw"] == "pride"
    assert contract["moral_line"] == "kill-innocents"
    assert contract["relationship_archetype"] == "nobody"
    assert contract["consequence_severity"] == "severe"
    # Tone and difficulty stay separate from stability/groundedness.
    assert contract["tone"] == "grim"
    assert contract["difficulty"] == "hard"
    assert contract["world_stability"] != contract["tone"]
    assert contract["groundedness"] != contract["tone"]


def test_empty_optionals_omitted_from_contract():
    contract = creation_contract.build_creation_contract(
        genre="modern",
        role="local",
        custom_world_setup={"want": "safety", "whoMatters": "nobody"},
    )
    assert "ghost" not in contract
    assert "talent" not in contract
    assert "required_elements" not in contract


# ---------------------------------------------------------------------------
# Seeding — pressure graph, rolling, relationship archetypes
# ---------------------------------------------------------------------------


def test_guided_pressure_seeds_pressure_graph_with_provenance():
    setup = {"pressures": ["isolation"], "want": "freedom", "whoMatters": "nobody"}
    state, _ = replayability.init_new_story(
        genre="fantasy",
        role="a wanderer",
        tone="grounded",
        difficulty="standard",
        scenario_id=None,
        custom_premise=None,
        custom_world_setup=setup,
        scenario=None,
        run_seed="seed-guided-pressure-1",
    )
    nodes = (state.get("pressure_graph") or {}).get("nodes") or []
    custom = [
        n
        for n in nodes
        if isinstance(n, dict) and n.get("origin_type") == "custom_setup"
    ]
    assert custom, "expected custom_setup pressure node"
    hit = next(
        (n for n in custom if "isolation" in str(n.get("origin_id") or "")),
        custom[0],
    )
    assert hit["kind"] == "social"  # isolation maps to social group
    assert "creation" in (hit.get("tags") or []) or any(
        "isolation" in str(t) for t in (hit.get("tags") or [])
    )
    assert any("isolation" in str(r) for r in (hit.get("evidence_refs") or []))


def test_seed_location_and_stability_into_rolling():
    setup = {
        "startingLocation": "crowded_city",
        "worldCondition": "uneasy",
        "recentChange": "conflict_intensified",
        "characterKnowledge": "well_connected",
        "settingGroundedness": "mostly_grounded",
        "want": "safety",
        "fear": "failure",
        "whoMatters": "friend",
    }
    out = server._seed_custom_setup_into_rolling({}, setup)
    assert "crowded city" in str(out.get("scene") or "").lower() or any(
        "starting_location" in str(h) for h in (out.get("simulation_hooks") or [])
    )
    assert out.get("knowledge_scope") == "well_connected"
    hooks = " | ".join(str(h) for h in (out.get("simulation_hooks") or []))
    assert "desire:safety" in hooks or "desire: safety" in hooks.replace(" ", "")
    assert "world_stability:uneasy" in "".join(str(x) for x in (out.get("world_instability") or []))
    # Dead control absent
    assert "world pace" not in hooks.lower()
    assert "story_focus" not in out


def test_who_matters_nobody_no_floor_or_named_cast():
    out = server._seed_custom_setup_into_rolling(
        {},
        {"whoMatters": "nobody", "want": "freedom", "contentSettings": {"relationships": "none"}},
    )
    threads = out.get("relationship_threads") or []
    assert threads == [] or all(
        t.get("name") != "who_matters_floor" for t in threads if isinstance(t, dict)
    )
    dumped = json.dumps(out)
    assert "who_matters_floor" not in dumped
    # No invented proper names.
    assert not any(name in dumped for name in ("Marlene", "Greg", "the child who"))


def test_who_matters_family_member_unnamed_archetype():
    out = server._seed_custom_setup_into_rolling(
        {},
        {"whoMatters": "family-member", "want": "safety"},
    )
    threads = out.get("relationship_threads") or []
    floor = [t for t in threads if isinstance(t, dict) and t.get("name") == "who_matters_floor"]
    assert floor
    assert floor[0]["archetype"] == "family-member"
    assert floor[0].get("named") is False
    # Must not personify as parent or invent a cast name.
    dumped = json.dumps(threads)
    assert "parent" not in dumped
    assert "the family-member who matters most" not in dumped
    assert "the family member who matters most" not in dumped


def test_someone_depending_not_child():
    out = server._seed_custom_setup_into_rolling(
        {}, {"whoMatters": "someone-depending", "want": "safety"}
    )
    threads = json.dumps(out.get("relationship_threads") or [])
    assert "someone-depending" in threads
    assert '"archetype": "child"' not in threads
    assert "the child who" not in threads


# ---------------------------------------------------------------------------
# Later-turn projection + compaction survival
# ---------------------------------------------------------------------------


def test_later_turn_directive_is_bounded_not_full_dump():
    setup = {
        "creationFlow": "advanced",
        "startingLocation": "small_settlement",
        "worldCondition": "divided",
        "characterKnowledge": "very_little",
        "worldElements": "a " + ("long element, " * 40),
        "worldExclusions": "zombies; vampires; " + ("x" * 200),
        "want": "redemption",
        "fear": "failure",
        "whoMatters": "partner",
        "ghost": "betrayal",
        "talent": "leadership",
        "flaw": "pride",
        "line": "kill-innocents",
        "pressures": ["authority"],
    }
    contract = creation_contract.build_creation_contract(
        genre="modern",
        role="leader",
        tone="grounded",
        difficulty="standard",
        custom_world_setup=setup,
    )
    directive = creation_contract.build_later_turn_creation_directive(contract)
    assert directive.startswith("[CREATION_CONTEXT]")
    assert "role=leader" in directive or "leader" in directive
    assert "authority" in directive
    assert "tone=grounded" in directive
    assert "difficulty=standard" in directive
    # Not a full JSON dump of setup.
    assert "creationFlow" not in directive
    assert len(directive) < 2200


def test_compaction_keeps_simulation_hooks_and_session_reconstructs_contract():
    setup = {
        "creationFlow": "guided",
        "want": "justice",
        "fear": "being-forgotten",
        "whoMatters": "mentor",
        "pressures": ["betrayal"],
        "worldExclusions": "cartoon slapstick",
    }
    seeded = server._seed_custom_setup_into_rolling({}, setup)
    # Simulate later-turn model output that drops some fields.
    model_rolling = {
        "scene": "a rain-slick alley",
        "objectives": ["find the ledger"],
        "simulation_hooks": [],  # model omitted — protected restore
        "world_instability": [],
    }
    merged = consolidate_rolling_state(seeded, model_rolling)
    hooks = " | ".join(str(h) for h in (merged.get("simulation_hooks") or []))
    assert "desire:justice" in hooks or "justice" in hooks
    assert "relationship_archetype:mentor" in hooks or "mentor" in hooks

    # Session bag remains the durable contract source after turn 1.
    session = {
        "genre": "noir",
        "role": "an investigator",
        "tone": "grim",
        "difficulty": "hard",
        "custom_world_setup": creation_contract.normalize_custom_world_setup(setup),
    }
    contract = creation_contract.build_creation_contract(session)
    assert contract["desire"] == "justice"
    assert contract["relationship_archetype"] == "mentor"
    assert contract["active_pressures"] == ["betrayal"]
    assert contract["excluded_elements"] == "cartoon slapstick"
    assert contract["genre"] == "noir"
    directive = creation_contract.build_later_turn_creation_directive(contract)
    assert "betrayal" in directive
    assert "mentor" in directive


def test_surprise_genre_frozen_on_session_contract():
    # Client resolves Surprise once into concrete genre; session.genre is authority.
    session = {
        "genre": "horror",
        "role": "a survivor",
        "tone": "bleak",
        "difficulty": "brutal",
        "custom_world_setup": {
            "creationFlow": "guided",
            "want": "safety",
            "fear": "dying-alone",
            "whoMatters": "nobody",
            "pressures": ["unknown"],
        },
    }
    contract = creation_contract.build_creation_contract(session)
    assert contract["genre"] == "horror"
    assert contract["tone"] == "bleak"
    assert contract["difficulty"] == "brutal"
    # Tone ≠ difficulty separation
    assert contract["tone"] != contract["difficulty"]


def test_classify_fields():
    assert creation_contract.classify_field("genre") == "hard_state"
    assert creation_contract.classify_field("active_pressures") == "persistent_simulation_input"
    assert creation_contract.classify_field("tone") == "presentation_policy"
    assert creation_contract.classify_field("secret") == "unsupported_excluded"
    assert creation_contract.classify_field("worldPace") == "unsupported_excluded"


def test_no_uncontrolled_duplication_growth():
    setup = {
        "want": "safety",
        "fear": "failure",
        "whoMatters": "friend",
        "pressures": ["scarcity"],
        "startingLocation": "small_settlement",
        "worldCondition": "uneasy",
        "settingGroundedness": "realistic",
        "characterKnowledge": "basic_local_knowledge",
        "ghost": "failure",
        "talent": "survival",
        "flaw": "pride",
        "line": "kill-innocents",
        "worldElements": "watchtowers",
        "worldExclusions": "magic",
    }
    contract = creation_contract.build_creation_contract(
        genre="fantasy", role="local", tone="grounded", difficulty="standard", custom_world_setup=setup
    )
    out = creation_contract.seed_creation_into_rolling({}, contract, setup=setup)
    # Second seed should not explode list sizes.
    out2 = creation_contract.seed_creation_into_rolling(out, contract, setup=setup)
    assert len(out2.get("simulation_hooks") or []) <= 16
    assert len(out2.get("world_instability") or []) <= 12
    assert len(json.dumps(out2.get("character_hooks") or {})) < 800
