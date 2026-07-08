# Next Work

Practical backlog from confirmed repo gaps on the **`emergent`** branch. No speculative product features. Historical ranking-equivalence and NaN-ranking items remain excluded; ADR-024's same-candidate Utility AI shadow comparison is implemented and tracked separately below.

---

## Completed (documentation)

### NW-DOC-01: Reconcile docs with `emergent` runtime ✅

| Field | Detail |
|-------|--------|
| **Problem** | Pass 1–2 docs described `main` (no gateway/relationship/HUD); cherry-picked to `emergent` without re-audit. |
| **Evidence** | Git diff `main` vs `emergent`; 47-test bundle passed 2026-06-17 |
| **Resolution** | This reconciliation pass — see `change-history.md` 2026-06-17 pass 3 |

---

## Completed (P0 security)

### NW-P0-01: Admin authentication + safe export ✅

| Field | Detail |
|-------|--------|
| **Resolution** | `security.require_admin`; player `/export` always sanitised; `/export/raw` for admin + ownership |
| **Tests** | `test_security.py` cases 11–20 ✅ |
| **ADR** | ADR-012 |

### NW-P0-02: Session ownership enforcement ✅

| Field | Detail |
|-------|--------|
| **Resolution** | `security.fetch_owned_session` on all protected routes; frontend sends `device_id` |
| **Tests** | `test_security.py` cases 1–10 ✅ |
| **ADR** | ADR-012 |

### NW-P0-03: Deployment operator workflow

| Field | Detail |
|-------|--------|
| **Problem** | Expo Settings admin UI cannot call `/api/admin/*` without embedding credentials (forbidden). |
| **Recommended action** | Document curl/operator proxy pattern; set `ADMIN_API_KEY` in deployment |
| **Acceptance criteria** | `development.md` or ops runbook describes admin access |
| **Files** | `docs/development.md` (future), deployment env |

---

## Completed (Replayability Engine v1)

### NW-LIVING-CAST-01: Living Cast Engine v1 ✅

| Field | Detail |
|-------|--------|
| **Status** | Merged and live on `emergent`; deterministic NPC world-move substrate remains authoritative for eligibility, targets, effects, receipts, and commit |
| **Resolution** | `npc_agendas.py`, `npc_world_moves.py`, `arc_diversity.py` orchestrated in `replayability.py`; ≤1 deterministic NPC move per turn before narration; Policy A legacy skip; world execution `TURN_COUPLED_AUTONOMY_ONLY` |
| **Tests** | Living Cast modules run under emergent deterministic CI |
| **ADR** | ADR-020; amended by ADR-024 scoring bridge |
| **Remaining blocker** | None — relationship provenance (the prior golden-path blocker) was resolved 2026-07-02; see NW-RELPROV-01 below |
| **Follow-up** | Full PRD Ch 25 Actor Resolution remains open; see NW-RELPROV-02 below for a separate, narrow Living Cast provenance-symmetry gap |

### NW-RELPROV-01: Relationship provenance remediation (Phase 1) ✅

