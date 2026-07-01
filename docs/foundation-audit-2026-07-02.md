# Foundation Completion Audit

**Date:** 2026-07-02
**Branch / HEAD:** `emergent` @ `f168dd2` (prompt-only `prior_state` projection landed)
**Auditor:** Nova
**Scope:** Read-only audit. No production code modified. One documentation defect found (described, not fixed).

**Evidence labels:** VERIFIED = confirmed from code/tests run this pass. LIKELY = supported by evidence, not directly re-run here. UNKNOWN = not determinable in this environment.

**Sandbox caveat (VERIFIED):** this environment has no MongoDB and no OpenRouter key. Pure-deterministic engine tests run here; every FastAPI/Motor-backed test hangs on a 30 s server-selection timeout and every `@pytest.mark.live` test is deselected. ~480 pure tests were run green this pass (0 failures). The remaining tests to reach the documented 749 non-live count are DB-integration tests that pass under CI's Mongo service (LIKELY, not re-run here).

---

## Headline

The **deterministic engine substrate is solid and genuinely complete**: pressure authority, replayability, the anti-hallucination gateway, prompt projection, and the full canonical foundation stack (Actor / Gravity / Utility / Retrieval) are implemented, deterministic, and passing their offline suites. The gap is uniform and predictable: **almost nothing is live-verified against a real LLM turn, and the canonical foundation runs in shadow, not as authority.** The foundation is *architecturally* ready for the next phase; it is not yet *behaviourally* proven.

Two structural facts dominate the audit:

1. **The foundation is built but inert.** `actor_resolution.py` (Ch 25), `gravity_governance.py` (Ch 26), `utility_ai.py` (Ch 27), `memory_retrieval.py` (Ch 28) are computed every turn inside `replayability.prepare_action_turn` → `foundation_integration.evaluate_foundation_turn`, wrapped in a swallow-all `try/except` with `developer_mode=False`. They are deterministic, tested, and staged to `foundation_prepared_v1` as diagnostics — **read by no live consumer, projected to no prompt or player surface.** (VERIFIED: `foundation_integration.py`, `replayability.py:621-633`, `engine_projection.py`.)

2. **The one named golden-path blocker is relationship provenance** — vectors mutate from player intent + generated prose, not from a guarded event source. Everything else labelled "unverified" is live-turn verification debt.

---

## Subsystem verdicts

### 1. Event Sourcing — FAIL
Formal event sourcing (immutable log + canonical aggregate rebuild) **does not exist**. Turns are `insert_one` append-only during normal play (H4), but `reset`/`delete` destroy history and `rolling_state` is overwritten in place. `grep` for any rebuild/event-store/aggregate path returns nothing (VERIFIED). `transition_receipts` provide idempotency and causal pointers only — explicitly *not* reconstruction. This is **deferred by design**, not a regression, and is not a golden-path blocker — but as a canonical subsystem it is absent.

### 2. State Is Truth compliance — PARTIAL
H1/H2 are enforced where it counts: gateway STRIP, protected rolling-state keys, engine-owned `relationship_vectors`, engine-owned `pressure_graph`/`active_pressures`, engine-owned `actor_stress`, object canonicalization. All tested green (VERIFIED: gateway + object-permanence + injection-ignored tests). The ceiling: **the LLM still authors the initial `rolling_state` each turn** before deterministic merge, so "state is truth" holds by correction, not by construction. Doctrine itself rates H1/H2 "Partial." Accurate.

### 3. Anti-Hallucination Gateway — PASS
PREVENT (`build_immutable_truth_block`), STRIP (`strip_illegal_state_changes`), DETECT (`detect_prose_contradictions` + retry), death/destruction registries, and the sole `invoke_llm` chokepoint are all implemented and load-bearing on the live turn path. `test_anti_hallucination_gateway.py` + `test_gateway_e2e.py` pass (VERIFIED this pass). Caveats, not blockers: full Ch 31 conformance is not claimed, and the live probe (`test_gateway_live_probe.py`) is unrun (LIKELY-fine, UNKNOWN under real provider).

### 4. Memory Retrieval — PARTIAL
`memory_retrieval.py` (Ch 28 relevance scoring + seeded weighted sampling) is implemented, deterministic, and tested (25 green, VERIFIED). But it runs **shadow-only** (`shadow_mode=True` hardcoded in `evaluate_foundation_turn`); its `selected_memory_ids` never enter the prompt. Live retrieval is still naive Mongo replay (`DEFAULT_MEMORY_DEPTH=3`) + `<prior_state>`. Canon delta `D_MEMORY_RETRIEVAL_SHADOW` is `NOT_MACHINE_CHECKABLE / SEPARATE_SHADOW_ACCEPTANCE_REQUIRED`. Component ready; not integrated.

