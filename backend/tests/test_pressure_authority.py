"""ADR-023 — pressure authority: pressure_graph is the single canonical source;
active_pressures is an engine-derived, read-only projection (never model-authored)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pressure_graph
import replayability


def _graph(nodes, fg=None):
    return {"nodes": nodes, "foreground_node_id": fg, "tick": 0, "threshold_crossings": []}


def test_projection_foreground_first_excludes_inactive_deterministic():
    g = _graph([
        {"id": "n1", "status": "active", "label": "dusk closing in", "magnitude": 40},
        {"id": "n2", "status": "active", "label": "wound throbbing", "magnitude": 70},
        {"id": "n3", "status": "resolved", "label": "old debt", "magnitude": 90},
    ], fg="n1")
    a = pressure_graph.project_active_pressures(g)
    b = pressure_graph.project_active_pressures(g)
    assert a == b == ["dusk closing in", "wound throbbing"]


def test_projection_empty_and_nondict():
    assert pressure_graph.project_active_pressures({}) == []
    assert pressure_graph.project_active_pressures({"nodes": []}) == []
    assert pressure_graph.project_active_pressures(None) == []


def test_projection_caps_and_dedups():
    nodes = [{"id": f"n{i}", "status": "active", "label": f"L{i}", "magnitude": i} for i in range(5)]
    nodes.append({"id": "dup", "status": "active", "label": "L4", "magnitude": 4})
    out = pressure_graph.project_active_pressures(_graph(nodes))
    assert len(out) <= 3
    assert len(out) == len(set(out))


def test_projection_orders_by_magnitude_after_foreground():
    g = _graph([
        {"id": "a", "status": "active", "label": "A", "magnitude": 10},
        {"id": "b", "status": "active", "label": "B", "magnitude": 20},
    ], fg="b")
    assert pressure_graph.project_active_pressures(g) == ["B", "A"]


def test_enforce_overwrites_model_active_pressures():
    auth = {"run_seed": "s", "pressure_graph": _graph(
        [{"id": "n1", "status": "active", "label": "generator dying", "magnitude": 50}], fg="n1")}
    merged = {
        "active_pressures": ["LLM-invented pressure not grounded in the graph"],
        "pressure_graph": {"nodes": [{"id": "fake", "status": "active", "magnitude": 100}]},
    }
    adj = replayability.enforce_authoritative(merged, auth)
    assert merged["active_pressures"] == ["generator dying"]          # engine-derived
    assert "active_pressures" in merged                                # key preserved
    assert merged["pressure_graph"]["nodes"][0]["id"] == "n1"          # engine-derived
    assert merged["pressure_graph"]["nodes"][0]["magnitude"] == 50
    assert "rolling_pressure_graph_stripped" in adj
    assert "rolling_pressure_graph_engine_derived" in adj
    assert "rolling_active_pressures_engine_derived" in adj


def test_enforce_active_pressures_deterministic_across_inputs():
    auth = {"run_seed": "s", "pressure_graph": _graph(
        [{"id": "a", "status": "active", "label": "A", "magnitude": 10},
         {"id": "b", "status": "active", "label": "B", "magnitude": 20}], fg="b")}
    m1 = {"active_pressures": ["x"]}
    m2 = {"active_pressures": ["y"]}
    replayability.enforce_authoritative(m1, auth)
    replayability.enforce_authoritative(m2, auth)
    assert m1["active_pressures"] == m2["active_pressures"] == ["B", "A"]
    assert m1["pressure_graph"] == m2["pressure_graph"]


def test_prompt_pressure_projection_respects_cap_and_order():
    nodes = [
        {"id": f"n{i}", "status": "active", "label": f"L{i}", "magnitude": i}
        for i in range(6)
    ]
    graph = _graph(nodes, fg="n2")
    projected = pressure_graph.project_pressure_graph_for_prompt(graph, limit=3)
    assert [node["id"] for node in projected["nodes"]] == ["n2", "n5", "n4"]
    assert len(projected["nodes"]) == 3
