"""
Simulation clock + lifecycle integration — Chapter 33 structured clock seam.

Authoritative, replay-safe integer simulation-day clock and the orchestration
seam that drives the Phase-1 lifecycle core during real turn execution.

Time rules (non-negotiable): time advances ONLY from an explicit engine-owned
structured time-advance event. An ordinary turn with no such event advances the
clock by exactly zero. No wall-clock, no ``datetime.now()``, no turn×duration,
no provider latency, no prose-derived time.

State (engine-owned; lives in ``replayability_state`` which is never
player-visible and never LLM-authored):

    simulation_clock = {
        schema_version, current_simulation_day,
        last_applied_advance_event_id, lifecycle_processed_through_day, migrated
    }
    npc_lifecycle = { npc_id: lifecycle_record, ... }

The whole seam is gated on ``ENABLE_NPC_LIFECYCLE`` (default OFF): with the flag
OFF ``integrate_turn`` is a complete no-op, so no clock/lifecycle state is
created and no player-visible gameplay behavior changes. Authority is split:
the clock advance is committed independently of lifecycle; lifecycle is planned
on copies, validated, then committed atomically. If lifecycle fails the clock
advance may remain, but no partial lifecycle mutation is left and
``lifecycle_processed_through_day`` does not advance, so overdue periods retry
deterministically.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import npc_lifecycle

CLOCK_SCHEMA_VERSION = 1
MAX_CATCHUP_PERIODS = 50           # bounded catch-up per turn (no full burn-in)
MAX_ADVANCE_EVENT_RECEIPTS = 64    # bounded applied time-advance receipt window
_LIFECYCLE_RECEIPTS_MAX = 32       # mirrors replayability.TRANSITION_RECEIPTS_MAX
_RECEIPT_TYPE_DEATH = "npc_lifecycle_death"
_DAYS_PER_YEAR = npc_lifecycle.DAYS_PER_SIMULATION_YEAR


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# Clock migration
# ---------------------------------------------------------------------------
def migrate_clock(replayability_state: Mapping[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """
    Return (clock, migrated). Absent/invalid state migrates deterministically to
    day 0 (never wall-clock, never retroactive aging, never negative, never
    backwards). Valid existing clock state is preserved.
    """
    existing = (
        replayability_state.get("simulation_clock")
        if isinstance(replayability_state, Mapping)
        else None
    )
    if isinstance(existing, Mapping) and _is_int(existing.get("current_simulation_day")):
        clock = dict(existing)
        clock["schema_version"] = CLOCK_SCHEMA_VERSION
        if not _is_int(clock.get("lifecycle_processed_through_day")):
            clock["lifecycle_processed_through_day"] = 0
        clock.setdefault("last_applied_advance_event_id", None)
        _recent = clock.get("recent_advance_event_ids")
        clock["recent_advance_event_ids"] = (
            list(_recent)[-MAX_ADVANCE_EVENT_RECEIPTS:] if isinstance(_recent, list) else []
        )
        if clock["current_simulation_day"] < 0:
            clock["current_simulation_day"] = 0
        if clock["lifecycle_processed_through_day"] < 0:
            clock["lifecycle_processed_through_day"] = 0
        clock["migrated"] = False
        return clock, False
    return (
        {
            "schema_version": CLOCK_SCHEMA_VERSION,
            "current_simulation_day": 0,
            "last_applied_advance_event_id": None,
            "recent_advance_event_ids": [],
            "lifecycle_processed_through_day": 0,
            "migrated": True,
        },
        True,
    )


# ---------------------------------------------------------------------------
# Structured time advance
# ---------------------------------------------------------------------------
def validate_time_advance(advance: Any) -> Tuple[bool, Optional[str]]:
    if not isinstance(advance, Mapping):
        return False, "not_a_mapping"
    if not advance.get("event_id"):
        return False, "missing_event_id"
    days = advance.get("elapsed_simulation_days")
    if not _is_int(days):
        return False, "elapsed_not_int"
    if days < 0:
        return False, "negative_elapsed"
    return True, None


def apply_time_advance(
    clock: Dict[str, Any],
    advance: Optional[Mapping[str, Any]],
    *,
    require_precondition: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Idempotently apply a structured time-advance to a clock copy. Returns
    (clock, diagnostic). ``advance`` None (ordinary turn) → zero advance.
    Re-applying the same event_id is a no-op; negative/invalid is rejected;
    time never moves backwards.

    ``require_precondition`` is the authoritative contract switch. When True
    (every authoritative runtime consumer passes True via ``integrate_turn``), an
    otherwise-valid event that omits ``expected_previous_simulation_day`` is a
    hard, fail-closed rejection (``validation_failure =
    "missing_expected_previous_simulation_day"``, ``precondition_missing = True``)
    — it never silently falls through to the bounded recent-id window. When False
    (the pure-primitive / legacy path used only by unit tests, reachable by no
    authoritative producer) a missing precondition retains the historical
    bounded-window duplicate behaviour. The compare-and-advance permanent barrier
    is identical in both modes when the precondition IS supplied, so the
    ``integrate_turn`` seam and this unit seam enforce the same contract.
    """
    clock = dict(clock)
    prev = int(clock["current_simulation_day"])
    diag: Dict[str, Any] = {
        "authority": "engine_structured_time_advance",
        "previous_day": prev,
        "requested_elapsed_days": None,
        "applied_elapsed_days": 0,
        "resulting_day": prev,
        "advance_event_id": None,
        "duplicate": False,
        "stale": False,
        "precondition_missing": False,
        "validation_failure": None,
    }
    if advance is None:
        return clock, diag
    diag["advance_event_id"] = advance.get("event_id") if isinstance(advance, Mapping) else None
    diag["requested_elapsed_days"] = (
        advance.get("elapsed_simulation_days") if isinstance(advance, Mapping) else None
    )
    ok, reason = validate_time_advance(advance)
    if not ok:
        diag["validation_failure"] = reason
        return clock, diag
    event_id = str(advance["event_id"])
    days = int(advance["elapsed_simulation_days"])

    # Permanent replay barrier (authoritative when supplied): the event declares
    # the clock day it expects. A stale event (expected < now) is a duplicate/
    # stale no-op even after its id has been evicted from the bounded receipt
    # window; a future/out-of-order event (expected > now) is rejected. This does
    # NOT rely on the bounded recent-id list for permanent safety.
    expected_prev = advance.get("expected_previous_simulation_day")
    if expected_prev is None:
        if require_precondition:
            # Authoritative contract: a supplied structured advance MUST declare
            # the clock day it expects. Missing it is a hard, fail-closed
            # rejection — never a silent fall-through to the bounded recent-id
            # window. Distinct from stale replay (duplicate + stale) and from
            # ordinary duplicate detection (duplicate only).
            diag["precondition_missing"] = True
            diag["validation_failure"] = "missing_expected_previous_simulation_day"
            return clock, diag
        # Legacy / pure-primitive path (no authoritative producer reaches here):
        # the bounded recent-id window below provides duplicate detection only.
    else:
        if not _is_int(expected_prev):
            diag["validation_failure"] = "expected_prev_not_int"
            return clock, diag
        if expected_prev < prev:
            diag["duplicate"] = True
            diag["stale"] = True
            return clock, diag
        if expected_prev > prev:
            diag["validation_failure"] = "expected_day_ahead"
            return clock, diag
        target = advance.get("target_simulation_day")
        if target is not None and _is_int(target) and int(target) != prev + days:
            diag["validation_failure"] = "target_day_mismatch"
            return clock, diag

    recent_ids = clock.get("recent_advance_event_ids") or []
    if event_id == clock.get("last_applied_advance_event_id") or event_id in recent_ids:
        diag["duplicate"] = True                        # bounded receipt: reject ANY prior applied event
        return clock, diag
    clock["current_simulation_day"] = prev + days      # days >= 0 → never backwards
    clock["last_applied_advance_event_id"] = event_id
    clock["recent_advance_event_ids"] = (list(recent_ids) + [event_id])[-MAX_ADVANCE_EVENT_RECEIPTS:]
    diag["applied_elapsed_days"] = days
    diag["resulting_day"] = prev + days
    return clock, diag


