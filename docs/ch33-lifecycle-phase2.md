# Chapter 33 — NPC Lifecycle & Generational Succession

## Structured Clock Seam: Authoritative Simulation Clock & Lifecycle Integration

**Branch:** `emergent` · **Feature flag:** `ENABLE_NPC_LIFECYCLE` (default **OFF**)
**New module:** `backend/simulation_clock.py` · **Seam:** one flag-gated call in
`backend/replayability.py::prepare_action_turn` · **Tests:**
`backend/tests/test_simulation_clock.py`

This seam connects the deterministic Phase-1 lifecycle core to real turn
execution through an authoritative, replay-safe simulation clock. **Time never
advances from ordinary turns** — only from an explicit engine-owned structured
event. With the flag OFF the seam is a complete no-op: no clock/lifecycle state
is created and no player-visible gameplay behavior changes.

Flow: structured time-advance → authoritative clock → due lifecycle periods →
pure lifecycle evaluation (plan) → validation → atomic commit → deceased-registry
+ transition-receipt projection → developer diagnostics. No part reads prose.

### Clock state schema (engine-owned; in `replayability_state`)

```
simulation_clock = {
  schema_version: 1,
  current_simulation_day: int,               # authoritative integer sim day
  last_applied_advance_event_id: str | None, # idempotency guard
  lifecycle_processed_through_day: int,       # lifecycle processing cursor
  migrated: bool                              # transient: did this load migrate?
}
npc_lifecycle = { npc_id: <Phase-1 lifecycle record>, ... }
```

Both live in `replayability_state`, which is engine-owned, never LLM-authored,
and excluded from player payloads (`player_api` allowlist + `replayability_state`
stripping). The LLM cannot modify birth day, current day, life stage, alive/dead
status, death day, death cause, or the processing cursor.

### Structured time-advance contract

```
time_advance = {
  event_id: str,                 # deterministic / approved engine event id
  elapsed_simulation_days: int,  # integer >= 0
  reason: str,
  source_type: str,
  source_event_ids: [..],        # where available
  expected_previous_simulation_day: int,  # required by the authoritative seam
  target_simulation_day: int,    # optional — consistency check
}
```

Supplied via `replayability_state["pending_time_advance"]` (consumed each turn).
`elapsed_simulation_days` must be a non-negative int; negative/invalid is
rejected; a repeated `event_id` is a no-op (time never moves backwards);
zero-day advances are valid no-ops; **no prose field can create or alter elapsed
time**. Ordinary turns supply nothing → the clock advances by exactly zero. There
is no automatic action-duration inference (deferred).

**Permanent replay safety.** No authoritative monotonic event sequence exists for
time-advance events (the repository has no event sourcing — not claimed). The
permanent duplicate barrier is therefore an explicit **clock-state precondition**:
authoritative events must supply `expected_previous_simulation_day`, and an event
advances the clock only if that equals `current_simulation_day`. A stale event
(expected < now) is a
duplicate/stale no-op **even after its id has been evicted** from the bounded
`recent_advance_event_ids` window; a future/out-of-order event (expected > now) is
rejected; an optional `target_simulation_day` must equal
`expected_previous_simulation_day + elapsed_simulation_days`. The bounded
recent-ID list is fast duplicate detection and diagnostics only — **not** the
permanent replay authority. Old events remain harmless after receipt eviction.

### Migration

Absent/invalid clock state migrates deterministically to
`current_simulation_day = 0`, `lifecycle_processed_through_day = 0` — never
wall-clock, never retroactive aging, never negative, never backwards. Valid
existing clock state is preserved; `migrated` is exposed.

### Lifecycle scheduling contract

