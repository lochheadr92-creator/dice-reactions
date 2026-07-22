import copy
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import information_engine
import memory_retrieval
import replayability
import server
import simulate_world
from foundation_snapshot import FoundationTurnSnapshot

FIXED_SEED = "information-seed"


def _pressure_event(event_id="evt-raid", *, kind="raid", turn=3, magnitude=84):
    return {
        "event_id": event_id,
        "event_type": "pressure_world_event",
        "pressure_event_kind": kind,
        "pressure_node_id": "p-raid",
        "pressure_kind": "danger",
        "turn": turn,
        "magnitude": magnitude,
        "actor_ids": ["npc-bandit"],
        "location_ids": ["dock"],
        "faction_ids": ["watch"],
        "tags": ["pressure_world_event"],
    }


def _state(*, events=None, evidence=None, investigations=None):
    return {
        "run_seed": FIXED_SEED,
        "pressure_graph": {"nodes": [], "foreground_node_id": None, "evolution_receipts": []},
        "engine_world_events": copy.deepcopy(list(events or [])),
        "world_events": [],
        "world_event_receipts": [],
        "evidence": copy.deepcopy(list(evidence or [])),
        "investigations": copy.deepcopy(list(investigations or [])),
        "investigation_receipts": [],
        "information_items": [],
        "information_receipts": [],
        "reputation_signals": [],
        "transition_receipts": [],
    }


def test_rumour_creation_from_source_event_and_replay_duplicate_suppression():
    state = _state(events=[_pressure_event()])

    first = information_engine.evolve_information(state, {}, 3, run_seed=FIXED_SEED)
    snapshot = copy.deepcopy(state)
    second = information_engine.evolve_information(state, {}, 3, run_seed=FIXED_SEED)

    assert first["diagnostics"]["information_created"] == 1
    assert first["diagnostics"]["reputation_signal_created"] >= 1
    assert len(state["information_items"]) == 1
    item = state["information_items"][0]
    assert item["information_type"] == "rumour"
    assert item["truth_status"] == "belief"
    assert item["source_event_ids"] == ["evt-raid"]
    assert item["known_by"]
    assert state["reputation_signals"][0]["source_event_ids"] == ["evt-raid"]
    assert second["diagnostics"]["information_duplicate_suppressed"] >= 1
    assert second["diagnostics"]["reputation_duplicate_suppressed"] >= 1
    assert state["information_items"] == snapshot["information_items"]
    assert state["reputation_signals"] == snapshot["reputation_signals"]
    assert state["information_receipts"] == snapshot["information_receipts"]


def test_information_receipt_history_keeps_newest_provenance_window():
    state = _state()
    state["information_receipts"] = [
        {"receipt_id": f"old-{index}", "source_event_ids": [f"evt-{index}"]}
        for index in range(information_engine.MAX_INFORMATION_RECEIPTS)
    ]

    added = information_engine._append_receipt(
        state,
        [],
        receipt_type="information_created",
        turn_number=99,
        target_key="information_id",
        target_id="info-new",
        source_event_ids=["evt-new"],
    )

    assert added is True
    assert len(state["information_receipts"]) == information_engine.MAX_INFORMATION_RECEIPTS
    assert state["information_receipts"][0]["receipt_id"] == "old-1"
    assert state["information_receipts"][-1]["source_event_ids"] == ["evt-new"]


def test_belief_and_reputation_do_not_overwrite_objective_event_truth():
    event = _pressure_event(kind="theft", magnitude=70)
    state = _state(events=[copy.deepcopy(event)])
    before_event = copy.deepcopy(state["engine_world_events"][0])

    information_engine.evolve_information(state, {}, 4, run_seed=FIXED_SEED)

    assert state["engine_world_events"][0] == before_event
    assert all(row["information_type"] != "truth" for row in state["information_items"])
    assert all(row["truth_status"] == "belief" for row in state["information_items"])
    assert state["reputation_signals"][0]["dimension"] == "suspicious"
    assert "reputation_signals" not in state["engine_world_events"][0]


