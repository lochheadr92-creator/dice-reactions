# Next Work

Practical backlog from confirmed repo gaps and Unknown items from the first documentation pass. No speculative product features.

---

## P0: Release blockers or data/security risks

### NW-P0-01: Unauthenticated admin and export endpoints

| Field | Detail |
|-------|--------|
| **Problem** | `/api/admin/*` and `/api/story/session/{id}/export` lack authentication; any caller with network access can read full simulation state or change global AI settings. |
| **Evidence** | `server.py` admin routes; `export_session` returns unsanitized `session` + `turns` |
| **Impact** | Credential-less abuse, data leak, cost injection via model changes |
| **Recommended action** | Add API key, session auth, or network-level restriction; sanitize export or require dev auth |
| **Acceptance criteria** | Unauthenticated client receives 401 on admin POST and optionally on export; documented in `api.md` |
| **Files** | `backend/server.py`, `docs/api.md`, `docs/failure-modes.md` |
| **Dependencies** | Deployment auth strategy decision (ADR) |

### NW-P0-02: Session access without device ownership check

| Field | Detail |
|-------|--------|
| **Problem** | `get_session`, `export_session`, `story_action` use `session_id` only; knowing UUID grants access. |
| **Evidence** | `server.py` routes — no `device_id` verification on get/export/action |
| **Impact** | Cross-device chronicle access if ID leaks |
| **Recommended action** | Require `device_id` query/body param and match `session.device_id` |
| **Acceptance criteria** | Mismatched device returns 403; integration test added |
| **Files** | `backend/server.py`, `frontend/src/api.ts` |
| **Dependencies** | NW-P0-01 auth strategy optional but related |

---

## P1: Correctness and verification

### NW-P1-01: Integration tests not runnable in default dev setup

| Field | Detail |
|-------|--------|
| **Problem** | `test_custom_world_system.py` failed with connection refused when backend not running (2026-06-17). |
| **Evidence** | Pytest run output: `localhost:8000` connection refused |
| **Impact** | Regression suite gives false negatives; PRD "30 passed" status stale |
| **Recommended action** | Document server prerequisite in `development.md`; add pytest marker `live` or docker-compose for CI |
| **Acceptance criteria** | `pytest tests/test_custom_world_system.py` passes with documented one-command stack |
| **Files** | `backend/tests/conftest.py`, `docs/development.md`, `docs/release-checklist.md` |
| **Dependencies** | MongoDB + OpenRouter key |

### NW-P1-02: Outdated `test_story_engine.py`

| Field | Detail |
|-------|--------|
| **Problem** | `AGENTS.md` and PRD state assertions are outdated vs Haiku/OpenRouter runtime. |
| **Evidence** | `AGENTS.md` line 59; `memory/PRD.md` observations |
| **Impact** | False regressions or missed regressions |
| **Recommended action** | Update assertions or split into live vs contract tests; fix E741 |
| **Acceptance criteria** | File passes on current stack or is skipped with documented reason |
| **Files** | `backend/tests/test_story_engine.py` |
| **Dependencies** | NW-P1-01 |

### NW-P1-03: Live hostile stress test not executed

| Field | Detail |
|-------|--------|
| **Problem** | `qa_live_20turn_hostile.py` and PRD P1 items (20+ turn, 15+ turn compression) not run in doc passes. |
| **Evidence** | Script exists; not executed 2026-06-17 |
| **Impact** | Long-run guard failures unknown |
| **Recommended action** | Run script; record results in `change-history.md` and `feature-status.md` |
| **Acceptance criteria** | Script completes; failures triaged or filed as P0/P1 |
| **Files** | `backend/tests/qa_live_20turn_hostile.py`, `docs/verification.md` |
| **Dependencies** | NW-P1-01 |

### NW-P1-04: Provider fallback drill

| Field | Detail |
|-------|--------|
| **Problem** | Fallback chain coded but deliberate failure test not recorded. |
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
| **Problem** | `api.md` previously marked export/reset Unknown; no automated contract tests. |
| **Evidence** | `failure-modes.md` FM-17 |
| **Impact** | Frontend share/reset breakage undetected |
| **Recommended action** | Add pytest for export JSON keys and reset turn_count=0 |
| **Acceptance criteria** | Tests pass against live server |
| **Files** | `backend/tests/`, `docs/api.md` |
| **Dependencies** | NW-P1-01 |

### NW-P2-03: Configuration source-of-truth documentation

| Field | Detail |
|-------|--------|
| **Problem** | Code defaults, env, DB overrides, and PRD deployment values disagree in docs. |
| **Evidence** | `overview.md` vs PRD (`history_window`, `max_tokens`, `developer_mode`) |
| **Impact** | Ops/debug confusion |
| **Recommended action** | `/api/health` is canonical for effective runtime; PRD numbers tagged Docs-claimed only |
| **Acceptance criteria** | `current-state.md` updated after each release with health snapshot |
| **Files** | `docs/current-state.md`, `memory/PRD.md` (reference only) |
| **Dependencies** | None |

### NW-P2-04: CI pipeline missing

| Field | Detail |
|-------|--------|
| **Problem** | No GitHub Actions / CI config in repo. |
| **Evidence** | Code search |
| **Impact** | Verification scripts not run on every PR |
| **Recommended action** | CI job: P0/P1/P1.5 scripts + `yarn tsc` |
| **Acceptance criteria** | CI config runs deterministic tests without API key |
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

- Utility AI
- Actor resolution / caps
- Formal event sourcing rebuild
- Gravity retention beyond context budget
- Historical scoring equivalence / NaN guards
- Vector retrieval RAG