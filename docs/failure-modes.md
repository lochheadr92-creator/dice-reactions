# Failure Modes

For each mode: detection, prevention, recovery, and **current protection status** based on code/tests on the **`emergent`** branch.

**Protection status:** Protected / Partial / Unprotected / N/A

---

## FM-01: LLM inventing state

| Field | Detail |
|-------|--------|
| **Trigger** | Model emits new `rolling_state` fields, objects, or consequences not grounded in play. |
| **Effect** | Simulation drift; contradictions across turns. |
| **Detection** | Guard adjustment logs; gateway strip messages; player reports; dev panel compare. |
| **Prevention** | `build_immutable_truth_block` in prompt; `strip_illegal_state_changes`; `consolidate_rolling_state` protected keys; object canonicalization; ledger guards. |
| **Recovery** | Guards rewrite parsed turn before persist; contradiction retry; manual session reset. |
| **Files** | `gateway.py`, `memory.py`, `server.py` |
| **Tests** | `verify_p0_object_permanence.py` ✅, `test_anti_hallucination_gateway.py` ✅, `test_gateway_e2e.py` ✅ |
| **Status** | **Partial** — gateway + protected lists merged; many fields still LLM-authored |

---

## FM-02: Hidden mechanics leaking into narration

| Field | Detail |
|-------|--------|
| **Trigger** | Model puts `Roll:`, modifiers, or meta language inside `<narrative>`. |
| **Effect** | Immersion break; players see machinery. |
| **Detection** | `_validate_parsed` regexes; `detect_prose_contradictions`; frontend `MECHANIC_LINE_RE`; manual chronicle review. |
| **Prevention** | System prompt concealment rules; validation retry; `sanitizeParagraphs`. |
| **Recovery** | Retry once (format or hallucination); strip on render; dev fix prompt. |
| **Files** | `server.py`, `gateway.py`, `frontend/src/sanitize.ts` |
| **Tests** | `verify_p1_immersion_integrity.py` (P1-A) ✅, `verify_p15_microfixes.py` ✅ |
| **Status** | **Partial** — validator blocks many cases; not all live LLM outputs tested |

---

## FM-03: Hallucinated inventory or objects

| Field | Detail |
|-------|--------|
| **Trigger** | Model adds items to `ledger` or `inventory_objects` without prior presence. |
| **Effect** | Player gains unearned items. |
| **Detection** | Ledger vs `object_locations` mismatch; room audit drift flags; destruction registry. |
| **Prevention** | Object permanence guards; `update_destruction_registry`; canonical registry. |
| **Recovery** | `_apply_object_permanence`, `_apply_ledger_object_permanence`, gateway strip; manual edit **Unknown** (no admin edit route). |
| **Files** | `server.py`, `memory.py`, `gateway.py` |
| **Tests** | `verify_p0_object_permanence.py` ✅, `test_gateway_e2e.py` ✅ |
| **Status** | **Partial** — dedup/contradiction focus; novel item injection not fully blocked |

---

## FM-04: Destroyed objects reappearing

| Field | Detail |
|-------|--------|
| **Trigger** | Model re-lists destroyed/consumed items as carried. |
| **Effect** | Object permanence violation. |
| **Detection** | P0 scenarios; gateway strip; ledger cross-category check. |
| **Prevention** | Status priority in canonicalization; `strip_illegal_state_changes`; ledger dedup against `object_locations`. |
| **Recovery** | Guards remove duplicate carried rows. |
| **Files** | `server.py`, `memory.py`, `gateway.py` |
| **Tests** | `verify_p0_object_permanence.py` ✅, `test_gateway_e2e.py` ✅ |
| **Status** | **Protected** (deterministic scenarios + gateway e2e) |

---

## FM-05: Duplicate inventory entries

| Field | Detail |
|-------|--------|
| **Trigger** | Label drift creates multiple rows for same object. |
| **Effect** | Memory bloat; contradictory locations. |
| **Detection** | Row count on `object_locations` after N turns. |
| **Prevention** | `canonicalize_object_registry`. |
| **Recovery** | Merge on each turn. |
| **Files** | `memory.py` |
| **Tests** | P0 Scenario 2 (10 cycles) ✅ |
| **Status** | **Protected** (deterministic) |

---

## FM-06: Actor identity confusion

