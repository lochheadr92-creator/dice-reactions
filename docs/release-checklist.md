# Release Checklist

Distinguishes **runnable today** (commands exist in repo) from **recommended** (not yet implemented).

---

## Before implementation

- [ ] Read `system-doctrine.md` hard invariants for affected area
- [ ] Check `feature-status.md` for current status and known risks
- [ ] Check `decision-log.md` — new architectural choices need ADR or candidate entry
- [ ] Identify guard pipeline touchpoints in `server.py` if changing turn flow
- [ ] Confirm no casual edits to protected `memory.py` key lists without review

---

## Before merge

### Runtime tests (runnable — matches CI)

```bash
# Backend deterministic verification (no live server; needs local MongoDB)
cd backend
export MONGO_URL=mongodb://localhost:27017
export DB_NAME=dice_reactions_ci
export ADMIN_API_KEY=test-admin-key
python -m pytest -m "not live" -q
```

- [ ] Deterministic backend bundle passes (**205** tests as of 2026-06-20)

### Frontend tests (matches CI)

```bash
cd frontend
yarn install --frozen-lockfile
yarn test
yarn typecheck
```

- [ ] Jest New Chronicle suite passes (17 tests)
- [ ] TypeScript passes
- [ ] Lint passes (optional — not required in CI until Expo lint shim warning resolved cross-platform)

### Runtime tests (require live backend + OpenRouter key)

```bash
# Terminal 1
cd backend && uvicorn server:app --reload --port 8000

# Terminal 2
cd backend
pytest tests/test_custom_world_system.py -q
pytest tests/test_story_engine.py -q   # update assertions if outdated
```

- [ ] `test_custom_world_system.py` passes
- [ ] `test_story_engine.py` passes or is explicitly quarantined with issue link

### Recommended (not automated in repo)

- [ ] Historical equivalence tests — **N/A** (no scoring subsystem)
- [ ] Value-trace tests — **not present**; add if scoring added
- [ ] Narrative leakage live probe — manual or browser automation (Docs-claimed in PRD)
- [ ] `python tests/qa_live_20turn_hostile.py` — **runnable** with server + key; not in CI

### API contract verification

- [ ] `curl http://localhost:8000/api/health` returns `status=ok`
- [ ] `POST /api/story/new` shape matches `api.md`
- [ ] `GET /api/story/session/{id}/export` shape matches documented schema
- [ ] `POST /api/story/session/{id}/reset` returns `{ reset: true }` and clears turns

### GitHub Actions (automated on `emergent`)

Workflow: `.github/workflows/deterministic-ci.yml`

- [ ] Backend job green (pytest `-m "not live"`)
- [ ] Frontend job green (`yarn test`, `yarn typecheck`)

### Configuration review

- [ ] `backend/.env`: `MONGO_URL`, `DB_NAME`, `OPENROUTER_API_KEY` set for target env
- [ ] `frontend/.env`: `EXPO_PUBLIC_BACKEND_URL` matches deployment origin (no trailing slash)
- [ ] Compare `/api/health` effective settings vs expected deployment defaults
- [ ] `CORS_ORIGINS` reviewed for production (not `*` unless intentional)

### Authentication / security review

- [ ] `ADMIN_API_KEY` set in production `backend/.env` (not committed)
- [ ] Admin routes return 401 without `X-Admin-Api-Key` (see `test_security.py`)
- [ ] Player `/export` returns sanitised payload only
- [ ] Raw `/export/raw` not exposed to public clients
- [ ] `X-Device-Id` header sent on all protected frontend API calls
- [ ] `developer_mode` default appropriate for production
- [ ] No secrets committed

### Documentation updates

- [ ] `current-state.md` snapshot date if behavior changed
- [ ] `feature-status.md` rows updated
- [ ] `change-history.md` entry added
- [ ] ADR in `decision-log.md` if architecture changed

### Migration / index review

- [ ] **Recommended:** MongoDB indexes for `sessions.device_id`, `turns.session_id`, `turns.turn_number` — **not defined in code today**
- [ ] Data migration plan if `rolling_state` schema changes

### Git diff review

- [ ] No unintended `frontend/yarn.lock` changes (Yarn is canonical; `package-lock.json` removed)
- [ ] No runtime code changes bundled with doc-only PRs
- [ ] Guard pipeline order preserved

### Developer-only feature checks

- [ ] Player routes omit `rolling_state`, `debug`, `raw` even when `developer_mode` true
- [ ] Wrong-device and unknown-session return identical 404 bodies
- [ ] Public Settings has no server-admin controls (operator curl documented in `api.md`)

---

## Before release

All **Before merge** items, plus:

- [ ] Live smoke: create story → 3 actions → reload session → chronicle intact
- [ ] Custom World flow smoke (if release touches setup)
- [ ] Preset scenario smoke (at least one `scenario_id`)
- [ ] Settings save/load round-trip for admin AI settings
- [ ] Provider fallback drill (PRD P1) — **recommended**, manual
- [ ] 15+ turn session for context budget stability — **recommended**, manual
- [ ] Preview deployment URL verified (environment-specific)

---

## After release

- [ ] Record verification results in `change-history.md`
- [ ] Update `current-state.md` and `feature-status.md`
- [ ] Note any Docs-claimed PRD items superseded
- [ ] Monitor OpenRouter errors (429, 402) in client alerts
- [ ] Rollback plan:
  - Revert git release tag / deployment
  - Restore prior `admin_settings` document from backup if model settings changed
  - MongoDB: sessions unaffected by code rollback unless schema migration ran

---

## Command reference (runnable)

| Command | Location | Requires |
|---------|----------|----------|
| `python tests/verify_p0_object_permanence.py` | `backend/` | venv |
| `python tests/verify_p1_immersion_integrity.py` | `backend/` | venv |
| `python tests/verify_p15_microfixes.py` | `backend/` | venv |
| `pytest tests/ -q` | `backend/` | venv + server + API key |
| `python tests/qa_live_20turn_hostile.py` | `backend/` | venv + server + API key |
| `uvicorn server:app --reload --port 8000` | `backend/` | venv + MongoDB |
| `yarn tsc --noEmit` | `frontend/` | yarn install |
| `yarn lint` | `frontend/` | yarn install |
| `yarn start` | `frontend/` | yarn install |