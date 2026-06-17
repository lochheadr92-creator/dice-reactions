# Current State Snapshot

**Generated:** 2026-06-17  
**Repository:** `dice-reactions` (FastAPI backend + Expo frontend)  
**Git branch:** `main` (per last inspection)

This document is the canonical operational snapshot of the repository **as it exists now**. Claims are tagged by evidence source.

**Evidence tags used throughout:**

| Tag | Meaning |
|-----|---------|
| **Code** | Confirmed by reading runtime source in this repo |
| **Tests** | Confirmed by running or reading test/verification scripts in this session or repo |
| **Docs-claimed** | Stated in `memory/PRD.md`, `AGENTS.md`, or prior `/docs` files but not independently re-verified in this pass |
| **Unknown** | Not determinable from available evidence |

---

## Current runtime stack

| Component | Version / detail | Evidence |
|-----------|------------------|----------|
| Backend | FastAPI 0.110.1, Uvicorn 0.25.0, Python 3.12 (`.venv`) | Code |
| Frontend | Expo ~54, Expo Router ~6, React 19.1, RN 0.81 | Code |
| Database | MongoDB via Motor 3.3.1 | Code |
| LLM | OpenRouter chat completions via `httpx` | Code |
| Default model | `anthropic/claude-3-5-haiku` | Code (`ai_config.py`) |
| Fallback chain | Haiku → Sonnet → Mythomax | Code |

---

## Important configuration defaults

### Environment defaults (Code)

| Variable | Default | File |
|----------|---------|------|
| `DEFAULT_MODEL` | `anthropic/claude-3-5-haiku` | `backend/ai_config.py` |
| `DEFAULT_MAX_TOKENS` | `2048` | `backend/ai_service.py` |
| `DEFAULT_HISTORY_WINDOW` | `40` | `backend/ai_service.py` |
| `DEFAULT_MEMORY_DEPTH` | `3` | `backend/server.py` |
| `DEFAULT_MODE` | `advanced` | `backend/server.py` |
| `MAX_RETRIES` | `2` per model | `backend/ai_config.py` |
| `PROVIDER_TIMEOUT` | `180` s | `backend/ai_config.py` |
| `ENABLE_DEBUG_PANEL` | `true` | `backend/ai_config.py` |
| `developer_mode` (admin settings) | `false` | `backend/server.py` (`get_ai_settings`) |
| `CORS_ORIGINS` | `*` | `backend/server.py` |
| `EXPO_PUBLIC_BACKEND_URL` | `http://localhost:8000` | `frontend/.env` |

### Database overrides (Code)

`admin_settings` collection (`key: "ai_settings"`) merges over env defaults via `get_ai_settings()`. Active deployment values may differ from code defaults without being visible in git.

**Docs-claimed:** PRD lists `history_window: 22`, `max_tokens: 1536`, `developer_mode: true` for last verified deployment — **not confirmed** against live DB in this pass.

---

## Current implemented systems

| System | Status | Evidence |
|--------|--------|----------|
| Story session CRUD | Implemented | Code (`server.py` routes) |
| Turn generation pipeline | Implemented | Code |
| LLM output parsing (`parse_turn`) | Implemented | Code |
| Output validation + single retry | Implemented | Code + Tests (`verify_p1_immersion_integrity.py`) |
| State supremacy guard (Health/Fatigue) | Implemented | Code + Tests (`test_custom_world_system.py` unit tests) |
| Object permanence guards | Implemented | Code + Tests (`verify_p0_object_permanence.py` **passed** 2026-06-17) |
| Rolling memory consolidation | Implemented | Code + Tests (P0 scenarios) |
| Context budget governor | Implemented | Code |
| NPC memory bounds | Implemented | Code + Tests (`verify_p1_immersion_integrity.py` **passed**) |
| Faction consequence tick | Implemented | Code + Tests (P1-D **passed**) |
| Room audit / known_rooms | Implemented | Code + Tests (P1-C **passed**) |
| Custom World seeding | Implemented | Code |
| Curated scenarios (3 presets) | Implemented | Code (`scenarios.py`) |
| Backend player sanitization | Implemented | Code |
| Frontend presentation sanitization | Implemented | Code (`frontend/src/sanitize.ts`) |
| Admin AI settings (MongoDB-backed) | Implemented | Code |
| Model fallback chain + telemetry | Implemented | Code (`ai_service.py`) |
| Developer unlock (7-tap) + diagnostics UI | Implemented | Code |
| Export session endpoint | Implemented | Code — returns full session + turns |
| Reset session endpoint | Implemented | Code — deletes turns, clears rolling state |
| Frontend error mapping | Implemented | Code (`frontend/src/errors.ts`) |

---

## Partially implemented systems

| System | What exists | What is missing / weak | Evidence |
|--------|-------------|------------------------|----------|
| Mechanic concealment | Prompt rules, `_validate_parsed`, backend + frontend sanitizers | LLM can still leak before validation; no continuous live leakage monitor | Code + Tests (P1-A blocks many patterns **in validator**) |
| Relationship state | `relationship_threads` in rolling_state, Custom World seeding, protected merge | No deterministic guard for directionality or consistency vs `npc_memory` | Code |
| Long-run compression stress | `compute_compression_metrics`, context trim | No automated 15+ turn test run in this pass | Code; Docs-claimed backlog |
| Provider fallback verification | Fallback chain in code | Deliberate fallback failure test not run in this pass | Docs-claimed backlog |
| Export UX | Backend export + frontend Share hook | No dedicated share-friendly summary view | Code (backend); Docs-claimed P2 |