| Field | Detail |
|-------|--------|
| **Trigger** | NPC name variants treated as different actors. |
| **Effect** | Split memory, inconsistent relationships. |
| **Detection** | Manual review of `npc_memory` keys. |
| **Prevention** | **None dedicated** — no actor resolver in code (PRD Ch 25 planned). |
| **Recovery** | **Unknown** |
| **Files** | — |
| **Tests** | — |
| **Status** | **Unprotected** |

---

## FM-07: Relationship drift or LLM vector injection

| Field | Detail |
|-------|--------|
| **Trigger** | Model injects `relationship_vectors` or flips social dynamic without detected events. |
| **Effect** | Social state incoherence; wrong NPC behaviour. |
| **Detection** | `test_engine_owns_vectors_ignores_llm_injection`; dev panel `relationship_vectors` review. |
| **Prevention** | Engine reads prior `relationship_vectors` as authority; `update_relationship_calculus` recomputes from events + decay; protected merge key in `memory.py`. |
| **Recovery** | Deterministic revert on each turn; no NPC↔NPC edge repair. |
| **Files** | `relationships.py`, `memory.py`, `server.py` |
| **Tests** | `test_relationship_calculus.py` ✅ |
| **Status** | **Partial** — NPC→player only; regex event detection; `relationship_threads` not guarded |

---

## FM-08: Retrieval repetition (prompt)

| Field | Detail |
|-------|--------|
| **Trigger** | Same turns replayed; topic ledger exhausted but history repeats. |
| **Effect** | Looping dialogue; wasted tokens. |
| **Detection** | `topic_ledger`, `recent_choice_signatures` in rolling_state; player perception. |
| **Prevention** | Prompt anti-loop rules; `topic_ledger` authoritative pruning. |
| **Recovery** | Context trim drops old messages. |
| **Files** | `server.py` (prompt), `memory.py` |
| **Tests** | `qa_live_20turn_hostile.py` (not run) |
| **Status** | **Partial** |

---

## FM-09: Retrieval starvation (prompt)

| Field | Detail |
|-------|--------|
| **Trigger** | `enforce_context_budget` drops too much history. |
| **Effect** | Model forgets recent causality. |
| **Detection** | `debug` context_budget fields; continuity breaks in play. |
| **Prevention** | Protected recent messages; protected state item count in diagnostics. |
| **Recovery** | Increase budget env vars or reduce `memory_depth`. |
| **Files** | `memory.py`, `ai_config.py` |
| **Tests** | None dedicated |
| **Status** | **Partial** |

---

## FM-10: Prose contradicting immutable truth

| Field | Detail |
|-------|--------|
| **Trigger** | Model narrates using destroyed objects, deceased NPCs, or illegal state despite truth block. |
| **Effect** | Player sees impossible actions; immersion break. |
| **Detection** | `detect_prose_contradictions` in `_full_validate`. |
| **Prevention** | `build_immutable_truth_block` in prompt; single retry with hallucination hint. |
| **Recovery** | Retry turn; if still failing, HTTP 502. |
| **Files** | `gateway.py`, `server.py` |
| **Tests** | `test_anti_hallucination_gateway.py` ✅ |
| **Status** | **Partial** — retry once; regex/heuristic detection only |

---

## FM-11: HUD steering player toward objectives

| Field | Detail |
|-------|--------|
| **Trigger** | Model emits Objective/Goal chips or prescriptive Pressure text. |
| **Effect** | Quest-marker UX; reduces emergent play. |
| **Detection** | `hud._PRESCRIPTIVE_RE`; frontend chip inspection. |
| **Prevention** | `shape_hud` strips Objective/Goal; `derive_pressure` rejects prescriptive phrases. |
| **Recovery** | Engine overwrites DNG/MOM; replaces or drops PRS. |
| **Files** | `hud.py`, `frontend/app/play/[id].tsx` |
| **Tests** | `test_hud.py` ✅ |
| **Status** | **Protected** (deterministic unit tests) |

---

## FM-12: Event sequence or ordering drift

| Field | Detail |
|-------|--------|
| **Trigger** | Turns fetched out of order; concurrent writes **Unknown**. |
| **Effect** | Wrong chronicle display. |
| **Detection** | `sort("turn_number", 1)` on queries. |
| **Prevention** | Monotonic `turn_number` increment in code. |
| **Recovery** | Re-fetch session. |
| **Files** | `server.py` |
| **Tests** | `test_story_engine.py` (ordering assertion — not run) |
| **Status** | **Partial** — single-writer assumed; no concurrency tests |

---

## FM-13: Invalid model fallback

