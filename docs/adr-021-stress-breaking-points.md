# ADR-021: Chapter 14 Stress & Breaking Points as authoritative actor state

**Status:** Proposed
**Date:** 2026-06-22
**Deciders:** Ryan
**Branch target:** `reimplementation/foundation-systems-v01` (merge to `emergent`)
**Supersedes / unblocks:** prerequisite for the Ch 27 Utility AI load-bearing flip (separate ADR)

---

## Context

Ch 27 Utility AI is implemented and runs live in **shadow mode**, but it cannot become
load-bearing. The blocker is one authoritative input:

- Canon (Ch 27.7) defines `stress_level` as a per-actor scalar `0–100`, classified
  `AUTHORITATIVE_ENGINE_STATE`. The stress-reduction dimension is `reduction × 100`, weight 20,
  modified `×(stress/100)` (Ch 27.4.1/27.4.2, Appendix A).
- The consumption side is already coded correctly (`utility_dimensions.score_stress_reduction`,
  `utility_ai.build_canonical_dimension_bundle`).
- The **production** side does not exist: `foundation_snapshot._utility_input_refs`
  (foundation_snapshot.py:179–230) emits no `stress_level` key, so `inputs.get("stress_level")`
  is always `None` → `MISSING_STRESS_LEVEL` → `replacement_authorised = False`.
  Verified: `tests/foundation_acceptance/test_d_sel_activation.py` (2 passed).

Canon for the production side is **Chapter 14 (Stress & Breaking Point Systems)**, which is
unbuilt. Two hard facts about that canon shape the decision:

1. **Chapter 14 is non-numerical.** It defines stress qualitatively — pressure→interpretation→
   tolerance→stress generation (14.4), accumulation over time (14.6), capacity per personality
   (14.5), six behavioural states (14.9–14.15), five breaking-point archetypes (14.16–14.23),
   plus social/collective/settlement/faction stress, transfer, burnout, recovery (14.24–14.34).
   It states explicitly: *"Thresholds are behavioural, not numerical."* Appendix A carries **no**
   stress accumulation rate, decay constant, capacity number, or threshold cut-point — the only
   stress number in the entire 20,932-line canon is the weight (20). **Every numeric value in a
   stress implementation is therefore a designed extension, not a canon transcription, and must
   be logged as a canon delta.**
2. **Canon requires accumulation over time (14.6).** A stateless per-turn derivation cannot
   satisfy this, so `stress_level` must be **persisted** authoritative state, not computed
   on the fly. This brings the determinism invariant into play (`engine_determinism.canonical_json`
   / stable hash, `run_identity`).

Decision scope was set to **wider** by the deciders: implement full Chapter 14 (including
breaking points), as its own milestone ahead of the Ch 27 flip — not the minimal one-field slice.

## Decision

Introduce Chapter 14 as a new **authoritative actor subsystem**:

- A persisted per-actor `stress_level` (`0–100`) in `rolling_state`, updated each turn by a
  deterministic **generation → capacity/tolerance → accumulation → decay/recovery** model.
- Six behavioural **state bands** derived from `stress_level`, used for narration and as utility
  weight modifiers (goal narrowing per 14.24/14.27).
- Five **breaking-point archetypes** (aggressive / withdrawal / rebellion / collapse / adaptive)
  triggered when accumulated stress exceeds capacity, emitting **world moves** via
  `npc_world_moves` (world-events-drive-pacing invariant), one-shot with cooldown.
- A deferred sub-phase for **social/collective stress** (transfer, settlement, faction, burnout).
- All numeric constants in the registry; all numeric choices recorded in
  `docs/foundation-canon-deltas.md` as documented divergences.
- `foundation_snapshot._utility_input_refs` emits `stress_level`, which unblocks Ch 27.

This ADR delivers the **stress substrate only**. Flipping Ch 27 to load-bearing remains a
separate downstream decision and carries its own numeric-equivalence proof obligation.

## Options Considered

