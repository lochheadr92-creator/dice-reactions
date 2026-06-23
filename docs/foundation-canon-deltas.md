# Foundation Canon Deltas — Executable Ledger v1.0.0

**Harness:** `backend/tests/foundation_acceptance/` (test-owned, not production policy)  
**Ledger hash:** computed at test time from `delta_ledger.ledger_hash()`  
**Branch:** `reimplementation/foundation-systems-v01`  
**Not merged. Not deployed. No production replacement authorised.**

## Executable delta registry

| Delta ID | System | Facet | Status | Canon ref | Replacement |
|----------|--------|-------|--------|-----------|-------------|
| `D_SEL` | utility_ai | action_kind | PLACEHOLDER_BLOCKED | Ch 27.5 L18949–L18956 | Blocked until oracle + inputs complete |
| `D_UTILITY_PLACEHOLDER` | utility_ai | dimension_score | PLACEHOLDER_BLOCKED | Ch 27.4.1 L18910–L18927 | Diagnostic only |
| `D_TIER_ASSIGNMENT` | actor_resolution | tier | NOT_MACHINE_CHECKABLE | Ch 25.8 L18521–L18530 | Missing Context Gravity |
| `D_ACTING_ELIGIBILITY` | actor_resolution | eligibility | ACTIVE | Ch 25.3 | Witness required |
| `D_TIER_PROCESSING_CADENCE` | actor_resolution | processing_eligibility | ACTIVE | Ch 27.6 L18966–L18974 | Witness required |
| `D_GRACE` | actor_resolution | tier | PLACEHOLDER_BLOCKED | Ch 25.6 L18490–L18495 | `BLOCKED_BY_MISSING_AUTHORITATIVE_INPUT — SIMULATION_TIME` |
| `D_MEMORY_RETRIEVAL_SHADOW` | memory_retrieval | retrieval_membership | NOT_MACHINE_CHECKABLE | Ch 28.3 L19118–L19133 | `SEPARATE_SHADOW_ACCEPTANCE_REQUIRED` |

## Documented divergences (descriptive)

| System | Canon requirement | v0.1 behaviour | Reason | Reconciliation path |
|--------|-------------------|----------------|--------|---------------------|
| Actor Resolution | Promotion from spatial/event triggers | Retention+gravity signals; no Ch 20 Context Gravity | Context Gravity not computed | Compute G_peak per Ch 20.17 |
| Actor Resolution | Grace in simulation minutes | Explicit-time fixtures only; turn×60 proxy in production | No simulation clock | Add `simulation_minutes` authority |
| Utility AI | Full dimension inputs | Canon formulas; stress/SVU blocked without inputs | Missing authoritative fields | Extend utility_input_refs |
| Utility AI | Replace `score_move` | Provisional path retained | Harness not PASS_FOR_REPLACEMENT | Frozen corpus + coverage |
| Memory Retrieval | Prompt inclusion | Shadow only | Increment scope | Separate shadow acceptance |
| Numeric contract | IEEE rounding | Full float until clamp | Canon silent | Approve rounding table |

## Chapter 14 — Stress substrate (P1, ADR-021) — designed numeric extensions

Canon Ch 14 is **non-numerical** ("Thresholds are behavioural, not numerical").
Appendix A carries no stress accumulation rate, decay constant, capacity number,
or threshold cut-point — the only stress number in canon is the Ch 27.4.2 weight
(20), which lives in `utility_ai.BASE_WEIGHTS`. **Every value below is therefore a
designed extension, not a canon transcription.** All live in `backend/stress.py`
as named module constants (per the codebase's "constants in the registry"
convention; there is no central registry module). Values ratified 2026-06-22 from
the ADR-021 "Proposed constants" table; starting points to tune against play.

| Constant (`stress.py`) | Value | Canon chain | Rationale |
|------------------------|-------|-------------|-----------|
| `STRESS_MIN` / `STRESS_MAX` | `0.0` / `100.0` | Ch 27.7 range | Authoritative scalar bounds |
| `STRESS_DECAY_PER_TURN` | `0.85` (half-life ≈ 4.3 turns) | 14.6 accumulation / 14.34 recovery | Baseline per-turn dissipation applied every update; continuing pressure generation can outweigh it (decay is NOT conditional on safety) |
| `STRESS_CAPACITY_MIN/MAX` | `0.7` / `1.3` (nominal `1.0`) | 14.5 (proxy) | Deterministic per-actor capacity **proxy**, stable across replay but **not** derived from authoritative personality traits; divides generation (higher = more resilient). Replace when personality-based capacity inputs exist |
| `STRESS_GENERATION_SCALE` | `100.0` | 14.4 pressure→stress | Lifts 0–1 pressure intensity onto the 0–100 stress axis |
| `STRESS_THREAT_WEIGHT_BASE` | `1.0` | 14.4 interpretation | Default perceived-threat weight |
| `STRESS_THREAT_WEIGHT_FEAR_BONUS` | `0.25` | 14.4 interpretation | See `D_STRESS_FEAR_INTERPRETATION` — interpretation policy, not just a number |

