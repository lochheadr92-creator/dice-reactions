# Frontend

Expo SDK 54 app using file-based routing under `frontend/app/`.

## Structure

```
frontend/
├── app/
│   ├── _layout.tsx       # Fonts, SafeAreaProvider, Stack navigator
│   ├── +html.tsx         # Web HTML shell
│   ├── index.tsx         # Home — chronicle list
│   ├── new-story.tsx     # Story creation / Custom World setup
│   ├── play/[id].tsx     # Active chronicle play screen
│   └── settings.tsx      # App + admin AI settings
└── src/
    ├── api.ts            # REST client and TypeScript types
    ├── theme.ts          # Colors, fonts, BACKEND_URL, API base
    ├── storage.ts        # AsyncStorage: device ID, app settings
    ├── sanitize.ts       # Player-facing paragraph/choice filter
    └── errors.ts         # User-friendly error mapping
```

## Routing

Expo Router maps files to routes:

| File | Route | Purpose |
|------|-------|---------|
| `index.tsx` | `/` | Home |
| `new-story.tsx` | `/new-story` | Create chronicle |
| `play/[id].tsx` | `/play/:id` | Play session |
| `settings.tsx` | `/settings` | Settings |

## API client (`src/api.ts`)

All requests go to `${EXPO_PUBLIC_BACKEND_URL}/api`.

Exported functions mirror backend routes:

- `newStory`, `sendAction`, `listSessions`, `getSession`, `getLatestTurn`, `deleteSession`
- `listScenarios`, `setSessionMode`, `exportSession`, `resetSession`
- `getAdminSettings`, `saveAdminSettings`, `getHealth`

Types: `Turn`, `SessionSummary`, `Scenario`, `CustomWorldSetup`, `AISettings`, `AdminSettingsBundle`.

## Device identity (`src/storage.ts`)

On first launch, generates and persists a UUID under `dice_device_id`. All session listing and creation uses this ID. There is no account system.

App settings (`dice_settings`):

```typescript
type AppSettings = {
  debugDefault: boolean;
  fontScale: number;
  developerUnlocked?: boolean;
};
```

## Presentation sanitization (`src/sanitize.ts`)

**Presentation only** — does not mutate turn objects in React state.

`sanitizeParagraphs(paragraphs, fallbackNarrative)`:

- Strips engine tags: `rolling_state`, `debug`, `state`, `ledger`, `choices`, `prior_state`, `scenario`, `system`
- Removes mechanic lines matching `Roll:`, `Modifiers:`, `Rolling state:`, etc.
- Removes JSON-like lines

`sanitizeChoices(choices)`:

- Filters empty or placeholder choices (`none`, `n/a`, etc.)

Used in `play/[id].tsx` before rendering chronicle text.

## Play screen (`app/play/[id].tsx`)

Features:

- Scrollable chronicle of all turns
- State chips: Health, Stress, Fatigue, Objective (color-mapped)
- Choice buttons A–F (sanitized)
- Custom action text input
- Ledger modal (consequence ledger from latest turn)
- Menu: export, reset, delete, mode toggle
- Debug panel (gated by `developerUnlocked` from storage + session `debug_mode`)

Loads session via `getSession(sessionId)` on mount.

Submits actions via `sendAction({ session_id, action_text, debug_mode })`.

## New story screen (`app/new-story.tsx`)

Flows:

1. **Genre grid** — 8 genres with images
2. **Curated scenarios** — fetched from `GET /scenarios`
3. **Custom World** — 6-part setup:
   - World concept / tone / danger
   - Player origin / former life / strengths / weakness
   - Carried items / desire
   - Active pressures (chips)
   - Story focus (chips)
   - Content settings (gore, psych horror, scarcity, cruelty, moral ambiguity, relationships)
   - Seed questions (free text)

Configurable: role, tone, difficulty (`soft`–`brutal`), mode (`basic`/`advanced`), custom premise.

On submit: `newStory()` then navigates to `/play/{session_id}`.

## Settings screen (`app/settings.tsx`)

Sections:

- Display: font scale
- Debug default toggle
- Hidden developer unlock (7 taps on version)
- ADMIN · AI ENGINE (visible when unlocked):
  - Model picker (expandable full list)
  - Temperature, max tokens, history window, memory depth
  - Default mode, compression level, cost mode, developer mode
  - Save via `saveAdminSettings()`

Unlock also sets server `developer_mode: true` so API returns full payloads.

## Theming (`src/theme.ts`)

Dark palette with amber primary (`#F59E0B`). Fonts:

- Headings: Cormorant Garamond
- Body: EB Garamond
- Mono: JetBrains Mono

Loaded in `_layout.tsx` via `@expo-google-fonts/*`.

## Error UX (`src/errors.ts`)

`friendlyError()` converts raw fetch/HTTP errors into titled alerts for:

- Network failures
- Rate limits (429)
- Insufficient credits (402)
- Auth failures (401)
- Model not found (404)
- Empty model output
- Generic 5xx

Used in `play/[id].tsx` and `new-story.tsx`.

## Environment

| Variable | Location | Purpose |
|----------|----------|---------|
| `EXPO_PUBLIC_BACKEND_URL` | `frontend/.env` | Backend origin (no trailing slash) |

## Known frontend observations

From `memory/PRD.md`:

- Expo/RN web may emit deprecated `pointerEvents` warning from framework internals; app source does not set `pointerEvents`.
- Historical tunnel errors in `expo.err.log` did not block preview in last verification.

## Unknown

- Offline / cached chronicle playback strategy (not implemented — requires network for all turns)
- Push notifications or background sync
- Native build / app store release process