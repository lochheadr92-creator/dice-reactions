# Current State Snapshot

**Generated:** 2026-06-25 (reconciled against `emergent` runtime @ `cf2329d`)
**Repository:** `dice-reactions` (FastAPI backend + Expo frontend)
**Git branch:** `emergent` (canonical runtime branch for this documentation pass)

This document is the canonical operational snapshot of the repository **as it exists now** on the `emergent` branch. Claims are tagged by evidence source.

**Operational source authority:** runtime code and passing tests on `emergent` outrank this snapshot, followed by `system-doctrine.md`, `failure-modes.md`, `feature-status.md`, `decision-log.md` and accepted ADRs, verification evidence, then agent summaries and chat handoffs. Feature branches remain proposals until merged. Agent summaries and old PR descriptions cannot promote a feature or override runtime/test evidence.

**Evidence tags used throughout:**

| Tag | Meaning |
|-----|---------|
| **Code** | Confirmed by reading runtime source in this repo |
| **Tests** | Confirmed by running or reading test/verification scripts in this session or repo |
| **Docs-claimed** | Stated in `memory/PRD.md`, `AGENTS.md`, or prior `/docs` files but not independently re-verified in this pass |
| **Unknown** | Not determinable from available evidence |

**Planning vs runtime:** `memory/PRD.md` is the planning and Source-of-Truth conformance tracker — not runtime truth. Treat its verification dates and chapter checklists as **Docs-claimed** until re-run against code. The PRD contains duplicate Chapter 29 entries with contradictory completion status — treat the chapter matrix in this pass as authoritative over stale PRD rows.

---

## Bible implementation reality (2026-06-24 reconciliation)

| Item | `emergent` HEAD | `recovery/living-cast-working-tree` |
|------|-----------------|-------------------------------------|
| Git ref | `cf2329d` | `4dadb3feb3737b28a4e5fbb1ef71aa0d56b365a5` |
| Merge status | Canonical runtime branch | **Unmerged** — not deployed |
| CI coverage | Deterministic CI on `emergent` only | **Not covered by emergent CI** |
| Living Cast | **Present & live on `emergent`** -- `npc_agendas.py`, `npc_world_moves.py`, `arc_diversity.py`, `consequence_echoes.py`, `living_cast_*` merged; wired into the live turn path (`replayability.prepare_action_turn` -> `select_npc_move`/`commit_npc_move`). Remains a **local substitute** for full PRD Ch 25 Actor Resolution; ADR-024 supplies the Utility AI scoring bridge. | Superseded -- merged to `emergent` |
| Actor Resolution / Utility AI | ADR-024 Phase 1 and NW-UTILITY-01 are complete. `ENABLE_UTILITY_AI_LIVE_SELECTION` exposes feature-gated live selection and defaults OFF. Shadow comparison always calls `utility_ai.select_action` over the eligible `npc_world_moves` candidate set; flag ON hands an authorised Utility AI winner to the unchanged commit path. Deterministic backend proof now covers eligible candidate generation, agreement and disagreement handoff paths, and committed receipts matching the Utility AI winner; live LLM gameplay validation remains separate. Utility AI remains `TURN_INTEGRATION_UNVERIFIED`; full PRD Ch 25 Actor Resolution remains incomplete. | Merged to `emergent` |
| World execution mode | `TURN_COUPLED_AUTONOMY_ONLY` | Same (turn-coupled; no offline sim) |
| Event sourcing | Turn log only on `emergent` HEAD | **LOCAL SUBSTITUTE** — bounded transition receipts provide idempotency and causal pointers but do not provide canonical reconstruction or durable complete event history; **DEFERRED** — full contract unavailable beyond PRD summary |
| Pressure authority | **ADR-023 complete** — `replayability_state.pressure_graph` is canonical; `rolling_state.active_pressures` is a derived, engine-owned projection | Recovery branch superseded by canonical `emergent` implementation |
| Relationship provenance | **Unresolved** — vectors mutated from player intent + generated prose | Same blocker; blocks merge |
| Feature development | **Frozen** | Recovery work is provisional; not merge-ready |
| Golden-path blockers | Relationship provenance | Same |

**Bible text in repository:** Chapters 1–21 full text in `memory/DESIGN_BIBLE.txt`. Chapters 22–32 have **PRD tracker summaries only** — full Chapter 22–32 conformance is **unverified**. Chapter 26 is a **PRD extension associated with Chapter 20**, not a recovered standalone Bible chapter.

**Weighted verified-contract coverage (audit formula; not feature quality):**

