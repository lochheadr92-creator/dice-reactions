"""Stage 2B — creation-contract runtime enforcement (deterministic)."""

from __future__ import annotations

import copy
import json
import os
import sys
from types import SimpleNamespace
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import creation_contract  # noqa: E402
import opening_state  # noqa: E402
import scenario_coherence as sc  # noqa: E402
import server  # noqa: E402
from memory import consolidate_rolling_state  # noqa: E402
import replayability  # noqa: E402


def _session(**over):
    base = {
        "genre": "fantasy",
        "role": "a scholar",
        "tone": "grim",
        "difficulty": "hard",
        "custom_world_setup": {
            "creationFlow": "guided",
            "want": "knowledge",
            "fear": "failure",
            "whoMatters": "nobody",
            "pressures": ["scarcity"],
            "startingLocation": "small_settlement",
            "settingGroundedness": "mostly_grounded",
        },
        "turn_count": 0,
    }
    base.update(over)
    return base


def _parsed(narrative: str, choices=None, rolling=None):
    return SimpleNamespace(
        narrative=narrative,
        paragraphs=[narrative],
        choices=choices or [{"label": "A", "text": "Look around carefully"}],
        rolling_state=rolling or {"scene": "a small settlement lane", "character": "a weary scholar"},
    )


# ---------------------------------------------------------------------------
# Genre catalogue gap
# ---------------------------------------------------------------------------


def test_science_fiction_and_modern_have_explicit_catalogs():
    assert opening_state.normalize_genre("science fiction") == "science fiction"
    assert opening_state.normalize_genre("science-fiction") == "science fiction"
    assert opening_state.normalize_genre("sci-fi") == "science fiction"
    assert opening_state.normalize_genre("modern") == "modern"
    sf = opening_state.catalog_for_genre("science fiction")
    assert "debt_called" not in sf
    assert opening_state.normalize_genre("cyberpunk") == "cyberpunk"
    cyber = opening_state.catalog_for_genre("cyberpunk")
    assert "debt_called" in cyber
    # SF must not equal cyberpunk catalog
    assert set(sf) != set(cyber)


def test_modern_containment_not_prehistoric_alias():
    assert opening_state.normalize_genre("modern containment") == "modern containment"
    cat = opening_state.catalog_for_genre("modern containment")
    assert "debt_called" not in cat
    assert "injury_complicates" in cat


def test_detective_and_custom_genre_handling():
    assert opening_state.normalize_genre("detective") == "mystery"
    # Unknown custom falls to general (still explicit path)
    assert opening_state.normalize_genre("my custom realm of fog") == "general"


# ---------------------------------------------------------------------------
# Hard constraint contradictions
# ---------------------------------------------------------------------------


def test_rejects_firearms_when_excluded():
    session = _session(
        genre="modern",
        custom_world_setup={
            "creationFlow": "advanced",
            "want": "safety",
            "fear": "failure",
            "whoMatters": "nobody",
            "worldExclusions": "firearms",
            "settingGroundedness": "mostly_grounded",
            "startingLocation": "crowded_city",
        },
    )
    parsed = _parsed(
        "Rain on neon glass.",
        [{"label": "A", "text": "Draw your pistol and fire at the crowd"}],
    )
    ok, reason = sc.run_creation_contract_checks(
        parsed=parsed, session=session, prior_rolling=None, is_opening=True
    )
    assert ok is False
    assert "firearm" in reason.lower() or "excluded" in reason.lower()


def test_rejects_magic_when_excluded():
    session = _session(
        genre="modern",
        custom_world_setup={
            "creationFlow": "advanced",
            "want": "safety",
            "whoMatters": "nobody",
            "worldExclusions": "magic",
            "settingGroundedness": "realistic",
        },
    )
    parsed = _parsed(
        "An alley.",
        [{"label": "A", "text": "Cast a spell to freeze the mugger"}],
    )
    ok, reason = sc.run_creation_contract_checks(
        parsed=parsed, session=session, prior_rolling=None, is_opening=True
    )
    assert ok is False
    assert "magic" in reason.lower()


def test_rejects_supernatural_in_realistic_world():
    session = _session(
        custom_world_setup={
            "creationFlow": "advanced",
            "want": "safety",
            "whoMatters": "nobody",
            "settingGroundedness": "realistic",
        }
    )
    parsed = _parsed("A quiet kitchen.", [{"label": "A", "text": "Talk to the ghost in the corner"}])
    ok, reason = sc.run_creation_contract_checks(
        parsed=parsed, session=session, prior_rolling=None, is_opening=True
    )
    assert ok is False
    assert "supernatural" in reason.lower() or "realistic" in reason.lower()


