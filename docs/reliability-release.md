# Reliability Release — Evidence (2026-10-30)

Scope: recoverable turn persistence, action request idempotency, bounded paid
provider usage, canonical narration (renderer disabled), and the repaired
automated checks / installation contract. Branch `emergent`, starting from
`d670da33b07a6b49352b888d218994b7a3c725f0`. Nothing in this release was
committed, pushed or deployed; the changes sit in the working tree for owner
review.

Evidence rule: everything under **Current results** was executed on
2026-10-30 in the isolated environment described below. Historical figures in
other documents are not re-asserted here.

## Baseline findings reproduced before changes

| Finding | Reproduced | Where |
|---------|------------|-------|
| Two backend tests import stdlib `secrets` instead of `story_secrets` (collection error + 5 failures) | Yes — `ERROR tests/test_secret_reveal.py … module 'secrets' has no attribute …`; a third stale reference read `backend/secrets.py` from disk | `.nw_tmp/logs/baseline-backend.log`, `…-after-import-fix.log` |
| Frontend: 53 Jest tests pass; `tsc` fails on `talent: ""`; ESLint fails with `TypeError: Unexpected array` | Yes | `.nw_tmp/logs/frontend-baseline.log` |
| Interrupted persistence left turn row without session update | Yes — covered by the previous assessment probe; the split-write helpers (`_insert_story_action_turn` → `_cas_update_story_action_session`) existed in `server.py` | code reading; probe output in the assessment evidence |
| Repeated identical action POST created two turns and two provider calls | Yes — `ActionRequest` had no identity; now the legacy (no-id) path keeps that behaviour and is tested as such | `tests/test_action_idempotency.py::test_legacy_request_without_id_is_not_idempotent_and_documented` |
| Creation quotas exhausted but actions still invoked the provider | Yes — no action quota existed | `tests/test_provider_budget.py::test_per_device_action_quota_blocks_before_provider` |
| Mature renderer accepted a rewrite that changed an event | Yes — `render_mature_presentation` accepted any single-`<narrative>` rewrite | `tests/test_canonical_rendering.py` |

## What changed

### Automated checks and installation contract
- Stale imports fixed in `tests/test_action_concurrency.py` and `tests/test_secret_reveal.py` (+ the `secrets.py` path read).
- `frontend/__tests__/new-story.test.tsx`: the empty `talent` is now an explicit malformed-runtime-input cast with an assertion that it is dropped; production types unchanged.
- `frontend/eslint.config.js`: `eslint-config-expo/flat` is an array; wrapped with `defineConfig` so it is flattened. Lint findings revealed afterwards (unused `useRef`, duplicate `react-native` import, `import/first`) fixed; CI runs `yarn lint --max-warnings=0`.
- `frontend/package-lock.json` removed after verifying `yarn install --frozen-lockfile` (Yarn 1.22.22 via Corepack, Node 20).
- `backend/constraints.txt` pins the verified resolution; install with `-c constraints.txt` (works on Windows dev and Linux CI; constraints never force platform-only packages).
- CI: MongoDB 7 is started as a single-node replica set, initiated, waited for a writable primary, and probed with a real commit/abort transaction before tests; frontend job adds lint and web export.
- `backend/.env.example`, `frontend/.env.example` added (placeholders only).

### Recoverable turn persistence (`backend/turn_commit.py`, `action_concurrency.py`)
- Provider generation stays outside the transaction. One multi-document transaction commits the turn row, the session state, the `session_revision` increment, the lease release and the request record — or nothing.
- Commit precondition inside the transaction: lease token + expected `turn_count` + expected `session_revision`. Reset bumps the revision so a stale generation cannot commit even when `turn_count` returns to the same value; delete removes the session under the lease.
- Transient transaction errors re-run the database-only callback (never the provider). Lost commit acknowledgements are resolved by looking up the committed turn by id; if that is impossible the request is marked `uncertain` and resolved from the database on the next read.
- Transaction support is checked at startup; without it, paid writes return 503 and read-only routes continue. No split-write fallback exists.
- Story creation commits the opening turn and the session completion the same way.
- Reset/delete acquire the same lease (409 while an action runs) and commit transactionally.
- Lease release after commit is quiet and can never turn a committed turn into a failed request.
- `GET /admin/consistency`: read-only diagnostic for mismatched counts, orphaned turns, duplicate turn numbers and incomplete request records.

