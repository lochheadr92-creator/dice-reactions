import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine_projection import forbid_player_projection, project_foundation_prepared


def test_score_table_not_in_player_projection():
    payload = {
        "utility_score_table": [{"actor_id": "a1"}],
        "retrieval_trace": [],
    }
    assert forbid_player_projection(payload) is not None


def test_bounded_projection_allows_safe_fields():
    bundle = {
        "snapshot_schema_version": 2,
        "actor_resolution": {"schema_version": 1, "acting_actor_ids": ["a1"], "tier_counts": {}, "source_state_hash": "x"},
        "gravity": {"schema_version": 1, "evaluated_count": 1, "overflow": False, "source_state_hash": "x"},
        "utility": {
            "schema_version": 2,
            "selected_actor_id": "a1",
            "selected_action_kind": "gather",
            "selected_target_kind": "pressure",
            "selected_target_id": "p1",
            "candidate_set_hash": "abc",
            "source_state_hash": "x",
        },
        "retrieval": {"schema_version": 1, "selected_memory_ids": [], "working_memory_size": 0, "shadow_mode": True, "source_state_hash": "x"},
    }
    proj = project_foundation_prepared(bundle)
    assert forbid_player_projection(proj) is None