| Branch | Calculation | Result |
|--------|-------------|--------|
| `emergent` HEAD | 16 PARTIAL × 0.5 = 8.0 → 8.0 / 21 | **38.1%** |
| `recovery/living-cast-working-tree` | 15 PARTIAL × 0.5 + 1 LOCAL SUBSTITUTE × 0.35 = 7.85 → 7.85 / 21 | **37.4%** |

Do **not** report 39.8%. The chapter matrix remains authoritative.

---

## Current runtime stack

| Component | Version / detail | Evidence |
|-----------|------------------|----------|
| Backend | FastAPI 0.110.1, Uvicorn 0.25.0, Python 3.12 (`.venv`) | Code |
| Frontend | Expo ~54, Expo Router ~6, React 19.1, RN 0.81 | Code |
| Database | MongoDB via Motor 3.3.1 | Code |
| LLM | OpenRouter chat completions via `httpx` | Code |
| LLM chokepoint | `gateway.invoke_llm` — sole approved provider call path | Code (`gateway.py`, `server.py`) |
| Default model | `anthropic/claude-haiku-4.5` | Code (`ai_config.py`) |
| Fallback chain | Haiku 4.5 → Sonnet 4.5 → Mythomax | Code |

**Branch note:** `main` lacks `gateway.py`, `relationships.py`, and `hud.py`. Prior documentation (pass 1–2) described `main` and was cherry-picked onto `emergent` without re-audit — corrected in this pass.

---

## Important configuration defaults

### Environment defaults (Code)

| Variable | Default | File |
|----------|---------|------|
| `DEFAULT_MODEL` | `anthropic/claude-haiku-4.5` | `backend/ai_config.py` |
| `DEFAULT_MAX_TOKENS` | `2048` | `backend/ai_service.py` |
| `DEFAULT_HISTORY_WINDOW` | `40` | `backend/ai_service.py` |
| `DEFAULT_MEMORY_DEPTH` | `3` | `backend/server.py` |
| `DEFAULT_MODE` | `advanced` | `backend/server.py` |
| `MAX_RETRIES` | `2` per model | `backend/ai_config.py` |
| `PROVIDER_TIMEOUT` | `180` s | `backend/ai_config.py` |
| `ENABLE_DEBUG_PANEL` | `true` | `backend/ai_config.py` |
| `ENABLE_UTILITY_AI_LIVE_SELECTION` | `false` | `backend/ai_config.py` |
| `developer_mode` (admin settings) | `false` | `backend/server.py` (`get_ai_settings`) |
| `ADMIN_API_KEY` | unset unless configured in deployment | `backend/security.py` — required for admin routes |
| `CORS_ORIGINS` | `*` | `backend/server.py` |
| `ACTION_LOCK_LEASE_SEC` | `600` (clamped 60–3600) | `backend/action_concurrency.py` |
| `EXPO_PUBLIC_BACKEND_URL` | `http://localhost:8000` | `frontend/.env` |

### Database overrides (Code)

`admin_settings` collection (`key: "ai_settings"`) merges over env defaults via `get_ai_settings()`. Active deployment values may differ from code defaults without being visible in git.

**Docs-claimed:** PRD lists deployment-specific values (`history_window: 22`, `max_tokens: 1536`, `developer_mode: true`) — **not confirmed** against live DB in this pass.

---

## Current implemented systems