# ---------------------------------------------------------------------------
# Receipt seam (reuses the caller's approved append-only helper; test fallback)
# ---------------------------------------------------------------------------
def _default_append_receipt(
    state: Dict[str, Any], *, source_event_id: str, receipt_type: str, turn_number: int
) -> bool:
    receipts = state.setdefault("transition_receipts", [])
    if any(
        isinstance(r, dict)
        and r.get("source_event_id") == source_event_id
        and r.get("receipt_type") == receipt_type
        for r in receipts
    ):
        return False
    receipts.append(
        {"source_event_id": source_event_id, "receipt_type": receipt_type, "turn": turn_number}
    )
    if len(receipts) > _LIFECYCLE_RECEIPTS_MAX:
        state["transition_receipts"] = receipts[-_LIFECYCLE_RECEIPTS_MAX:]
    return True


def _tiers_for(working_rolling: Mapping[str, Any], turn_number: int) -> Dict[str, str]:
    """Reuse Actor Resolution tier output as an input (no enumeration change)."""
    import npc_world_moves as world_moves

    tiers: Dict[str, str] = {}
    for row in working_rolling.get("npcs") or []:
        if not isinstance(row, Mapping):
            continue
        npc_id = str(row.get("npc_id") or row.get("name") or "")
        if not npc_id:
            continue
        tiers[npc_id] = world_moves.resolve_actor_tier(
            npc_id, str(row.get("name") or ""), working_rolling, turn_number
        )
    return tiers


