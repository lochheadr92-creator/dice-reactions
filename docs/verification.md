# Verification & Backlog

Test coverage and verification status for the **`emergent`** branch.

**Evidence rule:** `memory/PRD.md` is the **planning and Source-of-Truth conformance tracker** — not runtime truth. PRD-dated verification below is **Docs-claimed** unless re-run and recorded in [current-state.md](./current-state.md) or [change-history.md](./change-history.md).

## GitHub Actions — Deterministic CI

**Workflow:** `.github/workflows/deterministic-ci.yml`

| Setting | Value |
|---------|-------|
| Triggers | `push` to `emergent`, `pull_request` targeting `emergent`, `workflow_dispatch` |
| Concurrency | Newer run on same branch/PR cancels in-progress run |
| Permissions | `contents: read` only |
| Backend Python | 3.12 |
| Frontend Node | 20 |
| Frontend Yarn | 1.22.22 |
| MongoDB | Service container `mongo:7` on `localhost:27017` (hermetic — not external Atlas) |

**Backend job command:**

```bash
cd backend
export MONGO_URL=mongodb://localhost:27017
export DB_NAME=dice_reactions_ci
export ADMIN_API_KEY=test-admin-key
python -m pytest -m "not live" -q
```

**Frontend job commands:**

```bash
cd frontend
yarn install --frozen-lockfile
yarn test
yarn typecheck
```

**Passed 2026-06-20 on `emergent` HEAD @ `d8b9caf`:** **390** deterministic backend tests (replayability engine v1, action concurrency, secret reveal, P2 verifier) + **41** frontend Jest tests + TypeScript clean. **Living Cast tests are not on `emergent` HEAD** — they exist only on unmerged `recovery/living-cast-working-tree` and are **not covered by emergent CI**.

**Recovery branch only (`recovery/living-cast-working-tree` @ `4dadb3f` — provisional, unmerged, not deployed):**

```bash
cd backend
python -m pytest \
  tests/test_living_cast_bounded_state.py \
  tests/test_living_cast_finalize.py \
  tests/test_npc_agendas.py \
  tests/test_npc_world_moves.py \
  tests/test_arc_diversity.py \
  tests/test_living_cast_integration.py \
  -q
```

Bounded-state audit, seeded live-gate preflight, and manual `living-cast-proof` scenario apply to the recovery branch only. See [living-cast-live-gate.md](./living-cast-live-gate.md). Live gate remains blocked until merge remediation completes.

**Lint:** `yarn lint` passes locally (exit 0) but is **not** a required CI step in this increment — Expo lint subprocess emits a benign `yarnpkg` shim warning on Windows; no ESLint rule debt was found.

**Backend install:** `python -m pip install -r backend/requirements.txt` (exact committed file; no CI mutation). Stale `emergentintegrations==0.1.0` removed 2026-06-20 — never imported by backend code.

**Frontend install:** Yarn 1.22.22 with `frontend/yarn.lock` only (`package-lock.json` removed).

## Deterministic test bundle (no live server)

**Local equivalent of CI backend job:**

```bash
cd backend
# PowerShell:
#   $env:MONGO_URL="mongodb://localhost:27017"
#   $env:DB_NAME="dice_reactions_ci"
#   $env:ADMIN_API_KEY="test-admin-key"
python -m pytest -m "not live" -q
# 394 passed, 34 deselected (live)
```

| File | What it covers |
|------|----------------|
| `test_anti_hallucination_gateway.py` | Gateway strip, detect, truth block, registries |
| `test_relationship_calculus.py` | NPC→player vectors, event deltas, LLM injection ignored |
| `test_hud.py` | DNG/MOM vocabularies, objective removal, pressure derivation |
| `test_gateway_e2e.py` | In-process e2e: gateway strip, destruction, relationship turn |
| `verify_p0_object_permanence.py` | Object permanence scenarios |
| `verify_p1_immersion_integrity.py` | Immersion / leak validator |
| `verify_p15_microfixes.py` | P1.5 microfix scenarios |

## Full test commands

```bash
# From backend/ — all tests (many need live server)
pytest tests/ -q

# From frontend/
yarn tsc --noEmit
yarn lint
```

## Backend test inventory

