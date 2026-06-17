# Verification & Backlog

Test coverage and verification status for the **`emergent`** branch.

**Evidence rule:** `memory/PRD.md` is the **planning and Source-of-Truth conformance tracker** — not runtime truth. PRD-dated verification below is **Docs-claimed** unless re-run and recorded in [current-state.md](./current-state.md) or [change-history.md](./change-history.md).

## Deterministic test bundle (no live server)

**Passed 2026-06-17 on `emergent`:** 47 tests

```bash
cd backend
pytest tests/test_anti_hallucination_gateway.py \
       tests/test_relationship_calculus.py \
       tests/test_hud.py \
       tests/test_gateway_e2e.py \
       tests/verify_p0_object_permanence.py \
       tests/verify_p1_immersion_integrity.py \
       tests/verify_p15_microfixes.py -q
# 47 passed
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
| `test_gateway_e2e.py` | pytest | ✅ Passed 2026-06-17 (offline) |
| `verify_p0_object_permanence.py` | script | ✅ Passed 2026-06-17 |
| `verify_p1_immersion_integrity.py` | script | ✅ Passed 2026-06-17 |
| `verify_p15_microfixes.py` | script | ✅ Passed 2026-06-17 |
| `test_custom_world_system.py` | pytest | **Unverified** — needs live server |
| `test_story_engine.py` | pytest | **Unverified** — outdated assertions (Docs-claimed) |
| `test_gateway_live_probe.py` | pytest | **Unverified** — needs live server + OpenRouter |
| `test_relationship_calculus_live.py` | pytest | **Unverified** — needs live server + export |
| `qa_live_20turn_hostile.py` | script | **Unverified** — live 20-turn stress |
| `qa_live_20turn_full_stack.py` | script | **Unverified** — live full-stack stress |
| `qa_live_20turn_p2_stack.py` | script | **Unverified** — live P2 stress |
| `verify_p2_consequences_rumours.py` | script | **Unverified** — hardcoded `/app/backend` path |

`conftest.py` loads `backend/.env` and `frontend/.env` for `EXPO_PUBLIC_BACKEND_URL`.

## Live-server tests (unverified in this pass)

These require MongoDB, Uvicorn on `localhost:8000` (or `EXPO_PUBLIC_BACKEND_URL`), and `OPENROUTER_API_KEY`:

- `test_custom_world_system.py` — integration + unit guards
- `test_story_engine.py` — full API contract (stale)
- `test_gateway_live_probe.py` — live LLM gateway probe
- `test_relationship_calculus_live.py` — live relationship events via `/export`
- `qa_live_20turn_*.py` — long-run stress scripts
- `verify_p2_consequences_rumours.py` — P2 rumour propagation (path may not match local tree)

No security-specific automated tests exist for admin auth, export auth, or `device_id` ownership.

## Verification completed — 2026-05-27 (Docs-claimed, from PRD)

- `/api/health` returned `status=ok`, `llm_configured=true`, `provider=openrouter`
- `/api/admin/settings` and `/api/admin/runtime` returned expected model, fallback, memory, and context budget data
- 3-turn live OpenRouter verification with Haiku
- Browser preview health at `https://chronicle-runtime.preview.emergentagent.com`
- Play screen mechanic-concealment browser automation
- Test sessions deleted after verification

**Note:** PRD verification predates gateway/relationship/HUD modules on `emergent`. Treat as historical planning evidence.

## Verification completed — Custom World upgrade (Docs-claimed, from PRD)

- `yarn tsc --noEmit` passed
- Python lint passed for backend app code
- Backend regression: **30 passed** (superseded locally by **47 passed** deterministic bundle on `emergent`)
- Custom World setup visibility, preset regression, mechanic-concealment probe

## Observations / regressions

- No runtime-breaking regressions confirmed in 47-test bundle (2026-06-17)
- Prior docs described `main` branch — missing gateway/relationship/HUD; corrected in reconciliation pass
- Lint tooling not fully clean: `test_story_engine.py` flake8 `E741` (Docs-claimed)

## Backlog (confirmed gaps, not speculative scoring work)

| Priority | Item |
|----------|------|
| P0 | Admin + export authentication; `device_id` ownership on all session routes |
| P1 | Run live-server test bundle; update/quarantine `test_story_engine.py` |
| P1 | Fresh 20+ turn hostile stress test |
| P1 | 15+ turn stress chronicle (compression + context budget) |
| P1 | Deliberate provider fallback test |
| P1 | Pin `httpx` in `requirements.txt` |
| P2 | CI job for 47-test deterministic bundle |
| P2 | In-app long-run diagnostics summary |
| P2 | Share/export-friendly chronicle summary view |

## Explicitly not in backlog

- Historical scoring equivalence — never existed in this repo
- NaN/infinity ranking guards — never existed in this repo

Do not schedule unless a future subsystem introduces scoring/ranking.

## Items marked Unknown

- Whether P1 live stress tests have been run since PRD last update
- CI/CD integration for automated verification
- Coverage metrics or minimum coverage targets
- Production monitoring / alerting setup
- Frontend `tsc` / `lint` status on current `emergent` HEAD