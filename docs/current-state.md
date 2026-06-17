# Current State Snapshot

**Generated:** 2026-06-17 (reconciled against `emergent` runtime)
**Repository:** `dice-reactions` (FastAPI backend + Expo frontend)
**Git branch:** `emergent` (canonical runtime branch for this documentation pass)

This document is the canonical operational snapshot of the repository **as it exists now** on the `emergent` branch. Claims are tagged by evidence source.

**Evidence tags used throughout:**

| Tag | Meaning |
|-----|---------|
| **Code** | Confirmed by reading runtime source in this repo |
| **Tests** | Confirmed by running or reading test/verification scripts in this session or repo |
| **Docs-claimed** | Stated in `memory/PRD.md`, `AGENTS.md`, or prior `/docs` files but not independently re-verified in this pass |
| **Unknown** | Not determinable from available evidence |

**Planning vs runtime:** `memory/PRD.md` is the planning and Source-of-Truth conformance tracker — not runtime truth. Treat its verification dates and chapter checklists as **Docs-claimed** until re-run against code.

---

## Current runtime stack

| Component | Version / detail | Evidence |
|-----------|------------------|----------|
| Backend | FastAPI 0.110.1, Uvicorn 0.25.0, Python 3.12 (`.venv`) | Code |
| Frontend | Expo ~54, Expo Router ~6, React 19.1, RN 0.81 | Code |
| Database | MongoDB via Motor 3.3.1 | Code |
| LLM | OpenRouter chat completions via `httpx` | Code |
| LLM chokepoint | `gateway.invoke_llm` — sole approved provider call path | Code (`gateway.py`, `server.py`) |
| Default model | `anthropic/claude-3-5-haiku` | Code (`ai_config.py`) |
| Fallback chain | Haiku → Sonnet → Mythomax | Code |

**Branch note:** `main` lacks `gateway.py`, `relationships.py`, and `hud.py`. Prior documentation (pass 1–2) described `main` and was cherry-picked onto `emergent` without re-audit — corrected in this pass.

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

**Docs-claimed:** PRD lists deployment-specific values (`history_window: 22`, `max_tokens: 1536`, `developer_mode: true`) — **not confirmed** against live DB in this pass.

---

## Current implemented systems

| System | Status | Evidence |
|--------|--------|----------|
| Story session CRUD | Implemented | Code (`server.py` routes) |
| Turn generation pipeline | Implemented | Code |
| Anti-Hallucination Gateway | Implemented | Code (`gateway.py`) + Tests (`test_anti_hallucination_gateway.py`, `test_gateway_e2e.py` ✅) |
| LLM chokepoint (`invoke_llm`) | Implemented | Code — all `_generate_turn` / retry calls route through `gateway.invoke_llm` |
| Relationship calculus (NPC→player) | Implemented (partial scope) | Code (`relationships.py`) + Tests (`test_relationship_calculus.py` ✅) |
| HUD shaping (DNG / MOM / PRS) | Implemented | Code (`hud.py`) + Tests (`test_hud.py` ✅) |
| LLM output parsing (`parse_turn`) | Implemented | Code |
| Output validation + single retry | Implemented | Code + Tests (`verify_p1_immersion_integrity.py` ✅) |
| Gateway prose contradiction retry | Implemented | Code (`_full_validate`) + Tests (`test_anti_hallucination_gateway.py` ✅) |
| State supremacy guard (Health/Fatigue) | Implemented | Code + Tests (`test_custom_world_system.py` unit guards — live integration unverified) |
| Object permanence guards | Implemented | Code + Tests (`verify_p0_object_permanence.py` ✅) |
| Rolling memory consolidation | Implemented | Code + Tests (P0 scenarios ✅) |
| Context budget governor | Implemented | Code |
| NPC memory bounds | Implemented | Code + Tests (`verify_p1_immersion_integrity.py` ✅) |
| Faction consequence tick | Implemented | Code + Tests (P1-D ✅) |
| Room audit / known_rooms | Implemented | Code + Tests (P1-C ✅) |
| Custom World seeding | Implemented | Code |
| Curated scenarios (3 presets) | Implemented | Code (`scenarios.py`) |
| Backend player sanitization | Implemented | Code |
| Frontend presentation sanitization | Implemented | Code (`frontend/src/sanitize.ts`, `play/[id].tsx` DNG/MOM/PRS) |
| Admin AI settings (MongoDB-backed) | Implemented | Code |
| Model fallback chain + telemetry | Implemented | Code (`ai_service.py`, called via `gateway.invoke_llm`) |
| Developer unlock (7-tap) + diagnostics UI | Implemented | Code |
| Export session endpoint | Implemented | Code — returns full unsanitized session + turns |
| Reset session endpoint | Implemented | Code — deletes turns, clears rolling state |
| Frontend error mapping | Implemented | Code (`frontend/src/errors.ts`) |