def test_local_rumour_spreads_locally_not_globally():
    event = _pressure_event(event_id="evt-dock-raid", magnitude=72)
    event["faction_ids"] = []
    event["witness_ids"] = ["npc-witness"]
    state = _state(events=[event])
    rolling = {
        "scene": "dock",
        "npcs": [
            {"npc_id": "npc-witness", "name": "Witness", "location_id": "dock"},
            {"npc_id": "npc-far", "name": "Far Guard", "location_id": "castle"},
        ],
    }

    result = information_engine.evolve_information(state, rolling, 4, run_seed=FIXED_SEED)

    assert result["diagnostics"]["information_propagated"] >= 1
    item = state["information_items"][0]
    assert any(
        row["access_type"] == "local_community"
        and row["scope_type"] == "settlement"
        and row["scope_id"] == "dock"
        for row in item["observer_access"]
    )
    assert information_engine.rumours_visible_in_settlement(state, "dock")
    assert not information_engine.rumours_visible_in_settlement(state, "castle", include_claims=False)
    assert information_engine.information_visible_to_actor(
        state,
        "npc-witness",
        location_id="dock",
        include_public=False,
    )
    assert not information_engine.information_visible_to_actor(
        state,
        "npc-far",
        location_id="castle",
        include_public=False,
    )


def test_witness_becomes_carrier_without_overwriting_truth():
    event = _pressure_event(event_id="evt-witnessed-theft", kind="theft", magnitude=70)
    event["witness_ids"] = ["guard-a"]
    state = _state(events=[copy.deepcopy(event)])
    before_event = copy.deepcopy(state["engine_world_events"][0])

    information_engine.evolve_information(state, {}, 4, run_seed=FIXED_SEED)

    assert state["engine_world_events"][0] == before_event
    item = state["information_items"][0]
    assert item["truth_status"] == "belief"
    assert any(
        row["access_type"] == "direct_witness"
        and row["scope_type"] == "actor"
        and row["scope_id"] == "guard-a"
        for row in item["observer_access"]
    )


def test_duplicate_propagation_is_idempotent_on_replay():
    event = _pressure_event(event_id="evt-replay-raid", magnitude=80)
    event["faction_ids"] = []
    state = _state(events=[event])
    rolling = {
        "scene": "dock",
        "npcs": [{"npc_id": "npc-bandit", "name": "Bandit", "location_id": "dock"}],
    }

    information_engine.evolve_information(state, rolling, 4, run_seed=FIXED_SEED)
    snapshot = copy.deepcopy(state)
    information_engine.evolve_information(state, rolling, 4, run_seed=FIXED_SEED)

    assert state["information_items"] == snapshot["information_items"]
    assert state["information_receipts"] == snapshot["information_receipts"]


def test_low_gravity_rumour_decays_and_is_deprioritised():
    state = _state()
    state["information_items"] = [
        {
            "information_id": "info-old",
            "information_type": "rumour",
            "summary": "old tavern rumour",
            "source_event_ids": ["evt-old"],
            "subject_refs": [{"subject_type": "location", "subject_id": "dock"}],
            "known_by": [{"scope_type": "settlement", "scope_id": "dock"}],
            "observer_access": [
                {
                    "access_type": "local_community",
                    "scope_type": "settlement",
                    "scope_id": "dock",
                    "source_event_ids": ["evt-old"],
                    "reliability": 45,
                    "distortion_level": 12,
                    "acquired_at": {"turn": 1},
                }
            ],
            "reliability": 45,
            "distortion_level": 12,
            "visibility_scope": "settlement",
            "created_at": {"turn": 1},
            "updated_at": {"turn": 1},
            "gravity": 1,
        },
        {
            "information_id": "info-fresh",
            "information_type": "rumour",
            "summary": "fresh raid warning",
            "source_event_ids": ["evt-fresh"],
            "subject_refs": [{"subject_type": "location", "subject_id": "dock"}],
            "known_by": [{"scope_type": "settlement", "scope_id": "dock"}],
            "observer_access": [
                {
                    "access_type": "local_community",
                    "scope_type": "settlement",
                    "scope_id": "dock",
                    "source_event_ids": ["evt-fresh"],
                    "reliability": 80,
                    "distortion_level": 4,
                    "acquired_at": {"turn": 19},
                }
            ],
            "reliability": 80,
            "distortion_level": 4,
            "visibility_scope": "settlement",
            "created_at": {"turn": 19},
            "updated_at": {"turn": 19},
            "gravity": 8,
        },
    ]

    result = information_engine.evolve_information(state, {}, 20, run_seed=FIXED_SEED)

    old = next(row for row in state["information_items"] if row["information_id"] == "info-old")
    assert result["diagnostics"]["information_decay_applied"] == 1
    assert old["reliability"] < 45
    assert old["distortion_level"] > 12
    assert old["stale"] is True
    projected = information_engine.project_active_information_for_rolling(state)
    assert projected[0]["summary"] == "fresh raid warning"


