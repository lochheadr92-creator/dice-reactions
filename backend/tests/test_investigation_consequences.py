import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import goal_engine
import information_engine
import investigation_engine
import replayability
import situation_engine
import utility_ai
from foundation_snapshot import FoundationTurnSnapshot

FIXED_SEED = "investigation-consequence-seed"


def _evidence(
    evidence_id="ev-clue",
    *,
    actor_ids=None,
    discovered_by=None,
    confidence=85,
    location_id="market",
):
    return {
        "evidence_id": evidence_id,
        "evidence_type": "physical_clue",
        "source_event_ids": ["evt-clue"],
        "discovered_turn": 3,
        "discovered_by": list(discovered_by or ["guard-a"]),
        "location_id": location_id,
        "actor_ids": list(actor_ids or ["suspect-a"]),
        "reliability": confidence,
        "confidence": confidence,
        "related_case_ids": ["inv-case"],
        "related_evidence_ids": [],
        "tags": ["world_event"],
        "archived": False,
    }


def _investigation(*, suspect_ids=None, assigned=None):
    return {
        "investigation_id": "inv-case",
        "situation_id": "s-murder",
        "status": "active",
        "priority": 7,
        "assigned_actor_ids": list(assigned or ["guard-a"]),
        "suspect_ids": list(suspect_ids or ["suspect-a"]),
        "evidence_ids": ["ev-clue"],
        "confidence": 75,
        "progress": 20,
        "created_turn": 3,
        "updated_turn": 3,
    }


def _situation():
    return {
        "situation_id": "s-murder",
        "type": "murder_investigation",
        "title": "Murder Investigation",
        "status": "active",
        "priority": 7,
        "severity": 7,
        "created_turn": 2,
        "updated_turn": 2,
        "originating_pressure_ids": [],
        "originating_world_event_ids": [],
        "involved_actor_ids": ["guard-a", "suspect-a"],
        "involved_locations": ["market"],
        "involved_factions": [],
        "objectives": ["gather_evidence"],
        "blockers": ["missing_evidence"],
        "evidence_refs": [],
        "progress": 10,
        "expiry": 20,
        "source_event_ids": ["s-murder"],
        "dedupe_key": "murder_investigation:location:market",
    }


def _replay_state(*, evidence=None, investigations=None, situations=None, goals=None, information=None):
    return {
        "run_seed": FIXED_SEED,
        "pressure_graph": {"nodes": [], "foreground_node_id": None, "evolution_receipts": []},
        "engine_world_events": [],
        "situations": copy.deepcopy(list(situations or [])),
        "situation_receipts": [],
        "goals": copy.deepcopy(list(goals or [])),
        "goal_receipts": [],
        "evidence": copy.deepcopy(list(evidence or [_evidence()])),
        "investigations": copy.deepcopy(list(investigations or [_investigation()])),
        "investigation_receipts": [],
        "information_items": copy.deepcopy(list(information or [])),
        "reputation_signals": [],
    }


def _public_evidence_information():
    return {
        "information_id": "info-ev-clue",
        "information_type": "evidence_summary",
        "summary": "physical_clue noted",
        "source_event_ids": ["ev-clue", "evt-clue"],
        "subject_refs": [
            {"subject_type": "evidence", "subject_id": "ev-clue"},
            {"subject_type": "npc", "subject_id": "suspect-a"},
            {"subject_type": "location", "subject_id": "market"},
        ],
        "known_by": [{"scope_type": "settlement", "scope_id": "market"}],
        "observer_access": [
            {
                "access_type": "local_community",
                "scope_type": "settlement",
                "scope_id": "market",
                "source_event_ids": ["ev-clue"],
                "reliability": 80,
                "distortion_level": 8,
                "acquired_at": {"turn": 4},
            }
        ],
        "reliability": 80,
        "reliability_band": "high",
        "distortion_level": 8,
        "visibility_scope": "settlement",
        "gravity": 7,
        "created_at": {"turn": 4},
        "updated_at": {"turn": 4},
    }


def _utility_snapshot(*, rolling, replayability):
    return FoundationTurnSnapshot.build(
        run_seed=FIXED_SEED,
        turn_sequence=5,
        rolling_state=rolling,
        replayability_state={"run_seed": FIXED_SEED, "pressure_graph": {"nodes": []}, **replayability},
    )


