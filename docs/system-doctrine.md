# System Doctrine

Rules governing Dice Reaction implementation. Each **hard invariant** includes enforcement status based on code and tests found in this repository — not on PRD claims alone.

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
| **Files** | `AGENTS.md`, `backend/server.py`, `backend/memory.py`, `frontend/src/sanitize.ts` |
| **Tests** | `verify_p0_object_permanence.py`, `test_custom_world_system.py` (unit guards) |
| **Status** | **Partial** — guards correct many drift cases; LLM still authors initial `rolling_state` each turn before merge |

---

### H2: The LLM cannot be the sole author of simulation truth

| Field | Detail |
|-------|--------|
| **Meaning** | Model output is provisional until deterministic layers merge, guard, validate, and persist. |
| **Why** | LLMs omit, contradict, or leak mechanics. |
| **Allowed** | LLM emits `<rolling_state>`, `<ledger>`, `<state>`; backend merges with `consolidate_rolling_state`, applies guards, canonicalizes objects. |
| **Forbidden** | Persisting LLM output without guard pipeline on story turns. |
| **Files** | `server.py` (`story_action`, `new_story`), `memory.py` |
| **Tests** | `verify_p0_object_permanence.py` (merge + canonicalization) |
| **Status** | **Partial** — protected-key union restore and object canonicalization are deterministic; many rolling fields still accept fresh LLM values wholesale |

---

### H3: Engine-only state cannot leak into player-facing text

| Field | Detail |
|-------|--------|
| **Meaning** | Rolls, modifiers, triggers, `rolling_state`, debug payloads, and mechanic labels must not appear in normal play UI. |
| **Why** | Product is hidden-systems narrative; immersion breaks on exposure. |
| **Allowed** | Sanitized paragraphs/choices in chronicle view; dev panel when unlocked. |
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
| **Files** | `server.py` (`insert_one` at lines ~2416, ~2537) |
| **Tests** | No dedicated append-only test found |
| **Status** | **Partial** — normal path appends; `reset_session` and `delete_session` delete turns; session `rolling_state` is overwritten (not event-sourced) |

---

### H5: Narrative must pass through the approved gateway or sanitization path

| Field | Detail |
|-------|--------|
| **Meaning** | Player-visible text flows through `_validate_parsed` (backend) and `sanitizeParagraphs` / `sanitizeChoices` (frontend). API uses `_maybe_sanitise_turn` when `developer_mode` is off. |
| **Why** | Single controlled presentation boundary. |
| **Allowed** | Validated LLM narrative → optional backend strip → frontend presentation filter. |
| **Forbidden** | Bypassing sanitizers for default player views (except intentional dev diagnostics). |
| **Files** | `server.py`, `frontend/src/sanitize.ts`, `frontend/app/play/[id].tsx` |
| **Tests** | `verify_p1_immersion_integrity.py`, `verify_p15_microfixes.py` |
| **Status** | **Enforced** on standard `get_session` / `story_action` responses when `developer_mode` false; **Partial** overall due to `export_session` and unauthenticated API access |

---

### H6: Historical scoring behaviour cannot change accidentally

| Field | Detail |
|-------|--------|
| **Meaning** | If a scoring/ranking subsystem exists, same inputs must yield same rankings across releases. |
| **Why** | Fairness and regression safety for mechanical outcomes. |
| **Allowed** | N/A if no scoring subsystem. |
| **Forbidden** | Silent changes to ranking formulas without versioned decision. |
| **Files** | None found — D20 outcomes are LLM-mediated inside `<debug>` / hidden rolls, not a deterministic scoring module |
| **Tests** | None found |
| **Status** | **N/A** — no historical scoring subsystem in repo. Hidden D20 is prompt-defined, not code-versioned. |

---

### H7: Developer-only information must remain inaccessible to normal players

| Field | Detail |
|-------|--------|
| **Meaning** | `rolling_state`, `debug`, `raw`, internal state keys, and admin diagnostics are dev-only. |
| **Why** | Protect immersion and prevent mechanic gaming. |
| **Allowed** | Full payloads when `developer_mode` true (server) and UI unlock + debug toggles (client). |
| **Forbidden** | Default sessions exposing dev fields; `[DEV_MODE: ON]` without gates. |
| **Files** | `server.py` (`_maybe_sanitise_*`, debug marker in `story_action`), `frontend/app/settings.tsx`, `frontend/app/play/[id].tsx` |
| **Tests** | `test_custom_world_system.py` checks `debug_mode: false` stories omit leaks (integration, needs server) |
| **Status** | **Partial** — API sanitization works when `developer_mode` false; admin/export endpoints expose full data without player auth |

---

## Architectural constraints

May evolve only through an explicit recorded decision in `decision-log.md`.

| ID | Constraint |
|----|------------|
| AC1 | OpenRouter is the sole LLM provider abstraction (`ai_service.py`). Swapping providers requires adapter work, not a runtime plug-in. |
| AC2 | MongoDB is the system of record for sessions and turns. |
| AC3 | `rolling_state` is the compression packet for long-horizon continuity; prompt carries `<prior_state>` plus bounded replay. |
| AC4 | Session-locked `active_model` and `fallback_chain` at story creation. |
| AC5 | Single system prompt document (`STORY_ENGINE_SYSTEM_PROMPT`) defines output tag contract. |
| AC6 | Device `device_id` (client UUID) scopes session listing — not user accounts. |
| AC7 | Admin settings stored in `admin_settings` collection, merged over env defaults. |

---

## Current preferences

Useful choices, not fundamental invariants. May change without ADR if low risk.

| Preference | Current choice | Files |
|------------|----------------|-------|
| Default model | Claude 3.5 Haiku | `ai_config.py` |
| Default mode | `advanced` | `server.py` |
| Memory depth | `3` recent turns replayed | `server.py` |
| Validation retry | Single retry on invalid output | `server.py` `_generate_validated_turn` |
| Typography | Garamond + JetBrains Mono dark theme | `frontend/src/theme.ts` |
| Error copy | User-friendly OpenRouter mapping | `frontend/src/errors.ts` |
| Cost mode | `normal` unless set `low` | `ai_config.py` |

---

## Candidate invariants requiring confirmation

These were suggested by engine design vocabulary but **lack enforcing code** in this repo:

- Actor identity resolution and caps
- Relationship edge directionality enforcement
- Utility AI deterministic decision layer
- Gravity-based memory retention beyond `enforce_context_budget`
- Formal event sourcing with immutable aggregate rebuild
- Numeric scoring with boundary / NaN guards

Do not treat as invariants until implemented and tested.