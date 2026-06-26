"""ADR-024 shadow comparison and feature-gated live handoff tests."""
import copy
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import living_cast_shadow
import ai_config
import replayability
import utility_ai
import npc_world_moves
from foundation_snapshot import FoundationTurnSnapshot


PROOF_SEED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
DISAGREEMENT_PROOF_SEED = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _snap(stress_level=30.0, actor_id="npc-a"):
    rolling = {"npcs": [{"npc_id": actor_id, "name": "Mara"}]}
    if stress_level is not None:
        rolling["actor_stress"] = {actor_id: {"stress_level": stress_level, "capacity": 1.0}}
    replay = {
        "run_seed": "s",
        "pressure_graph": {"nodes": [{"id": "p1", "status": "active", "magnitude": 50}]},
        "npc_agendas": {"agendas": [{"npc_id": actor_id, "goal_kind": "escape_danger"}]},
    }
    return FoundationTurnSnapshot.build(
        run_seed="s", turn_sequence=1, rolling_state=rolling, replayability_state=replay
    )


def _cands():
    return [
        {"npc_id": "npc-a", "agenda_id": "ag1", "move_kind": "withdraw", "target_type": "location", "target_id": "loc-1", "score": 40, "tier": "hero"},
        {"npc_id": "npc-a", "agenda_id": "ag1", "move_kind": "gather", "target_type": "pressure", "target_id": "p1", "score": 25, "tier": "hero"},
    ]


def _proof_state_and_rolling(run_seed=PROOF_SEED, goal_kind=None):
    state, _ = replayability.init_new_story(
        genre="noir",
        role="detective",
        tone="gritty",
        difficulty="standard",
        scenario_id=None,
        custom_premise=None,
        custom_world_setup=None,
        run_seed=run_seed,
        npc_seed_records=[
            {"name": "Marlene Cho", "source_type": "seed_record", "source_slot": 0}
        ],
    )
    state["pressure_graph"]["nodes"] = [
        {
            "id": "pressure-resource-proof",
            "kind": "resource",
            "status": "active",
            "magnitude": 60,
            "trend": 1,
        }
    ]
    agenda = state["npc_agendas"]["active"][0]
    if goal_kind:
        agenda["goal_kind"] = goal_kind
    npc_id = agenda["npc_id"]
    rolling = {
        "scene": "dock warehouse",
        "npcs": [
            {
                "npc_id": npc_id,
                "name": "Marlene Cho",
                "stance": "ally",
                "last_seen": "dock",
            }
        ],
        "relationship_vectors": [
            {
                "npc_id": npc_id,
                "name": "Marlene Cho",
                "trust": 10,
                "loyalty": 30,
                "fear": 0,
                "resentment": 12,
                "state": "neutral",
            }
        ],
        "faction_pressure": [
            {"name": "Syndicate", "ticks": {"suspicion": 0, "goodwill": 0}}
        ],
        "actor_stress": {npc_id: {"stress_level": 55, "capacity": 1.0}},
    }
    return state, rolling


def test_shadow_record_shape_and_scores():
    rec = living_cast_shadow.compare_move_scoring(_snap(), _cands(), _cands()[0])
    assert rec["shadow_schema_version"] == 2
    assert rec["candidate_count"] == 2
    assert rec["heuristic_pick"]["move_kind"] == "withdraw"
    assert len(rec["scores"]) == 2
    assert all("utility_score" in r and "heuristic_score" in r for r in rec["scores"])
    assert "agree" in rec
    assert rec["selector"] == "utility_ai.select_action"


def test_shadow_is_pure_and_deterministic():
    snap, cands = _snap(), _cands()
    before = copy.deepcopy(cands)
    r1 = living_cast_shadow.compare_move_scoring(snap, cands, cands[0])
    r2 = living_cast_shadow.compare_move_scoring(snap, cands, cands[0])
    assert cands == before          # inputs not mutated
    assert r1 == r2                 # deterministic


