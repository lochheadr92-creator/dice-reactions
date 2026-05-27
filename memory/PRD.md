# Dice Reaction Story Engine — Current-State PRD

## Problem Statement
Build and maintain the **DICE REACTION STORY ENGINE — Fused Master Runtime**, a persistent causal D20 story simulation for Expo mobile. The player should experience an immersive living world while internal mechanics, debug payloads, rolling memory, and provider diagnostics remain hidden from the normal play view.

## Confirmed Architecture
- **Frontend**: Expo SDK 54 + Expo Router mobile app.
  - `app/index.tsx`: home screen, save slots, settings entry.
  - `app/new-story.tsx`: scenario/genre intake, role, tone, difficulty, mode, premise.
  - `app/play/[id].tsx`: chronicle reader, state chips, objective bar, choices, custom action, ledger modal, gated diagnostics.
  - `src/sanitize.ts`: presentation filter for leaked engine tags/mechanic lines.
  - `src/api.ts`: API client using `EXPO_PUBLIC_BACKEND_URL + /api`.
- **Backend**: FastAPI + MongoDB + OpenRouter.
  - `server.py`: story routes, validation/retry pipeline, runtime governance prompt, player/dev sanitization, diagnostics endpoints.
  - `ai_service.py`: OpenRouter chat-completions integration with retry/fallback telemetry.
  - `ai_config.py`: model routing, fallback chain, token budgets, low-cost/runtime settings.
  - `memory.py`: rolling memory consolidation and context budget trimming.
- **Persistence**: MongoDB stores `sessions` and `turns`; device identity is stored client-side via AsyncStorage.

## Implemented Runtime Capabilities
- Player-facing rendering sanitizer removes raw JSON/debug/mechanic leaks from the main chronicle view.
- Runtime Governance v3.6: anti-loop rules, forward pressure, topic ledger, active pressures, choice freshness.
- Output format validation: backend enforces 2–4 short paragraphs, 4–6 A–F choices, and retries once on invalid output.
- Narrative Immersion Governor: prompt rules prevent system/tutorial-style exposition in prose.
- AI Routing v3.7: OpenRouter default model is `anthropic/claude-3-5-haiku`; fallback chain is Haiku → Sonnet → Mythomax; telemetry is persisted in dev diagnostics.
- Rolling Memory Compression v3.8: session-level `rolling_state` is consolidated turn-to-turn while preserving unresolved causal state.
- Context Budget Governor v3.9: pre-call prompt budget estimation/trimming protects recent turns and authoritative state.
- Lightweight Custom World setup: selecting Custom World opens a concise 6-part ignition flow for world concept, player origin, active pressures, story focus, intensity/social settings, and seed questions.
- Custom setup persistence: setup answers are stored as canonical simulation seed data and injected into protected rolling-state hooks including `simulation_hooks`, `world_instability`, `story_focus`, `relationship_threads`, `inventory_objects`, and `object_locations`.
- Relationship/social settings are integrated as persistent systems affecting NPC memory, faction reaction, stress/trust/leverage, delayed consequences, and material behavior rather than isolated flavor toggles.
- State Supremacy guard: deterministic backend guard prevents uncaused Health/Fatigue improvements against tracked prior state.
- Object Permanence guard: deterministic backend guard reduces duplicate carried-vs-hidden/dropped/consumed/destroyed item contradictions and seeds object locations independently from inventory objects.
- Runtime hardening prompt rules added for failure doctrine, world momentum, NPC realism, compression hardening, mechanic concealment, anti-stagnation, and choice quality.

## Confirmed Current Settings
- Provider: OpenRouter.
- Active model: `anthropic/claude-3-5-haiku`.
- Fallback models: `anthropic/claude-3-5-haiku`, `anthropic/claude-3-5-sonnet`, `gryphe/mythomax-l2-13b`.
- Current max output tokens: `1536`.
- Current history window: `22`.
- Current memory depth: `3`.
- Current default mode: `advanced`.
- Current compression level: `standard`.
- Current backend developer mode: `true`.

## Verification Completed — 2026-05-27
- Backend health passed locally: `/api/health` returned `status=ok`, `llm_configured=true`, `provider=openrouter`.
- Admin/runtime endpoints passed locally: `/api/admin/settings` and `/api/admin/runtime` returned expected model, fallback, memory, and context budget data.
- Story runtime passed a 3-turn live OpenRouter verification using Haiku:
  - Turn 1: 2 paragraphs, 4 choices, valid state/ledger, no narrative mechanic leaks.
  - Turn 2: 2 paragraphs, 5 choices, valid persistence.
  - Turn 3: 2 paragraphs, 5 choices, valid persistence.
  - Session retrieval confirmed `turn_count=3`, turns sorted `[1,2,3]`, and `rolling_state` present with expected continuity keys.
  - Diagnostics confirmed active model `anthropic/claude-3-5-haiku`, no model fallback, context under budget, no trimming required in this short run.
- Preview health passed in browser automation at `https://chronicle-runtime.preview.emergentagent.com`.
- Play screen rendering passed in browser automation: generated chronicle displayed no visible `DEBUG`, `ROLLING`, `Roll:`, `Modifiers:`, `<rolling_state>`, or `<debug>` terms in the normal player view.
- Test sessions created during verification were deleted afterward.

## Verification Completed — Custom World Upgrade
- TypeScript check passed: `yarn tsc --noEmit`.
- Python lint passed for backend app code.
- Python compile passed for backend runtime modules.
- Backend regression suite passed: `30 passed`.
- Independent testing agent verified frontend Custom World setup visibility, all six sections, chip/input interactions, custom story start, preset-flow regression, and mechanic-concealment probe.
- Blocking issue found by testing agent was fixed: `object_locations` now seeds/merges independently when custom carried items exist, even if the model already produced `inventory_objects`.
- Frontend preview was verified after restart; Custom World setup renders and remains interactive.
- Expo/RN web still emits a development console warning about deprecated `pointerEvents`, but app source no longer contains `pointerEvents`; warning appears to originate from framework/runtime internals and did not block UI testing.

## Observations / Regressions
- No runtime-breaking regressions found.
- Expo preview is currently functional, but `expo.err.log` contains repeated historical tunnel errors (`Cannot read properties of undefined (reading 'body')`, `Premature close`). Current browser preview still loaded successfully.
- Static lint tooling is not currently clean:
  - Python lint flags one existing test-only style issue in `backend/tests/test_story_engine.py` (`E741 ambiguous variable name`).
  - The generic JavaScript lint tool failed to parse TypeScript/TSX files, so it is not a reliable signal for this Expo project as configured.
- Existing `backend/tests/test_story_engine.py` is outdated against the current OpenRouter/Haiku implementation and should not be treated as the current source of truth without updating assertions.

## Backlog
- **P0**: None confirmed.
- **P1**: Run a fresh 20+ turn hostile stress test against the upgraded runtime to verify state supremacy, object permanence, and anti-stagnation behavior under adversarial play.
- **P1**: Run a 15+ turn stress chronicle to confirm rolling compression activates after memory depth and context budget diagnostics remain stable.
- **P1**: Test provider fallback deliberately with an invalid/disabled primary model, then restore Haiku.
- **P2**: Add a dedicated in-app long-run diagnostics summary for dev-unlocked sessions.
- **P2**: Add a share/export-friendly chronicle summary view for memorable runs.
