"""Ch 14 P1 — turn-path integration tests (run on a clean local checkout)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import stress


def test_consolidation_clobber_protection():
    """A model-supplied actor_stress cannot replace engine-owned stress."""
    engine = {"npc-a": {"stress_level": 41.0, "capacity": 1.0, "schema_version": 1}}
    merged = {"actor_stress": {"npc-a": {"stress_level": 0.0}}}  # malicious/LLM value
    notes = stress.enforce_authoritative_stress(merged, engine)
    assert merged["actor_stress"] == engine
    assert "actor_stress_model_mutation_stripped" in notes


def test_prepare_action_turn_emits_stress_before_snapshot():
    """Real turn: stress is updated and reaches the foundation snapshot inputs."""
    import replayability
    import foundation_snapshot

    run_seed = "seed-itest"
    rolling = {"npcs": [{"npc_id": "npc-a", "name": "Mara"}]}
    replay = {
        "run_seed": run_seed,
        "pressure_graph": {"nodes": [{"id": "p1", "status": "active", "magnitude": 60}]},
        "npc_agendas": {"agendas": [{"npc_id": "npc-a", "goal_kind": "escape_danger"}]},
    }
    state, _dirs, _diag, _thr, working_rolling = replayability.prepare_action_turn(
        replay, turn_number=2, rolling_state=rolling
    )
    assert working_rolling["actor_stress"]["npc-a"]["stress_level"] > 0.0
    snap = foundation_snapshot.FoundationTurnSnapshot.build(
        run_seed=run_seed,
        turn_sequence=2,
        rolling_state=working_rolling,
        replayability_state=state,
    )
    ref = next(r for r in snap.utility_input_refs if r["actor_id"] == "npc-a")
    assert ref["stress_level"] == working_rolling["actor_stress"]["npc-a"]["stress_level"]
