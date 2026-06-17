# Overview

## What it is

Dice Reaction (internally: **Dice Reaction Story Engine**) is an immersive narrative game where players make choices or type custom actions inside procedurally sustained story worlds. Under the hood, a D20-style causal simulation runs each turn: consequences persist, objects have permanence, NPC memory and faction pressure evolve, and rolling state compresses over long sessions.

Players experience prose, state chips (Health, Stress, Objective, etc.), and A–F choices. They do **not** see dice rolls, modifier math, rolling-state JSON, or debug telemetry in normal play.

## Repository layout

```
dice-reactions/
├── AGENTS.md              # Coding/agent instructions
├── memory/
│   └── PRD.md             # Product requirements & verification log
├── backend/
│   ├── server.py          # FastAPI app, story engine, guards
│   ├── ai_service.py      # OpenRouter integration
│   ├── ai_config.py       # Model routing & runtime config
│   ├── memory.py          # Rolling memory & context budget
│   ├── scenarios.py       # Curated scenario presets
│   ├── requirements.txt
│   ├── .env               # Secrets & connection strings (not committed)
│   └── tests/             # Pytest + verification scripts
├── frontend/
│   ├── app/               # Expo Router screens
│   ├── src/               # API client, theme, sanitize, storage
│   ├── package.json
│   └── .env               # EXPO_PUBLIC_BACKEND_URL
└── docs/                  # This documentation set
```

## Technology stack

| Layer | Technology |
|-------|------------|
| Mobile / web UI | Expo SDK 54, Expo Router 6, React Native 0.81, TypeScript |
| API | FastAPI, Pydantic v2, Motor (async MongoDB) |
| LLM provider | OpenRouter (chat completions) |
| Default model | `anthropic/claude-3-5-haiku` |
| Fallback chain | Haiku → Sonnet → Mythomax |
| Persistence | MongoDB collections: `sessions`, `turns`, `admin_settings` |
| Client identity | Device UUID in AsyncStorage (`dice_device_id`) |

## Player-facing flows

1. **Home** (`app/index.tsx`) — list chronicles for this device, start new story, open settings.
2. **New story** (`app/new-story.tsx`) — pick genre, optional curated scenario, or Custom World (6-part setup); configure role, tone, difficulty, mode.
3. **Play** (`app/play/[id].tsx`) — chronicle reader, state chips, objective bar, choices, custom action, ledger modal; gated diagnostics when developer-unlocked.
4. **Settings** (`app/settings.tsx`) — font scale, debug default, admin AI engine controls; hidden 7-tap developer unlock on version row.

## Implemented capabilities (confirmed in code)

- Runtime Governance v3.6 system prompt (anti-loop, forward pressure, mechanic concealment).
- Output validation: 2–4 paragraphs, 4–6 choices, single retry on invalid output.
- Player API sanitization strips `rolling_state`, `debug`, `raw`, and internal state keys unless `developer_mode` is on.
- Frontend presentation sanitizer (`src/sanitize.ts`) strips leaked engine tags from rendered paragraphs.
- Rolling Memory Compression v3.8 (`memory.consolidate_rolling_state`).
- Context Budget Governor v3.9 (`memory.enforce_context_budget`).
- State Supremacy guard (uncaused Health/Fatigue improvements blocked).
- Object Permanence guard and canonical object registry.
- Custom World setup seeded into `rolling_state` hooks.
- Curated scenarios: Suburban Collapse, Dinosaur Containment Breach, Cosmic Horror Road Town.
- Session-locked AI routing (model + fallback chain per session).
- Admin settings persisted in MongoDB, overridable via Settings UI.

## Current runtime defaults

**Canonical source:** [current-state.md](./current-state.md) (evidence-tagged). Code defaults below; effective runtime = DB `admin_settings` overrides > env > code.

| Setting | Code default | Docs-claimed deployment (PRD, not re-verified) |
|---------|--------------|--------------------------------------------------|
| Default mode | `advanced` | — |
| Default compression level | `standard` | — |
| Default memory depth | `3` | — |
| Default max output tokens | `2048` (`ai_service.py`) | `1536` |
| Default history window | `40` (`ai_service.py`) | `22` |
| Developer mode | `false` (`get_ai_settings`) | `true` |