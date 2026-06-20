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