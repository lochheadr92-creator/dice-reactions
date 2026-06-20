# Change History

Lightweight log of documentation and operational changes. One entry per meaningful doc or release pass.

---

## 2026-06-20 — Bible implementation status truth correction (`emergent` docs)

| Field | Detail |
|-------|--------|
| **Change** | Corrected `/docs/*` overclaims: Living Cast is **not** on `emergent` HEAD; exists only on unmerged `recovery/living-cast-working-tree` as a **provisional integrated local substitute**; bounded receipts are **LOCAL SUBSTITUTE** (not canonical event sourcing); full event sourcing **DEFERRED**; Chapters 1–21 have full Bible text; Chapters 22–32 are PRD tracker summaries only; Chapter 26 is a PRD extension bundled with Chapter 20; weighted verified-contract coverage **38.1%** on `emergent` HEAD and **37.4%** on recovery (audit formula — not feature quality); pressure authority and relationship provenance remain **unresolved**; feature development **frozen**; golden-path blockers remain. |
| **Reason** | Prior doc pass falsely treated recovery-branch Living Cast work as shipped on `emergent` and inflated coverage. |
| **Files affected** | `docs/change-history.md`, `docs/current-state.md`, `docs/decision-log.md`, `docs/failure-modes.md`, `docs/feature-status.md`, `docs/next-work.md`, `docs/release-checklist.md`, `docs/story-engine.md`, `docs/verification.md` |
| **Branch** | `emergent` @ `d8b9caf` — documentation only; no runtime changes |
| **Recovery reference** | `recovery/living-cast-working-tree` @ `4dadb3f` — Living Cast modules and tests live here; **not deployed**, **not covered by emergent CI**, **not merge-ready** |

---

## 2026-06-20 — Replayability Engine v1 (contract-correction pass)

| Field | Detail |
|-------|--------|
| **Change** | Pre-commit contract correction: removed raw player-text echo scheduling; replaced `engine_events` with bounded `transition_receipts`; causal pressure graph (`magnitude`, `trend`, links, foreground scoring); causal run-identity dimensions seeding opening/pressure; structured opening facts; post-guard `collect_qualifying_echo_sources` + `finalize_action_turn`; `.gitignore` for `terminals/`. |
| **Reason** | State-as-truth: echoes and pressure movement must come from confirmed engine structures, not keywords or a duplicate event log. |
| **Files affected** | `backend/replayability.py`, `run_identity.py`, `opening_state.py`, `pressure_graph.py`, `consequence_echoes.py`, `server.py`, replayability test modules, `docs/*`, `.gitignore` |
| **Tests run** | Target replayability bundle **185** ✅; full `pytest -m "not live" -q` → **390 passed** |
| **Decision-log entry** | ADR-019 (updated) |
| **Remaining risks** | Theft/violence/promise echo kinds unsupported until structured guard outputs exist; no cross-session replay comparison UI |

---

## 2026-06-20 — Replayability Engine v1 (initial)

| Field | Detail |
|-------|--------|
| **Change** | Added replayability modules and session field `replayability_state`. Wired into new-story and story-action pipelines. Policy A legacy skip. |
| **Reason** | Deterministic run variation without LLM-authored replayability truth. |
| **Superseded by** | Contract-correction pass above (keyword echoes and `engine_events` removed) |

---

## 2026-06-20 — Frontend Action Conflict Recovery v1 (three-stage increment)

| Field | Detail |
|-------|--------|
| **Change** | Stage 1: reconciled docs — Advanced Builder extraction complete (`AdvancedBuilder.tsx`). Stage 2: added `frontend/src/api-error.ts` (`ApiError` with status/detail/body); `api.ts` throws typed errors; `friendlyError()` explicit 409 copy. Stage 3: play-screen 409 recovery — `action-conflict-sync.ts` (bounded read-only `getSession` polling), `chronicle-merge.ts` (`mergeChronicleTurns`), `play/[id].tsx` conflict sync + focus refresh; preserves typed input; no auto-resubmit. |
| **Reason** | Frontend must handle Session Action Concurrency Guard HTTP **409** without losing player input, duplicating turns, showing raw JSON, or stuck loading state. |
| **Files affected** | `frontend/src/api-error.ts`, `frontend/src/action-conflict-sync.ts`, `frontend/src/chronicle-merge.ts`, `frontend/src/api.ts`, `frontend/src/errors.ts`, `frontend/app/play/[id].tsx`, `frontend/__tests__/*`, `docs/*` |
| **Tests run** | `node node_modules/jest/bin/jest.js --runInBand` → **41 passed**; `tsc --noEmit` → clean. Backend unchanged — no pytest run. |
| **Remaining risks** | Multi-tab pre-submit races; idempotent replay; reset/delete/mode concurrency; full browser/device matrix |