def test_rejects_debt_frame_in_science_fiction_opening():
    session = _session(
        genre="science fiction",
        role="a technician",
        custom_world_setup={
            "creationFlow": "guided",
            "want": "freedom",
            "fear": "failure",
            "whoMatters": "nobody",
            "pressures": ["scarcity"],
        },
    )
    parsed = _parsed(
        "The creditor arrives for foreclosure and building inspection of the habitat deed.",
        [{"label": "A", "text": "Renegotiate the fraudulent debt terms"}],
    )
    ok, reason = sc.run_creation_contract_checks(
        parsed=parsed, session=session, prior_rolling=None, is_opening=True
    )
    assert ok is False


def test_rejects_wrong_role_on_opening():
    session = _session(role="a scholar")
    parsed = _parsed(
        "You are issued a rifle and ordered into the trench as a soldier of the line.",
        rolling={"scene": "trenches", "character": "a frontline soldier"},
    )
    ok, reason = sc.run_creation_contract_checks(
        parsed=parsed, session=session, prior_rolling=None, is_opening=True
    )
    assert ok is False
    assert "role" in reason.lower()


def test_rejects_location_replacement_on_opening():
    session = _session(
        custom_world_setup={
            "creationFlow": "advanced",
            "startingLocation": "remote_wilderness",
            "want": "safety",
            "whoMatters": "nobody",
        }
    )
    parsed = _parsed(
        "Chrome elevators hum in the corporate tower lobby as traders shout on the stock exchange floor.",
        rolling={"scene": "corporate tower lobby", "character": "a visitor"},
    )
    ok, reason = sc.run_creation_contract_checks(
        parsed=parsed, session=session, prior_rolling=None, is_opening=True
    )
    assert ok is False
    assert "location" in reason.lower()


def test_nobody_rejects_named_relationship_invention():
    session = _session(
        custom_world_setup={
            "creationFlow": "guided",
            "want": "safety",
            "whoMatters": "nobody",
            "pressures": ["isolation"],
        }
    )
    parsed = _parsed(
        "Alone on the ridge.",
        [{"label": "A", "text": "Find Marlene and protect your partner"}],
        rolling={
            "relationship_threads": [
                {"name": "who_matters_floor", "archetype": "partner", "named": True}
            ]
        },
    )
    ok, reason = sc.run_creation_contract_checks(
        parsed=parsed, session=session, prior_rolling=None, is_opening=True
    )
    assert ok is False


def test_family_member_not_parent():
    session = _session(
        custom_world_setup={
            "whoMatters": "family-member",
            "want": "safety",
            "pressures": ["betrayal"],
        }
    )
    parsed = _parsed(
        "The road is empty.",
        [{"label": "A", "text": "Write to your father for money"}],
        rolling={"relationship_threads": [{"name": "parent", "archetype": "family-member"}]},
    )
    ok, reason = sc.run_creation_contract_checks(
        parsed=parsed, session=session, prior_rolling=None, is_opening=False
    )
    assert ok is False


def test_rejects_omniscient_choice_when_knowledge_very_little():
    session = _session(
        custom_world_setup={
            "characterKnowledge": "very_little",
            "want": "knowledge",
            "whoMatters": "nobody",
        }
    )
    parsed = _parsed(
        "Strangers fill the hall.",
        [{"label": "A", "text": "Expose the conspiracy you already know using hidden motive insight"}],
    )
    ok, reason = sc.run_creation_contract_checks(
        parsed=parsed, session=session, prior_rolling=None, is_opening=False
    )
    assert ok is False


def test_choice_rejects_unsupported_tech_object():
    session = _session(
        custom_world_setup={
            "worldExclusions": "firearms",
            "want": "safety",
            "whoMatters": "nobody",
        }
    )
    parsed = _parsed(
        "A quiet street.",
        [{"label": "A", "text": "Grab the plasma railgun from the crate"}],
        rolling={"inventory_objects": []},
    )
    ok, reason = sc.run_creation_contract_checks(
        parsed=parsed,
        session=session,
        prior_rolling={"inventory_objects": []},
        is_opening=False,
    )
    assert ok is False


def test_choice_accepts_visible_and_held_items():
    session = _session(
        custom_world_setup={"want": "safety", "whoMatters": "nobody", "worldExclusions": ""}
    )
    narrative = "A lantern hangs by the door. Mira watches the street."
    prior = {
        "inventory_objects": [{"object": "iron key", "location_state": "carried"}],
        "npcs": [{"name": "Mira"}],
    }
    ok, reason = sc.validate_choices_named_entities(
        [{"label": "A", "text": "Ask Mira about the road"}],
        narrative=narrative,
        prior_rolling=prior,
        scenario=None,
    )
    assert ok is True, reason
    ok2, reason2 = sc.validate_choice_grounding_objects_and_tech(
        contract=creation_contract.build_creation_contract(session),
        choices=[{"label": "B", "text": "Use the iron key on the door"}],
        narrative=narrative,
        prior_rolling=prior,
    )
    assert ok2 is True, reason2