### 5. Gravity Governance — PARTIAL
`gravity_governance.py` (Ch 26 retention scoring + disposition) is implemented, deterministic, tested green (VERIFIED), and already feeds actor-resolution retention in shadow. By its own contract it **"does not delete authoritative truth or select prompt top-N retrieval subsets"** — i.e. it computes retention but governs nothing live. Actual retention is still the `enforce_context_budget` heuristic. **Doc divergence:** `current-state.md` and `feature-status.md` still call gravity "Planned — partial ad-hoc only / no gravity module" (see Defect D-1).

### 6. Actor Resolution Scaling — PARTIAL
Two implementations coexist (VERIFIED). Live/load-bearing: `npc_world_moves.resolve_actor_tier` heuristic (tier + cadence eligibility). Canonical/shadow: `actor_resolution.py` (Ch 25 tiers, promotion, demotion, caps, cadence), deterministic and tested green. Canonical compliance is **input-blocked**: `D_TIER_ASSIGNMENT` is `NOT_MACHINE_CHECKABLE` (no Ch 20 Context Gravity `G_peak`) and `D_GRACE` is `PLACEHOLDER_BLOCKED` (no simulation clock — `turn×60` proxy only). The canonical module exists but cannot yet be authority without those inputs.

### 7. Relationship Calculus — PARTIAL
`relationships.py` engine-owns trust/loyalty/fear/resentment vectors (NPC→player), with event detection, neglect decay, and a prompt block; LLM-injected vectors are ignored (VERIFIED green). **This subsystem carries the single named golden-path blocker: relationship provenance** — vectors are driven by player-intent + generated prose rather than a guarded structured event source, so their causal authority is unsound. Also missing: NPC↔NPC edges; regex-only event detection; legacy `relationship_threads` duplication.

### 8. Utility AI — PARTIAL
`utility_ai.py` + `utility_dimensions.py` implement Ch 27 (dimension formulas, dynamic weights, seeded whim noise, deterministic tie handling) plus P2 stress-band goal-narrowing. Extensively tested green (utility oracle 35, dimensions, shadow bridge 12, stress behaviour 66 — VERIFIED). Two shadow paths exist: the foundation shadow (`candidates_from_agendas`) and the ADR-024 live bridge over `npc_world_moves` candidates. The bridge is **feature-gated (`ENABLE_UTILITY_AI_LIVE_SELECTION`, default OFF)** with deterministic OFF/ON/fail-closed handoff proofs. Canonical replacement of `score_move` is `D_SEL PLACEHOLDER_BLOCKED`; status is `TURN_INTEGRATION_UNVERIFIED` (no real-LLM turn-path acceptance). Best-developed inert system in the engine.

### 9. Prompt Context Projection — PASS
`engine_projection.py` allowlists give foundation internals **zero** player/prompt projection; the prompt seam (`build_immutable_truth_block` + `build_relationship_block` + `build_pressure_directive` + `<prior_state>`) is assembled deterministically. Leakage tests, `test_prompt_fingerprint.py` (now a real seam guard, not the old stale git-range tripwire), and `test_leakage.py` pass (VERIFIED this pass). Load-bearing and correct. Only the live-endurance edge (below) is unproven.

### 10. Context Budget Enforcement — PARTIAL
`enforce_context_budget` + the recent prompt-only `<prior_state>` registry caps (object_locations 48 / inventory_objects 36 / known_rooms 12 / npc_memory 16) are implemented correctly: caps apply to the **prompt copy only**, persisted state is untouched, causal-spine keys are never capped, determinism holds. `test_context_budget.py` passes (VERIFIED). It is PARTIAL for exactly one reason, stated by its own docs: **live 20-turn endurance is unproven** (`test_live_20_turn_harness.py` is live-marked, never run) and the token estimate is a heuristic.

### 11. Pressure Authority — PASS
ADR-023 is complete and clean: `replayability_state.pressure_graph` is the single canonical authority; `rolling_state.active_pressures` is a derived engine-owned projection; model-authored pressure is stripped. It is the sole input to stress, Utility AI `pressure_relief`, and snapshot identity. `test_pressure_graph.py` + `test_pressure_authority.py` pass (VERIFIED). This is the model of what "done" looks like here: single source of truth, load-bearing, tested.

### 12. Replayability — PASS
`replayability.py` + `run_identity.py` + `opening_state.py` + `pressure_graph.py` + `consequence_echoes.py` deliver deterministic per-run variation, session `replayability_state`, and structured-source-only echoes (never parses player text). Pure suites + `foundation_acceptance/` pass green (VERIFIED). Caveats: echoes require confirmed structured sources (theft/violence/promise echoes wait on guard outputs); integration tests are Mongo-gated (CI-green, LIKELY). Solid v1.

