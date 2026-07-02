# Source of Truth v1.2 — Chapter Implementation Audit

**Branch:** `emergent` · **Date:** 2026-07-02
**Basis:** `Source_of_Truth_v1.2.md` (33 canonical chapters)
**Purpose:** Classify every SoT chapter by *actual* implementation maturity, with
code / test / doc citations, so completion is reported honestly rather than as a
single collapsed figure.

> `Source_of_Truth_v1.2.md` is the **target specification**. Every chapter's
> `## Status` reads "Canonical" — that denotes *doctrine* maturity (the spec is
> locked), **not** implementation. The SoT records nothing about what is built,
> so each classification below is derived from repository evidence: the backend
> module inventory, the test inventory, and the reconciled status docs
> (`current-state.md`, `system-doctrine.md`, `foundation-promotion.md`,
> `next-work.md`).

---

## Evidence tags

| Tag | Meaning |
|-----|---------|
| **Run✅** | Test suite executed and passing in the audit session (offline, no live stack) |
| **Code** | Confirmed by reading runtime source in this repo |
| **Docs-claimed** | Stated in a reconciled status doc; not independently re-executed here |
| **Live-unverified** | Requires a running backend + provider; not exercised |

## Classification ladder (ascending)

| Class | Definition |
|-------|------------|
| **Not Started** | No implementing module exists. |
| **Partial** | A subset of the chapter's contract exists, or authority is unresolved / scope-limited. |
| **Implemented** | Module is wired into the live path, but verification is thin/indirect. |
| **Implemented + Verified** | Deterministic module with passing tests — but shadow, flag-off, or scope-limited (not the sole live authority). |
| **Authoritative/Live** | The chapter's core mechanism is the canonical authority in the live turn path **and** is verified. |

Classifications reflect the **whole chapter contract**. A chapter can contain a
verified sub-component yet still be classified lower because the full contract is
incomplete (noted in "Caveat").

---

## Distribution (33 chapters)

| Class | Count | Chapters |
|-------|:-----:|----------|
| Authoritative/Live | 3 | 6, 14, 31 |
| Implemented + Verified | 12 | 10, 11, 12, 18, 19, 20, 25, 26, 27, 28, 29, 32 |
| Implemented | 1 | 4 |
| Partial | 12 | 1, 2, 3, 9, 13, 16, 17, 21, 22, 24, 30, 33 |
| Not Started | 5 | 5, 7, 8, 15, 23 |

---

## Per-chapter audit

