import copy
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import investigation_engine
import memory_retrieval
import replayability
import server
import simulate_world
from foundation_snapshot import FoundationTurnSnapshot

FIXED_SEED = "investigation-seed"


def _state(*, world_events=None, investigations=None, evidence=None, engine_events=None, goals=None, actions=None):
    return {
        "run_seed": FIXED_SEED,
        "pressure_graph": {"nodes": [], "foreground_node_id": None, "evolution_receipts": []},
        "engine_world_events": copy.deepcopy(list(engine_events or [])),
        "world_events": copy.deepcopy(list(world_events or [])),
        "world_event_receipts": [],
        "evidence": copy.deepcopy(list(evidence or [])),
        "investigations": copy.deepcopy(list(investigations or [])),
        "investigation_receipts": [],
        "situations": [],
        "situation_receipts": [],
        "goals": copy.deepcopy(list(goals or [])),
        "goal_receipts": [],
        "npc_actions": copy.deepcopy(list(actions or [])),
        "npc_action_receipts": [],
        "world_state_consumed_event_ids": [],
        "world_state_receipts": [],
        "world_state_guard_receipts": [],
        "transition_receipts": [],
    }


def _world_event(event_id="we-case", *, severity=8, actors=None, location="market"):
    return {
        "world_event_id": event_id,
        "event_type": "investigation",
        "title": "Investigation",
        "severity": severity,
        "status": "active",
        "progress": 0,
        "created_turn": 2,
        "updated_turn": 2,
        "originating_pressure_ids": ["p-case"],
        "originating_situation_ids": [],
        "originating_goal_ids": [],
        "originating_action_ids": [],
        "affected_locations": [location],
        "affected_regions": [],
        "affected_factions": ["watch"],
        "affected_actor_ids": list(actors or ["guard-a"]),
        "evidence_refs": ["pressure:p-case"],
        "expiry": 20,
        "source_event_ids": ["p-case"],
        "dedupe_key": f"investigation:location:{location}",
        "last_reinforced_turn": 2,
        "inactive_turns": 0,
    }


def _npc_clue_event(action_id="act-find-clue", *, actor_id="guard-a", location="market", turn=4):
    return {
        "event_type": "npc_action_event",
        "event_kind": "npc_found_clue",
        "event_id": f"evt-{action_id}",
        "action_id": action_id,
        "actor_ids": [actor_id],
        "goal_id": "goal-case",
        "situation_id": "",
        "location_ids": [location],
        "turn": turn,
        "outcome": "success",
        "magnitude": 80,
        "tags": ["npc_action", "investigate", "success", "find_murderer"],
    }


def test_deterministic_evidence_creation_and_duplicate_suppression():
    state_a = _state(world_events=[_world_event()])
    state_b = copy.deepcopy(state_a)

    result_a = investigation_engine.evolve_investigations(state_a, {}, 3, run_seed=FIXED_SEED)
    result_b = investigation_engine.evolve_investigations(state_b, {}, 3, run_seed=FIXED_SEED)

    assert state_a["investigations"] == state_b["investigations"]
    assert state_a["evidence"] == state_b["evidence"]
    assert result_a["receipts"] == result_b["receipts"]
    assert len(state_a["investigations"]) == 1
    assert len(state_a["evidence"]) == 1
    assert state_a["evidence"][0]["source_event_ids"][0] == "we-case"

    again = investigation_engine.evolve_investigations(state_a, {}, 4, run_seed=FIXED_SEED)
    assert len(state_a["investigations"]) == 1
    assert len(state_a["evidence"]) == 1
    assert again["diagnostics"]["evidence_duplicate_suppressed"] >= 1


def test_progression_and_confidence_accumulation_from_npc_evidence():
    state = _state(world_events=[_world_event(severity=10)])
    investigation_engine.evolve_investigations(state, {}, 3, run_seed=FIXED_SEED)
    first_confidence = state["investigations"][0]["confidence"]
    state["engine_world_events"].append(_npc_clue_event())

    result = investigation_engine.evolve_investigations(state, {}, 4, run_seed=FIXED_SEED)

    assert result["diagnostics"]["evidence_created"] >= 1
    assert len(state["evidence"]) == 2
    assert state["investigations"][0]["confidence"] > first_confidence
    assert state["investigations"][0]["progress"] > 0

    stalled = investigation_engine.evolve_investigations(state, {}, 11, run_seed=FIXED_SEED)
    assert stalled["diagnostics"]["investigations_progressed"] >= 1
    assert state["investigations"][0]["status"] in {"active", "stalled"}


