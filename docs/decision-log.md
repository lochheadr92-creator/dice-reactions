# Decision Log

Architecture Decision Records (ADRs) supported by evidence in this repository on the **`emergent`** branch. Dates reflect when the decision is documented here; implementation commits noted where known.

**`memory/PRD.md`** is the planning and conformance tracker — not evidence for accepted ADR status.

---

## ADR-001: State versus narrative authority

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | LLM-generated prose can contradict persisted simulation state or invent mechanics visible to players. |
| **Decision** | Persisted `rolling_state`, `ledger`, and guarded `state` are authoritative. Narrative is output. Deterministic guards and `consolidate_rolling_state` correct LLM drift before persistence. |
| **Alternatives considered** | Narrative-first (reject — causes drift); full deterministic sim without LLM (reject — product is LLM-narrated). |
| **Consequences** | Guard pipeline must run every turn; protected keys must be maintained in `memory.py`. |
| **Risks** | LLM still proposes initial rolling state; guards are heuristic, not complete. |
| **Files affected** | `AGENTS.md`, `backend/server.py`, `backend/memory.py` |
| **Tests required** | `verify_p0_object_permanence.py`, guard unit tests in `test_custom_world_system.py` |
| **Evidence** | `AGENTS.md` lines 7–11; `consolidate_rolling_state` in `memory.py`; guard calls in `story_action` route |

---

## ADR-002: Dual-layer narrative gateway (backend API + frontend presentation)

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | LLM output occasionally leaks engine tags into `<narrative>`. API consumers include web client and potential future clients. |
| **Decision** | (1) Backend strips dev fields and internal state keys when `developer_mode` is false. (2) Frontend `sanitize.ts` strips leaked tags/mechanic lines from rendered paragraphs only, without mutating stored turn objects. (3) `_validate_parsed` rejects invalid player-facing output with one retry. |
| **Alternatives considered** | Frontend-only filter (reject — other clients exposed); backend-only (reject — truncated tags still render in edge cases). |
| **Consequences** | Two sanitization layers to maintain; export endpoint currently bypasses player sanitization. |
| **Risks** | Export and dev mode leaks; regex maintenance burden. |
| **Files affected** | `backend/server.py`, `frontend/src/sanitize.ts`, `frontend/app/play/[id].tsx` |
| **Tests required** | `verify_p1_immersion_integrity.py`, `verify_p15_microfixes.py` |
| **Evidence** | `sanitize.ts` header comment; `_sanitise_turn_for_player`; P1-A/P1.5 scripts passed 2026-06-17 |

---

## ADR-003: Turn log persistence (not full event sourcing)

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Chronicles need history; long sessions need compressed state. |
| **Decision** | Append turns via `insert_one`. Maintain latest `rolling_state` on session document. Rebuild prompts from recent turn replay + `<prior_state>`. `reset_session` deletes turns and clears rolling state. No aggregate rebuild from event log. |
| **Alternatives considered** | Full event sourcing with aggregate rebuild (not implemented); overwrite turns in place (reject — loses audit trail). |
| **Consequences** | Reset is destructive; no immutable event store. |
| **Risks** | `rolling_state` overwrite can lose history not captured in turn log fields. |
| **Files affected** | `backend/server.py` |
| **Tests required** | None dedicated |
| **Evidence** | `insert_one` for turns; `reset_session` deletes `turns` collection entries |

---

## ADR-004: Context retrieval budgeting (prompt trim, not RAG)

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Long chronicles exceed model context limits. |
| **Decision** | `enforce_context_budget` trims oldest/low-priority messages and compresses `<prior_state>` JSON. Budgets vary by `cost_mode` and `mode` via `resolve_context_budget`. Protected recent messages and protected rolling keys are not dropped. |
| **Alternatives considered** | Vector retrieval over turn archive (not implemented); unbounded prompt growth (reject). |
| **Consequences** | Heuristic token estimate (`chars/4`); old narrative may be dropped from prompt while surviving in DB. |
| **Risks** | Retrieval starvation if budget too aggressive; repetition if too much history kept. |
| **Files affected** | `backend/memory.py`, `backend/ai_config.py`, `backend/server.py` |
| **Tests required** | PRD P1 15+ turn stress (not run) |
| **Evidence** | `enforce_context_budget` implementation; `result["budget"]` attached in `_generate_turn` |

