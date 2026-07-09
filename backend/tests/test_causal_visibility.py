import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import causal_visibility


def _replay_state():
    return {
        "pressure_graph": {
            "evolution_receipts": [
                {
                    "receipt_id": "pressure-receipt-1",
                    "receipt_type": "pressure_escalated",
                    "turn": 3,
                    "node_id": "pressure-dock",
                    "before": {
                        "status": "active",
                        "magnitude": 40,
                        "narrative": "model-only pressure prose",
                    },
                    "after": {
                        "status": "active",
                        "magnitude": 58,
                        "summary": "rendered pressure prose",
                    },
                    "source_event_ids": ["info-raid", "evt-raid"],
                    "source_kind": "information_item",
                    "pressure_kind": "social_tension",
                    "reason": "spreading rumour reached 2 scopes with gravity 7 and reliability 80",
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
                "prose": "relationship prose must not pass through",
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


def _by_category(projection):
    return {entry["effect_category"]: entry for entry in projection["entries"]}


def test_projects_relationship_pressure_and_gravity_effects():
    projection = causal_visibility.project_causal_visibility(_replay_state())

    assert projection["schema_version"] == causal_visibility.CAUSAL_VISIBILITY_SCHEMA_VERSION
    entries = _by_category(projection)
    assert {"relationship", "pressure", "gravity"} <= set(entries)

    pressure = entries["pressure"]
    assert pressure["source_system"] == "pressure_graph"
    assert pressure["affected_entity_type"] == "pressure_node"
    assert pressure["affected_entity_id"] == "pressure-dock"
    assert pressure["delta"] == {"magnitude": 18}
    assert pressure["source_ids"] == ["info-raid", "evt-raid"]
    assert pressure["reason"].startswith("spreading rumour reached")
    assert pressure["metadata"]["affected_location_ids"] == ["dock"]

    relationship = entries["relationship"]
    assert relationship["affected_entity_id"] == "Greg Stahl"
    assert relationship["before"] == {"state": "neutral"}
    assert relationship["after"] == {"state": "collapsed"}
    assert relationship["delta"]["state"] == "neutral->collapsed"
    assert relationship["source_ids"] == ["evt-rel-greg-turn-4"]

    gravity = entries["gravity"]
    assert gravity["source_system"] == "runtime_scheduling"
    assert gravity["affected_entity_type"] == "actor"
    assert gravity["before"] == {"band": "keep_active"}
    assert gravity["after"] == {"band": "compress"}


def test_projection_is_deterministic_and_does_not_mutate_inputs():
    replay = _replay_state()
    before = copy.deepcopy(replay)

    first = causal_visibility.project_causal_visibility(replay)
    second = causal_visibility.project_causal_visibility(replay)

    assert first == second
    assert replay == before


def test_projection_is_bounded_and_sanitized():
    replay = {"pressure_graph": {"evolution_receipts": []}}
    for idx in range(causal_visibility.MAX_CAUSAL_VISIBILITY_ENTRIES + 5):
        replay["pressure_graph"]["evolution_receipts"].append(
            {
                "receipt_id": f"pressure-receipt-{idx}",
                "receipt_type": "pressure_escalated",
                "turn": idx,
                "node_id": f"pressure-{idx}",
                "before": {"status": "active", "magnitude": idx, "debug": "internal"},
                "after": {"status": "active", "magnitude": idx + 1, "text": "model prose"},
                "source_event_ids": [f"evt-{idx}-{n}" for n in range(20)],
                "reason": "generated prose says this should not leak",
                "summary": "narrative-only summary",
            }
        )

    projection = causal_visibility.project_causal_visibility(replay, limit=5)
    payload = json.dumps(projection).lower()

    assert projection["entry_count"] == 5
    assert projection["truncated"] is True
    assert all(
        len(entry["source_ids"]) <= causal_visibility.MAX_CAUSAL_VISIBILITY_SOURCE_IDS
        for entry in projection["entries"]
    )
    assert "model prose" not in payload
    assert "narrative-only" not in payload
    assert "generated prose" not in payload
    assert "debug" not in payload
    assert all(entry["reason"] == "" for entry in projection["entries"])


def test_optional_provenance_and_retrieval_traces_are_normalized():
    provenance = [
        {
            "event_id": "rel-evt-1",
            "turn": 2,
            "target_name": "Mara",
            "source_kind": "player_action",
            "cause": "player",
            "kind": "help",
            "reason": "player action resolved: help toward Mara",
            "applied_deltas": {"trust": 12, "loyalty": 8},
            "before": {"trust": 0, "loyalty": 0, "prose": "do not leak"},
            "after": {"trust": 12, "loyalty": 8, "narrative": "do not leak"},
        }
    ]
    retrieval = {
        "turn": 6,
        "retrieval_traces": [
            {
                "actor_id": "npc-mara",
                "tier": "hero",
                "working_memory_size": 2,
                "selected_memory_ids": ["mem-1", "mem-2"],
                "shadow_mode": True,
                "probabilities": [0.5, 0.5],
                "summary": "memory prose must not pass through",
            }
        ],
    }

    projection = causal_visibility.project_causal_visibility(
        {},
        relationship_provenance=provenance,
        retrieval_prepared=retrieval,
    )
    entries = _by_category(projection)

    relationship = entries["relationship"]
    assert relationship["source_system"] == "relationship_provenance"
    assert relationship["effect_type"] == "help"
    assert relationship["delta"] == {"loyalty": 8, "trust": 12}

    memory = entries["memory"]
    assert memory["source_system"] == "memory_retrieval"
    assert memory["source_ids"] == ["mem-1", "mem-2"]
    assert memory["after"] == {"selected_memory_count": 2}
    assert "probabilities" not in memory["metadata"]
    assert "memory prose" not in json.dumps(projection).lower()