def test_shadow_utility_pick_is_max_utility():
    rec = living_cast_shadow.compare_move_scoring(_snap(), _cands(), _cands()[0])
    scored = [r for r in rec["scores"] if r["noisy_utility"] is not None]
    if scored:
        best = max(s["noisy_utility"] for s in scored)
        assert rec["utility_pick"]["noisy_utility"] == best


def test_shadow_empty_candidates():
    rec = living_cast_shadow.compare_move_scoring(_snap(), [], None)
    assert rec["candidate_count"] == 0
    assert rec["utility_pick"] is None
    assert rec["agree"] is False


def test_shadow_reports_agreement_or_divergence_without_forcing():
    # Both systems remain present and their comparison stays diagnostic.
    rec = living_cast_shadow.compare_move_scoring(_snap(), _cands(), _cands()[0])
    assert isinstance(rec["agree"], bool)
    assert rec["utility_pick"] is None or set(rec["utility_pick"]) >= {"actor_id", "move_kind", "target_id", "utility_score"}


def test_live_flag_off_preserves_heuristic_pick():
    candidates = _cands()
    comparison = {
        "utility_pick": {
            "actor_id": "npc-a",
            "move_kind": "gather",
            "target_id": "p1",
            "replacement_authorised": True,
        }
    }

    selected, applied = living_cast_shadow.choose_live_move(
        candidates,
        candidates[0],
        comparison,
        enabled=False,
        run_seed="s",
        turn_number=2,
    )

    assert selected == candidates[0]
    assert applied is False


def test_live_flag_on_hands_off_select_action_winner(monkeypatch):
    def fake_select_action(candidates, *, snapshot, actor_resolution, seed_draw_start=0):
        assert candidates
        assert actor_resolution["acting_actor_ids"] == ["npc-a"]
        return {
            "selected": {
                "actor_id": "npc-a",
                "action_kind": "gather",
                "target_kind": "pressure",
                "target_id": "p1",
                "base_utility": 80.0,
                "noisy_utility": 80.25,
                "replacement_authorised": True,
                "stress_band": "ELEVATED",
            },
            "score_table": [
                {
                    "actor_id": "npc-a",
                    "action_kind": "gather",
                    "target_id": "p1",
                    "base_utility": 80.0,
                    "noisy_utility": 80.25,
                    "replacement_authorised": True,
                }
            ],
        }

    monkeypatch.setattr(utility_ai, "select_action", fake_select_action)
    candidates = _cands()
    comparison = living_cast_shadow.compare_move_scoring(_snap(), candidates, candidates[0])
    selected, applied = living_cast_shadow.choose_live_move(
        candidates,
        candidates[0],
        comparison,
        enabled=True,
        run_seed="s",
        turn_number=2,
    )

    assert comparison["selector"] == "utility_ai.select_action"
    assert comparison["heuristic_pick"]["move_kind"] == "withdraw"
    assert comparison["utility_pick"]["move_kind"] == "gather"
    assert selected["move_kind"] == "gather"
    assert selected["receipt_id"]
    assert selected["turn"] == 2
    assert applied is True


def test_live_handoff_fails_closed_when_replacement_is_unauthorised():
    candidates = _cands()
    comparison = {
        "utility_pick": {
            "actor_id": "npc-a",
            "move_kind": "gather",
            "target_id": "p1",
            "replacement_authorised": False,
        }
    }

    selected, applied = living_cast_shadow.choose_live_move(
        candidates,
        candidates[0],
        comparison,
        enabled=True,
        run_seed="s",
        turn_number=2,
    )

    assert selected == candidates[0]
    assert applied is False


