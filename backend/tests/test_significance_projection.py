import copy
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import causal_visibility
import significance_projection as significance


def _causal_entries():
    replay = {
        "pressure_graph": {
            "evolution_receipts": [
                {
                    "receipt_id": "pressure-receipt-1",
                    "receipt_type": "pressure_escalated",
                    "turn": 3,
                    "node_id": "pressure-dock",
                    "before": {"status": "active", "magnitude": 40},
                    "after": {"status": "active", "magnitude": 70},
                    "source_event_ids": ["info-raid", "evt-raid"],
                    "source_kind": "information_item",
                    "pressure_kind": "social_tension",
                    "reason": "spreading rumour reached 2 scopes",
                    "affected_location_ids": ["dock"],
                }
            ]
        },
        "relationship_effect_receipts": [
            {
                "receipt_id": "rel-src-1",
                "receipt_type": "relationship_threshold_crossed",
                "turn": 4,
                "npc_name": "Greg Stahl",
                "before_state": "neutral",
                "after_state": "collapsed",
                "source_event_id": "evt-rel-greg-turn-4",
                "source_kind": "relationship_threshold_crossed",
            }
        ],
        "scheduling_receipts": [
            {
                "receipt_id": "sched-1",
                "receipt_type": "gravity_compress",
                "turn": 5,
                "subject_id": "actor:npc-mara",
                "detail": "keep_active->compress",
            }
        ],
    }
    return causal_visibility.project_causal_visibility(replay)["entries"]


def test_empty_input_returns_valid_empty_projection():
    projection = significance.project_significance([], {"turn_sequence": 7, "actor_id": "npc-a"})

    assert projection == {
        "schema_version": significance.SIGNIFICANCE_PROJECTION_SCHEMA_VERSION,
        "source_visibility_schema_version": significance.SIGNIFICANCE_SOURCE_VISIBILITY_SCHEMA_VERSION,
        "turn": 7,
        "scope": {"actor_id": "npc-a", "location_id": "", "faction_id": ""},
        "entries": [],
        "entry_count": 0,
        "max_entries": significance.MAX_SIGNIFICANCE_ENTRIES,
        "truncated": False,
    }


def test_projects_contract_shape_and_contextual_importance():
    projection = significance.project_significance(
        _causal_entries(),
        {"turn_sequence": 4, "actor_id": "Greg Stahl", "location_id": "dock"},
    )

    assert projection["schema_version"] == 1
    assert projection["source_visibility_schema_version"] == 1
    assert projection["turn"] == 4
    assert projection["entry_count"] == 3
    first = projection["entries"][0]
    assert first["affected_entity_id"] == "Greg Stahl"
    assert first["effect_category"] == "relationship"
    assert first["significance_band"] == "critical"
    assert 0.0 <= first["significance_score"] <= 1.0
    assert first["source_causal_entry_ids"]
    assert first["source_ids"] == ["evt-rel-greg-turn-4"]
    assert "category_relationship" in first["reason_codes"]
    assert "affected_actor_matches_scope" in first["reason_codes"]

    pressure = next(row for row in projection["entries"] if row["effect_category"] == "pressure")
    assert pressure["metadata"]["affected_location_ids"] == ["dock"]
    assert "metadata_location_matches_scope" in pressure["reason_codes"]


def test_projection_is_deterministic_order_independent_and_does_not_mutate_inputs():
    entries = _causal_entries()
    reversed_entries = list(reversed(copy.deepcopy(entries)))
    before = copy.deepcopy(entries)

    first = significance.project_significance(entries, {"turn_sequence": 5, "location_id": "dock"})
    second = significance.project_significance(reversed_entries, {"location_id": "dock", "turn_sequence": 5})

    assert first == second
    assert entries == before


def test_projection_is_bounded_and_sanitized():
    entries = []
    for idx in range(significance.MAX_SIGNIFICANCE_ENTRIES + 5):
        entries.append(
            {
                "entry_id": f"causal-{idx}",
                "turn": idx,
                "source_system": "pressure_graph",
                "source_ids": [f"evt-{idx}-{n}" for n in range(20)]
                + ["generated prose should not become a source id"],
                "affected_entity_type": "pressure_node",
                "affected_entity_id": f"pressure-{idx}",
                "effect_category": "pressure",
                "effect_type": "pressure_escalated",
                "delta": {"magnitude": idx},
                "metadata": {
                    "affected_location_ids": ["dock"],
                    "affected_actor_ids": ["player said this should not leak"],
                    "narrative": "model-only prose",
                    "probabilities": [0.5, 0.4],
                    "debug": "internal",
                    "note": "generated prose says this should not leak",
                },
            }
        )

    projection = significance.project_significance(
        entries,
        {"turn_sequence": 40, "location_id": "dock", "max_entries": 5},
    )
    payload = json.dumps(projection).lower()

    assert projection["entry_count"] == 5
    assert projection["max_entries"] == 5
    assert projection["truncated"] is True
    assert all(len(row["source_ids"]) <= significance.MAX_SIGNIFICANCE_SOURCE_IDS for row in projection["entries"])
    assert all(len(row["reason_codes"]) <= significance.MAX_SIGNIFICANCE_REASON_CODES for row in projection["entries"])
    assert "model-only prose" not in payload
    assert "generated prose" not in payload
    assert "player said" not in payload
    assert "probabilities" not in payload
    assert "debug" not in payload


def test_malformed_entries_fail_closed():
    projection = significance.project_significance(
        [
            {"entry_id": "missing-category", "affected_entity_type": "npc"},
            "not-a-dict",
            {
                "entry_id": "valid",
                "turn": 2,
                "affected_entity_type": "npc",
                "affected_entity_id": "Mara",
                "effect_category": "relationship",
                "effect_type": "help",
            },
        ],
        {"turn_sequence": 2},
    )

    assert projection["entry_count"] == 1
    assert projection["entries"][0]["source_causal_entry_ids"] == ["valid"]


def test_passive_evaluator_is_not_wired_into_runtime_modules():
    root = Path(__file__).resolve().parents[1]
    runtime_files = [
        root / "replayability.py",
        root / "foundation_integration.py",
        root / "pressure_graph.py",
        root / "relationships.py",
        root / "memory_retrieval.py",
    ]

    for path in runtime_files:
        assert "significance_projection" not in path.read_text(encoding="utf-8")