def test_choice_length_bounds():
    ok, reason = sc.validate_choice_length_and_intent(
        [
            {
                "label": "A",
                "text": " ".join(["word"] * 40),
            }
        ]
    )
    assert ok is False


# ---------------------------------------------------------------------------
# Role continuity later turns
# ---------------------------------------------------------------------------


def test_role_change_without_event_rejected():
    session = _session(role="a scholar", turn_count=3)
    prior = {"character": "a careful scholar with ink-stained hands"}
    rolling = {"character": "a frontline soldier with a rifle"}
    parsed = _parsed(
        "You march with the regiment now.",
        rolling=rolling,
    )
    ok, reason = sc.validate_creation_role_continuity(
        contract=creation_contract.build_creation_contract(session),
        narrative=parsed.narrative,
        rolling=rolling,
        prior_rolling=prior,
        is_opening=False,
    )
    assert ok is False


def test_role_change_with_event_allowed():
    session = _session(role="a scholar", turn_count=3)
    prior = {"character": "a careful scholar"}
    rolling = {
        "character": "a conscripted soldier",
        "recent_beats": ["forced into militia after the raid"],
        "objectives": ["survive enlistment"],
    }
    ok, reason = sc.validate_creation_role_continuity(
        contract=creation_contract.build_creation_contract(session),
        narrative="They enlisted you at spearpoint.",
        rolling=rolling,
        prior_rolling=prior,
        is_opening=False,
    )
    assert ok is True, reason


# ---------------------------------------------------------------------------
# Compaction reconstruction
# ---------------------------------------------------------------------------


def test_compaction_restores_world_frame_and_character_hooks():
    session = _session(
        custom_world_setup={
            "creationFlow": "advanced",
            "want": "redemption",
            "fear": "becoming-a-monster",
            "whoMatters": "mentor",
            "ghost": "betrayal",
            "talent": "investigation",
            "worldExclusions": "zombies",
            "worldElements": "watchtowers",
            "settingGroundedness": "realistic",
            "startingLocation": "small_settlement",
            "pressures": ["authority"],
        }
    )
    seeded = server._seed_custom_setup_into_rolling({}, session["custom_world_setup"])
    seeded = creation_contract.restore_creation_surfaces(seeded, session)
    assert seeded.get("world_frame")
    assert seeded.get("character_hooks", {}).get("desire") == "redemption"

    # Model omits dict surfaces on later turn
    model = {
        "scene": "market square",
        "objectives": ["find water"],
        "simulation_hooks": [],
        "world_instability": [],
        "character_hooks": {},
        "world_frame": {},
    }
    merged = consolidate_rolling_state(seeded, model)
    # Protected hooks lists restored; dicts may be empty — restore from session
    restored = creation_contract.restore_creation_surfaces(merged, session)
    assert restored["world_frame"].get("excluded_elements") == "zombies" or "zombies" in str(
        restored["world_frame"]
    )
    assert restored["character_hooks"]["desire"] == "redemption"
    assert restored["character_hooks"].get("fear")
    contract = creation_contract.build_creation_contract(session)
    assert contract["required_elements"] == "watchtowers"
    assert contract["excluded_elements"] == "zombies"
    d1 = creation_contract.build_later_turn_creation_directive(contract)
    d2 = creation_contract.build_later_turn_creation_directive(contract)
    assert d1 == d2
    assert len(d1) < 2200


def test_bounded_projection_does_not_grow_every_turn():
    session = _session()
    contract = creation_contract.build_creation_contract(session)
    sizes = [
        len(creation_contract.build_later_turn_creation_directive(contract)) for _ in range(5)
    ]
    assert max(sizes) == min(sizes)


# ---------------------------------------------------------------------------
# Pressure seeding continuity
# ---------------------------------------------------------------------------


def test_guided_pressure_remains_in_graph_and_context():
    setup = {"pressures": ["isolation"], "want": "knowledge", "whoMatters": "nobody"}
    state, _ = replayability.init_new_story(
        genre="horror",
        role="an investigator",
        tone="grim",
        difficulty="hard",
        scenario_id=None,
        custom_premise=None,
        custom_world_setup=setup,
        scenario=None,
        run_seed="seed-2b-pressure",
    )
    session = {
        "genre": "horror",
        "role": "an investigator",
        "tone": "grim",
        "difficulty": "hard",
        "custom_world_setup": setup,
        "replayability_state": state,
    }
    labels = creation_contract.active_seeded_pressure_labels(session)
    assert any("isolation" in str(x).lower() for x in labels)
    nodes = (state.get("pressure_graph") or {}).get("nodes") or []
    custom = [n for n in nodes if isinstance(n, dict) and n.get("origin_type") == "custom_setup"]
    assert custom
    assert all(str(n.get("status") or "active") != "" for n in custom)


