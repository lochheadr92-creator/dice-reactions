"""
Pressure Graph Lite v1 — causal movement, scoring, threshold policy.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pressure_graph  # noqa: E402
import run_identity  # noqa: E402
import opening_state  # noqa: E402

SEED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _identity(**over):
    base = run_identity.derive_run_identity(SEED, {
        "genre": "noir", "role": "d", "tone": "t", "difficulty": "standard",
        "scenario_id": None, "custom_premise": "", "custom_world_setup": {},
    })
    base.update(over)
    return base


def _opening(identity):
    return opening_state.select_opening_archetype(SEED, {"genre": "noir"}, identity=identity)


def _graph(identity=None):
    identity = identity or _identity()
    opening = _opening(identity)
    return pressure_graph.init_pressure_graph(SEED, identity, opening)


def _node(graph, idx=0):
    return graph["nodes"][idx]


def test_init_seeds_nodes_with_causal_schema():
    graph = _graph()
    node = _node(graph)
    for field in (
        "id", "kind", "origin", "origin_type", "origin_id", "scope",
        "magnitude", "trend", "trend_label", "status", "actor_ids",
        "location_ids", "faction_ids", "tags", "linked_node_ids",
        "linked_pressure_ids", "created_turn", "updated_turn",
        "last_foreground_turn", "age_turns", "last_evolved_turn",
        "spawned_event_ids", "threshold", "last_threshold", "evidence_refs",
    ):
        assert field in node


def test_neutral_pressure_does_not_rise():
    graph = _graph()
    node = _node(graph)
    node["trend"] = 0
    before = node["magnitude"]
    pressure_graph.tick_pressure_graph(graph, 2, identity=_identity())
    assert node["magnitude"] == before


def test_declining_pressure_falls_and_clamps():
    graph = _graph()
    node = _node(graph)
    node["trend"] = -1
    node["magnitude"] = 3
    pressure_graph.tick_pressure_graph(graph, 2, identity=_identity())
    assert node["magnitude"] == 0


def test_escalating_pressure_rises():
    graph = _graph()
    node = _node(graph)
    node["trend"] = 1
    before = node["magnitude"]
    pressure_graph.tick_pressure_graph(graph, 2, identity=_identity())
    assert node["magnitude"] > before


def test_foreground_has_no_magnitude_bonus_from_prior_selection():
    graph = _graph()
    a, b = graph["nodes"][0], graph["nodes"][1]
    a["trend"] = 0
    b["trend"] = 0
    a["magnitude"] = 50
    b["magnitude"] = 50
    a["last_foreground_turn"] = 1
    b["last_foreground_turn"] = None
    pressure_graph.select_foreground(graph, identity=_identity(), turn_number=2)
    assert graph["foreground_node_id"] == b["id"]


def test_recency_penalty_rotates_similarly_urgent_pressures():
    graph = _graph()
    a, b = graph["nodes"][0], graph["nodes"][1]
    a["magnitude"] = 55
    b["magnitude"] = 55
    a["trend"] = 1
    b["trend"] = 1
    a["last_foreground_turn"] = 1
    b["last_foreground_turn"] = None
    fg = pressure_graph.select_foreground(graph, identity=_identity(), turn_number=2)
    assert fg == b["id"]


def test_critical_pressure_can_remain_foreground():
    graph = _graph()
    node = _node(graph)
    node["magnitude"] = 95
    node["trend"] = 1
    node["last_foreground_turn"] = 1
    others = graph["nodes"][1:]
    for other in others:
        other["magnitude"] = 30
        other["last_foreground_turn"] = None
    fg = pressure_graph.select_foreground(graph, identity=_identity(), turn_number=2)
    assert fg == node["id"]


def test_threshold_crossing_emits_once():
    graph = _graph()
    node = _node(graph)
    node["trend"] = 1
    node["magnitude"] = 68
    node["threshold"] = 70
    fired1 = pressure_graph.tick_pressure_graph(graph, 2, identity=_identity())
    assert len(fired1) == 1
    fired2 = pressure_graph.tick_pressure_graph(graph, 3, identity=_identity())
    assert fired2 == []


def test_threshold_rearms_after_falling_below():
    graph = _graph()
    node = _node(graph)
    node["trend"] = 1
    node["magnitude"] = 68
    node["threshold"] = 70
    pressure_graph.tick_pressure_graph(graph, 2, identity=_identity())
    node["trend"] = -1
    node["magnitude"] = 72
    pressure_graph.tick_pressure_graph(graph, 3, identity=_identity())
    assert node["last_threshold"] == "below"
    node["trend"] = 1
    fired = pressure_graph.tick_pressure_graph(graph, 4, identity=_identity())
    assert len(fired) == 1


def test_links_bounded_and_point_to_existing_nodes():
    graph = _graph()
    for node in graph["nodes"]:
        links = node.get("linked_pressure_ids") or []
        assert len(links) <= pressure_graph.MAX_LINKS_PER_NODE
        ids = {n["id"] for n in graph["nodes"]}
        assert all(lid in ids for lid in links)


def test_model_cannot_alter_protected_pressure_fields():
    graph = _graph()
    auth = copy.deepcopy(graph)
    tampered = copy.deepcopy(graph)
    tampered["nodes"][0]["magnitude"] = 99
    tampered["nodes"][0]["trend"] = 1
    tampered["nodes"][0]["linked_pressure_ids"] = ["fake"]
    adj = pressure_graph.strip_model_pressure_mutations(tampered, auth)
    assert tampered["nodes"][0]["magnitude"] == auth["nodes"][0]["magnitude"]
    assert adj


def test_identity_primary_kind_seeds_opening_origin():
    identity = _identity(primary_pressure_kind="political")
    opening = _opening(identity)
    graph = pressure_graph.init_pressure_graph(SEED, identity, opening)
    kinds = {n["kind"] for n in graph["nodes"]}
    assert "political" in kinds


def test_max_active_nodes_enforced_on_add():
    graph = _graph()
    for i in range(20):
        pressure_graph.add_pressure_node(
            graph,
            node_id=f"extra-{i}",
            kind="resource",
            origin_type="structured_event",
            origin_id=f"evt-{i}",
            turn_number=2,
        )
    active = [n for n in graph["nodes"] if n.get("status") == "active"]
    assert len(active) <= pressure_graph.MAX_ACTIVE_NODES


def test_upsert_dedupes_equivalent_pressure_and_bounds_values():
    graph = pressure_graph.copy_pressure_graph(None)
    first = pressure_graph.upsert_pressure_node(
        graph,
        run_seed=SEED,
        kind="danger",
        origin_type="structured_event",
        origin_id="evt-flood",
        magnitude=150,
        trend="rising",
        turn_number=1,
        actor_ids=["npc-1"],
        evidence_refs=["evt-1"],
        label="floodwater rising",
    )
    second = pressure_graph.upsert_pressure_node(
        graph,
        run_seed=SEED,
        kind="danger",
        origin_type="structured_event",
        origin_id="evt-flood",
        magnitude=45,
        trend="falling",
        turn_number=2,
        actor_ids=["npc-1", "npc-2"],
        evidence_refs=["evt-2"],
    )

    assert first["id"] == second["id"]
    assert len(graph["nodes"]) == 1
    assert second["magnitude"] == 100
    assert second["trend"] == -1
    assert second["trend_label"] == "falling"
    assert second["actor_ids"] == ["npc-1", "npc-2"]
    assert second["evidence_refs"] == ["evt-1", "evt-2"]


def test_reduce_resolve_and_link_pressure_nodes():
    graph = pressure_graph.copy_pressure_graph(None)
    a = pressure_graph.upsert_pressure_node(
        graph,
        node_id="p-a",
        kind="danger",
        origin_type="structured_event",
        origin_id="a",
        magnitude=20,
    )
    b = pressure_graph.upsert_pressure_node(
        graph,
        node_id="p-b",
        kind="opportunity",
        origin_type="structured_event",
        origin_id="b",
        magnitude=30,
    )

    assert pressure_graph.link_pressure_nodes(graph, a["id"], b["id"]) is True
    assert b["id"] in a["linked_node_ids"]
    assert pressure_graph.reduce_pressure_node(graph, a["id"], amount=5, turn_number=2) is True
    assert a["magnitude"] == 15
    assert a["status"] == "active"
    assert a["trend_label"] == "falling"
    assert pressure_graph.reduce_pressure_node(graph, a["id"], amount=99, turn_number=3) is True
    assert a["status"] == "reduced"
    assert pressure_graph.resolve_pressure_node(graph, b["id"], turn_number=4) is True
    assert b["status"] == "resolved"
    assert b["magnitude"] == 0


def test_pressure_projection_caps_and_orders_structured_nodes():
    graph = pressure_graph.copy_pressure_graph(None)
    for i in range(6):
        pressure_graph.upsert_pressure_node(
            graph,
            node_id=f"p-{i}",
            kind="danger",
            origin_type="structured_event",
            origin_id=f"evt-{i}",
            magnitude=10 + i,
            turn_number=i,
            label=f"pressure {i}",
        )
    graph["foreground_node_id"] = "p-2"

    projected = pressure_graph.project_pressure_graph_for_prompt(graph, limit=3)
    assert [node["id"] for node in projected["nodes"]] == ["p-2", "p-5", "p-4"]
    assert len(projected["nodes"]) == 3
    assert all("threshold_crossings" not in node for node in projected["nodes"])
    assert all("trend_label" in node for node in projected["nodes"])


def test_pressure_directive_contains_marker():
    graph = _graph()
    directive = pressure_graph.build_pressure_directive(graph)
    assert pressure_graph.PRESSURE_DIRECTIVE_MARKER in directive


def test_pressure_evolution_escalates_spawns_event_and_receipts():
    graph = pressure_graph.copy_pressure_graph(None)
    node = pressure_graph.upsert_pressure_node(
        graph,
        node_id="p-danger",
        kind="danger",
        origin_type="structured_event",
        origin_id="evt-danger",
        magnitude=80,
        trend=1,
        turn_number=1,
        location_ids=["dock"],
    )

    result = pressure_graph.evolve_pressure_graph(graph, 3, run_seed=SEED)

    assert node["magnitude"] == 82
    assert node["age_turns"] == 2
    assert node["last_evolved_turn"] == 3
    assert len(result["events"]) == 1
    assert result["events"][0]["event_type"] == "pressure_world_event"
    assert result["events"][0]["pressure_event_kind"] in {"accident", "attack", "collapse", "injury", "evacuation"}
    assert result["events"][0]["event_id"] in node["spawned_event_ids"]
    receipt_types = {r["receipt_type"] for r in result["receipts"]}
    assert {"pressure_escalated", "pressure_spawned_event"} <= receipt_types


def test_pressure_evolution_decay_and_resolution():
    graph = pressure_graph.copy_pressure_graph(None)
    decaying = pressure_graph.upsert_pressure_node(
        graph,
        node_id="p-decay",
        kind="scarcity",
        origin_type="structured_event",
        origin_id="evt-decay",
        magnitude=30,
        trend=0,
        turn_number=1,
    )
    resolving = pressure_graph.upsert_pressure_node(
        graph,
        node_id="p-resolve",
        kind="unknown",
        origin_type="structured_event",
        origin_id="evt-resolve",
        magnitude=5,
        trend=-1,
        turn_number=1,
    )

    result = pressure_graph.evolve_pressure_graph(graph, 6, run_seed=SEED)

    assert decaying["magnitude"] == 28
    assert decaying["status"] == "active"
    assert resolving["magnitude"] == 0
    assert resolving["status"] == "resolved"
    receipt_types = {r["receipt_type"] for r in result["receipts"]}
    assert "pressure_reduced" in receipt_types
    assert "pressure_resolved" in receipt_types


def test_saturated_pressure_naturally_decays_after_event_capacity():
    graph = pressure_graph.copy_pressure_graph(None)
    saturated = pressure_graph.upsert_pressure_node(
        graph,
        node_id="p-saturated",
        kind="danger",
        origin_type="structured_event",
        origin_id="evt-saturated",
        magnitude=100,
        trend=1,
        turn_number=1,
    )
    saturated["spawned_event_ids"] = ["evt-a", "evt-b"]

    result = pressure_graph.evolve_pressure_graph(graph, 6, run_seed=SEED)

    assert saturated["magnitude"] == 98
    assert saturated["trend_label"] == "falling"
    assert saturated["status"] == "active"
    assert any(receipt["receipt_type"] == "pressure_reduced" for receipt in result["receipts"])


def test_pressure_evolution_duplicate_prevention_same_turn():
    graph = pressure_graph.copy_pressure_graph(None)
    pressure_graph.upsert_pressure_node(
        graph,
        node_id="p-danger",
        kind="danger",
        origin_type="structured_event",
        origin_id="evt-danger",
        magnitude=80,
        trend=1,
        turn_number=1,
    )

    first = pressure_graph.evolve_pressure_graph(graph, 3, run_seed=SEED)
    second = pressure_graph.evolve_pressure_graph(graph, 3, run_seed=SEED)

    assert len(first["events"]) == 1
    assert second["events"] == []
    assert second["evaluated_node_ids"] == []
    assert not any(r["receipt_type"] == "pressure_spawned_event" for r in second["receipts"])


def test_pressure_evolution_caps_events_and_evaluations():
    graph = pressure_graph.copy_pressure_graph(None)
    for idx in range(6):
        pressure_graph.upsert_pressure_node(
            graph,
            node_id=f"p-{idx}",
            kind="danger",
            origin_type="structured_event",
            origin_id=f"evt-{idx}",
            magnitude=90 - idx,
            trend=1,
            turn_number=1,
        )

    result = pressure_graph.evolve_pressure_graph(graph, 3, run_seed=SEED)

    assert len(result["evaluated_node_ids"]) == pressure_graph.MAX_PRESSURE_EVOLUTIONS_PER_TICK
    assert len(result["events"]) == pressure_graph.MAX_PRESSURE_EVENTS_PER_TICK


def test_pressure_evolution_mitigation_reduces_only_target_pressure():
    graph = pressure_graph.copy_pressure_graph(None)
    target = pressure_graph.upsert_pressure_node(
        graph,
        node_id="p-target",
        kind="environmental",
        origin_type="structured_event",
        origin_id="evt-target",
        magnitude=50,
        trend=1,
        turn_number=1,
    )
    unrelated = pressure_graph.upsert_pressure_node(
        graph,
        node_id="p-unrelated",
        kind="danger",
        origin_type="structured_event",
        origin_id="evt-unrelated",
        magnitude=45,
        trend=0,
        turn_number=1,
    )

    result = pressure_graph.evolve_pressure_graph(
        graph,
        2,
        run_seed=SEED,
        recent_mitigations=[
            {
                "pressure_node_id": "p-target",
                "delta": -4,
                "before": 50,
                "after": 46,
                "source_event_id": "fx-fortify",
            }
        ],
    )

    assert target["magnitude"] == 46
    assert target["trend_label"] == "falling"
    assert unrelated["magnitude"] == 45
    assert any(r["receipt_type"] == "pressure_reduced" for r in result["receipts"])


def test_pressure_evolution_links_are_deterministic_and_stale_links_removed():
    graph = pressure_graph.copy_pressure_graph(None)
    a = pressure_graph.upsert_pressure_node(
        graph,
        node_id="p-a",
        kind="danger",
        origin_type="structured_event",
        origin_id="evt-a",
        magnitude=20,
        trend=0,
        turn_number=1,
        location_ids=["dock"],
        linked_node_ids=["missing"],
    )
    b = pressure_graph.upsert_pressure_node(
        graph,
        node_id="p-b",
        kind="scarcity",
        origin_type="structured_event",
        origin_id="evt-b",
        magnitude=20,
        trend=0,
        turn_number=1,
        location_ids=["dock"],
    )

    result = pressure_graph.evolve_pressure_graph(graph, 2, run_seed=SEED)

    assert "missing" not in a["linked_node_ids"]
    assert b["id"] in a["linked_node_ids"]
    receipt_types = {r["receipt_type"] for r in result["receipts"]}
    assert "pressure_link_removed" in receipt_types
    assert "pressure_link_created" in receipt_types


def test_pressure_evolution_replay_is_deterministic():
    graph = pressure_graph.copy_pressure_graph(None)
    pressure_graph.upsert_pressure_node(
        graph,
        node_id="p-danger",
        kind="danger",
        origin_type="structured_event",
        origin_id="evt-danger",
        magnitude=80,
        trend=1,
        turn_number=1,
        faction_ids=["watch"],
    )
    a = copy.deepcopy(graph)
    b = copy.deepcopy(graph)

    first = pressure_graph.evolve_pressure_graph(a, 3, run_seed=SEED)
    second = pressure_graph.evolve_pressure_graph(b, 3, run_seed=SEED)

    assert first == second
    assert a == b


def test_resolved_pressure_no_longer_evolves():
    graph = pressure_graph.copy_pressure_graph(None)
    pressure_graph.upsert_pressure_node(
        graph,
        node_id="p-resolved",
        kind="danger",
        origin_type="structured_event",
        origin_id="evt-resolved",
        magnitude=80,
        trend=1,
        turn_number=1,
    )
    pressure_graph.resolve_pressure_node(graph, "p-resolved", turn_number=2)

    result = pressure_graph.evolve_pressure_graph(graph, 3, run_seed=SEED)

    assert result["events"] == []
    assert result["evaluated_node_ids"] == []
