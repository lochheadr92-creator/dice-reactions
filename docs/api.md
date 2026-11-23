# API Reference

Base URL: `{EXPO_PUBLIC_BACKEND_URL}/api`

The frontend constructs this from `src/theme.ts`:

```
API = process.env.EXPO_PUBLIC_BACKEND_URL + "/api"
```

All endpoints below are relative to `/api`.

## Health & metadata

### `GET /`

Returns engine identification message.

**Response:** `{ "message": "Dice Reaction Story Engine v3.3" }`

### `GET /health`

Minimal uptime probe. Does not expose model names, runtime configuration, or admin flags.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"ok"` when reachable |
| `llm_configured` | boolean | Whether the configured story model route has what it needs (`ai_service.is_configured`). Covers OpenRouter, the direct OpenAI-compatible route and the NVIDIA route. It does not say which route is in use. |

Full AI settings: `GET /api/admin/settings` (requires `X-Admin-Api-Key`).

## Scenarios

### `GET /scenarios`

List curated scenario presets (seed paragraphs omitted).

**Response:** `{ "scenarios": Scenario[] }`

Each scenario includes: `id`, `title`, `pitch`, `genre`, `role`, `tone`, `difficulty`, `mode`, `starting_location`, `starting_pressure`, `key_npcs`, `starting_inventory`, `hidden_threat`.

Known scenario IDs:
- `suburban-collapse`
- `dinosaur-containment-breach`
- `cosmic-horror-road-town`

## Story flow

### `POST /story/new`

Start a new chronicle.

**Request body (`NewStoryRequest`):**

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `device_id` | yes | string | Client device UUID |
| `genre` | yes | string | e.g. `fantasy`, `cosmic horror` |
| `role` | no | string | Player role |
| `tone` | no | string | Narrative tone |
| `difficulty` | no | string | `soft`, `standard`, `hard`, `brutal` (default `standard`) |
| `debug_mode` | no | boolean | Request debug blocks from model |
| `custom_premise` | no | string | Legacy free-text premise. Still accepted. The builders send the player's premise in `custom_world_setup.premise` |
| `mode` | no | string | `basic` or `advanced` |
| `scenario_id` | no | string | Curated scenario override |
| `custom_world_setup` | no | object | Builder answers (see `CustomWorldSetup` in `frontend/src/api.ts`). Includes `premise` (the player's own premise, at most 600 characters kept), `timePeriod`, `recentChange` and the other Guided and Advanced answers |
| `prose_mode` | no | string | Turn length. `brief`, `standard`, `story`, `cinematic`, or the aliases `S`, `M`, `L`, `XL`. Paragraph ranges 1 to 2, 2 to 4, 4 to 6, 6 to 8 |
| `prose_style` | no | string | Writing style. `plain`, `balanced` or `rich`. At most 32 characters |
| `thinking_effort` | no | string | Speed. `low`, `medium` or `high`. At most 32 characters. Used only when the direct route is configured with a named effort |

Text the player types (genre, role, tone, premise, custom answers) reaches the model as bounded story data in a `<player_story_data>` block in the final user message, never as part of an engine instruction. See `docs/story-engine.md`.

**Response:** `{ session_id, turn, session }` — player allowlist serializers only (`player_api.py`). No `device_id`, `rolling_state`, `debug`, or engine metadata in responses.

**Input limits (422 before any paid work):** short fields (`genre`, `role`, `tone`, `difficulty`, `mode`, `prose_mode`, `scenario_id`) ≤ `CREATION_SHORT_FIELD_MAX_CHARS` (200); `custom_premise` and every string inside `custom_world_setup` / `mature_content` ≤ `CREATION_TEXT_FIELD_MAX_CHARS` (2000); all `custom_world_setup` text combined ≤ `CREATION_SETUP_TOTAL_MAX_CHARS` (12000). The serialized JSON of `custom_world_setup` (keys, numbers and empty values included) ≤ `CREATION_SETUP_JSON_MAX_CHARS` (16000), and of `mature_content` ≤ `MATURE_CONTENT_JSON_MAX_CHARS` (8000). The `detail` names the field and the limit. Any request body over `MAX_REQUEST_BODY_BYTES` (262144) is refused with **413** `{ "detail": "Request body too large" }` before the route runs.

**Failed creations leave nothing behind:** any error or cancellation after the provisional session is inserted and before the opening commit is attempted deletes that session. A provisional session older than `ACTION_GENERATION_DEADLINE_SEC` + 60s (a creation that died, for example a killed process) is removed when the client retries with the same `creation_request_id`, and the retry creates the story; a younger one still answers **409** `Story creation already in progress`.

**Persistence:** the opening turn, the session completion (`turn_count`, state, model lock) and the session revision commit in **one MongoDB transaction** (`turn_commit.commit_opening_turn`). The server refuses story creation with **503** `{ "detail": "Service unavailable" }` when the connected MongoDB cannot run transactions (standalone server).

**Rate limits (enforced before LLM call or session insert):**

| Env variable | Default | Meaning |
|--------------|---------|---------|
| `RATE_LIMIT_IP_MAX` | 10 | Max creations per client IP per window |
| `RATE_LIMIT_IP_WINDOW_SEC` | 3600 | IP window (seconds) |
| `RATE_LIMIT_DEVICE_MAX` | 5 | Max creations per `device_id` per window |
| `RATE_LIMIT_DEVICE_WINDOW_SEC` | 3600 | Device window (seconds) |
| `RATE_LIMIT_GLOBAL_MAX` | 50 | Max total story creations globally per fixed window |
| `RATE_LIMIT_GLOBAL_WINDOW_SEC` | 3600 | Global fixed window (seconds) |
| `RATE_LIMIT_GLOBAL_CONCURRENT` | 3 | Max in-flight story creations (expiring lease pool; a crashed worker's slot frees itself after `STORY_CREATION_LEASE_SEC`, default 600) |
| `TRUSTED_PROXY_COUNT` | 0 | When >0, client IP from `X-Forwarded-For` at `parts[-N]` (requires chain length ≥ N; with N trusted proxies an honest chain has exactly N entries, and entries a client prepends are ignored). **Do not trust `X-Forwarded-For` unless this matches your deployment proxy depth.** |

Story creation also consumes the shared provider controls listed under **Paid-provider controls** below (global concurrency lease, per-request attempt budget, global attempt quota).

Exceeded limits → **429** `{ "detail": "Too many requests" }` (generic; no admin/model details). Limiter backend failure → **503** `{ "detail": "Service unavailable" }` (fail closed). A creation answered with any **4xx** (invalid scenario or settings, duplicate in progress, provider quota refusal) made no provider call and its quota reservation is refunded; **502** answers keep it, because paid work may have happened.

`device_id` in the body is **not** abuse-proof — clients can regenerate UUIDs. IP limits complement device limits.

Scenario fields override client defaults when `scenario_id` is set.

### `POST /story/action`

Submit a player action for the next turn.

**Request body (`ActionRequest`):**

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `session_id` | yes | string | |
| `action_text` | yes | string | non-empty; ≤ `ACTION_TEXT_MAX_CHARS` (default 2000) → otherwise **422** before any paid work |
| `debug_mode` | no | boolean | part of the request identity (see below) |
| `action_request_id` | no | string (≤128) | Client-generated idempotency key. **Strongly recommended.** |

**Header:** `X-Device-Id` (required) — must match the session owner's persisted `device_id`.

**Response:** `{ turn: Turn }` — plus `replayed: true` when the response is the saved result of an already-completed `action_request_id`.

**Idempotency contract (`action_request_id` supplied):**

- One `action_request_id` ⇒ **at most one committed game transition** for that session. The id is bound to the owner device, the session, and a fingerprint of (`action_text` trimmed, `debug_mode`).
- Retrying a **completed** id returns the saved turn (`replayed: true`), rebuilt from the stored turn through the current ownership check and player-safe serializer. It consumes **no** action quota, no provider attempt, and no concurrency slot.
- Reusing an id with **different contents** → **409** `{ "detail": "action_request_id was already used for a different action" }`. Nothing is generated.
- A retry while the first attempt is still running → **409** `{ "detail": "An action is already in progress for this chronicle" }` (same body as the lease conflict). Poll the status endpoint; do not resend with a new id.
- Failed attempts (provider 502, rate limit 429, interrupted request, storage 503) leave the id **retryable** with the same contents. A retry performs new paid work (the first attempt made no transition).
- **At most one external provider call is NOT guaranteed**: a provider timeout or transport failure may have incurred usage even though no transition committed; such attempts are recorded as uncertain usage (`provider_usage.status = "uncertain"`).
- **Legacy clients that omit `action_request_id`** keep the pre-release behaviour: every POST that acquires the lease generates and commits a new turn; nothing is deduplicated and no request record is kept.

**Persistence:** the turn row, the session state (`turn_count`, `rolling_state`, model lock), the session `session_revision` increment, the lease release and the request record commit in **one MongoDB transaction** (`turn_commit.commit_action_turn`). The commit re-verifies the lease token, expected `turn_count` and expected `session_revision` inside the transaction; a stale worker (expired lease, reset/delete in between, competing commit) gets **409** and writes nothing. Lost commit acknowledgements are resolved by looking the committed turn up by id — the mutation is never replayed. If the outcome still cannot be determined the server answers **503** and marks the request `uncertain`; the next status read or retry resolves it from the database.

**Other errors:** **429** `{ "detail": "Too many requests" }` (per-device action quota, global provider attempt quota, or global provider concurrency full — nothing generated, text safe to resend with the same id); **502** `{ "detail": "Story engine unavailable" }` (provider failure or per-request attempt budget/deadline exhausted); **503** `{ "detail": "Service unavailable" }` (limiter/usage storage unavailable, transactions unavailable, or commit outcome unknown).

**Conflict (concurrent action):** When another unexpired action already owns the session lease, the server returns **409** with:

```json
{ "detail": "An action is already in progress for this chronicle" }
```

No lock token, timestamps, internal field names, or player action text are included. The rejected request makes zero provider calls. Successful responses are unchanged.

**Frontend behaviour on 409 (v1):** The play screen does not append a turn from the failed request, does not clear typed custom action, and does not automatically resubmit. It shows a short syncing state, calls read-only `GET /story/session/{id}` (via `getSession`) up to **four** reads with **three** ~1s delays between attempts (~3s bounded polling), merges turns by `turn.id`, and restores controls. Initial friendly copy: title **Chronicle already moving**, message **Checking for the latest turn now** (does not promise sync after polling stops). If no newer turn appears, exhaustion copy tells the player their text was kept and to try again shortly. No lock/lease/token terminology. See `frontend/src/api-error.ts`, `frontend/src/action-conflict-sync.ts`, `frontend/src/chronicle-merge.ts`. After the sync the client also looks up its **own** `action_request_id` via the status endpoint: if that id completed (the conflict was the client's own duplicate) the saved turn is adopted and the input cleared; otherwise the id and text are kept.

**Frontend request-id behaviour:** `frontend/src/pending-action.ts` keeps one pending action per session (`AsyncStorage` key `dice_pending_action:<session_id>`). The same id is reused while the outcome is uncertain (transport failure, 409 lease conflict, 429, 502, 503); a deliberately new action (different text or debug flag) gets a new id. A transport failure never resends blindly — the client polls the status endpoint (`frontend/src/action-status-sync.ts`, up to 4 reads ~1.5s apart) and adopts a completed turn. On reload the pending action is restored into the input and its status queried. A 409 contents mismatch drops the id and keeps the text. 422 keeps the text and frees the id.

### `GET /story/session/{session_id}/action/{request_id}`

Player-safe status of one `action_request_id` (owner-verified; **404** for unknown session or wrong device).

**Header:** `X-Device-Id` (required)

**Response:**

| `status` | Meaning | Extra fields |
|----------|---------|--------------|
| `completed` | The turn committed | `turn` (player-safe) |
| `in_progress` | A worker still holds the claim | — |
| `failed` | No transition happened; retry with the same id is safe | `error_kind`: `provider_unavailable` \| `conflict` \| `rate_limited` \| `validation` \| `storage` \| `interrupted` \| `superseded` |
| `unknown` | The backend never recorded this id | — |

Records expire after 7 days. `uncertain` records (worker lost the commit acknowledgement) are resolved on read: the committed turn is found by id → `completed`, otherwise → `failed` / `storage`.

Turn shape (player-facing responses always omit internal fields):

| Field | Type |
|-------|------|
| `id` | string |
| `session_id` | string |
| `turn_number` | number |
| `player_action` | string \| null |
| `narrative` | string |
| `paragraphs` | string[] |
| `choices` | `{ label, text }[]` |
| `state` | `Record<string, string>` |
| `ledger` | object |
| `rolling_state` | omitted on player routes |
| `debug` | omitted on player routes |
| `created_at` | ISO datetime string |

### `GET /story/sessions`

List sessions for a device.

**Header:** `X-Device-Id` (required)

**Response:** `{ sessions: SessionSummary[] }` — sessions are always sanitised (no `rolling_state`). Provisional sessions (creation still running, or a creation that died) are not listed; reset sessions are.

### `GET /story/session/{session_id}`

Session with its newest turns (at most `TURN_WINDOW_MAX`, default 500, oldest first). Player-facing response is always sanitised.

**Header:** `X-Device-Id` (required) — must match `session.device_id`.

**Response:** `{ session, turns }`

**Errors:** `400` missing `X-Device-Id`; `404` `{ "detail": "Session not found" }` for unknown session or wrong device (indistinguishable).

### `GET /story/session/{session_id}/latest`

Most recent turn only. Turn is always sanitised.

**Header:** `X-Device-Id` (required)

**Response:** `{ turn }`

### `DELETE /story/session/{session_id}`

Delete session, its turns and its action request records in one transaction, under the session lease.

**Header:** `X-Device-Id` (required)

**Response:** `{ deleted: true }`

**Errors:** **409** `{ "detail": "An action is already in progress for this chronicle" }` while an action holds the lease (retry after it finishes or the lease expires); **503** when transactions are unavailable. A generation that outlives the delete can no longer commit (its lease token and session no longer exist).

### `POST /story/session/{session_id}/mode`

Switch simulation mode mid-chronicle.

**Header:** `X-Device-Id` (required)

**Request:** `{ mode: "basic" | "advanced" }`

**Response:** `{ mode }`

### `POST /story/session/{session_id}/play-settings`

Change turn length, writing style or speed for a story you own. `mode` (above) and `prose_mode` are different settings.

**Header:** `X-Device-Id` (required)

**Request:** any of `{ prose_mode, prose_style, thinking_effort }`. Send only what changes. `prose_mode` takes `brief`, `standard`, `story`, `cinematic` or `S`, `M`, `L`, `XL`. `prose_style` takes `plain`, `balanced`, `rich`. `thinking_effort` takes `low`, `medium`, `high`.

**Response:** the accepted values in canonical form, for example `{ "prose_mode": "story" }`.

**Errors:** 400 for an unknown value or a body with no known setting. 422 for a wrong type or an over-long string. 404 when the story does not exist or belongs to another device.

**Effect:** the next action uses the new values. Nothing already written changes. This is a preference, not play: it does not change `updated_at`, so the story keeps its place in the list. It does not touch the turn count, the revision or a held action lease. Values equal to the stored ones write nothing. A real change stamps `settings_updated_at`.

### `GET /story/session/{session_id}/export`

**Player-safe export.** Requires verified session ownership. Always returns sanitised chronicle data — `rolling_state`, `debug`, and `raw` are stripped regardless of server `developer_mode`.

**Header:** `X-Device-Id` (required)

**Response:**

```json
{
  "exported_at": "ISO-8601 datetime",
  "session": { },
  "turns": [ ],
  "summary": {
    "turn_count": 0,
    "turns_included": 0,
    "truncated": false,
    "last_state": { }
  }
}
```

Turns are the newest `TURN_WINDOW_MAX` (default 500), sorted by `turn_number` ascending. `summary.turn_count` is the chronicle's full turn count; `truncated` is `true` when older turns were left out.

### `GET /story/session/{session_id}/export/raw`

**Administrative raw export.** Requires `X-Admin-Api-Key` only (no player device credential). Returns full unsanitised session + turns including `rolling_state`, `debug`, `raw`.

**Header:** `X-Admin-Api-Key` (required)

**Errors:** `401` missing/invalid admin key; `404` unknown session; `503` if `ADMIN_API_KEY` env not configured on server.

Not exposed in the player UI. Not enabled by `developer_mode` alone.

### `POST /story/session/{session_id}/reset`

Delete all turns and clear rolling state; keep session shell (genre, role, difficulty, mode) and mark it with `reset_at`. Runs in one transaction under the session lease and increments `session_revision`, so a stale generation started before the reset can never commit against the reset session (even though `turn_count` returns to 0). The session's action request records are deleted with its turns, the same as a delete, so no record points at a deleted turn; an old `action_request_id` sent again afterwards is a new request for the reset session (its status reads `unknown` until then).

The app's "Reset chronicle" menu no longer calls this endpoint: it deletes the chronicle and opens New Story, so no empty shell is left behind. The endpoint remains for API clients.

**Header:** `X-Device-Id` (required)

**Response:** `{ "reset": true }`

**Errors:** **409** while an action holds the lease; **503** when transactions are unavailable.

Client should start fresh via `POST /story/action` or create a new story.

### `POST /story/session/{session_id}/branch`

Body `{request_id, expected_turn_count?}`. Copies the save at its latest committed decision into a new save with its own id (deterministic from source, device and `request_id`, so a double tap returns the same branch with `replayed: true`). One transaction under the source action lease. No narrator call, no credit, no game time. Pending requests, locks and retry records are not copied. The notebook is not copied. `409` when `expected_turn_count` is stale or a turn is in flight.

### Notebook (private to the player, scoped to one save)

`GET /story/session/{id}/notebook`, `POST .../notebook/pins` (`{turn_number, paragraph_index, start?, end?}`), `DELETE .../notebook/pins/{pin_id}`, `POST .../notebook/theories` (`{title, body, pin_ids}`), `PUT` and `DELETE .../notebook/theories/{theory_id}`, `GET /story/session/{id}/turn/{turn_number}`. Pins are validated against the text published to the player, so hidden engine text cannot be pinned. Notebook rows live in `notebook_items`, are never read by the narrator path or the export, take no turn and change no world state. Deleted with the save and on reset.

### Chapter handover

`GET /story/session/{id}/handover` returns `{can_end_chapter, reason, candidates[{id, name, relation, last_seen}]}`. `POST` takes `{request_id, successor_id, expected_turn_count}` and returns `{session, turn, replayed}`. One handover per save. The turn is engine written (`turn_kind: "handover"`), with no narrator call. `409` for a stale choice list or an in-flight turn, `422` for an ineligible successor. `ActionRequest.expected_turn_count` is also accepted by `POST /story/action` and returns `409` when the choices on screen are stale.

## Paid-provider controls

Every paid model call — story creation and player actions, including validation retries and automatic model fallbacks — passes through `ai_service.chat_completion_with_meta`, which **refuses to run without an active `provider_budget`**. The route installs the budget; no other module can reach the provider. Routing intent (primary model, fallback chain, retries per model, cost mode) is unchanged; the budget only caps how much of it may run per request.

| Env variable | Default | Scope | Effect when reached |
|--------------|---------|-------|---------------------|
| `RATE_LIMIT_ACTION_DEVICE_MAX` / `RATE_LIMIT_ACTION_DEVICE_WINDOW_SEC` | 60 / 3600 | per `device_id`, actions | **429** before generation |
| `PROVIDER_GLOBAL_CONCURRENT` | 4 | all paid requests | **429** before generation (expiring lease pool; crashed workers release automatically after `ACTION_GENERATION_DEADLINE_SEC` + 60s) |
| `PROVIDER_ATTEMPTS_PER_ACTION` | 8 | per logical request (shared by per-model retries, fallbacks and the validation retry) | **502**; no further retry or fallback |
| `ACTION_GENERATION_DEADLINE_SEC` | 240 | per logical request | **502**; each HTTP call is capped at the remaining time as a **wall-clock** limit (`asyncio.wait_for`; httpx timeouts alone only bound the gap between bytes). The session action lease and the request claim default to this deadline + 60s (`ACTION_LOCK_LEASE_SEC` may lengthen, never shorten, them) so a retry can never take over a still-running action |
| `PROVIDER_GLOBAL_ATTEMPT_MAX` / `PROVIDER_GLOBAL_ATTEMPT_WINDOW_SEC` | 500 / 3600 | all attempts globally | **429** (checked before every attempt) |
| `ACTION_TEXT_MAX_CHARS`, `CREATION_TEXT_FIELD_MAX_CHARS`, `CREATION_SETUP_TOTAL_MAX_CHARS`, `CREATION_SHORT_FIELD_MAX_CHARS` | 2000 / 2000 / 12000 / 200 | input size | **422** before any work |
| `CREATION_SETUP_JSON_MAX_CHARS`, `MATURE_CONTENT_JSON_MAX_CHARS` | 16000 / 8000 | serialized size, keys included | **422** before any work |
| `MAX_REQUEST_BODY_BYTES` | 262144 | any request body | **413** before the route runs |
| `TURN_WINDOW_MAX` | 500 | turns per read (session, export, history) | newest turns kept |
| `CLEAR_LEASES_ON_STARTUP` | off | startup | `1` frees every session lease, creation/provider concurrency slot and request claim left by an earlier process. **Only for single-process deployments** (the Windows launcher sets it); with several workers it would free a running worker's lease |

Usage accounting: every attempt writes a `provider_usage` row (request key, model, status `started`→`ok`/`error`/`uncertain`, token counts when the provider reports them, `telemetry_missing` otherwise; 30-day TTL). Rows are never deleted on uncertain outcomes. These are hard request/attempt/concurrency caps with token accounting — **not a monetary spending ceiling** (no pricing is embedded). Limiter or usage storage failure → **503** for new paid work; read-only story routes keep working.

### Mature renderer (off by default)

The optional second-pass mature prose renderer runs only when the operator sets `MATURE_RENDERER_ENABLED=true` and a pinned `MATURE_MODEL_ID` whose provider is configured. Off (the default), `GET /setup/capabilities` reports `mature_renderer_configured: false`; every session — including saved sessions whose `rendering_policy.route` is `mature_pinned` — receives the validated canonical narrative with `rendering_policy.last_status = "safe_fallback_renderer_disabled"` and `last_renderer = "standard"`, and no second provider call executes.

On, a session whose `mature_content.adult_mode_enabled` is true gets one strict call to the mature model (no automatic fallback) inside the same provider budget as the turn. The rewrite is served only if it keeps the paragraph count, passes the 18+ boundary and passes the full turn validator; otherwise the canonical narrative is served with a `safe_fallback_*` status (`safe_fallback_provider_budget` when the budget is spent). The canonical narrative is always stored as `canonical_narrative`. Known risk: no complete factual-equivalence check exists (FM-30).

## Admin / AI settings

All `/api/admin/*` routes require the `X-Admin-Api-Key` request header matching the server `ADMIN_API_KEY` environment variable. Fails closed with **503** when `ADMIN_API_KEY` is unset, **401** when missing or incorrect.

The Expo client does **not** embed admin credentials. Server admin settings are operator-only.

### Operator access (curl examples)

Set `ADMIN_API_KEY` in `backend/.env`. All examples assume `http://localhost:8000/api`.

```bash
# Read current AI settings
curl -s -H "X-Admin-Api-Key: $ADMIN_API_KEY" http://localhost:8000/api/admin/settings

# Enable developer_mode (affects LLM prompt markers only — player routes stay sanitised)
curl -s -X POST -H "X-Admin-Api-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"developer_mode": true}' http://localhost:8000/api/admin/settings

# Raw export for a session (admin only — no device credential)
curl -s -H "X-Admin-Api-Key: $ADMIN_API_KEY" \
  http://localhost:8000/api/story/session/SESSION_ID/export/raw

# Per-session diagnostics
curl -s -H "X-Admin-Api-Key: $ADMIN_API_KEY" \
  http://localhost:8000/api/admin/session/SESSION_ID/diagnostics
```
### `GET /admin/settings`

**Response:** `AdminSettingsBundle` with `settings`, `models`, `modes`, `compression_levels`, `limits`, `defaults`, `provider_configured`.

### `POST /admin/settings`

Patch global AI settings.

**Request body (all optional):**

| Field | Type |
|-------|------|
| `model` | string (must be in supported list) |
| `temperature` | 0.0–2.0 |
| `max_tokens` | 256–16384 |
| `history_window` | 4–200 |
| `default_mode` | `basic` \| `advanced` |
| `compression_level` | `light` \| `standard` \| `aggressive` |
| `memory_depth` | 0–10 |
| `developer_mode` | boolean |
| `fallback_models` | string[] |
| `cost_mode` | `normal` \| `low` |

**Response:** `{ settings }`

### `GET /admin/models`

**Response:** `{ models: ModelOption[] }`

### `GET /admin/runtime`

Runtime routing snapshot. Returns **404** if `ENABLE_DEBUG_PANEL` is false.

### `GET /admin/session/{session_id}/diagnostics`

Per-session diagnostics (model switches, compression, context budget). Returns **404** if debug panel disabled or session not found.

### `GET /admin/consistency?sample_limit=20`

Read-only consistency diagnostic for existing data: sessions whose `turn_count` disagrees with their stored turns, orphaned turns (session missing), duplicate `(session_id, turn_number)` rows, provisional sessions without an opening turn, reset sessions without turns (`reset_sessions_without_turns`, expected after a reset and not an anomaly), and action-request record counts (`in_progress_active`, `in_progress_stale_claim`, `uncertain`, `failed`, `completed_without_turn`). Samples contain identifiers only. `transaction_support_error` reports why paid writes are disabled, or `null`. **Never deletes or rewrites data** — repairs of ambiguous historical data are an operator decision.

## Error handling

- Standard FastAPI `HTTPException` with `{ "detail": "..." }`.
- Story engine provider failures return **502** `{ "detail": "Story engine unavailable" }` — no raw exception strings to clients. Details are logged server-side only.
- Rate limit exceeded returns **429** `{ "detail": "Too many requests" }`.
- Limiter/usage storage, transaction support, or commit-outcome problems return **503** `{ "detail": "Service unavailable" }`.
- Input-size violations return **422** with a field-and-limit message (player-safe, no payload echo); an oversized request body returns **413** `{ "detail": "Request body too large" }`.
- Frontend `friendlyError()` maps common patterns (429, 402, 401, 404, network) to user-facing alerts.

## Authentication and ownership

This increment provides **device-scoped session isolation**, not full user accounts.

| Mechanism | Scope | Transport |
|-----------|-------|-----------|
| Session ownership | Protected story routes (reads, writes, deletes, exports, reset, mode) | Header `X-Device-Id` |
| Session creation | `POST /story/new` only | JSON body field `device_id` (binds owner at creation) |
| Admin API key | `/api/admin/*` and `/export/raw` | Header `X-Admin-Api-Key` |

**Environment variable:** `ADMIN_API_KEY` — required on the server for admin routes to accept requests.

**Ownership errors:** Wrong `X-Device-Id` and unknown session both return **404** `{ "detail": "Session not found" }` with identical bodies (no enumeration). Missing header → **400** `{ "detail": "device_id is required" }`.

**Player allowlists:** All player-facing session/turn/list/export responses are built by `player_api.py` allowlists — unknown/internal fields never pass through. State/ledger string values are scrubbed for mechanic leaks. Raw state is operator-only via `/export/raw` or `/admin/session/{id}/diagnostics`.

**Operator access model:**

| Endpoint | Auth | Sanitised |
|----------|------|-----------|
| Player `/export` | `X-Device-Id` + ownership | Always |
| `/export/raw` | `X-Admin-Api-Key` | Never (full dump) |
| `/admin/session/{id}/diagnostics` | `X-Admin-Api-Key` | Never |

**Not authentication:** `developer_mode`, client UI unlock, or CORS — these do not grant admin, raw-export, or unsanitised player-route access.

## Planted secrets, standing instructions and two-player stories

All routes need the `X-Device-ID` header.

### Planted secrets (solo)
`ActionRequest.disclosure` carries a told secret: who it was told to, the claim, and whether it was true. The engine records it in the session's `claim_state` ledger (who knows what, and who could overhear). `GET /story/session/{id}/tell-targets` lists the people the player can tell. The player session view adds `claims_told`. Hidden ledger entries never appear in player responses.

### Standing instructions (solo)
`ActionRequest.order` leaves an instruction with a person. `POST /story/session/{id}/orders/preview` returns what the engine understood (trigger, action, whether the person would refuse). The engine ticks `order_state` each turn before the narrator runs and tells the narrator the result. The player session view adds `orders_given`.

### Two-player stories ("Two Lights")
Separate collections `duets` and `duet_turns`. Solo sessions are untouched.

| Route | Purpose |
| --- | --- |
| `POST /duets` | Host picks a seat (`ferryman` or `keeper`). Returns the view and a one-time `invite_code`. |
| `POST /duets/join` | Friend joins with the code. 404 for a bad code, 409 if used or if it is the host's own invite. |
| `POST /duets/{id}/invite` | Host re-issues the code while the friend has not joined. |
| `GET /duets`, `GET /duets/{id}` | List and resume. Anyone who is not one of the two seat devices gets 404. |
| `POST /duets/{id}/action` | Body `action_text`, `action_request_id`, optional `expected_turn_count`. 409 when it is not your turn, the story moved on, or another action is resolving. A repeated request id replays the stored result. |
| `POST /duets/{id}/end-chapter` | Either player ends the chapter. |
| `GET` / `POST /duets/{id}/comparison` | Each player opts in with `{share: bool}`. Both accounts are returned only when both opted in. |
| `GET /duets/{id}/export` | The caller's own account only. |

Every response is built per seat from a whitelist. Narrator requests are built only from that seat's data plus engine-written observation sentences.

## Player moves (challenge, bargain, route, regard, build, signal, teach)

Seven structured moves ride on the normal action. None is switched on by a genre, scenario name or example word; each is offered because the saved story supports it (who is here, what is carried, what was shown, trust, known places).

### `POST /story/session/{session_id}/action` with `move`

`move` is `{ "kind": "challenge|bargain|route|regard|build|signal|teach", "op": "<optional>", "args": { ... } }`. At most one of `disclosure`, `order` or `move` per request. The server checks the move against the save, decides the outcome, replaces `action_text` with its own wording, and takes one normal turn. A refused move (4xx) takes no turn and changes nothing. The same `action_request_id` replays the committed result and never applies a move twice.

State lives in `session.play_state[kind]`, is copied into a branch, and is absent in saves made before this feature (treated as empty).

### `GET /story/session/{session_id}/moves`

Returns `{ "turn_count": n, "moves": { "<kind>": { "available": bool, "reason": str|null, ... } } }`. The options are built only from what the player was shown or holds. A character after a handover sees only what that character knows.

### `POST /story/session/{session_id}/moves/preview`

Body is the same `move`. Returns `{ kind, can_commit, issues[], terms?, notes? }`. Reads only; nothing is kept and no turn is taken.

### Two-player signals

`POST /duets/{id}/signals` with `{ request_id, count, meaning }` offers a signal before the first lamp is lit. `POST /duets/{id}/signals/{signal_id}/respond` with `{ accept }` is answered by the other seat. `POST /duets/{id}/action` accepts `clarity: "clear"|"faint"`. The duet view carries `signals` and `signal_window_open`.