# ---------------------------------------------------------------------------
# Tone vs difficulty
# ---------------------------------------------------------------------------


def test_tone_and_difficulty_separate_consumers():
    session = {
        "genre": "modern",
        "role": "local",
        "tone": "hopeful",
        "difficulty": "brutal",
        "custom_world_setup": {"want": "safety", "whoMatters": "nobody", "worldCondition": "collapsing"},
    }
    contract = creation_contract.build_creation_contract(session)
    assert contract["tone"] == "hopeful"
    assert contract["difficulty"] == "brutal"
    assert contract["world_stability"] == "collapsing"
    assert contract["tone"] != contract["difficulty"]
    assert contract["world_stability"] != contract["tone"]
    info = creation_contract.difficulty_reaches_severity(session)
    assert info["severity_multiplier"] > 1.0
    assert info["tone_independent"] is True
    soft = creation_contract.difficulty_reaches_severity({**session, "difficulty": "soft"})
    assert soft["severity_multiplier"] < info["severity_multiplier"]


def test_hook_influence_is_not_mind_control():
    contract = creation_contract.build_creation_contract(
        _session(
            custom_world_setup={
                "want": "revenge",
                "fear": "failure",
                "ghost": "betrayal",
                "talent": "fighting",
                "flaw": "pride",
                "line": "kill-innocents",
                "whoMatters": "friend",
            }
        )
    )
    text = creation_contract.build_hook_influence_directive(contract)
    assert "never force" in text.lower() or "Never force" in text
    assert "guarantee success" in text.lower() or "never guarantee" in text.lower()
    assert "revenge" in text.lower()


# ---------------------------------------------------------------------------
# Full coherence path + server validation kind
# ---------------------------------------------------------------------------


def test_full_validate_marks_creation_coherence_failure():
    session = _session(
        custom_world_setup={
            "worldExclusions": "firearms",
            "want": "safety",
            "whoMatters": "nobody",
        }
    )
    parsed = server.ParsedTurn(
        narrative="Quiet street.",
        paragraphs=["Quiet street."],
        choices=[
            {"label": "A", "text": "Fire the shotgun at the crowd"},
            {"label": "B", "text": "Walk away"},
            {"label": "C", "text": "Hide"},
            {"label": "D", "text": "Wait"},
        ],
        state={"Pressure": "tense", "Health": "ok"},
        rolling_state={"scene": "street"},
        ledger={},
        debug=None,
        raw="",
    )
    # Ensure minimum choice count for format validation
    ok, reason, kind = server._full_validate(parsed, session, player_action=None, early_game_stage=1)
    if not ok and kind == "format":
        # Format may fail first if choices insufficient — still assert coherence path works
        ok2, reason2 = sc.run_coherence_checks(
            parsed=parsed, session=session, scenario=None, prior_rolling=None, is_opening=True
        )
        assert ok2 is False
        assert "firearm" in reason2.lower() or "excluded" in reason2.lower()
    else:
        assert ok is False
        assert kind in ("coherence", "format", "pacing")


# ---------------------------------------------------------------------------
# Five-turn mocked evolution (no provider)
# ---------------------------------------------------------------------------


def _five_turn_session(setup, genre, role, tone, difficulty):
    state, _ = replayability.init_new_story(
        genre=genre,
        role=role,
        tone=tone,
        difficulty=difficulty,
        scenario_id=None,
        custom_premise=None,
        custom_world_setup=setup,
        scenario=None,
        run_seed=f"five-{genre}-{role}"[:40],
    )
    return {
        "genre": genre,
        "role": role,
        "tone": tone,
        "difficulty": difficulty,
        "custom_world_setup": setup,
        "replayability_state": state,
        "turn_count": 0,
    }


def _advance_mocked(session, prior_rolling, turn_i: int):
    """Simulate a valid turn: compact model output + restore + re-derive contract."""
    model = {
        "scene": f"scene-turn-{turn_i}",
        "character": str(session.get("role") or "traveller"),
        "objectives": [f"objective-{turn_i}"],
        "unresolved": ["keep moving"],
        "simulation_hooks": [],
        "world_instability": [],
        "recent_beats": [f"beat {turn_i}"],
        "inventory_objects": prior_rolling.get("inventory_objects") or [],
    }
    merged = consolidate_rolling_state(prior_rolling, model)
    merged = creation_contract.restore_creation_surfaces(merged, session)
    contract = creation_contract.build_creation_contract(session)
    directive = creation_contract.build_later_turn_creation_directive(contract)
    session = dict(session)
    session["turn_count"] = turn_i
    session["rolling_state"] = merged
    return session, merged, contract, directive


