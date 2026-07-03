import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import utility_ai
from foundation_snapshot import FoundationTurnSnapshot


def _snapshot(turn=3, *, pressure_nodes=None, rolling=None, foreground_node_id=None):
    rolling_state = rolling or {"npcs": [{"name": "A", "npc_id": "a1", "stance": "ally"}]}
    return FoundationTurnSnapshot.build(
        run_seed="utility-seed",
        turn_sequence=turn,
        rolling_state=rolling_state,
        replayability_state={
            "run_seed": "utility-seed",
            "pressure_graph": {
                "nodes": list(pressure_nodes or []),
                "foreground_node_id": foreground_node_id,
            },
        },
    )


def _candidate(actor_id="a1", action_kind="investigate", target_kind="player", target_id="player"):
    return {
        "actor_id": actor_id,
        "action_kind": action_kind,
        "target_kind": target_kind,
        "target_id": target_id,
        "dimension_scores": {k: 50.0 for k in utility_ai.DIMENSION_ORDER},
        "personality_order": ["investigate", "gather", "idle", "confront", "avoid"],
    }


def _score_row(result, *, actor_id="a1", action_kind="investigate"):
    for row in result["score_table"]:
        if row["actor_id"] == actor_id and row["action_kind"] == action_kind:
            return row
    raise AssertionError(f"missing score row {actor_id}:{action_kind}")


def test_weighted_average_formula():
    scores = {
        "survival": 80.0,
        "goal_progression": 60.0,
        "pressure_relief": 40.0,
        "stress_reduction": 20.0,
        "relationship_impact": 50.0,
        "resource_gain_loss": 30.0,
        "memory_avoidance": 10.0,
    }
    weights = utility_ai.compute_dimension_weights()
    utility = utility_ai.compute_utility_score(scores, weights)
    assert 0.0 <= utility <= 100.0


def test_noise_reproducible():
    material = "run_seed=s|turn=1|subsystem=utility_ai|actor_id=a1|candidate_set=x|rng_v=1|seed_schema_v=1"
    n1 = utility_ai.apply_whim_noise(50.0, seed_material=material, draw_index=0)
    n2 = utility_ai.apply_whim_noise(50.0, seed_material=material, draw_index=0)
    assert n1 == n2


def test_tie_window_prefers_personality_order():
    snapshot = _snapshot()
    actor_resolution = {
        "acting_actor_ids": ["a1", "a2"],
        "tiers_by_actor_id": {"a1": "hero", "a2": "hero"},
    }
    candidates = []
    for actor_id, action in (("a1", "gather"), ("a2", "gather")):
        candidates.append(
            {
                "actor_id": actor_id,
                "action_kind": action,
                "target_kind": "player",
                "target_id": "player",
                "dimension_scores": {k: 50.0 for k in utility_ai.DIMENSION_ORDER},
                "personality_order": ["gather", "protect"],
            }
        )
    result = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)
    assert result["selected"] is not None


def test_ineligible_actor_excluded():
    snapshot = _snapshot()
    actor_resolution = {"acting_actor_ids": [], "tiers_by_actor_id": {"a1": "archived"}}
    result = utility_ai.select_action(
        [
            {
                "actor_id": "a1",
                "action_kind": "gather",
                "target_kind": "player",
                "target_id": "player",
                "dimension_scores": {"survival": 90.0},
            }
        ],
        snapshot=snapshot,
        actor_resolution=actor_resolution,
    )
    assert result["selected"] is None


def test_pressure_modifies_scores_without_selecting_directly():
    snapshot = _snapshot(
        pressure_nodes=[
            {
                "id": "p-danger",
                "kind": "danger",
                "status": "active",
                "magnitude": 100,
                "actor_ids": ["a1"],
            }
        ]
    )
    actor_resolution = {"acting_actor_ids": ["a1"], "tiers_by_actor_id": {"a1": "hero"}}
    result = utility_ai.select_action(
        [
            _candidate(action_kind="investigate"),
            _candidate(action_kind="idle"),
        ],
        snapshot=snapshot,
        actor_resolution=actor_resolution,
    )

    investigate = _score_row(result, action_kind="investigate")
    idle = _score_row(result, action_kind="idle")
    assert investigate["pressure_modifier"] == 4.0
    assert idle["pressure_modifier"] == -3.0
    assert investigate["base_utility"] > 50.0
    assert idle["base_utility"] < 50.0
    assert result["selected_action_kind"] in {"investigate", "idle"}


def test_pressure_absent_keeps_legacy_scores_and_output_shape():
    actor_resolution = {"acting_actor_ids": ["a1"], "tiers_by_actor_id": {"a1": "hero"}}
    candidates = [_candidate()]
    baseline = utility_ai.select_action(
        candidates,
        snapshot=_snapshot(),
        actor_resolution=actor_resolution,
    )
    unrelated = utility_ai.select_action(
        candidates,
        snapshot=_snapshot(
            pressure_nodes=[
                {
                    "id": "p-other",
                    "kind": "danger",
                    "status": "active",
                    "magnitude": 100,
                    "actor_ids": ["someone-else"],
                }
            ]
        ),
        actor_resolution=actor_resolution,
    )

    base_row = _score_row(baseline)
    unrelated_row = _score_row(unrelated)
    assert base_row["base_utility"] == unrelated_row["base_utility"] == 50.0
    assert base_row["noisy_utility"] == unrelated_row["noisy_utility"]
    assert baseline["state_hash"] == unrelated["state_hash"]
    assert "pressure_modifier" not in base_row
    assert "pressure_modifier" not in unrelated_row