---

## Partially implemented systems

| System | What exists | What is missing / weak | Evidence |
|--------|-------------|------------------------|----------|
| Anti-Hallucination Gateway | PREVENT (`build_immutable_truth_block`), STRIP (`strip_illegal_state_changes`), DETECT (`detect_prose_contradictions`), death/destruction registries | Full Ch 31 conformance not claimed; LLM still proposes initial `rolling_state` each turn | Code + Tests ✅ |
| Relationship calculus | Engine-owned `relationship_vectors` (trust/loyalty/fear/resentment); NPC→player only; event detection + neglect decay; prompt block | No NPC↔NPC edges; no `relationship_threads`-only mode; regex event detection only; `relationship_threads` still seeded separately in Custom World | Code + `test_engine_owns_vectors_ignores_llm_injection` ✅ |
| HUD presentation | `shape_hud` strips Objective; DNG/MOM chips; non-prescriptive PRS pressure | LLM can emit prescriptive pressure before `shape_hud` strips/replaces; frontend renders chips only | Code + `test_hud.py` ✅ |
| Mechanic concealment | Prompt rules, `_validate_parsed`, gateway contradiction retry, backend + frontend sanitizers | LLM can still leak before validation; no continuous live leakage monitor | Code + Tests (P1-A blocks many patterns **in validator**) |
| Relationship threads (legacy schema) | `relationship_threads` in rolling_state, Custom World seeding, protected merge | Superseded for mechanics by `relationship_vectors`; threads not directionality-guarded | Code |
| Turn log / event history | `insert_one` per turn; chronicle replay | No aggregate rebuild; `reset`/`delete` destroy history; `rolling_state` overwritten | Code |
| Long-run compression stress | `compute_compression_metrics`, context trim | No automated 15+ turn test run in this pass | Code; Docs-claimed backlog |
| Provider fallback verification | Fallback chain in code | Deliberate fallback failure test not run in this pass | Docs-claimed backlog |
| Export UX | Backend export + frontend Share hook | No dedicated share-friendly summary view | Code (backend); Docs-claimed P2 |
| Session ownership | `device_id` stored at `new_story`; `list_sessions` filters by `device_id` | `get_session`, `export`, `story_action`, `reset`, `delete`, `mode` do not verify `device_id` | Code — no ownership tests |

---

## Planned or not present (not lost features)

These appear in `memory/PRD.md` or design vocabulary but **have no implementing modules** in this repository. They were never implemented in git history on this repo — do not classify as deleted or incomplete Dice Reactions features.

| System | Status | Evidence |
|--------|--------|----------|
| Utility AI | Planned (PRD Ch 27) — not present | **Code search:** no module |
| Actor resolution / actor caps | Planned (PRD Ch 25) — not present | **Code search:** no dedicated module |
| Gravity / retention governance (beyond context budget) | Planned — partial ad-hoc only | Only `enforce_context_budget` and `consolidate_rolling_state` exist |
| Formal event sourcing | Partial — turn log only | Turns `insert_one`; session `rolling_state` overwritten; no rebuild |
| Historical scoring equivalence | **N/A** — never existed in this repo | `git log -S` empty; no ranking subsystem |
| NaN / infinity input protection for rankings | **N/A** — never existed in this repo | No ranking subsystem |
| Vector retrieval / RAG | Not present | History replay from MongoDB turns only |

---

## Known test failures or tests not run

### Runnable and passed (Tests — 2026-06-17, `emergent`, no live server)

```bash
cd backend
pytest tests/test_anti_hallucination_gateway.py \
       tests/test_relationship_calculus.py \
       tests/test_hud.py \
       tests/test_gateway_e2e.py \
       tests/verify_p0_object_permanence.py \
       tests/verify_p1_immersion_integrity.py \
       tests/verify_p15_microfixes.py -q
# Result: 47 passed
```

### Requires running backend + OpenRouter key (Unverified in this pass)

| Test file | Status | Notes |
|-----------|--------|-------|
| `tests/test_custom_world_system.py` | **Unverified** | Integration tests need live server at `localhost:8000` |
| `tests/test_story_engine.py` | **Unverified** | Docs-claimed outdated vs current Haiku runtime |
| `tests/test_gateway_live_probe.py` | **Unverified** | Live LLM probe |
| `tests/test_relationship_calculus_live.py` | **Unverified** | Live relationship events via export |
| `tests/qa_live_20turn_hostile.py` | **Unverified** | Live 20-turn hostile stress script |
| `tests/qa_live_20turn_full_stack.py` | **Unverified** | Live full-stack stress |
| `tests/qa_live_20turn_p2_stack.py` | **Unverified** | Live P2 stack stress |
| `tests/verify_p2_consequences_rumours.py` | **Unverified** | Hardcoded `/app/backend` path — may not run in local tree |

