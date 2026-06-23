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


## Chapter 14 — Stress behavioural bands (P2, ADR-022) — designed extensions

**Status: proposed, unmerged (draft PR on `codex/ch14-stress-behaviour`, base
`02646ab`). Shadow-only; no production replacement authorised.**

Canon Ch 14 is non-numerical; every cut-point and modifier below is a
`DESIGNED_EXTENSION` (ADR-022), not a canon transcription. Bands are derived on
read in `stress.evaluate_stress_behaviour`; they are never persisted or accepted
from model output. This **supersedes the 6-band proposal** in the ADR-021
"Proposed constants" table — P2 ratifies a 4-band model; the Critical/Collapse
archetype end moves to P3.

Thresholds (lower bound inclusive, upper exclusive; OVERLOADED includes 100):

| Band | Range |
|------|-------|
| CALM | 0 <= stress < 25 |
| ELEVATED | 25 <= stress < 50 |
| STRAINED | 50 <= stress < 75 |
| OVERLOADED | 75 <= stress <= 100 |

Weight modifiers (applied exactly once on top of canonical Ch 27 dynamic weights,
in `utility_ai.select_action` after `compute_dimension_weights`):

| Dimension | CALM | ELEVATED | STRAINED | OVERLOADED |
|-----------|------|----------|----------|------------|
| survival | 1.00 | 1.10 | 1.25 | 1.60 |
| goal_progression | 1.00 | 0.85 | 0.60 | 0.30 |
| pressure_relief | 1.00 | 1.10 | 1.30 | 1.50 |
| stress_reduction | 1.00 | 1.00 | 1.00 | 1.00 |
| relationship_impact | 1.00 | 0.95 | 0.80 | 0.50 |
| resource_gain_loss | 1.00 | 1.00 | 0.85 | 0.60 |
| memory_avoidance | 1.00 | 1.00 | 1.10 | 1.25 |

`stress_reduction` stays x1.0 in every band: Ch 27.4.2 already scales it by
`stress/100`; a band multiplier would double-count. Higher bands narrow toward
survival/relief and away from goals (goal-narrowing 14.24/14.27), but the band
never selects an action; selection stays weighted-utility argmax + seeded noise.

**Fail-closed.** Missing/invalid authoritative stress is never CALM: no band,
identity (x1.0) modifiers, `stress_input_valid = False`, `replacement_authorised`
forced False, candidate visible in shadow `score_table` but never an authorised
replacement, no maximum/emergency bonus. Blocker codes: `MISSING_STRESS_LEVEL`
(preserved from P1), `INVALID_STRESS_LEVEL` (wrong type incl. bool/numeric
string), `NONFINITE_STRESS_LEVEL` (NaN / +/-inf), `OUT_OF_RANGE_STRESS_LEVEL`
(< 0 or > 100).

| Delta ID | Facet | Classification | Runtime status | Canon ref | Notes |
|----------|-------|----------------|----------------|-----------|-------|
| `D_STRESS_BANDS` | stress band | `DESIGNED_EXTENSION` | `COMPONENT_VERIFIED / TURN_INTEGRATION_UNVERIFIED` | Ch 14.9-14.15/14.24/14.27 | 4-band cut-points 25/50/75; supersedes ADR-021 6-band proposal |
| `D_STRESS_WEIGHT_MODIFIERS` | utility weights | `DESIGNED_EXTENSION` | `COMPONENT_VERIFIED / TURN_INTEGRATION_UNVERIFIED` | Ch 27.4.2 | Applied once in `select_action`; `stress_reduction` fixed x1.0 |
| `D_STRESS_BAND_FAILCLOSED` | input validity | `DESIGNED_EXTENSION` | `COMPONENT_VERIFIED / TURN_INTEGRATION_UNVERIFIED` | Ch 27.7 | MISSING/INVALID/NONFINITE/OUT_OF_RANGE_STRESS_LEVEL; forces `replacement_authorised=False` |

**Hash safety.** Candidate identity, `candidate_set_hash`, noise seed material,
the noise draw, and tie-breaking are unchanged (the candidate is not mutated). P2
diagnostic fields are excluded from the prepared `state_hash`
(`utility_ai._hashable_candidate`); CALM and every invalid input apply x1.0
modifiers, so weights/`base_utility`/`state_hash` are byte-identical to pre-P2.
P1 actor/off-screen policy and foundation snapshot identity rules are unchanged.

**Verification (this pass, truthful):** both touched files compile; focused
non-live bundle 139 passed + 1 pre-existing unrelated failure
(`test_prompt_fingerprint` server.py commit-range vs `9da1ae2`); new
`test_stress_behaviour.py` 66 passed; determinism/hash-boundary green. Turn-path
tests needing fastapi+MongoDB not run in this sandbox. P3/P4 deferred.
