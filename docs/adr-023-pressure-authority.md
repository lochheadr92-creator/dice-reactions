# ADR-023: Pressure authority — `pressure_graph` canonical, `active_pressures` derived

**Status:** Proposed (decision recorded; implementation deferred to a separate task)
**Date:** 2026-06-24
**Deciders:** Ryan
**Branch target:** `emergent` (commit on `emergent` after PR #3 merges, or a dedicated docs branch — NOT folded into the Ch 14 stress PR #3)
**Amends:** ADR-019 (Replayability Engine — `pressure_graph`), ADR-016 (Early-Game Pacing — `active_pressures` validation)
**Source material:** Pressure Authority Remediation design pass (code inspection, 2026-06-24)

---

## 1. Context / problem

Pressure currently has two competing representations, violating **State is truth, narrative is output**:

- **`replayability_state.pressure_graph`** — engine-owned, deterministic, causal model. Authored by `init_pressure_graph` / `tick_pressure_graph` / `select_foreground` (`replayability.py:199,304,343`); protected from the LLM by `strip_model_pressure_mutations` (`replayability.py:765-772`). It is the SOLE pressure source for every causal/authoritative consumer: stress generation and Utility AI read `highest_pressure_intensity` / `resource_scarcity` derived from it (`foundation_snapshot.py:243,272,282,293`), and it is committed into snapshot identity `source_state_hash` (`foundation_snapshot.py:49,66`).
- **`rolling_state.active_pressures`** — an LLM-authored prose list. Requested from the model in the rolling_state schema and system prompt (`server.py:498,250`; `pressure_graph.py:414`), persisted via protected-merge (`memory.py:57`, `server.py:1680`), and used as a pacing Stage-1 validation gate (`pacing.py:201-203`). The engine never writes it (absent from `replayability.py` and `foundation_snapshot.py`). It is not causal and not player-facing (excluded from `player_api`; only `state.Pressure` is allowlisted, `player_api.py:56`; no frontend references).

Because `active_pressures` is LLM/prose-authored yet load-bearing (pacing gate, persisted, protected), it is a second, narrative-derived pressure authority that can diverge from the engine's causal `pressure_graph`. The prompt already injects `pressure_graph`-derived prose via `build_pressure_directive` (`replayability.py:274,383`), making `active_pressures` largely redundant LLM duplication.

## 2. Decision

1. **`replayability_state.pressure_graph` is the single canonical pressure authority.**
2. **`rolling_state.active_pressures` becomes a derived, engine-owned, read-only projection** of the canonical `pressure_graph` foreground.
3. **LLM-authored `active_pressures` is no longer authoritative**: any model-emitted value is stripped/overwritten during consolidation (mirroring `strip_model_pressure_mutations` / `enforce_authoritative_stress`).
4. **The `active_pressures` key is preserved** (not removed) for backward compatibility and snapshot `rolling_keys` stability.
5. **No pressure authority may originate from narrative / prose / LLM output.**

## 3. Rationale

Code confirms `pressure_graph` is the richer causal model (nodes with kind/magnitude/status/trend/scope/links; foreground scoring; threshold crossings — ADR-019), is engine-owned and deterministic, is already LLM-protected, and is already the only source for stress, Utility AI, and snapshot identity. `active_pressures` is LLM/prose-authored, non-causal, and non-player-facing, so it is disqualified as authority and safe to demote. Deriving it from `pressure_graph` removes the duplicate (LLM) write path and aligns narrative with engine truth.

## 4. Consequences

- **Easier:** one unambiguous pressure truth beneath stress (P1/P2), Utility AI `pressure_relief`, pacing, and future breaking-point triggers; narrative pressure aligns with causal pressure.
- **Changed behaviour (intended):** the model no longer authors `active_pressures` (engine derives it); pacing Stage-1 validates engine-derived pressure rather than model output; the prompt contract drops the LLM `active_pressures` obligation. These require test updates (see §7).
- **Compatibility:** the `active_pressures` key remains present and populated, so persistence, protected-merge, and any internal readers continue to function.

## 5. Migration plan (smallest safe diff; implementation is a separate task)

- **Step 1 — Authority of record:** this ADR + decision-log entry (documentation only).
- **Step 2 — Engine derivation:** add a pure `project_active_pressures(pressure_graph) -> list[str]` (reuse existing pg->prose machinery, `build_pressure_directive`); consolidation sets `rolling_state.active_pressures` from it and strips/overwrites any model-emitted value.
- **Step 3 — Repoint pacing:** `pacing.validate_opening_structure` validates the engine-derived pressure (projection or `pressure_graph` nodes), not LLM-authored `active_pressures`. `init_pressure_graph` runs at `created_turn=1`, so the engine source is non-empty at Turn 1.
- **Step 4 — Prompt contract:** drop the LLM obligation to author `active_pressures` (`server.py:250,498`; `pressure_graph.py:414`); keep the instruction to reference pressure sensorily; rely on `build_pressure_directive`.
- **Sequencing:** Steps 2-3 are the behavioural core; Step 4 is prompt-only and follows once 2-3 are green.

## 6. Determinism / hash implications

- `source_state_hash` hashes `pressure_graph` and `sorted(rolling.keys())` but NOT `active_pressures` values (`foundation_snapshot.py:49-50`). Preserving the `active_pressures` key keeps `rolling_keys` unchanged -> snapshot identity unchanged. Removing the key would churn `rolling_keys` across all historical states — hence the key is preserved.
- The projection must be a pure, deterministic function of `pressure_graph` (no wall-clock/RNG; stable ordering) so consolidation stays deterministic.
- Causal paths (stress, Utility AI) already read only `pressure_graph`, so their values/hashes are unaffected.
- Ordering risk: the projection must run after `pressure_graph` tick/foreground selection so it reflects the post-tick foreground.

## 7. Test plan (for the implementation task; no tests written by this ADR)

- Unit: `project_active_pressures` purity/determinism; empty/degenerate graph -> defined output; stable ordering.
- Enforcement: model-emitted `active_pressures` is stripped/overwritten by the engine projection.
- Pacing: update `test_early_game_pacing.py` (incl. the `"missing active_pressures"` case) so the gate passes from engine state and fails only when the engine pressure source is genuinely empty.
- Determinism/identity: pressure fixtures retain identical `source_state_hash`; `rolling_keys` unchanged (key preserved).
- Regression: `test_replayability_integration`, `test_gateway_e2e`, `test_foundation_integration` byte-equivalence remain green.

## 8. Files likely affected (implementation task)

`backend/replayability.py`, `backend/pressure_graph.py`, `backend/pacing.py`, `backend/server.py`, `backend/memory.py` (protected-key semantics; key retained), `backend/opening_state.py`; tests `test_early_game_pacing.py` (+ regression touch in `test_replayability_integration.py`, `test_gateway_e2e.py`). No change expected in `foundation_snapshot.py`, `stress.py`, `utility_ai.py`, `hud.py`, or frontend.

## 9. Status of T2

**T2 (live turn-path verification) remains deferred** until after pressure authority remediation is implemented and verified. Verifying the live turn path while pressure has dual authority would validate a system resting on ambiguous truth. Sequence: this ADR -> implement remediation (separate task) -> then T2. Runtime status stays `TURN_INTEGRATION_UNVERIFIED` for the affected systems; this ADR does not promote it.

## 10. Non-goals

- No P3 (breaking-point archetypes / world-move emission).
- No T2 / live turn-path verification.
- No relationship provenance remediation (the second golden-path blocker — separate ADR/task).
- No full event sourcing.
- No reconciliation of unrelated docs.
- No production code or test changes in this ADR (documentation only).

## Action items

1. [ ] On acceptance, implement Steps 2-4 as a separate task (production code + tests).
2. [ ] Add a failure-mode entry (LLM-authored pressure authority) and update feature/canon docs as part of that implementation task — not now.
3. [ ] Keep T2 deferred until remediation lands.