| File | Framework | Status |
|------|-----------|--------|
| `test_anti_hallucination_gateway.py` | pytest | ✅ Passed 2026-06-17 (offline) |
| `test_relationship_calculus.py` | pytest | ✅ Passed 2026-06-17 (offline) |
| `test_hud.py` | pytest | ✅ Passed 2026-06-17 (offline) |
| `test_security.py` | pytest | ✅ Passed 2026-06-17 (20 cases, offline, needs `ADMIN_API_KEY` + MongoDB) |
| `test_gateway_e2e.py` | pytest | ✅ Passed 2026-06-17 (offline) |
| `verify_p0_object_permanence.py` | script | ✅ Passed 2026-06-17 |
| `verify_p1_immersion_integrity.py` | script | ✅ Passed 2026-06-17 |
| `verify_p15_microfixes.py` | script | ✅ Passed 2026-06-17 |
| `test_early_game_pacing.py` | pytest | ✅ Passed 2026-06-20 (offline, MongoDB) |
| `test_http_integration.py` | pytest | ✅ Passed 2026-06-20 (TestClient + mocked LLM) |
| `test_onboarding_hooks.py` | pytest | ✅ Passed 2026-06-20 (offline) |
| `test_secret_reveal.py` | pytest | ✅ Passed 2026-06-20 (offline, explicit confession reveal) |
| `test_run_identity.py` | pytest | ✅ Passed 2026-06-20 (offline, replayability identity) |
| `test_opening_state.py` | pytest | ✅ Passed 2026-06-20 (offline, opening archetypes) |
| `test_pressure_graph.py` | pytest | ✅ Passed 2026-06-20 (offline, pressure graph) |
| `test_consequence_echoes.py` | pytest | ✅ Passed 2026-06-20 (offline, consequence echoes) |
| `test_replayability_integration.py` | pytest | ✅ Passed 2026-06-20 (offline, server integration) |
| `test_action_concurrency.py` | pytest | ✅ Passed 2026-06-20 (offline, per-session action lease + HTTP 409) |
| `test_provider_selection.py` | pytest | ✅ Passed 2026-06-20 (offline) |
| `test_ci_network_safety.py` | pytest | ✅ Passed 2026-06-20 (gateway chokepoint guard) |
| `test_custom_world_system.py` | pytest | **Mixed** — 3 unit guards ✅ in CI; 4 integration tests marked `@pytest.mark.live` |
| `test_story_engine.py` | pytest | **Live only** — `@pytest.mark.live` (24 tests) |
| `test_gateway_live_probe.py` | pytest | **Live only** — `@pytest.mark.live` (5 tests) |
| `test_relationship_calculus_live.py` | pytest | **Live only** — `@pytest.mark.live` (2 tests) |
| `qa_live_20turn_hostile.py` | script | **Unverified** — live 20-turn stress |
| `qa_live_20turn_full_stack.py` | script | **Unverified** — live full-stack stress |
| `qa_live_20turn_p2_stack.py` | script | **Unverified** — live P2 stress |
| `verify_p2_consequences_rumours.py` | pytest | ✅ Passed 2026-06-20 (offline, delayed consequences + rumour propagation) |

`conftest.py` loads `backend/.env` and `frontend/.env` for `EXPO_PUBLIC_BACKEND_URL`.

## Live tests (excluded from CI via `@pytest.mark.live`)

Run manually when a live stack is available:

```bash
cd backend
export EXPO_PUBLIC_BACKEND_URL=http://localhost:8000
export OPENROUTER_API_KEY=sk-or-...
uvicorn server:app --port 8000   # separate terminal
python -m pytest -m live -q
```

| Module | Count | Requires |
|--------|-------|----------|
| `test_story_engine.py` | 24 | Running FastAPI + OpenRouter |
| `test_custom_world_system.py` (live only) | 4 | Running FastAPI + OpenRouter |
| `test_gateway_live_probe.py` | 5 | Running FastAPI + OpenRouter |
| `test_relationship_calculus_live.py` | 2 | Running FastAPI + OpenRouter + export |

**Not collected by default pytest:**

- `qa_live_20turn_*.py` — long-run stress scripts (`if __name__` only)


Security coverage: `test_security.py` — ownership (10), admin auth (5), export safety (5). Requires `ADMIN_API_KEY` in test environment.

## Verification completed — 2026-05-27 (Docs-claimed, from PRD)