| System | Status | Evidence |
|--------|--------|----------|
| Story session CRUD | Implemented | Code (`server.py` routes) |
| Early-Game Pacing Governor v1 | Implemented (deterministic structural Stage 1) | Code (`pacing.py`) + Tests (`test_early_game_pacing.py` ✅) |
| Replayability Engine v1 | Implemented (deterministic — session `replayability_state`); ADR-023 pressure authority complete | Code (`replayability.py`, `run_identity.py`, `opening_state.py`, `pressure_graph.py`, `consequence_echoes.py`) + Tests (`test_run_identity.py`, `test_opening_state.py`, `test_pressure_graph.py`, `test_consequence_echoes.py`, `test_replayability_integration.py` ✅) |
| P1 actor stress substrate | **Canonical — `TURN_INTEGRATION_VERIFIED` / `UTILITY_STRESS_INPUT_COMPLETE`** | Code (`stress.py`, `foundation_snapshot.py`, `replayability.py`, `server.py`) + Tests (`test_stress.py`, `test_stress_integration.py`) |
| Foundation Utility AI | **ADR-024 Phase 1 + NW-UTILITY-01 complete; deterministic live-handoff proof complete; feature-gated live selection available; default OFF; `TURN_INTEGRATION_UNVERIFIED`** — shadow comparison remains active in both modes; authorised band-aware Utility AI winners drive NPC choice only when enabled | Code (`ai_config.py`, `utility_ai.py`, `living_cast_shadow.py`, `replayability.py`) + Tests (foundation acceptance / utility / `test_living_cast_shadow` agreement + disagreement live-handoff proof / Living Cast integration) |
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
| Context budget governor | Implemented — prompt-only `<prior_state>` projection caps added (persisted state untouched); live 20-turn verification pending | Code (`memory.enforce_context_budget`, `memory._compress_prior_state_json_with_meta`) + Tests (`test_context_budget.py` ✅) |
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
| Session ownership enforcement | Implemented | Code (`security.fetch_owned_session`) + Tests (`test_security.py` ✅) |
| Admin API key authentication | Implemented | Code (`security.require_admin`) + Tests (`test_security.py` ✅) |
| Player-safe export | Implemented | Code — sanitised export; Tests (`test_security.py` ✅) |
| Raw administrative export | Implemented | Code — `/export/raw` + admin key + ownership; Tests ✅ |
| Reset session endpoint | Implemented | Code — deletes turns, clears rolling state and `replayability_state` |
| Frontend error mapping | Implemented | Code (`frontend/src/errors.ts`) |

---

### P1 stress canonical status

P1 stress is canonical on `emergent` as of merge commit `5c042fb`, with runtime status **`TURN_INTEGRATION_VERIFIED`** and Utility input status **`UTILITY_STRESS_INPUT_COMPLETE`**. Actor stress is deterministic, persisted in `rolling_state["actor_stress"]`, and engine-owned across model consolidation. When authoritative stress values are present, stress and capacity are committed into foundation snapshot identity.

The accepted P1 update scope is **living actors with active agendas only**. Widening to all scene-present actors is deferred to a separate future design decision. Utility AI remains shadow-evaluated on every eligible turn and can drive the existing NPC commit path only when `ENABLE_UTILITY_AI_LIVE_SELECTION=true`; the default is false. Deterministic tests now prove candidate generation plus agreement and disagreement live handoff, including committed receipts matching the Utility AI winner. Live LLM gameplay validation remains separate, so live turn integration remains unverified.

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
| Device-scoped isolation | Not full user accounts | UUID `device_id` only; no login, password reset, or cross-device recovery | By design (P0 increment scope) |

---

## Planned or not present (not lost features)

These appear in `memory/PRD.md` or design vocabulary but **have no implementing modules** in this repository. They were never implemented in git history on this repo — do not classify as deleted or incomplete Dice Reactions features.

| System | Status | Evidence |
|--------|--------|----------|
| Actor resolution / actor caps | **Canonical module present as shadow** — `actor_resolution.py` (tiers, ceilings, demotion grace, acting set) runs every turn via `foundation_integration`. Flag-promotable to authoritative via `ENABLE_CANONICAL_ACTOR_RESOLUTION` (default OFF). `npc_world_moves.resolve_actor_tier` remains the legacy fallback. Grace still uses the `turn × 60` proxy (`D_GRACE`). | **Code:** `actor_resolution.py`, `foundation_integration.py`, `foundation_promotion.py`; see `docs/foundation-promotion.md` |
| Gravity / retention governance (beyond context budget) | **Canonical module present as shadow** — `gravity_governance.py` (retention score, bands, protected set) runs every turn via `foundation_integration`. Flag-promotable to authoritative over the `npc_memory` prompt projection via `ENABLE_CANONICAL_GRAVITY` (default OFF); persisted state untouched. Legacy `enforce_context_budget`/`consolidate_rolling_state` remain the fallback. | **Code:** `gravity_governance.py`, `foundation_promotion.py`, `memory.py`; see `docs/foundation-promotion.md` |
| Formal event sourcing | **DEFERRED** — full contract unavailable beyond PRD summary; turn log only on `emergent` HEAD | Turns `insert_one`; session `rolling_state` overwritten; no rebuild. Recovery branch: **LOCAL SUBSTITUTE** — bounded receipts provide idempotency and causal pointers but not canonical reconstruction or durable complete event history |
| Historical scoring equivalence | **N/A** — never existed in this repo | `git log -S` empty; no ranking subsystem |
| NaN / infinity input protection for rankings | **N/A** — never existed in this repo | No ranking subsystem |
| Vector retrieval / RAG | Not present | History replay from MongoDB turns only |

---

## Known test failures or tests not run