def test_replayability_forwards_live_feature_flag_and_keeps_shadow(monkeypatch, caplog):
    state, _ = replayability.init_new_story(
        genre="noir",
        role="detective",
        tone="gritty",
        difficulty="standard",
        scenario_id=None,
        custom_premise=None,
        custom_world_setup=None,
        run_seed="s",
        npc_seed_records=[
            {"name": "Mara", "source_type": "seed_record", "source_slot": 0}
        ],
    )
    seen = {}

    def spy_choose(candidates, heuristic_pick, comparison, *, enabled, **kwargs):
        seen["enabled"] = enabled
        seen["heuristic_pick"] = copy.deepcopy(heuristic_pick)
        selected = dict(heuristic_pick) if heuristic_pick else None
        seen["selected_move"] = copy.deepcopy(selected)
        return selected, False

    monkeypatch.setattr(ai_config, "ENABLE_UTILITY_AI_LIVE_SELECTION", True)
    monkeypatch.setattr(ai_config, "ENABLE_UTILITY_AI_DIAGNOSTIC_LOGS", True)
    monkeypatch.setattr(living_cast_shadow, "choose_live_move", spy_choose)
    with caplog.at_level(logging.INFO, logger=replayability.__name__):
        _, _, diagnostics, _, _ = replayability.prepare_action_turn(
            state,
            2,
            rolling_state={"scene": "dock", "npcs": [{"name": "Mara"}]},
        )

    assert seen["enabled"] is True
    assert seen["selected_move"] == seen["heuristic_pick"]
    assert diagnostics["utility_ai_live_selection_enabled"] is True
    assert diagnostics["utility_ai_live_selection_applied"] is False
    assert diagnostics["utility_ai_selected_live_winner_source"] == "heuristic"
    assert diagnostics["utility_ai_heuristic_winner_actor"] == seen["heuristic_pick"]["npc_id"]
    assert diagnostics["utility_ai_heuristic_winner_move"] == seen["heuristic_pick"]["move_kind"]
    assert diagnostics["utility_ai_heuristic_winner_target"] == seen["heuristic_pick"]["target_id"]
    assert "utility_ai_utility_winner_actor" in diagnostics
    assert "utility_ai_shadow_agreement" in diagnostics
    assert "utility_ai_shadow_divergence" in diagnostics
    assert "utility_ai_shadow_comparison" in diagnostics
    assert any(
        "Utility AI live-selection diagnostic" in record.getMessage()
        and "utility_ai_selected_live_winner_source" in record.getMessage()
        for record in caplog.records
    )


def test_replayability_logs_no_eligible_utility_ai_candidates(monkeypatch, caplog):
    state = {"run_seed": "s", "npc_agendas": {"agendas": []}}

    monkeypatch.setattr(ai_config, "ENABLE_UTILITY_AI_LIVE_SELECTION", True)
    monkeypatch.setattr(ai_config, "ENABLE_UTILITY_AI_DIAGNOSTIC_LOGS", True)
    with caplog.at_level(logging.INFO, logger=replayability.__name__):
        _, _, diagnostics, _, _ = replayability.prepare_action_turn(
            state,
            2,
            rolling_state={"scene": "empty dock", "npcs": []},
        )

    assert diagnostics["utility_ai_shadow_comparison_exists"] is True
    assert diagnostics["utility_ai_shadow_candidate_count"] == 0
    assert diagnostics["utility_ai_live_selection_enabled"] is True
    assert diagnostics["utility_ai_live_selection_applied"] is False
    assert diagnostics["utility_ai_selected_live_winner_source"] == "heuristic"
    assert any(
        "Utility AI live-selection diagnostic: no eligible NPC move candidates this turn"
        in record.getMessage()
        for record in caplog.records
    )