def test_observer_aware_queries_return_different_information_and_reputation():
    state = _state()
    state["information_items"] = [
        {
            "information_id": "info-dock",
            "information_type": "rumour",
            "summary": "dock rumour",
            "source_event_ids": ["evt-dock"],
            "known_by": [{"scope_type": "settlement", "scope_id": "dock"}],
            "observer_access": [
                {
                    "access_type": "local_community",
                    "scope_type": "settlement",
                    "scope_id": "dock",
                    "source_event_ids": ["evt-dock"],
                    "reliability": 70,
                    "distortion_level": 12,
                    "acquired_at": {"turn": 2},
                }
            ],
            "reliability": 70,
            "distortion_level": 12,
            "visibility_scope": "settlement",
            "created_at": {"turn": 2},
            "updated_at": {"turn": 2},
            "gravity": 6,
        },
        {
            "information_id": "info-market",
            "information_type": "rumour",
            "summary": "market rumour",
            "source_event_ids": ["evt-market"],
            "known_by": [{"scope_type": "settlement", "scope_id": "market"}],
            "observer_access": [
                {
                    "access_type": "local_community",
                    "scope_type": "settlement",
                    "scope_id": "market",
                    "source_event_ids": ["evt-market"],
                    "reliability": 70,
                    "distortion_level": 12,
                    "acquired_at": {"turn": 2},
                }
            ],
            "reliability": 70,
            "distortion_level": 12,
            "visibility_scope": "settlement",
            "created_at": {"turn": 2},
            "updated_at": {"turn": 2},
            "gravity": 6,
        },
    ]
    state["reputation_signals"] = [
        {
            "signal_id": "rep-dock",
            "subject_type": "npc",
            "subject_id": "npc-bandit",
            "observer_scope": {"scope_type": "settlement", "scope_id": "dock"},
            "dimension": "dangerous",
            "score": 40,
            "value_delta": 40,
            "source_event_ids": ["evt-dock"],
            "confidence": 70,
            "reliability": 70,
            "created_at": {"turn": 2},
            "updated_at": {"turn": 2},
        },
        {
            "signal_id": "rep-market",
            "subject_type": "npc",
            "subject_id": "npc-bandit",
            "observer_scope": {"scope_type": "settlement", "scope_id": "market"},
            "dimension": "suspicious",
            "score": 22,
            "value_delta": 22,
            "source_event_ids": ["evt-market"],
            "confidence": 70,
            "reliability": 70,
            "created_at": {"turn": 2},
            "updated_at": {"turn": 2},
        },
    ]

    dock_info = information_engine.information_visible_to_actor(state, "npc-a", location_id="dock")
    market_info = information_engine.information_visible_to_actor(state, "npc-b", location_id="market")
    dock_rep = information_engine.reputation_visible_to_observer(
        state,
        subject_ids=["npc-bandit"],
        observer_scope_ids=["dock"],
    )
    market_rep = information_engine.reputation_visible_to_observer(
        state,
        subject_ids=["npc-bandit"],
        observer_scope_ids=["market"],
    )

    assert [row["summary"] for row in dock_info] == ["dock rumour"]
    assert [row["summary"] for row in market_info] == ["market rumour"]
    assert [row["signal_id"] for row in dock_rep] == ["rep-dock"]
    assert [row["signal_id"] for row in market_rep] == ["rep-market"]


