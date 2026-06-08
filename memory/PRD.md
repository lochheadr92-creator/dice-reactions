# Dice Reaction Story Engine — Source-of-Truth Conformance Tracker

> **Authority:** `Source of Truth 1–32` (Living World Simulation Bible, v1.0, Canonical).
> This file is NOT the bible. It tracks how far the running app conforms to each
> chapter, chapter-by-chapter. The bible wins every conflict.

## Prime Doctrine (the lens for everything below)
- **Ch 31:** *"The LLM writes prose. The engine writes truth."* The LLM must never
  decide outcomes, choose NPC actions, or mutate state — only render prose.
- **Ch 3 / Ch 2:** State is truth; simulation first, narrative second.
- **Reality of this app today:** the LLM still invents narrative + state + choices each
  turn; the backend applies deterministic *guards/ticks* on top. This is the inverse of
  Ch 31 and is being corrected **incrementally** (agreed approach — no full rebuild yet).

## Runtime facts (current)
- Stack: Expo SDK 54 + Expo Router · FastAPI · MongoDB · OpenRouter.
- Active model: `cognitivecomputations/dolphin-mistral-24b-venice-edition:free`
  (kept intentionally cheap until architecture is more compliant). ⚠️ Currently
  rate-limited upstream (HTTP 429) and auto-falling back to `anthropic/claude-3-5-haiku`.
- Fallback chain: haiku → claude-3-5-sonnet → mythomax.
- Key backend modules: `server.py` (routes + guards + prompt), `ai_service.py`
  (OpenRouter client), `ai_config.py` (routing), `memory.py` (rolling-state
  consolidation/compression/budget), `gateway.py` (**Anti-Hallucination Gateway, Ch 31**).

## Status legend
- ❌ None — not implemented.
- 🟡 Partial — LLM-driven with deterministic guard(s), not a true engine.
- 🟢 Conformant — deterministic engine owns this truth.
- 🔵 Active — currently being built.

---

## ✅ Increment log
- **Inc-1 (Ch 31 — Anti-Hallucination Gateway):** `gateway.py` added.
  - PREVENT: `build_immutable_truth_block` injects established facts (destroyed/consumed
    objects, dead NPCs, ongoing wounds) into the prompt as "do not contradict".
  - STRIP: `strip_illegal_state_changes` reverts terminal-object revival, silent injury
    resolution/improvement (no recovery cue), and deceased-NPC revival.
  - DETECT: `detect_prose_contradictions` → correction re-prompt.
  - REGISTRY: `update_death_registry` → engine-owned `rolling_state.deceased`.
- **Inc-1b (Ch 31 — Destruction/Consumption registry):** `update_destruction_registry`
  records terminal object truth even when the live model RENAMES a destroyed item
  ("lantern"→"lantern fragments") or silently drops a consumed item — writes the terminal
  row under the ORIGINAL identity. Closes the live-probe CRITICAL (iteration_3).
- **Inc-1c (Ch 31 — remaining sub-increments):**
  - SOLE CALLER: `gateway.invoke_llm` is now the ONLY entry point to the provider
    (Ch 31.11); `server.py` no longer imports `chat_completion*`.
  - ACTION ASSERTION: prose claiming the player acquired a tracked item whose state
    wasn't updated to a possession status → correction re-prompt.
  - KNOWLEDGE BOUNDARY (partial): a dead NPC framed as a future/interactive actor
    ("Garrett will help", "ask Mira") → correction re-prompt. NOTE: full per-NPC
    working-memory knowledge boundary (an NPC knowing facts they never witnessed)
    requires the Ch 28 memory-retrieval model and is deferred to P2/P3.
  - Tests: `tests/test_anti_hallucination_gateway.py` (24 unit), `tests/test_gateway_e2e.py`
    (2 full-pipeline). Live: 5/5 adversarial families verified (iteration_3 + iteration_4).

---

## Conformance table (Ch 1–32)

### Ch 1 — Living World Doctrine
- Required: world has independent motion, persistent memory, resource movement, pressure.
- Status: 🟡 (world_instability / faction / rumour ticks simulate light independent motion).
- Gap: no true off-screen world heartbeat; motion is prompt-driven + light ticks.
- Plan: later — World Heartbeat (Ch 5) engine.
- Priority: P3. Test: Dead World Test (Ch 32.5) automated — not yet.

### Ch 2 — Simulation First Philosophy
- Required: causality/consequence outrank narrative; emergence over script.
- Status: 🟡 (prompt rules + consequence/rumour ticks).
- Gap: narrative still authored by LLM, not derived from sim.
- Plan: shrinks as engine systems land. Priority: P3. Test: anti-script audit.

