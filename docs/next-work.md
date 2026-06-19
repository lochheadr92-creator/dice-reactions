# Next Work

Practical backlog from confirmed repo gaps on the **`emergent`** branch. No speculative product features. Scoring-equivalence and NaN-ranking items are **excluded** — those symbols never existed in this repository.

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

### NW-P2-03: CI pipeline for deterministic bundle

| Field | Detail |
|-------|--------|
| **Problem** | No GitHub Actions / CI config; 47-test bundle run manually only. |
| **Evidence** | 47 passed 2026-06-17; no `.github/workflows` |
| **Impact** | Regressions on gateway/relationship/HUD undetected on PR |
| **Recommended action** | CI job: 47-test pytest bundle + `yarn tsc` |
| **Acceptance criteria** | CI runs deterministic tests without API key |
| **Files** | `.github/workflows/` (future) |
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

- Utility AI (PRD Ch 27)
- Actor resolution / caps (PRD Ch 25)
- Formal event sourcing rebuild
- Gravity retention beyond context budget
- NPC↔NPC relationship edges
- Vector retrieval RAG

**Not applicable to this repo (never existed):** historical scoring equivalence, NaN/infinity ranking guards.