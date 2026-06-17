# Development Guide

## Prerequisites

| Tool | Version (from repo) | Purpose |
|------|---------------------|---------|
| Python | 3.12 (inferred from `.venv`) | Backend |
| Node.js | — | Frontend (Expo) |
| Yarn | 1.22.22 (`packageManager` in `package.json`) | Frontend deps |
| MongoDB | — | Session/turn persistence |
| OpenRouter API key | — | LLM completions |

## Backend setup

```bash
cd backend
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Create or edit `backend/.env`:

```env
MONGO_URL=mongodb://127.0.0.1:27017
DB_NAME=dice_reaction
OPENROUTER_API_KEY=your-openrouter-api-key-here
CORS_ORIGINS=*
ENABLE_DEBUG_PANEL=true
```

Optional overrides (see `ai_config.py` / `ai_service.py`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEFAULT_MODEL` | `anthropic/claude-3-5-haiku` | Primary model |
| `FALLBACK_MODELS` | CSV of model IDs | Fallback chain |
| `DEFAULT_TEMPERATURE` | `0.85` | Sampling |
| `DEFAULT_MAX_TOKENS` | `2048` | Completion cap |
| `DEFAULT_HISTORY_WINDOW` | `40` | History replay cap |
| `MAX_RETRIES` | `2` | Retries per model |
| `PROVIDER_TIMEOUT` | `180` | HTTP timeout (seconds) |
| `COST_MODE` | `normal` | `normal` or `low` |
| `NORMAL_CONTEXT_BUDGET_TOKENS` | `12000` | Prompt budget |
| `LOW_COST_CONTEXT_BUDGET_TOKENS` | `7000` | Low-cost budget |
| `ADVANCED_CONTEXT_BUDGET_TOKENS` | `16000` | Advanced mode budget |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | API base |
| `APP_PUBLIC_URL` | example URL | OpenRouter referer header |
| `APP_TITLE` | `Dice Reaction Story Engine` | OpenRouter title header |

Start the server:

```bash
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Verify:

```bash
curl http://localhost:8000/api/health
```

## Frontend setup

```bash
cd frontend
yarn install
```

Create or edit `frontend/.env`:

```env
EXPO_PUBLIC_BACKEND_URL=http://localhost:8000
```

No trailing slash on the backend URL.

Start Expo:

```bash
yarn start          # interactive dev server
yarn web            # web only
yarn android        # Android
yarn ios            # iOS
```

## Verification commands

From `AGENTS.md` and `memory/PRD.md`:

```bash
# Backend tests (from backend/)
pytest tests/ -q

# Frontend typecheck (from frontend/)
yarn tsc --noEmit

# Frontend lint (from frontend/)
yarn lint
```

### Test layout

| Path | Type | Notes |
|------|------|-------|
| `tests/test_custom_world_system.py` | pytest | Custom World regression |
| `tests/test_story_engine.py` | pytest | **Outdated** — update before treating failures as regressions |
| `tests/verify_p0_object_permanence.py` | standalone script | Object permanence checks |
| `tests/verify_p1_immersion_integrity.py` | standalone script | Immersion leak checks |
| `tests/verify_p15_microfixes.py` | standalone script | Microfix verification |
| `tests/qa_live_20turn_hostile.py` | live QA script | 20+ turn hostile stress (requires running server + API key) |

Integration tests read `EXPO_PUBLIC_BACKEND_URL` from `frontend/.env` via `conftest.py`.

## Developer unlock flow

1. Open Settings.
2. Tap the version row 7 times within 2 seconds.
3. Client sets `developerUnlocked: true` in AsyncStorage.
4. Client calls `POST /admin/settings` with `developer_mode: true`.
5. Play screen exposes diagnostics panel; API returns `rolling_state`, `debug`, `raw`.

Lock developer access reverses both local and server flags.

## Coding guidelines

See `AGENTS.md`:

- State is truth; narrative is output.
- Prefer small, testable changes.
- Do not remove tests to make builds pass.
- Run lint/build/tests where available.

## Known tooling gaps

- `test_story_engine.py` has a flake8 `E741` style issue and outdated assertions.
- Generic JS lint may not parse TypeScript/TSX reliably for this Expo project.
- `httpx` is required by `ai_service.py` but not explicitly pinned in `requirements.txt` (**Unknown** whether always installed transitively).

## Deployment

**Unknown:** No Dockerfile, CI config, or deployment manifest was found in the inspected repository. `memory/PRD.md` references a preview URL (`chronicle-runtime.preview.emergentagent.com`) from a prior verification run; that is environment-specific and not defined in source.