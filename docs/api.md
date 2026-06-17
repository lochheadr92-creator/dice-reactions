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
| `llm_configured` | boolean | Whether `OPENROUTER_API_KEY` is set |

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
| `custom_premise` | no | string | Free-text premise |
| `mode` | no | string | `basic` or `advanced` |
| `scenario_id` | no | string | Curated scenario override |
| `custom_world_setup` | no | object | Custom World 6-part setup (see frontend types) |

**Response:** `{ session_id, turn, session }` — player allowlist serializers only (`player_api.py`). No `device_id`, `rolling_state`, `debug`, or engine metadata in responses.

**Rate limits (enforced before LLM call or session insert):**

| Env variable | Default | Meaning |
|--------------|---------|---------|
| `RATE_LIMIT_IP_MAX` | 10 | Max creations per client IP per window |
| `RATE_LIMIT_IP_WINDOW_SEC` | 3600 | IP window (seconds) |
| `RATE_LIMIT_DEVICE_MAX` | 5 | Max creations per `device_id` per window |
| `RATE_LIMIT_DEVICE_WINDOW_SEC` | 3600 | Device window (seconds) |
| `RATE_LIMIT_GLOBAL_MAX` | 50 | Max total story creations globally per fixed window |
| `RATE_LIMIT_GLOBAL_WINDOW_SEC` | 3600 | Global fixed window (seconds) |
| `RATE_LIMIT_GLOBAL_CONCURRENT` | 3 | Max in-flight story creations |
| `TRUSTED_PROXY_COUNT` | 0 | When >0, client IP from `X-Forwarded-For` at `parts[-N]` (requires chain length > N). **Do not trust `X-Forwarded-For` unless this matches your deployment proxy depth.** |

Exceeded limits → **429** `{ "detail": "Too many requests" }` (generic; no admin/model details). Limiter backend failure → **503** `{ "detail": "Service unavailable" }` (fail closed).

`device_id` in the body is **not** abuse-proof — clients can regenerate UUIDs. IP limits complement device limits.

Scenario fields override client defaults when `scenario_id` is set.

### `POST /story/action`

Submit a player action for the next turn.

**Request body (`ActionRequest`):**

| Field | Required | Type |
|-------|----------|------|
| `session_id` | yes | string |
| `action_text` | yes | string |
| `debug_mode` | no | boolean |

**Header:** `X-Device-Id` (required) — must match the session owner's persisted `device_id`.

**Response:** `{ turn: Turn }`

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

**Response:** `{ sessions: SessionSummary[] }` — sessions are always sanitised (no `rolling_state`).

### `GET /story/session/{session_id}`

Full session with all turns. Player-facing response is always sanitised.

**Header:** `X-Device-Id` (required) — must match `session.device_id`.

**Response:** `{ session, turns }`

**Errors:** `400` missing `X-Device-Id`; `404` `{ "detail": "Session not found" }` for unknown session or wrong device (indistinguishable).

### `GET /story/session/{session_id}/latest`

Most recent turn only. Turn is always sanitised.

**Header:** `X-Device-Id` (required)

**Response:** `{ turn }`

### `DELETE /story/session/{session_id}`

Delete session and its turns.

**Header:** `X-Device-Id` (required)

**Response:** `{ deleted: true }`

### `POST /story/session/{session_id}/mode`

Switch simulation mode mid-chronicle.

**Header:** `X-Device-Id` (required)

**Request:** `{ mode: "basic" | "advanced" }`

**Response:** `{ mode }`

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
    "last_state": { }
  }
}
```

Turns are sorted by `turn_number` ascending (max 500).

### `GET /story/session/{session_id}/export/raw`

**Administrative raw export.** Requires `X-Admin-Api-Key` only (no player device credential). Returns full unsanitised session + turns including `rolling_state`, `debug`, `raw`.

**Header:** `X-Admin-Api-Key` (required)

**Errors:** `401` missing/invalid admin key; `404` unknown session; `503` if `ADMIN_API_KEY` env not configured on server.

Not exposed in the player UI. Not enabled by `developer_mode` alone.

### `POST /story/session/{session_id}/reset`

Delete all turns and clear rolling state; keep session shell (genre, role, difficulty, mode).

**Header:** `X-Device-Id` (required)

**Response:** `{ "reset": true }`

Client should start fresh via `POST /story/action` or create a new story.

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

## Error handling

- Standard FastAPI `HTTPException` with `{ "detail": "..." }`.
- Story engine provider failures return **502** `{ "detail": "Story engine unavailable" }` — no raw exception strings to clients. Details are logged server-side only.
- Rate limit exceeded returns **429** `{ "detail": "Too many requests" }`.
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