def test_multiple_pressures_combine_deterministically_with_total_cap():
    nodes = [
        {
            "id": f"p-danger-{idx}",
            "kind": "danger",
            "origin_type": "structured_event",
            "origin_id": f"evt-{idx}",
            "scope": "local",
            "status": "active",
            "magnitude": 100,
        }
        for idx in range(6)
    ]
    snapshot = _snapshot(pressure_nodes=nodes)
    first = utility_ai.pressure_score_modifier(snapshot, actor_id="a1", action_kind="investigate")
    second = utility_ai.pressure_score_modifier(snapshot, actor_id="a1", action_kind="investigate")

    assert first == second
    assert first["modifier"] == utility_ai.MAX_PRESSURE_TOTAL_SCORE_MODIFIER
    assert len(first["node_ids"]) == utility_ai.MAX_PRESSURE_NODES_PER_UTILITY_ACTOR


def test_actor_specific_pressure_filtering():
    rolling = {
        "npcs": [
            {"name": "A", "npc_id": "a1", "stance": "ally"},
            {"name": "B", "npc_id": "a2", "stance": "ally"},
        ]
    }
    snapshot = _snapshot(
        rolling=rolling,
        pressure_nodes=[
            {
                "id": "p-a2",
                "kind": "danger",
                "status": "active",
                "magnitude": 100,
                "actor_ids": ["a2"],
            }
        ],
    )
    result = utility_ai.select_action(
        [_candidate("a1"), _candidate("a2")],
        snapshot=snapshot,
        actor_resolution={"acting_actor_ids": ["a1", "a2"], "tiers_by_actor_id": {"a1": "hero", "a2": "hero"}},
    )

    assert "pressure_modifier" not in _score_row(result, actor_id="a1")
    assert _score_row(result, actor_id="a2")["pressure_modifier"] == 4.0


def test_region_specific_pressure_filtering():
    snapshot = _snapshot(
        rolling={"scene": "market", "npcs": [{"name": "A", "npc_id": "a1", "last_seen": "market"}]},
        pressure_nodes=[
            {
                "id": "p-market",
                "kind": "opportunity",
                "status": "active",
                "magnitude": 50,
                "location_ids": ["market"],
            },
            {
                "id": "p-harbor",
                "kind": "opportunity",
                "status": "active",
                "magnitude": 100,
                "location_ids": ["harbor"],
            },
        ],
    )

    modifier = utility_ai.pressure_score_modifier(snapshot, actor_id="a1", action_kind="trade")
    assert modifier["modifier"] == 1.25
    assert modifier["node_ids"] == ["p-market"]


def test_evidence_refs_do_not_make_global_pressure_actor_specific():
    snapshot = _snapshot(
        pressure_nodes=[
            {
                "id": "p-evidence",
                "kind": "danger",
                "status": "active",
                "magnitude": 50,
                "evidence_refs": ["evt-opening"],
            }
        ],
    )

    modifier = utility_ai.pressure_score_modifier(snapshot, actor_id="a1", action_kind="investigate")
    assert modifier["modifier"] == 2.0
    assert modifier["node_ids"] == ["p-evidence"]


def test_faction_pressure_filtering():
    snapshot = _snapshot(
        rolling={"npcs": [{"name": "A", "npc_id": "a1", "faction_id": "guild"}]},
        pressure_nodes=[
            {
                "id": "p-guild",
                "kind": "social_tension",
                "status": "active",
                "magnitude": 80,
                "faction_ids": ["guild"],
            },
            {
                "id": "p-rival",
                "kind": "social_tension",
                "status": "active",
                "magnitude": 100,
                "faction_ids": ["rival"],
            },
        ],
    )

    modifier = utility_ai.pressure_score_modifier(snapshot, actor_id="a1", action_kind="pressure")
    assert modifier["modifier"] == 2.0
    assert modifier["node_ids"] == ["p-guild"]


def test_duplicate_pressure_nodes_do_not_double_count():
    duplicate_a = {
        "id": "p-dup-a",
        "kind": "danger",
        "origin_type": "structured_event",
        "origin_id": "same-event",
        "scope": "local",
        "status": "active",
        "magnitude": 100,
    }
    duplicate_b = dict(duplicate_a, id="p-dup-b")
    snapshot = _snapshot(pressure_nodes=[duplicate_a, duplicate_b])

    modifier = utility_ai.pressure_score_modifier(snapshot, actor_id="a1", action_kind="investigate")
    assert modifier["modifier"] == utility_ai.MAX_PRESSURE_NODE_SCORE_MODIFIER
    assert modifier["node_ids"] == ["p-dup-a"]


def test_resolved_pressure_no_longer_affects_utility_ai():
    snapshot = _snapshot(
        pressure_nodes=[
            {
                "id": "p-resolved",
                "kind": "danger",
                "status": "resolved",
                "magnitude": 100,
                "actor_ids": ["a1"],
            }
        ]
    )

    modifier = utility_ai.pressure_score_modifier(snapshot, actor_id="a1", action_kind="investigate")
    assert modifier["modifier"] == 0.0
    assert modifier["node_ids"] == []


def test_pressure_bridge_replay_decisions_are_identical():
    snapshot = _snapshot(
        pressure_nodes=[
            {"id": "p-danger", "kind": "danger", "status": "active", "magnitude": 70},
            {"id": "p-scarcity", "kind": "resource_pressure", "status": "active", "magnitude": 60},
        ]
    )
    candidates = [_candidate(action_kind="investigate"), _candidate(action_kind="gather")]
    actor_resolution = {"acting_actor_ids": ["a1"], "tiers_by_actor_id": {"a1": "hero"}}

    first = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)
    second = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)
    assert first == second
