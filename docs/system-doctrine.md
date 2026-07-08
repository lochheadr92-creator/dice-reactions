# System Doctrine

Rules governing Dice Reaction implementation on the **`emergent`** branch. Each **hard invariant** includes enforcement status based on code and tests found in this repository — not on `memory/PRD.md` claims alone.

**`memory/PRD.md`** is the planning and Source-of-Truth conformance tracker. It is **not** runtime truth.

**Enforcement status key:**

| Status | Meaning |
|--------|---------|
| **Enforced** | Code path actively applies the rule; verification scripts or tests cover it |
| **Partial** | Rule exists but gaps remain (LLM drift, missing auth, incomplete guards) |
| **Unverified** | No enforcing code or tests found |
| **N/A** | Concept does not apply to this codebase |

---

## Hard invariants

### H1: State is truth. Narrative is output.

| Field | Detail |
|-------|--------|
| **Meaning** | Persisted simulation state (`rolling_state`, `ledger`, guarded `state`) is authoritative. Prose is generated presentation. |
| **Why** | Prevents narrative hallucination from becoming game facts. |
| **Allowed** | LLM proposes state in tagged blocks; guards merge, correct, and persist. |
| **Forbidden** | Frontend or API treating narrative text as source of truth for mechanics. |
| **Files** | `AGENTS.md`, `backend/server.py`, `backend/memory.py`, `backend/gateway.py`, `frontend/src/sanitize.ts` |
| **Tests** | `verify_p0_object_permanence.py`, `test_anti_hallucination_gateway.py`, `test_gateway_e2e.py` |
| **Status** | **Partial** — gateway STRIP/registry and guards correct many drift cases; LLM still authors initial `rolling_state` each turn before merge |

---

### H2: The LLM cannot be the sole author of simulation truth

| Field | Detail |
|-------|--------|
| **Meaning** | Model output is provisional until deterministic layers merge, guard, validate, and persist. |
| **Why** | LLMs omit, contradict, or leak mechanics. |
| **Allowed** | LLM emits tagged blocks; backend merges with `consolidate_rolling_state`, applies gateway strip, relationship calculus, HUD shaping, and other guards. |
| **Forbidden** | Persisting LLM output without guard pipeline on story turns; calling OpenRouter outside `gateway.invoke_llm`. |
| **Files** | `server.py` (`story_action`, `new_story`), `memory.py`, `gateway.py`, `relationships.py`, `hud.py` |
| **Tests** | `verify_p0_object_permanence.py`, `test_anti_hallucination_gateway.py`, `test_relationship_calculus.py` (`test_engine_owns_vectors_ignores_llm_injection`) |
| **Status** | **Partial** — protected-key union restore, gateway strip, engine-owned `relationship_vectors`, and object canonicalization are deterministic; many rolling fields still accept fresh LLM values wholesale |

---

### H3: Engine-only state cannot leak into player-facing text

| Field | Detail |
|-------|--------|
| **Meaning** | Rolls, modifiers, triggers, `rolling_state`, debug payloads, relationship vector numbers, and mechanic labels must not appear in normal play UI. |
| **Why** | Product is hidden-systems narrative; immersion breaks on exposure. |
| **Allowed** | Sanitized paragraphs/choices in chronicle view; DNG/MOM/PRS HUD chips; dev panel when unlocked. |
| **Forbidden** | Rendering raw `debug`, `rolling_state`, or mechanic lines in default play view. |
| **Files** | `server.py` (`_sanitise_turn_for_player`, `_validate_parsed`), `frontend/src/sanitize.ts`, `frontend/app/play/[id].tsx` |
| **Tests** | `verify_p1_immersion_integrity.py` (P1-A validator), `verify_p15_microfixes.py` |
| **Status** | **Partial** — three layers exist; LLM may leak before validation retry fails; export endpoint bypasses player sanitization |

---

### H4: Persisted turn events are append-only during normal play

| Field | Detail |
|-------|--------|
| **Meaning** | Each story action creates a new turn document; existing turns are not rewritten in place. |
| **Why** | Audit trail and chronicle history integrity. |
| **Allowed** | `db.turns.insert_one` on each turn; read by `turn_number` sort. |
| **Forbidden** | Silently mutating prior turn documents after persistence. |
| **Files** | `server.py` (`insert_one` in `story_action`, `new_story`) |
| **Tests** | No dedicated append-only test found |
| **Status** | **Partial** — normal path appends; `reset_session` and `delete_session` delete turns; session `rolling_state` is overwritten (not event-sourced) |

---

### H5: Narrative must pass through the approved gateway and sanitization path

| Field | Detail |
|-------|--------|
| **Meaning** | (1) All LLM calls route through `gateway.invoke_llm` (Ch 31.11 chokepoint). (2) Prompt carries `build_immutable_truth_block` + `build_relationship_block` before generation. (3) Post-parse: `strip_illegal_state_changes`, death/destruction registries, `detect_prose_contradictions` with retry. (4) Player-visible text flows through `_validate_parsed` / `_full_validate`, `_maybe_sanitise_turn`, and frontend `sanitizeParagraphs` / `sanitizeChoices`. |
| **Why** | Single controlled invocation and presentation boundary; engine is authority over immutable facts. |
| **Allowed** | Validated LLM narrative → gateway strip → guards → optional backend strip → frontend presentation filter. |
| **Forbidden** | Direct `chat_completion_with_meta` calls from routes; bypassing sanitizers for default player views. |
| **Files** | `gateway.py`, `server.py`, `frontend/src/sanitize.ts`, `frontend/app/play/[id].tsx` |
| **Tests** | `test_anti_hallucination_gateway.py` ✅, `test_gateway_e2e.py` ✅, `verify_p1_immersion_integrity.py` ✅, `verify_p15_microfixes.py` ✅ |
| **Status** | **Enforced** on LLM chokepoint and standard player routes when `developer_mode` false; **Partial** overall due to `export_session`, unauthenticated admin API, and pre-validation LLM leaks |