| Field | Detail |
|-------|--------|
| **Status** | Merged and live on `emergent` (merge commit `5009dec`, branch `phase1-relationship-provenance`, 2026-07-02). Not recorded in this doc, `feature-status.md`, or `current-state.md` at merge time — reconciled here 2026-07-08. No dedicated ADR was written for this remediation. |
| **Problem it closed** | Relationship vectors could previously be described as mutated by "player intent + generated prose" (see `current-state.md`'s pre-2026-07-02 reconciliation table) — a State-is-truth violation if generated narrative ever fed the mutation path. |
| **Resolution** | `backend/relationship_provenance.py` — single authoritative mutation path (`apply_relationship_events`) driven only by structured events derived from the player's declared action (`resolve_player_action_events`), never from generated prose. `backend/relationships.py`'s `update_relationship_calculus` now delegates to it directly; the `parsed` (generated-narrative) argument is kept only for call-site compatibility and is provably never read. |
| **Tests** | `backend/tests/test_relationship_provenance.py` — 15 passed (structured-event updates, prose-driven-update rejection, replay determinism, malformed-event rejection, no duplicate application, event-ordering stability, provenance traceability, dev-only leakage containment). `backend/tests/test_relationship_calculus.py` — 11 passed (existing calculus suite unaffected by the delegation). Both re-run 2026-07-08. |
| **Follow-up** | See NW-RELPROV-02 (narrow, separate gap) |

### NW-RELPROV-02: Living Cast relationship-effect provenance not wired

| Field | Detail |
|-------|--------|
| **Problem** | `relationship_provenance.living_cast_effect_provenance()` exists and is unit-tested but is never called from `relationships.apply_living_cast_relationship_effects` (the actual Living Cast NPC-effect application path, invoked from `replayability.py`) or anywhere else reachable at runtime. Player-action relationship mutation has full structured-event provenance (NW-RELPROV-01); NPC-authored (Living Cast) relationship mutation does not yet get a provenance record anywhere it can be inspected. |
| **Evidence** | `grep` for `living_cast_effect_provenance(` — only defined in `relationship_provenance.py` and called from `tests/test_relationship_provenance.py`; zero call sites in `relationships.py` or `replayability.py` (2026-07-08). |
| **Impact** | Cosmetic/diagnostic gap only — does not affect gameplay, determinism, or the State-is-truth guarantee (Living Cast effects were already structured/engine-owned before this). It just means Living Cast relationship deltas aren't traceable the same way player-action deltas are. |
| **Recommended action** | Either wire `living_cast_effect_provenance` into `apply_living_cast_relationship_effects`'s call site, or explicitly document this as a deferred Phase 2 and scope it there. Do not conflate with NW-RELPROV-01 — that blocker is resolved. |
| **Files** | `backend/relationships.py` (`apply_living_cast_relationship_effects`), `backend/relationship_provenance.py` (`living_cast_effect_provenance`) |

### NW-PRESSURE-01: ADR-023 pressure authority remediation ✅

| Field | Detail |
|-------|--------|
| **Status** | Complete on `emergent` |
| **Resolution** | `replayability_state.pressure_graph` is canonical; `rolling_state.active_pressures` is a deterministic, engine-owned derived projection; model-authored pressure is not authoritative |
| **Evidence** | ADR-023 implementation commits `79f1d48` and `75009f0`; deterministic CI verified |
| **Follow-up** | None for pressure authority; preserve single-source ownership |

### NW-UTILITY-01: ADR-024 shadow comparison + feature-gated live selection ✅

| Field | Detail |
|-------|--------|
| **Status** | ADR-024 Phase 1 complete; NW-UTILITY-01 complete on `emergent` @ `cf2329d`; deterministic live-handoff proof complete |
| **Resolution** | Shadow comparison always runs. `ENABLE_UTILITY_AI_LIVE_SELECTION` defaults OFF; when enabled, an authorised band-aware `utility_ai.select_action` winner is handed to the unchanged `npc_world_moves` commit path |
| **Safety** | Flag OFF preserves current live selection; missing/invalid Utility inputs fail closed to the heuristic winner; dev-only diagnostics record enabled/applied/source/candidate/receipt evidence |
| **Verification status** | Deterministic backend tests prove eligible candidate generation, agreement and disagreement live-handoff paths, and committed receipts matching the Utility AI winner. `TURN_INTEGRATION_UNVERIFIED` remains correct because live LLM gameplay turn-path acceptance is separate |
| **Follow-up** | Real LLM gameplay turn-path acceptance before any `TURN_INTEGRATION_VERIFIED` claim or default activation |

---

### NW-FOUNDATION-PROMOTION-01: Foundation Completion Phase 2 — flag-gated promotion ✅ (infra)

| Field | Detail |
|-------|--------|
| **Status** | Promotion infrastructure landed on `emergent`; all `ENABLE_CANONICAL_*` flags default OFF. OFF path byte-identical to pre-promotion behaviour |
| **Resolution** | `foundation_promotion.py` (pure, fail-closed routing) + flags in `ai_config.py`; Stage 1 Actor Resolution veto in `replayability.py`; Stage 2 Gravity `npc_memory` prompt-projection ordering in `memory.py`; Stage 3 `ENABLE_CANONICAL_UTILITY` alias for the ADR-024 handoff; Stage 4 Memory Retrieval flag + diagnostics with prompt injection gated OFF |
| **Safety** | Every helper returns legacy on flag-off / error / mapping gap; deterministic (no new RNG/I/O/LLM); persisted `rolling_state` untouched; context-budget count unchanged; canonical-vs-legacy diagnostics are dev/admin only |
| **Verification** | Offline deterministic: 76-passed OFF baseline (foundation + integration + context budget) + new `test_foundation_promotion.py`. Live/LLM acceptance for any flag-ON default flip is separate and PENDING |
| **Remaining blocker** | **Memory Retrieval authoritative prompt use** — blocked by `SEPARATE_SHADOW_ACCEPTANCE_REQUIRED` (`D_MEMORY_RETRIEVAL_SHADOW`); requires granting `CANONICAL_MEMORY_RETRIEVAL_PROMPT_INJECTION_ACCEPTED` after a separate shadow-acceptance pass |
| **Docs** | `docs/foundation-promotion.md`; `current-state.md` promotion section (2026-07-02) |

---

### NW-REPLAY-01: Session replayability_state + deterministic variation ✅

| Field | Detail |
|-------|--------|
| **Resolution** | `backend/replayability.py` + `run_identity.py`, `opening_state.py`, `pressure_graph.py`, `consequence_echoes.py` — session document field only; Policy A legacy skip |
| **Tests** | Five replayability modules ✅; targeted bundle **185**; full bundle **390** passed (contract-corrected) |
| **ADR** | ADR-019 |
| **Follow-up** | Richer structured-event sources from ledger/guards; Living World Test remains separate |

---

## Completed (Session Action Concurrency Guard v1)

### NW-CONCURRENCY-01: Per-session action lease ✅

| Field | Detail |
|-------|--------|
| **Resolution** | `backend/action_concurrency.py` — Mongo lease on session; acquire before provider; CAS persistence; HTTP **409** on conflict |
| **Tests** | `test_action_concurrency.py` ✅ (33 cases); `test_secret_reveal.py` regression ✅ |
| **ADR** | ADR-018 |
| **Follow-up** | Reset/delete/mode concurrency audit; repair plan if historical duplicate `(session_id, turn_number)` rows block unique index |

---

## Completed (Frontend reliability increment — three stages)

### NW-FE-01: Advanced Builder documentation reconciliation ✅

| Field | Detail |
|-------|--------|
| **Resolution** | Confirmed `frontend/src/newstory/AdvancedBuilder.tsx` is extracted and used; `new-story.tsx` orchestrates Quick, Guided, and Advanced modes only |
| **Tests** | `frontend/__tests__/new-story.test.tsx` ✅ |

### NW-FE-02: Typed API errors + HTTP 409 friendly copy ✅

| Field | Detail |
|-------|--------|
| **Resolution** | `frontend/src/api-error.ts` (`ApiError` class); `frontend/src/api.ts` throws typed errors; `friendlyError()` maps 409 to player-safe title/message |
| **Tests** | `frontend/__tests__/api-errors.test.ts` ✅ |

### NW-FE-03: Play-screen action-conflict recovery ✅

| Field | Detail |
|-------|--------|
| **Resolution** | `syncAfterActionConflict()` read-only refresh; `mergeChronicleTurns()` dedupe; play screen preserves input, no auto-resubmit, bounded polling, focus refresh |
| **Tests** | `frontend/__tests__/play-action-conflict.test.tsx` ✅, `frontend/__tests__/chronicle-merge.test.ts` ✅ |

---

## Completed (Secret Reveal Trigger v1)

### NW-SECRET-01: Explicit confession reveal ✅

| Field | Detail |
|-------|--------|
| **Resolution** | `backend/secrets.py` — deterministic confession detection, copy-on-write reveal before generation, internal directive, registry mutation strip |
| **Tests** | `test_secret_reveal.py` ✅ (37 cases); onboarding concealment preserved |
| **ADR** | ADR-017 |
| **Follow-up** | Automatic/evidence/NPC reveal policies — out of v1 scope |

---

## P1: Correctness and verification

### NW-P1-01: Live-server integration tests

| Field | Detail |
|-------|--------|
| **Problem** | Live tests unverified; `test_custom_world_system.py` needs running backend. |
| **Evidence** | Unverified list in `verification.md` |
| **Impact** | Integration regressions unknown |
| **Recommended action** | Document server prerequisite; add pytest marker `live` or docker-compose for CI |
| **Acceptance criteria** | Live bundle passes with documented one-command stack |
| **Files** | `backend/tests/conftest.py`, `docs/development.md`, `docs/release-checklist.md` |
| **Dependencies** | MongoDB + OpenRouter key |

### NW-P1-02: Outdated `test_story_engine.py`

| Field | Detail |
|-------|--------|
| **Problem** | `AGENTS.md` and PRD state assertions are outdated vs Haiku/OpenRouter + gateway runtime. |
| **Evidence** | `AGENTS.md`; Docs-claimed |
| **Impact** | False regressions or missed regressions |
| **Recommended action** | Update assertions or split into live vs contract tests; fix E741 |
| **Acceptance criteria** | File passes on current stack or is skipped with documented reason |
| **Files** | `backend/tests/test_story_engine.py` |
| **Dependencies** | NW-P1-01 |

### NW-P1-03: Live hostile stress test not executed

| Field | Detail |
|-------|--------|
| **Problem** | `qa_live_20turn_hostile.py` and PRD P1 items (20+ turn, 15+ turn compression) not run. |
| **Evidence** | Scripts exist; **Unverified** 2026-06-17 |
| **Impact** | Long-run guard failures unknown |
| **Recommended action** | Run script; record results in `change-history.md` and `feature-status.md` |
| **Acceptance criteria** | Script completes; failures triaged or filed as P0/P1 |
| **Files** | `backend/tests/qa_live_20turn_hostile.py`, `docs/verification.md` |
| **Dependencies** | NW-P1-01 |

### NW-P1-04: Provider fallback drill

| Field | Detail |
|-------|--------|
| **Problem** | Fallback chain coded via `gateway.invoke_llm` but deliberate failure test not recorded. |
| **Evidence** | PRD P1 backlog; `ai_service.py` fallback_events |
| **Impact** | Production outage if primary model disabled |
| **Recommended action** | Temporarily set invalid primary in test env; confirm Sonnet/Mythomax rescue |
| **Acceptance criteria** | `fallback_events` populated in turn debug; chronicle continues |
| **Files** | `backend/ai_service.py`, admin settings |
| **Dependencies** | NW-P1-01 |

### NW-P1-05: Pin `httpx` dependency

| Field | Detail |
|-------|--------|
| **Problem** | `ai_service.py` imports `httpx`; not listed in `requirements.txt`. |
| **Evidence** | Code inspection |
| **Impact** | Fresh install may break if transitive dep removed |
| **Recommended action** | Add `httpx` with compatible version to `requirements.txt` |
| **Acceptance criteria** | Clean venv install + import works |
| **Files** | `backend/requirements.txt` |
| **Dependencies** | None |

### NW-P1-07: Living World Test (autonomous heartbeat — not implemented)

| Field | Detail |
|-------|--------|
| **Problem** | Early-Game Pacing Governor v1 improves opening guidance and Stage 1 field-presence but does not prove the world moves without player requests. |
| **Evidence** | ADR-016; `test_early_game_pacing.py` explicitly does not claim autonomous simulation |
| **Impact** | Cannot verify engine-owned world advancement between turns or while player is absent |
| **Recommended action** | Design and implement a separate Living World Test: deterministic engine ticks producing state before LLM narration; Stage 3 must surface only engine-authored developments |
| **Acceptance criteria** | Test proves state changes originate from engine modules, not pacing directives alone; documented separately from pacing v1 |
| **Files** | Future engine modules; `docs/verification.md` |
| **Dependencies** | Pressure ecology / delayed-consequence engine maturity (planned — not present) |

### NW-P1-06: Live gateway and relationship probes

| Field | Detail |
|-------|--------|
| **Problem** | `test_gateway_live_probe.py` and `test_relationship_calculus_live.py` not run. |
| **Evidence** | Offline unit/e2e tests pass; live probes **Unverified** |
| **Impact** | Provider behaviour vs gateway/relationship guards unknown under real LLM |
| **Recommended action** | Run both against live stack; record in `change-history.md` |
| **Acceptance criteria** | Both pass or failures documented with triage |
| **Files** | `backend/tests/test_gateway_live_probe.py`, `test_relationship_calculus_live.py` |
| **Dependencies** | NW-P1-01 |

---

## P2: Maintainability and documentation

### NW-P2-01: MongoDB indexes undefined

| Field | Detail |
|-------|--------|
| **Problem** | No indexes declared for `device_id`, `session_id`, `turn_number`. |
| **Evidence** | Code search — no index creation |
| **Impact** | Slow lists at scale |
| **Recommended action** | Document required indexes; add migration script or startup ensure |
| **Acceptance criteria** | Indexes documented in `development.md`; optional script in repo |
| **Files** | `docs/development.md`, new migration script (future) |
| **Dependencies** | None |

### NW-P2-02: Export/reset API contract tests

| Field | Detail |
|-------|--------|
| **Problem** | No automated contract tests for export JSON keys and reset `turn_count=0`. |
| **Evidence** | `failure-modes.md` FM-18 |
| **Impact** | Frontend share/reset breakage undetected |
| **Recommended action** | Add pytest for export JSON keys and reset turn_count=0 |
| **Acceptance criteria** | Tests pass against live server |
| **Files** | `backend/tests/`, `docs/api.md` |
| **Dependencies** | NW-P1-01 |

### NW-P2-03: CI pipeline for deterministic bundle ✅

| Field | Detail |
|-------|--------|
| **Resolution** | `.github/workflows/deterministic-ci.yml` — separate backend (pytest `-m "not live"`, MongoDB service) and frontend (`yarn test`, `yarn typecheck`) jobs on `emergent` |
| **Evidence** | 205 backend + 17 frontend tests passed locally 2026-06-20 |
| **Files** | `.github/workflows/deterministic-ci.yml`, `backend/pytest.ini`, `backend/tests/conftest.py`, `frontend/yarn.lock` |
| **Follow-up** | Add `yarn lint` to CI when Expo lint runs reliably on Ubuntu runners; run live `@pytest.mark.live` bundle manually |

### NW-P2-04: Reconcile engine-layer docs (situation/goal/npc_action/world_event/investigation/information + pressure_graph/pressure_genesis)

| Field | Detail |
|-------|--------|
| **Problem** | `situation_engine.py`, `goal_engine.py`, `npc_action_engine.py`, `world_event_engine.py`, `investigation_engine.py`, `information_engine.py`, `pressure_graph.py`, and `pressure_genesis.py` (Stage 6C) are live on `emergent`, each wired into `replayability.prepare_action_turn` via an `evolve_*` call, and each has a dedicated test file — none of this appears anywhere in this backlog or in `feature-status.md` prior to 2026-07-08. |
| **Evidence (2026-07-08, offline)** | Test counts, all passing: `test_situation_engine.py` (11), `test_goal_engine.py` (12), `test_npc_action_engine.py` (9), `test_world_event_engine.py` (5), `test_investigation_engine.py` (5), `test_information_engine.py` (12), `test_pressure_graph.py` (26), `test_pressure_genesis.py` (17, Stage 6C-0 scaffold + 6C-1 rule table). Wiring into `prepare_action_turn` confirmed by direct code read, not just test presence. |
| **Impact** | Anyone reading only `next-work.md`/`feature-status.md` would not know this engine layer exists — same class of staleness NW-DOC-01 fixed in 2026-06-17, recurred since. |
| **Recommended action** | A dedicated documentation pass (similar to NW-DOC-01) per module: confirm exact wiring/ownership, add `feature-status.md` rows, and record design intent/limits — this backlog entry only confirms presence + offline test status, not full behavioural acceptance. Mark each as "present, needs doc verification" until that pass runs. |
| **Files** | `docs/feature-status.md`, `docs/next-work.md`, `docs/current-state.md` |
| **Dependencies** | None |

---

## Later: Product improvements (Docs-claimed, not verified as gaps)

From PRD P2 — only if P0/P1 clear:

| Item | Evidence |
|------|----------|
| In-app long-run diagnostics summary | PRD P2 |
| Share/export-friendly chronicle summary view | PRD P2; export exists but raw JSON |

---

## Explicitly out of scope until code exists

Do not schedule without implementation evidence:

- Actor resolution / caps (PRD Ch 25)
- Formal event sourcing rebuild
- Gravity retention beyond context budget
- NPC↔NPC relationship edges
- Vector retrieval RAG

## Chapter 33 — NPC Lifecycle (status)

- **Phase 1 closure (implemented and committed):** deterministic lifecycle core (`backend/npc_lifecycle.py`) plus structured clock seam (`backend/simulation_clock.py`, `replayability.prepare_action_turn`). `ENABLE_NPC_LIFECYCLE` defaults OFF. Time advances only from engine-owned structured events; ordinary turns advance zero.
- **Current blocker:** accepted action duration has no existing engine-owned structured action-result authority. Do not infer time from client payloads, player wording, LLM output, parsed model fields, wall-clock time, or `turn_number * duration`; see `docs/ch33-action-duration-authority-brief.md` and blocker `D_ACTION_DURATION_AUTHORITY`.
- **Blocker resolution path (ADR Accepted, runtime NOT implemented):** ADR-025 (`docs/adr-025-action-duration-authority.md`, Accepted 2026-07-04 with owner amendments) ratifies the v1 policy — ordinary actions advance 0 days; time advances only via an explicit structured time command (engine-owned validation, approved duration, event construction, and clock mutation; deterministic `event_id = time_advance:{session_id}:{turn_number}:{command_kind}:{approved_days}`); corrected same-turn pipeline (produce + consume through the existing clock seam BEFORE provider narration; authoritative only on CAS persistence success); `MAX_TIME_COMMAND_DAYS = 30` hard ceiling with rejection (never silent clamping); separate default-OFF `ENABLE_TIME_COMMANDS` flag (clock progression must not depend on `ENABLE_NPC_LIFECYCLE`); sub-day = 0 days, no rounding, no accumulation. **Phase 2A implementation scope: `WAIT_ONE_DAY` → 1 approved simulation day only**; `rest`/`travel`/N-day commands stay deferred. The blocker stays OPEN until the Phase 2A runtime implementation and tests land and are verified.
- **Still deferred:** action-duration -> structured-time mapping (so gameplay can stage time advances); births/pregnancy/family formation; inheritance (property, dispositions, grudges); leadership succession; disputed-inheritance pressure; 200-year burn-in turnover; player-facing lifecycle/death surfacing. Chapter 33 is **not** complete.

**Not applicable to this repo (never existed):** historical scoring equivalence, NaN/infinity ranking guards.
