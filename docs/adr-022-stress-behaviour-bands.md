# ADR-022: Chapter 14 P2 stress behavioural bands + Utility AI integration

**Status:** Proposed (unmerged — draft PR into `emergent`)
**Date:** 2026-06-24
**Deciders:** Ryan
**Branch:** `codex/ch14-stress-behaviour` (canonical base `02646ab`)
**Builds on:** ADR-021 (P1 stress substrate, accepted on `emergent`)
**Defers:** P3 breaking points, P4 social/collective stress

---

## Context

P1 (ADR-021) made `stress_level` an authoritative, persisted, deterministic
per-actor scalar and emitted it into the foundation snapshot's utility inputs.
P2 consumes that value: it derives a behavioural **band** on read and uses the
band to modify the canonical Ch 27 Utility AI dimension weights (goal-narrowing,
14.24/14.27), shadow-only.

Chapter 14 is non-numerical ("Thresholds are behavioural, not numerical"). Every
cut-point and modifier below is therefore a DESIGNED_EXTENSION, logged in
`docs/foundation-canon-deltas.md`, not a canon transcription.

## Decision

Add a pure classification layer in `backend/stress.py`
(`evaluate_stress_behaviour`) and integrate it exactly once into
`utility_ai.select_action`.

### Bands and thresholds (designed extension)

Four bands on the 0-100 axis. Lower bound inclusive, upper bound exclusive,
except OVERLOADED includes the maximum (100):

| Band | Range |
|------|-------|
| CALM | 0 <= s < 25 |
| ELEVATED | 25 <= s < 50 |
| STRAINED | 50 <= s < 75 |
| OVERLOADED | 75 <= s <= 100 |

This **supersedes the 6-band proposal** in the ADR-021 "Proposed constants"
table (Stable/Strained/Stressed/Overloaded/Critical/Collapse). The 6-band split
was a starting proposal; P2 ratifies a simpler 4-band model. The Critical/Collapse
(breaking-point) end moves to P3.

### Weight modifiers (designed extension)

Applied exactly once on top of the canonical dynamic weights. `stress_reduction`
stays x1.0 in every band because Ch 27.4.2 already scales it by `stress/100` —
a band multiplier would double-count authoritative stress.

| Dimension | CALM | ELEVATED | STRAINED | OVERLOADED |
|-----------|------|----------|----------|------------|
| survival | 1.00 | 1.10 | 1.25 | 1.60 |
| goal_progression | 1.00 | 0.85 | 0.60 | 0.30 |
| pressure_relief | 1.00 | 1.10 | 1.30 | 1.50 |
| stress_reduction | 1.00 | 1.00 | 1.00 | 1.00 |
| relationship_impact | 1.00 | 0.95 | 0.80 | 0.50 |
| resource_gain_loss | 1.00 | 1.00 | 0.85 | 0.60 |
| memory_avoidance | 1.00 | 1.00 | 1.10 | 1.25 |

Higher bands narrow toward survival/relief and away from goals/relationships
(goal-narrowing), but the band never selects an action: selection stays the
existing weighted-utility argmax with seeded whim noise and deterministic
tie-breaking.

### Exact-once application point

In `utility_ai.select_action`, immediately after the canonical weights are built
by `compute_dimension_weights(...)` and before utility scoring:
`weights = apply_stress_band_modifiers(baseline_weights, behaviour["modifiers"])`.
Applied once per candidate, nowhere else.

### Authoritative source

The band derives from `snapshot.utility_input_refs[actor].stress_level`
(None-preserving), NOT the candidate's coerced `stress` field — which
`candidates_from_agendas` flattens missing -> 0.0 and would misread as CALM.

## Fail-closed contract

Missing or invalid authoritative stress is NEVER treated as CALM. For missing,
non-numeric / wrong-type, NaN, +/-inf, negative, or >100:

- no band is assigned (`band = None`);
- identity (x1.0) modifiers are returned, so weights are unchanged;
- `stress_input_valid = False`;
- an explicit blocker code is recorded;
- `replacement_authorised` is forced False (the band can never authorise);
- the candidate stays visible in shadow diagnostics (`score_table`) but cannot
  become an authorised replacement; no maximum / emergency bonus is produced.

Blocker codes (distinct by cause):

| Cause | Code |
|-------|------|
| missing (None) | `MISSING_STRESS_LEVEL` (preserved from P1) |
| wrong type / non-numeric (incl. bool, numeric string) | `INVALID_STRESS_LEVEL` |
| NaN / +inf / -inf | `NONFINITE_STRESS_LEVEL` |
| < 0 or > 100 | `OUT_OF_RANGE_STRESS_LEVEL` |

## Determinism / hash safety

- Band derivation and modifier application are pure functions of authoritative
  inputs; same inputs -> identical output.
- The candidate is never mutated, so `candidate_set_hash`, the whim-noise seed
  material, the noise draw, and tie-breaking are unchanged. CALM and every
  invalid input apply x1.0 modifiers, so `weights`, `base_utility`,
  `noisy_utility`, and the prepared `state_hash` are byte-identical to pre-P2.
- P2 diagnostic fields (`stress_band`, `stress_input_valid`,
  `stress_blocker_code`) are shadow-only and EXCLUDED from `state_hash`
  (`_hashable_candidate`). A valid non-CALM band's weight change does flow into
  the hash via `weights`/`base_utility` — that is real scoring, not a diagnostic.
- P1 foundation snapshot identity rules are untouched (no snapshot changes).

## Scope / non-goals

- P1 stress accumulation, capacity, decay, actor scope, and off-screen retention
  are unchanged.
- Utility AI remains shadow-only and non-load-bearing; no live action flip.
- P3 (breaking-point archetypes + world moves) and P4 (social / collective
  stress) remain deferred.

## Verification (truthful, this pass)

- `backend/stress.py` and `backend/utility_ai.py` compile (`py_compile`).
- New P2 suite `backend/tests/test_stress_behaviour.py`: 66 passed.
- Focused non-live bundle (stress / stress_behaviour / stress_integration /
  utility_ai / utility_dimensions / foundation_integration / engine_determinism /
  foundation_acceptance): 139 passed, 1 pre-existing unrelated failure
  (`test_prompt_fingerprint::test_server_prompt_unchanged_since_base` — a
  commit-range server.py fingerprint vs base `9da1ae2`, red at the canonical base
  independent of P2).
- Determinism, candidate-hash/noise stability, CALM/missing `state_hash`
  equality, and stress-free legacy equivalence are covered and green.
- Turn-path tests requiring fastapi + MongoDB were not run in this sandbox (the
  repo's `backend/secrets.py` shadows stdlib `secrets` under CWD=backend, and
  they need a live DB). No verification is claimed beyond tests actually run.

## Files

- Modified: `backend/stress.py` (pure layer), `backend/utility_ai.py` (integration).
- New: `backend/tests/test_stress_behaviour.py`, this ADR.
- Docs: `foundation-canon-deltas.md`, `decision-log.md`, `feature-status.md`,
  `failure-modes.md`, `current-state.md`.

## Consequences

- Utility weighting now reflects accumulated stress (goal-narrowing) in shadow,
  giving P3 a behavioural substrate.
- A new set of designed constants (bands, modifiers) to tune against play.
- Revisit cut-points / modifiers after playtest; reconcile with the deferred
  6-band archetype split when P3 lands.

## Action items

1. [ ] Review the 4-band cut-points and modifier table against play.
2. [ ] Keep Utility AI shadow-only until a separate load-bearing ADR + proof.
3. [ ] On acceptance, append an ADR-022 summary row workflow and proceed to P3.
