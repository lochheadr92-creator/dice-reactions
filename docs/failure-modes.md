# Failure Modes

For each mode: detection, prevention, recovery, and **current protection status** based on code/tests in this repo.

**Protection status:** Protected / Partial / Unprotected / N/A

---

## FM-01: LLM inventing state

| Field | Detail |
|-------|--------|
| **Trigger** | Model emits new `rolling_state` fields, objects, or consequences not grounded in play. |
| **Effect** | Simulation drift; contradictions across turns. |
| **Detection** | Guard adjustment logs; player reports; compare `rolling_state` across turns in dev panel. |
| **Prevention** | `consolidate_rolling_state` restores protected unresolved keys; object canonicalization; ledger guards. |
| **Recovery** | Guards rewrite parsed turn before persist; manual session reset. |
| **Files** | `memory.py`, `server.py` |
| **Tests** | `verify_p0_object_permanence.py` |
| **Status** | **Partial** — protected lists merged; many fields still LLM-authored |

---

## FM-02: Hidden mechanics leaking into narration

| Field | Detail |
|-------|--------|
| **Trigger** | Model puts `Roll:`, modifiers, or meta language inside `<narrative>`. |
| **Effect** | Immersion break; players see machinery. |
| **Detection** | `_validate_parsed` regexes; frontend `MECHANIC_LINE_RE`; manual chronicle review. |
| **Prevention** | System prompt concealment rules; validation retry; `sanitizeParagraphs`. |
| **Recovery** | Retry once; strip on render; dev fix prompt. |
| **Files** | `server.py`, `frontend/src/sanitize.ts` |
| **Tests** | `verify_p1_immersion_integrity.py` (P1-A), `verify_p15_microfixes.py` |
| **Status** | **Partial** — validator blocks many cases; not all live LLM outputs tested |

---

## FM-03: Hallucinated inventory or objects

| Field | Detail |
|-------|--------|
| **Trigger** | Model adds items to `ledger` or `inventory_objects` without prior presence. |
| **Effect** | Player gains unearned items. |
| **Detection** | Ledger vs `object_locations` mismatch; room audit drift flags. |
| **Prevention** | Object permanence guards; canonical registry. |
| **Recovery** | `_apply_object_permanence`, `_apply_ledger_object_permanence`; manual edit **Unknown** (no admin edit route). |
| **Files** | `server.py`, `memory.py` |
| **Tests** | `verify_p0_object_permanence.py` |
| **Status** | **Partial** — dedup/contradiction focus; novel item injection not fully blocked |

---

## FM-04: Destroyed objects reappearing

| Field | Detail |
|-------|--------|
| **Trigger** | Model re-lists destroyed/consumed items as carried. |
| **Effect** | Object permanence violation. |
| **Detection** | P0 scenarios; ledger cross-category check. |
| **Prevention** | Status priority in canonicalization; ledger dedup against `object_locations`. |
| **Recovery** | Guards remove duplicate carried rows. |
| **Files** | `server.py`, `memory.py` |
| **Tests** | `verify_p0_object_permanence.py` ✅ |
| **Status** | **Protected** (deterministic scenarios) |

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
| **Prevention** | **None dedicated** — no actor resolver in code. |
| **Recovery** | **Unknown** |
| **Files** | — |
| **Tests** | — |
| **Status** | **Unprotected** |

---

## FM-07: Relationship direction reversal

| Field | Detail |
|-------|--------|
| **Trigger** | Model flips trust/debt dynamic without cause. |
| **Effect** | Social state incoherence. |
| **Detection** | Dev panel `relationship_threads` review. |
| **Prevention** | Protected merge keeps threads; no directionality guard. |
| **Recovery** | LLM-only; no deterministic revert. |
| **Files** | `memory.py` (protected key), prompt schema in `server.py` |
| **Tests** | None |
| **Status** | **Unprotected** |

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

## FM-10: Exact scoring boundary drift

| Field | Detail |
|-------|--------|
| **Trigger** | N/A — no code scoring subsystem. |
| **Effect** | N/A |
| **Detection** | N/A |
| **Prevention** | N/A |
| **Recovery** | N/A |
| **Files** | — |
| **Tests** | — |
| **Status** | **N/A** |

---

## FM-11: NaN or infinity corrupting rankings

| Field | Detail |
|-------|--------|
| **Trigger** | N/A — no ranking subsystem. |
| **Effect** | N/A |
| **Files** | — |
| **Tests** | — |
| **Status** | **N/A** |

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
| **Prevention** | Fallback chain; retries with backoff. |
| **Recovery** | User switches model in Settings; add credits. |
| **Files** | `ai_service.py`, `frontend/src/errors.ts` |
| **Tests** | PRD P1 deliberate fallback drill (not run) |
| **Status** | **Partial** |

---

## FM-14: Developer data exposure

| Field | Detail |
|-------|--------|
| **Trigger** | `developer_mode` true; export endpoint; unauthenticated admin access. |
| **Effect** | Full `rolling_state`, `debug`, `raw` exposed. |
| **Detection** | API response inspection. |
| **Prevention** | `_maybe_sanitise_*` when `developer_mode` false. |
| **Recovery** | Set `developer_mode` false; restrict network. |
| **Files** | `server.py`, `export_session` |
| **Tests** | None for export |
| **Status** | **Partial** — player routes protected; export/admin weak |

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

## FM-16: Configuration values differing (code vs DB vs env)

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

## FM-17: Export/reset schema mismatch

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

## FM-18: Stale documentation treated as runtime truth

| Field | Detail |
|-------|--------|
| **Trigger** | PRD verification dates pass; code changes; tests not re-run. |
| **Effect** | False confidence in release readiness. |
| **Detection** | `current-state.md` evidence tags; this doc set. |
| **Prevention** | Separate Docs-claimed vs Code/Tests tags; `change-history.md`. |
| **Recovery** | Re-run verification scripts and update docs. |
| **Files** | `memory/PRD.md`, `/docs/*` |
| **Tests** | `release-checklist.md` |
| **Status** | **Partial** — addressed by this documentation spine |