Lifecycle runs only when: flag ON, valid clock state, and
`current_simulation_day > lifecycle_processed_through_day` (≥1 due sim-year
period). Ordinary turns do not re-evaluate mortality. Elapsed-time jumps process
only **due** mortality periods (sim-years) in deterministic order by NPC id and
period — never one loop per day; stage is derived directly from the final day.
Catch-up is bounded by `MAX_CATCHUP_PERIODS` (50); the processing cursor persists
and remaining backlog is exposed. No due period is skipped. Full 200-year burn-in
is **not** implemented.

### Failure & retry semantics (atomic, fail-closed)

Clock advance and lifecycle have separate authority. The clock advance is
committed first. Lifecycle is **planned on copies, validated, then committed
atomically**. If lifecycle planning/validation fails: the clock advance remains,
`lifecycle_processed_through_day` does **not** advance, NPC records are unchanged,
no partial death state is left, and the same overdue periods retry
deterministically later (mortality rolls are seeded by period, so retries never
reroll). Any total failure is a full no-op. Failures emit developer-only
diagnostics and never enter the prompt.

### Death persistence path

Natural and unnatural death both pass through the single Phase-1 authoritative
`apply_death` transition. A committed death produces: (1) preserved lifecycle
record marked dead + `life_stage="archived"`; (2) projection into the existing
engine-owned `rolling_state["deceased"]` registry (which makes
`resolve_actor_tier` return `archived`, excluding the NPC from acting); (3) one
bounded structured transition receipt (`receipt_type="npc_lifecycle_death"`,
deterministic id) via the existing append-only receipt seam
(`replayability._append_transition_receipt`, passed in as a callback — no second
store). Re-applying the same death is idempotent across the registry, the
receipt, and the archive transition. This repository has **no formal Chapter 22
event sourcing**; deaths are bounded transition receipts + lifecycle events, not
an event-sourced log.

### Feature-flag behaviour

`ENABLE_NPC_LIFECYCLE` default **OFF** (reused; no separate clock flag). OFF →
the seam is a complete no-op: no clock, no migration, no aging/mortality, no
persisted events, no prompt content, and no player-visible gameplay change. ON →
a valid structured advance may make periods due;
only due periods evaluate; failures stay fail-closed; deterministic developer
diagnostics show authority and fallback status.

### Diagnostics (developer-only; never in the prompt)

`simulation_clock`: authority, feature status, previous/requested/applied elapsed
days, resulting day, advance event id, duplicate/no-op, migration, validation
failure. `lifecycle`: enabled, due, processed-from/through day, remaining
backlog, NPCs evaluated, tier counts, stage transitions, mortality periods
evaluated, death event ids, duplicate deaths rejected, deceased projections,
receipts appended, fallback/error. These flow into `diagnostics` → `turn.debug`
(developer-gated) and `replayability_state` (player-stripped) — no clock,
probability, roll, or lifecycle value reaches the player prompt or response.

### Tests

`test_simulation_clock.py` — clock migration; time-advance (positive/zero/
negative/duplicate/none/prose-ignored/replay); scheduling (not-due no-op, one due
period, ordinary-turn no-reroll, bounded large jump + backlog, archived/dead
skipped, deterministic tier ordering); atomicity (failed lifecycle leaves records
+ cursor unchanged, deterministic retry); death persistence (registry + one
receipt, record preserved, duplicate no-dup); feature flag (OFF total no-op, ON
no-advance no-work); and the **end-to-end golden-path** through
`replayability.prepare_action_turn`. Phase-1 lifecycle tests and the foundation/
replayability/actor/utility/gateway/context-budget regressions remain green.

### Deferred to later Chapter 33 phases (NOT in this seam)

Automatic action-duration inference / narrative duration parsing · births ·
pregnancy · fertility · partnership/family formation · family trees · inheritance
· inherited traits/dispositions/grudges · leadership succession · disputed-
inheritance pressure · 200-year burn-in turnover · player-facing lifecycle UI or
death narration.

**This seam does not infer time from ordinary turns; time stays zero unless an
approved structured advance occurs. Chapter 33 is NOT complete.**
