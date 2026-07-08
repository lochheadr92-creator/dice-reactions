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


def _social_snapshot(*, rolling=None, replayability=None, turn=4):
    rolling_state = rolling or {
        "scene": "dock",
        "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "dock"}],
    }
    replay = {
        "run_seed": "utility-seed",
        "pressure_graph": {"nodes": [], "foreground_node_id": None},
        **(replayability or {}),
    }
    return FoundationTurnSnapshot.build(
        run_seed="utility-seed",
        turn_sequence=turn,
        rolling_state=rolling_state,
        replayability_state=replay,
    )


def _visible_information_item(
    information_id="info-rumour",
    *,
    summary="raid warning",
    gravity=80,
    location_id="dock",
):
    return {
        "information_id": information_id,
        "information_type": "rumour",
        "summary": summary,
        "source_event_ids": ["evt-rumour"],
        "subject_refs": [{"subject_type": "location", "subject_id": location_id}],
        "known_by": [{"scope_type": "settlement", "scope_id": location_id}],
        "observer_access": [
            {
                "access_type": "local_community",
                "scope_type": "settlement",
                "scope_id": location_id,
                "source_event_ids": ["evt-rumour"],
                "reliability": 80,
                "distortion_level": 4,
                "acquired_at": {"turn": 3},
            }
        ],
        "reliability": 80,
        "reliability_band": "high",
        "distortion_level": 4,
        "visibility_scope": "settlement",
        "gravity": gravity,
        "created_at": {"turn": 3},
        "updated_at": {"turn": 3},
    }


def test_relationship_resentment_boosts_pressure_and_changes_selection():
    actor_resolution = {"acting_actor_ids": ["g1"], "tiers_by_actor_id": {"g1": "hero"}}
    candidates = [
        _candidate("g1", action_kind="negotiate", target_kind="player", target_id="player"),
        _candidate("g1", action_kind="pressure", target_kind="player", target_id="player"),
    ]
    resentful = _social_snapshot(
        rolling={
            "scene": "dock",
            "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "dock"}],
            "relationship_vectors": [
                {"name": "Guard", "npc_id": "g1", "trust": -20, "loyalty": 10, "fear": 10, "resentment": 85}
            ],
        }
    )
    trusting = _social_snapshot(
        rolling={
            "scene": "dock",
            "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "dock"}],
            "relationship_vectors": [
                {"name": "Guard", "npc_id": "g1", "trust": 85, "loyalty": 70, "fear": 5, "resentment": 5}
            ],
        }
    )

    resentful_result = utility_ai.select_action(candidates, snapshot=resentful, actor_resolution=actor_resolution)
    trusting_result = utility_ai.select_action(candidates, snapshot=trusting, actor_resolution=actor_resolution)

    resent_pressure = _score_row(resentful_result, actor_id="g1", action_kind="pressure")
    resent_negotiate = _score_row(resentful_result, actor_id="g1", action_kind="negotiate")
    trust_negotiate = _score_row(trusting_result, actor_id="g1", action_kind="negotiate")
    assert resent_pressure["relationship_modifier"] > 0
    assert "resentment" in resent_pressure["relationship_signals"]
    assert trust_negotiate["relationship_modifier"] > 0
    assert "trust_positive" in trust_negotiate["relationship_signals"]
    assert resentful_result["selected_action_kind"] == "pressure"
    assert trusting_result["selected_action_kind"] == "negotiate"
    assert resent_negotiate["base_utility"] < trust_negotiate["base_utility"]


def test_reputation_dangerous_boosts_avoid_over_negotiate():
    actor_resolution = {"acting_actor_ids": ["g1"], "tiers_by_actor_id": {"g1": "hero"}}
    candidates = [
        _candidate("g1", action_kind="avoid", target_kind="player", target_id="player"),
        _candidate("g1", action_kind="negotiate", target_kind="player", target_id="player"),
    ]
    baseline = _social_snapshot()
    dangerous = _social_snapshot(
        replayability={
            "reputation_signals": [
                {
                    "signal_id": "rep-danger-player",
                    "subject_type": "actor",
                    "subject_id": "player",
                    "dimension": "dangerous",
                    "score": 60,
                    "observer_scope": {"scope_type": "public", "scope_id": "public"},
                    "confidence": 80,
                    "reliability": 80,
                }
            ]
        }
    )

    baseline_result = utility_ai.select_action(candidates, snapshot=baseline, actor_resolution=actor_resolution)
    dangerous_result = utility_ai.select_action(candidates, snapshot=dangerous, actor_resolution=actor_resolution)

    assert "reputation_modifier" not in _score_row(baseline_result, actor_id="g1", action_kind="avoid")
    avoid_row = _score_row(dangerous_result, actor_id="g1", action_kind="avoid")
    negotiate_row = _score_row(dangerous_result, actor_id="g1", action_kind="negotiate")
    assert avoid_row["reputation_modifier"] > 0
    assert negotiate_row["reputation_modifier"] < 0
    assert dangerous_result["selected_action_kind"] == "avoid"