def test_five_turn_guided_and_advanced_matrices():
    cases = [
        # Guided
        (
            "fantasy",
            "a scholar",
            "grim",
            "hard",
            {
                "creationFlow": "guided",
                "want": "knowledge",
                "fear": "failure",
                "whoMatters": "mentor",
                "pressures": ["scarcity"],
            },
        ),
        (
            "horror",
            "an investigator",
            "grim",
            "hard",
            {
                "creationFlow": "guided",
                "want": "safety",
                "fear": "dying-alone",
                "whoMatters": "nobody",
                "pressures": ["isolation"],
            },
        ),
        (
            "post-apocalyptic",
            "a hardened survivor",
            "bleak",
            "brutal",
            {
                "creationFlow": "guided",
                "want": "freedom",
                "fear": "failure",
                "whoMatters": "friend",
                "pressures": ["authority"],
            },
        ),
        # Advanced
        (
            "fantasy",
            "local resident",
            "bleak",
            "standard",
            {
                "creationFlow": "advanced",
                "startingLocation": "small_settlement",
                "worldCondition": "stable",
                "settingGroundedness": "mostly_grounded",
                "want": "safety",
                "whoMatters": "nobody",
                "storyFeel": "bleak",
            },
        ),
        (
            "modern",
            "outsider",
            "hopeful",
            "hard",
            {
                "creationFlow": "advanced",
                "startingLocation": "crowded_city",
                "worldCondition": "collapsing",
                "settingGroundedness": "realistic",
                "want": "justice",
                "whoMatters": "partner",
                "worldExclusions": "supernatural",
            },
        ),
        (
            "science fiction",
            "technician",
            "grounded",
            "standard",
            {
                "creationFlow": "advanced",
                "startingLocation": "isolated_location",
                "settingGroundedness": "openly_speculative",
                "want": "knowledge",
                "whoMatters": "nobody",
                "worldExclusions": "firearms",
            },
        ),
        (
            "modern",
            "traveller",
            "grounded",
            "standard",
            {
                "creationFlow": "advanced",
                "startingLocation": "remote_wilderness",
                "characterKnowledge": "very_little",
                "settingGroundedness": "realistic",
                "want": "safety",
                "whoMatters": "nobody",
            },
        ),
        (
            "modern",
            "ranger",
            "grim",
            "hard",
            {
                "creationFlow": "advanced",
                "startingLocation": "remote_wilderness",
                "settingGroundedness": "openly_speculative",
                "worldElements": "dinosaurs",
                "want": "survival" if False else "safety",
                "whoMatters": "nobody",
                "worldExclusions": "magic",
            },
        ),
    ]

    for genre, role, tone, difficulty, setup in cases:
        session = _five_turn_session(setup, genre, role, tone, difficulty)
        rolling = creation_contract.restore_creation_surfaces(
            server._seed_custom_setup_into_rolling({}, setup), session
        )
        directives = []
        for t in range(1, 6):
            session, rolling, contract, directive = _advance_mocked(session, rolling, t)
            directives.append(directive)
            assert contract.get("genre") == genre
            assert contract.get("role") == role
            assert rolling.get("character_hooks") or contract.get("desire")
            if setup.get("worldExclusions"):
                assert contract.get("excluded_elements")
                assert setup["worldExclusions"] in str(contract.get("excluded_elements"))
            if setup.get("pressures"):
                labels = creation_contract.active_seeded_pressure_labels(session)
                assert labels
            # Invalid firearm injection still fails
            if "firearm" in str(setup.get("worldExclusions") or "").lower():
                bad = _parsed(
                    "A field.",
                    [{"label": "A", "text": "Fire the rifle at the trees"}],
                )
                ok, _ = sc.run_creation_contract_checks(
                    parsed=bad, session=session, prior_rolling=rolling, is_opening=False
                )
                assert ok is False
            # Legitimate evolution: new objective is fine
            good = _parsed(
                f"You press on through turn {t}.",
                [{"label": "A", "text": "Search the area"}, {"label": "B", "text": "Wait and listen"}],
                rolling=rolling,
            )
            ok_g, reason_g = sc.run_creation_contract_checks(
                parsed=good, session=session, prior_rolling=rolling, is_opening=False
            )
            assert ok_g is True, f"{genre}: {reason_g}"
        # Projection stable size
        assert max(len(d) for d in directives) - min(len(d) for d in directives) < 200