def test_replayability_goal_and_npc_integration_from_investigation():
    state = _state(world_events=[_world_event()])
    rolling = {
        "scene": "market",
        "npcs": [{"name": "Guard A", "npc_id": "guard-a", "location_id": "market"}],
    }

    updated, _, diagnostics, _, working = replayability.prepare_action_turn(
        state,
        3,
        rolling_state=rolling,
    )

    assert diagnostics["investigations_created"] == 1
    assert diagnostics["evidence_created"] == 1
    assert updated["investigations"]
    assert updated["goals"]
    assert working["active_investigations"][0]["known_evidence_count"] == 1
    assert "investigation_id" not in working["active_investigations"][0]

    updated2, _, diagnostics2, _, working2 = replayability.prepare_action_turn(
        updated,
        4,
        rolling_state=working,
    )

    assert diagnostics2["npc_actions_created"] >= 1
    assert updated2["npc_actions"][0]["action_type"] in {"investigate", "search"}
    assert working2["active_npc_actions"]


def test_prompt_safe_foundation_and_memory_retrieval_evidence_cues():
    state = _state(world_events=[_world_event(event_id="we-memory")])
    investigation_engine.evolve_investigations(state, {}, 3, run_seed=FIXED_SEED)
    investigation_id = state["investigations"][0]["investigation_id"]
    evidence_id = state["evidence"][0]["evidence_id"]
    rolling = {
        "scene": "market",
        "npcs": [{"name": "Guard A", "npc_id": "guard-a", "location_id": "market"}],
        "npc_memory": [
            {
                "name": "Guard A",
                "remembers": [
                    {
                        "summary": "found a scratched lock",
                        "since_turn": 3,
                        "weight": "major",
                        "context": {
                            "investigation_ids": [investigation_id],
                            "evidence_ids": [evidence_id],
                        },
                    },
                    {
                        "summary": "heard unrelated gossip",
                        "since_turn": 3,
                        "weight": "major",
                        "context": {"evidence_ids": ["other"]},
                    },
                ],
            }
        ],
    }
    replayability.enforce_authoritative(rolling, state)

    safe = server._prompt_safe_rolling(
        {
            **rolling,
            "evidence": state["evidence"],
            "investigations": state["investigations"],
            "investigation_receipts": [{"receipt_id": "hidden"}],
            "active_investigations": [
                {
                    "investigation_id": "hidden",
                    "status": "active",
                    "priority": 8,
                    "confidence": 70,
                    "known_evidence_count": 1,
                    "case_status": "active",
                    "progress": 40,
                    "source_event_ids": ["hidden"],
                }
            ],
        }
    )

    assert "evidence" not in safe
    assert "investigations" not in safe
    assert "investigation_receipts" not in safe
    assert "investigation_id" not in safe["active_investigations"][0]
    assert "source_event_ids" not in safe["active_investigations"][0]

    snapshot = FoundationTurnSnapshot.build(
        run_seed=FIXED_SEED,
        turn_sequence=5,
        rolling_state=rolling,
        replayability_state=state,
    )
    assert snapshot.investigation_state_ref["investigations"][0]["investigation_id"] == investigation_id
    assert "source_event_ids" not in snapshot.investigation_state_ref["evidence"][0]
    ref = next(row for row in snapshot.utility_input_refs if row["actor_id"] == "guard-a")
    assert ref["active_investigation_ids"] == [investigation_id]
    assert ref["known_evidence_ids"] == [evidence_id]
    assert 0.0 <= ref["evidence_confidence"] <= 1.0

    prepared = memory_retrieval.evaluate_memory_retrieval(
        snapshot,
        actor_resolution={"tiers_by_actor_id": {"guard-a": "hero"}, "acting_actor_ids": ["guard-a"]},
        gravity={},
        rolling_state=rolling,
    )
    trace = next(row for row in prepared["retrieval_traces"] if row["actor_id"] == "guard-a")
    assert trace["candidate_count"] == 1
    assert trace["investigation_ids"] == [investigation_id]
    assert trace["evidence_ids"] == [evidence_id]
    assert prepared["investigation_context"]["active"][0]["known_evidence_count"] == 1


def test_simulation_harness_reports_investigation_metrics(tmp_path):
    summary = simulate_world.run_simulation(
        turns=30,
        seed="investigation-short",
        out_dir=tmp_path / "investigation_short",
    )

    assert "active_investigations" in summary["final_metrics"]
    assert "active_evidence" in summary["final_metrics"]
    assert summary["anomaly_counts"].get("duplicate_id", 0) == 0
    assert summary["anomaly_counts"].get("orphan_evidence", 0) == 0
    assert summary["anomaly_counts"].get("orphan_investigation", 0) == 0
    assert summary["anomaly_counts"].get("evidence_cycle", 0) == 0
