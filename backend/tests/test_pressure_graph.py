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
        "id", "kind", "origin_type", "origin_id", "scope", "magnitude", "trend",
        "status", "linked_pressure_ids", "created_turn", "updated_turn",
        "last_foreground_turn", "threshold", "last_threshold",
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


def test_pressure_directive_contains_marker():
    graph = _graph()
    directive = pressure_graph.build_pressure_directive(graph)
    assert pressure_graph.PRESSURE_DIRECTIVE_MARKER in directive