def test_full_onboarding_not_duplicated_in_later_turn_projection():
    setup = {
        "creationFlow": "advanced",
        "want": "safety",
        "fear": "failure",
        "whoMatters": "friend",
        "ghost": "betrayal",
        "talent": "survival",
        "flaw": "pride",
        "line": "kill-innocents",
        "worldElements": "long " * 50,
        "worldExclusions": "magic",
        "startingLocation": "small_settlement",
        "characterKnowledge": "basic_local_knowledge",
        "pressures": ["scarcity", "violence"],
    }
    session = _session(custom_world_setup=setup)
    contract = creation_contract.build_creation_contract(session)
    directive = creation_contract.build_later_turn_creation_directive(contract)
    assert "creationFlow" not in directive
    assert directive.count("[CREATION_CONTEXT]") == 1
    assert "long long long" not in directive or len(directive) < 2200


# ---------------------------------------------------------------------------
# Stage 3 — hard both-fail fail-forward (no invalid best-available commit)
# ---------------------------------------------------------------------------


def _valid_choice_block(*texts):
    labels = "ABCDEF"
    lines = []
    for i, t in enumerate(texts):
        lines.append(f"{labels[i]}. {t}")
    while len(lines) < 4:
        lines.append(f"{labels[len(lines)]}. Wait and watch")
    return "\n".join(lines)


def _turn_xml(
    narrative: str,
    choices,
    rolling: dict,
    *,
    state: Optional[dict] = None,
) -> str:
    import json as _json

    choice_block = _valid_choice_block(*choices) if isinstance(choices[0], str) else None
    if choice_block is None:
        choice_block = "\n".join(f"{c['label']}. {c['text']}" for c in choices)
    st = state or {"Health": "stable", "Pressure": "scarcity", "Position": "lane"}
    state_lines = "\n".join(f"{k}: {v}" for k, v in st.items())
    return (
        f"<rolling_state>{_json.dumps(rolling)}</rolling_state>\n"
        f"<narrative>\n{narrative}\n</narrative>\n"
        f"<paragraphs><p>{narrative}</p></paragraphs>\n"
        f"<choices>\n{choice_block}\n</choices>\n"
        f"<state>\n{state_lines}\n</state>\n"
        f"<ledger>\nCarried: satchel\n</ledger>\n"
    )


def test_validation_severity_hard_vs_soft():
    assert server._validation_failure_is_hard(
        "coherence", "choice introduces unknown person 'Harwood' before narrative/state introduction"
    )
    assert server._validation_failure_is_hard(
        "coherence", "choice uses excluded technology/element (firearms)"
    )
    assert server._validation_failure_is_hard("hallucination", "npc resurrected")
    assert server._validation_failure_is_hard("format", "missing required choice labels: A")
    assert not server._validation_failure_is_hard(
        "coherence", "choice too long (40 words; max 28)"
    )
    assert not server._validation_failure_is_hard(
        "coherence", "choice packs multiple strategies; use one intention"
    )
    assert not server._validation_failure_is_hard("pacing", "opening lacks setup beat")


def test_fail_forward_builder_preserves_prior_state_and_grounds_choices():
    prior = {
        "scene": "small settlement lane",
        "character": "a weary scholar",
        "active_pressures": [{"id": "p1", "label": "scarcity", "status": "active"}],
        "inventory_objects": [{"object": "satchel"}],
        "object_locations": [{"object": "well", "location": "lane"}],
        "npcs": [{"name": "Mira", "alive": True}],
        "role": "a scholar",
    }
    session = _session(
        turn_count=2,
        role="a scholar",
        last_state={"Health": "bruised", "Pressure": "scarcity", "Position": "lane"},
        rolling_state=prior,
        custom_world_setup={
            "worldExclusions": "firearms",
            "want": "knowledge",
            "whoMatters": "nobody",
            "pressures": ["scarcity"],
            "startingLocation": "small_settlement",
        },
    )
    parsed, raw, receipt = server._build_fail_forward_parsed_turn(
        session,
        "Ask Harwood for a pistol",
        first_kind="coherence",
        first_reason="unknown person",
        second_kind="coherence",
        second_reason="firearms",
    )
    assert receipt["validation_hard_fallback"] == "yes"
    assert "Harwood" not in parsed.narrative
    assert "pistol" not in parsed.narrative.lower()
    assert "firearm" not in parsed.narrative.lower()
    # Freeform invalid action text must not re-enter player prose
    assert "Ask Harwood" not in parsed.narrative
    assert parsed.rolling_state["scene"] == prior["scene"]
    assert parsed.rolling_state["character"] == prior["character"]
    assert parsed.rolling_state["active_pressures"][0]["label"] == "scarcity"
    assert parsed.rolling_state["npcs"][0]["name"] == "Mira"
    labels = {c["label"] for c in parsed.choices}
    assert labels == {"A", "B", "C", "D"}
    blob = " ".join(c["text"] for c in parsed.choices).lower()
    assert "satchel" in blob or "well" in blob
    assert "mira" in blob
    assert "scarcity" in blob
    assert "Harwood" not in blob
    assert "pistol" not in blob
    # Merge must not drop prior when fallback rolling is prior copy
    merged = consolidate_rolling_state(prior, parsed.rolling_state)
    assert merged["scene"] == prior["scene"]
    assert merged["active_pressures"][0]["label"] == "scarcity"


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


