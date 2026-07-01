# Chapter 33 — NPC Lifecycle & Generational Succession

## Phase 1: Lifecycle Core — Aging, Mortality, and Death Events

**Branch:** `emergent` · **Feature flag:** `ENABLE_NPC_LIFECYCLE` (default **OFF**)
**Module:** `backend/npc_lifecycle.py` (pure, deterministic) · **Tests:** `backend/tests/test_npc_lifecycle.py`

Phase 1 delivers the deterministic lifecycle core that later phases extend. It is
a **new self-contained module** with no live wiring into `server.py` /
`replayability.py` — see *Live integration status* below. With the flag OFF,
gameplay is byte-identical; the pure functions and tests remain available.

> **Canon note.** `Source_of_Truth_v1.2.md` Chapter 33 and Appendix A.7 are
> currently stubs (table-of-contents + intro only). The numeric constants here
> are therefore **designed extensions** supplied by the Phase-1 specification —
> the same convention used for `backend/stress.py` — kept in one module.

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
There is **no `turn_number × 60`** and no invented turn duration anywhere. See
*Live integration status* for the missing-clock dependency.

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
Phase 1 does not persist events itself and invents no competing store; the
deferred live seam will append a minimal receipt via the existing append-only
`transition_receipts` path and record deaths in the engine-owned
`rolling_state["deceased"]` registry.

### Actor-Resolution-tier contracts

Tiers are consumed as **input** (existing Actor Resolution output); this phase
does not change actor enumeration.

| Tier | Aging | Mortality |
|------|-------|-----------|
| Hero / Active | individual | individual |
| Relevant | individual | individual (regional-heartbeat cadence set by caller) |
| Dormant | — | batch API (`process_dormant_batch`); every death still emits an event; aggregate births NOT implemented |
| Archived | none | none (no-op) |

### Feature-flag behaviour

`ENABLE_NPC_LIFECYCLE` default **OFF** (env-overridable). OFF → no live aging or
mortality; pure functions/tests still available; gameplay unchanged. ON → only
`evaluate_lifecycle_tick` acts (fail-closed: a missing simulation day or any
internal error yields a no-op with a developer diagnostic, never a raise, never
mutated NPC state). Diagnostics are developer-only and never enter the prompt.

### Live integration status (blocker)

`evaluate_lifecycle_tick` is the wired-seam entry point but is **not called from
the turn path**: there is no authoritative simulation clock in the repository
(cf. `D_GRACE` — `BLOCKED_BY_MISSING_AUTHORITATIVE_INPUT — SIMULATION_TIME`).
Wiring live aging requires an authoritative `current_simulation_day` source; this
is a later-phase dependency. Phase 1 deliberately does **not** advance lifecycle
from ordinary turns.

### Deferred to later Chapter 33 phases (NOT in Phase 1)

Births · pregnancy · partnership/family formation · family trees · property
inheritance · inherited dispositions · inherited grudges · leadership succession ·
disputed-inheritance pressure · 200-year burn-in turnover · prompt injection ·
player-facing death announcements · authoritative simulation-clock integration.

Chapter 33 is **not** complete. This is Phase 1 (lifecycle core) only.
