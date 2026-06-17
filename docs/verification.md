# Verification & Backlog

This document summarizes test coverage and verification status from `memory/PRD.md` and the `backend/tests/` directory. For the living PRD, see `memory/PRD.md`.

**Evidence rule:** PRD-dated verification below is **Docs-claimed** unless re-run and recorded in [current-state.md](./current-state.md) or [change-history.md](./change-history.md). Deterministic scripts (`verify_p0_*`, `verify_p1_*`, `verify_p15_*`) were **passed 2026-06-17** without a live server.

## Test commands

```bash
# From backend/
pytest tests/ -q

# From frontend/
yarn tsc --noEmit
yarn lint
```

## Backend test inventory

| File | Framework | Status |
|------|-----------|--------|
| `test_custom_world_system.py` | pytest | Active regression suite |
| `test_story_engine.py` | pytest | **Outdated** — assertions not aligned with current OpenRouter/Haiku runtime |
| `verify_p0_object_permanence.py` | script | P0 object permanence verification |
| `verify_p1_immersion_integrity.py` | script | P1 immersion / leak checks |
| `verify_p15_microfixes.py` | script | P1.5 microfix verification |
| `qa_live_20turn_hostile.py` | script | Live 20-turn hostile stress (needs running server + API key) |

`conftest.py` loads `backend/.env` and `frontend/.env` for `EXPO_PUBLIC_BACKEND_URL`.

## Verification completed — 2026-05-27 (from PRD)

- `/api/health` returned `status=ok`, `llm_configured=true`, `provider=openrouter`
- `/api/admin/settings` and `/api/admin/runtime` returned expected model, fallback, memory, and context budget data
- 3-turn live OpenRouter verification with Haiku:
  - Valid paragraph/choice counts each turn
  - No narrative mechanic leaks
  - Session `turn_count=3`, turns sorted, `rolling_state` present
  - Diagnostics: active model Haiku, no fallback, context under budget
- Browser preview health at `https://chronicle-runtime.preview.emergentagent.com`
- Play screen: no visible `DEBUG`, `ROLLING`, `Roll:`, `Modifiers:`, `<rolling_state>`, `<debug>` in normal player view
- Test sessions deleted after verification

## Verification completed — Custom World upgrade (from PRD)

- `yarn tsc --noEmit` passed
- Python lint passed for backend app code
- Python compile passed for runtime modules
- Backend regression: **30 passed**
- Independent testing: Custom World setup visibility, six sections, chip interactions, custom start, preset regression, mechanic-concealment probe
- Fix verified: `object_locations` seeds independently when custom carried items exist
- Frontend preview verified after restart

## Observations / regressions (from PRD)

- No runtime-breaking regressions confirmed at last verification
- Expo preview functional; historical tunnel errors in `expo.err.log` did not block UI
- Lint tooling not fully clean:
  - `test_story_engine.py`: flake8 `E741` ambiguous variable name
  - Generic JS lint unreliable on TypeScript/TSX for this project

## Backlog (from PRD)

| Priority | Item |
|----------|------|
| P0 | None confirmed |
| P1 | Fresh 20+ turn hostile stress test (state supremacy, object permanence, anti-stagnation) |
| P1 | 15+ turn stress chronicle (rolling compression activation, context budget stability) |
| P1 | Deliberate provider fallback test (invalid primary model, then restore Haiku) |
| P2 | In-app long-run diagnostics summary for dev-unlocked sessions |
| P2 | Share/export-friendly chronicle summary view |

## Items marked Unknown

- Whether P1 backlog stress tests have been run since PRD last update
- CI/CD integration for automated verification
- Coverage metrics or minimum coverage targets
- Production monitoring / alerting setup