def test_hard_violation_twice_uses_fail_forward_not_best_available():
    """First unknown person, retry forbidden firearm — neither committed."""
    prior = {
        "scene": "small settlement lane",
        "character": "a weary scholar",
        "active_pressures": [{"id": "scar", "label": "scarcity", "status": "active"}],
        "inventory_objects": [{"object": "satchel"}],
        "object_locations": [{"object": "well", "location": "lane"}],
        "npcs": [{"name": "Mira", "alive": True}],
    }
    session = {
        "id": "sess-hard-ff",
        "genre": "fantasy",
        "role": "a scholar",
        "tone": "grim",
        "difficulty": "hard",
        "mode": "basic",
        "turn_count": 2,
        "last_state": {"Health": "stable", "Pressure": "scarcity", "Position": "lane"},
        "rolling_state": copy.deepcopy(prior),
        "custom_world_setup": {
            "creationFlow": "guided",
            "want": "knowledge",
            "fear": "failure",
            "whoMatters": "nobody",
            "pressures": ["scarcity"],
            "startingLocation": "small_settlement",
            "worldExclusions": "firearms",
            "settingGroundedness": "mostly_grounded",
        },
    }

    first_raw = _turn_xml(
        "Rain streaks the lane. You clutch your satchel near the well.",
        [
            "Ask Harwood for directions out of town",
            "Check the well carefully",
            "Watch Mira closely",
            "Hold position and wait",
        ],
        {
            **prior,
            "npcs": prior["npcs"] + [{"name": "Harwood", "alive": True}],
            "character": "a frontline soldier",
            "scene": "enemy trenches",
        },
    )
    second_raw = _turn_xml(
        "You draw a shotgun from nowhere and fire at the crowd.",
        [
            "Fire the shotgun at the crowd",
            "Reload the pistol quickly",
            "Throw a grenade toward the ridge",
            "Sprint for the jeep",
        ],
        {
            **prior,
            "active_pressures": [],  # model tries to erase pressure
            "character": "a gunslinger",
            "scene": "neon arcade",
        },
    )

    calls = {"n": 0}

    async def fake_generate(*_a, **_k):
        calls["n"] += 1
        return first_raw, {
            "model_used": "test-model",
            "model_requested": "test-model",
            "telemetry": {},
            "fallback_events": [],
            "prose_mode": "standard",
            "prose_mode_requested": "standard",
            "prose_budget": 1200,
        }

    async def fake_invoke(**_k):
        calls["n"] += 1
        return {
            "content": second_raw,
            "model_used": "test-model",
            "model_requested": "test-model",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {"test-model": 1},
        }

    async def fake_messages(*_a, **_k):
        return [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}]

    async def fake_settings():
        return {
            "model": "test-model",
            "default_mode": "basic",
            "memory_depth": 4,
            "history_window": 6,
            "cost_mode": "normal",
            "max_tokens": 800,
            "temperature": 0.7,
            "developer_mode": False,
        }

    import gateway as _gw

    orig_gen = server._generate_turn
    orig_invoke = _gw.invoke_llm
    orig_msgs = server._build_messages
    orig_settings = server.get_ai_settings
    server._generate_turn = fake_generate
    _gw.invoke_llm = fake_invoke
    server._build_messages = fake_messages
    server.get_ai_settings = fake_settings
    try:
        parsed, raw, meta = _run_async(
            server._generate_validated_turn(
                session,
                "[DEV_MODE: OFF]\n\nPlayer action: ask around",
                player_action="ask around",
            )
        )
    finally:
        server._generate_turn = orig_gen
        _gw.invoke_llm = orig_invoke
        server._build_messages = orig_msgs
        server.get_ai_settings = orig_settings

    assert calls["n"] == 2  # exactly one retry
    assert meta.get("validation_retried") is True
    assert meta.get("validation_hard_fallback") is True
    assert meta.get("validation_discarded_invalid_model_output") is True
    assert "Harwood" not in parsed.narrative
    assert "shotgun" not in parsed.narrative.lower()
    assert "pistol" not in (parsed.narrative + " ".join(c["text"] for c in parsed.choices)).lower()
    assert "Harwood" not in " ".join(c["text"] for c in parsed.choices)
    # Invalid rolling mutations discarded
    assert parsed.rolling_state["scene"] == prior["scene"]
    assert parsed.rolling_state["character"] == prior["character"]
    assert parsed.rolling_state["active_pressures"][0]["label"] == "scarcity"
    assert all(n.get("name") != "Harwood" for n in parsed.rolling_state.get("npcs") or [])
    assert parsed.debug and parsed.debug.get("validation_hard_fallback") == "yes"
    # Session continues with grounded choices
    assert len(parsed.choices) >= 4
    assert {c["label"] for c in parsed.choices} >= {"A", "B", "C", "D"}


