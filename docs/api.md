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

Runtime health and resolved AI settings snapshot.

**Response fields (representative):**

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"ok"` when reachable |
| `llm_configured` | boolean | Whether `OPENROUTER_API_KEY` is set |
| `provider` | string | `"openrouter"` |
| `model` | string | Active default model |
| `temperature` | number | Sampling temperature |
| `max_tokens` | number | Max completion tokens |
| `history_window` | number | Max turns considered for replay |
| `default_mode` | string | `basic` or `advanced` |
| `compression_level` | string | `light`, `standard`, or `aggressive` |
| `memory_depth` | number | Recent turns replayed verbatim |
| `developer_mode` | boolean | Whether dev payloads are returned |
| `fallback_models` | string[] | Ordered fallback chain |
| `cost_mode` | string | `normal` or `low` |
| `runtime_config` | object | Snapshot from `ai_config.get_runtime_config()` |

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

**Response:** `{ session_id, turn, session }`

Scenario fields override client defaults when `scenario_id` is set.

### `POST /story/action`

Submit a player action for the next turn.

**Request body (`ActionRequest`):**

| Field | Required | Type |
|-------|----------|------|
| `session_id` | yes | string |
| `action_text` | yes | string |
| `debug_mode` | no | boolean |

**Response:** `{ turn: Turn }`

Turn shape (player view may omit fields when `developer_mode` is off):

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
| `rolling_state` | object \| null (dev only by default) |
| `debug` | object \| null (dev only by default) |
| `created_at` | ISO datetime string |

### `GET /story/sessions`

List sessions for a device.

**Query:** `device_id` (required)

**Response:** `{ sessions: SessionSummary[] }`

### `GET /story/session/{session_id}`

Full session with all turns.

**Response:** `{ session, turns }`

### `GET /story/session/{session_id}/latest`

Most recent turn only.

**Response:** `{ turn }`

### `DELETE /story/session/{session_id}`

Delete session and its turns.

**Response:** `{ deleted: true }`

### `POST /story/session/{session_id}/mode`

Switch simulation mode mid-chronicle.

**Request:** `{ mode: "basic" | "advanced" }`

**Response:** `{ mode }`

### `GET /story/session/{session_id}/export`

Return full session state JSON (unsanitized — includes `rolling_state`, `debug`, `raw` on turns).

**Response:**

```json
{
  "exported_at": "ISO-8601 datetime",
  "session": { },
  "turns": [ ],
  "summary": {
    "turn_count": 0,
    "rolling_state": { },
    "last_state": { }
  }
}
```

Turns are sorted by `turn_number` ascending (max 500). No `device_id` ownership check.

### `POST /story/session/{session_id}/reset`

Delete all turns and clear rolling state; keep session shell (genre, role, difficulty, mode).

**Response:** `{ "reset": true }`

Client should start fresh via `POST /story/action` or create a new story.

## Admin / AI settings

These endpoints power Settings → ADMIN · AI ENGINE. No separate auth layer is implemented; access is UI-gated only.

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
- Story engine wraps provider failures as 502-style errors with OpenRouter status embedded in detail string.
- Frontend `friendlyError()` maps common patterns (429, 402, 401, 404, network) to user-facing alerts.

## Authentication

**Unknown / not implemented:** There is no user login or API key per client. Sessions are scoped by `device_id` only. Admin endpoints are not separately authenticated.