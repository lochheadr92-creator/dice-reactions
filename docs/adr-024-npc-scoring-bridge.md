# ADR-024: Live NPC action selection bridge — Ch 27 utility as scoring core via a shadow-equivalence gate (Option D)

**Status:** Accepted — Phase 1 retained; NW-UTILITY-01 Phase 2 implemented behind a default-off feature flag; `TURN_INTEGRATION_UNVERIFIED`
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

`replayability.prepare_action_turn` (pre-provider) first asks `npc_world_moves` for its eligible candidate set and heuristic winner. `living_cast_shadow.compare_move_scoring` then adapts that exact set and calls band-aware `utility_ai.select_action`. The default-off feature flag controls which winner is handed to the existing `npc_world_moves.commit_npc_move` effects/receipt/directive path. Shadow comparison records both winners in either mode.

## 3. Decision

1. **`npc_world_moves` remains the live eligibility, target-resolution, effect, receipt, and commit substrate.** No replacement.
2. **Ch 27 `utility_ai.select_action` is the canonical alternative selector for the eligible set**, including P2 stress-band weights, seeded noise, and deterministic tie handling.
3. **`ENABLE_UTILITY_AI_LIVE_SELECTION` controls live handoff and defaults to false.** OFF preserves the heuristic winner. ON hands off the authorised Utility AI winner; missing/invalid authoritative inputs fail closed to the heuristic.
4. **Phase 1 comparison remains active in both modes.** The feature flag changes selection only; it does not replace eligibility, effects, receipts, directives, or pressure authority.
5. **Status remains `TURN_INTEGRATION_UNVERIFIED`** until a real turn-path acceptance run is completed.

## 4. Rejected options

- **Replace `npc_world_moves` with `utility_ai` (Option A).** `utility_ai` has no eligibility/targets/effects/commit/receipts/directive; replacement reimplements the entire live substrate around a currently-unverified system. Breaks working runtime; premature. **Rejected.**
- **Keep permanent duplicate scoring (Option B as end-state).** Leaves canon Ch 27 inert, perpetuates divergence and the dead `utility_selection` write, and provides no single scoring authority. **Rejected as an end-state** (acceptable only as the transient Phase-1 shadow).
- **Direct flip without shadow evidence.** Replacing `score_move` with Ch 27 scoring immediately changes live NPC behaviour with no equivalence data; risks emergent-behaviour and determinism regressions and violates "evidence before a load-bearing flip." **Rejected.**

## 5. Migration phases

- **Phase 0 - this ADR (documentation only).**
- **Phase 1 — complete.** Same-candidate-set comparison is always recorded in internal diagnostics.
- **Phase 2 — implemented, default OFF.** The comparison's `utility_ai.select_action` winner can be handed to the existing commit path when authorised. `npc_world_moves` still owns all hard eligibility gates and cadence; its heuristic remains the OFF-mode winner and fail-closed fallback. This intentionally avoids replacing `score_move`, preserving continuous comparison and rollback.

## 6. Determinism and state / hash implications

- Phase 1 must be a pure, deterministic function of engine state; the committed move and `rolling_state` must be byte-identical to today (shadow is observation-only). Diagnostics must not enter `rolling_state`, snapshot identity, player, or prompt surfaces (engine-projection allowlist).
- Canon scoring is deterministic + seeded (whim noise via `engine_determinism`; canonical hashes). Phase 2 reuses `utility_ai.select_action` noise/tie handling and maps its winner back to the existing eligible candidate without re-sorting or adding randomness.
- `source_state_hash` already commits `pressure_graph` and `actor_stress` (the canon scorer's inputs); Phase 1 adds no new authoritative state (diagnostics only), so snapshot identity and hashes are unchanged.
- Dependency: the canon scorer's `pressure_relief`/weights consume `pressure_graph` (ADR-023 canonical) and P2 stress bands (ADR-022); pressure authority remediation (ADR-023) cleanly precedes and strengthens this work.

## 7. Verification

- **Phase 1:** shadow-compare is pure/deterministic; committed move + `rolling_state` byte-identical to baseline (regression: existing `npc_world_moves` / `replayability` / foundation suites stay green); divergence diagnostics excluded from player/prompt (`test_leakage` / engine-projection); deterministic recorded comparison.
- **Phase 2:** focused tests prove flag OFF preserves the heuristic winner, flag ON hands off the `utility_ai.select_action` winner, unauthorised inputs fail closed, shadow diagnostics remain present, and Living Cast eligibility/integration regressions remain green. Real provider/turn-path acceptance is still outstanding.

## 8. Risks

- Behaviour drift at Phase 2 (canon vs heuristic pick differ) - mitigated by Phase-1 divergence data + acceptance gate.
- Determinism regression from integrating seeded noise into the sort - covered by determinism tests.
- Candidate-set mismatch (canon scorer expecting inputs the `npc_world_moves` candidates lack) - surfaced by Phase 1 before any flip.
- Hidden coupling: `score_move`'s gates (goal-align hard gate, tier, cadence) encode behaviour the canon scorer does not - must be preserved as a gate layer, not lost in the flip.
- Doc drift: `current-state.md` / ADR-020 already misstate `npc_world_moves` as absent on `emergent` (see Non-goals; reconciliation deferred).

## 9. Non-goals

- No replacement of `npc_world_moves`.
- No default deployment activation; the feature flag is an explicit opt-in.
- No `TURN_INTEGRATION_VERIFIED` claim.
- No P3, no relationship provenance remediation, no full event sourcing.
- No unrelated ADR-020 reconciliation.
- No production code or test changes (documentation only).

## 10. Status labels

- **Live NPC action selection:** heuristic winner by default; authorised Utility AI winner when the flag is enabled; commit remains `LIVE_LOAD_BEARING` through `npc_world_moves`.
- **Ch 27 `utility_ai`:** `FEATURE_GATED_LIVE_SELECTION` / default OFF / `TURN_INTEGRATION_UNVERIFIED`; shadow evaluation always remains active.
- **This ADR:** Accepted — Phase 1 comparison and NW-UTILITY-01 Phase 2 handoff implemented.

## Action items

1. [x] Implement Phase 1 same-candidate shadow comparison.
2. [x] Implement default-off Phase 2 handoff with OFF/ON/fail-closed tests.
3. [ ] Run real turn-path acceptance before any `TURN_INTEGRATION_VERIFIED` claim or default activation.
4. [ ] Reconcile unrelated ADR-020 historical wording separately.