# ---------------------------------------------------------------------------
# Lifecycle planning (pure, no mutation) + validation
# ---------------------------------------------------------------------------
def _plan_lifecycle(
    *,
    npcs: List[Mapping[str, Any]],
    existing_records: Mapping[str, Mapping[str, Any]],
    deceased_names: List[str],
    tiers: Mapping[str, str],
    run_seed: str,
    current_day: int,
    processed_through: int,
) -> Dict[str, Any]:
    due_periods = npc_lifecycle.due_mortality_periods(processed_through, current_day)
    batch = due_periods[:MAX_CATCHUP_PERIODS]
    backlog = max(0, len(due_periods) - len(batch))
    if backlog == 0:
        new_processed_through = current_day
    else:
        last_period = batch[-1] if batch else npc_lifecycle.mortality_evaluation_period(processed_through)
        new_processed_through = last_period * _DAYS_PER_YEAR + (_DAYS_PER_YEAR - 1)

    records: Dict[str, Dict[str, Any]] = {}
    events: List[Dict[str, Any]] = []
    deceased_add: List[Tuple[str, str]] = []       # (event_id, npc_name)
    stage_transitions: List[Dict[str, Any]] = []
    tier_counts: Dict[str, int] = {}
    npcs_evaluated = 0
    periods_evaluated = 0

    ordered = sorted(
        (r for r in npcs if isinstance(r, Mapping) and (r.get("npc_id") or r.get("name"))),
        key=lambda r: str(r.get("npc_id") or r.get("name")),
    )
    for row in ordered:
        npc_id = str(row.get("npc_id") or row.get("name"))
        tier = tiers.get(npc_id, "active")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        existing = existing_records.get(npc_id)
        if existing:
            source = dict(row)
            source.update(existing)
        else:
            source = row
        record, _mig = npc_lifecycle.migrate_record(
            source,
            current_simulation_day=current_day,
            run_seed=run_seed,
            deceased_names=deceased_names,
            profile_id=str(source.get("lifecycle_profile") or "human"),
        )
        # Prior stage is the STORED stage (from the last processing), captured
        # before migration recomputes it at the current day — so a boundary
        # crossing during this advance is detected.
        prior_stage = source.get("life_stage")

        # Archived / dead / no-process tiers: preserve, never age or evaluate.
        if tier in ("archived", "unknown") or not record.get("alive", True):
            records[npc_id] = record
            continue

        updated, death_event, evaluated, _last = npc_lifecycle.process_due_periods(
            record,
            processed_through_day=processed_through,
            current_simulation_day=current_day,
            run_seed=run_seed,
            max_periods=MAX_CATCHUP_PERIODS,
        )
        npcs_evaluated += 1
        periods_evaluated += evaluated
        if prior_stage is not None and updated.get("life_stage") != prior_stage:
            stage_transitions.append({"npc_id": npc_id, "from": prior_stage, "to": updated.get("life_stage")})
        if death_event is not None:
            events.append(death_event)
            deceased_add.append((death_event["event_id"], str(row.get("name") or npc_id)))
        records[npc_id] = updated

    # Preserve historical records for NPCs no longer present in rolling.
    for npc_id, rec in (existing_records or {}).items():
        records.setdefault(npc_id, dict(rec))

    return {
        "records": records,
        "events": events,
        "deceased_add": deceased_add,
        "new_processed_through": new_processed_through,
        "backlog_periods": backlog,
        "stage_transitions": stage_transitions,
        "tier_counts": tier_counts,
        "npcs_evaluated": npcs_evaluated,
        "periods_evaluated": periods_evaluated,
        "batch_periods": len(batch),
    }