### Runnable and passed (Tests — 2026-06-17, `emergent`, no live server)

```bash
cd backend
pytest tests/test_security.py \
       tests/test_anti_hallucination_gateway.py \
       tests/test_relationship_calculus.py \
       tests/test_hud.py \
       tests/test_gateway_e2e.py \
       tests/verify_p0_object_permanence.py \
       tests/verify_p1_immersion_integrity.py \
       tests/verify_p15_microfixes.py -q
# Result: 67 passed (2026-06-17, includes 20 security tests)
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
| `emergentintegrations` removed from requirements (was unused, unavailable on PyPI) | Code search + CI hardening 2026-06-20 |
| FastAPI `@app.on_event("shutdown")` deprecated | Tests warnings when importing `server` |
| No MongoDB indexes defined in code | Code |
| Deterministic CI on `emergent` | `.github/workflows/deterministic-ci.yml` — 242 backend + 17 frontend tests; Yarn + `yarn.lock` canonical |
| Documentation pass 1–2 authored against `main`, cherry-picked to `emergent` without re-audit | Git history + code diff vs `main` |

---

## Security audit (`emergent` branch — post P0 increment)

| Finding | Status | Evidence |
|---------|--------|----------|
| Admin route authentication | **Confirmed** | `security.require_admin` on all `/api/admin/*`; `test_security.py` cases 11–15 ✅ |
| Player export safety | **Confirmed** | `export_session` always sanitised; `test_security.py` cases 16–17 ✅ |
| Raw export gate | **Confirmed** | `/export/raw` requires `X-Admin-Api-Key` + ownership; cases 18–20 ✅ |
| Session ownership (`device_id`) | **Confirmed** on protected routes | `fetch_owned_session` on get/action/export/reset/delete/mode/latest; cases 1–10 ✅ |
| Raw / debug exposure via player export | **Mitigated** | Player export strips `rolling_state`/`debug`/`raw` always |
| Raw / debug via `get_session` when `developer_mode` true | **Partial** | Still possible for session owner with server dev mode on — not raw export |
| Developer-mode toggle | **Confirmed** admin-gated | `POST /admin/settings` requires `X-Admin-Api-Key`; case 14 ✅ |
| Full user authentication | **Not present** | Device UUID isolation only — by design |
| `CORS_ORIGINS=*` default | **Unchanged** | Network-level risk remains |
| Story creation rate limits | **Confirmed** | `rate_limit.py` on `POST /story/new`; `test_rate_limit.py` ✅ |
| Player response allowlists | **Confirmed** | `player_api.py`; `test_player_api.py` ✅ |
| Minimal `/health` | **Confirmed** | Returns `status` + `llm_configured` only |

---

## Current highest-priority work

Derived from confirmed gaps (not speculative features):

| Priority | Work | Evidence |
|----------|------|----------|
| ~~P1 Chronicle Creation Phase 4 — Advanced Builder extraction~~ ✅ | `frontend/src/newstory/AdvancedBuilder.tsx` extracted; `new-story.tsx` orchestrates three modes | `frontend/__tests__/new-story.test.tsx` ✅ |
| ~~P1 Secret reveal trigger~~ ✅ | Secret Reveal Trigger v1 — explicit confession only | `secrets.py` + `test_secret_reveal.py` ✅ |
| ~~P1 Session action concurrency~~ ✅ | Session Action Concurrency Guard v1 — `story_action` only | `action_concurrency.py` + `test_action_concurrency.py` ✅ |
| P2 | Live-server long-run stress (`qa_live_20turn_hostile.py`) and wider story-engine bundle | Not run in this Phase 3 pass |
| P2 | ~~CI job for deterministic tests~~ ✅ | `.github/workflows/deterministic-ci.yml` (2026-06-20) |

---

## Early-Game Pacing Governor v1 (2026-06-20)

**What this increment proves (deterministic):**

- Stage 1 (turn_count 0) receives a non-persisted internal genesis directive as a separate system message in `_build_messages`.
- Stage 1 structural validation uses the engine-derived `active_pressures` projection from canonical `pressure_graph`; model-authored pressure is not authoritative.
- Pacing stage is computed once per request from pre-generation `turn_count` and threaded unchanged through initial generation, validation, and the single shared retry.
- Only one retry total per request; pacing failures use the same retry budget as format/hallucination failures.
- Internal directives are absent from `player_action`, turn records, rolling state, player export, raw admin export, and player API responses.

**What this increment does not prove:**

- Semantic concreteness of every opening (field presence ≠ narrative quality).
- Autonomous world movement or a living-world heartbeat.
- Stage 3 surfacing when no engine-owned development exists (directive plumbing only). Developer telemetry `pacing_stage3_no_engine_development` may appear in persisted turn `debug`, raw admin export turn debug, and admin diagnostics `latest_turn_debug` when `debug_mode` is on; it remains absent from player-safe exports, player session payloads, normal frontend responses, narrative, choices, player-facing state, and rolling state.

**Evidence:** `backend/pacing.py`, `backend/tests/test_early_game_pacing.py` (46 tests); regression bundle **118 passed** 2026-06-20.

A true **Living World Test** remains separate future work (see `next-work.md` NW-P1-07).

---

## Session Action Concurrency Guard v1 (2026-06-20)

**What this increment proves (deterministic):**

- Only one active `POST /story/action` may own a session at a time (Mongo lease on session document).
- Conflicting requests are rejected with HTTP **409** before any provider call.
- `next_turn_number` is derived from the locked session snapshot after atomic lease acquisition.
- Final persistence requires lease ownership and expected `turn_count` (CAS); model-lock fields are folded into the same update.
- Stale leases expire (default 600s) and may be reclaimed; old owners cannot release newer leases.
- Exact-turn rollback by `TurnRecord.id` remains; CAS conflict does not restore an old session snapshot.
- Successful API response contract is unchanged.
- Lease fields are absent from player serializers, player-safe export, and LLM prompt construction.

**What this increment does not prove:**

- ACID cross-collection persistence (compensating rollback only).
- Safety if MongoDB loses acknowledged writes.
- Concurrency safety for reset/delete/mode endpoints.
- ~~Frontend handling of HTTP **409**~~ ✅ (typed `ApiError`, read-only conflict sync, bounded polling — see Frontend Action Conflict Recovery v1 below).
- Idempotent replay of the same action after a completed request.
- Multi-region clock-skew resilience beyond the chosen expiry model.

**Evidence:** `backend/action_concurrency.py`, `backend/tests/test_action_concurrency.py` (33 tests); targeted bundle **151 passed**; full deterministic bundle **306 passed** 2026-06-20.

---

## Phase 2 update — Quick Start UI (2026-06-18)

- **Implemented:** `frontend/src/newstory/QuickStart.tsx` now drives the default New Chronicle path with six deterministic, zero-typing steps: World, Character, Tone, Want, Fear, and Who matters most. **Evidence:** Code + browser preview.
- **Request mapping:** Quick Start submits through the existing `POST /api/story/new` contract only. It maps to top-level `genre` / `role` / `tone` / `difficulty` / `mode="advanced"` and `custom_world_setup.{want,fear,whoMatters}`. **Evidence:** Code + deterministic test.
- **Duplicate-submit protection:** `frontend/app/new-story.tsx` uses a local submission lock plus immediate button disabling so one tap can create at most one request. **Evidence:** Code + deterministic test + browser preview.
- **Advanced Builder preservation:** The previous large builder remains available behind an explicit `Advanced Builder` switch; its scenario/manual setup path and submission contract remain intact. **Evidence:** Code + deterministic test + browser preview.
- **Secret handling verified:** Quick Start does not collect or render any secret field. Existing Phase 1 protections still keep secret data out of `simulation_hooks`, prompt-visible `<prior_state>`, and player/session payloads. **Evidence:** `backend/tests/test_onboarding_hooks.py` (16 passed).
- **Frontend tests added:** `frontend/__tests__/new-story.test.tsx` covers default mode, step flow, review summary, payload mapping, duplicate-submit protection, failure recovery, Advanced Builder accessibility, and font scaling. **Evidence:** Jest 10/10 passed.
- **Manual regression passed:** Preview flow completed from `/new-story` to `/play/[id]`; no secret/admin/mechanic leakage observed; Settings font-scale remained functional. **Evidence:** Playwright screenshots + console run 2026-06-18.
- **Known limitation:** Art integration and secret reveal mechanics were intentionally still out of scope for this pass. Advanced Builder extraction completed in a later increment (see Frontend Action Conflict Recovery v1).

---

## Phase 3 update — Guided Start + three-mode structure (2026-06-18)

- **Implemented:** New Chronicle now exposes three player-facing modes: `Quick Start`, `Guided Start`, and `Advanced Builder`. Quick Start remains the default. **Evidence:** Code + browser preview.
- **Guided Start:** Added a curated multi-step flow in `frontend/src/newstory/GuidedStart.tsx` covering world, world turning point, character, tone, want, fear, who matters most, and intensity. It completes without typing and ends with a deterministic review. **Evidence:** Code + Jest + browser preview.
- **Endpoint retained:** Guided Start still submits through the existing `POST /api/story/new` contract only. It maps world/character/tone/difficulty to top-level fields, uses `custom_premise` for the world turning point, and sends `custom_world_setup.{want,fear,whoMatters}`. Backend engine `mode` remains `advanced`. **Evidence:** Code + Jest.
- **State isolation:** Quick Start, Guided Start, and Advanced Builder now maintain separate frontend state so switching modes does not silently discard or corrupt selections. **Evidence:** Code + Jest.
- **Submission protection:** Guided Start reuses the screen-level submission lock and recoverable error handling already introduced in Phase 2. **Evidence:** Code + Jest + browser preview.
- **Security / secrecy:** Guided Start does not request or render any secret field and does not expose admin/debug/engine terminology to normal players. **Evidence:** Code + backend tests + browser preview.
- **Tests expanded:** `frontend/__tests__/new-story.test.tsx` now covers all three modes and Guided Start regressions. **Evidence:** Jest 17/17 passed.
- **Manual regression passed:** Preview verified Quick Start, Guided Start, Advanced Builder access, play-screen navigation, and Settings XL font scale. No blank-route regression recurred. **Evidence:** Playwright screenshots + console run 2026-06-18.
- **Known limitation (superseded):** Advanced Builder was later extracted to `frontend/src/newstory/AdvancedBuilder.tsx`; `new-story.tsx` now holds orchestration only.

---

## Frontend Action Conflict Recovery v1 (2026-06-20)

**What this increment proves (deterministic):**

- Advanced Builder extraction status matches code (`AdvancedBuilder.tsx` imported by `new-story.tsx`; builder UI not inline).
- Frontend throws typed `ApiError` with HTTP status and parsed `detail`; `friendlyError()` maps **409** to player-safe copy (no lock/lease/token terminology).
- On **409**, the play screen does not append a failed turn, does not clear typed custom action, and does not automatically call `sendAction()` again.
- Conflict recovery uses read-only `getSession()` via `syncAfterActionConflict()` (max 3 refresh attempts, ~1s apart); no provider calls during recovery.
- Refreshed turns merge through `mergeChronicleTurns()` (dedupe by `turn.id`, prefer server copy, ascending `turn_number`).
- Controls disable during submit and conflict sync; recover after sync success or bounded exhaustion; unmount cancels in-flight sync signal.
- Lightweight read-only focus refresh merges session state without full loading screen or input loss.

**What this increment does not prove:**

- Multi-tab UI coordination before a request reaches the server.
- Idempotent replay of a completed action.
- Backend safety for reset/delete/mode races.
- Browser rendering on every supported device.
- Provider quality or offline action queuing.

**Evidence:** `frontend/src/api-error.ts`, `frontend/src/action-conflict-sync.ts`, `frontend/src/chronicle-merge.ts`, `frontend/app/play/[id].tsx`, `frontend/__tests__/api-errors.test.ts`, `frontend/__tests__/chronicle-merge.test.ts`, `frontend/__tests__/play-action-conflict.test.tsx`, `frontend/__tests__/new-story.test.tsx`; Jest **41 passed**; TypeScript clean 2026-06-20.

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


## Chapter 14 P2 stress behavioural bands (MERGED, 2026-06-24)

**Status: canonical on `emergent`. P2 remains a scoring input only: it reshapes
Utility AI weights and never bypasses the feature flag or world-move eligibility.**

P2 derives a behavioural band from the authoritative P1 `stress_level` and uses
it to modify canonical Ch 27 Utility AI weights (goal-narrowing), applied exactly
once in `utility_ai.select_action`. Four bands (CALM/ELEVATED/STRAINED/OVERLOADED
at 25/50/75; lower-inclusive, OVERLOADED includes 100). The `stress_reduction`
weight stays x1.0 (Ch 27.4.2 already scales by stress/100).

Fail-closed: missing/invalid stress is never CALM — no band, identity modifiers,
`stress_input_valid=False`, `replacement_authorised` forced False, explicit
blocker code; candidate visible in shadow but never an authorised replacement.

Determinism/hash: candidate identity, `candidate_set_hash`, noise seed, and
tie-breaking unchanged; P2 diagnostics excluded from `state_hash`; CALM/invalid
byte-identical to pre-P2. P1 accumulation/scope/off-screen and snapshot identity
unchanged. Band-aware Utility AI live handoff is default-off and fail-closed.
P3/P4 remain deferred.

**Verification (truthful):** `stress.py`+`utility_ai.py` compile; focused
non-live bundle 139 passed + 1 pre-existing unrelated failure
(`test_prompt_fingerprint` server.py commit-range vs `9da1ae2`);
`test_stress_behaviour.py` 66 passed. Turn-path tests needing fastapi+MongoDB not
run in this sandbox. Evidence: `decision-log.md` (ADR-022),
`adr-022-stress-behaviour-bands.md`, `foundation-canon-deltas.md`,
`failure-modes.md` (FM-27).


## Prompt-only prior_state projection (2026-06-27)

**Status: canonical on `emergent` @ `f168dd2`. Offline-verified; live 20-turn
endurance verification PENDING.**

The Context Budget Governor now caps high-cardinality `rolling_state` registries
**only in the projected `<prior_state>` block inserted into the prompt** — never
in persisted state. State is truth; the projection is output.

- **Caps (prompt copy only):** `object_locations` 48, `inventory_objects` 36,
  `known_rooms` 12, `npc_memory` 16 (`memory.PROMPT_REGISTRY_CAPS`). Capping
  engages only when the assembled prompt is already over the active context
  budget; it preferentially keeps the most important entries (active/carried/
  worn/terminal objects, `current` rooms, major-severity NPC memories) and the
  most-recent items.
- **Persisted `rolling_state` is untouched.** `_compress_prior_state_json_with_meta`
  operates on a parsed copy of the prompt's `<prior_state>` JSON only; object
  permanence, room reconciliation, and NPC memory remain authoritative and keep
  growing in storage.
- **Causal-spine keys are never capped:** `active_consequences`,
  `delayed_consequences`, `active_threats` / `unresolved_threats`, `promises`,
  `clues`, `active_pressures`, `relationship_vectors`, `relationship_threads`,
  `objectives` / `current_objective` are carried in full.
- **Debug-only telemetry:** `compressed_prior_state` (bool) and
  `projected_registry_caps` (`{key: {original, kept, elided, protected_kept}}`)
  are surfaced in the dev/admin turn `debug` payload via `_meta_into_debug`; they
  never appear in player-facing prompt text, narrative, choices, player state, or
  player/session exports.
- **Prompt fingerprint guard modernised:** the former
  `tests/foundation_acceptance/test_prompt_fingerprint.py` asserted
  `git diff 9da1ae2..HEAD -- backend/server.py` produced no output — a stale
  tripwire that failed on any legitimate `server.py` edit. It now asserts the
  actual prompt seam (system prompt + `build_immutable_truth_block` +
  `build_relationship_block` + `<prior_state>` + `enforce_context_budget`) and
  that the debug-only budget fields never enter `_build_messages`. This resolves
  the single pre-existing failure noted in the Chapter 14 P2 section above.

**What this increment proves (offline, deterministic — reported at `f168dd2`):**
`backend/tests/test_context_budget.py` passes (caps applied prompt-only, persisted
counts unchanged, causal-spine preserved, determinism); `test_prompt_fingerprint.py`
passes; full offline suite **749 passed, 36 deselected, 0 failed**.

**What this increment does NOT prove (PENDING):** live 20-turn endurance
behaviour against a running backend (`tests/test_live_20_turn_harness.py`,
`@pytest.mark.live`) — confirming `compressed_prior_state` /
`projected_registry_caps` in live debug output, `estimated_prompt_tokens <=
context_budget_tokens` on every turn, and persisted > projected counts across
real LLM turns. Not run; requires a live stack.

**Evidence:** `backend/memory.py` (`PROMPT_REGISTRY_CAPS`, `_cap_prompt_registry`,
`_compress_prior_state_json_with_meta`, `enforce_context_budget`),
`backend/server.py` (`_meta_into_debug`), `backend/tests/test_context_budget.py`,
`backend/tests/foundation_acceptance/test_prompt_fingerprint.py`.


## Foundation promotion — Phase 2 (2026-07-02)

**Status: promotion infrastructure landed on `emergent`; all promotion flags
default OFF. With every flag off, the turn path is byte-identical to
pre-promotion behaviour.**

The four canonical foundation subsystems (Actor Resolution, Gravity Governance,
Utility AI, Memory Retrieval) already run every turn as a shadow evaluation via
`foundation_integration.evaluate_foundation_turn` (called from
`replayability.prepare_action_turn`). This increment adds a flag-gated, fail-closed
**promotion layer** that lets each canonical subsystem become the authoritative
decision path while the legacy implementation remains available as fallback.

- **Flags (default OFF, `ai_config.py`):** `ENABLE_CANONICAL_ACTOR_RESOLUTION`,
  `ENABLE_CANONICAL_GRAVITY`, `ENABLE_CANONICAL_UTILITY`,
  `ENABLE_CANONICAL_MEMORY_RETRIEVAL`. Routing helpers live in
  `foundation_promotion.py` (pure, deterministic, no I/O/LLM).
- **Actor Resolution** (Stage 1): canonical veto + re-pick over the existing NPC
  candidate set; unmapped actors fail open; legacy `resolve_actor_tier` fallback.
- **Gravity Governance** (Stage 2): canonical retention ranks the `npc_memory`
  prompt projection only; persisted `rolling_state` untouched (State Is Truth);
  retained count unchanged (context budget preserved); legacy heuristic fallback.
- **Utility AI** (Stage 3): `ENABLE_CANONICAL_UTILITY` is the canonical name for
  the existing ADR-024 live handoff; legacy `ENABLE_UTILITY_AI_LIVE_SELECTION`
  remains an accepted alias.
- **Memory Retrieval** (Stage 4): **BLOCKED** for authoritative prompt use by
  `SEPARATE_SHADOW_ACCEPTANCE_REQUIRED` (`D_MEMORY_RETRIEVAL_SHADOW`). Flag +
  comparison diagnostics added; prompt injection stays gated OFF behind
  `CANONICAL_MEMORY_RETRIEVAL_PROMPT_INJECTION_ACCEPTED = False`; retrieval keeps
  running `shadow_mode=True`.
- **Diagnostics:** `foundation_promotion_flags`, `memory_retrieval_promotion`
  (with `memory_retrieval_blocker_code`), and per-stage legacy-vs-canonical
  fields are recorded in dev/admin turn `debug` only — never player-visible.

**What this increment proves (offline, deterministic):** consolidated offline run
of `test_foundation_promotion.py` + the foundation unit suites
(`test_actor_resolution/gravity_governance/memory_retrieval`) +
`tests/foundation_acceptance/` + `test_foundation_integration.py` +
`test_context_budget.py` + `test_living_cast_shadow.py` = **112 passed** with the
OFF path byte-identical (the turn-path integration suites import the edited
`replayability.py`/`foundation_integration.py`/`memory.py`). `test_foundation_promotion.py`
runs **25/25** from a clean checkout and covers flags, promotion/fallback paths,
determinism, divergence, rollback, budget stability, and the memory-retrieval
leakage gate. (A stale-file artifact in this sandbox mount can make the single
gravity `npc_memory` cap test read a pre-edit `memory.py`; it passes from a clean
checkout — CI/production are unaffected.)

**What this increment does NOT prove (PENDING):** live 20-turn endurance with
any flag ON; real-LLM gameplay acceptance for flipping any flag to default ON;
Memory Retrieval authoritative prompt use (blocked). See
`docs/foundation-promotion.md`.

**Evidence:** `backend/ai_config.py`, `backend/foundation_promotion.py`,
`backend/replayability.py`, `backend/memory.py`,
`backend/foundation_integration.py`,
`backend/tests/test_foundation_promotion.py`, `docs/foundation-promotion.md`.

---

## Chapter 33 — NPC Lifecycle, Phase 1 (Lifecycle Core) — 2026-07-02

**Code + Tests.** Deterministic lifecycle core landed as a new module
`backend/npc_lifecycle.py` (aging from explicit simulation days, Appendix A.7
life stages, seeded natural mortality, one idempotent death transition for
natural + unnatural death emitting structured events, tier-aware processing,
deterministic migration/defaulting). Feature flag `ENABLE_NPC_LIFECYCLE`
**default OFF**; with it off gameplay is byte-identical (nothing calls the
module). 42 focused tests pass; affected foundation/gateway/death-registry
regressions green.

**Live integration status:** the `evaluate_lifecycle_tick` seam is **not wired
into the turn path** — no authoritative simulation clock exists yet (cf.
`D_GRACE — SIMULATION_TIME`). Live aging is a later-phase dependency; Phase 1
never advances lifecycle from ordinary turns. Births, inheritance, grudges,
succession, and burn-in turnover remain deferred. Chapter 33 is **not** complete.

**Evidence:** `backend/npc_lifecycle.py`, `backend/ai_config.py`
(`ENABLE_NPC_LIFECYCLE`), `backend/tests/test_npc_lifecycle.py`,
`docs/ch33-lifecycle-phase1.md`.
