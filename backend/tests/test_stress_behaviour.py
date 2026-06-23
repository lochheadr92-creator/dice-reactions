"""
Ch 14 P2 — stress behavioural bands + Utility AI integration (shadow-only).

Two layers:
  * pure classification  (stress.evaluate_stress_behaviour / apply weights)
  * Utility AI integration (utility_ai.select_action band modifiers + fail-closed)

Every numeric cut-point/modifier is a DESIGNED_EXTENSION (ADR-022); Chapter 14 is
non-numerical. These tests pin the exact thresholds, the exactly-once application
point, the fail-closed contract, and determinism / hash stability.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import stress
import utility_ai
from engine_determinism import canonical_json
from foundation_snapshot import FoundationTurnSnapshot


# --------------------------------------------------------------------------- #
# Pure layer — band classification + boundaries
# --------------------------------------------------------------------------- #
def _band(level):
    return stress.evaluate_stress_behaviour(level)["band"]


def test_floor_zero_is_calm_and_ceiling_100_is_overloaded():
    assert _band(0.0) == "CALM"
    assert _band(100.0) == "OVERLOADED"


def test_exact_thresholds_are_inclusive_lower_bounds():
    assert _band(25.0) == "ELEVATED"
    assert _band(50.0) == "STRAINED"
    assert _band(75.0) == "OVERLOADED"


def test_just_below_thresholds():
    assert _band(24.999) == "CALM"
    assert _band(49.999) == "ELEVATED"
    assert _band(74.999) == "STRAINED"


def test_just_above_thresholds():
    assert _band(25.001) == "ELEVATED"
    assert _band(50.001) == "STRAINED"
    assert _band(75.001) == "OVERLOADED"


@pytest.mark.parametrize("level", [0.0, 25.0, 50.0, 75.0, 100.0, 12.5, 99.9])
def test_in_range_values_are_valid(level):
    res = stress.evaluate_stress_behaviour(level)
    assert res["valid"] is True
    assert res["band"] in {"CALM", "ELEVATED", "STRAINED", "OVERLOADED"}
    assert res["blocker_code"] is None
    assert res["stress_level"] == level


# --------------------------------------------------------------------------- #
# Pure layer — fail closed on every invalid input
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value,code",
    [
        (None, stress.MISSING_STRESS_LEVEL),
        (True, stress.INVALID_STRESS_LEVEL),
        (False, stress.INVALID_STRESS_LEVEL),
        ("50", stress.INVALID_STRESS_LEVEL),
        ("high", stress.INVALID_STRESS_LEVEL),
        ([], stress.INVALID_STRESS_LEVEL),
        ({}, stress.INVALID_STRESS_LEVEL),
        (float("nan"), stress.NONFINITE_STRESS_LEVEL),
        (float("inf"), stress.NONFINITE_STRESS_LEVEL),
        (float("-inf"), stress.NONFINITE_STRESS_LEVEL),
        (-0.001, stress.OUT_OF_RANGE_STRESS_LEVEL),
        (-5, stress.OUT_OF_RANGE_STRESS_LEVEL),
        (100.001, stress.OUT_OF_RANGE_STRESS_LEVEL),
        (150, stress.OUT_OF_RANGE_STRESS_LEVEL),
    ],
)
def test_invalid_inputs_emit_distinct_blocker_codes(value, code):
    assert stress.evaluate_stress_behaviour(value)["blocker_code"] == code


@pytest.mark.parametrize(
    "value",
    [None, True, False, "50", "high", [], {}, float("nan"), float("inf"),
     float("-inf"), -0.001, -5, 100.001, 150],
)
def test_invalid_inputs_have_no_band_and_are_never_calm(value):
    res = stress.evaluate_stress_behaviour(value)
    assert res["valid"] is False
    assert res["band"] is None
    assert res["band"] != "CALM"
    assert res["stress_level"] is None
    # identity (x1.0) modifiers so a naive multiplier leaves weights unchanged
    assert res["modifiers"] == stress.STRESS_WEIGHT_MODIFIERS[stress.StressBand.CALM]


def test_missing_blocker_code_is_preserved_constant():
    assert stress.MISSING_STRESS_LEVEL == "MISSING_STRESS_LEVEL"
    assert stress.evaluate_stress_behaviour(None)["blocker_code"] == "MISSING_STRESS_LEVEL"


# --------------------------------------------------------------------------- #
# Pure layer — modifier profiles + determinism
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "level,band",
    [(0.0, "CALM"), (30.0, "ELEVATED"), (60.0, "STRAINED"), (90.0, "OVERLOADED")],
)
def test_modifier_profiles_match_table(level, band):
    res = stress.evaluate_stress_behaviour(level)
    assert res["band"] == band
    assert res["modifiers"] == stress.STRESS_WEIGHT_MODIFIERS[stress.StressBand(band)]


def test_calm_modifiers_are_all_identity():
    assert all(v == 1.0 for v in stress.STRESS_WEIGHT_MODIFIERS[stress.StressBand.CALM].values())


def test_stress_reduction_modifier_is_identity_in_every_band():
    for band in stress.StressBand:
        assert stress.STRESS_WEIGHT_MODIFIERS[band]["stress_reduction"] == 1.0


def test_higher_bands_narrow_goal_and_raise_survival():
    mods = stress.STRESS_WEIGHT_MODIFIERS
    goal = [mods[b]["goal_progression"] for b in
            (stress.StressBand.CALM, stress.StressBand.ELEVATED,
             stress.StressBand.STRAINED, stress.StressBand.OVERLOADED)]
    surv = [mods[b]["survival"] for b in
            (stress.StressBand.CALM, stress.StressBand.ELEVATED,
             stress.StressBand.STRAINED, stress.StressBand.OVERLOADED)]
    assert goal == sorted(goal, reverse=True) and goal[0] > goal[-1]
    assert surv == sorted(surv) and surv[-1] > surv[0]


def test_pure_layer_is_deterministic():
    assert stress.evaluate_stress_behaviour(42.0) == stress.evaluate_stress_behaviour(42.0)


# --------------------------------------------------------------------------- #
# apply_stress_band_modifiers — exactly once, identity-preserving
# --------------------------------------------------------------------------- #
def _base_weights():
    return dict(utility_ai.BASE_WEIGHTS)


def test_modifiers_applied_exactly_once_not_squared():
    base = _base_weights()
    mods = stress.STRESS_WEIGHT_MODIFIERS[stress.StressBand.OVERLOADED]
    once = utility_ai.apply_stress_band_modifiers(base, mods)
    assert once["goal_progression"] == pytest.approx(base["goal_progression"] * 0.30)
    assert once["survival"] == pytest.approx(base["survival"] * 1.60)
    # a second application would square the modifier — guard against it
    assert once["goal_progression"] != pytest.approx(base["goal_progression"] * 0.30 * 0.30)


def test_calm_modifiers_leave_weights_bit_identical():
    base = _base_weights()
    out = utility_ai.apply_stress_band_modifiers(
        base, stress.STRESS_WEIGHT_MODIFIERS[stress.StressBand.CALM]
    )
    assert out == base


def test_apply_keeps_stress_reduction_weight_unchanged():
    base = {k: 10.0 for k in utility_ai.DIMENSION_ORDER}
    for band in stress.StressBand:
        out = utility_ai.apply_stress_band_modifiers(base, stress.STRESS_WEIGHT_MODIFIERS[band])
        assert out["stress_reduction"] == 10.0


# --------------------------------------------------------------------------- #
# Utility AI integration — fixtures
# --------------------------------------------------------------------------- #
VARIED_SCORES = {
    "survival": 90.0,
    "goal_progression": 10.0,
    "pressure_relief": 60.0,
    "stress_reduction": 50.0,
    "relationship_impact": 40.0,
    "resource_gain_loss": 30.0,
    "memory_avoidance": 70.0,
}


def _ar(actor_id="npc-a"):
    return {"acting_actor_ids": [actor_id], "tiers_by_actor_id": {actor_id: "hero"}}


def _snapshot_with_stress(level, actor_id="npc-a"):
    rolling = {"npcs": [{"npc_id": actor_id, "name": "Mara"}]}
    if level is not None:
        rolling["actor_stress"] = {actor_id: {"stress_level": level, "capacity": 1.0}}
    replay = {
        "run_seed": "s",
        "pressure_graph": {"nodes": [{"id": "p1", "status": "active", "magnitude": 50}]},
        "npc_agendas": {"agendas": [{"npc_id": actor_id, "goal_kind": "escape_danger"}]},
    }
    return FoundationTurnSnapshot.build(
        run_seed="s", turn_sequence=1, rolling_state=rolling, replayability_state=replay
    )


def _candidate(actor_id="npc-a", action="withdraw", target_id="loc-1",
               replacement_authorised=True, scores=None):
    return {
        "actor_id": actor_id,
        "action_kind": action,
        "target_kind": "location",
        "target_id": target_id,
        "dimension_scores": dict(scores or VARIED_SCORES),
        "replacement_authorised": replacement_authorised,
        "personality_order": [action],
    }


def _canonical_base_utility():
    """Pre-band canonical utility for a default-input candidate with VARIED_SCORES."""
    weights = utility_ai.compute_dimension_weights()
    return utility_ai.compute_utility_score(VARIED_SCORES, weights)


# --------------------------------------------------------------------------- #
# Integration — CALM baseline equivalence, exactly-once, narrowing
# --------------------------------------------------------------------------- #
def test_calm_is_baseline_equivalent():
    res = utility_ai.select_action(
        [_candidate()], snapshot=_snapshot_with_stress(0.0), actor_resolution=_ar()
    )
    sel = res["selected"]
    assert sel["stress_band"] == "CALM"
    assert sel["stress_input_valid"] is True
    assert sel["base_utility"] == pytest.approx(_canonical_base_utility())


def test_integration_applies_band_modifiers_exactly_once():
    res = utility_ai.select_action(
        [_candidate()], snapshot=_snapshot_with_stress(90.0), actor_resolution=_ar()
    )
    once_weights = utility_ai.apply_stress_band_modifiers(
        utility_ai.compute_dimension_weights(),
        stress.STRESS_WEIGHT_MODIFIERS[stress.StressBand.OVERLOADED],
    )
    expected_once = utility_ai.compute_utility_score(VARIED_SCORES, once_weights)
    twice_weights = utility_ai.apply_stress_band_modifiers(
        once_weights, stress.STRESS_WEIGHT_MODIFIERS[stress.StressBand.OVERLOADED]
    )
    expected_twice = utility_ai.compute_utility_score(VARIED_SCORES, twice_weights)
    assert res["selected"]["base_utility"] == pytest.approx(expected_once)
    assert res["selected"]["base_utility"] != pytest.approx(expected_twice)


def test_higher_band_narrows_weighting_without_changing_scores():
    calm = utility_ai.select_action(
        [_candidate()], snapshot=_snapshot_with_stress(0.0), actor_resolution=_ar()
    )["selected"]
    over = utility_ai.select_action(
        [_candidate()], snapshot=_snapshot_with_stress(90.0), actor_resolution=_ar()
    )["selected"]
    # weighting shifted toward survival (high score) -> utility moves; dimension
    # scores themselves are untouched (same candidate input both times).
    assert over["base_utility"] != pytest.approx(calm["base_utility"])
    assert over["base_utility"] > calm["base_utility"]


def test_band_does_not_directly_force_an_action():
    # Two distinct candidates; selection must remain the noisy-utility argmax,
    # never a band-dictated action.
    high = _candidate(action="withdraw", target_id="loc-1", scores={k: 80.0 for k in utility_ai.DIMENSION_ORDER})
    low = _candidate(action="pressure", target_id="loc-2", scores={k: 20.0 for k in utility_ai.DIMENSION_ORDER})
    res = utility_ai.select_action(
        [high, low], snapshot=_snapshot_with_stress(90.0), actor_resolution=_ar()
    )
    top = res["score_table"][0]
    assert res["candidates_evaluated"] == 2
    assert res["selected"]["action_kind"] == top["action_kind"]
    assert res["selected"]["action_kind"] == "withdraw"  # higher utility wins, not forced


# --------------------------------------------------------------------------- #
# Integration — fail closed
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("level", [None])
def test_missing_stress_forces_replacement_unauthorised(level):
    res = utility_ai.select_action(
        [_candidate(replacement_authorised=True)],
        snapshot=_snapshot_with_stress(level),
        actor_resolution=_ar(),
    )
    sel = res["selected"]
    assert sel["replacement_authorised"] is False
    assert sel["stress_input_valid"] is False
    assert sel["stress_band"] is None
    assert sel["stress_blocker_code"] == "MISSING_STRESS_LEVEL"


def test_invalid_stress_never_labelled_calm_in_integration():
    res = utility_ai.select_action(
        [_candidate(replacement_authorised=True)],
        snapshot=_snapshot_with_stress(None),
        actor_resolution=_ar(),
    )
    for row in res["score_table"]:
        assert row["stress_band"] is None
        assert row["stress_band"] != "CALM"


def test_valid_band_cannot_authorise_an_unauthorised_candidate():
    # baseline replacement_authorised False + valid OVERLOADED band -> stays False
    # (no maximum/emergency bonus), but the candidate is still visible in shadow.
    res = utility_ai.select_action(
        [_candidate(replacement_authorised=False)],
        snapshot=_snapshot_with_stress(90.0),
        actor_resolution=_ar(),
    )
    sel = res["selected"]
    assert sel["stress_band"] == "OVERLOADED"
    assert sel["stress_input_valid"] is True
    assert sel["replacement_authorised"] is False
    assert any(r["actor_id"] == "npc-a" for r in res["score_table"])


def test_valid_stress_preserves_baseline_authorisation():
    auth = utility_ai.select_action(
        [_candidate(replacement_authorised=True)],
        snapshot=_snapshot_with_stress(30.0),
        actor_resolution=_ar(),
    )["selected"]
    assert auth["stress_input_valid"] is True
    assert auth["replacement_authorised"] is True


# --------------------------------------------------------------------------- #
# Integration — determinism, candidate hash / noise / state hash stability
# --------------------------------------------------------------------------- #
def test_same_inputs_produce_identical_output():
    snap = _snapshot_with_stress(90.0)
    r1 = utility_ai.select_action([_candidate()], snapshot=snap, actor_resolution=_ar())
    r2 = utility_ai.select_action([_candidate()], snapshot=snap, actor_resolution=_ar())
    assert canonical_json(r1) == canonical_json(r2)


def test_candidate_hash_and_noise_are_band_independent():
    results = {
        lvl: utility_ai.select_action(
            [_candidate()], snapshot=_snapshot_with_stress(lvl), actor_resolution=_ar()
        )
        for lvl in (0.0, 30.0, 60.0, 90.0, None)
    }
    # candidate_set_hash derives from the raw candidate only -> identical
    assert len({r["candidate_set_hash"] for r in results.values()}) == 1
    # the whim-noise DRAW is seeded from the candidate hash, not the band:
    # noisy - base must be the same value across all bands.
    noises = {round(r["selected"]["noisy_utility"] - r["selected"]["base_utility"], 12)
              for r in results.values()}
    assert len(noises) == 1


def test_calm_and_missing_share_state_hash_when_unauthorised():
    # identity modifiers in both -> byte-identical decision hash when the baseline
    # authorisation is already False (so the fail-closed gate changes nothing).
    calm = utility_ai.select_action(
        [_candidate(replacement_authorised=False)],
        snapshot=_snapshot_with_stress(0.0), actor_resolution=_ar(),
    )
    missing = utility_ai.select_action(
        [_candidate(replacement_authorised=False)],
        snapshot=_snapshot_with_stress(None), actor_resolution=_ar(),
    )
    assert calm["state_hash"] == missing["state_hash"]
    assert calm["selected"]["base_utility"] == pytest.approx(missing["selected"]["base_utility"])


def test_p2_diagnostic_keys_excluded_from_state_hash():
    # Adding the diagnostic keys to a row must not change the hash projection.
    row = {
        "actor_id": "a", "action_kind": "withdraw", "weights": {"survival": 100.0},
        "stress_band": "OVERLOADED", "stress_input_valid": True,
        "stress_blocker_code": None,
    }
    projected = utility_ai._hashable_candidate(row)
    assert "stress_band" not in projected
    assert "stress_input_valid" not in projected
    assert "stress_blocker_code" not in projected
    assert projected == {"actor_id": "a", "action_kind": "withdraw", "weights": {"survival": 100.0}}


def test_stress_free_legacy_candidate_is_baseline_equivalent():
    # No actor_stress in the snapshot (legacy/stress-free) -> identity weights,
    # canonical base utility, fail-closed authorisation, never CALM.
    res = utility_ai.select_action(
        [_candidate(replacement_authorised=False)],
        snapshot=_snapshot_with_stress(None),
        actor_resolution=_ar(),
    )
    sel = res["selected"]
    assert sel["base_utility"] == pytest.approx(_canonical_base_utility())
    assert sel["stress_band"] is None
    assert sel["stress_input_valid"] is False
    assert sel["stress_blocker_code"] == "MISSING_STRESS_LEVEL"


def test_utility_ai_remains_shadow_only_no_live_flip():
    # The P2 integration must not introduce any authoritative/live execution flag;
    # the selection stays a staged shadow decision.
    res = utility_ai.select_action(
        [_candidate()], snapshot=_snapshot_with_stress(90.0), actor_resolution=_ar()
    )
    forbidden = {"authoritative", "live", "load_bearing", "applied", "executed"}
    assert forbidden.isdisjoint(res.keys())
    assert forbidden.isdisjoint(res["selected"].keys())


# --------------------------------------------------------------------------- #
# P1 invariant — off-screen actor stress unchanged by P2 work
# --------------------------------------------------------------------------- #
def test_p1_offscreen_actor_retains_stress_unchanged():
    rolling = {"npcs": [{"npc_id": "npc-a", "name": "Mara"}]}
    pressure = {"nodes": [{"id": "p1", "status": "active", "magnitude": 70}]}
    in_scope = {"npc-a": {"goal_kind": "escape_danger"}}
    stress.update_actor_stress(rolling, pressure, run_seed="s", turn_sequence=1, agendas_by_actor=in_scope)
    held = rolling["actor_stress"]["npc-a"]["stress_level"]
    assert held > 0.0
    # off-screen next turn (empty interpretation set): no decay, no generation
    stress.update_actor_stress(rolling, pressure, run_seed="s", turn_sequence=2, agendas_by_actor={})
    assert rolling["actor_stress"]["npc-a"]["stress_level"] == held