---

## 2026-06-20 — Session Action Concurrency Guard v1

| Field | Detail |
|-------|--------|
| **Change** | Added `backend/action_concurrency.py` (Mongo-backed per-session lease on `sessions` document). Wired into `story_action` before reveal/provider work; final persistence uses lease-token + expected `turn_count` CAS with model-lock folded into the same update. HTTP **409** on active-action conflict. Added `test_action_concurrency.py` (33 tests). Startup creates idempotent unique indexes on `sessions.id`, `turns.id`, and `(session_id, turn_number)` when no historical duplicates exist. |
| **Reason** | Prevent overlapping `POST /story/action` requests from racing turn numbers, rolling state, secret reveals, and provider spend across tabs, retries, and workers. |
| **Files affected** | `backend/action_concurrency.py`, `backend/server.py`, `backend/tests/test_action_concurrency.py`, `backend/tests/test_secret_reveal.py`, `docs/*` |
| **Tests run** | `pytest tests/test_action_concurrency.py tests/test_secret_reveal.py tests/test_early_game_pacing.py -q` → **151 passed**; full `pytest -m "not live" -q` → **306 passed** |
| **Decision-log entry** | ADR-018 |
| **Remaining risks** | No concurrency guard on reset/delete/mode; no idempotent replay of completed actions (frontend 409 handling added in Frontend Action Conflict Recovery v1) |

---

## 2026-06-20 — Secret Reveal Trigger v1

| Field | Detail |
|-------|--------|
| **Change** | Added `backend/secrets.py` (explicit confession detection, copy-on-write reveal, internal directive, registry authority). Wired into `story_action`, `_build_messages`, `_generate_validated_turn` retry path, and post-consolidation registry protection. Added `test_secret_reveal.py` (37 tests). |
| **Reason** | Allow deliberate player confession to reveal onboarding secrets deterministically without LLM classification or automatic triggers. |
| **Files affected** | `backend/secrets.py`, `backend/server.py`, `backend/tests/test_secret_reveal.py`, `backend/tests/test_early_game_pacing.py` (signature fix), `docs/*` |
| **Tests run** | `pytest tests/test_onboarding_hooks.py tests/test_secret_reveal.py tests/test_early_game_pacing.py -q` → **103 passed**; full `pytest -m "not live" -q` → **242 passed** |
| **Decision-log entry** | ADR-017 |
| **Remaining risks** | Confession phrasing false negatives; provider prose quality; no automatic/evidence reveals |

---

## 2026-06-20 — Deterministic GitHub Actions CI

| Field | Detail |
|-------|--------|
| **Change** | Added `.github/workflows/deterministic-ci.yml` (push/PR to `emergent`, `workflow_dispatch`). Added `backend/pytest.ini` with `live` marker. Marked live-only tests in `test_story_engine.py`, `test_gateway_live_probe.py`, `test_relationship_calculus_live.py`, and four integration tests in `test_custom_world_system.py`. Added network-safety autouse fixture in `conftest.py` and `test_ci_network_safety.py`. Added pytest wrappers in verify scripts. Added `frontend/package.json` scripts `test` and `typecheck`; generated `frontend/yarn.lock`. |
| **Reason** | Automate deterministic regression detection on every `emergent` push/PR without OpenRouter, live server, or paid APIs. |
| **Files affected** | `.github/workflows/deterministic-ci.yml`, `backend/pytest.ini`, `backend/tests/conftest.py`, live marker files, verify wrappers, `frontend/package.json`, `frontend/yarn.lock`, `docs/verification.md`, `docs/release-checklist.md`, `docs/current-state.md`, `docs/feature-status.md`, `docs/next-work.md`, `docs/change-history.md` |
| **Tests run** | Backend: `python -m pytest -m "not live" -q` → **205 passed**, 34 deselected. Frontend: `yarn test` → **17 passed**; `yarn typecheck` → clean |
| **CI boundary** | Proves deterministic backend/frontend surfaces; excludes live OpenRouter, provider fallback, long-run quality, browser/mobile |
| **Dependency note** | Removed unused `emergentintegrations==0.1.0` from `requirements.txt`; CI installs exact committed file |
| **Hardening patch** | Deleted `frontend/package-lock.json` (Yarn canonical); fixed `verify_p2_consequences_rumours.py` path + pytest wrapper → **205** deterministic tests |