def test_evidence_summary_forms_information_and_scoped_reputation_signal():
    evidence = {
        "evidence_id": "ev-lock",
        "evidence_type": "physical_clue",
        "source_event_ids": ["we-case"],
        "discovered_turn": 3,
        "discovered_by": ["guard-a"],
        "location_id": "market",
        "actor_ids": ["suspect-a"],
        "reliability": 82,
        "confidence": 76,
        "related_case_ids": ["case-a"],
        "related_evidence_ids": [],
        "tags": ["world_event"],
        "archived": False,
    }
    state = _state(evidence=[evidence])

    information_engine.evolve_information(state, {}, 5, run_seed=FIXED_SEED)

    item = next(row for row in state["information_items"] if row["information_type"] == "evidence_summary")
    assert item["source_event_ids"][:2] == ["ev-lock", "we-case"]
    assert item["truth_status"] == "evidence"
    assert item["visibility_scope"] == "private"
    signal = state["reputation_signals"][0]
    assert signal["subject_id"] == "suspect-a"
    assert signal["dimension"] == "suspicious"
    assert signal["observer_scope"] == {"scope_type": "settlement", "scope_id": "market"}


def test_pressure_signal_candidates_ignore_low_severity_noise():
    state = _state()
    state["information_items"] = [
        {
            "information_id": "info-noise",
            "information_type": "rumour",
            "summary": "someone maybe saw trouble",
            "source_event_ids": ["evt-noise"],
            "subject_refs": [{"subject_type": "location", "subject_id": "dock"}],
            "known_by": [{"scope_type": "settlement", "scope_id": "dock"}],
            "observer_access": [
                {
                    "access_type": "local_community",
                    "scope_type": "settlement",
                    "scope_id": "dock",
                    "source_event_ids": ["evt-noise"],
                    "reliability": 48,
                    "distortion_level": 30,
                    "acquired_at": {"turn": 2},
                }
            ],
            "reliability": 48,
            "distortion_level": 30,
            "visibility_scope": "settlement",
            "created_at": {"turn": 2},
            "updated_at": {"turn": 2},
            "gravity": 3,
        }
    ]
    state["reputation_signals"] = [
        {
            "signal_id": "rep-noise",
            "subject_type": "npc",
            "subject_id": "npc-bandit",
            "observer_scope": {"scope_type": "settlement", "scope_id": "dock"},
            "dimension": "suspicious",
            "score": 10,
            "value_delta": 10,
            "source_event_ids": ["evt-noise"],
            "confidence": 55,
            "reliability": 55,
            "created_at": {"turn": 2},
            "updated_at": {"turn": 2},
        }
    ]

    assert information_engine.pressure_signal_candidates(state) == []


def test_pressure_signal_candidates_nominate_threshold_information_reputation_and_relationships():
    state = _state()
    state["information_items"] = [
        {
            "information_id": "info-rumour",
            "information_type": "rumour",
            "summary": "the raid is spreading through the docks",
            "source_event_ids": ["evt-rumour"],
            "subject_refs": [{"subject_type": "location", "subject_id": "dock"}],
            "known_by": [
                {"scope_type": "settlement", "scope_id": "dock"},
                {"scope_type": "faction", "scope_id": "watch"},
            ],
            "observer_access": [
                {
                    "access_type": "local_community",
                    "scope_type": "settlement",
                    "scope_id": "dock",
                    "source_event_ids": ["evt-rumour"],
                    "reliability": 74,
                    "distortion_level": 10,
                    "acquired_at": {"turn": 3},
                },
                {
                    "access_type": "secondary_source",
                    "scope_type": "faction",
                    "scope_id": "watch",
                    "source_event_ids": ["evt-rumour"],
                    "reliability": 74,
                    "distortion_level": 12,
                    "acquired_at": {"turn": 3},
                },
            ],
            "reliability": 74,
            "distortion_level": 10,
            "visibility_scope": "settlement",
            "created_at": {"turn": 3},
            "updated_at": {"turn": 3},
            "gravity": 7,
        }
    ]
    state["reputation_signals"] = [
        {
            "signal_id": "rep-danger",
            "subject_type": "npc",
            "subject_id": "npc-bandit",
            "observer_scope": {"scope_type": "settlement", "scope_id": "dock"},
            "dimension": "dangerous",
            "score": 42,
            "value_delta": 42,
            "source_event_ids": ["evt-danger"],
            "confidence": 80,
            "reliability": 80,
            "created_at": {"turn": 3},
            "updated_at": {"turn": 3},
        }
    ]
    state["relationship_effect_receipts"] = [
        {
            "receipt_id": "rel-collapse",
            "receipt_type": "relationship_threshold_crossed",
            "turn": 3,
            "npc_name": "Guard",
            "before_state": "neutral",
            "after_state": "collapsed",
            "source_event_id": "evt-rel-guard-turn-3",
        }
    ]

    candidates = information_engine.pressure_signal_candidates(state, limit=8)

    assert {row["source_kind"] for row in candidates} == {
        "information_item",
        "reputation_signal",
        "relationship_receipt",
    }
    assert any(row["pressure_kind"] == "social_tension" for row in candidates)
    assert any(row["pressure_kind"] == "danger" for row in candidates)
    assert any(row["pressure_kind"] == "social_tension" and row["source_kind"] == "relationship_receipt" for row in candidates)