def test_replayability_live_handoff_proof_commits_utility_winner(monkeypatch):
    state, rolling = _proof_state_and_rolling()
    heuristic_move, candidates = npc_world_moves.select_npc_move(
        PROOF_SEED,
        state["npc_agendas"],
        rolling,
        state,
        state["identity"],
        2,
    )
    assert heuristic_move
    assert len(candidates) == 2

    monkeypatch.setattr(ai_config, "ENABLE_UTILITY_AI_LIVE_SELECTION", True)
    updated, _, diagnostics, _, _ = replayability.prepare_action_turn(
        state,
        2,
        rolling_state=rolling,
    )

    comparison = diagnostics["utility_ai_shadow_comparison"]
    utility_pick = comparison["utility_pick"]
    receipt = updated["npc_move_receipts"][0]

    assert diagnostics["utility_ai_shadow_candidate_count"] == 2
    assert diagnostics["utility_ai_live_selection_enabled"] is True
    assert diagnostics["utility_ai_replacement_authorised"] is True
    assert diagnostics["utility_ai_live_selection_applied"] is True
    assert diagnostics["utility_ai_selected_live_winner_source"] == "utility_ai"
    assert diagnostics.get("utility_ai_replacement_blocker_code") is None
    assert diagnostics["utility_ai_heuristic_winner_actor"] == heuristic_move["npc_id"]
    assert diagnostics["utility_ai_heuristic_winner_move"] == heuristic_move["move_kind"]
    assert diagnostics["utility_ai_heuristic_winner_target"] == heuristic_move["target_id"]
    assert diagnostics["utility_ai_utility_winner_actor"] == utility_pick["actor_id"]
    assert diagnostics["utility_ai_utility_winner_move"] == utility_pick["move_kind"]
    assert diagnostics["utility_ai_utility_winner_target"] == utility_pick["target_id"]
    assert diagnostics["utility_ai_committed_move_receipt_id"] == receipt["receipt_id"]
    assert diagnostics["utility_ai_selected_move_receipt_id"] == receipt["receipt_id"]
    assert receipt["npc_id"] == utility_pick["actor_id"]
    assert receipt["move_kind"] == utility_pick["move_kind"]
    assert receipt["target_id"] == utility_pick["target_id"]


def test_replayability_live_handoff_disagreement_commits_utility_winner(monkeypatch):
    state, rolling = _proof_state_and_rolling(
        run_seed=DISAGREEMENT_PROOF_SEED,
        goal_kind="repay_debt",
    )
    heuristic_move, candidates = npc_world_moves.select_npc_move(
        DISAGREEMENT_PROOF_SEED,
        state["npc_agendas"],
        rolling,
        state,
        state["identity"],
        2,
    )
    assert heuristic_move
    assert len(candidates) == 2

    monkeypatch.setattr(ai_config, "ENABLE_UTILITY_AI_LIVE_SELECTION", True)
    updated, _, diagnostics, _, _ = replayability.prepare_action_turn(
        state,
        2,
        rolling_state=rolling,
    )

    comparison = diagnostics["utility_ai_shadow_comparison"]
    heuristic_pick = comparison["heuristic_pick"]
    utility_pick = comparison["utility_pick"]
    receipt = updated["npc_move_receipts"][0]

    assert diagnostics["utility_ai_shadow_candidate_count"] == 2
    assert heuristic_pick["move_kind"] == "negotiate"
    assert heuristic_pick["target_id"] == "faction-0d0d2e740e7a"
    assert utility_pick["move_kind"] == "gather"
    assert utility_pick["target_id"] == "pressure-resource-proof"
    assert heuristic_pick["move_kind"] != utility_pick["move_kind"]
    assert utility_pick["replacement_authorised"] is True
    assert diagnostics["utility_ai_replacement_authorised"] is True
    assert diagnostics["utility_ai_shadow_agreement"] is False
    assert diagnostics["utility_ai_shadow_divergence"] is True
    assert diagnostics["utility_ai_live_selection_enabled"] is True
    assert diagnostics["utility_ai_live_selection_applied"] is True
    assert diagnostics["utility_ai_selected_live_winner_source"] == "utility_ai"
    assert diagnostics.get("utility_ai_replacement_blocker_code") is None
    assert diagnostics["utility_ai_heuristic_winner_move"] == "negotiate"
    assert diagnostics["utility_ai_utility_winner_move"] == "gather"
    assert diagnostics["utility_ai_committed_move_receipt_id"] == receipt["receipt_id"]
    assert diagnostics["utility_ai_selected_move_receipt_id"] == receipt["receipt_id"]
    assert receipt["receipt_id"] == "npc-move-d0ef8b9826d5"
    assert receipt["npc_id"] == utility_pick["actor_id"]
    assert receipt["move_kind"] == utility_pick["move_kind"]
    assert receipt["target_id"] == utility_pick["target_id"]
    assert receipt["move_kind"] != heuristic_move["move_kind"]