def _candidate(actor_id, action_kind):
    return {
        "actor_id": actor_id,
        "action_kind": action_kind,
        "target_kind": "player",
        "target_id": "player",
        "dimension_scores": {k: 50.0 for k in utility_ai.DIMENSION_ORDER},
        "personality_order": ["conceal", "withdraw", "investigate", "pressure", "negotiate", "idle"],
    }


def _score_row(result, *, actor_id, action_kind):
    for row in result["score_table"]:
        if row["actor_id"] == actor_id and row["action_kind"] == action_kind:
            return row
    raise AssertionError(f"missing score row {actor_id}:{action_kind}")


def test_implicated_suspect_gets_hide_evidence_goal():
    state = _replay_state()

    result = goal_engine.evolve_goals(state, {}, 5, run_seed=FIXED_SEED)

    hide_goals = [row for row in state["goals"] if row["goal_type"] == "hide_evidence"]
    assert len(hide_goals) >= 1
    assert hide_goals[0]["owner_id"] == "suspect-a"
    assert any(ref.startswith("evidence_exposure:") for ref in hide_goals[0]["evidence_refs"])
    assert result["receipts"][0]["receipt_type"] == "goal_created"


def test_investigating_actor_gets_find_murderer_goal():
    state = _replay_state()

    goal_engine.evolve_goals(state, {}, 5, run_seed=FIXED_SEED)

    find_goals = [row for row in state["goals"] if row["goal_type"] == "find_murderer"]
    assert len(find_goals) >= 1
    assert find_goals[0]["owner_id"] == "guard-a"


def test_implicated_suspect_prefers_conceal_over_investigate():
    rolling = {
        "scene": "market",
        "npcs": [
            {"name": "Suspect", "npc_id": "suspect-a", "location_id": "market"},
        ],
    }
    snapshot = _utility_snapshot(rolling=rolling, replayability=_replay_state())
    actor_resolution = {"acting_actor_ids": ["suspect-a"], "tiers_by_actor_id": {"suspect-a": "hero"}}
    candidates = [
        _candidate("suspect-a", "conceal"),
        _candidate("suspect-a", "investigate"),
    ]

    result = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)

    conceal = _score_row(result, actor_id="suspect-a", action_kind="conceal")
    investigate = _score_row(result, actor_id="suspect-a", action_kind="investigate")
    assert conceal["evidence_exposure_modifier"] > 0
    assert investigate["evidence_exposure_modifier"] < 0
    assert result["selected_action_kind"] == "conceal"


def test_public_exposure_boosts_withdraw_and_pressure_for_suspect():
    state = _replay_state(information=[_public_evidence_information()])
    rolling = {
        "scene": "market",
        "npcs": [{"name": "Suspect", "npc_id": "suspect-a", "location_id": "market"}],
    }
    snapshot = _utility_snapshot(rolling=rolling, replayability=state)
    actor_resolution = {"acting_actor_ids": ["suspect-a"], "tiers_by_actor_id": {"suspect-a": "hero"}}
    candidates = [
        _candidate("suspect-a", "withdraw"),
        _candidate("suspect-a", "pressure"),
        _candidate("suspect-a", "investigate"),
    ]

    result = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)

    withdraw = _score_row(result, actor_id="suspect-a", action_kind="withdraw")
    pressure = _score_row(result, actor_id="suspect-a", action_kind="pressure")
    assert withdraw["evidence_exposure_modifier"] > 0
    assert pressure["evidence_exposure_modifier"] > 0
    assert "implicated_public" in str(withdraw.get("evidence_exposure_signal_ids"))


def test_investigator_prefers_investigate_with_exposure():
    rolling = {
        "scene": "market",
        "npcs": [{"name": "Guard", "npc_id": "guard-a", "location_id": "market"}],
    }
    snapshot = _utility_snapshot(rolling=rolling, replayability=_replay_state())
    actor_resolution = {"acting_actor_ids": ["guard-a"], "tiers_by_actor_id": {"guard-a": "hero"}}
    candidates = [
        _candidate("guard-a", "investigate"),
        _candidate("guard-a", "idle"),
    ]

    result = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)

    investigate = _score_row(result, actor_id="guard-a", action_kind="investigate")
    assert investigate["evidence_exposure_modifier"] > 0
    assert result["selected_action_kind"] == "investigate"