---

### H6: Historical scoring behaviour cannot change accidentally

| Field | Detail |
|-------|--------|
| **Meaning** | If a scoring/ranking subsystem exists, same inputs must yield same rankings across releases. |
| **Why** | Fairness and regression safety for mechanical outcomes. |
| **Allowed** | N/A — no scoring subsystem in this repository. |
| **Forbidden** | Treating external engine scoring symbols as lost Dice Reactions features. |
| **Files** | None — D20 outcomes are LLM-mediated inside `<debug>` / hidden rolls, not a deterministic scoring module |
| **Tests** | None — symbols `score_candidate_decomposed`, NaN-ranking guards never existed in this repo's git history |
| **Status** | **N/A** |

---

### H7: Developer-only information must remain inaccessible to normal players

| Field | Detail |
|-------|--------|
| **Meaning** | `rolling_state`, `debug`, `raw`, internal state keys, relationship vector numbers, and admin diagnostics are dev-only. |
| **Why** | Protect immersion and prevent mechanic gaming. |
| **Allowed** | Raw payloads via admin-authenticated `/export/raw` or `/admin/session/{id}/diagnostics`; `[DEV_MODE: ON]` prompt marker when server `developer_mode` and request `debug_mode` both true. |
| **Forbidden** | Player routes returning `rolling_state`/`debug`/`raw` when `developer_mode` true; client Settings calling admin API; `device_id` in protected-route URLs. |
| **Files** | `server.py` (`_sanitise_*`, debug marker in `story_action`), `security.py`, `frontend/app/settings.tsx`, `frontend/app/play/[id].tsx` |
| **Tests** | `test_security.py` cases 16–25 ✅; `test_story_engine.py` (live — **not run**) |
| **Status** | **Enforced** on player routes; admin raw export gated; public client has no admin credentials |

---

## Architectural constraints

May evolve only through an explicit recorded decision in `decision-log.md`.

| ID | Constraint |
|----|------------|
| AC1 | OpenRouter is the sole LLM provider abstraction (`ai_service.py`), invoked only via `gateway.invoke_llm`. |
| AC2 | MongoDB is the system of record for sessions and turns. |
| AC3 | `rolling_state` is the compression packet for long-horizon continuity; prompt carries `<prior_state>` plus bounded replay. |
| AC4 | Session-locked `active_model` and `fallback_chain` at story creation. |
| AC5 | Single system prompt document (`STORY_ENGINE_SYSTEM_PROMPT`) defines output tag contract. |
| AC6 | Device `device_id` (client UUID) scopes session listing and ownership on protected routes — not user accounts. |
| AC10 | Admin mutations require `ADMIN_API_KEY` + `X-Admin-Api-Key` header; player `/export` is always sanitised. |
| AC11 | `POST /story/new` rate-limited before LLM; player responses use `player_api` allowlists. |
| AC7 | Admin settings stored in `admin_settings` collection, merged over env defaults. |
| AC8 | `relationship_vectors` in `rolling_state` are engine-owned (protected key); LLM-injected vectors are ignored. |
| AC9 | HUD exposes DNG/MOM/PRS only — no Objective/quest steering (`hud.shape_hud`). |
| AC12 | The `Simulation-Kernel-Research` gitlink has been removed from the repository (2026-07-08, ADR-026 amendment); it carried no runtime dependency while present, confirmed both before and after removal by the guard test. Any future research-only location remains non-runtime documentation by default — not current app configuration, not automatically canonical for existing behaviour. Production runtime code must not import, open, or otherwise depend on such locations; adopting a research concept requires a dedicated migration ADR. Guarded by `backend/tests/test_research_isolation.py`. See ADR-026. |

---

## Current preferences

Useful choices, not fundamental invariants. May change without ADR if low risk.

| Preference | Current choice | Files |
|------------|----------------|-------|
| Default model | Claude 3.5 Haiku | `ai_config.py` |
| Default mode | `advanced` | `server.py` |
| Memory depth | `3` recent turns replayed | `server.py` |
| Validation retry | Single retry on invalid output (format or hallucination) | `server.py` `_generate_validated_turn` |
| Relationship direction | NPC→player vectors only | `relationships.py` |
| HUD chips | Danger (DNG), Momentum (MOM), Pressure (PRS) | `hud.py`, `play/[id].tsx` |
| Typography | Garamond + JetBrains Mono dark theme | `frontend/src/theme.ts` |
| Error copy | User-friendly OpenRouter mapping | `frontend/src/errors.ts` |
| Cost mode | `normal` unless set `low` | `ai_config.py` |

---

## Candidate invariants requiring confirmation

These appear in `memory/PRD.md` or design vocabulary but **lack enforcing code** in this repo:

- Actor identity resolution and caps (PRD Ch 25)
- NPC↔NPC relationship edges (only NPC→player implemented)
- Utility AI deterministic decision layer (PRD Ch 27)
- Gravity-based memory retention beyond `enforce_context_budget`
- Formal event sourcing with immutable aggregate rebuild

Do not treat as invariants until implemented and tested.

**Explicitly N/A in this repository:** historical scoring equivalence, NaN/infinity ranking guards — never implemented here.