### Option A: Full Ch 14 subsystem, persisted, phased  *(recommended; matches "wider scope")*
| Dimension | Assessment |
|-----------|------------|
| Complexity | High — new persisted state + state machine + breaking-point → move generation |
| Canon fidelity | High on structure; numeric model is a logged extension (canon is non-numerical) |
| Determinism risk | Medium — new authoritative state in the hashed path; mitigated by pure-function update + seeded RNG |
| Scope | Large — individual + social/collective stress |

**Pros:** Honors accumulation-over-time canon; gives Ch 27 a real authoritative input; adds
emergent breaking-point world events (pacing value); single coherent subsystem.
**Cons:** Largest surface; most determinism exposure; many designed constants needing tuning.

### Option B: Minimal individual stress only (no breaking points)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium |
| Canon fidelity | Partial — implements stress state but omits breaking points (14.16–14.23) |
| Determinism risk | Low–Medium |
| Scope | Small — just enough to unblock Ch 27 |

**Pros:** Fastest path to unblocking Ch 27; smallest determinism surface.
**Cons:** Leaves Chapter 14 half-built; breaking points are called *"among the most important
simulation mechanisms in the engine"* (14.16). **Rejected** per the wider-scope decision; retained
as a fallback if scope must be cut.

### Option C: Stateless derived stress in the snapshot builder
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Canon fidelity | Violates 14.6 (no accumulation over time) |
| Determinism risk | Low |
| Scope | Trivial |

**Pros:** Unblocks the gate immediately, no schema change.
**Cons:** Authorises Ch 27 replacement on a value canon says is authoritative *accumulated* state;
contradicts 14.6. **Rejected**; only viable as an explicitly ledgered divergence.

## Trade-off Analysis

The real axis is **canon fidelity vs. scope/determinism risk**. Canon forces a persisted,
accumulating value (kills C). The wider-scope decision plus 14.16's emphasis on breaking points
kills B as the end state. A is therefore the target; the risk it introduces (determinism surface,
many designed constants) is managed by **internal phasing with gates** rather than a big-bang
build, and by keeping the numeric model isolated in `backend/stress.py` + the registry so the
designed extensions are auditable and tunable in one place.

## Proposed numeric model *(designed extension — to be ratified, then logged as canon deltas)*

- **Generation** `g_t` = f(active pressure intensity on actor, acute threat flags, unmet/blocked
  goals). Canon chain 14.4.
- **Capacity / tolerance** `C` — per-actor; reduces incoming generation. *Open question: source
  of personality/capacity (see below).*
- **Accumulation + decay** `stress_t = clamp_{0..100}( stress_{t-1} · e^{−r·Δ} + g_t / C )`,
  mirroring the exponential decay convention already in Appendix A (relationships
  `V(t)=V_last·e^{−r·days}`, memory `G(t)=G_peak·0.5^{t/half_life}`). `r` and `Δ` units = registry
  constants. Recovery (14.34) = low `g_t` under safety/support → decay dominates.
- **Behavioural bands** map `0–100` → Stable / Strained / Stressed / Overloaded / Critical /
  Collapse. Cut-points = registry constants (designed; canon says these are behavioural).
- **Breaking points** (14.16–14.23): on entering Critical+ and exceeding capacity, deterministically
  select an archetype by actor disposition + seeded RNG (same seeded-draw discipline as utility whim
  noise), emit a world move via `npc_world_moves`, then apply a cooldown to prevent loops.
- **Decision effects**: 14.24/14.27 goal-narrowing → utility weight modifiers (the
  `×(stress/100)` stress weight already exists; extend to goal-flexibility reduction). 14.25/14.26
  (relationships, memory emotional bias / Ch 28) noted but kept minimal in this milestone.

## Existing scaffold — reconciliation required (verified 2026-06-22)

A partial breaking-point mechanism already exists and **diverges from canon on two axes**;
P3 is a reconciliation, not a greenfield build:

- **Axis mismatch.** `npc_agendas.BREAKING_POINTS` is a *cause/trigger* taxonomy
  (`trust_collapse`, `fear_threshold`, `resource_crisis`, `ally_harmed`, `faction_order`,
  `repeated_failure`, `public_humiliation`, `secret_exposure`, …). Canon Ch 14.18–14.23 breaking
  points are *response archetypes* (aggressive / withdrawal / rebellion / collapse / adaptive).
  These are orthogonal — the engine has the cause, canon specifies the response. P3 must add the
  response-archetype axis and map cause→response, not rename the existing list.
- **Trigger mismatch.** `breaking_fired` fires at `progress >= 85` (npc_agendas.py:297–298) —
  agenda progress, not stress. Canon 14.17 ties the break to accumulated stress exceeding
  capacity. P3 must move the trigger onto `stress_level` while preserving the existing one-shot
  semantics and the consumers at `npc_world_moves.py:300,410` and
  `living_cast_seeded_scenario.py:215` (currently gate a `defect` move). This is a behaviour-path
  change in a sanctioned world-move surface — equivalence/regression care applies.
- **No capacity field.** No numeric trait/capacity exists. Per-actor variation is seeded only
  (`sha256(run_seed:npc_id)` selections in `_new_agenda`; `personality_order` tie-keys in
  `utility_ai`). Capacity `C` and archetype bias will be **new seeded per-actor derivations**
  (deterministic, no new randomness source) — this resolves open question 1.

## Proposed constants (for ratification — all go to the registry + canon-delta log)

Designed extensions (canon is non-numerical). Turn-based units (engine ticks per turn):

| Constant | Proposed value | Rationale |
|----------|---------------|-----------|
| `STRESS_MIN / STRESS_MAX` | `0 / 100` | Canon Ch 27.7 range |
| `STRESS_DECAY_PER_TURN` `d` | `0.85` (half-life ≈ 4.3 turns) | Recovery under safety (14.34) without erasing chronic load |
| `STRESS_CAPACITY_BAND` `C` | seeded per actor ∈ `[0.7, 1.3]`, nominal `1.0` | Divides generation; higher `C` = more resilient (14.5) |
| `STRESS_PRESSURE_GAIN` | `g_t = 100 · highest_pressure_intensity · threat_weight / C` | 14.4 pressure→stress |
| Band cut-points | Stable `0–19` / Strained `20–39` / Stressed `40–59` / Overloaded `60–74` / Critical `75–89` / Collapse `90–100` | Six states 14.9–14.15 |
| `BREAKING_TRIGGER` | enter Critical (`stress ≥ 75`) **and** `stress > 100·C·0.75` | 14.17 stress-exceeds-capacity |
| `BREAKING_COOLDOWN_TURNS` | `5` | Anti-loop |
| Band hysteresis | must fall `≥10` below a band floor to de-escalate | Prevents oscillation |

These are **starting proposals to tune against play**, not canon values; the table itself becomes
the `foundation-canon-deltas.md` entry on ratification.

## Determinism plan (invariant — do not break)

- Stress update is a **pure function** of prior persisted state + the run seed; no wall-clock,
  no unordered iteration.
- `stress_level` and band live in `rolling_state` actor records and are included in
  `canonical_json` / stable hash; reproducible from seed (`run_identity`).
- Breaking-point selection uses the existing seeded RNG draw, not `random`.
- New determinism tests assert byte-identical stress trajectories for a fixed seed.

## Consequences

- **Easier:** Ch 27 can `replacement_authorised = True` on real turns; world gains emergent
  breaking-point events that drive pacing through the sanctioned world-event layer.
- **Harder:** larger authoritative-state surface and a bigger determinism-hashed footprint;
  a standing set of non-canon constants that must be tracked as deltas and tuned against play.
- **Revisit:** band cut-points and decay rate after playtest; overlap between collective stress
  (14.30–14.32) and `pressure_graph` (avoid double-counting the same world pressure).

## Risks

- Numeric model is non-canon → risk of drifting from intended "feel"; mitigated by isolation +
  delta log + tuning pass.
