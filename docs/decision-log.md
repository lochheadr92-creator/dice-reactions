# Decision Log

Architecture Decision Records (ADRs) supported by evidence in this repository. Dates reflect when the decision is documented here, not necessarily original authorship.

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
| **Decision** | Append turns via `insert_one`. Maintain latest `rolling_state` on session document. Rebuild prompts from recent turn replay + `<prior_state>`. `reset_session` deletes turns and clears rolling state. |
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
| **Risks** | Missed or false faction ticks; relationship direction not enforced. |
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
| **Decision** | `admin_post_settings` rejects `model` not in `SUPPORTED_MODELS` catalog. Runtime uses session-locked `active_model` + `chat_completion_with_meta` fallback chain. |
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
| **Consequences** | Two flags to coordinate; export endpoint ignores sanitization. |
| **Risks** | Unauthenticated `developer_mode` toggle; export leak. |
| **Files affected** | `backend/server.py`, `frontend/app/settings.tsx`, `frontend/app/play/[id].tsx` |
| **Tests required** | Integration with `debug_mode: false` (not run this pass) |
| **Evidence** | `bumpVersionTap` in `settings.tsx`; `debug_marker` logic in `story_action` |

---

## Candidate decisions requiring confirmation

These topics appear in design briefs or related engine vocabulary but **lack sufficient code evidence** for accepted ADR status:

| Topic | Finding |
|-------|---------|
| Actor caps / actor resolution | No resolver module; NPCs are LLM-authored lists |
| Relationship directionality | `relationship_threads` schema in prompt only; no edge-direction guard |
| Deterministic utility AI | Not present |
| Gravity-based memory retention | Only context budget + rolling merge |
| Historical score equivalence | No scoring subsystem |
| Non-finite scoring inputs (NaN/∞) | No scoring subsystem |
| Formal event sourcing | Turn log only (see ADR-003) |

Promote to ADR when implementation and tests exist.