### 13. Burn-in — PARTIAL
The harness exists and expanded recently (`test_live_20_turn_harness.py`, `qa_live_20turn_hostile/full_stack/p2_stack.py`, plus the new golden-path validation harness `ae162be`). **None has ever been executed** — all are `@pytest.mark.live` and require a running stack (VERIFIED: live marker + no run record). Long-run compression, provider fallback under load, and 20-turn endurance are all unproven. Structurally ready, behaviourally unverified.

### 14. Existing Developer Tooling — PASS
7-tap dev unlock, admin AI settings (Mongo-backed, key-gated), player-safe + raw admin export, reset, model/provider selection, session ownership enforcement. `test_provider_selection.py` green here (VERIFIED); the security/admin/export suite is CI-green (LIKELY — Mongo-gated, not re-run this pass). Minor debt: client Settings can't call admin API without a proxy; `developer_mode` server toggle is coarse. Genuinely present and gated.

### 15. Existing Diagnostics — PARTIAL
Rich diagnostics exist: per-turn `debug` payloads, foundation projection diagnostics, ADR-024 live-selection evidence (enabled/applied/source/candidate/receipt), pacing telemetry, projected-registry-cap metadata. All correctly fenced out of player/prompt surfaces (leakage tests green, VERIFIED). PARTIAL because the **admin diagnostics endpoint and dev-panel UI are not integration-exercised** (Mongo/live-gated), and the diagnostics are emit-only — there is no inspector that makes the shadow foundation legible. The data is there; the lens is not.

---

## FOUNDATION SCORE

Method: PASS = 1.0, PARTIAL = 0.5, FAIL = 0.0, unweighted mean of 15 subsystems. Measures canonical completeness + verification depth — **not** code quality (which is high).

```
Event Sourcing............FAIL     0.0
State Is Truth............PARTIAL  0.5
Anti-Hallucination GW.....PASS     1.0
Memory Retrieval..........PARTIAL  0.5
Gravity Governance........PARTIAL  0.5
Actor Resolution..........PARTIAL  0.5
Relationship Calculus.....PARTIAL  0.5
Utility AI................PARTIAL  0.5
Prompt Projection.........PASS     1.0
Context Budget............PARTIAL  0.5
Pressure Authority........PASS     1.0
Replayability.............PASS     1.0
Burn-in...................PARTIAL  0.5
Developer Tooling.........PASS     1.0
Diagnostics...............PARTIAL  0.5

Overall Foundation: 63%  (9.5 / 15)
```

Sensitivity: treating the three "live-endurance-pending" PASSes (Gateway, Projection) and the shadow PARTIALs as a band gives a defensible **58–68%**. The number is deliberately not higher: five canonical systems are built but inert, and virtually nothing is live-verified.

**Interpretation:** the *deterministic foundation* is ~90% there (every core module exists, is canonical, and passes offline). The *integrated, behaviourally-verified foundation* is ~50% there. 63% reflects the honest midpoint. **The foundation is complete enough to build the next phase ON, but is not yet self-proven.**

---

## Defects found

### D-1 (Documentation, not code) — foundation status is contradictory across canonical docs
`current-state.md` ("Planned or not present") and `feature-status.md` still classify Gravity as "no gravity module / planned", Actor Resolution as "local substitute only", and Utility/Retrieval as candidate-only — while `actor_resolution.py`, `gravity_governance.py`, `utility_ai.py`, `memory_retrieval.py` are **merged on HEAD and executed every turn in shadow** (VERIFIED). Simultaneously `foundation-systems-v01.md` and `foundation-canon-deltas.md` still head with "Merged: No | Deployed: No | Branch: reimplementation/foundation-systems-v01".

**Impact:** violates the repo's single-source-of-truth principle. An agent trusting `current-state.md` would conclude these systems are absent and could **re-implement work that already exists**, or mis-scope the next phase. This is the highest-value cleanup, and it is free.

**Smallest safe fix (documentation only — not performed):** update the two status tables to "present, shadow-only, turn-integration-unverified", and update the two v01 headers to "Merged: yes (shadow) @ b4e5fcc". No code change. I did not edit these because the task scoped me to code-defect fixes only; flagging per instructions.

No critical **code** architectural defect was found. The swallow-all `try/except` around `evaluate_foundation_turn` is correct for a shadow subsystem (fail-open, non-load-bearing) but **must become fail-loud before any live promotion** — noted as a risk for the next phase, not a current defect.

---

## NEXT PHASE — ranked by architectural value