def test_information_caps_and_projection_order_are_bounded_and_deterministic():
    state = _state()
    state["information_items"] = [
        {
            "information_id": f"info-{idx:02d}",
            "information_type": "rumour",
            "summary": f"rumour {idx}",
            "source_event_ids": [f"evt-{idx:02d}"],
            "subject_refs": [{"subject_type": "event", "subject_id": f"evt-{idx:02d}"}],
            "known_by": [{"scope_type": "public", "scope_id": "public"}],
            "reliability": 40 + idx,
            "distortion_level": idx % 20,
            "visibility_scope": "public",
            "created_at": {"turn": idx},
            "updated_at": {"turn": idx},
            "gravity": idx % 10,
        }
        for idx in range(information_engine.MAX_INFORMATION_ITEMS + 8)
    ]

    information_engine.evolve_information(state, {}, 40, run_seed=FIXED_SEED)
    projected = information_engine.project_active_information_for_rolling(state)

    assert len(state["information_items"]) == information_engine.MAX_INFORMATION_ITEMS
    assert len(projected) == information_engine.MAX_PROJECTED_INFORMATION
    assert projected == information_engine.project_active_information_for_rolling(copy.deepcopy(state))
    projected_gravity = [row["gravity"] for row in projected]
    assert projected_gravity == sorted(projected_gravity, reverse=True)


def test_prompt_safe_summaries_exclude_internal_metadata():
    safe = server._prompt_safe_rolling(
        {
            "information_items": [{"information_id": "hidden"}],
            "information_receipts": [{"receipt_id": "hidden"}],
            "reputation_signals": [{"signal_id": "hidden"}],
            "active_information": [
                {
                    "information_id": "hidden-info",
                    "information_type": "rumour",
                    "summary": "raid reported",
                    "source_event_ids": ["evt-hidden"],
                    "known_by": [{"scope_type": "actor", "scope_id": "hidden"}],
                    "observer_access": [
                        {
                            "access_type": "direct_witness",
                            "scope_type": "actor",
                            "scope_id": "hidden",
                            "source_event_ids": ["evt-hidden"],
                            "acquired_at": {"turn": 3},
                        }
                    ],
                    "subject_refs": [{"subject_type": "location", "subject_id": "dock"}],
                    "reliability": 72,
                    "reliability_band": "high",
                    "distortion_level": 12,
                    "visibility_scope": "settlement",
                    "gravity": 7,
                    "last_decay_turn": 8,
                    "decay_ready": True,
                    "stale": True,
                }
            ],
            "active_reputation": [
                {
                    "signal_id": "hidden-signal",
                    "subject_type": "npc",
                    "subject_id": "npc-bandit",
                    "observer_scope": {"scope_type": "settlement", "scope_id": "dock"},
                    "dimension": "dangerous",
                    "score": 42,
                    "score_band": "strong_positive",
                    "confidence": 80,
                    "source_event_ids": ["evt-hidden"],
                }
            ],
        }
    )

    assert "information_items" not in safe
    assert "information_receipts" not in safe
    assert "reputation_signals" not in safe
    info = safe["active_information"][0]
    rep = safe["active_reputation"][0]
    assert "information_id" not in info
    assert "source_event_ids" not in info
    assert "known_by" not in info
    assert "observer_access" not in info
    assert "access_type" not in info
    assert "last_decay_turn" not in info
    assert "decay_ready" not in info
    assert "stale" not in info
    assert "reliability" not in info
    assert info["summary"] == "raid reported"
    assert "signal_id" not in rep
    assert "source_event_ids" not in rep
    assert "score" not in rep
    assert rep["score_band"] == "strong_positive"