### Frontend verification

| Command | Status in this pass |
|---------|---------------------|
| `yarn tsc --noEmit` | **Not run** |
| `yarn lint` | **Not run** |

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
| Documentation pass 1–2 authored against `main`, cherry-picked to `emergent` without re-audit | Git history + code diff vs `main` |

---

## Security audit (`emergent` branch)

Re-audited from code review. No dedicated security test suite exists; statuses reflect code evidence unless a test is cited.

| Finding | Status | Evidence |
|---------|--------|----------|
| Admin route authentication | **Not present** | `/api/admin/*` routes (`admin_get_settings`, `admin_post_settings`, `admin_runtime`, `admin_session_diagnostics`, `admin_list_models`) — no auth middleware or API key check (`server.py` ~2359–2477) |
| Export authentication | **Not present** | `export_session` — no auth, no sanitization (`server.py` ~2857–2873) |
| Session ownership (`device_id`) | **Partial** | Enforced: `list_sessions(device_id)`, stored at `new_story`. **Not enforced:** `get_session`, `export_session`, `story_action`, `reset_session`, `delete_session`, `set_session_mode` — `session_id` alone grants access |
| `device_id` enforcement on mutations | **Partial** | Same as ownership — write routes accept `session_id` without matching `device_id` |
| Raw / debug / `rolling_state` exposure | **Partial** | `_maybe_sanitise_turn` / `_sanitise_session_for_player` when `developer_mode` false on `get_session`, `story_action`, `get_latest_turn`, `list_sessions`. **Bypass:** `export_session` always returns full `rolling_state`, `debug`, `raw`; `get_session` returns unsanitized data when `developer_mode` true |
| Developer-mode enforcement | **Partial** | `[DEV_MODE: ON]` requires server `developer_mode` **and** request `debug_mode` (`story_action` ~2706). Toggle via unauthenticated `POST /admin/settings` (`admin_post_settings` ~2458). No test proves auth cannot flip `developer_mode` |

---

## Current highest-priority work

Derived from confirmed gaps (not speculative features):

| Priority | Work | Evidence |
|----------|------|----------|
| P0 | Add real auth or access control for admin + export endpoints | Security audit above |
| P0 | Enforce `device_id` ownership on get/export/action/reset/delete/mode | Security audit above |
| P1 | Run live-server test bundle; update or quarantine outdated tests | Unverified list above |
| P1 | Execute `qa_live_20turn_hostile.py` and PRD P1 stress items | Not run; Docs-claimed backlog |
| P1 | Pin `httpx` in `requirements.txt` | Dependency gap |
| P2 | CI job for 47-test deterministic bundle | Tests passed 2026-06-17 |

---

## Areas that must not be modified casually

| Area | Reason | Files |
|------|--------|-------|
| Guard pipeline order | Deterministic corrections depend on sequence | `backend/server.py` (`new_story`, `story_action` routes) |
| Gateway chokepoint | All LLM calls must route through `invoke_llm` | `backend/gateway.py`, `server.py` `_generate_turn` |
| Protected rolling-state keys | Causal continuity contract | `backend/memory.py` (`relationship_vectors` engine-owned) |
| Player sanitization gates | Prevents mechanic leaks to clients | `server.py` `_maybe_sanitise_*`, `frontend/src/sanitize.ts` |
| System prompt validation rules | Turn shape contract with LLM | `server.py` `STORY_ENGINE_SYSTEM_PROMPT`, `_validate_parsed`, `_full_validate` |
| Session-locked model routing | Continuity across fallback events | `server.py` session fields + `_generate_turn` |
| Object canonicalization | Anti-bloat / contradiction prevention | `memory.canonicalize_object_registry` |
| HUD non-prescriptive contract | DNG/MOM/PRS must not steer player | `backend/hud.py`, `frontend/app/play/[id].tsx` |

---

## Docs-claimed verification (not re-run in this pass)

From `memory/PRD.md` (planning tracker — not runtime truth):

- 3-turn live Haiku verification — **Docs-claimed**
- Browser preview at `chronicle-runtime.preview.emergentagent.com` — **Docs-claimed**, environment-specific
- Play screen mechanic-concealment browser automation — **Docs-claimed**
- Backend regression `30 passed` — **Docs-claimed**, superseded locally by **47 passed** deterministic bundle on `emergent`

Treat PRD verification dates as historical planning reports, not current CI truth.