### Ch 3 — State Is Truth
- Required: state is authoritative; nothing changes without a tracked cause.
- Status: 🟡 (state-supremacy guard for Health/Fatigue; gateway adds objects/injuries/deaths).
- Gap: many state fields still trust the LLM.
- Plan: extend gateway strip to more tracked fields. Priority: **P1**.
- Test: gateway unit tests + adversarial revival/heal probes.

### Ch 4 — The Simulation Loop (validate→context→resolve→consequence)
- Required: hidden D20 resolution; validation of action legality.
- Status: 🟡 (hidden D20 in prompt/debug; format validation; direct-inspection guard).
- Gap: resolution decided by LLM prose, not engine. Plan: P2. Test: resolution audit.

### Ch 5 — World Heartbeat Architecture
- Required: micro/local/regional/macro ticks advancing the world.
- Status: ❌ (no real heartbeat; per-turn ticks only).
- Plan: P3 engine. Test: off-screen change over N ticks.

### Ch 6 — Pressure Ecology
- Required: pressures generate/relieve/cascade.
- Status: 🟡 (`active_pressures`, `pressure_horizon`, faction_pressure in rolling_state).
- Gap: not numeric/cascading. Plan: P3. Test: pressure propagation.

### Ch 7 — Settlement Organism Theory
- Required: settlements with food/wealth/security/stability variables.
- Status: ❌. Plan: P3 (depends on World Genesis). Test: settlement variance.

### Ch 8 — Resource Flow Theory
- Required: resources move/deplete/renew.
- Status: ❌ (object inventory only, no economy). Plan: P3. Test: flow audit.

### Ch 9 — Information Theory
- Required: information spreads as rumours with distortion.
- Status: 🟡 (`_apply_rumour_propagation_tick`). Gap: not graph-based. Plan: P3.
- Test: rumour reaches NPC after N turns.

### Ch 10 — NPC Architecture
- Required: NPCs with identity, drives, goals, memory, relationships.
- Status: 🟡 (`npc_memory`, `npcs`, goals/next_move in rolling_state).
- Gap: no numeric drives/utility. Plan: feeds Ch 27/29. Priority: P2.

### Ch 11 — Goal Systems
- Required: goal hierarchy (core→life→strategic→operational→action).
- Status: 🟡 (single `goal` per NPC). Gap: no hierarchy. Plan: P3.

### Ch 12 — Memory Systems
- Required: weighted memories that decay/compress.
- Status: 🟡 (`npc_memory` severity + decay bounds; rolling compression).
- Gap: no retrieval probability. Plan: feeds Ch 28. Priority: P2.

### Ch 29 — Relationship Calculus  🟢 (NPC↔player)
- Required: trust/loyalty/fear/resentment 4-vector with decay + events.
- Status: 🟢 for NPC→player. `relationships.py` — engine-owned vectors in
  `rolling_state.relationship_vectors` (PROTECTED). Per turn: neglect decay toward
  neutral (Ch 29.10), event detection from action+narrative applying canonical
  Ch 29.8 deltas (betrayal/save_life/help/threaten/attack/lie/gift/reward/keep_promise/
  break_promise/humiliate/apology, with subsumption + hypothetical guard), derived
  states (collapsed/betrayal_risk/cowed/devoted/trusting/resentful/wary/neutral),
  coarse stance sync, and a `<relationships>` prompt block so the LLM renders behaviour
  to match. LLM-injected vectors are ignored (engine reads PRIOR as authority).
- Gap: NPC↔NPC / faction-level calculus (Ch 29.11) and emotional-intensity/personality
  multipliers not yet modelled (base values used). Memory-retrieval weighting = Ch 28.
- Priority: NPC↔player done. Test: `tests/test_relationship_calculus.py` (11) +
  e2e `tests/test_gateway_e2e.py::test_relationship_calculus_end_to_end`.

### Ch 14 — Stress & Breaking Point Systems
- Required: numeric stress driving behaviour/breaks.
- Status: ❌ (Fatigue chip only). Plan: P3. Test: stress→behaviour.

### Ch 15 — Social Structures / Ch 16 — Reputation / Ch 17 — Faction Architecture
- Required: groups, reputation grounded in interactions, factions act.
- Status: 🟡 (`faction_pressure` ticks: suspicion/guard_attention/goodwill/debt).
- Gap: reputation not derived from relationship calculus. Plan: P3.