| Field | Detail |
|-------|--------|
| **Trigger** | Primary model 404/429/402; all fallbacks fail. |
| **Effect** | 502 to client; turn not created. |
| **Detection** | `AIServiceError`; `fallback_events` in meta; `friendlyError` on client. |
| **Prevention** | Fallback chain via `gateway.invoke_llm`; retries with backoff. |
| **Recovery** | User switches model in Settings; add credits. |
| **Files** | `ai_service.py`, `gateway.py`, `frontend/src/errors.ts` |
| **Tests** | PRD P1 deliberate fallback drill (not run) |
| **Status** | **Partial** |

---

## FM-14: Developer data exposure

| Field | Detail |
|-------|--------|
| **Trigger** | `developer_mode` true; export endpoint; unauthenticated admin access. |
| **Effect** | Full `rolling_state`, `debug`, `raw`, relationship numbers exposed. |
| **Detection** | API response inspection. |
| **Prevention** | `_maybe_sanitise_*` when `developer_mode` false on player routes. |
| **Recovery** | Set `developer_mode` false; restrict network. |
| **Files** | `server.py`, `export_session` |
| **Tests** | None for export |
| **Status** | **Partial** — player routes protected when `developer_mode` false; export/admin weak |

---

## FM-15: Admin endpoints lacking real authentication

| Field | Detail |
|-------|--------|
| **Trigger** | Any client calls `/api/admin/*` or toggles settings. |
| **Effect** | Model/cost/dev mode changed; potential abuse. |
| **Detection** | Audit `admin_settings` collection. |
| **Prevention** | **None in code** — UI gating only. |
| **Recovery** | Restore settings via MongoDB or Settings UI. |
| **Files** | `server.py` admin routes |
| **Tests** | None |
| **Status** | **Unprotected** |

---

## FM-16: Session hijack via leaked `session_id`

| Field | Detail |
|-------|--------|
| **Trigger** | Attacker obtains UUID; calls get/export/action without matching `device_id`. |
| **Effect** | Read or mutate another device's chronicle. |
| **Detection** | Code review of route handlers. |
| **Prevention** | **Partial** — only `list_sessions` scopes by `device_id`. |
| **Recovery** | Rotate session IDs **Unknown** (not implemented). |
| **Files** | `server.py` |
| **Tests** | None |
| **Status** | **Unprotected** on get/export/action/reset/delete |

---

## FM-17: Configuration values differing (code vs DB vs env)

| Field | Detail |
|-------|--------|
| **Trigger** | `admin_settings` overrides env; PRD documents deployment-specific values. |
| **Effect** | Docs/ops mismatch; debugging confusion. |
| **Detection** | Compare `/api/health` vs `ai_config.py` defaults. |
| **Prevention** | Document source-of-truth order: DB > env > code defaults. |
| **Recovery** | `GET /admin/settings`; reset DB document. |
| **Files** | `server.py` `get_ai_settings`, `ai_config.py` |
| **Tests** | None |
| **Status** | **Partial** — health endpoint exposes effective settings |

---

## FM-18: Export/reset schema mismatch

| Field | Detail |
|-------|--------|
| **Trigger** | Client expects different export shape; reset without re-seed. |
| **Effect** | Broken share UX; empty chronicle after reset. |
| **Detection** | Contract tests **missing**. |
| **Prevention** | Documented schema in `api.md`. |
| **Recovery** | `new_story` or first `story_action` after reset. |
| **Files** | `server.py`, `frontend/app/play/[id].tsx` |
| **Tests** | None |
| **Status** | **Partial** — code documented; no automated contract test |

---

## FM-19: Stale documentation treated as runtime truth

| Field | Detail |
|-------|--------|
| **Trigger** | Docs authored against `main` cherry-picked to `emergent` without re-audit; PRD dates pass. |
| **Effect** | False confidence; missing gateway/relationship/HUD in operational docs. |
| **Detection** | `current-state.md` evidence tags; branch note in `change-history.md`. |
| **Prevention** | Treat `memory/PRD.md` as planning only; re-run 47-test bundle on `emergent`. |
| **Recovery** | This reconciliation pass (2026-06-17). |
| **Files** | `memory/PRD.md`, `/docs/*` |
| **Tests** | `release-checklist.md` |
| **Status** | **Partial** — addressed by emergent reconciliation pass |

---

## Removed from catalogue (N/A)

FM entries for **exact scoring boundary drift** and **NaN/infinity corrupting rankings** are **N/A** — no scoring/ranking subsystem ever existed in this repository. Do not track as Dice Reactions failure modes.