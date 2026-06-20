import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import utility_ai
from foundation_acceptance.utility_oracle import inputs_complete
from foundation_snapshot import FoundationTurnSnapshot


def test_d_sel_blocked_without_stress_on_withdraw():
    snapshot = FoundationTurnSnapshot(
        schema_version=2,
        run_id="s",
        run_seed="s",
        turn_sequence=1,
        actor_registry=(),
        actor_resolution_inputs={},
        pressure_state_ref={"nodes": [{"id": "p1", "status": "active", "magnitude": 50}]},
        confirmed_consequence_refs=(),
        relationship_vector_ref={"vectors": []},
        agenda_refs=(),
        location_ref="",
        secret_access_facts=(),
        gravity_metadata={},
        utility_input_refs=(
            {
                "actor_id": "npc-a",
                "goal_kind": "escape_danger",
                "highest_pressure_intensity": 0.5,
                "resource_scarcity": 0.3,
                "relationship_importance": 5.0,
                "memory_signatures": (),
            },
        ),
        source_state_hash="x",
    )
    import npc_world_moves as world_moves

    bundle = utility_ai.build_canonical_dimension_bundle(
        snapshot,
        actor_id="npc-a",
        action_kind="withdraw",
        target_kind="location",
        aligned_goals=world_moves.MOVE_GOAL_ALIGN["withdraw"],
        relationship_deltas={},
    )
    assert bundle["replacement_authorised"] is False
    assert "MISSING_STRESS_LEVEL" in bundle["blocker_codes"]


def test_d_sel_authorised_on_complete_gather_fixture():
    fixture = {
        "action_kind": "gather",
        "goal_kind": "secure_resources",
        "highest_pressure_intensity": 0.8,
        "stress_level": 20.0,
        "resource_scarcity": 0.4,
    }
    assert inputs_complete(fixture) is True
    snapshot = FoundationTurnSnapshot(
        schema_version=2,
        run_id="s",
        run_seed="s",
        turn_sequence=2,
        actor_registry=(),
        actor_resolution_inputs={},
        pressure_state_ref={"nodes": [{"id": "p1", "status": "active", "magnitude": 80, "kind": "resource"}]},
        confirmed_consequence_refs=(),
        relationship_vector_ref={"vectors": []},
        agenda_refs=(),
        location_ref="",
        secret_access_facts=(),
        gravity_metadata={},
        utility_input_refs=(
            {
                "actor_id": "npc-a",
                "goal_kind": "secure_resources",
                "highest_pressure_intensity": 0.8,
                "stress_level": 20.0,
                "resource_scarcity": 0.4,
                "relationship_importance": 5.0,
                "memory_signatures": (),
            },
        ),
        source_state_hash="x",
    )
    import npc_world_moves as world_moves

    bundle = utility_ai.build_canonical_dimension_bundle(
        snapshot,
        actor_id="npc-a",
        action_kind="gather",
        target_kind="pressure",
        aligned_goals=world_moves.MOVE_GOAL_ALIGN["gather"],
        relationship_deltas={},
    )
    assert bundle["replacement_authorised"] is True