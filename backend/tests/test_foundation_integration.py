import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import foundation_integration
import replayability
from engine_determinism import canonical_json
from engine_projection import forbid_player_projection, project_foundation_prepared


def test_identical_snapshot_byte_equivalent_outputs():
    rolling = {
        "npcs": [{"name": "Ava", "npc_id": "ava-1", "stance": "ally", "last_seen": "yard"}],
        "scene": "yard",
        "npc_memory": [
            {
                "name": "Ava",
                "remembers": [{"summary": "trade", "since_turn": 1, "weight": "moderate"}],
            }
        ],
    }
    replay = replayability.empty_replayability_state()
    replay["run_seed"] = "foundation-seed"
    b1, _ = foundation_integration.evaluate_foundation_turn(
        run_seed="foundation-seed",
        turn_sequence=4,
        rolling_state=rolling,
        replayability_state=replay,
    )
    b2, _ = foundation_integration.evaluate_foundation_turn(
        run_seed="foundation-seed",
        turn_sequence=4,
        rolling_state=rolling,
        replayability_state=replay,
    )
    assert canonical_json(b1) == canonical_json(b2)


def test_failed_prepare_does_not_persist_foundation_state():
    replay = replayability.empty_replayability_state()
    replay["run_seed"] = "seed"
    cleared = foundation_integration.clear_prepared(replay)
    assert "foundation_prepared_v1" not in cleared


def test_internal_traces_not_player_safe():
    rolling = {"npcs": [{"name": "A", "npc_id": "a1"}]}
    replay = replayability.empty_replayability_state()
    replay["run_seed"] = "seed"
    bundle, _ = foundation_integration.evaluate_foundation_turn(
        run_seed="seed",
        turn_sequence=2,
        rolling_state=rolling,
        replayability_state=replay,
    )
    projection = project_foundation_prepared(bundle)
    assert forbid_player_projection(projection) is None
    assert "utility_score_table" not in projection


def _memory_rolling():
    return {
        "npcs": [{"name": "Ava", "npc_id": "ava-1", "stance": "ally", "last_seen": "yard"}],
        "scene": "yard",
        "npc_memory": [
            {"name": "Ava", "remembers": [{"summary": "trade", "since_turn": 1, "weight": "major"}]}
        ],
    }


def test_memory_retrieval_authority_legacy_when_flag_off():
    # Default flags: memory authority is legacy and prompt injection is blocked;
    # the shadow eval still runs (shadow_mode True) but never feeds the prompt.
    replay = replayability.empty_replayability_state()
    replay["run_seed"] = "seed"
    bundle, diag = foundation_integration.evaluate_foundation_turn(
        run_seed="seed",
        turn_sequence=2,
        rolling_state=_memory_rolling(),
        replayability_state=replay,
    )
    assert bundle["retrieval"]["shadow_mode"] is True
    assert diag["foundation_authority"]["memory"] == "legacy"
    assert (
        diag["memory_retrieval_promotion"]["memory_retrieval_blocker_code"]
        == "SEPARATE_SHADOW_ACCEPTANCE_REQUIRED"
    )


def test_memory_retrieval_blocker_holds_at_seam_with_flag_on(monkeypatch):
    # Dangerous operator case: canonical Memory Retrieval flag ON, acceptance
    # constant still default False. The seam must keep retrieval in shadow_mode
    # (fail-closed), surface the blocker, and never promote memory to canonical.
    import ai_config

    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_MEMORY_RETRIEVAL", True)
    replay = replayability.empty_replayability_state()
    replay["run_seed"] = "seed"
    bundle, diag = foundation_integration.evaluate_foundation_turn(
        run_seed="seed",
        turn_sequence=4,
        rolling_state=_memory_rolling(),
        replayability_state=replay,
    )
    assert bundle["retrieval"]["shadow_mode"] is True          # prompt injection blocked
    mrp = diag["memory_retrieval_promotion"]
    assert mrp["memory_retrieval_enabled"] is True
    assert mrp["memory_retrieval_prompt_injection_allowed"] is False
    assert mrp["memory_retrieval_blocker_code"] == "SEPARATE_SHADOW_ACCEPTANCE_REQUIRED"
    assert diag["foundation_authority"]["memory"] == "shadow_diagnostics"
    # Even with the flag ON, nothing player-facing is exposed.
    assert forbid_player_projection(project_foundation_prepared(bundle)) is None


def test_flag_on_seam_is_deterministic(monkeypatch):
    import ai_config

    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_MEMORY_RETRIEVAL", True)
    replay = replayability.empty_replayability_state()
    replay["run_seed"] = "seed"
    b1, _ = foundation_integration.evaluate_foundation_turn(
        run_seed="seed", turn_sequence=4, rolling_state=_memory_rolling(), replayability_state=replay
    )
    b2, _ = foundation_integration.evaluate_foundation_turn(
        run_seed="seed", turn_sequence=4, rolling_state=_memory_rolling(), replayability_state=replay
    )
    assert canonical_json(b1) == canonical_json(b2)