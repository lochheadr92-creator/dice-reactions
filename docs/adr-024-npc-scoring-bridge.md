# ADR-024: Live NPC action selection bridge — Ch 27 utility as scoring core via a shadow-equivalence gate (Option D)

**Status:** Proposed (decision recorded; implementation deferred; documentation-only)
**Date:** 2026-06-24
**Deciders:** Ryan
**Branch:** `docs/adr-024-npc-scoring-bridge` (off the ADR-023 branch `a0e9054`, which is off `emergent` `c82c0af`)
**Amends / relates:** ADR-020 (Living Cast / `npc_world_moves`), ADR-022 (P2 stress bands feed the canon scorer), ADR-023 (pressure authority — `pressure_graph` feeds the canon dimensions)
**Source material:** T2 static turn-path trace + live-NPC-selection design pass (code inspection, 2026-06-24)

---

## 1. Context / problem

The T2 static trace established (code evidence, `emergent` `c82c0af`) that there are two parallel, engine-state-driven NPC decision systems:

- **Live, load-bearing:** `npc_world_moves` selects and **commits** NPC moves using a LOCAL heuristic scorer `score_move` (tier priority + flat bonuses - repetition; `npc_world_moves.py:377`). ADR-020 explicitly classifies this as a local substitute, not PRD Ch 25/27.
- **Shadow, inert:** Ch 27 `utility_ai.select_action` runs AFTER the move is committed; its result is staged to `replayability_state.foundation_prepared_v1.utility_selection` and **read by no one** (`server.py` has zero references; `utility_selection` has zero readers).

This is a canon-fidelity + duplication problem, not a "State is truth" violation (both scorers read engine state; neither is prose/LLM-derived). The canon Ch 27 model — extended by P2 stress bands (ADR-022) and fed by the canonical `pressure_graph` (ADR-023) — is currently inert for NPC decisions.

## 2. Current architecture

`replayability.prepare_action_turn` (pre-provider), per turn: `world_moves.select_npc_move` (`replayability.py:347`) -> `world_moves.commit_npc_move` (`:353`, applies real effects: relationship vectors, faction ticks, pressure graph, receipts) -> `world_moves.build_move_directive` (`:385`, `[NPC_WORLD_MOVE_V1]` prompt directive) -> `stress.update_actor_stress` (`:456`) -> `foundation_integration.evaluate_foundation_turn` (`:465`, Ch 27 utility, shadow) -> `apply_prepared_to_replayability_state` stages `foundation_prepared_v1` (`:474`). `npc_world_moves` owns eligibility (`resolve_actor_tier`, cadence), targets (`resolve_move_target`), effects (`apply_move_effects`), receipts, directive, commit; `utility_ai` owns canon dimensional scoring only, staged and unconsumed.

## 3. Decision

1. **`npc_world_moves` remains the live eligibility, target-resolution, effect, receipt, and commit substrate.** No replacement.
2. **Ch 27 `utility_ai` shall become the canonical NPC scoring core only after shadow-equivalence evidence** (Option D -> Option C).
3. **Until then, `utility_ai.select_action` remains `SHADOW_ONLY` / `TURN_INTEGRATION_UNVERIFIED`**; live scoring continues via `npc_world_moves.score_move`.
4. **Migration = Option D:** a shadow-equivalence-gated bridge. Phase 1 adds same-candidate-set shadow comparison with ZERO behaviour change. Phase 2 MAY flip scoring to Ch 27 only after evidence + tests + acceptance.
5. **No `TURN_INTEGRATION_VERIFIED` claim until live scoring actually uses Ch 27 utility.**

## 4. Rejected options

- **Replace `npc_world_moves` with `utility_ai` (Option A).** `utility_ai` has no eligibility/targets/effects/commit/receipts/directive; replacement reimplements the entire live substrate around a currently-unverified system. Breaks working runtime; premature. **Rejected.**
- **Keep permanent duplicate scoring (Option B as end-state).** Leaves canon Ch 27 inert, perpetuates divergence and the dead `utility_selection` write, and provides no single scoring authority. **Rejected as an end-state** (acceptable only as the transient Phase-1 shadow).
- **Direct flip without shadow evidence.** Replacing `score_move` with Ch 27 scoring immediately changes live NPC behaviour with no equivalence data; risks emergent-behaviour and determinism regressions and violates "evidence before a load-bearing flip." **Rejected.**

## 5. Migration phases