### Ch 18 — Consequence Ledger / Ch 19 — Delayed Consequences
- Required: consequences tracked + fire later.
- Status: 🟡 (`active_consequences`/`delayed_consequences`/`latent_triggers` protected;
  `_apply_delayed_consequence_tick`). Gap: heuristic firing. Plan: P2. Test: delayed fire.

### Ch 20 — Context Gravity / Ch 26 — Gravity Governance Layer
- Required: single retention score governs keep/compress/archive/forget.
- Status: ❌ (ad-hoc compression in `memory.py`; no unified retention score).
- Plan: **candidate next increment** (unifies memory/compression). Priority: P2.
- Test: Governance Test (Ch 26.11) — retention bands trigger correct action.

### Ch 21 — Scar Theory / Ch 22 — Event Sourcing / Ch 23 — Historical Layering
- Required: permanent scars; every state change traceable to an event; legends.
- Status: ❌ (turns stored, but not an event-sourced reconstructable log).
- Plan: P3 (large). Test: Event Sourcing Test (Ch 32.7).

### Ch 24 — Discovery Architecture
- Required: player assembles clues; engine never hands the solution.
- Status: 🟡 (`clues`/`topic_ledger`). Plan: P3.

### Ch 25 — Actor Resolution Scaling
- Required: Hero/Active/Relevant/Dormant/Archived tiers.
- Status: ❌ (all NPCs treated equally). Plan: P3. Test: Actor Resolution Test (32.8).

### Ch 27 — NPC Decision Engine (Utility AI)
- Required: deterministic utility AI chooses NPC actions (NOT the LLM).
- Status: ❌ (NPC behaviour authored by LLM). Plan: P2 (high doctrine value).
- Test: Decision Engine Test (32.3) — starving NPC eats.

### Ch 28 — Memory Retrieval System
- Required: probabilistic recency/emotion/cue retrieval into working memory.
- Status: ❌. Plan: P3 (after Ch 27). Test: Memory Retrieval Test (32.3).

### Ch 29 — Relationship Calculus
- Required: trust/loyalty/fear/resentment 4-vector with decay + events.
- Status: ❌ (qualitative threads only). Plan: **strong candidate** P2.
- Test: Relationship Calculus Test (32.4) — betrayal damages trust+loyalty, raises resentment.

### Ch 30 — World Genesis & Burn-In
- Required: pre-played history before player enters.
- Status: 🟡 (Custom World setup seeds hooks/instability; no burn-in sim).
- Plan: P3 (large). Test: World Genesis Test (32.11).

### Ch 31 — LLM Architecture & Integration  🔵→🟡
- Required: LLM = prose only; anti-hallucination gateway validates against state.
- Status: 🟡 (**Inc-1 done**: truth injection + strip + detect + death registry +
  correction re-prompt). LLM still authors state proposals (stripped/validated, not yet
  fully engine-owned).
- Gap: knowledge-boundary + action-assertion checks; gateway as the *only* LLM caller.
- Plan: next sub-increments. Priority: **P1**. Test: `tests/test_anti_hallucination_gateway.py`
  + live adversarial probes (revive destroyed item / resurrect dead NPC).

### Ch 32 — Simulation Testing Framework
- Required: every doctrine becomes an automated, deterministic test.
- Status: 🟡 (pytest suites: custom world, story engine, **gateway**; live QA scripts).
- Gap: no Dead/Living/Event-Sourcing/Governance world tests.
- Plan: grow alongside each engine increment. Priority: P2.

---

## Backlog / next candidate increments (in priority order)
1. **P1 — Ch 31 sub-increments:** route ALL LLM calls through the gateway; add
   knowledge-boundary + action-assertion checks; expand strip coverage (Ch 3).
2. **P2 — Ch 29 Relationship Calculus:** numeric trust/loyalty/fear/resentment vector
   maintained by the engine, fed from interaction events. Highest emergent-behaviour ROI.
3. **P2 — Ch 26 Gravity Governance:** unify retention scoring; replace ad-hoc compression.
4. **P2 — Ch 27 Utility AI:** deterministic NPC action selection.
5. **P3 — Ch 25 Actor Resolution, Ch 5 Heartbeat, Ch 30 Burn-In, Ch 22 Event Sourcing.**

## Verification status
- `tests/test_anti_hallucination_gateway.py`: 13 passing (unit).
- `tests/test_custom_world_system.py`: 7 passing (live).
- Live end-to-end gateway probe (revive/resurrect): **pending testing_agent run.**
