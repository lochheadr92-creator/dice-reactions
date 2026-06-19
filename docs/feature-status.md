# Feature Status

**Snapshot date:** 2026-06-20
**Branch:** `emergent` (canonical runtime for this table)

| Feature | Status | Runtime files | Tests | Documentation | Known risks | Next required action |
|---------|--------|---------------|-------|---------------|-------------|---------------------|
| Anti-Hallucination Gateway | Verified complete (deterministic) | `gateway.py`, `server.py` (`_generate_turn`, `_full_validate`, guard pipeline) | `test_anti_hallucination_gateway.py` ✅, `test_gateway_e2e.py` ✅ | `story-engine.md`, `system-doctrine.md` H5 | LLM still proposes rolling_state; not full Ch 31 | Live probe (`test_gateway_live_probe.py`) |
| LLM chokepoint (`invoke_llm`) | Verified complete | `gateway.py` | Indirect via gateway tests ✅ | `architecture.md` | Bypass if new code calls `ai_service` directly | Lint/import guard |
| Relationship calculus (NPC→player) | Verified complete (scoped) | `relationships.py`, `memory.py` (`relationship_vectors` protected) | `test_relationship_calculus.py` ✅ | `story-engine.md` | NPC↔NPC not supported; regex events only; `relationship_threads` legacy | Live probe (`test_relationship_calculus_live.py`) |
| HUD (DNG / MOM / PRS) | Verified complete (deterministic) | `hud.py`, `frontend/app/play/[id].tsx` | `test_hud.py` ✅ | `story-engine.md`, `frontend.md` | Prescriptive LLM pressure stripped at shape time | Optional UI snapshot tests |
| Story session lifecycle | Verified complete (ownership) | `server.py`, `security.py` | `test_security.py` ✅ | `api.md` | Device isolation only — not user accounts | Run live `test_story_engine.py` |
| Early-Game Pacing Governor v1 | Verified complete (deterministic — Stage 1 field-presence only) | `pacing.py`, `server.py` (`_build_messages`, `_full_validate`, `_generate_validated_turn`) | `test_early_game_pacing.py` ✅ | `current-state.md`, `decision-log.md` (ADR-016) | Stages 2–4 are non-persisted guidance; does not prove autonomous heartbeat | Living World Test (separate backlog) |
| Narrative generation | Implemented but unverified | `server.py` (`_generate_turn`, `_generate_validated_turn`) | `test_story_engine.py`, `qa_live_20turn_hostile.py` | `story-engine.md` | LLM latency/cost; provider outages | Live turn test + 20-turn script |
| Anti-hallucination / narrative guards (validator) | Partial | `server.py` (`_validate_parsed`, `_full_validate`) | `verify_p1_immersion_integrity.py` ✅, `verify_p15_microfixes.py` ✅ | `story-engine.md` | Validator cannot catch all leaks post-hoc | Add live leakage probe to CI |
| Backend player sanitization | Verified complete | `player_api.py` allowlist serializers | `test_security.py`, `test_player_api.py` ✅ | `architecture.md` | — | — |
| Story creation rate limits | Verified complete (deterministic) | `rate_limit.py` | `test_rate_limit.py` ✅ | `api.md` | IP trust requires `TRUSTED_PROXY_COUNT` | Tune limits per deployment |
| Frontend sanitization | Verified complete (unit) | `frontend/src/sanitize.ts`, `play/[id].tsx` | None dedicated | `frontend.md` | Presentation-only; state still holds leaks | Optional snapshot tests |
| Object permanence | Verified complete (deterministic) | `server.py`, `memory.py` | `verify_p0_object_permanence.py` ✅ | `story-engine.md` | Heuristic ledger matching | — |
| Inventory and item state | Partial | `server.py`, `memory.py`, `gateway.py` (destruction registry) | P0 ✅, `test_gateway_e2e.py` ✅ | `story-engine.md` | LLM can invent items before guards | Live hostile inventory probe |
| Actor resolution | Planned — not present | — | — | PRD Ch 25 | No module in repo or git history | Implement or mark permanently out of scope |
| Relationship threads (legacy) | Partial | `server.py` (seed + prompt schema), `memory.py` | Custom World tests (unverified) | `story-engine.md` | Superseded by `relationship_vectors` for mechanics | Document as narrative seed only |
| Utility AI | Planned — not present | — | — | PRD Ch 27 | Never in repo | Implement or mark out of scope |
| Retrieval and memory | Partial | `memory.py`, `server.py` (`_build_messages`) | P0/P1 scripts ✅ | `story-engine.md` | Not vector RAG; Mongo replay only | 15+ turn compression stress (PRD P1) |
| Gravity / retention governance | Partial (ad-hoc only) | `memory.enforce_context_budget`, `consolidate_rolling_state` | Context budget: no dedicated test | `story-engine.md` | No gravity module; token estimate heuristic | Long-run budget stability test |
| Event sourcing | Partial (turn log only) | `db.turns.insert_one` | None | `architecture.md`, `system-doctrine.md` | Turns deleted on reset; rolling_state overwritten; no rebuild | Document as turn-log, not ES |
| World history | Partial | Turns collection + `rolling_state` | P1-C room audit ✅ | `story-engine.md` | History cap: 500 turns/export, 200 sessions list | Index + pagination review |
| Telemetry | Implemented but unverified | `ai_service.py`, turn `debug` field | Live tests only | `architecture.md` | Telemetry in dev payloads only | Verify diagnostics endpoint |
| Model selection | Implemented but unverified | `ai_service.py`, `ai_config.py`, admin routes | `test_story_engine.py` (health only) | `api.md`, `development.md` | Unsupported model rejected on admin POST only | Fallback failure drill (PRD P1) |
| Developer mode | Partial | `server.py`, `settings.tsx`, `play/[id].tsx` | Integration (not run) | `frontend.md`, `development.md` | Server flag toggled without auth | Protect admin POST |
| Admin settings | Verified complete (server auth) | `security.py`, `server.py` | `test_security.py` ✅ | `api.md` | Client UI cannot call without `ADMIN_API_KEY` proxy | Operator deployment docs |
| Player export | Verified complete | `server.py` `export_session` | `test_security.py` ✅ | `api.md` | Always sanitised | — |
| Raw admin export | Verified complete | `server.py` `export_session_raw` | `test_security.py` ✅ | `api.md` | Requires admin key + ownership | Not in player UI |
| Reset endpoint | Verified complete (ownership) | `server.py` `reset_session` | `test_security.py` ✅ | `api.md` | Destructive; ownership enforced | Contract test optional |
| Frontend error handling | Verified complete (unit) | `frontend/src/errors.ts` | None | `frontend.md` | Pattern-based; may miss new errors | Add cases as discovered |
| Quick Start story-first onboarding | Verified complete (Phase 2 scope) | `frontend/app/new-story.tsx`, `frontend/src/newstory/QuickStart.tsx`, `frontend/src/newstory/options.ts`, `frontend/src/api.ts` | `frontend/__tests__/new-story.test.tsx` ✅, browser preview regression ✅ | `current-state.md`, `decision-log.md` | Guided Start and Advanced extraction still pending | Begin Phase 3 only with explicit approval |
| Guided Start curated onboarding | Verified complete (Phase 3 scope) | `frontend/app/new-story.tsx`, `frontend/src/newstory/GuidedStart.tsx`, `frontend/src/newstory/options.ts`, `frontend/src/api.ts` | `frontend/__tests__/new-story.test.tsx` ✅, browser preview regression ✅ | `current-state.md`, `decision-log.md` | Advanced extraction and secret reveal still pending | Begin Phase 4 only with explicit approval |
| Custom World creation | Implemented but unverified | `server.py`, `new-story.tsx` | `test_custom_world_system.py` (unverified) | `frontend.md`, PRD Docs-claimed | Depends on live LLM | Run pytest with server |
| State supremacy | Verified complete (deterministic) | `server.py` `_apply_state_supremacy` | `test_custom_world_system.py` (unit), P0 adjacent | `story-engine.md` | Health/Fatigue only | Extend if more chips added |
| NPC memory bounds | Verified complete (deterministic) | `server.py` `_apply_npc_memory_bounds` | `verify_p1_immersion_integrity.py` ✅ | `story-engine.md` | LLM may emit unbounded before guard | — |
| Faction consequence tick | Verified complete (deterministic) | `server.py` `_apply_faction_consequence_tick` | P1-D ✅, `qa_live_20turn_hostile.py` (not run) | `story-engine.md` | Theme regex false positives/negatives | Live hostile script |
| Room audit | Verified complete (deterministic) | `server.py` `_apply_room_audit` | P1-C ✅ | `story-engine.md` | Drift flag only; no auto-repair | — |
| Curated scenarios | Implemented but unverified | `scenarios.py`, `new-story.tsx` | Indirect via `story/new` | `overview.md` | Only 3 presets | Live preset smoke test |
| Advanced Builder preservation during Guided Start rollout | Verified complete (preserved, not extracted) | `frontend/app/new-story.tsx` | `frontend/__tests__/new-story.test.tsx` ✅, browser preview regression ✅ | `current-state.md` | Still a large screen file; Phase 4 extraction pending | Refactor later without changing contract |
| Context budget governor | Verified complete (deterministic) | `memory.enforce_context_budget` | `test_early_game_pacing.py` ✅ | `story-engine.md` | Heuristic token estimate | 15+ turn live budget stress |
| Scoring / rankings | N/A | — | — | — | Never existed in this repo | Do not backlog as lost feature |

**Status definitions used:**

- **Verified complete** — Deterministic code + verification script or pytest passed in 2026-06-17 pass (47-test bundle), or unit logic confirmed in code review.
- **Implemented but unverified** — Code exists; live/integration proof missing or stale.
- **Partial** — Some layers exist; gaps documented.
- **Planned — not present** — In PRD/plan only; no code.
- **N/A** — Not applicable to this repository.