def test_replayability_integration_projects_foundation_and_retrieval_cues():
    state = replayability.empty_replayability_state()
    state["run_seed"] = FIXED_SEED
    state["pressure_graph"] = {
        "foreground_node_id": "p-raid",
        "tick": 0,
        "threshold_crossings": [],
        "evolution_receipts": [],
        "nodes": [
            {
                "id": "p-raid",
                "kind": "danger",
                "origin": {"type": "structured_event", "id": "seed"},
                "origin_type": "structured_event",
                "origin_id": "seed",
                "scope": "local",
                "magnitude": 95,
                "trend": 1,
                "status": "active",
                "actor_ids": ["npc-bandit"],
                "location_ids": ["dock"],
                "faction_ids": ["watch"],
                "tags": [],
                "linked_node_ids": [],
                "created_turn": 1,
                "updated_turn": 1,
                "last_foreground_turn": None,
                "threshold": 70,
                "last_threshold": "below",
                "evidence_refs": [],
                "label": "dock raid",
                "spawned_event_ids": [],
            }
        ],
    }
    state["reputation_signals"] = [
        {
            "signal_id": "rep-dock-bandit",
            "subject_type": "npc",
            "subject_id": "npc-bandit",
            "observer_scope": {"scope_type": "settlement", "scope_id": "dock"},
            "dimension": "dangerous",
            "score": 40,
            "value_delta": 40,
            "source_event_ids": ["seed-reputation"],
            "confidence": 80,
            "reliability": 80,
            "created_at": {"turn": 2},
            "updated_at": {"turn": 2},
        }
    ]
    rolling = {
        "scene": "dock",
        "npcs": [{"name": "Bandit", "npc_id": "npc-bandit", "location_id": "dock", "faction_id": "watch"}],
    }

    updated, _, diagnostics, _, working = replayability.prepare_action_turn(
        state,
        3,
        rolling_state=rolling,
    )

    assert diagnostics["information_created"] >= 1
    assert updated["information_items"]
    assert updated["reputation_signals"]
    assert working["active_information"]
    assert working["active_reputation"]
    assert "source_event_ids" not in working["active_information"][0]
    snapshot = FoundationTurnSnapshot.build(
        run_seed=FIXED_SEED,
        turn_sequence=4,
        rolling_state=working,
        replayability_state=updated,
    )
    assert snapshot.information_state_ref["information_items"]
    ref = next(row for row in snapshot.utility_input_refs if row["actor_id"] == "npc-bandit")
    assert ref["active_information_count"] >= 1
    assert ref["reputation_hints"]

    prepared = memory_retrieval.evaluate_memory_retrieval(
        snapshot,
        actor_resolution={"tiers_by_actor_id": {"npc-bandit": "hero"}, "acting_actor_ids": ["npc-bandit"]},
        gravity={},
        rolling_state=working,
    )
    trace = next(row for row in prepared["retrieval_traces"] if row["actor_id"] == "npc-bandit")
    assert trace["information_ids"]
    assert trace["reputation_signal_ids"]
    assert prepared["information_context"]["active"]
    assert prepared["reputation_context"]["active"]


def test_headless_simulation_information_layer_stays_bounded_and_prompt_safe(tmp_path):
    summary = simulate_world.run_simulation(
        turns=30,
        seed="information-short",
        out_dir=tmp_path / "information_short",
    )

    final = summary["final_metrics"]
    assert "active_information" in final
    assert "active_reputation" in final
    assert final["active_information"] <= information_engine.MAX_INFORMATION_ITEMS
    assert final["active_reputation"] <= information_engine.MAX_REPUTATION_SIGNALS
    assert summary["anomaly_counts"].get("duplicate_id", 0) == 0
    assert summary["anomaly_counts"].get("unbounded_growth", 0) == 0
    assert summary["anomaly_counts"].get("prompt_leakage", 0) == 0