| Ch | System | Class | Evidence (code · tests · docs) | Caveat |
|----|--------|-------|--------------------------------|--------|
| 1 | Living World Doctrine | Partial | Code: `pressure_graph.py`, `consequence_echoes.py` (partial embodiment) · Docs-claimed: `next-work.md` **NW-P1-07** | Doctrine; its operational proof (the "Living World Test" — autonomous motion) is not built |
| 2 | Simulation First Philosophy | Partial | Docs-claimed: `system-doctrine.md` **H1/H2 "Partial"** | Doctrine; LLM still authors initial `rolling_state` before merge |
| 3 | State Is Truth | Partial | Code: `memory.py` (consolidate / protected keys), `gateway.py` (`strip_illegal_state_changes`) · Run✅-class: `verify_p0_object_permanence.py`, `test_anti_hallucination_gateway.py` · Docs: **H1 Partial** | Verified guard pipeline, but LLM authorship of state not eliminated |
| 4 | The Simulation Loop | Implemented | Code: `server.py` `story_action`, `replayability.prepare_action_turn` · Tests: `test_http_integration.py`, `verify_p1_immersion_integrity.py` | 4.12 hidden-D20 resolution is LLM-mediated, not a deterministic engine (`system-doctrine` H6 = N/A) |
| 5 | World Heartbeat Architecture | **Not Started** | Docs: `current-state.md` `TURN_COUPLED_AUTONOMY_ONLY`; **NW-P1-07** | No autonomous between-turn tick module |
| 6 | Pressure Ecology | **Authoritative/Live** | Code: `pressure_graph.py` (canonical; `active_pressures` derived) · Tests: `test_pressure_graph.py`, `test_pressure_authority.py` · Docs: **ADR-023 complete** | Pressure *authority* is canonical + live; broader ecological generation is partial |
| 7 | Settlement Organism Theory | **Not Started** | Code: no settlement module in inventory | — |
| 8 | Resource Flow Theory | **Not Started** | Code: no economy/resource module in inventory | — |
| 9 | Information Theory | Partial | Code: `server.py` `_apply_rumour_propagation_tick` · Tests: `verify_p2_consequences_rumours.py` | Rumour-tick subset only; no full information propagation model |
| 10 | NPC Architecture | Implemented + Verified | Code: `npc_world_moves.py`, `npc_liveness.py`, `living_cast_*` · Tests: `test_npc_world_moves.py`, `test_living_cast_integration.py` · Docs: Living Cast live (ADR-020) | Full Ch 25 actor scaling is shadow |
| 11 | Goal Systems | Implemented + Verified | Code: `npc_agendas.py` · Tests: `test_npc_agendas.py` | Drives live NPC move selection |
| 12 | Memory Systems | Implemented + Verified | Code: `memory.py` (rolling consolidation, npc-memory bounds) · Run✅: `test_context_budget.py`; `verify_p1_immersion_integrity.py` | Retrieval (Ch 28) is shadow |
| 13 | Relationship Systems | Partial | Code: `relationships.py`, `relationship_provenance.py` · Docs: `current-state.md` **"Relationship provenance — Unresolved"** | Golden-path blocker; NPC↔NPC edges absent |
| 14 | Stress & Breaking Point | **Authoritative/Live** | Code: `stress.py` (engine-owned `actor_stress`) · Run✅: `test_stress.py`, `test_stress_integration.py`, `test_stress_behaviour.py` · Docs: **`TURN_INTEGRATION_VERIFIED`**, ADR-022 | P3/P4 breaking-point behaviours deferred |
| 15 | Social Structures | **Not Started** | Code: no module in inventory | — |
| 16 | Reputation Systems | Partial | Code: faction `player_reputation`/`ticks` in `server.py`; `hud.py` PRS | No dedicated reputation engine |
| 17 | Faction Architecture | Partial | Code: `server.py` `_apply_faction_consequence_tick` · Tests: P1-D (`verify_p1_immersion_integrity.py`) | Consequence-tick only; no faction decision AI |
| 18 | Consequence Ledger | Implemented + Verified | Code: `server.py` ledger, `consequence_echoes.py` · Run✅: `test_consequence_echoes.py`; `test_replayability_integration.py` | — |
| 19 | Delayed Consequences | Implemented + Verified | Code: `server.py` `_apply_delayed_consequence_tick`, `replayability.collect_qualifying_echo_sources` · Run✅: `test_consequence_echoes.py` | — |
| 20 | Context Gravity | Implemented + Verified | Code: `memory.py` `enforce_context_budget`, `PROMPT_REGISTRY_CAPS` · Run✅: `test_context_budget.py` | Canonical gravity retention (Ch 26) is shadow; legacy budget governor is the live authority |
| 21 | Scar Theory | Partial | Code: persistence via `rolling_state` + death/destruction registries (`gateway.py`) · Tests: `verify_p0_object_permanence.py` | No formal permanent-scar system |
| 22 | Event Sourcing | Partial | Code: `replayability._append_transition_receipt` (bounded receipts) · Docs: `current-state.md` **"DEFERRED — turn log only, no aggregate rebuild"** | Bounded receipts are a local substitute, not canonical reconstruction |
| 23 | Historical Layering | **Not Started** | Docs: `current-state.md` (not present) | — |
| 24 | Discovery Architecture | Partial | Code: `secrets.py` (secret-reveal sub-mechanic) · Tests: `test_secret_reveal.py` (37 cases) | Reveal mechanic only; full discovery architecture absent |
| 25 | Actor Resolution Scaling | Implemented + Verified | Code: `actor_resolution.py`, `foundation_promotion.route_actor_move` · Run✅: `test_actor_resolution.py`, `test_foundation_promotion.py` · Docs: `foundation-promotion.md` | **Shadow / `ENABLE_CANONICAL_ACTOR_RESOLUTION` default OFF**; legacy `resolve_actor_tier` authoritative |
| 26 | Gravity Governance Layer | Implemented + Verified | Code: `gravity_governance.py` · Run✅: `test_gravity_governance.py` · Docs: `foundation-promotion.md` | **Shadow / flag OFF**; legacy heuristic authoritative |
| 27 | NPC Decision Engine (Utility AI) | Implemented + Verified | Code: `utility_ai.py`, `utility_dimensions.py`, `living_cast_shadow.py` · Run✅: `test_utility_ai.py`, `test_living_cast_shadow.py` · Docs: **NW-UTILITY-01** | `TURN_INTEGRATION_UNVERIFIED`; live selection flag OFF |
| 28 | Memory Retrieval System | Implemented + Verified | Code: `memory_retrieval.py` · Run✅: `test_memory_retrieval.py`, `test_foundation_integration.py` · Docs: `foundation-promotion.md` | **Shadow; prompt injection BLOCKED** by `D_MEMORY_RETRIEVAL_SHADOW` (gate hardened 2026-07-02) |
| 29 | Relationship Calculus | Implemented + Verified | Code: `relationships.update_relationship_calculus` (engine-owned vectors, AC8) · Run✅-class: `test_relationship_calculus.py` (`test_engine_owns_vectors_ignores_llm_injection`) | Provenance blocker shared with Ch 13 |
| 30 | World Genesis & Burn-In | Partial | Code: `opening_state.py`, `run_identity.py` · Tests: `test_opening_state.py`, `test_run_identity.py` | 200-year burn-in not implemented (deferred) |
| 31 | LLM Architecture & Integration | **Authoritative/Live** | Code: `gateway.py` (`invoke_llm` chokepoint, truth block, strip, contradiction retry) · Tests: `test_anti_hallucination_gateway.py`, `test_gateway_e2e.py` · Docs: **H5 "Enforced"** | Full Ch 31 conformance not claimed |
| 32 | Simulation Testing Framework | Implemented + Verified | Code: `engine_determinism.py`, `verify_hash.py`, `tests/conftest.py` · Tests: `test_engine_determinism.py`, `test_ci_network_safety.py`; `.github/workflows/deterministic-ci.yml` (**NW-P2-03**) | Live 20-turn harness (`test_live_20_turn_harness.py`, `qa_live_*`) Live-unverified |
| 33 | NPC Lifecycle & Generational Succession | Partial | Code: `npc_lifecycle.py`, `simulation_clock.py` · Run✅: `test_npc_lifecycle.py`, `test_simulation_clock.py`, `test_simulation_clock_hardening.py` · Docs: `ch33-lifecycle-phase2.md` | Phase 1+2 core verified but **flag OFF, not time-authoritative**; births/inheritance/succession/burn-in deferred |