---

## Unverified systems (not found in code)

These appear in the documentation task brief or similar engine designs but **have no implementing modules** in this repository:

| System | Evidence |
|--------|----------|
| Utility AI | **Code search:** no matches in backend |
| Actor resolution / actor caps | **Code search:** no dedicated module |
| Formal event sourcing | Turns are `insert_one`; session `rolling_state` is overwritten; `reset`/`delete` remove history |
| Gravity / retention governance (beyond context budget) | Only `enforce_context_budget` and `consolidate_rolling_state` exist |
| Historical scoring equivalence | No scoring/ranking subsystem found in `server.py` |
| NaN / infinity input protection for rankings | No ranking subsystem found |
| Vector retrieval / RAG | No retrieval layer; history replay from MongoDB turns |

Mark these **Unknown / not present** unless future code adds them.

---

## Known test failures or tests not run

### Runnable and passed (Tests — 2026-06-17)

```bash
cd backend
python tests/verify_p0_object_permanence.py    # ALL 4 scenarios PASSED
python tests/verify_p1_immersion_integrity.py  # ALL 4 scenarios PASSED
python tests/verify_p15_microfixes.py        # ALL 4 scenarios PASSED
```

### Requires running backend + OpenRouter key

| Test file | Status in this pass | Notes |
|-----------|---------------------|-------|
| `tests/test_custom_world_system.py` | **Setup errors** (connection refused `localhost:8000`) | 3 integration tests need live server; unit-style tests in same file may pass offline |
| `tests/test_story_engine.py` | **Not run** | Docs-claimed outdated vs current Haiku runtime |
| `tests/qa_live_20turn_hostile.py` | **Not run** | Live 20-turn hostile stress script |

### Frontend verification

| Command | Status in this pass |
|---------|---------------------|
| `yarn tsc --noEmit` | **Not run** in this pass |
| `yarn lint` | **Not run** in this pass |

**Docs-claimed:** PRD reports `yarn tsc --noEmit` passed and `30 passed` pytest during Custom World upgrade — **not re-run** here.

---

## Known technical debt

| Item | Evidence |
|------|----------|
| `test_story_engine.py` outdated assertions | Code + `AGENTS.md` + PRD |
| `test_story_engine.py` flake8 `E741` | Docs-claimed (PRD) |
| `httpx` not pinned in `requirements.txt` | Code (`ai_service.py` imports it) |
| `emergentintegrations` in requirements, unused in inspected modules | Code search |
| FastAPI `@app.on_event("shutdown")` deprecated | Tests warnings when importing `server` |
| No MongoDB indexes defined in code | Code |
| No CI/CD manifest in repo | Code search |
| `frontend/package-lock.json` dirty in working tree (pre-existing) | Git status — not modified in doc passes |

---

## Active security concerns

| Concern | Severity | Evidence |
|---------|----------|----------|
| Admin endpoints (`/api/admin/*`) have **no authentication** | High | Code — UI-gated only |
| Session access by `session_id` without device ownership check on all routes | Medium | Code — `get_session` does not verify `device_id` |
| `CORS_ORIGINS=*` default | Medium | Code |
| `developer_mode` toggled via unauthenticated POST | Medium | Code |
| Export returns **full unsanitized** session + turns including `rolling_state`, `debug`, `raw` | Medium | Code (`export_session` — no `_maybe_sanitise`) |
| OpenRouter API key in `backend/.env` | Operational | Code |

---

## Current highest-priority work

Derived from confirmed gaps (not speculative features):

| Priority | Work | Evidence |
|----------|------|----------|
| P0 | Add real auth or access control for admin + export endpoints | Security review above |
| P1 | Run `test_custom_world_system.py` and `test_story_engine.py` against live backend; update or quarantine outdated tests | Test run failure this pass |
| P1 | Execute `qa_live_20turn_hostile.py` and PRD P1 stress items | Not run; Docs-claimed backlog |
| P1 | Pin `httpx` in `requirements.txt` | Dependency gap |
| P2 | Resolve `api.md` / deployment default contradictions via documented source-of-truth rules | Docs inconsistency |

---

## Areas that must not be modified casually

| Area | Reason | Files |
|------|--------|-------|
| Guard pipeline order | Deterministic corrections depend on sequence | `backend/server.py` (`new_story`, `story_action` routes) |
| Protected rolling-state keys | Causal continuity contract | `backend/memory.py` |
| Player sanitization gates | Prevents mechanic leaks to clients | `server.py` `_maybe_sanitise_*`, `frontend/src/sanitize.ts` |
| System prompt validation rules | Turn shape contract with LLM | `server.py` `STORY_ENGINE_SYSTEM_PROMPT`, `_validate_parsed` |
| Session-locked model routing | Continuity across fallback events | `server.py` session fields + `_generate_turn` |
| Object canonicalization | Anti-bloat / contradiction prevention | `memory.canonicalize_object_registry` |

---

## Docs-claimed verification (not re-run in this pass)

From `memory/PRD.md` (2026-05-27 and Custom World upgrade):

- 3-turn live Haiku verification — **Docs-claimed**
- Browser preview at `chronicle-runtime.preview.emergentagent.com` — **Docs-claimed**, environment-specific
- Play screen mechanic-concealment browser automation — **Docs-claimed**
- Backend regression `30 passed` — **Docs-claimed**, not reproduced here

Treat these as historical reports, not current CI truth.