---

## 2026-06-20 — Early-Game Pacing Governor v1

| Field | Detail |
|-------|--------|
| **Change** | Added `backend/pacing.py` (stage mapping, non-persisted directives, Stage 1 structural validation, pacing retry instruction). Wired into `server.py` `_build_messages`, `_full_validate`, `_generate_validated_turn`, and strengthened `_create_new_story` genesis contract. Added `backend/tests/test_early_game_pacing.py` (46 tests). Updated `test_gateway_e2e.py` Turn 1 fixture for Stage 1 required fields. |
| **Reason** | Reduce slow atmospheric openings without claiming prompt instructions constitute an autonomous world heartbeat. |
| **Files affected** | `backend/pacing.py`, `backend/server.py`, `backend/tests/test_early_game_pacing.py`, `backend/tests/test_gateway_e2e.py`, `docs/current-state.md`, `docs/feature-status.md`, `docs/failure-modes.md`, `docs/decision-log.md`, `docs/next-work.md`, `docs/change-history.md` |
| **Tests run** | `pytest tests/test_early_game_pacing.py tests/test_security.py tests/test_anti_hallucination_gateway.py tests/test_relationship_calculus.py tests/test_hud.py tests/test_gateway_e2e.py tests/verify_p0_object_permanence.py tests/verify_p1_immersion_integrity.py tests/verify_p15_microfixes.py -q` → **118 passed** |
| **Documentation updated** | Listed above |
| **Decision-log entry** | ADR-016 |
| **Remaining risks** | Semantic opening quality provider-dependent; Living World Test unresolved; Stage 3 green test proves directive plumbing only |

---

## 2026-06-17 — P0/P1 security hardening (rate limits + allowlists + minimal health)

| Field | Detail |
|-------|--------|
| **Change** | Added `rate_limit.py` (MongoDB quotas before LLM on `/story/new`); `player_api.py` allowlist serializers; minimal `/health`; generic 502 errors; operator raw export without device credential; removed public admin client code; crypto UUID generation; `test_rate_limit.py`, `test_player_api.py`. |
| **Reason** | Release-gate blockers: paid-endpoint abuse, denylist leak risk, health oversharing, operator access model alignment. |
| **Tests run** | Deterministic bundle **83 passed**; live `test_story_engine` / `test_custom_world_system` **blocked** (invalid `OPENROUTER_API_KEY` placeholder) |
| **Documentation updated** | `api.md`, `architecture.md` (pending), `current-state.md`, `failure-modes.md`, `feature-status.md`, `system-doctrine.md`, `verification.md`, `release-checklist.md`, `decision-log.md` (ADR-013) |
| **Decision-log entry** | ADR-013 |

---

## 2026-06-17 — P0 security increment (ownership + admin auth + safe export)

| Field | Detail |
|-------|--------|
| **Change** | Added `backend/security.py`; enforced `device_id` ownership on protected routes; admin routes require `ADMIN_API_KEY`; split player `/export` (sanitised) from `/export/raw` (admin + ownership); updated frontend API calls; added `test_security.py` (20 cases). |
| **Reason** | Close confirmed access-control defects without changing story-engine/gateway/relationship/HUD behaviour. |
| **Files affected** | `backend/security.py`, `backend/server.py`, `backend/tests/test_security.py`, `frontend/src/api.ts`, `frontend/app/play/[id].tsx`, `frontend/app/index.tsx`, test updates, `docs/*` |
| **Tests run** | `pytest tests/test_security.py` + 47-test deterministic bundle → **67 passed**; `npx tsc --noEmit` ✅ |
| **Documentation updated** | `api.md`, `architecture.md`, `current-state.md`, `failure-modes.md`, `feature-status.md`, `system-doctrine.md`, `verification.md`, `release-checklist.md`, `next-work.md`, `decision-log.md` (ADR-012) |
| **Decision-log entry** | ADR-012 |
| **Remaining risks** | Device UUID leak still grants access; Settings admin UI needs operator proxy; CORS `*`; no rate limiting |

