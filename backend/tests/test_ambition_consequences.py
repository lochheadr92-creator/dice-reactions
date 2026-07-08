import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import goal_engine
import npc_agendas
import replayability
import situation_engine
import utility_ai
from foundation_snapshot import FoundationTurnSnapshot

FIXED_SEED = "ambition-consequence-seed"


def _npc_record(name="Merchant", role="trader", slot=0):
    return {"name": name, "source_type": "seed_record", "source_slot": slot, "role": role}


def _agendas_state(*, goal_kind="secure_resources", plan_kind="gather", progress=35):
    seeded = npc_agendas.seed_agendas_from_npcs(FIXED_SEED, [_npc_record()])
    agenda = seeded["active"][0]
    agenda["goal_kind"] = goal_kind
    agenda["plan_kind"] = plan_kind
    agenda["progress"] = progress
    agenda["status"] = "active"
    return seeded


def _replay_state(*, agendas=None, situations=None):
    return {
        "run_seed": FIXED_SEED,
        "pressure_graph": {"nodes": [], "foreground_node_id": None, "evolution_receipts": []},
        "engine_world_events": [],
        "situations": copy.deepcopy(list(situations or [])),
        "situation_receipts": [],
        "goals": [],
        "goal_receipts": [],
        "npc_agendas": copy.deepcopy(agendas or _agendas_state()),
    }


def _rolling(*, npc_id):
    return {
        "scene": "market",
        "npcs": [{"name": "Merchant", "npc_id": npc_id, "location_id": "market"}],
    }


def _situation(*, npc_id):
    return {
        "situation_id": "s-trade",
        "type": "trade_opportunity",
        "title": "Trade Opportunity",
        "status": "active",
        "priority": 6,
        "severity": 6,
        "created_turn": 1,
        "updated_turn": 1,
        "originating_pressure_ids": [],
        "originating_world_event_ids": [],
        "involved_actor_ids": [npc_id],
        "involved_locations": ["market"],
        "involved_factions": [],
        "objectives": ["secure_trade"],
        "blockers": [],
        "evidence_refs": [],
        "progress": 0,
        "expiry": 20,
        "source_event_ids": ["s-trade"],
        "dedupe_key": "trade_opportunity:location:market",
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
        "personality_order": ["gather", "negotiate", "idle", "investigate"],
    }


def _score_row(result, *, actor_id, action_kind):
    for row in result["score_table"]:
        if row["actor_id"] == actor_id and row["action_kind"] == action_kind:
            return row
    raise AssertionError(f"missing score row {actor_id}:{action_kind}")


def test_ambition_progress_persists_across_turns():
    agendas = _agendas_state(progress=20)
    before = int(agendas["active"][0]["progress"])

    npc_agendas.tick_eligible_agendas(agendas, 5)
    npc_agendas.tick_eligible_agendas(agendas, 9)

    after = int(agendas["active"][0]["progress"])
    assert after > before
    assert agendas["active"][0]["goal_kind"] == "secure_resources"


def test_ambition_generates_secure_food_goal_for_npc():
    agendas = _agendas_state()
    npc_id = agendas["active"][0]["npc_id"]
    state = _replay_state(agendas=agendas)

    result = goal_engine.evolve_goals(state, _rolling(npc_id=npc_id), 5, run_seed=FIXED_SEED)

    food_goals = [
        row for row in state["goals"]
        if row["goal_type"] == "secure_food" and row["owner_id"] == npc_id
    ]
    assert len(food_goals) == 1
    assert any(ref.startswith("ambition:") for ref in food_goals[0]["evidence_refs"])
    assert result["receipts"][0]["receipt_type"] == "goal_created"