- **Phase 0 - this ADR (documentation only).**
- **Phase 1 - shadow compare, zero behaviour change.** Score the candidate set that `npc_world_moves` actually enumerates with the canon utility model (reuse `build_canonical_dimension_bundle` + `compute_dimension_weights` + P2 bands + `compute_utility_score`); record per-turn agreement vs the heuristic pick in internal diagnostics only (engine-projection internal; never rolling_state / player / prompt). Live selection still uses `score_move`. Produces equivalence evidence and makes the shadow meaningful (same candidate set, unlike today's divergent sets).
- **Phase 2 - gated flip (only after evidence + acceptance + ratifying ADR).** Replace `score_move`'s heuristic body with the canon utility score, preserving the eligibility gates (tier / cadence / goal-align / target), the commit/effects path, determinism (seeded noise + tie-break folded into the deterministic sort), and the repetition/recency penalty (retained as an eligibility/penalty layer or folded into a dimension - explicit Phase-2 decision). Only then consider a `TURN_INTEGRATION_VERIFIED` claim, separately.

## 6. Determinism and state / hash implications

- Phase 1 must be a pure, deterministic function of engine state; the committed move and `rolling_state` must be byte-identical to today (shadow is observation-only). Diagnostics must not enter `rolling_state`, snapshot identity, player, or prompt surfaces (engine-projection allowlist).
- Canon scoring is deterministic + seeded (whim noise via `engine_determinism`; canonical hashes). Phase 2 must integrate noise/tie-break into `npc_world_moves`' deterministic sort without introducing nondeterminism.
- `source_state_hash` already commits `pressure_graph` and `actor_stress` (the canon scorer's inputs); Phase 1 adds no new authoritative state (diagnostics only), so snapshot identity and hashes are unchanged.
- Dependency: the canon scorer's `pressure_relief`/weights consume `pressure_graph` (ADR-023 canonical) and P2 stress bands (ADR-022); pressure authority remediation (ADR-023) cleanly precedes and strengthens this work.

## 7. Test plan (for the implementation tasks; no tests written by this ADR)

- **Phase 1:** shadow-compare is pure/deterministic; committed move + `rolling_state` byte-identical to baseline (regression: existing `npc_world_moves` / `replayability` / foundation suites stay green); divergence diagnostics excluded from player/prompt (`test_leakage` / engine-projection); deterministic recorded comparison.
- **Phase 2:** acceptance/equivalence - extend the foundation oracle to NPC-move selection; canon-scored selection matches the agreed expectation on fixtures; tier/cadence/goal-align gates preserved; effect application unchanged; determinism (noise + tie-break) stable; repetition penalty preserved or intentionally changed-with-tests; update selection tests.

## 8. Risks

- Behaviour drift at Phase 2 (canon vs heuristic pick differ) - mitigated by Phase-1 divergence data + acceptance gate.
- Determinism regression from integrating seeded noise into the sort - covered by determinism tests.
- Candidate-set mismatch (canon scorer expecting inputs the `npc_world_moves` candidates lack) - surfaced by Phase 1 before any flip.
- Hidden coupling: `score_move`'s gates (goal-align hard gate, tier, cadence) encode behaviour the canon scorer does not - must be preserved as a gate layer, not lost in the flip.
- Doc drift: `current-state.md` / ADR-020 already misstate `npc_world_moves` as absent on `emergent` (see Non-goals; reconciliation deferred).

## 9. Non-goals

- No replacement of `npc_world_moves`.
- No Phase-2 flip authorized by this ADR (decision + Phase-1 planning only).
- No `TURN_INTEGRATION_VERIFIED` claim.
- No P3, no relationship provenance remediation, no full event sourcing.
- No `current-state.md` / ADR-020 reconciliation yet (separate task; flagged).
- No production code or test changes (documentation only).

## 10. Status labels

- **Live NPC action selection:** `LIVE_LOAD_BEARING` via `npc_world_moves` local/non-canon scorer (ADR-020 substitute).
- **Ch 27 `utility_ai`:** `SHADOW_ONLY` / `TURN_INTEGRATION_UNVERIFIED` (unchanged; not promoted).
- **This ADR:** Proposed - Option D approved as direction; Phase 1 may be implemented next (separate task); Phase 2 gated on evidence.

## Action items

1. [ ] Implement Phase 1 (shadow compare) as a separate task (production code + tests).
2. [ ] Gather divergence evidence; define an acceptance threshold.
3. [ ] Separate ratifying ADR + acceptance before any Phase-2 flip; only then consider `TURN_INTEGRATION_VERIFIED`.
4. [ ] Reconcile `current-state.md` / ADR-020 (`npc_world_moves` present + live on `emergent`) - separate doc task.