def _validate_plan(plan: Mapping[str, Any], deceased_names: List[str]) -> None:
    """Raise on any inconsistency before commit (plan-then-commit safety)."""
    deceased_set = {str(d).strip().lower() for d in (deceased_names or [])}
    seen_event_ids: set = set()
    for npc_id, rec in plan["records"].items():
        alive = bool(rec.get("alive", True))
        if alive and str(rec.get("npc_id") or npc_id).strip().lower() in deceased_set:
            raise ValueError(f"lifecycle_plan_alive_and_deceased:{npc_id}")
        if not alive and rec.get("death_simulation_day") is None:
            raise ValueError(f"lifecycle_plan_dead_without_day:{npc_id}")
    for ev in plan["events"]:
        eid = ev.get("event_id")
        if not eid:
            raise ValueError("lifecycle_plan_missing_event_id")
        if eid in seen_event_ids:
            raise ValueError(f"lifecycle_plan_duplicate_event_id:{eid}")
        seen_event_ids.add(eid)


# ---------------------------------------------------------------------------
# Orchestration seam (called from the turn path with the approved receipt helper)
# ---------------------------------------------------------------------------
def _idle_diag() -> Dict[str, Any]:
    return {"lifecycle_enabled": False, "lifecycle_applied": False}


def integrate_turn(
    replayability_state: Dict[str, Any],
    working_rolling: Dict[str, Any],
    *,
    run_seed: str,
    turn_number: int,
    append_receipt: Optional[Callable[..., bool]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    The live integration seam. Returns (replayability_state, working_rolling,
    diagnostics). Flag OFF → complete no-op. Fail-closed on any error.
    """
    if not npc_lifecycle.is_enabled():
        return replayability_state, working_rolling, {"lifecycle": _idle_diag()}

    append = append_receipt or _default_append_receipt
    original_state = replayability_state
    try:
        state = copy.deepcopy(replayability_state)
        clock, migrated = migrate_clock(state)
        # Authoritative consumption seam: enforce the expected-previous-day
        # precondition on any supplied structured advance. This is the single
        # place a staged event becomes authoritative, so it is the enforcement
        # point for "every authoritative producer supplies the precondition".
        clock, clock_diag = apply_time_advance(
            clock, state.get("pending_time_advance"), require_precondition=True
        )
        clock_diag["migration"] = migrated

        # Fail closed on a missing precondition: do NOT commit the clock, do NOT
        # consume the pending event, do NOT run lifecycle. Return the caller's
        # original state untouched (zero partial mutation) with a distinct
        # diagnostic. A legitimate pending advance always carries the
        # precondition, so it is never discarded by this path.
        if clock_diag.get("validation_failure") == "missing_expected_previous_simulation_day":
            return original_state, working_rolling, {
                "simulation_clock": clock_diag,
                "lifecycle": {
                    "lifecycle_enabled": True,
                    "lifecycle_applied": False,
                    "due": False,
                    "skipped_reason": "missing_expected_previous_simulation_day",
                },
            }

        # Commit the authoritative clock advance and consume the pending event.
        state["simulation_clock"] = clock
        state.pop("pending_time_advance", None)

        current_day = int(clock["current_simulation_day"])
        processed_through = int(clock["lifecycle_processed_through_day"])
        life_diag: Dict[str, Any] = {
            "lifecycle_enabled": True,
            "lifecycle_applied": False,
            "due": current_day > processed_through,
            "processed_from_day": processed_through,
            "processed_through_day": processed_through,
            "current_simulation_day": current_day,
            "remaining_backlog_periods": 0,
            "npcs_evaluated": 0,
            "tier_counts": {},
            "stage_transitions": [],
            "mortality_periods_evaluated": 0,
            "death_event_ids": [],
            "duplicate_deaths_rejected": 0,
            "deceased_projections": [],
            "receipts_appended": 0,
            "error": None,
        }

        if current_day > processed_through:
            deceased_names = list(working_rolling.get("deceased") or [])
            try:
                plan = _plan_lifecycle(
                    npcs=list(working_rolling.get("npcs") or []),
                    existing_records=(state.get("npc_lifecycle") if isinstance(state.get("npc_lifecycle"), Mapping) else {}),
                    deceased_names=deceased_names,
                    tiers=_tiers_for(working_rolling, turn_number),
                    run_seed=run_seed,
                    current_day=current_day,
                    processed_through=processed_through,
                )
                _validate_plan(plan, deceased_names)

                # ---- atomic commit (only after a fully validated plan) ----
                state["npc_lifecycle"] = plan["records"]
                clock["lifecycle_processed_through_day"] = plan["new_processed_through"]
                state["simulation_clock"] = clock

                deceased_set = {str(d).strip().lower() for d in (working_rolling.get("deceased") or [])}
                projections: List[str] = []
                receipts_appended = 0
                dup_rejected = 0
                for event, name in zip(plan["events"], [n for _e, n in plan["deceased_add"]]):
                    if name.strip().lower() not in deceased_set:
                        working_rolling.setdefault("deceased", []).append(name)
                        deceased_set.add(name.strip().lower())
                        projections.append(name)
                    if append(state, source_event_id=event["event_id"], receipt_type=_RECEIPT_TYPE_DEATH, turn_number=turn_number):
                        receipts_appended += 1
                    else:
                        dup_rejected += 1

                life_diag.update(
                    lifecycle_applied=True,
                    processed_through_day=plan["new_processed_through"],
                    remaining_backlog_periods=plan["backlog_periods"],
                    npcs_evaluated=plan["npcs_evaluated"],
                    tier_counts=plan["tier_counts"],
                    stage_transitions=plan["stage_transitions"],
                    mortality_periods_evaluated=plan["periods_evaluated"],
                    death_event_ids=[e["event_id"] for e in plan["events"]],
                    duplicate_deaths_rejected=dup_rejected,
                    deceased_projections=projections,
                    receipts_appended=receipts_appended,
                )
            except Exception as life_exc:
                # Lifecycle failed: clock advance stays committed; cursor and NPC
                # records unchanged; overdue periods retry later. No partial state.
                life_diag["lifecycle_applied"] = False
                life_diag["error"] = str(life_exc)[:200]

        return state, working_rolling, {"simulation_clock": clock_diag, "lifecycle": life_diag}
    except Exception as exc:  # total failure → no-op, original state preserved
        return original_state, working_rolling, {
            "lifecycle": {"lifecycle_enabled": True, "lifecycle_applied": False, "error": str(exc)[:200]}
        }
