# Feature Status

**Snapshot date:** 2026-06-17

| Feature | Status | Runtime files | Tests | Documentation | Known risks | Next required action |
|---------|--------|---------------|-------|---------------|-------------|---------------------|
| Story session lifecycle | Implemented but unverified | `backend/server.py` | `test_story_engine.py` (not run; outdated) | `api.md`, `story-engine.md` | No `device_id` check on `get_session` | Run integration tests with live server |
| Narrative generation | Implemented but unverified | `server.py` (`_generate_turn`, `_generate_validated_turn`) | `test_story_engine.py`, `qa_live_20turn_hostile.py` | `story-engine.md` | LLM latency/cost; provider outages | Live turn test + 20-turn script |
| Anti-hallucination / narrative guards | Partial | `server.py` (`_validate_parsed`, `_check_direct_inspection_violation`, prompt) | `verify_p1_immersion_integrity.py` ✅, `verify_p15_microfixes.py` ✅ | `story-engine.md`, `system-doctrine.md` | Validator cannot catch all leaks post-hoc | Add live leakage probe to CI |
| Backend player sanitization | Implemented but unverified | `server.py` (`_maybe_sanitise_*`) | Indirect via integration tests | `architecture.md` | Bypass via `export_session`, `developer_mode` | Auth on export; integration test |
| Frontend sanitization | Verified complete (unit) | `frontend/src/sanitize.ts`, `play/[id].tsx` | None dedicated | `frontend.md` | Presentation-only; state still holds leaks | Optional snapshot tests |
| Object permanence | Verified complete (deterministic) | `server.py`, `memory.py` | `verify_p0_object_permanence.py` ✅ | `story-engine.md` | Heuristic ledger matching | Run inside CI |
| Inventory and item state | Partial | `server.py`, `memory.py` (`canonicalize_object_registry`) | P0 ✅ | `story-engine.md` | LLM can invent items before guards | Live hostile inventory probe |
| Actor resolution | Unknown | — | — | — | Not present in codebase | Confirm out of scope or implement |
| Relationship state | Partial | `server.py` (seed + prompt schema), `memory.py` (protected merge) | `test_custom_world_system.py` (needs server) | `story-engine.md` | No directionality guard | Add deterministic relationship guard or mark LLM-only |
| Utility AI | Unknown | — | — | — | Not present in codebase | Confirm out of scope |
| Retrieval and memory | Partial | `memory.py`, `server.py` (`_build_messages`) | P0/P1 scripts (memory portions) ✅ | `story-engine.md` | Not vector RAG; Mongo replay only | 15+ turn compression stress (PRD P1) |
| Gravity / retention governance | Partial | `memory.enforce_context_budget`, `consolidate_rolling_state` | Context budget: no dedicated test | `story-engine.md` | Token estimate is heuristic (chars/4) | Long-run budget stability test |
| Event sourcing | Partial | `db.turns.insert_one` | None | `architecture.md`, `system-doctrine.md` | Turns deleted on reset; rolling_state overwritten | Document as turn-log, not ES |
| World history | Partial | Turns collection + `rolling_state` | P1-C room audit ✅ | `story-engine.md` | History cap: 500 turns/export, 200 sessions list | Index + pagination review |
| Telemetry | Implemented but unverified | `ai_service.py`, turn `debug` field | Live tests only | `architecture.md` | Telemetry in dev payloads only | Verify diagnostics endpoint |
| Model selection | Implemented but unverified | `ai_service.py`, `ai_config.py`, admin routes | `test_story_engine.py` (health only) | `api.md`, `development.md` | Unsupported model rejected on admin POST only | Fallback failure drill (PRD P1) |
| Developer mode | Partial | `server.py`, `settings.tsx`, `play/[id].tsx` | Integration (not run) | `frontend.md`, `development.md` | Server flag toggled without auth | Protect admin POST |
| Admin settings | Implemented but unverified | `server.py`, `frontend/app/settings.tsx` | None | `api.md` | No authentication | Add auth or network restriction |
| Export endpoint | Implemented but unverified | `server.py` `export_session` | None | `api.md` (updated) | Returns unsanitized full state | Sanitize or require dev auth |
| Reset endpoint | Implemented but unverified | `server.py` `reset_session` | None | `api.md` (updated) | Deletes all turns irreversibly | Contract test + UI warning audit |
| Frontend error handling | Verified complete (unit) | `frontend/src/errors.ts` | None | `frontend.md` | Pattern-based; may miss new errors | Add cases as discovered |
| Custom World creation | Implemented but unverified | `server.py`, `new-story.tsx` | `test_custom_world_system.py` (server down in pass) | `frontend.md`, PRD Docs-claimed | Depends on live LLM | Run pytest with server |
| State supremacy | Verified complete (deterministic) | `server.py` `_apply_state_supremacy` | `test_custom_world_system.py` (unit), P0 adjacent | `story-engine.md` | Health/Fatigue only | Extend if more chips added |
| NPC memory bounds | Verified complete (deterministic) | `server.py` `_apply_npc_memory_bounds` | `verify_p1_immersion_integrity.py` ✅ | `story-engine.md` | LLM may emit unbounded before guard | — |
| Faction consequence tick | Verified complete (deterministic) | `server.py` `_apply_faction_consequence_tick` | P1-D ✅, `qa_live_20turn_hostile.py` (not run) | `story-engine.md` | Theme regex false positives/negatives | Live hostile script |
| Room audit | Verified complete (deterministic) | `server.py` `_apply_room_audit` | P1-C ✅ | `story-engine.md` | Drift flag only; no auto-repair | — |
| Curated scenarios | Implemented but unverified | `scenarios.py`, `new-story.tsx` | Indirect via `story/new` | `overview.md` | Only 3 presets | Live preset smoke test |
| Context budget governor | Implemented but unverified | `memory.enforce_context_budget` | None dedicated | `story-engine.md` | Heuristic token estimate | 15+ turn budget test |
| Scoring / rankings | Unknown | — | — | — | No subsystem found | N/A unless added |

**Status definitions used:**

- **Verified complete** — Deterministic code + verification script passed in 2026-06-17 pass, or unit logic confirmed in code review.
- **Implemented but unverified** — Code exists; live/integration proof missing or stale.
- **Partial** — Some layers exist; gaps documented.
- **Unknown** — Not found in code.