### Action request idempotency (`backend/action_requests.py`, frontend)
- `action_request_id` bound to device, session and a fingerprint of the contents. Completed ids replay the saved turn through the current ownership check and player serializer (no cached response bytes); different contents → 409 mismatch; concurrent duplicates → one commit, the other 409; failed/interrupted/uncertain records are retryable with the same id.
- `GET /story/session/{id}/action/{request_id}` returns player-safe status.
- Frontend keeps one pending action (id + text) per session in storage, reuses it while the outcome is uncertain, polls status instead of resending after a transport failure, restores pending text after reload, and generates a new id only for a deliberately new action. Text is preserved on 409/422/429/502/503 and transport failures.
- Legacy clients without the id keep the old non-idempotent behaviour (documented and tested).

### Bounded paid provider usage (`backend/provider_budget.py`, `rate_limit.py`, `ai_service.py`, `gateway.py`)
- `ai_service.chat_completion_with_meta` refuses to run without an active budget; every attempt (per-model retries, fallbacks, validation retry) reserves from one per-request attempt budget, honours one total deadline (also capping each HTTP timeout), reserves the global attempt quota, and writes a usage record (`started` → `ok`/`error`/`uncertain`, tokens or `telemetry_missing`).
- Per-device action quota; global provider concurrency as an expiring, owner-released lease pool (atomic `$expr` reservation; crashed workers free their slot on expiry; stale tokens cannot release another worker's slot). Story-creation concurrency migrated to the same pool mechanism.
- Input-size limits return 422 before any paid work. Limiter/usage storage failure fails closed (503).
- Routing intent unchanged (primary model, fallback chain, retries per model, cost mode).

### Canonical narration (`backend/mature_rendering.py`)
- `MATURE_RENDERER_ENABLED = False` (not environment-driven). The renderer returns the canonical narrative with `last_status = safe_fallback_renderer_disabled`; capabilities report `mature_renderer_configured: false`; the Advanced builder shows the unavailability. Preferences, saved stories and historical passages are untouched.

## Environment used for verification

| Component | Version / location |
|-----------|--------------------|
| Python | 3.12.10, venv `backend/.venv` (fresh), `pip check` clean |
| Node | 20.20.2 portable (`.nw_tmp/node20`, SHA256 verified against nodejs.org) |
| Yarn | 1.22.22 via Corepack 0.35.0 (`COREPACK_HOME=.nw_tmp/corepack`) |
| MongoDB | 7.0.16 single-node replica set `diceReliability` on 127.0.0.1:27928, data in `.nw_tmp/mongo-reliability`; commit and abort of a real transaction proven before use |
| Browser | Microsoft Edge (local install) driven headless by playwright-core 1.52.0 from `.nw_tmp/pw` |
| Provider | none — deterministic tests block `gateway.invoke_llm`; the rendered UI check used a local fake OpenAI-compatible server (`.nw_tmp/tools/fake_provider.py`) |

Test configuration (process-scoped, never written to repository env files):
`MONGO_URL=mongodb://127.0.0.1:27928/?replicaSet=diceReliability`,
`DB_NAME=dice_reactions_reliability_test`, `ADMIN_API_KEY=local-reliability-test-only`,
`OPENROUTER_API_KEY=`, `OPENAI_API_KEY=`, `NVIDIA_API_KEY=`.

## Current results

### Backend

```powershell
Set-Location backend
& .\.venv\Scripts\python.exe -m pip check          # No broken requirements found.
& .\.venv\Scripts\python.exe -m pytest -m "not live" -q
# 1387 passed, 36 deselected, 6 warnings in 51.46s   (.nw_tmp/logs/final-backend.log, after the review fixes)
```

New suites (run explicitly, same environment):

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_turn_commit.py tests/test_action_idempotency.py tests/test_provider_budget.py tests/test_session_lifecycle.py tests/test_canonical_rendering.py -q
# 58 passed  (included in the 1387 above)
```

Rewritten suites: `tests/test_action_concurrency.py`, `tests/test_secret_reveal.py` (102 passed together), `tests/test_mature_rendering.py`, `tests/test_model_catalogue.py`.

### Frontend (Node 20.20.2, Yarn 1.22.22)

```powershell
Set-Location frontend
corepack.cmd yarn test        # Test Suites: 8 passed; Tests: 70 passed
corepack.cmd yarn typecheck   # clean
corepack.cmd yarn lint --max-warnings=0   # 0 problems
corepack.cmd yarn expo export --platform web --output-dir dist   # Exported: dist
```

New tests: `__tests__/play-action-idempotency.test.tsx` (9), `__tests__/pending-action.test.ts` (8).

### Fresh installation from the final declarations
- Backend: new venv in `.nw_tmp/fresh-venv`, `pip install -r requirements.txt -c constraints.txt` exit 0, `pip check` clean, `pip freeze` identical to `constraints.txt`, `import server` OK.
- Frontend: `.nw_tmp/fresh-frontend` with only `package.json` + `yarn.lock`, `yarn install --frozen-lockfile` exit 0 in 10.9s, `yarn.lock` hash unchanged.

### Rendered UI check (headless Edge, exported web bundle, local backend, fake provider)
Script `.nw_tmp/tools/ui_check.js`; screenshots and `summary.json` in `.nw_tmp/ui-check/`. All 20 steps passed (`.nw_tmp/logs/ui-check-7.log`):
pending submission disables controls → turn appended, input cleared, request carried `action_request_id`; provider failure → friendly alert, text preserved, retry reuses the same id; lost response after a server-side commit (request fetched then aborted at the browser) → committed turn adopted with a single POST; lease conflict → syncing indicator, other action merged, typed text preserved; preserved text sent successfully; rate limit → alert, text preserved (API probe confirmed 429); reload with a pending completed action → recovered once, record cleared; Advanced builder shows renderer unavailability; capabilities report `mature_renderer_configured: false`.

The Claude-in-Chrome extension was not connected, so this check used Playwright against a local Edge instead; it is a rendered browser verification, distinct from the Jest component tests.

### Repository checks
`git diff --check` clean; `git status --short` lists only intended files; nothing committed or pushed.

## Fresh critical review

Performed after implementation: an own pass over transaction boundaries, identity, cancellation, races, lease expiry, bypasses, privacy and compatibility, plus an independent reviewer pass over the full diff. Findings and resolutions:

| # | Finding | Resolution |
|---|---------|------------|
| F1 (medium) | Lease / claim TTL (`ACTION_LOCK_LEASE_SEC`, clamped 60–3600) was independent of `ACTION_GENERATION_DEADLINE_SEC`; a short lease could let a retry take over a still-running action and pay for a second generation (no duplicate commit — the CAS still rejects — but duplicate spend). Dead `renew_claim` helper. | `resolve_lease_seconds()` is floored at deadline + 60s; claim TTL derives from it; dead helper removed; test `test_lease_and_claim_outlive_the_generation_deadline`. |
| F2 (medium) | `/admin/consistency` joined full turn documents and collected every anomaly row in memory. | `$lookup` pipelines project `turn_number` only; counts and samples computed server-side with `$facet`/`$limit`. |
| F3 (low) | Replay/status used the session's debug flag instead of the request's. | `debug_mode` persisted on the request record and used for replay/status (server `developer_mode` still required). |
| F4 (low) | Budget stops during the validation retry were logged as generic exceptions. | Logged with the budget reason and recorded in engine-only meta (`retry_budget_stop`); behaviour (keep first output, no further paid work) unchanged. |
| F5 (low) | `check_transaction_support` required the `hello` command (MongoDB ≥ 4.4.2). | Falls back to `isMaster` on "no such command". |
| F6 (low) | First-ever creation of a lease-pool document could race between workers and surface as 503 once. | `DuplicateKeyError` on the upsert is tolerated. |
| F7 (info) | Device action quota is not refunded when the global attempt quota/budget storage rejects after reservation. | Left as is (same style as story creation); documented. |
| F8 (info) | Delete did not clear the pending-action storage key; recovery cleared text typed after a reload. | Delete clears the key; only text equal to the recovered action is cleared. |

| Area | Result |
|------|--------|
| Transaction boundaries / commit uncertainty | PASS — provider work outside callbacks; ambiguity verified by turn id, never replayed |
| Idempotency / payload identity | PASS — device + session + contents fingerprint; concurrent duplicates admit one |
| Cancellation / interruption | PASS — checkpoint tests at every boundary; interrupted claims marked retryable; lease/claim expiry bounded |
| Cross-worker races | PASS — lease + revision CAS; competing commits admit one |
| Lease expiry / stale worker | PASS — stale token cannot release or commit |
| Usage-limit bypasses | PASS — budget required at `chat_completion_with_meta`; renderer disabled; limiter failure 503 |
| Response privacy / ownership | PASS — allowlist serializers, owner-verified status, identifier-only diagnostics |
| Legacy compatibility | PASS — no-id requests, sessions without `session_revision`, old concurrent-slot document |
| Setup / CI | PASS — replica set init + transaction probe; constraints; lint and export gates |

## Remaining limitations (not claimed)
- **No monetary spending ceiling.** Caps are request/attempt/concurrency counts plus token accounting; no provider pricing is embedded.
- **At most one provider call per request is not guaranteed** under timeouts/transport failures; those attempts are recorded as uncertain usage.
- **Live provider gameplay** was not exercised (no paid calls). The rendered UI check used a fake provider.
- **Mature renderer** is disabled, not redesigned; the wider content system is not independently validated here.
- **Historical data** is only diagnosed (`GET /admin/consistency`), never repaired.
- Deterministic suites assert behaviour with mocked provider responses; production readiness is not claimed from local tests alone.
