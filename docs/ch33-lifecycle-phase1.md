# Chapter 33 — NPC Lifecycle & Generational Succession

## Phase 1: Lifecycle Core — Aging, Mortality, and Death Events

**Branch:** `emergent` · **Feature flag:** `ENABLE_NPC_LIFECYCLE` (default **OFF**)
**Modules:** `backend/npc_lifecycle.py`, `backend/simulation_clock.py` · **Tests:** `backend/tests/test_npc_lifecycle.py`, `backend/tests/test_simulation_clock.py`, `backend/tests/test_simulation_clock_hardening.py`

Phase 1 delivers the deterministic lifecycle core that later phases extend. The
core remains a pure module; the current working tree also includes a structured
clock seam in `backend/simulation_clock.py` and `replayability.prepare_action_turn`.
With the flag OFF, no clock/lifecycle state is created and no player-visible
gameplay behavior changes.

> **Canon note.** `Source_of_Truth_v1.2.md` contains detailed Chapter 33 text
> and Appendix A.7 lifecycle constants. The default-human constants here mirror
> that contract and remain centralized in `backend/npc_lifecycle.py`.

---

### State schema

Canonical per-NPC lifecycle record (engine-owned; never authored from prose):

| Field | Type | Meaning |
|-------|------|---------|
| `npc_id` | str | Stable NPC identity |
| `birth_simulation_day` | int | Authoritative birth day (integer simulation day) |
| `lifecycle_profile` | str | Profile id (`"human"` default; configurable) |
| `life_stage` | str | Derived: `child` / `adult` / `elder` / `venerable` / `archived` |
| `alive` | bool | Liveness; `False` is permanent |
| `death_simulation_day` | int \| None | Day of death |
| `death_cause` | str \| None | Recorded cause |
| `last_mortality_evaluation_day` | int \| None | Per-period idempotency guard |
| `schema_version` | int | `LIFECYCLE_SCHEMA_VERSION = 1` |
| `migrated` | bool | Whether this record was defaulted by migration |

`life_stage` is **derived** from `current_simulation_day − birth_simulation_day`
and is never independently mutable by the model.

### Time contract

Lifecycle functions accept an **explicit integer simulation day**
(`current_simulation_day`, `birth_simulation_day`, …). `1 year = 365 days`.
There is **no `turn_number × 60`** and no invented turn duration anywhere. The
structured clock seam advances time only from an engine-owned
`pending_time_advance` event with an expected-previous-day precondition; ordinary
turns advance zero days.

### Life stages (Appendix A.7 default-human profile)

`child 0–15`, `adult 16–49`, `elder 50–69`, `venerable 70+` (bounds by completed
years; boundaries land exactly at 15/16, 49/50, 69/70). Profiles are configurable
for non-human/setting species via a `profile` dict; constants are centralized in
`npc_lifecycle.DEFAULT_HUMAN_PROFILE` / `LIFECYCLE_PROFILES`.

### Mortality formula (natural, per simulation year)

```
p = BASE_ADULT_MORTALITY_PER_YEAR × age_factor × health_factor × pressure_factor
BASE_ADULT_MORTALITY_PER_YEAR = 0.005          # 0.5% / year
age_factor  = 1.0                              for age ≤ 50
            = 2 ** ((age − 50) / 8)            past 50 (doubles ~every 8 years)
health_factor   ∈ [1.0, 5.0]  (clamped)
pressure_factor ∈ [1.0, 2.0]  (clamped)
p is clamped to [0.0, 1.0]; p = 0.0 below age 16 (min mortality age)
```

Evaluation is deterministic and idempotent per **evaluation period** (the sim-year
`current_simulation_day // 365`). The roll is a counter-based hash draw:
`derive_rng_unit(build_seed_material(run_seed, period, "npc_lifecycle_mortality",
npc_id, hash(inputs)), 0)` — **no process-global RNG**, identical for identical
`(run_seed, npc_id, period)`. An NPC already evaluated in the current period is
skipped (no reroll); dead / archived / sub-age records are never evaluated.

### Event contract

Natural **and** unnatural death pass through one authoritative, idempotent
transition (`apply_death`): `alive → dead` exactly once, death day + cause
recorded, the NPC record **preserved** (never deleted) and projected to
`archived`, a duplicate death refused (returns event `None`). Each death emits a
structured event:

| Field | Meaning |
|-------|---------|
| `event_id` | Deterministic (`lifeevt-…`, from npc_id + day + cause) |
| `event_type` | `"npc_death"` |
| `npc_id`, `simulation_day`, `cause` | Identity, time, cause |
| `classification` | `"natural"` \| `"unnatural"` |
| `caused_by` | Upstream event IDs (where available) |
| `seed_provenance` | Mortality seed material for natural deaths |
| `before` / `after` | Lifecycle snapshots |

Events are **returned** from the pure layer. This repository has **no formal
Chapter 22 event store** (system-doctrine candidate invariant, unimplemented), so
Phase 1 does not invent a competing event store. The structured clock seam
appends a minimal bounded receipt via the existing `transition_receipts` path
and records committed lifecycle deaths in the engine-owned
`rolling_state["deceased"]` registry.

### Actor-Resolution-tier contracts

Tiers are consumed as **input** (existing Actor Resolution output); this phase
does not change actor enumeration.

| Tier | Aging | Mortality |
|------|-------|-----------|
| Hero / Active | individual | individual |
| Relevant | individual | individual (regional-heartbeat cadence set by caller) |
| Dormant | batch / catch-up | batch API (`process_dormant_batch`) and structured-clock catch-up; every death still emits an event; aggregate births NOT implemented |
| Archived | none | none (no-op) |

### Feature-flag behaviour

`ENABLE_NPC_LIFECYCLE` default **OFF** (env-overridable). OFF → no live aging or
mortality; pure functions/tests still available; no player-visible gameplay
change. ON → lifecycle work runs only through pure lifecycle functions or the
structured clock seam (fail-closed: invalid time input or lifecycle planning
failure leaves lifecycle records unchanged and emits developer diagnostics).
Diagnostics are developer-only and never enter the prompt.

### Structured clock seam status

`backend/simulation_clock.py` provides an authoritative integer simulation-day
clock and a flag-gated, fail-closed seam in `replayability.prepare_action_turn`.
Time advances only from an engine-owned structured event; ordinary turns advance
the clock by zero. The seam persists lifecycle records in `replayability_state`,
projects deaths to `rolling_state["deceased"]`, and appends bounded receipts.

This is **offline deterministic integration**, not full gameplay time passage:
there is still no action-duration/in-story-time producer that stages
`pending_time_advance` during ordinary play, and burn-in integration is not
implemented.

### Deferred to later Chapter 33 phases (NOT in Phase 1)

Births · pregnancy · partnership/family formation · family trees · property
inheritance · inherited dispositions · inherited grudges · leadership succession ·
disputed-inheritance pressure · 200-year burn-in turnover · prompt injection ·
player-facing death announcements · action-duration to structured-time mapping ·
live/burn-in lifecycle producers.

Chapter 33 is **not** complete. This is Phase 1 (lifecycle core) only.