---

## Completion readings

The SoT provides no implementation status, so "percent complete" depends entirely
on the bar. Three honest readings, from strict to generous:

| Reading | Definition | Result |
|---------|------------|--------|
| **Live authority** | Authoritative/Live only | **3 / 33 ≈ 9%** |
| **Built + tested** | Authoritative/Live + Implemented+Verified (incl. shadow/flag-off) | **15 / 33 ≈ 45%** |
| **Weighted maturity** | Live 1.0 · Impl+Verified 0.6 · Impl 0.4 · Partial 0.25 · Not Started 0 | **13.6 / 33 ≈ 41%** |

The gap between **9%** and **45%** is the real state: a broad, well-tested engine
whose four flagship foundation systems (Ch 25–28) are deterministically
implemented and verified **but deliberately shadow / flag-off**. Making them
Authoritative/Live is gated on live validation (real-LLM 20-turn endurance +
gameplay acceptance) and, for Ch 28, an explicit shadow-acceptance decision — not
on additional code.

## Confidence and limits

- **Run✅** chapters were exercised in-session (foundation, memory-retrieval,
  simulation-clock, lifecycle, actor/gravity, context-budget → 192 passed, 1
  pre-existing sandbox-only failure unrelated to these systems).
- All other classifications are **Docs-claimed / Code** — reconciled from status
  docs and source inspection, **not** an independent live re-run.
- No live-stack (`@pytest.mark.live`) suite was executed; all "Authoritative/Live"
  claims rest on deterministic tests + reconciled runtime docs, not real-LLM play.
- This audit reflects the working tree on `emergent` at the audit date and should
  be re-run if foundation promotion flags change or live validation lands.
