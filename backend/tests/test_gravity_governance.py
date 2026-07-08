import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gravity_governance
from foundation_snapshot import FoundationTurnSnapshot


def test_retention_formula_matches_appendix():
    score = gravity_governance.compute_retention_score(
        gravity=0.8,
        connectivity=1.0,
        player_relevance=1.0,
        age_years=0.0,
    )
    expected = 0.8 * (1 + 0.5 * 1.0) * (1 + 0.5 * 1.0) * 1.0 / 2.25
    assert abs(score - min(1.0, expected)) < 1e-9


def test_retention_bands():
    assert gravity_governance.retention_band(0.85) == "keep_active"
    assert gravity_governance.retention_band(0.65) == "light_summarisation"
    assert gravity_governance.retention_band(0.45) == "compress"
    assert gravity_governance.retention_band(0.25) == "archive"
    assert gravity_governance.retention_band(0.05) == "eligible_for_deletion"


def test_player_relevance_zero_without_player():
    assert gravity_governance.player_relevance_factor(None, player_exists=False) == 0.0


def test_protected_pressure_not_archived():
    snapshot = FoundationTurnSnapshot.build(
        run_seed="seed",
        turn_sequence=2,
        rolling_state={},
        replayability_state={
            "run_seed": "seed",
            "pressure_graph": {
                "nodes": [{"id": "p1", "status": "active", "magnitude": 80, "kind": "resource"}]
            },
        },
    )
    prepared = gravity_governance.evaluate_gravity_governance(snapshot)
    bands = {row["item_id"]: row["band"] for row in prepared["dispositions"]}
    assert bands["pressure:p1"] != "archive"


def test_overflow_raises_deterministic_error():
    snapshot = FoundationTurnSnapshot.build(
        run_seed="seed",
        turn_sequence=1,
        rolling_state={},
        replayability_state={"run_seed": "seed", "pressure_graph": {"nodes": []}},
    )
    items = [
        {
            "item_id": f"item-{i}",
            "gravity": 0.2,
            "unresolved_consequence": True,
            "protected": True,
        }
        for i in range(600)
    ]
    with pytest.raises(gravity_governance.GravityBudgetOverflow):
        gravity_governance.evaluate_gravity_governance(
            snapshot,
            items=items,
            context_budget_items=100,
        )


def _trait_snapshot(*, replay_overrides=None):
    replay = {
        "run_seed": "trait-seed",
        "pressure_graph": {
            "nodes": [
                {
                    "id": "p-resource",
                    "status": "active",
                    "magnitude": 40,
                    "kind": "resource",
                    "location_ids": ["loc-town"],
                }
            ],
        },
    }
    replay.update(replay_overrides or {})
    return FoundationTurnSnapshot.build(
        run_seed="trait-seed",
        turn_sequence=3,
        rolling_state={
            "scene": "loc-town",
            "npcs": [
                {
                    "name": "Mara",
                    "npc_id": "npc-mara",
                    "location_id": "loc-town",
                }
            ],
        },
        replayability_state=replay,
    )


def _trait_refs():
    return {
        "npc_traits": {
            "version": 1,
            "by_npc_id": {
                "npc-mara": {
                    "ambition": "high",
                    "fear": "scarcity",
                    "loyalty_anchor": "player",
                    "personal_stakes": "survival",
                    "risk_tolerance": "high",
                    "pressure_sensitivity": "high",
                    "social_role": "leader",
                    "display_name": "Mara",
                }
            },
        },
        "settlement_traits": {
            "version": 1,
            "by_location_id": {
                "loc-town": {
                    "dominant_pressure": "resource",
                    "local_stakes": "supply",
                    "prosperity": "low",
                    "stability": "low",
                    "crime": "high",
                }
            },
        },
    }


def _score_by_item(prepared):
    return {
        row["item_id"]: row["retention_score"]
        for row in prepared["dispositions"]
    }


def test_trait_significance_absent_keeps_existing_scores_and_shape():
    snapshot = _trait_snapshot()
    legacy = gravity_governance.evaluate_gravity_governance(snapshot)
    trait_enabled = gravity_governance.evaluate_gravity_governance(
        snapshot,
        trait_significance_enabled=True,
    )
    empty_traits = gravity_governance.evaluate_gravity_governance(
        _trait_snapshot(
            replay_overrides={
                "npc_traits": {"version": 1, "by_npc_id": {}},
                "settlement_traits": {"version": 1, "by_location_id": {}},
            }
        ),
        trait_significance_enabled=True,
    )

    assert trait_enabled == legacy
    assert empty_traits == legacy


def test_trait_significance_changes_scores_deterministically_for_same_seed():
    snapshot_a = _trait_snapshot(replay_overrides=_trait_refs())
    snapshot_b = _trait_snapshot(replay_overrides=_trait_refs())

    baseline = gravity_governance.evaluate_gravity_governance(_trait_snapshot())
    scored_a = gravity_governance.evaluate_gravity_governance(
        snapshot_a,
        trait_significance_enabled=True,
    )
    scored_b = gravity_governance.evaluate_gravity_governance(
        snapshot_b,
        trait_significance_enabled=True,
    )

    assert scored_a == scored_b
    assert scored_a["trait_modified_count"] == 2
    assert _score_by_item(scored_a)["actor:npc-mara"] > _score_by_item(baseline)["actor:npc-mara"]
    assert _score_by_item(scored_a)["pressure:p-resource"] > _score_by_item(baseline)["pressure:p-resource"]


def test_trait_significance_modifiers_remain_within_bounds():
    modifier = gravity_governance.trait_significance_modifier(
        {
            "item_id": "actor:npc-mara",
            "kind": "actor",
            "actor_id": "npc-mara",
            "display_name": "Mara",
            "location_id": "loc-town",
            "event": "Mara exposed the resource supply secret.",
        },
        npc_trait_refs=_trait_refs()["npc_traits"],
        settlement_trait_refs=_trait_refs()["settlement_traits"],
        location_ref="loc-town",
    )

    assert abs(modifier["gravity"]) <= gravity_governance.MAX_TRAIT_GRAVITY_MODIFIER
    assert abs(modifier["connectivity"]) <= gravity_governance.MAX_TRAIT_CONNECTIVITY_MODIFIER
    assert modifier["gravity"] == gravity_governance.MAX_TRAIT_GRAVITY_MODIFIER


def test_partial_trait_records_are_safe_and_bounded():
    snapshot = _trait_snapshot(
        replay_overrides={
            "npc_traits": {
                "version": 1,
                "by_npc_id": {"npc-mara": {"ambition": "high"}},
            },
            "settlement_traits": {
                "version": 1,
                "by_location_id": {"loc-town": {"prosperity": "low"}},
            },
        }
    )
    prepared = gravity_governance.evaluate_gravity_governance(
        snapshot,
        trait_significance_enabled=True,
    )
    modifier = gravity_governance.trait_significance_modifier(
        {"item_id": "actor:npc-mara", "kind": "actor", "actor_id": "npc-mara"},
        npc_trait_refs=snapshot.npc_trait_refs,
        settlement_trait_refs=snapshot.settlement_trait_refs,
        location_ref=snapshot.location_ref,
    )

    assert prepared["trait_modified_count"] == 2
    assert abs(modifier["gravity"]) <= gravity_governance.MAX_TRAIT_GRAVITY_MODIFIER
    assert abs(modifier["connectivity"]) <= gravity_governance.MAX_TRAIT_CONNECTIVITY_MODIFIER