def test_soft_failure_both_still_uses_best_available():
    """Soft prose/choice defects may still take the best-available path."""
    long_choice = " ".join(["carefully"] * 35)
    prior = {
        "scene": "lane",
        "character": "a scholar",
        "active_pressures": [{"label": "scarcity"}],
        "inventory_objects": [{"object": "satchel"}],
    }
    session = {
        "id": "sess-soft",
        "genre": "fantasy",
        "role": "a scholar",
        "tone": "grim",
        "difficulty": "standard",
        "mode": "basic",
        "turn_count": 3,
        "last_state": {"Health": "stable", "Pressure": "scarcity"},
        "rolling_state": copy.deepcopy(prior),
        "custom_world_setup": {
            "want": "knowledge",
            "whoMatters": "nobody",
            "pressures": ["scarcity"],
            "startingLocation": "small_settlement",
        },
    }
    first_raw = _turn_xml(
        "You stand in the lane with your satchel.",
        ["Look around", "Check the satchel", "Listen nearby", "Wait"],
        prior,
    )
    second_choices = [
        long_choice,
        "Check the satchel again carefully",
        "Listen for footsteps on stone",
        "Wait beside the well",
        "Sit quietly a moment",
    ]
    second_raw = _turn_xml(
        "You stand in the lane with your satchel. Dust drifts.",
        second_choices,
        prior,
    )

    async def fake_generate(*_a, **_k):
        return first_raw, {
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "prose_mode": "standard",
            "prose_mode_requested": "standard",
            "prose_budget": 1200,
        }

    async def fake_invoke(**_k):
        return {
            "content": second_raw,
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    async def fake_messages(*_a, **_k):
        return [{"role": "user", "content": "x"}]

    async def fake_settings():
        return {
            "model": "test",
            "default_mode": "basic",
            "memory_depth": 4,
            "history_window": 6,
            "cost_mode": "normal",
            "max_tokens": 800,
            "temperature": 0.7,
            "developer_mode": False,
        }

    import gateway as _gw

    def soft_fail(_parsed, _sess, _action, early_game_stage=None):
        return False, "choice too long (40 words; max 28)", "coherence"

    orig_gen = server._generate_turn
    orig_invoke = _gw.invoke_llm
    orig_msgs = server._build_messages
    orig_val = server._full_validate
    orig_settings = server.get_ai_settings
    server._generate_turn = fake_generate
    _gw.invoke_llm = fake_invoke
    server._build_messages = fake_messages
    server._full_validate = soft_fail
    server.get_ai_settings = fake_settings
    try:
        parsed, raw, meta = _run_async(
            server._generate_validated_turn(
                session,
                "Player action: look",
                player_action="look",
            )
        )
    finally:
        server._generate_turn = orig_gen
        _gw.invoke_llm = orig_invoke
        server._build_messages = orig_msgs
        server._full_validate = orig_val
        server.get_ai_settings = orig_settings

    assert meta.get("validation_retried") is True
    assert not meta.get("validation_hard_fallback")
    # Best-available: more choices on retry
    assert len(parsed.choices) == 5
    assert "Dust drifts" in parsed.narrative or "carefully" in parsed.choices[0]["text"]


def test_fail_forward_is_deterministic_for_replay():
    session = _session(
        turn_count=2,
        role="a scout",
        last_state={"Health": "stable", "Pressure": "nightfall"},
        rolling_state={
            "scene": "ridge path",
            "character": "a scout",
            "active_pressures": [{"label": "nightfall"}],
            "inventory_objects": [{"object": "spear"}],
        },
        custom_world_setup={
            "want": "safety",
            "whoMatters": "nobody",
            "pressures": ["violence"],
            "startingLocation": "isolated_location",
        },
    )
    a = server._build_fail_forward_parsed_turn(
        session, "climb", first_kind="coherence", first_reason="x", second_kind="coherence", second_reason="y"
    )
    b = server._build_fail_forward_parsed_turn(
        session, "climb", first_kind="coherence", first_reason="x", second_kind="coherence", second_reason="y"
    )
    assert a[0].narrative == b[0].narrative
    assert a[0].choices == b[0].choices
    assert a[0].rolling_state == b[0].rolling_state
    # Compaction/merge cannot revive discarded invalid facts (never present)
    merged = consolidate_rolling_state(session["rolling_state"], a[0].rolling_state)
    assert "Harwood" not in str(merged)
    assert "shotgun" not in str(merged).lower()