- Breaking-point loops / oscillation → cooldown + hysteresis on band transitions.
- Double-counting pressure vs. stress in utility (pressure already a dimension) → keep stress as
  the *internalised* accumulation, distinct from instantaneous pressure intensity.
- Determinism regression from new state → gated by determinism tests before any merge.
- Scope creep — social/collective stress (14.29–14.32) is large; isolated to the last phase and
  separately cuttable.

## Sequencing (phases within the milestone — each a hard gate)

1. **P1 — Individual stress state.** `backend/stress.py` (generation/capacity/accumulation/decay),
   persist in `rolling_state`, turn-update hook in the engine path, registry constants. Emit
   `stress_level` from `_utility_input_refs`. *Gate:* determinism tests green; `inputs_complete`
   true on real turns; `replacement_authorised` reaches `True` on complete fixtures via the oracle.
2. **P2 — Behavioural bands + utility integration.** Band derivation, goal-narrowing weight
   modifiers (14.24/14.27). *Gate:* unit tests + oracle equivalence on bands.
3. **P3 — Breaking points.** Archetype selection + `npc_world_moves` emission + cooldown.
   *Gate:* tests for trigger threshold, archetype determinism, no-loop cooldown.
4. **P4 — Social/collective stress.** Transfer (14.29), collective/settlement/faction
   (14.30–14.32), burnout (14.33). *Gate:* tests; pressure-double-count check.
5. **P5 — Acceptance.** Oracle equivalence on a complete synthetic corpus; emit the acceptance
   artifact. *This milestone completes here; the Ch 27 load-bearing flip is a separate ADR that
   consumes this substrate and carries the equivalence-before-flip proof.*

## Open questions for sign-off

1. ~~Capacity/personality source.~~ **Resolved (2026-06-22):** no numeric trait/capacity field
   exists; per-actor variation is seeded only. Capacity `C` and archetype bias will be new seeded
   per-actor derivations (see Existing scaffold section).
2. **Ratify the proposed constants** (decay, capacity band, band cut-points, breaking trigger,
   cooldown) in the "Proposed constants" table. Values are tunable starting points.
3. **Breaking-point reconciliation approach.** Confirm: keep `BREAKING_POINTS` as the *cause* axis,
   add a *response-archetype* axis, move the trigger from `progress>=85` to stress-exceeds-capacity,
   and preserve the existing `defect`-gating consumers. (Behaviour-path change — regression-tested.)
4. **Is P4 (social/collective stress) in scope for this milestone, or deferred to a follow-up?**
   It is the largest and least Ch-27-relevant part.

## Files affected (anticipated)

- New: `backend/stress.py`, `backend/tests/test_stress.py`, `backend/tests/test_breaking_points.py`
- Modified: `backend/foundation_snapshot.py` (`_utility_input_refs`), `backend/npc_agendas.py`
  (stress-driven trigger, response-archetype field), `backend/npc_world_moves.py` (breaking-point
  moves; consumers at :300,:410), `backend/living_cast_seeded_scenario.py` (`breaking_fired`
  consumer at :215), `backend/replayability.py` (turn-update hook), constants registry,
  `docs/foundation-canon-deltas.md` (divergence log)
- Consumes (already correct): `backend/utility_dimensions.py`, `backend/utility_ai.py`

## Tests required

- Determinism: byte-identical stress trajectory per seed (extend `test_engine_determinism.py`).
- Unit: generation/decay/accumulation/clamp; band mapping; breaking-point trigger + cooldown.
- Acceptance: `foundation_acceptance` oracle equivalence on complete fixtures; `test_d_sel_activation`
  flips from blocked → authorised on real-shaped input.

## Action Items

1. [ ] Verify the personality/capacity source (open question 1) before P1.
2. [ ] Ratify the numeric model + constants; record them in `docs/foundation-canon-deltas.md`.
3. [ ] Confirm P4 in-scope vs deferred.
4. [ ] On acceptance, append a summary row for ADR-021 to `docs/decision-log.md`.