def test_information_rumour_boosts_investigate():
    actor_resolution = {"acting_actor_ids": ["g1"], "tiers_by_actor_id": {"g1": "hero"}}
    candidates = [
        _candidate("g1", action_kind="investigate"),
        _candidate("g1", action_kind="idle"),
    ]
    baseline = _social_snapshot()
    informed = _social_snapshot(
        replayability={"information_items": [_visible_information_item()]},
    )

    baseline_result = utility_ai.select_action(candidates, snapshot=baseline, actor_resolution=actor_resolution)
    informed_result = utility_ai.select_action(candidates, snapshot=informed, actor_resolution=actor_resolution)

    assert "information_modifier" not in _score_row(baseline_result, actor_id="g1", action_kind="investigate")
    investigate_row = _score_row(informed_result, actor_id="g1", action_kind="investigate")
    assert investigate_row["information_modifier"] > 0
    assert investigate_row["information_ids"]
    assert informed_result["selected_action_kind"] == "investigate"


def test_investigation_evidence_boosts_investigate():
    actor_resolution = {"acting_actor_ids": ["g1"], "tiers_by_actor_id": {"g1": "hero"}}
    candidates = [
        _candidate("g1", action_kind="investigate"),
        _candidate("g1", action_kind="gather"),
    ]
    baseline = _social_snapshot()
    investigating = _social_snapshot(
        replayability={
            "evidence": [
                {
                    "evidence_id": "ev-clue",
                    "evidence_type": "physical_clue",
                    "confidence": 85,
                    "reliability": 85,
                    "discovered_by": ["g1"],
                    "source_event_ids": ["evt-clue"],
                    "created_turn": 3,
                    "updated_turn": 3,
                }
            ],
            "investigations": [
                {
                    "investigation_id": "inv-case",
                    "status": "active",
                    "confidence": 70,
                    "progress": 20,
                    "created_turn": 3,
                    "updated_turn": 3,
                    "evidence_ids": ["ev-clue"],
                    "assigned_actor_ids": ["g1"],
                }
            ],
        }
    )

    baseline_result = utility_ai.select_action(candidates, snapshot=baseline, actor_resolution=actor_resolution)
    investigating_result = utility_ai.select_action(
        candidates,
        snapshot=investigating,
        actor_resolution=actor_resolution,
    )

    assert "investigation_modifier" not in _score_row(baseline_result, actor_id="g1", action_kind="investigate")
    investigate_row = _score_row(investigating_result, actor_id="g1", action_kind="investigate")
    assert investigate_row["investigation_modifier"] > 0
    assert investigate_row["evidence_ids"] == ["ev-clue"]
    assert investigate_row["investigation_ids"] == ["inv-case"]
    assert investigating_result["selected_action_kind"] == "investigate"


def test_social_collision_absent_keeps_legacy_scores():
    actor_resolution = {"acting_actor_ids": ["g1"], "tiers_by_actor_id": {"g1": "hero"}}
    candidates = [_candidate("g1", action_kind="investigate")]
    baseline = utility_ai.select_action(
        candidates,
        snapshot=_social_snapshot(),
        actor_resolution=actor_resolution,
    )
    unrelated = utility_ai.select_action(
        candidates,
        snapshot=_social_snapshot(
            rolling={
                "scene": "dock",
                "npcs": [{"name": "Other", "npc_id": "g2", "location_id": "castle"}],
                "relationship_vectors": [
                    {"name": "Other", "npc_id": "g2", "trust": 90, "loyalty": 90, "fear": 0, "resentment": 90}
                ],
            },
            replayability={
                "information_items": [_visible_information_item(location_id="castle")],
                "reputation_signals": [
                    {
                        "signal_id": "rep-other",
                        "subject_type": "actor",
                        "subject_id": "g2",
                        "dimension": "dangerous",
                        "score": 90,
                        "observer_scope": {"scope_type": "public", "scope_id": "public"},
                    }
                ],
            },
        ),
        actor_resolution=actor_resolution,
    )

    base_row = _score_row(baseline, actor_id="g1")
    unrelated_row = _score_row(unrelated, actor_id="g1")
    assert base_row["base_utility"] == unrelated_row["base_utility"] == 50.0
    for key in (
        "relationship_modifier",
        "reputation_modifier",
        "information_modifier",
        "investigation_modifier",
    ):
        assert key not in base_row
        assert key not in unrelated_row


def test_social_collision_bridge_replay_is_deterministic():
    snapshot = _social_snapshot(
        rolling={
            "scene": "dock",
            "npcs": [{"name": "Guard", "npc_id": "g1", "location_id": "dock"}],
            "relationship_vectors": [
                {"name": "Guard", "npc_id": "g1", "trust": 10, "loyalty": 20, "fear": 70, "resentment": 55}
            ],
        },
        replayability={
            "information_items": [_visible_information_item()],
            "reputation_signals": [
                {
                    "signal_id": "rep-suspicious-player",
                    "subject_type": "actor",
                    "subject_id": "player",
                    "dimension": "suspicious",
                    "score": 35,
                    "observer_scope": {"scope_type": "public", "scope_id": "public"},
                }
            ],
            "evidence": [
                {
                    "evidence_id": "ev-witness",
                    "evidence_type": "witness_statement",
                    "confidence": 75,
                    "reliability": 75,
                    "discovered_by": ["g1"],
                }
            ],
        },
    )
    candidates = [
        _candidate("g1", action_kind="investigate"),
        _candidate("g1", action_kind="avoid"),
        _candidate("g1", action_kind="negotiate", target_kind="player", target_id="player"),
    ]
    actor_resolution = {"acting_actor_ids": ["g1"], "tiers_by_actor_id": {"g1": "hero"}}

    first = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)
    second = utility_ai.select_action(candidates, snapshot=snapshot, actor_resolution=actor_resolution)

    assert first == second
