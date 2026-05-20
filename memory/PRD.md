# Dice Reaction Story Engine — PRD

## Overview
Expo mobile app implementing the **DICE REACTION STORY ENGINE — Fused Master Runtime v3.3** as a persistent causal D20 simulation. Players step into a living world where every action resolves through a hidden D20 roll, every consequence persists, and the inventory ledger never resets.

## User Choices
- **LLM**: Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) via Emergent Universal Key
- **Persistence**: Local-only (device_id stored in AsyncStorage; sessions persist server-side keyed by device_id)
- **Design**: Surprise-me — "grimoire × terminal" (Cormorant Garamond serif headings, EB Garamond prose, JetBrains Mono UI; deep #050505 + amber #F59E0B)
- **Features**: All v1 core features

## Architecture
- **Backend**: FastAPI + MongoDB + emergentintegrations.LlmChat (Anthropic)
  - System prompt encodes the entire v3.3 spec including paragraph preservation, choice randomisation, and strict tagged output (`<narrative>`, `<choices>`, `<state>`, `<ledger>`, `<debug>`)
  - Stateless LlmChat per call; full history rehydrated as context block from MongoDB turns
  - Endpoints under `/api`: `/health`, `/story/new`, `/story/action`, `/story/sessions`, `/story/session/{id}`, `/story/session/{id}/latest`, `DELETE /story/session/{id}`
- **Frontend**: Expo Router file-based routing
  - `app/index.tsx` — Home with D20 hero, save-slot list, settings entry
  - `app/new-story.tsx` — Genre grid (8 presets + custom), role/tone/difficulty intake, debug toggle
  - `app/play/[id].tsx` — Sticky state bar, objective bar, scrollable narrative paragraphs (FadeInDown), A–F choice cards, custom action input, ledger modal, menu sheet, debug per-turn block
  - `app/settings.tsx` — Debug default, font scale, about
- **Theme**: `/app/frontend/src/theme.ts` exports COLORS + FONTS + API base
- **Storage**: `/app/frontend/src/storage.ts` — device_id + settings via AsyncStorage

## Mechanics Honored
- Hidden D20 (1-5 crit fail / 6-10 fail / 11-15 partial / 16-19 success / 20 crit) — never surfaced unless debug ON
- Persistent inventory ledger (Carried/Worn/Stored/Weapons/Supplies/Uncertain/Load + summary)
- Paragraph preservation rule (2-5 paragraphs each turn)
- Choice randomisation rule (A-F shuffled per turn)
- Failure spiral brake, scale lock, consequence budget
- Foreground/background system gating, telegraphed threats
- Spatial continuity, active objective thread
- Debug block: roll, modifiers, final band, active systems, scale, delayed/latent triggers

## Testing
- **23/23 backend tests pass** (pytest at `/app/backend/tests/test_story_engine.py`)
- **Frontend E2E verified** on 390×844 viewport: home → new-story → fantasy/wanderer/soft/debug-on → play → choice tap → debug block + ledger modal all working
- No `_id` leak; session/device isolation confirmed

## Smart Enhancement (Shareability)
- "Chronicles" framing on save slots — the app frames each playthrough as an artefact worth keeping. Every slot card surfaces a hand-typeset narrative snippet + live HP/STR/turn count, turning the save list itself into a portfolio of past lives the player can return to or screenshot/share.

## Files
- Backend: `/app/backend/server.py`, `/app/backend/.env` (EMERGENT_LLM_KEY)
- Frontend: `/app/frontend/app/{_layout,index,new-story,settings}.tsx`, `/app/frontend/app/play/[id].tsx`, `/app/frontend/src/{api,theme,storage}.ts`
- Tests: `/app/backend/tests/test_story_engine.py`
