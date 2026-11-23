# Frontend

Expo SDK 54 app using file-based routing under `frontend/app/`.

## Structure

```
frontend/
├── app/
│   ├── _layout.tsx       # Fonts, SafeAreaProvider, Stack navigator
│   ├── +html.tsx         # Web HTML shell
│   ├── index.tsx         # Home — chronicle list
│   ├── new-story.tsx     # Story creation: Quick Start, Guided, Advanced
│   ├── play/[id].tsx     # Active chronicle play screen
│   └── settings.tsx      # Reading, turn and story-default settings; operator panel
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
- `listScenarios`, `setSessionMode`, `setSessionPlaySettings`, `exportSession`, `getSessionHistory`, `resetSession`
- `getActionRequestStatus`, `getHealth`, `getSetupCapabilities`
- `getAdminSettings(adminKey)`, `updateAdminSettings(adminKey, ...)` (both send `X-Admin-Api-Key`)

Helpers in `src/prose-length.ts`: `proseModeForTurnLength`, `playSettingsFor(settings)` (turns the saved Settings into the `prose_mode`, `prose_style`, `thinking_effort` values the API takes).

Types: `Turn`, `SessionSummary`, `Scenario`, `CustomWorldSetup`, `AISettings`, `AdminSettingsBundle`.

## Device identity (`src/storage.ts`)

On first launch, generates and persists a UUID under `dice_device_id`. All session listing and creation uses this ID. There is no account system.

App settings (`dice_settings`):

```typescript
type AppSettings = {
  debugDefault: boolean;
  fontScale: number;             // text size only
  turnLength?: TurnLength;       // S, M, L, XL. Missing = M. Separate from text size
  writingStyle?: WritingStyle;   // plain, balanced, rich. Missing = balanced
  speed?: Speed;                 // how long the model thinks. Missing = fast
  storyDefaults?: StoryDefaults; // what a new story starts from in the Advanced builder
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
- State chips: Health, Stress, Fatigue, Danger, Momentum (color-mapped)
- Choice buttons A–F (sanitized)
- Custom action text input
- Ledger modal (consequence ledger from latest turn)
- Menu: export, reset, delete, mode toggle
- Debug panel (gated by `developerUnlocked` from storage + session `debug_mode`)

Loads session via `getSession(sessionId)` on mount.

Each time the screen gains focus it reads the saved Settings and sends them with `setSessionPlaySettings(sessionId, deviceId, playSettingsFor(settings))`, so a change made in Settings applies to the next action. The server treats this as a preference: it does not move the story in the list, and identical values write nothing.

Submits actions via `sendAction({ session_id, action_text, debug_mode, action_request_id })`. The request ID lets a retry after a lost reply recover the same turn (`getActionRequestStatus`) instead of paying for a second one.

## New story screen (`app/new-story.tsx`)

Three ways in:

1. **Quick Start**: cards for curated scenarios (`GET /scenarios`). One tap starts the story.
2. **Guided**: seven answers, then the story starts.
3. **Advanced** (`src/newstory/AdvancedBuilder.tsx`): four input pages (World, Character, Story, Play) and a Review page. Every option shows what it does and what to expect. Inputs include the player's own premise, time period, what recently shifted, how real or strange the setting is, what belongs and what must not appear, role, knowledge, want, fear, who matters, harshness, turn length, writing style and speed.

The Advanced builder starts from the story defaults saved in Settings. All three paths send `playSettingsFor(settings)` with the creation request, so a new story begins with the saved turn length, writing style and speed.

On submit: `newStory()` then navigates to `/play/{session_id}`.

## Settings screen (`app/settings.tsx`)

Sections, in order:

- TEXT SIZE: reading size only. It no longer stands in for turn length.
- TURN LENGTH: S, M, L, XL (1 to 2, 2 to 4, 4 to 6, 6 to 8 paragraphs).
- WRITING STYLE: plain, balanced, rich.
- SPEED: how long the model thinks before it writes.
- STORY DEFAULTS: what the Advanced builder starts from, including 18+ content levels where the build allows them.
- ADMIN (shown after the local unlock, 7 taps on the version): model, temperature, token and memory settings. Reading or saving these needs the operator key, sent as `X-Admin-Api-Key`. The local unlock alone changes nothing on the server and does not turn on server developer mode.
- ABOUT: version and a credit line. The credit says an AI language model writes the stories. It names no provider, because the provider is an operator setting.

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