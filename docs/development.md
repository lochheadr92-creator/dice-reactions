# Development Guide

## Prerequisites

| Tool | Version (CI parity) | Purpose |
|------|---------------------|---------|
| Python | 3.12 | Backend |
| Node.js | 20 (LTS) | Frontend (Expo) |
| Yarn | 1.22.22 via Corepack (`packageManager` in `package.json`; no `package-lock.json`) | Frontend deps |
| MongoDB | 7, **replica set or sharded cluster** (transactions required) | Session/turn persistence |
| OpenRouter API key | — | LLM completions (leave empty for deterministic tests) |

**MongoDB must be transaction-capable.** Turn commits, story creation, reset and delete run in multi-document transactions. On a standalone `mongod` the server starts, logs `TRANSACTION SUPPORT UNAVAILABLE`, and answers **503** on every paid write route while read-only story routes keep working. Start a local single-node replica set:

```powershell
mongod --replSet rs0 --bind_ip 127.0.0.1 --port 27017 --dbpath C:\data\rs0
# then once, from a client (mongosh or Python/pymongo):
#   rs.initiate({ _id: "rs0", members: [{ _id: 0, host: "127.0.0.1:27017" }] })
# connection string: mongodb://127.0.0.1:27017/?replicaSet=rs0
```

## Backend setup

```powershell
Set-Location backend
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints.txt
& .\.venv\Scripts\python.exe -m pip check
```

`requirements.txt` declares the direct dependencies; `constraints.txt` pins the exact versions that were installed and verified (Windows dev + Linux CI, Python 3.12). Always install with `-c constraints.txt`; regenerate it only for an intentional upgrade (`python -m pip freeze --exclude-editable | grep -v "^pip==" > constraints.txt`).

Copy `backend/.env.example` to `backend/.env` and fill in real values (never commit `.env`):

```env
MONGO_URL=mongodb://127.0.0.1:27017/?replicaSet=rs0
DB_NAME=dice_reaction
OPENROUTER_API_KEY=your-openrouter-api-key-here
ADMIN_API_KEY=a-long-random-secret
CORS_ORIGINS=*
ENABLE_DEBUG_PANEL=true
```