---

## 2026-06-17 — Reconcile documentation with `emergent` runtime (pass 3)

| Field | Detail |
|-------|--------|
| **Change** | Re-audited all operational docs against `emergent` branch code. Documented `gateway.py`, `relationships.py`, `hud.py`. Corrected branch references from `main` to `emergent`. Re-ran 47-test deterministic bundle. Re-audited security findings. Labeled `memory/PRD.md` as planning tracker only. Removed scoring-equivalence / NaN-ranking from backlog. |
| **Reason** | Pass 1–2 docs were authored against `main` (no gateway/relationship/HUD), committed on `main`, cherry-picked to `emergent` (`a0f2bcc`) without runtime re-audit — causing false claims about missing systems and omitted emergent modules. |
| **Files affected** | `docs/current-state.md`, `system-doctrine.md`, `feature-status.md`, `failure-modes.md`, `decision-log.md`, `architecture.md`, `story-engine.md`, `verification.md`, `next-work.md`, `change-history.md`, `README.md` |
| **Tests run** | `pytest tests/test_anti_hallucination_gateway.py tests/test_relationship_calculus.py tests/test_hud.py tests/test_gateway_e2e.py tests/verify_p0_object_permanence.py tests/verify_p1_immersion_integrity.py tests/verify_p15_microfixes.py -q` → **47 passed** |
| **Documentation updated** | All files listed above |
| **Decision-log entry** | ADR-009 (gateway), ADR-010 (relationships), ADR-011 (HUD) documented from commits `b4a2891`, `a52b66d`, `ff1858d` |
| **Remaining risks** | Admin/export unauthenticated; `device_id` partial; live-server tests unverified; PRD verification claims remain Docs-claimed |

---

## 2026-06-17 — Operational and architectural documentation spine (pass 2)

| Field | Detail |
|-------|--------|
| **Change** | Added project-control documents: `current-state.md`, `system-doctrine.md`, `feature-status.md`, `decision-log.md`, `failure-modes.md`, `release-checklist.md`, `next-work.md`, `change-history.md`. Updated `README.md` with grouped index. Minimal `api.md` correction for export/reset schemas. |
| **Reason** | First pass provided technical reference but lacked operational spine, evidence tagging, and ADR-style decision record. |
| **Files affected** | `docs/*.md` (8 new + `README.md` modified + `api.md` minor fix) |
| **Tests run** | `verify_p0` ✅; `verify_p1` ✅; `verify_p15` ✅; `pytest test_custom_world_system.py` ❌ (server not running) |
| **Documentation updated** | All `/docs` files indexed in `README.md` |
| **Decision-log entry** | ADR-001–008 from code evidence |
| **Remaining risks** | **Pass 2 described `main` runtime** — corrected in pass 3; gateway/relationship/HUD omitted |

**Branch error:** Pass 2 committed on `main` (`791824b`), cherry-picked to `emergent` (`a0f2bcc`), docs reverted on `main` (`fc9b6e3`). Pass 2 never re-audited `emergent`-only modules.

---

## 2026-06-17 — Initial technical documentation (pass 1)

| Field | Detail |
|-------|--------|
| **Change** | Created eight system reference documents under `/docs`. |
| **Reason** | Establish codebase-derived technical reference for Dice Reaction. |
| **Files affected** | `docs/README.md`, `overview.md`, `architecture.md`, `api.md`, `development.md`, `story-engine.md`, `frontend.md`, `verification.md` |
| **Tests run** | Not run during pass 1 |
| **Documentation updated** | New `/docs` tree |
| **Decision-log entry** | — |
| **Remaining risks** | Export/reset marked Unknown in `api.md` until pass 2 |

---

## Template for future entries

```markdown
## YYYY-MM-DD — Short title

| Field | Detail |
|-------|--------|
| **Change** | What changed |
| **Reason** | Why |
| **Files affected** | Paths |
| **Tests run** | Commands and results |
| **Documentation updated** | Which docs |
| **Decision-log entry** | ADR-XXX or — |
| **Remaining risks** | Open items |
```