def test_ambition_reinforces_existing_goal_without_duplicate():
    agendas = _agendas_state()
    npc_id = agendas["active"][0]["npc_id"]
    state = _replay_state(agendas=agendas)
    rolling = _rolling(npc_id=npc_id)

    goal_engine.evolve_goals(state, rolling, 5, run_seed=FIXED_SEED)
    first_count = len(state["goals"])
    first_goal = copy.deepcopy(state["goals"][0])

    agendas["active"][0]["progress"] = 45
    second = goal_engine.evolve_goals(state, rolling, 6, run_seed=FIXED_SEED)

    assert len(state["goals"]) == first_count
    assert state["goals"][0]["goal_id"] == first_goal["goal_id"]
    assert second["diagnostics"]["goal_duplicate_suppressed"] >= 1


def test_ambition_biases_utility_toward_gather_for_resource_ambition():
    agendas = _agendas_state(goal_kind="secure_resources", plan_kind="gather", progress=40)
    npc_id = agendas["active"][0]["npc_id"]
    snapshot = _utility_snapshot(rolling=_rolling(npc_id=npc_id), replayability=_replay_state(agendas=agendas))
    actor_resolution = {"acting_actor_ids": [npc_id], "tiers_by_actor_id": {npc_id: "hero"}}
    candidates = [
        _candidate(npc_id, "gather"),
        _candidate(npc_id, "idle"),
    ]

    result = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)

    gather = _score_row(result, actor_id=npc_id, action_kind="gather")
    idle = _score_row(result, actor_id=npc_id, action_kind="idle")
    assert gather["ambition_modifier"] > 0
    assert idle["ambition_modifier"] < 0
    assert result["selected_action_kind"] == "gather"


def test_promoted_situation_includes_ambition_opportunities():
    agendas = _agendas_state(goal_kind="uncover_truth", plan_kind="investigate", progress=42)
    npc_id = agendas["active"][0]["npc_id"]
    state = _replay_state(agendas=agendas, situations=[_situation(npc_id=npc_id)])

    promoted = situation_engine.project_promoted_situations_for_rolling(
        state,
        rolling_state=_rolling(npc_id=npc_id),
    )

    assert len(promoted) == 1
    row = promoted[0]
    assert row["ambition_signals"]
    assert row["ambition_signals"][0]["ambition_kind"] == "uncover_truth"
    assert row["ambition_opportunities"]
    assert "follow a long-running truth hunt" in row["ambition_opportunities"]
    assert "follow a long-running truth hunt" in row["player_opportunities"]


def test_ambition_utility_bridge_replay_is_deterministic():
    agendas = _agendas_state(goal_kind="remove_rival", plan_kind="pressure", progress=50)
    npc_id = agendas["active"][0]["npc_id"]
    snapshot = _utility_snapshot(rolling=_rolling(npc_id=npc_id), replayability=_replay_state(agendas=agendas))
    candidates = [
        _candidate(npc_id, "pressure"),
        _candidate(npc_id, "negotiate"),
        _candidate(npc_id, "idle"),
    ]
    actor_resolution = {"acting_actor_ids": [npc_id], "tiers_by_actor_id": {npc_id: "hero"}}

    first = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)
    second = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)

    assert first == second


def test_ambition_goals_remain_in_replayability_state():
    agendas = _agendas_state()
    npc_id = agendas["active"][0]["npc_id"]
    state = _replay_state(agendas=agendas)
    rolling = _rolling(npc_id=npc_id)

    goal_engine.evolve_goals(state, rolling, 5, run_seed=FIXED_SEED)
    replayability.enforce_authoritative(rolling, state)

    assert state["goals"]
    assert "goals" not in rolling
    assert rolling["active_goals"]
    assert rolling["active_goals"][0]["title"] == "Earn Enough Food"


def test_foundation_snapshot_exposes_ambition_refs():
    agendas = _agendas_state()
    npc_id = agendas["active"][0]["npc_id"]
    snapshot = _utility_snapshot(rolling=_rolling(npc_id=npc_id), replayability=_replay_state(agendas=agendas))

    ref = snapshot.utility_input_refs[0]
    assert "secure_resources" in ref["ambition_kinds"]
    assert ref["ambition_signal_ids"]
    assert snapshot.agenda_refs
    assert snapshot.agenda_refs[0]["goal_kind"] == "secure_resources"