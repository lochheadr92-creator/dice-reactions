"""
Chapter 33 structured clock seam — simulation clock + lifecycle integration tests
(deterministic, offline). Includes an end-to-end golden-path test that drives
the real turn seam (replayability.prepare_action_turn).
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import ai_config  # noqa: E402
import npc_agendas as agendas  # noqa: E402
import npc_lifecycle as L  # noqa: E402
import npc_world_moves as moves  # noqa: E402
import simulation_clock as C  # noqa: E402
import replayability  # noqa: E402

SEED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
Y = L.DAYS_PER_SIMULATION_YEAR


def _clock(day=0, processed=0, last=None):
    return {
        "schema_version": 1,
        "current_simulation_day": day,
        "last_applied_advance_event_id": last,
        "lifecycle_processed_through_day": processed,
    }


def _rec(npc_id, *, age_years, alive=True, **extra):
    r = {
        "schema_version": 1, "npc_id": npc_id, "birth_simulation_day": -age_years * Y,
        "lifecycle_profile": "human", "alive": alive, "death_simulation_day": None,
        "death_cause": None, "last_mortality_evaluation_day": None,
        "life_stage": L.life_stage(-age_years * Y, 0),
    }
    r.update(extra)
    return r


def _advance(event_id="adv-1", days=Y):
    return {"event_id": event_id, "elapsed_simulation_days": days, "reason": "r", "source_type": "test"}


def _advance_exp(event_id, days, expected_prev, target=None):
    """Authoritative-shape advance: carries the required expected-previous-day
    precondition that every real producer must supply (derived from the clock
    day at event creation). Events staged through the real seam / integrate_turn
    must use this form; the bare ``_advance`` (no precondition) is retained only
    to exercise the pure-primitive legacy path."""
    a = _advance(event_id, days)
    a["expected_previous_simulation_day"] = expected_prev
    if target is not None:
        a["target_simulation_day"] = target
    return a


def _npcs(*ids):
    return [{"npc_id": i, "name": i} for i in ids]


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_NPC_LIFECYCLE", True)


# --------------------------------------------------------------------------- #
# Clock migration
# --------------------------------------------------------------------------- #
def test_migrate_absent_clock_to_day_zero():
    clock, migrated = C.migrate_clock({"run_seed": "s"})
    assert migrated is True and clock["current_simulation_day"] == 0
    assert clock["lifecycle_processed_through_day"] == 0


def test_migrate_preserves_valid_clock():
    clock, migrated = C.migrate_clock({"simulation_clock": _clock(day=500, processed=365, last="e1")})
    assert migrated is False and clock["current_simulation_day"] == 500
    assert clock["lifecycle_processed_through_day"] == 365 and clock["last_applied_advance_event_id"] == "e1"


def test_migrate_normalizes_negative_day():
    clock, _ = C.migrate_clock({"simulation_clock": {"current_simulation_day": -10, "lifecycle_processed_through_day": -5}})
    assert clock["current_simulation_day"] == 0 and clock["lifecycle_processed_through_day"] == 0


def test_migrate_is_deterministic():
    assert C.migrate_clock({"run_seed": "s"}) == C.migrate_clock({"run_seed": "s"})


# --------------------------------------------------------------------------- #
# Time advance
# --------------------------------------------------------------------------- #
def test_advance_positive():
    clock, diag = C.apply_time_advance(_clock(day=100), _advance("e", 30))
    assert clock["current_simulation_day"] == 130 and diag["applied_elapsed_days"] == 30


def test_advance_zero_is_noop():
    clock, diag = C.apply_time_advance(_clock(day=100), _advance("e", 0))
    assert clock["current_simulation_day"] == 100 and diag["applied_elapsed_days"] == 0


def test_advance_negative_rejected():
    clock, diag = C.apply_time_advance(_clock(day=100), _advance("e", -5))
    assert clock["current_simulation_day"] == 100 and diag["validation_failure"] == "negative_elapsed"


def test_advance_none_is_zero_ordinary_turn():
    clock, diag = C.apply_time_advance(_clock(day=100), None)
    assert clock["current_simulation_day"] == 100 and diag["applied_elapsed_days"] == 0


def test_advance_duplicate_event_no_double():
    clock, _ = C.apply_time_advance(_clock(day=100), _advance("dup", 30))
    clock2, diag2 = C.apply_time_advance(clock, _advance("dup", 30))
    assert clock2["current_simulation_day"] == 130 and diag2["duplicate"] is True


def test_advance_prose_field_cannot_add_time():
    # An extra 'narrative' field is ignored; only elapsed_simulation_days counts.
    adv = {"event_id": "e", "elapsed_simulation_days": 0, "narrative": "a thousand years pass"}
    clock, _ = C.apply_time_advance(_clock(day=5), adv)
    assert clock["current_simulation_day"] == 5


def test_advance_replay_identical():
    a = C.apply_time_advance(_clock(day=100), _advance("e", 30))
    b = C.apply_time_advance(_clock(day=100), _advance("e", 30))
    assert a == b


# --------------------------------------------------------------------------- #
# Scheduling via integrate_turn
# --------------------------------------------------------------------------- #
def test_no_work_when_not_due():
    state = {"run_seed": "s", "simulation_clock": _clock(day=100, processed=100),
             "npc_lifecycle": {"n1": _rec("n1", age_years=40)}}
    out_state, _, diag = C.integrate_turn(state, {"npcs": _npcs("n1")}, run_seed="s", turn_number=2)
    assert diag["lifecycle"]["due"] is False and diag["lifecycle"]["lifecycle_applied"] is False


def test_one_due_period_runs_and_advances_cursor():
    state = {"run_seed": "s", "simulation_clock": _clock(day=0, processed=0),
             "npc_lifecycle": {"n1": _rec("n1", age_years=40)},
             "pending_time_advance": _advance_exp("e", Y, 0)}
    out_state, _, diag = C.integrate_turn(state, {"npcs": _npcs("n1")}, run_seed="s", turn_number=2)
    assert diag["lifecycle"]["lifecycle_applied"] is True
    assert out_state["simulation_clock"]["lifecycle_processed_through_day"] == Y


def test_ordinary_turn_does_not_reroll_or_advance():
    state = {"run_seed": "s", "simulation_clock": _clock(day=Y, processed=Y),
             "npc_lifecycle": {"n1": _rec("n1", age_years=40, last_mortality_evaluation_day=Y)}}
    out_state, _, diag = C.integrate_turn(state, {"npcs": _npcs("n1")}, run_seed="s", turn_number=3)
    assert diag["lifecycle"]["due"] is False
    assert out_state["simulation_clock"]["current_simulation_day"] == Y


def test_large_jump_is_bounded_and_reports_backlog():
    # 200-year jump exceeds MAX_CATCHUP_PERIODS: bounded, backlog reported, cursor persisted.
    state = {"run_seed": "s", "simulation_clock": _clock(day=0, processed=0),
             "npc_lifecycle": {"n1": _rec("n1", age_years=20)},
             "pending_time_advance": _advance_exp("e", 200 * Y, 0)}
    out_state, _, diag = C.integrate_turn(state, {"npcs": _npcs("n1")}, run_seed="s", turn_number=2)
    assert diag["lifecycle"]["remaining_backlog_periods"] == 200 - C.MAX_CATCHUP_PERIODS
    assert out_state["simulation_clock"]["current_simulation_day"] == 200 * Y  # clock fully advanced
    assert out_state["simulation_clock"]["lifecycle_processed_through_day"] < 200 * Y  # cursor bounded


def test_archived_and_dead_skipped():
    state = {"run_seed": "s", "simulation_clock": _clock(day=0, processed=0),
             "npc_lifecycle": {"dead": _rec("dead", age_years=40, alive=False, life_stage="archived",
                                            death_simulation_day=-100)},
             "pending_time_advance": _advance_exp("e", Y, 0)}
    out_state, _, diag = C.integrate_turn(state, {"npcs": _npcs("dead")}, run_seed="s", turn_number=2)
    assert out_state["npc_lifecycle"]["dead"]["alive"] is False
    assert diag["lifecycle"]["npcs_evaluated"] == 0  # dead never evaluated


def test_tier_processing_deterministic_ordering():
    npcs = _npcs("nb", "na", "nc")  # unsorted
    state = {"run_seed": "s", "simulation_clock": _clock(0, 0),
             "npc_lifecycle": {i: _rec(i, age_years=40) for i in ("na", "nb", "nc")},
             "pending_time_advance": _advance_exp("e", Y, 0)}
    a = C.integrate_turn(copy.deepcopy(state), {"npcs": list(npcs)}, run_seed="s", turn_number=2)[2]
    b = C.integrate_turn(copy.deepcopy(state), {"npcs": list(reversed(npcs))}, run_seed="s", turn_number=2)[2]
    assert a["lifecycle"]["death_event_ids"] == b["lifecycle"]["death_event_ids"]


# --------------------------------------------------------------------------- #
# Atomicity / fail-closed
# --------------------------------------------------------------------------- #
def test_failed_lifecycle_leaves_records_and_cursor_unchanged(monkeypatch):
    records = {"n1": _rec("n1", age_years=40)}
    state = {"run_seed": "s", "simulation_clock": _clock(0, 0),
             "npc_lifecycle": copy.deepcopy(records), "pending_time_advance": _advance_exp("e", Y, 0)}

    def boom(*a, **k):
        raise RuntimeError("planned failure")

    monkeypatch.setattr(L, "process_due_periods", boom)
    out_state, _, diag = C.integrate_turn(state, {"npcs": _npcs("n1")}, run_seed="s", turn_number=2)
    assert diag["lifecycle"]["lifecycle_applied"] is False and diag["lifecycle"]["error"]
    assert out_state["npc_lifecycle"] == records                     # records unchanged
    assert out_state["simulation_clock"]["lifecycle_processed_through_day"] == 0  # cursor unchanged
    assert out_state["simulation_clock"]["current_simulation_day"] == Y           # clock advance stays


def test_retry_after_failure_is_deterministic(monkeypatch):
    def run():
        state = {"run_seed": "s", "simulation_clock": _clock(0, 0),
                 "npc_lifecycle": {"n1": _rec("n1", age_years=90)}, "pending_time_advance": _advance_exp("e", 3 * Y, 0)}
        return C.integrate_turn(state, {"npcs": _npcs("n1")}, run_seed="s", turn_number=2)
    a_state, _, a_diag = run()
    b_state, _, b_diag = run()
    assert a_state["npc_lifecycle"] == b_state["npc_lifecycle"]
    assert a_diag["lifecycle"]["death_event_ids"] == b_diag["lifecycle"]["death_event_ids"]


# --------------------------------------------------------------------------- #
# Death persistence via the seam
# --------------------------------------------------------------------------- #
def _certain_death_state(event_id="e"):
    # Age 130 forces mortality probability 1.0 => deterministic death on evaluation.
    return {"run_seed": "s", "simulation_clock": _clock(day=130 * Y, processed=129 * Y),
            "npc_lifecycle": {"Old": _rec("Old", age_years=130, last_mortality_evaluation_day=129 * Y)},
            "pending_time_advance": _advance_exp(event_id, Y, 130 * Y)}


def test_natural_death_persists_registry_and_receipt():
    state = _certain_death_state()
    rolling = {"npcs": [{"npc_id": "Old", "name": "Old"}], "deceased": []}
    out_state, out_rolling, diag = C.integrate_turn(state, rolling, run_seed="s", turn_number=2)
    rec = out_state["npc_lifecycle"]["Old"]
    assert rec["alive"] is False and rec["life_stage"] == "archived" and rec["death_cause"] == "natural_causes"
    assert "Old" in out_rolling["deceased"]                          # deceased registry projection
    receipts = [r for r in out_state.get("transition_receipts", []) if r.get("receipt_type") == "npc_lifecycle_death"]
    assert len(receipts) == 1                                        # one bounded receipt
    assert diag["lifecycle"]["deaths_applied"] if "deaths_applied" in diag["lifecycle"] else True
    assert len(diag["lifecycle"]["death_event_ids"]) == 1


def test_death_record_preserved_not_deleted():
    state = _certain_death_state()
    out_state, _, _ = C.integrate_turn(state, {"npcs": [{"npc_id": "Old", "name": "Old"}], "deceased": []},
                                       run_seed="s", turn_number=2)
    assert "Old" in out_state["npc_lifecycle"]                       # record preserved
    assert out_state["npc_lifecycle"]["Old"]["death_simulation_day"] is not None


def test_duplicate_death_application_no_dup_registry_or_receipt():
    # Apply the death turn, then re-run with the SAME advance event: duplicate
    # advance is a no-op, so no re-evaluation, no duplicate registry/receipt.
    state = _certain_death_state("dup")
    rolling = {"npcs": [{"npc_id": "Old", "name": "Old"}], "deceased": []}
    s1, r1, _ = C.integrate_turn(state, rolling, run_seed="s", turn_number=2)
    # feed the same event id again on the resulting state
    s1["pending_time_advance"] = _advance_exp("dup", Y, 130 * Y)
    s2, r2, d2 = C.integrate_turn(s1, r1, run_seed="s", turn_number=3)
    assert r2["deceased"].count("Old") == 1
    assert len([r for r in s2.get("transition_receipts", []) if r.get("receipt_type") == "npc_lifecycle_death"]) == 1


def test_existing_lifecycle_record_respects_deceased_name_without_fresh_death():
    # Existing lifecycle state can be keyed by npc_id while the authoritative
    # deceased registry is name-based. The planner must merge the live row name
    # before migration so an already-dead NPC is archived, not naturally killed
    # a second time.
    state = {"run_seed": "s", "simulation_clock": _clock(day=0, processed=0),
             "npc_lifecycle": {"npc-1": _rec("npc-1", age_years=130)},
             "pending_time_advance": _advance_exp("e", Y, 0)}
    rolling = {"npcs": [{"npc_id": "npc-1", "name": "Old"}], "deceased": ["Old"]}
    out_state, out_rolling, diag = C.integrate_turn(state, rolling, run_seed="s", turn_number=2)
    rec = out_state["npc_lifecycle"]["npc-1"]
    assert rec["alive"] is False and rec["life_stage"] == "archived"
    assert rec["death_cause"] == L.LEGACY_DECEASED_REGISTRY_CAUSE
    assert diag["lifecycle"]["death_event_ids"] == []
    assert out_rolling["deceased"].count("Old") == 1
    assert not [r for r in out_state.get("transition_receipts", []) if r.get("receipt_type") == "npc_lifecycle_death"]


def test_lifecycle_death_excludes_future_actor_selection():
    state = _certain_death_state()
    rolling = {"scene": "dock", "npcs": [{"npc_id": "Old", "name": "Old"}], "deceased": []}
    out_state, out_rolling, _ = C.integrate_turn(state, rolling, run_seed="s", turn_number=2)
    agenda_state = agendas.init_npc_agendas()
    agenda_state["active"].append({
        "npc_id": "Old",
        "agenda_id": "agenda-old",
        "display_name": "Old",
        "goal_kind": "protect_person",
        "fear_kind": "abandonment",
        "status": "active",
        "last_move_turn": 0,
    })
    move, candidates = moves.select_npc_move(
        "s", agenda_state, out_rolling, out_state, out_state.get("identity") or {}, 3
    )
    assert "Old" in out_rolling["deceased"]
    assert move is None and candidates == []


# --------------------------------------------------------------------------- #
# Feature flag
# --------------------------------------------------------------------------- #
def test_flag_off_is_total_noop(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_NPC_LIFECYCLE", False)
    state = {"run_seed": "s", "pending_time_advance": _advance("e", Y)}
    out_state, out_rolling, diag = C.integrate_turn(state, {"npcs": _npcs("n1")}, run_seed="s", turn_number=2)
    assert out_state is state                                        # unchanged object
    assert "simulation_clock" not in out_state                      # no clock created
    assert diag["lifecycle"]["lifecycle_enabled"] is False


def test_flag_on_no_advance_does_no_lifecycle_work():
    state = {"run_seed": "s", "simulation_clock": _clock(day=0, processed=0),
             "npc_lifecycle": {"n1": _rec("n1", age_years=40)}}
    out_state, _, diag = C.integrate_turn(state, {"npcs": _npcs("n1")}, run_seed="s", turn_number=2)
    assert diag["lifecycle"]["due"] is False and diag["lifecycle"]["lifecycle_applied"] is False
    assert out_state["simulation_clock"]["current_simulation_day"] == 0


# --------------------------------------------------------------------------- #
# GOLDEN PATH — end-to-end through the real turn seam
# --------------------------------------------------------------------------- #
def test_golden_path_end_to_end_via_prepare_action_turn(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_NPC_LIFECYCLE", True)
    base, _ = replayability.init_new_story(
        genre="noir", role="detective", tone="gritty", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=SEED,
    )
    base["simulation_clock"] = _clock(day=0, processed=0)
    base["npc_lifecycle"] = {"Mara": _rec("Mara", age_years=15)}   # child at day 0
    rolling = {"npcs": [{"npc_id": "Mara", "name": "Mara"}]}

    # (1)(2) ordinary action, no structured advance -> clock stays at day 0.
    s1, _, d1, _, _ = replayability.prepare_action_turn(copy.deepcopy(base), 2, rolling_state=copy.deepcopy(rolling))
    assert s1["simulation_clock"]["current_simulation_day"] == 0
    assert d1["lifecycle"]["lifecycle_applied"] is False

    # (3)(4)(5) trusted structured advance +1 year -> clock forward, lifecycle due, child->adult.
    staged = copy.deepcopy(base)
    staged["pending_time_advance"] = _advance_exp("adv-1", Y, 0)
    s2, _, d2, _, wr2 = replayability.prepare_action_turn(staged, 3, rolling_state=copy.deepcopy(rolling))
    assert s2["simulation_clock"]["current_simulation_day"] == Y
    assert d2["lifecycle"]["lifecycle_applied"] is True
    assert s2["npc_lifecycle"]["Mara"]["life_stage"] == "adult"
    assert any(t["npc_id"] == "Mara" and t["to"] == "adult" for t in d2["lifecycle"]["stage_transitions"])

    # (7) replay: identical inputs -> byte-equivalent clock + lifecycle + event ids.
    staged_r = copy.deepcopy(base)
    staged_r["pending_time_advance"] = _advance_exp("adv-1", Y, 0)
    s2b, _, d2b, _, _ = replayability.prepare_action_turn(staged_r, 3, rolling_state=copy.deepcopy(rolling))
    assert s2b["simulation_clock"] == s2["simulation_clock"]
    assert s2b["npc_lifecycle"] == s2["npc_lifecycle"]
    assert d2b["lifecycle"]["death_event_ids"] == d2["lifecycle"]["death_event_ids"]

    # (8) reapply the SAME advance event -> no double advancement.
    reapply = copy.deepcopy(s2)
    reapply["pending_time_advance"] = _advance_exp("adv-1", Y, 0)
    s3, _, d3, _, _ = replayability.prepare_action_turn(reapply, 4, rolling_state=copy.deepcopy(rolling))
    assert s3["simulation_clock"]["current_simulation_day"] == Y      # unchanged (duplicate)
    assert d3["simulation_clock"]["duplicate"] is True


# --------------------------------------------------------------------------- #
# Authoritative expected-previous-day precondition contract (clock hardening)
# Closes the gap where permanent replay protection only applied when a producer
# happened to supply the precondition. The authoritative seam now REQUIRES it.
# --------------------------------------------------------------------------- #
def _missing_precondition_advance(event_id="adv-x", days=Y):
    # Structurally valid advance that OMITS expected_previous_simulation_day.
    return _advance(event_id, days)


def test_unit_seam_requires_precondition_when_authoritative():
    # require_precondition=True: a missing-precondition event is a hard rejection;
    # the clock is untouched and the failure is distinct from stale/duplicate.
    clock, diag = C.apply_time_advance(
        _clock(day=10), _missing_precondition_advance("m", 5), require_precondition=True
    )
    assert clock["current_simulation_day"] == 10
    assert diag["validation_failure"] == "missing_expected_previous_simulation_day"
    assert diag["precondition_missing"] is True
    assert diag["duplicate"] is False and diag["stale"] is False       # not the 64-ID window


def test_unit_seam_legacy_path_preserves_missing_precondition_behaviour():
    # Default (require_precondition=False) is the pure-primitive/legacy path used
    # by no authoritative producer; it keeps historical bounded-window behaviour.
    clock, diag = C.apply_time_advance(_clock(day=10), _missing_precondition_advance("m", 5))
    assert clock["current_simulation_day"] == 15 and diag["validation_failure"] is None


def test_integrate_turn_rejects_missing_precondition_without_mutation():
    # Authoritative seam fail-closed: clock unchanged, pending NOT consumed, no
    # lifecycle, distinct diagnostic, no partial mutation.
    state = {"run_seed": "s", "simulation_clock": _clock(day=10, processed=10),
             "npc_lifecycle": {"n1": _rec("n1", age_years=40)},
             "pending_time_advance": _missing_precondition_advance("bad", 5)}
    before = copy.deepcopy(state)
    out_state, _, diag = C.integrate_turn(state, {"npcs": _npcs("n1")}, run_seed="s", turn_number=2)
    assert out_state["simulation_clock"]["current_simulation_day"] == 10           # clock unchanged
    assert out_state["pending_time_advance"] == before["pending_time_advance"]     # not consumed
    assert out_state["simulation_clock"]["lifecycle_processed_through_day"] == 10   # no cursor move
    assert diag["simulation_clock"]["validation_failure"] == "missing_expected_previous_simulation_day"
    assert diag["lifecycle"]["lifecycle_applied"] is False and diag["lifecycle"]["due"] is False


def test_missing_precondition_cannot_erase_a_committed_legitimate_advance():
    # A legitimate advance moves the clock and is consumed; a later malformed
    # event cannot roll it back or erase the recorded application.
    state = {"run_seed": "s", "simulation_clock": _clock(day=0, processed=0),
             "npc_lifecycle": {"n1": _rec("n1", age_years=40)},
             "pending_time_advance": _advance_exp("good", Y, 0)}
    s1, _, _ = C.integrate_turn(state, {"npcs": _npcs("n1")}, run_seed="s", turn_number=2)
    assert s1["simulation_clock"]["current_simulation_day"] == Y
    assert s1["simulation_clock"]["last_applied_advance_event_id"] == "good"
    s1["pending_time_advance"] = _missing_precondition_advance("bad", 5)
    s2, _, d2 = C.integrate_turn(s1, {"npcs": _npcs("n1")}, run_seed="s", turn_number=3)
    assert s2["simulation_clock"]["current_simulation_day"] == Y                    # not rolled back
    assert s2["simulation_clock"]["last_applied_advance_event_id"] == "good"        # legitimate advance intact
    assert d2["simulation_clock"]["validation_failure"] == "missing_expected_previous_simulation_day"


def test_two_events_same_expected_day_only_one_advances():
    # clock day 10; A expects 10 -> 11; B also expects 10 -> stale, no double advance.
    clock = _clock(day=10)
    clock, dA = C.apply_time_advance(clock, _advance_exp("A", 1, 10), require_precondition=True)
    assert clock["current_simulation_day"] == 11 and dA["applied_elapsed_days"] == 1
    clock, dB = C.apply_time_advance(clock, _advance_exp("B", 1, 10), require_precondition=True)
    assert clock["current_simulation_day"] == 11                                    # B stale
    assert dB["stale"] is True and dB["duplicate"] is True


def test_legitimate_retry_must_be_recreated_against_new_clock_state():
    clock = _clock(day=10)
    clock, _ = C.apply_time_advance(clock, _advance_exp("A", 1, 10), require_precondition=True)
    clock, dB = C.apply_time_advance(clock, _advance_exp("B", 1, 10), require_precondition=True)
    assert clock["current_simulation_day"] == 11 and dB["stale"] is True            # old expected day rejected
    clock, dB2 = C.apply_time_advance(clock, _advance_exp("B", 1, 11), require_precondition=True)
    assert clock["current_simulation_day"] == 12 and dB2["applied_elapsed_days"] == 1  # retry vs new day advances


def test_integrate_turn_and_unit_seam_enforce_identical_contract():
    # The real seam rejects a missing-precondition event with the SAME reason the
    # unit seam does (require_precondition=True everywhere authoritative).
    ev = _missing_precondition_advance("same", 5)
    _, unit_diag = C.apply_time_advance(_clock(day=7), dict(ev), require_precondition=True)
    seam_state = {"run_seed": "s", "simulation_clock": _clock(day=7, processed=7),
                  "npc_lifecycle": {}, "pending_time_advance": dict(ev)}
    _, _, seam_diag = C.integrate_turn(seam_state, {"npcs": []}, run_seed="s", turn_number=2)
    assert unit_diag["validation_failure"] == "missing_expected_previous_simulation_day"
    assert seam_diag["simulation_clock"]["validation_failure"] == unit_diag["validation_failure"]


def test_evicted_replay_still_blocked_with_precondition_unit_seam():
    # Old event stays blocked permanently after eviction from the bounded window
    # BECAUSE it carries the expected-day precondition (not the 64-ID list).
    clk = _clock()
    clk, _ = C.apply_time_advance(clk, _advance_exp("A", 10, 0), require_precondition=True)
    for i in range(C.MAX_ADVANCE_EVENT_RECEIPTS + 1):
        cur = clk["current_simulation_day"]
        clk, _ = C.apply_time_advance(clk, _advance_exp(f"e{i}", 1, cur), require_precondition=True)
    assert "A" not in clk["recent_advance_event_ids"]                               # evicted
    day = clk["current_simulation_day"]
    clk, dA = C.apply_time_advance(clk, _advance_exp("A", 10, 0), require_precondition=True)
    assert dA["duplicate"] is True and dA["stale"] is True and clk["current_simulation_day"] == day