- `/api/health` returned `status=ok`, `llm_configured=true`, `provider=openrouter`
- `/api/admin/settings` and `/api/admin/runtime` returned expected model, fallback, memory, and context budget data
- 3-turn live OpenRouter verification with Haiku
- Browser preview health at `https://narrative-hooks.preview.emergentagent.com`
- Play screen mechanic-concealment browser automation
- Test sessions deleted after verification

**Note:** PRD verification predates gateway/relationship/HUD modules on `emergent`. Treat as historical planning evidence.

## Verification completed — Custom World upgrade (Docs-claimed, from PRD)

- `yarn tsc --noEmit` passed
- Python lint passed for backend app code
- Backend regression: **30 passed** (superseded locally by **47 passed** deterministic bundle on `emergent`)
- Custom World setup visibility, preset regression, mechanic-concealment probe

## What CI proves (2026-06-20)

- Early-game pacing (Stage 1 structural validation, directive plumbing, context-budget protection)
- Anti-Hallucination Gateway deterministic strip/detect/registry behaviour
- Gateway end-to-end with mocked `invoke_llm`
- Relationship calculus (engine-owned vectors, event deltas)
- HUD shaping (DNG/MOM/PRS vocabularies, pressure derivation)
- Security (ownership, admin auth, export safety, player route sanitisation)
- Rate limiting (Mongo quotas, trusted-proxy extraction)
- Player API allowlist sanitisation
- Onboarding hooks and secret concealment
- Object permanence, immersion integrity, microfix regression scenarios
- P2 delayed consequences and rumour propagation (`verify_p2_consequences_rumours.py`)
- Secret reveal on explicit player confession (`test_secret_reveal.py`)
- Hermetic HTTP integration (TestClient + mocked LLM)
- Provider selection routing (no live calls — network-safety autouse fixture)
- New Chronicle frontend: Quick Start, Guided Start, Advanced Builder extraction, duplicate-submit, payload mapping, mode isolation, large font scale
- Frontend API errors: typed `ApiError`, 409 friendly copy, legacy 402/429/5xx mappings
- Play-screen action conflict: 409 preserves input, read-only sync, turn merge dedupe, bounded polling, control recovery

## What CI does not prove

- Live OpenRouter behaviour or provider fallback under outage
- Long-run Chronicle quality (20+ turns)
- Autonomous world movement / living-world heartbeat
- Live MongoDB integration against Atlas or production topology
- Browser rendering or mobile device behaviour
- Custom World live integration (`test_custom_world_system.py` live tests)
- Full `test_story_engine.py` API contract against real LLM output
- Automatic secret reveal timing, NPC evidence discovery, or semantic confession inference
- Natural provider prose quality when reacting to a confession

## Observations / regressions

- No runtime-breaking regressions in **390** deterministic backend tests on `emergent` HEAD (2026-06-20)
- Prior docs described `main` branch — missing gateway/relationship/HUD; corrected in reconciliation pass
- Lint tooling not fully clean: `test_story_engine.py` flake8 `E741` (Docs-claimed)

## Backlog (confirmed gaps, not speculative scoring work)

| Priority | Item |
|----------|------|
| P0 | Configure `ADMIN_API_KEY` in deployment; operator admin workflow |
| P1 | Run live-server test bundle; update/quarantine `test_story_engine.py` |
| P1 | Fresh 20+ turn hostile stress test |
| P1 | 15+ turn stress chronicle (compression + context budget) |
| P1 | Deliberate provider fallback test |
| P1 | Pin `httpx` in `requirements.txt` |
| P2 | ~~CI job for deterministic bundle~~ ✅ `.github/workflows/deterministic-ci.yml` |
| P2 | In-app long-run diagnostics summary |
| P2 | Share/export-friendly chronicle summary view |

## Explicitly not in backlog

- Historical scoring equivalence — never existed in this repo
- NaN/infinity ranking guards — never existed in this repo

Do not schedule unless a future subsystem introduces scoring/ranking.

## Items marked Unknown

- Whether P1 live stress tests have been run since PRD last update
- ~~CI/CD integration for automated verification~~ — **resolved** 2026-06-20 (`deterministic-ci.yml`)
- Coverage metrics or minimum coverage targets
- Production monitoring / alerting setup
- Frontend `tsc` ✅ and Jest ✅ on `emergent` HEAD 2026-06-20; lint clean but excluded from required CI