Model: `g_t = SCALE · highest_pressure_intensity · threat_weight / C`;
`stress_t = clamp_{0..100}( stress_{t-1} · decay + g_t )`. **Capacity `C` is divided
in exactly once — inside `generate()`; `accumulate()` adds the generated value
unchanged apart from decay+clamp** (guard test: `test_generation_divides_capacity_exactly_once`).
`C` is a seeded per-actor derivation via `engine_determinism.build_seed_material` +
`derive_rng_range` (no new RNG source). Persisted in `rolling_state["actor_stress"]`,
engine-owned (re-asserted after `consolidate_rolling_state` via
`stress.enforce_authoritative_stress`).

**Snapshot hash commitment — exact boundary:** the authoritative stress values are
committed into `source_state_hash` (provenance, not just determinism), but the digest
is **omitted when no authoritative stress values exist** (key absent, `{}`, or only
None-valued entries). Legacy hash identity is therefore claimed **only for rolling
states where `actor_stress` is absent entirely** — an empty/inert `actor_stress` key
already changes `rolling_keys` (pre-existing), independent of this digest.
Historical byte-identity vs the pre-P1 implementation is confirmed against commit
`b4e5fcc`: the stress-free fixture hash is
`7d2825b108b1da752b9fcfbdd10b9916295179d85eb3e9a0b047dfa7c4535134` both before
and after P1. Existing stress-free foundation fixtures also remain green.

**Actor update scope (P1 policy):** only actors in the authoritative interpretation
set this turn update — **alive actors the engine is actually simulating (those
carrying an active agenda)**. Actors outside that set **retain their existing stress
unchanged** (no decay, no generation), avoiding free global recovery without inventing
cadence. Full tier-based recovery / offscreen decay (Ch 27.6 processing cadence) is
**deferred** to before P2. (Guard: `test_offscreen_actor_retains_stress_unchanged`.)

**Deferred to later sub-phases (NOT in P1):** behavioural state bands + goal-narrowing
weight modifiers (P2, 14.9–14.15/14.24/14.27); breaking-point archetypes + world-move
emission (P3, 14.16–14.23); social/collective stress (P4, 14.29–14.33).

`DESIGNED_EXTENSION` below is a **design classification** (the value is a designed
choice, canon being non-numerical). It is distinct from **runtime status** (lifecycle).
Runtime status is promoted only as tests/acceptance genuinely pass.

| Delta ID | Facet | Classification | Runtime status | Canon ref | Notes |
|----------|-------|----------------|----------------|-----------|-------|
| `D_STRESS_NUMERIC_MODEL` | stress_level | `DESIGNED_EXTENSION` | `TURN_INTEGRATION_VERIFIED` | Ch 14.4/14.6/14.34 | 69-test offline bar and two real-turn/clobber integration tests pass |
| `D_STRESS_CAPACITY` | capacity | `DESIGNED_EXTENSION` | `TURN_INTEGRATION_VERIFIED` | Ch 14.5 (proxy) | Seeded per-actor proxy; not personality-derived |
| `D_STRESS_FEAR_INTERPRETATION` | perceived_threat | `DESIGNED_EXTENSION` | `TURN_INTEGRATION_VERIFIED` | Ch 14.4 | Agenda fear (`fear_kind != ""`) currently applies a **general** threat multiplier to ALL applicable pressure; pressure-to-fear relevance matching deferred — an unrelated fear can magnify an unrelated pressure |

Runtime-status lexicon: `COMPONENT_VERIFIED / TURN_INTEGRATION_UNVERIFIED` (component
code present and unit/offline-verified; feeds shadow foundation eval; the large
turn-path files `replayability.py`/`server.py` were edited but **not compiled or
executed here** — the sandbox mount served truncated copies, so "confirmed-by-read"
only) → `TURN_INTEGRATION_VERIFIED` (those files compile + real-turn/clobber tests
pass on a clean checkout) → `ACCEPTANCE_VERIFIED` → `AUTHORISED_FOR_PRODUCTION_CONSUMPTION`.

## Harness verdict

`HARNESS_STRUCTURE_READY` — corpus execution deferred.

## Utility verdict

`UTILITY_STRESS_INPUT_COMPLETE — stress_level is authoritative and snapshot-produced;
D_SEL blocked only by any other incomplete required input.` The `stress_level` production
path exists in code (produced by `stress.update_actor_stress`, persisted under
`rolling_state["actor_stress"]`, emitted by `foundation_snapshot._utility_input_refs`,
protected by `stress.enforce_authoritative_stress`). Verified offline: a snapshot built
**with** `actor_stress` flips the bundle to `replacement_authorised = True`
(`test_gate_authorised_with_stress`); the missing-input fail-closed path is unchanged
(`test_gate_blocked_without_stress`).

Verified 2026-06-22 on Python 3.12: all four touched files compile; the focused
stress/foundation/utility/determinism bar is 69 passed; the real-turn snapshot-emission
and consolidation-clobber tests are 2 passed. The full backend collection recorded
628 passed with 34 live-HTTP failures/errors attributable to no service listening at
`localhost:8000`. Baseline hash equivalence confirmed vs `b4e5fcc`.

`UTILITY_CANON_CONTRACT_COMPLETE` applies only to fixtures with complete authoritative inputs (see `utility_oracle_complete_v1`).
