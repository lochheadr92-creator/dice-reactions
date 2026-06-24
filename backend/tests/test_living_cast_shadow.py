"""ADR-024 Phase 1 -- shadow comparison tests (pure function; no live handoff)."""
import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import living_cast_shadow
from foundation_snapshot import FoundationTurnSnapshot


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


def test_shadow_record_shape_and_scores():
    rec = living_cast_shadow.compare_move_scoring(_snap(), _cands(), _cands()[0])
    assert rec["shadow_schema_version"] == 1
    assert rec["candidate_count"] == 2
    assert rec["heuristic_pick"]["move_kind"] == "withdraw"
    assert len(rec["scores"]) == 2
    assert all("utility_score" in r and "heuristic_score" in r for r in rec["scores"])
    assert "agree" in rec
    assert "no action handoff" in rec["note"]


def test_shadow_is_pure_and_deterministic():
    snap, cands = _snap(), _cands()
    before = copy.deepcopy(cands)
    r1 = living_cast_shadow.compare_move_scoring(snap, cands, cands[0])
    r2 = living_cast_shadow.compare_move_scoring(snap, cands, cands[0])
    assert cands == before          # inputs not mutated
    assert r1 == r2                 # deterministic


def test_shadow_utility_pick_is_max_utility():
    rec = living_cast_shadow.compare_move_scoring(_snap(), _cands(), _cands()[0])
    scored = [r for r in rec["scores"] if r["utility_score"] is not None]
    if scored:
        best = max(s["utility_score"] for s in scored)
        assert rec["utility_pick"]["utility_score"] == best


def test_shadow_empty_candidates():
    rec = living_cast_shadow.compare_move_scoring(_snap(), [], None)
    assert rec["candidate_count"] == 0
    assert rec["utility_pick"] is None
    assert rec["agree"] is False


def test_shadow_reports_agreement_or_divergence_without_forcing():
    # both systems present -> 'agree' is a bool comparison only; no selection is made
    rec = living_cast_shadow.compare_move_scoring(_snap(), _cands(), _cands()[0])
    assert isinstance(rec["agree"], bool)
    # utility_pick is a *record*, not an applied action
    assert rec["utility_pick"] is None or set(rec["utility_pick"]) >= {"actor_id", "move_kind", "target_id", "utility_score"}