Optional overrides (see `ai_config.py` / `ai_service.py`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEFAULT_MODEL` | `anthropic/claude-haiku-4.5` | Primary model |
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
| `OPENAI_DIRECT_REASONING_EFFORT` | unset | Sent as `reasoning_effort` only for `openai-direct/*` models. Set `none` for local Ollama thinking models, which otherwise spend `max_tokens` on thinking and return empty content. Set `low` for Grok 4.7 on xAI direct, which reasons at `high` when this is unset and cannot turn reasoning off (measured 2026-11-23: openings 89 s at `low` against 198 to 262 s unset). On this route the engine also joins its leading system messages into one, because some local chat templates (Qwen in Ollama) reject more than one |
| `OPENAI_DIRECT_ASSISTANT_PREFILL` | off | When `true`, story turns on `openai-direct/*` models send `<rolling_state>\n{` as the start of the model's reply, and the engine puts it back on the returned text. The model can no longer skip the required state block. Needs a server that continues a trailing assistant message (Ollama does; real OpenAI does not). Never applied to OpenRouter |
| `SSL_USE_SYSTEM_TRUST_STORE` | off | `true` verifies provider HTTPS against the operating system's trust store (truststore) instead of certifi. Needed when antivirus HTTPS scanning (e.g. Norton Web Shield) re-signs traffic, which otherwise fails with `CERTIFICATE_VERIFY_FAILED`. If truststore is not installed, the engine refuses to start |
| `MATURE_RENDERER_ENABLED` | off | `true` turns on the second-pass mature prose renderer (also needs `MATURE_MODEL_ID`, `DISTRIBUTION_CHANNEL=development` or `adult_web`, `ENABLE_MATURE_CONTENT=true`, and a story created with adult mode on). Known risk: the rewrite can change events (docs/failure-modes.md FM-30). Tests pin it off |
| `MATURE_MODEL_ID` | unset | Pinned model id for the renderer, e.g. `openai-direct/dice-qwen36` (`:latest` ids are refused) |
| `DEFAULT_PROSE_MODE` | `standard` | Narration length for new stories when the app sends no `prose_mode`: `brief` (300-600 chars), `standard` (700-1200), `story` (1800-2400), `cinematic` (3000-4000). Only these four names are accepted; any other value stops the engine at startup. Existing stories keep the mode they were created with. Tests pin it to `standard` |
| `VALIDATION_RETRY_STYLE` | `show_rejected` | How a rejected turn is retried. `show_rejected` appends the rejected reply and a rewrite instruction. `fresh` asks for the turn again with one short correction line on the player's message and does not show the rejected reply. Use `fresh` for local Ollama models: shown its own rejected reply, Qwen writes only the state block and stops (docs/eval, 2026-11-21). Any other value stops the engine at startup. Tests pin `show_rejected` |
| `APP_PUBLIC_URL` | example URL | OpenRouter referer header |
| `APP_TITLE` | `Dice Reaction Story Engine` | OpenRouter title header |

Paid-work limits (`RATE_LIMIT_*`, `PROVIDER_*`, `ACTION_GENERATION_DEADLINE_SEC`, `*_MAX_CHARS`) and their defaults are listed in [api.md](./api.md#paid-provider-controls) and `backend/.env.example`.

Start the server:

```bash
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Verify:

```bash
curl http://localhost:8000/api/health
```

## Frontend setup

```powershell
Set-Location frontend
node --version            # v20.x
corepack enable           # or use `corepack.cmd yarn ...` without enabling shims
corepack yarn --version   # 1.22.22 (from packageManager)
corepack yarn install --frozen-lockfile
```

Only `yarn.lock` is committed; do not add a `package-lock.json`. If `yarn install --frozen-lockfile` fails, fix the declaration rather than regenerating the lockfile to hide the failure.

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

Backend (needs the replica set; the deterministic suite makes no provider calls):

```powershell
Set-Location backend
$env:MONGO_URL = "mongodb://127.0.0.1:27017/?replicaSet=rs0"
$env:ADMIN_API_KEY = "local-test-only"
& .\.venv\Scripts\python.exe -m pip check
& .\.venv\Scripts\python.exe -m pytest -m "not live" -q
```

**Test database guard.** Several test fixtures delete every session and turn in the test database. `tests/conftest.py` (through `tests/db_guard.py`) therefore never uses `DB_NAME` from the shell or `backend/.env`: it always runs against `TEST_DB_NAME` (default `dice_reactions_test`), refuses to start unless that name ends in `_test`, does not load `backend/.env`, and sets provider keys to empty unless the shell exports them. Your saved stories in the database named in `backend/.env` are never touched by a test run.

Frontend (Node 20):

```powershell
Set-Location frontend
corepack yarn test
corepack yarn typecheck
corepack yarn lint --max-warnings=0
corepack yarn expo export --platform web --output-dir dist
```

See [verification.md](./verification.md) for the CI definition and the test inventory, and [reliability-release.md](./reliability-release.md) for the reliability-release evidence.

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

- `test_story_engine.py` targets a live server (`live` marker) and has outdated assertions.
- `expo lint` prints a benign `yarnpkg` shim warning on Windows.

## Deployment prerequisites

- MongoDB 7 **replica set or sharded cluster** (transactions). Verify after deploy: `GET /api/admin/consistency` → `transaction_support_error` must be `null`.
- Node 20 / Yarn 1.22.22 for web export; Python 3.12 with `constraints.txt` for the backend.
- `ADMIN_API_KEY` set; provider keys set only on the deployment that should make paid calls.
- Single backend process (one uvicorn without workers, as the Windows launcher runs it): set `CLEAR_LEASES_ON_STARTUP=1` so a restart frees leases left by the previous process instead of blocking those chronicles for up to `ACTION_GENERATION_DEADLINE_SEC` + 60s. Leave it unset with several workers.
- Unique request-key index: startup creates `turns_action_request_key_unique`. Databases created by the first reliability build also keep the older non-unique `turns_action_request_key` index; it is redundant and harmless, and dropping it is an operator choice. If duplicate request keys already exist the unique index is not created and an error is logged; check `GET /api/admin/consistency`.
- Rollback: the release adds collections (`action_requests`, `provider_usage`), indexes, and the `session_revision` / `turns.action_request_key` / `sessions.reset_at` fields. Rolling the code back leaves those in place harmlessly; the previous code ignores them. Rolling forward again normalises `session_revision` lazily on the next lease acquisition. No data migration is required or performed.
- No Dockerfile or deployment manifest exists in the repository; CI is `.github/workflows/deterministic-ci.yml`.