---

## ADR-005: Object identity canonicalization

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Same physical object with label drift accumulated contradictory rows in rolling memory (QA #2). |
| **Decision** | `_normalize_object_name` + `canonicalize_object_registry` collapse `object_locations` and `inventory_objects` to one row per identity; status priority prefers terminal states. |
| **Alternatives considered** | Trust LLM to prune (reject — demonstrated bloat). |
| **Consequences** | Heuristic identity matching may merge distinct objects with similar labels. |
| **Risks** | False merge on ambiguous names. |
| **Files affected** | `backend/memory.py`, `backend/server.py` |
| **Tests required** | `verify_p0_object_permanence.py` ✅ |
| **Evidence** | P0 all scenarios passed 2026-06-17 |

---

## ADR-006: NPC memory bounds and local faction ticks

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | `npc_memory` and `faction_pressure` could grow without bound; social consequences need light determinism. |
| **Decision** | `_apply_npc_memory_bounds` caps remembers list, decays stale minors, caps NPC count. `_apply_faction_consequence_tick` counts theme repeats in memory and bumps existing `faction_pressure` entries after threshold. |
| **Alternatives considered** | Global faction simulation graph (not implemented); unbounded LLM lists (reject). |
| **Consequences** | Regex theme matching; no actor graph resolution. |
| **Risks** | Missed or false faction ticks. |
| **Files affected** | `backend/server.py` |
| **Tests required** | `verify_p1_immersion_integrity.py` P1-D ✅ |
| **Evidence** | P1-D scenarios passed 2026-06-17 |

---

## ADR-007: OpenRouter model picker validation

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Admin UI exposes many models; invalid IDs cause provider errors. |
| **Decision** | `admin_post_settings` rejects `model` not in `SUPPORTED_MODELS` catalog. Runtime uses session-locked `active_model` + `chat_completion_with_meta` (via `gateway.invoke_llm`) fallback chain. |
| **Alternatives considered** | Free-form model string (reject — poor UX/errors). |
| **Consequences** | Catalog must be updated manually in `ai_service.py`. |
| **Risks** | Catalog drift vs OpenRouter availability; free-tier rate limits. |
| **Files affected** | `backend/ai_service.py`, `backend/server.py`, `frontend/app/settings.tsx` |
| **Tests required** | Manual admin POST negative test (not automated) |
| **Evidence** | `admin_post_settings` HTTP 400 on unsupported model |

---

## ADR-008: Developer-only history and telemetry gating

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Debug payloads needed for tuning; must not appear for normal players. |
| **Decision** | Server `developer_mode` in admin settings controls `_maybe_sanitise_*`. Client 7-tap unlock sets local `developerUnlocked` and sets server `developer_mode`. `[DEV_MODE: ON]` only when both server `developer_mode` and request `debug_mode` true. |
| **Alternatives considered** | Per-session only (partially used via `debug_mode`); always-on debug (reject). |
| **Consequences** | Two flags to coordinate; export endpoint ignores sanitization; admin POST unauthenticated. |
| **Risks** | Unauthenticated `developer_mode` toggle; export leak. |
| **Files affected** | `backend/server.py`, `frontend/app/settings.tsx`, `frontend/app/play/[id].tsx` |
| **Tests required** | Integration with `debug_mode: false` (not run this pass) |
| **Evidence** | `bumpVersionTap` in `settings.tsx`; `debug_marker` logic in `story_action` |

---

## ADR-009: Anti-Hallucination Gateway (Ch 31 incremental)

| Field | Detail |
|-------|--------|
| **Date** | Implemented `b4a2891`; documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | LLM can contradict established object, injury, and death facts across turns. |
| **Decision** | Introduce `gateway.py` with: `invoke_llm` as sole LLM entry; `build_immutable_truth_block` (PREVENT); `strip_illegal_state_changes` (STRIP); `detect_prose_contradictions` (DETECT + retry); `update_death_registry` / `update_destruction_registry`. Wire into `_build_messages`, `_generate_turn`, `_full_validate`, and post-parse guard pipeline. |
| **Alternatives considered** | Prompt-only truth (reject — demonstrated drift); direct `ai_service` calls (reject — bypass risk). |
| **Consequences** | All new LLM paths must use `gateway.invoke_llm`; contradiction retry adds latency on failure. |
| **Risks** | Heuristic death/object detection; not full Ch 31 conformance. |
| **Files affected** | `backend/gateway.py`, `backend/server.py` |
| **Tests required** | `test_anti_hallucination_gateway.py` ✅, `test_gateway_e2e.py` ✅ |
| **Evidence** | Commit `b4a2891`; 47-test bundle passed 2026-06-17 |

---

## ADR-010: Relationship calculus — engine-owned NPC→player vectors (Ch 29)

| Field | Detail |
|-------|--------|
| **Date** | Implemented `a52b66d`; documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Social state drifted when LLM authored relationship feelings each turn. |
| **Decision** | `relationships.py` maintains `rolling_state['relationship_vectors']` (protected key). Prior vectors are authoritative; LLM injection ignored. Each turn: neglect decay, regex-detected event deltas (Ch 29.8 table + extensions), derived behavioural state, coarse stance sync on `npcs`, `build_relationship_block` for prompt. **Directionality: NPC→player only.** |
| **Alternatives considered** | LLM-authored `relationship_threads` only (reject — no determinism); full NPC graph (not implemented). |
| **Consequences** | `relationship_threads` remains for seeding/narrative but not for vector mechanics; no NPC↔NPC edges. |
| **Risks** | Regex false positives/negatives; identity bonds decay slower only. |
| **Files affected** | `backend/relationships.py`, `backend/memory.py`, `backend/server.py` |
| **Tests required** | `test_relationship_calculus.py` ✅ (`test_engine_owns_vectors_ignores_llm_injection`) |
| **Evidence** | Commit `a52b66d`; `test_gateway_e2e.py` relationship turn assertion |

---

## ADR-011: HUD shaping — DNG / MOM / PRS (non-prescriptive)

| Field | Detail |
|-------|--------|
| **Date** | Implemented `ff1858d`; documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Objective/quest chips steered player behaviour; product requires condition + pressure without solutions. |
| **Decision** | `hud.shape_hud` strips Objective/Goal keys; ensures Danger (`none`–`critical`) and Momentum (`surging`–`lost`) chips; sets single Pressure line via `derive_pressure` rejecting prescriptive language. Frontend renders DNG, MOM, PRS labels in `play/[id].tsx`. |
| **Alternatives considered** | LLM-only HUD (reject — prescriptive leaks); Objective bar (reject — quest-marker UX). |
| **Consequences** | HUD is engine-shaped every turn after guards; LLM pressure used only if non-prescriptive. |
| **Risks** | Fallback pressure phrases may feel generic. |
| **Files affected** | `backend/hud.py`, `backend/server.py`, `frontend/app/play/[id].tsx` |
| **Tests required** | `test_hud.py` ✅ |
| **Evidence** | Commit `ff1858d`; `test_hud.py` assertions on chip vocabularies |

---

## Candidate decisions requiring confirmation

These topics appear in `memory/PRD.md` or design briefs but **lack sufficient code evidence** for accepted ADR status:

| Topic | Finding |
|-------|---------|
| Actor caps / actor resolution | No resolver module; NPCs are LLM-authored lists (PRD Ch 25 ❌) |
| NPC↔NPC relationship edges | Only NPC→player vectors implemented |
| Deterministic utility AI | Not present (PRD Ch 27) |
| Gravity-based memory retention | Only context budget + rolling merge |
| Formal event sourcing | Turn log only (see ADR-003) |

Promote to ADR when implementation and tests exist.

**Explicitly N/A:** historical score equivalence, NaN/infinity ranking guards — symbols never existed in this repository's git history.