Ranking optimises for *leverage* (unblocks other work / cashes in existing investment), not gameplay novelty. Effort S/M/L is relative.

| Rank | Phase | Effort | Dependencies | Risk | Gameplay value | Architectural value |
|------|-------|--------|--------------|------|----------------|---------------------|
| **1** | **Relationship Provenance Remediation** | **S–M** | Guard/echo event outputs (exist) | Low–Med (touches a load-bearing engine-owned key) | Med (relationships stop drifting; NPCs feel causally fair) | **Highest — clears the one named golden-path blocker; unblocks merge coherence** |
| **2** | **Foundation Live-Integration** (promote Utility AI → then Actor/Gravity/Retrieval from shadow to authority, behind flags, with acceptance) | **M** | #1; simulation clock + Ch 20 Context Gravity for full Actor compliance; fail-loud conversion of the foundation try/except | Med (behaviour drift vs heuristic — mitigated: shadow comparison already records divergence) | High (canon AI actually drives NPCs) | **Very high — cashes in ~2,000 lines of built-but-inert canonical code; turns 5 PARTIALs toward PASS** |
| **3** | **Ch 33 NPC Lifecycle & Generational Succession** | **L** | #2 (needs live Actor Resolution); a durable history/event substrate; simulation clock | High (identity churn, save-compat, balance) | **Highest — living multi-generational world** | High, but gated — do not start before #2 |
| **4** | **Resource Flow Simulation** | **M** | Pressure graph (done); a resource ledger; feeds Utility `resource_gain_loss` + Gravity `resource_scarcity` | Med | High (scarcity-driven decisions, economic pressure) | Med–High — strengthens Utility/Gravity inputs already wired |
| **5** | **Discovery Architecture** | **M** | Secret Reveal v1 (done); clue/knowledge state | Low–Med | Med–High (investigation, earned reveals) | Med — extends an existing seam rather than opening a new axis |
| **6** | **Engine Inspector Tooling** | **S–M** | Diagnostics already emitted (done) | Low | Low (dev-facing) | Med — **strong enabler**: makes shadow foundation legible, accelerates #2 acceptance and burn-in triage. Best done *alongside* #2, not as a standalone phase |
| — | **Long-term Burn-in Expansion** | M | Live stack (Mongo + provider) | Low | None (verification) | **Not ranked as a phase.** Per the audit's own rule against "recommend more testing", burn-in is the *acceptance gate for #2*, not an independent phase. Fold it in there. |

### Recommended action
**Run Phase 1 (Relationship Provenance) immediately, then Phase 2 (Foundation Live-Integration) starting with the already-gated Utility AI turn-path acceptance.** Rationale: #1 removes the single blocker the codebase itself names, and #2 converts the largest body of finished-but-inert canonical code into live behaviour — moving the audit's dominant failure mode ("built but unverified/inert") more than any other work. Pair #2 with Engine Inspector (#6) and the existing burn-in harness as its acceptance gate. Defer Ch 33 until Actor Resolution is live, a simulation clock exists, and a durable history substrate is in place — starting it now would build a generational world on an inert actor model.

---

## STATUS / RISKS / NEXT STEP

**STATUS**
- VERIFIED: ~480 pure deterministic tests pass this pass, 0 failures. Pressure authority, replayability, gateway, prompt projection, and the canonical foundation stack are implemented, deterministic, and offline-green. The historically-noted `test_prompt_fingerprint` failure is resolved (2 passed).
- VERIFIED: the canonical foundation (Ch 25–28) runs every turn in shadow, fail-open, non-leaking, consumed by nothing live.
- LIKELY: the full 749 non-live bundle is green under CI's Mongo service (DB-integration tests hang here for lack of Mongo — environmental, not defect).
- UNKNOWN: all live/real-LLM behaviour (burn-in, gateway live probe, Utility AI turn-path, 20-turn context-budget endurance) — no live stack available this pass.

**RISKS**
- Five canonical systems are inert; "done" offline ≠ correct live. Promotion will surface behaviour drift (shadow comparison mitigates).
- Relationship provenance is causally unsound until remediated.
- The foundation try/except is fail-open by design; it must become fail-loud before live promotion or a real determinism bug could hide.
- D-1 doc divergence risks duplicated/misscoped work until reconciled.

**NEXT STEP**
Reconcile D-1 (free, prevents wasted work), then execute Phase 1 → Phase 2 as above. Do not begin Ch 33 until its dependencies exist.

**Bottom line:** the foundation is genuinely *built* and deterministically *sound*, but not yet *proven live* or *load-bearing*. It is ready to be the base of the next phase — provided the next phase is the one that makes it load-bearing, not one that stacks more inert systems on top.
