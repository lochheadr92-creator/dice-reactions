"""
Chapter 33 structured clock seam — acceptance-hardening tests.

1. Non-adjacent duplicate time-event idempotency (A -> B -> A).
2. pending_time_advance consumption across a real turn.
3. No clock/lifecycle/probability leakage into player payloads or the prompt.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import ai_config  # noqa: E402
import gateway  # noqa: E402
import npc_lifecycle as L  # noqa: E402
import player_api  # noqa: E402
import replayability  # noqa: E402
import simulation_clock as C  # noqa: E402

SEED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
Y = L.DAYS_PER_SIMULATION_YEAR


def _clock(day=0, processed=0):
    return {"schema_version": 1, "current_simulation_day": day,
            "last_applied_advance_event_id": None, "recent_advance_event_ids": [],
            "lifecycle_processed_through_day": processed}


def _rec(npc_id, *, age_years, **extra):
    r = {"schema_version": 1, "npc_id": npc_id, "birth_simulation_day": -age_years * Y,
         "lifecycle_profile": "human", "alive": True, "death_simulation_day": None,
         "death_cause": None, "last_mortality_evaluation_day": None,
         "life_stage": L.life_stage(-age_years * Y, 0)}
    r.update(extra)
    return r


def _advance(event_id, days=Y):
    return {"event_id": event_id, "elapsed_simulation_days": days, "reason": "r", "source_type": "test"}


# 1. Non-adjacent duplicate protection --------------------------------------- #
def test_non_adjacent_duplicate_time_event_rejected():
    clk = _clock()
    clk, _ = C.apply_time_advance(clk, _advance("A", 10))
    clk, _ = C.apply_time_advance(clk, _advance("B", 10))
    day = clk["current_simulation_day"]                       # 20 (A applied first, then B)
    clk, dA = C.apply_time_advance(clk, _advance("A", 10))    # reapply the OLDER event A
    assert dA["duplicate"] is True
    assert clk["current_simulation_day"] == day               # no advance from the stale event


def test_recent_receipt_is_bounded():
    clk = _clock()
    for i in range(C.MAX_ADVANCE_EVENT_RECEIPTS + 20):
        clk, _ = C.apply_time_advance(clk, _advance(f"e{i}", 1))
    assert len(clk["recent_advance_event_ids"]) == C.MAX_ADVANCE_EVENT_RECEIPTS  # bounded, no unbounded log


# 2. pending_time_advance consumption over a real turn ----------------------- #
def test_pending_advance_consumed_and_next_ordinary_turn_zero(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_NPC_LIFECYCLE", True)
    base, _ = replayability.init_new_story(
        genre="noir", role="detective", tone="gritty", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=SEED)
    base["simulation_clock"] = _clock()
    base["npc_lifecycle"] = {"Mara": _rec("Mara", age_years=30)}
    base["pending_time_advance"] = _adv_exp("adv-1", Y, 0)
    rolling = {"npcs": [{"npc_id": "Mara", "name": "Mara"}]}

    s1, _, _, _, _ = replayability.prepare_action_turn(copy.deepcopy(base), 2, rolling_state=copy.deepcopy(rolling))
    assert s1["simulation_clock"]["current_simulation_day"] == Y
    assert "pending_time_advance" not in s1                    # consumed, not a lingering instruction

    # next ordinary turn on the resulting state -> zero advance, no lifecycle work
    s2, _, d2, _, _ = replayability.prepare_action_turn(copy.deepcopy(s1), 3, rolling_state=copy.deepcopy(rolling))
    assert s2["simulation_clock"]["current_simulation_day"] == Y
    assert d2["lifecycle"]["due"] is False

    # even if the SAME advance event is re-staged, durable idempotency blocks it
    restaged = copy.deepcopy(s1)
    restaged["pending_time_advance"] = _adv_exp("adv-1", Y, 0)
    s3, _, d3, _, _ = replayability.prepare_action_turn(restaged, 4, rolling_state=copy.deepcopy(rolling))
    assert s3["simulation_clock"]["current_simulation_day"] == Y
    assert d3["simulation_clock"]["duplicate"] is True


# 3. Leakage -------------------------------------------------------------------#
_LEAK_TOKENS = ("simulation_clock", "npc_lifecycle", "pending_time_advance",
                "lifecycle_processed_through_day", "recent_advance_event_ids",
                "mortality_probabilities", "mortality_rolls", "current_simulation_day")


def test_player_turn_payload_excludes_clock_and_lifecycle_diagnostics():
    turn = {"id": "t1", "session_id": "s1", "turn_number": 2, "player_action": "wait",
            "narrative": "You wait.", "paragraphs": ["You wait."], "choices": [],
            "state": {}, "ledger": {},
            "debug": {"simulation_clock": {"current_simulation_day": 365, "duplicate": False},
                      "lifecycle": {"mortality_probabilities": {"Old": 0.9}, "mortality_rolls": {"Old": 0.1},
                                    "death_event_ids": ["lifeevt-x"]},
                      "simulation_lifecycle_error": None}}
    blob = json.dumps(player_api.build_player_turn(turn))
    assert "debug" not in blob
    for tok in _LEAK_TOKENS + ("0.9", "0.1", "lifeevt"):
        assert tok not in blob


def test_player_session_payload_excludes_replayability_state():
    session = {"id": "s1", "genre": "noir", "title": "x", "turn_count": 3,
               "replayability_state": {
                   "simulation_clock": _clock(day=365),
                   "npc_lifecycle": {"Old": {"alive": False, "death_cause": "natural_causes"}},
                   "pending_time_advance": _advance("A")}}
    blob = json.dumps(player_api.build_player_session(session))
    assert "replayability_state" not in blob
    for tok in _LEAK_TOKENS + ("natural_causes",):
        assert tok not in blob


def test_prompt_truth_block_ignores_clock_and_lifecycle_state():
    # Even if engine-internal keys somehow sat in rolling_state, the prompt block
    # renders only terminal objects / deceased names / injuries.
    rolling = {"deceased": ["Old"], "simulation_clock": _clock(day=365),
               "npc_lifecycle": {"Old": {"death_cause": "natural_causes"}},
               "pending_time_advance": _advance("A")}
    block = gateway.build_immutable_truth_block(rolling)
    assert "Old" in block                                      # deceased NAME is asserted (correct)
    # (Note: the block legitimately contains the word "rolling_state" in its
    # standard instruction text; only lifecycle/clock identifiers are leaks.)
    for tok in _LEAK_TOKENS + ("natural_causes",):
        assert tok not in block


def test_seam_adds_no_clock_or_lifecycle_keys_to_rolling_state(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_NPC_LIFECYCLE", True)
    rolling = {"npcs": [{"npc_id": "Old", "name": "Old"}], "deceased": []}
    state = {"run_seed": "s", "simulation_clock": _clock(day=130 * Y, processed=129 * Y),
             "npc_lifecycle": {"Old": _rec("Old", age_years=130, last_mortality_evaluation_day=129 * Y)},
             "pending_time_advance": _adv_exp("e", Y, 130 * Y)}
    _, out_rolling, _ = C.integrate_turn(state, rolling, run_seed="s", turn_number=2)
    for k in ("simulation_clock", "npc_lifecycle", "pending_time_advance",
              "mortality_probabilities", "lifecycle_processed_through_day"):
        assert k not in out_rolling                            # prompt source stays clean
    assert "Old" in out_rolling["deceased"]                    # only the deceased projection lands here


# 4. Permanent replay barrier (expected-clock-state precondition) ------------- #
def _adv_exp(event_id, days, expected_prev, target=None):
    a = {"event_id": event_id, "elapsed_simulation_days": days, "reason": "r",
         "source_type": "test", "expected_previous_simulation_day": expected_prev}
    if target is not None:
        a["target_simulation_day"] = target
    return a


def test_evicted_event_blocked_by_expected_day_precondition():
    clk = _clock()
    clk, _ = C.apply_time_advance(clk, _adv_exp("A", 10, 0))
    for i in range(C.MAX_ADVANCE_EVENT_RECEIPTS + 1):          # 65 unique valid events
        cur = clk["current_simulation_day"]
        clk, _ = C.apply_time_advance(clk, _adv_exp(f"e{i}", 1, cur))
    assert "A" not in clk["recent_advance_event_ids"]          # evicted from the bounded window
    day = clk["current_simulation_day"]
    clk, dA = C.apply_time_advance(clk, _adv_exp("A", 10, 0))  # replay the evicted event
    assert dA["duplicate"] is True and dA["stale"] is True
    assert clk["current_simulation_day"] == day                # permanent: no advance


def test_out_of_order_and_target_mismatch_rejected():
    clk = _clock(day=100)
    clk, d = C.apply_time_advance(clk, _adv_exp("F", 5, 500))  # expects day 500, clock is 100
    assert d["validation_failure"] == "expected_day_ahead" and clk["current_simulation_day"] == 100
    clk, d2 = C.apply_time_advance(clk, _adv_exp("G", 5, 100, target=999))
    assert d2["validation_failure"] == "target_day_mismatch" and clk["current_simulation_day"] == 100


def test_ordered_stream_replay_is_identical():
    stream = [_adv_exp("A", 10, 0), _adv_exp("B", 5, 10), _adv_exp("C", 7, 15)]

    def run():
        clk = _clock()
        for ev in stream:
            clk, _ = C.apply_time_advance(clk, ev)
        return clk

    assert run() == run() and run()["current_simulation_day"] == 22


def test_evicted_replay_blocked_via_real_turn_seam(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_NPC_LIFECYCLE", True)
    rolling = {"npcs": []}
    state = {"run_seed": "s", "simulation_clock": _clock()}
    state["pending_time_advance"] = _adv_exp("A", 10, 0)
    state, _, _ = C.integrate_turn(state, dict(rolling), run_seed="s", turn_number=1)
    for i in range(C.MAX_ADVANCE_EVENT_RECEIPTS + 1):          # evict A through the real seam
        cur = state["simulation_clock"]["current_simulation_day"]
        state["pending_time_advance"] = _adv_exp(f"e{i}", 1, cur)
        state, _, _ = C.integrate_turn(state, dict(rolling), run_seed="s", turn_number=2 + i)
    assert "A" not in state["simulation_clock"]["recent_advance_event_ids"]
    day = state["simulation_clock"]["current_simulation_day"]
    state["pending_time_advance"] = _adv_exp("A", 10, 0)       # replay the evicted event via the seam
    state, _, diag = C.integrate_turn(state, dict(rolling), run_seed="s", turn_number=999)
    assert state["simulation_clock"]["current_simulation_day"] == day
    assert diag["simulation_clock"]["duplicate"] is True and diag["simulation_clock"]["stale"] is True