def test_reputation_pressure_biases_avoid_after_evidence_spreads():
    state = _replay_state()
    information_engine.evolve_information(state, {}, 5, run_seed=FIXED_SEED)
    assert state["reputation_signals"]
    assert state["reputation_signals"][0]["dimension"] == "suspicious"
    state["reputation_signals"][0]["score"] = 60
    state["reputation_signals"][0]["confidence"] = 85
    state["reputation_signals"][0]["reliability"] = 85

    rolling = {
        "scene": "market",
        "npcs": [{"name": "Witness", "npc_id": "witness-b", "location_id": "market"}],
    }
    snapshot = _utility_snapshot(rolling=rolling, replayability=state)
    actor_resolution = {"acting_actor_ids": ["witness-b"], "tiers_by_actor_id": {"witness-b": "hero"}}
    candidates = [
        _candidate("witness-b", "avoid"),
        _candidate("witness-b", "negotiate"),
    ]
    candidates[0]["target_kind"] = "actor"
    candidates[0]["target_id"] = "suspect-a"
    candidates[1]["target_kind"] = "actor"
    candidates[1]["target_id"] = "suspect-a"

    result = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)

    avoid = _score_row(result, actor_id="witness-b", action_kind="avoid")
    negotiate = _score_row(result, actor_id="witness-b", action_kind="negotiate")
    assert avoid["reputation_modifier"] > 0
    assert negotiate["reputation_modifier"] < 0
    assert avoid["base_utility"] > negotiate["base_utility"]
    assert result["selected_action_kind"] == "avoid"


def test_promoted_situation_includes_evidence_exposure_behaviours():
    state = _replay_state(situations=[_situation()], information=[_public_evidence_information()])
    rolling = {"scene": "market", "npcs": []}

    promoted = situation_engine.project_promoted_situations_for_rolling(state, rolling_state=rolling)

    assert len(promoted) == 1
    row = promoted[0]
    assert row["evidence_exposure_signals"]
    assert row["evidence_exposure_behaviours"]
    assert "withdraw before exposure spreads" in row["evidence_exposure_behaviours"]
    assert any(
        label in row["player_opportunities"]
        for label in row["evidence_exposure_behaviours"]
    )


def test_evidence_exposure_utility_bridge_replay_is_deterministic():
    rolling = {
        "scene": "market",
        "npcs": [
            {"name": "Suspect", "npc_id": "suspect-a", "location_id": "market"},
            {"name": "Guard", "npc_id": "guard-a", "location_id": "market"},
        ],
    }
    replayability = _replay_state(information=[_public_evidence_information()])
    snapshot = _utility_snapshot(rolling=rolling, replayability=replayability)
    candidates = [
        _candidate("suspect-a", "conceal"),
        _candidate("suspect-a", "withdraw"),
        _candidate("guard-a", "investigate"),
        _candidate("guard-a", "pressure"),
    ]
    actor_resolution = {
        "acting_actor_ids": ["suspect-a", "guard-a"],
        "tiers_by_actor_id": {"suspect-a": "hero", "guard-a": "hero"},
    }

    first = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)
    second = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)

    assert first == second


def test_exposure_goals_remain_in_replayability_state():
    state = _replay_state()
    rolling = {"scene": "market", "npcs": []}

    goal_engine.evolve_goals(state, {}, 5, run_seed=FIXED_SEED)
    replayability.enforce_authoritative(rolling, state)

    assert state["goals"]
    assert "goals" not in rolling
    assert rolling["active_goals"]
    assert any(row["title"] == "Hide Evidence" for row in rolling["active_goals"])


def test_foundation_snapshot_exposes_evidence_exposure_refs():
    rolling = {
        "scene": "market",
        "npcs": [{"name": "Suspect", "npc_id": "suspect-a", "location_id": "market"}],
    }
    snapshot = _utility_snapshot(rolling=rolling, replayability=_replay_state())

    ref = snapshot.utility_input_refs[0]
    assert "implicated_private" in ref["evidence_exposure_kinds"]
    assert ref["evidence_exposure_behaviours"]