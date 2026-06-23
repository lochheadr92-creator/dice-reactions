# Decision Log

Architecture Decision Records (ADRs) supported by evidence in this repository on the **`emergent`** branch. Dates reflect when the decision is documented here; implementation commits noted where known.

**`memory/PRD.md`** is the planning and conformance tracker — not evidence for accepted ADR status.

---

## ADR-001: State versus narrative authority

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | LLM-generated prose can contradict persisted simulation state or invent mechanics visible to players. |
| **Decision** | Persisted `rolling_state`, `ledger`, and guarded `state` are authoritative. Narrative is output. Deterministic guards and `consolidate_rolling_state` correct LLM drift before persistence. |
| **Alternatives considered** | Narrative-first (reject — causes drift); full deterministic sim without LLM (reject — product is LLM-narrated). |
| **Consequences** | Guard pipeline must run every turn; protected keys must be maintained in `memory.py`. |
| **Risks** | LLM still proposes initial rolling state; guards are heuristic, not complete. |
| **Files affected** | `AGENTS.md`, `backend/server.py`, `backend/memory.py` |
| **Tests required** | `verify_p0_object_permanence.py`, guard unit tests in `test_custom_world_system.py` |
| **Evidence** | `AGENTS.md` lines 7–11; `consolidate_rolling_state` in `memory.py`; guard calls in `story_action` route |

---

## ADR-002: Dual-layer narrative gateway (backend API + frontend presentation)

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | LLM output occasionally leaks engine tags into `<narrative>`. API consumers include web client and potential future clients. |
| **Decision** | (1) Backend strips dev fields and internal state keys when `developer_mode` is false. (2) Frontend `sanitize.ts` strips leaked tags/mechanic lines from rendered paragraphs only, without mutating stored turn objects. (3) `_validate_parsed` rejects invalid player-facing output with one retry. |
| **Alternatives considered** | Frontend-only filter (reject — other clients exposed); backend-only (reject — truncated tags still render in edge cases). |
| **Consequences** | Two sanitization layers to maintain; export endpoint currently bypasses player sanitization. |
| **Risks** | Export and dev mode leaks; regex maintenance burden. |
| **Files affected** | `backend/server.py`, `frontend/src/sanitize.ts`, `frontend/app/play/[id].tsx` |
| **Tests required** | `verify_p1_immersion_integrity.py`, `verify_p15_microfixes.py` |
| **Evidence** | `sanitize.ts` header comment; `_sanitise_turn_for_player`; P1-A/P1.5 scripts passed 2026-06-17 |

---

## ADR-003: Turn log persistence (not full event sourcing)

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Chronicles need history; long sessions need compressed state. |
| **Decision** | Append turns via `insert_one`. Maintain latest `rolling_state` on session document. Rebuild prompts from recent turn replay + `<prior_state>`. `reset_session` deletes turns and clears rolling state. No aggregate rebuild from event log. |
| **Alternatives considered** | Full event sourcing with aggregate rebuild (not implemented); overwrite turns in place (reject — loses audit trail). |
| **Consequences** | Reset is destructive; no immutable event store. |
| **Risks** | `rolling_state` overwrite can lose history not captured in turn log fields. |
| **Files affected** | `backend/server.py` |
| **Tests required** | None dedicated |
| **Evidence** | `insert_one` for turns; `reset_session` deletes `turns` collection entries |

---

## ADR-004: Context retrieval budgeting (prompt trim, not RAG)

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Long chronicles exceed model context limits. |
| **Decision** | `enforce_context_budget` trims oldest/low-priority messages and compresses `<prior_state>` JSON. Budgets vary by `cost_mode` and `mode` via `resolve_context_budget`. Protected recent messages and protected rolling keys are not dropped. |
| **Alternatives considered** | Vector retrieval over turn archive (not implemented); unbounded prompt growth (reject). |
| **Consequences** | Heuristic token estimate (`chars/4`); old narrative may be dropped from prompt while surviving in DB. |
| **Risks** | Retrieval starvation if budget too aggressive; repetition if too much history kept. |
| **Files affected** | `backend/memory.py`, `backend/ai_config.py`, `backend/server.py` |
| **Tests required** | PRD P1 15+ turn stress (not run) |
| **Evidence** | `enforce_context_budget` implementation; `result["budget"]` attached in `_generate_turn` |

---

## ADR-005: Object identity canonicalization

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Same physical object with label drift accumulated contradictory rows in rolling memory (QA #2). |
| **Decision** | `_normalize_object_name` + `canonicalize_object_registry` collapse `object_locations` and `inventory_objects` to one row per identity; status priority prefers terminal states. |
| **Alternatives considered** | Trust LLM to prune (reject — demonstrated bloat). |
| **Consequences** | Heuristic identity matching may merge distinct objects with similar labels. |
| **Risks** | False merge on ambiguous names. |
| **Files affected** | `backend/memory.py`, `backend/server.py` |
| **Tests required** | `verify_p0_object_permanence.py` ✅ |
| **Evidence** | P0 all scenarios passed 2026-06-17 |

---

## ADR-006: NPC memory bounds and local faction ticks

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | `npc_memory` and `faction_pressure` could grow without bound; social consequences need light determinism. |
| **Decision** | `_apply_npc_memory_bounds` caps remembers list, decays stale minors, caps NPC count. `_apply_faction_consequence_tick` counts theme repeats in memory and bumps existing `faction_pressure` entries after threshold. |
| **Alternatives considered** | Global faction simulation graph (not implemented); unbounded LLM lists (reject). |
| **Consequences** | Regex theme matching; no actor graph resolution. |
| **Risks** | Missed or false faction ticks. |
| **Files affected** | `backend/server.py` |
| **Tests required** | `verify_p1_immersion_integrity.py` P1-D ✅ |
| **Evidence** | P1-D scenarios passed 2026-06-17 |

---

## ADR-007: OpenRouter model picker validation

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Admin UI exposes many models; invalid IDs cause provider errors. |
| **Decision** | `admin_post_settings` rejects `model` not in `SUPPORTED_MODELS` catalog. Runtime uses session-locked `active_model` + `chat_completion_with_meta` (via `gateway.invoke_llm`) fallback chain. |
| **Alternatives considered** | Free-form model string (reject — poor UX/errors). |
| **Consequences** | Catalog must be updated manually in `ai_service.py`. |
| **Risks** | Catalog drift vs OpenRouter availability; free-tier rate limits. |
| **Files affected** | `backend/ai_service.py`, `backend/server.py`, `frontend/app/settings.tsx` |
| **Tests required** | Manual admin POST negative test (not automated) |
| **Evidence** | `admin_post_settings` HTTP 400 on unsupported model |

---

## ADR-008: Developer-only history and telemetry gating

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Debug payloads needed for tuning; must not appear for normal players. |
| **Decision** | Server `developer_mode` (admin-only) controls `[DEV_MODE: ON]` prompt marker when request `debug_mode` is also true. Player routes always use `_sanitise_*` regardless of `developer_mode`. Client 7-tap unlock sets local `developerUnlocked` only (display preferences). |
| **Alternatives considered** | Per-session only (partially used via `debug_mode`); always-on debug (reject); `developer_mode` bypassing player sanitisation (reject — ADR-012 correction). |
| **Consequences** | Two flags for prompt behaviour; player API never returns raw state; admin changes require operator credentials. |
| **Risks** | Device UUID leak still grants session access; no rate limiting. |
| **Files affected** | `backend/server.py`, `frontend/app/settings.tsx`, `frontend/app/play/[id].tsx` |
| **Tests required** | Integration with `debug_mode: false` (not run this pass) |
| **Evidence** | `bumpVersionTap` in `settings.tsx`; `debug_marker` logic in `story_action` |

---

## ADR-009: Anti-Hallucination Gateway (Ch 31 incremental)

| Field | Detail |
|-------|--------|
| **Date** | Implemented `b4a2891`; documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | LLM can contradict established object, injury, and death facts across turns. |
| **Decision** | Introduce `gateway.py` with: `invoke_llm` as sole LLM entry; `build_immutable_truth_block` (PREVENT); `strip_illegal_state_changes` (STRIP); `detect_prose_contradictions` (DETECT + retry); `update_death_registry` / `update_destruction_registry`. Wire into `_build_messages`, `_generate_turn`, `_full_validate`, and post-parse guard pipeline. |
| **Alternatives considered** | Prompt-only truth (reject — demonstrated drift); direct `ai_service` calls (reject — bypass risk). |
| **Consequences** | All new LLM paths must use `gateway.invoke_llm`; contradiction retry adds latency on failure. |
| **Risks** | Heuristic death/object detection; not full Ch 31 conformance. |
| **Files affected** | `backend/gateway.py`, `backend/server.py` |
| **Tests required** | `test_anti_hallucination_gateway.py` ✅, `test_gateway_e2e.py` ✅ |
| **Evidence** | Commit `b4a2891`; 47-test bundle passed 2026-06-17 |

---

## ADR-010: Relationship calculus — engine-owned NPC→player vectors (Ch 29)

| Field | Detail |
|-------|--------|
| **Date** | Implemented `a52b66d`; documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Social state drifted when LLM authored relationship feelings each turn. |
| **Decision** | `relationships.py` maintains `rolling_state['relationship_vectors']` (protected key). Prior vectors are authoritative; LLM injection ignored. Each turn: neglect decay, regex-detected event deltas (Ch 29.8 table + extensions), derived behavioural state, coarse stance sync on `npcs`, `build_relationship_block` for prompt. **Directionality: NPC→player only.** |
| **Alternatives considered** | LLM-authored `relationship_threads` only (reject — no determinism); full NPC graph (not implemented). |
| **Consequences** | `relationship_threads` remains for seeding/narrative but not for vector mechanics; no NPC↔NPC edges. |
| **Risks** | Regex false positives/negatives; identity bonds decay slower only. |
| **Files affected** | `backend/relationships.py`, `backend/memory.py`, `backend/server.py` |
| **Tests required** | `test_relationship_calculus.py` ✅ (`test_engine_owns_vectors_ignores_llm_injection`) |
| **Evidence** | Commit `a52b66d`; `test_gateway_e2e.py` relationship turn assertion |

---

## ADR-011: HUD shaping — DNG / MOM / PRS (non-prescriptive)

| Field | Detail |
|-------|--------|
| **Date** | Implemented `ff1858d`; documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Objective/quest chips steered player behaviour; product requires condition + pressure without solutions. |
| **Decision** | `hud.shape_hud` strips Objective/Goal keys; ensures Danger (`none`–`critical`) and Momentum (`surging`–`lost`) chips; sets single Pressure line via `derive_pressure` rejecting prescriptive language. Frontend renders DNG, MOM, PRS labels in `play/[id].tsx`. |
| **Alternatives considered** | LLM-only HUD (reject — prescriptive leaks); Objective bar (reject — quest-marker UX). |
| **Consequences** | HUD is engine-shaped every turn after guards; LLM pressure used only if non-prescriptive. |
| **Risks** | Fallback pressure phrases may feel generic. |
| **Files affected** | `backend/hud.py`, `backend/server.py`, `frontend/app/play/[id].tsx` |
| **Tests required** | `test_hud.py` ✅ |
| **Evidence** | Commit `ff1858d`; `test_hud.py` assertions on chip vocabularies |

---

## Candidate decisions requiring confirmation

These topics appear in `memory/PRD.md` or design briefs but **lack sufficient code evidence** for accepted ADR status:

| Topic | Finding |
|-------|---------|
| Actor caps / actor resolution | No resolver module; NPCs are LLM-authored lists (PRD Ch 25 ❌) |
| NPC↔NPC relationship edges | Only NPC→player vectors implemented |
| Deterministic utility AI | Foundation implementation exists in shadow mode; live/load-bearing activation remains a separate decision |
| Gravity-based memory retention | Only context budget + rolling merge |
| Formal event sourcing | Turn log only (see ADR-003) |

Promote to ADR when implementation and tests exist.

**Explicitly N/A:** historical score equivalence, NaN/infinity ranking guards — symbols never existed in this repository's git history.

---

## ADR-012: Device-scoped ownership and admin API key (P0 security)

| Field | Detail |
|-------|--------|
| **Date** | Documented 2026-06-17 |
| **Status** | Accepted |
| **Context** | Admin routes, export, and session mutations were reachable without server-side authentication. `device_id` was stored but not verified on most routes. |
| **Decision** | (1) Centralise ownership in `security.fetch_owned_session`. (2) Transport device credential via `X-Device-Id` header on all protected story routes; `POST /story/new` binds owner via body `device_id`. (3) Protect `/api/admin/*` with `ADMIN_API_KEY` env + `X-Admin-Api-Key` header (constant-time compare, fail closed). (4) Split export: player `/export` and all player session responses always sanitised; administrative `/export/raw` requires admin key + ownership. (5) Wrong-owner and unknown-session failures are indistinguishable (404). (6) Do not embed admin credentials in the Expo client; remove server-admin UI from public Settings. |
| **Alternatives considered** | Full user accounts (reject — out of P0 scope); `developer_mode` as auth (reject); `device_id` in query strings (reject — credential in URLs); 403 on wrong owner (reject — enables enumeration). |
| **Consequences** | Operators use curl/out-of-band tooling for admin; live integration tests using `/export/raw` need `ADMIN_API_KEY`. |
| **Risks** | Device UUID leak still grants access; no rate limiting; CORS still `*` by default. |
| **Files affected** | `backend/security.py`, `backend/server.py`, `frontend/src/api.ts`, `frontend/app/settings.tsx`, `frontend/app/play/[id].tsx`, `frontend/app/index.tsx`, `backend/tests/test_security.py`, `docs/api.md` |
| **Tests required** | `test_security.py` (25 cases) |
| **Evidence** | Release-gate correction pass 2026-06-17 |

---

## ADR-013: Paid-endpoint abuse controls and player allowlist serializers (P0/P1 hardening)

| Field | Detail |
|-------|--------|
| **Date** | 2026-06-17 |
| **Status** | Accepted |
| **Context** | `POST /story/new` invokes a paid LLM call with no rate limits. Player responses used denylist `pop()` sanitisation. Health endpoint leaked runtime config. Raw export required device credential alongside admin key. |
| **Decision** | (1) MongoDB-backed rate limits on story creation: per-IP, per-device, global concurrent; fail before LLM/insert; 429 generic body; fail closed on limiter errors. (2) `player_api.py` explicit allowlist serializers for all player routes; state/ledger values scrubbed via existing `_scrub_meta_from_text`. (3) `/health` returns only `status` + `llm_configured`. (4) Operator `/export/raw` and diagnostics require admin key only. (5) Generic 502 client errors; explicit CORS headers when origins are not `*`. |
| **Alternatives considered** | In-memory-only rate limiter (reject — unbounded keys); full user accounts (reject — out of scope); keeping denylist sanitisation (reject — unknown fields leak). |
| **Consequences** | Deployments behind proxies must set `TRUSTED_PROXY_COUNT`; live tests need valid `OPENROUTER_API_KEY`. |
| **Files affected** | `rate_limit.py`, `player_api.py`, `server.py`, `security.py`, `frontend/src/api.ts`, `frontend/src/storage.ts`, tests |
| **Tests required** | `test_rate_limit.py`, `test_player_api.py`, extended `test_security.py` |
| **Evidence** | 83-test deterministic bundle passed 2026-06-17 |

---

## ADR-014: Phase 2 Quick Start becomes the default New Chronicle experience

| Field | Detail |
|-------|--------|
| **Date** | 2026-06-18 |
| **Status** | Accepted |
| **Context** | The prior New Chronicle screen defaulted to an abstract, scroll-heavy worldbuilding form. Product direction requires a concrete story-first default that reduces cognitive load without breaking the existing backend contract or the legacy builder. |
| **Decision** | Introduce `frontend/src/newstory/QuickStart.tsx` as the default entry flow on `frontend/app/new-story.tsx`. Quick Start uses six deterministic selections (World, Character, Tone, Want, Fear, Who matters most), zero mandatory typing, and a deterministic review summary. Submission continues through the existing `POST /api/story/new` payload only, mapped to top-level story fields plus `custom_world_setup.{want,fear,whoMatters}` with engine `mode` fixed to `advanced`. |
| **Alternatives considered** | Full immediate extraction of the old builder (reject — Phase 4 scope); introducing a second API contract (reject — backend stability and migration risk); exposing secret/engine terms in Quick Start (reject — violates product language and Phase 1 secrecy constraints). |
| **Consequences** | `new-story.tsx` now hosts a small flow switcher: Quick Start by default, preserved Advanced Builder behind an explicit toggle. Frontend must guard against duplicate submit locally because story creation is paid/slow. Test files must live outside Expo Router `app/` so Metro does not bundle them as routes. |
| **Risks** | The preserved Advanced Builder remains a large file until a later extraction. Guided Start is still absent, so some players still need the Advanced path for deeper setup. |
| **Files affected** | `frontend/app/new-story.tsx`, `frontend/src/newstory/QuickStart.tsx`, `frontend/src/api.ts`, `frontend/src/newstory/options.ts`, `frontend/__tests__/new-story.test.tsx` |
| **Tests required** | Frontend deterministic flow tests + browser preview regression |
| **Evidence** | `frontend/__tests__/new-story.test.tsx` (10 passed), preview regression run 2026-06-18 |

---

## ADR-015: Phase 3 adds Guided Start while preserving the single creation contract

| Field | Detail |
|-------|--------|
| **Date** | 2026-06-18 |
| **Status** | Accepted |
| **Context** | Quick Start reduced cognitive load, but players still needed a richer curated path before falling all the way back to the legacy builder. Product direction requires a three-mode structure without introducing a second backend creation API or exposing engine terminology. |
| **Decision** | Add `Guided Start` as a dedicated curated flow alongside `Quick Start` and the preserved `Advanced Builder`. Guided Start remains fully deterministic, requires no typing, and uses existing catalogs from `frontend/src/newstory/options.ts`. It maps its world turning point into `custom_premise`, maps world/character/tone/difficulty to existing top-level request fields, maps want/fear/who matters most into `custom_world_setup`, and keeps backend engine `mode` fixed to `advanced`. |
| **Alternatives considered** | New `/story/new-guided` endpoint (reject — contract duplication); free-text-heavy guided setup (reject — higher abandonment, less deterministic); refactoring the full Advanced Builder first (reject — Phase 4 scope). |
| **Consequences** | `new-story.tsx` now owns three mode states and one shared submission lock. Mode switching must preserve each mode’s selections independently. Public Advanced Builder intentionally hides dev-only engine/debug controls unless the existing local developer unlock is active. |
| **Risks** | `new-story.tsx` remains structurally heavy until later extraction. Guided Start currently covers only fields already supported by the existing request contract. |
| **Files affected** | `frontend/app/new-story.tsx`, `frontend/src/newstory/GuidedStart.tsx`, `frontend/src/newstory/QuickStart.tsx`, `frontend/src/newstory/options.ts`, `frontend/src/api.ts`, `frontend/__tests__/new-story.test.tsx` |
| **Tests required** | Backend onboarding tests, frontend deterministic flow tests, browser preview regression |
| **Evidence** | `backend/tests/test_onboarding_hooks.py` (16 passed), `frontend/__tests__/new-story.test.tsx` (17 passed), preview regression run 2026-06-18 |

---

## ADR-016: Early-Game Pacing Governor v1 (prompt guidance + Stage 1 structural enforcement)

| Field | Detail |
|-------|--------|
| **Date** | 2026-06-20 |
| **Status** | Accepted |
| **Context** | Opening turns often spent atmosphere/setup before a concrete situation. Existing system-prompt rules mention scene advancement but do not constitute an autonomous world heartbeat. |
| **Decision** | Add pure `pacing.py` module. Compute immutable pacing stage once from pre-generation `session.turn_count` (0→Stage 1 … 3→Stage 4; ≥4→none). Inject non-persisted internal system directives in `_build_messages`. Stage 1 only: structural field-presence validation after format checks, before gateway contradiction detection. Pacing failures share the single existing validation retry. Stage 1 may author genesis truth; Stages 2–4 may guide continuity/surfacing/direction from existing state only — not invent autonomous world movement. |
| **Alternatives considered** | Prompt-only pacing (reject — no structural enforcement); separate pacing retry budget (reject — violates one-retry-total); persisting directives in rolling state (reject — leak risk). |
| **Consequences** | Validation kind extended with `"pacing"`; opening prompt strengthened in `_create_new_story`; optional dev-only `pacing_stage3_no_engine_development` diagnostic when no engine-owned development exists. |
| **Risks** | Field-presence validation cannot distinguish atmospheric vs concrete pressure; qualitative pacing remains provider-dependent; not a Living World Test. |
| **Files affected** | `backend/pacing.py`, `backend/server.py`, `backend/tests/test_early_game_pacing.py`, `docs/*` |
| **Tests required** | `test_early_game_pacing.py` ✅; existing 83-test regression bundle ✅ |
| **Evidence** | 118-test bundle passed 2026-06-20 on `emergent` |

---

## ADR-017: Secret Reveal Trigger v1 (explicit player confession only)

| Field | Detail |
|-------|--------|
| **Date** | 2026-06-20 |
| **Status** | Accepted |
| **Context** | Onboarding secrets are stored unrevealed in `secret_registry` but had no deterministic reveal path. Automatic, semantic, or LLM-inferred reveals risk false positives and mechanic leaks. |
| **Decision** | Add pure `secrets.py`. Reveal only on `explicit_player_confession` detected by narrow regex intent (with negation guards). Compute reveal once per request before `_generate_validated_turn`; persist only after successful generation via copy-on-write working rolling state. Inject non-persisted internal system directive after pacing directive. Strip any model-emitted `secret_registry` during consolidation. Legacy entries without `reveal_policy` default to explicit confession. |
| **Alternatives considered** | LLM intent classification (reject — non-deterministic, extra provider risk); keyword match on secret text (reject — leaks content into matcher); timer/NPC/evidence triggers (reject — v1 scope); persisting directive in turns (reject — leak risk). |
| **Consequences** | `story_action` uses generation-session copy; authoritative registry enforced post-consolidation; debug may record reveal index/mode but never secret text. |
| **Risks** | False negatives on unusual confession phrasing; narrative quality of reactions remains provider-dependent; no automatic dramatic timing. |
| **Files affected** | `backend/secrets.py`, `backend/server.py`, `backend/tests/test_secret_reveal.py`, `docs/*` |
| **Tests required** | `test_secret_reveal.py` ✅; `test_onboarding_hooks.py` ✅; full deterministic bundle ✅ |
| **Evidence** | 242 deterministic tests passed 2026-06-20 on `emergent` |

---

## ADR-018: Session Action Concurrency Guard v1 (Mongo-backed lease)

| Field | Detail |
|-------|--------|
| **Date** | 2026-06-20 |
| **Status** | Accepted |
| **Context** | Overlapping `POST /story/action` requests (multiple tabs, retries, workers) could race on `turn_count`, `rolling_state`, secret reveals, and provider calls. In-memory `asyncio.Lock` does not span processes. |
| **Decision** | Store an engine-only lease on the session document (`action_lock_token`, `action_lock_acquired_at`, `action_lock_expires_at`). Acquire atomically via `find_one_and_update` before reveal detection, turn-number calculation, or any provider call. Reject conflicts with HTTP **409** and zero provider use. Keep one token per request through retry and persistence. Final session write requires matching lease token and expected `turn_count` (optimistic CAS). Fold model-lock fields into the same CAS update. Release in `finally` with token-scoped `$unset`. Default lease 600s (`ACTION_LOCK_LEASE_SEC`, clamped 60–3600). |
| **Alternatives considered** | `asyncio.Lock` / process mutex (reject — not cross-worker); turn-number check alone (reject — does not block provider spend); Mongo multi-document transactions (reject — not used elsewhere; compensating rollback retained); idempotency keys on client (reject — out of v1 scope). |
| **Consequences** | Lease fields excluded from player serializers and prompt-safe rolling; raw admin export may include them. CAS conflict deletes only the exact inserted turn by `TurnRecord.id` — no blind session snapshot restore. Stale leases expire and may be reclaimed atomically. |
| **Risks** | Reset/delete/mode endpoints remain unguarded; duplicate historical `(session_id, turn_number)` rows defer unique index creation; clock skew beyond expiry model not addressed. |
| **Files affected** | `backend/action_concurrency.py`, `backend/server.py`, `backend/tests/test_action_concurrency.py`, `docs/*` |
| **Tests required** | `test_action_concurrency.py` ✅; `test_secret_reveal.py` regression ✅; full deterministic bundle ✅ |
| **Evidence** | 306 deterministic tests passed 2026-06-20 on `emergent` |

---

## ADR-019: Replayability Engine v1 (session `replayability_state`)

| Field | Detail |
|-------|--------|
| **Date** | 2026-06-20 |
| **Status** | Accepted |
| **Context** | Chronicles need deterministic run variation (identity, opening archetype, pressure foreground, delayed echoes) without storing engine truth in `rolling_state` or exposing it to players. |
| **Decision** | Add pure modules: `run_identity.py` (narrative + **causal** closed enums; `has_secret` bool; difficulty → `severity_multiplier` only), `opening_state.py` (14 archetypes with **structured opening facts** + `pressure_origins`), `pressure_graph.py` (causal nodes: `kind`, `magnitude`, `trend`, `scope`, links; trend-based movement; foreground scoring with recency penalty; one-shot threshold crossings in `threshold_crossings`), `consequence_echoes.py` (schedule/mature/fire max 1/turn from **confirmed source events only**), orchestrated by `replayability.py`. Persist on `sessions.replayability_state` only. **No** `engine_events` log — canonical transitions live in `rolling_state` (delayed consequences, relationship vectors, faction ticks, destruction registry) and `pressure_graph.threshold_crossings`; replayability keeps bounded `transition_receipts` (IDs + receipt type) for idempotency only. Echo sources: `collect_qualifying_echo_sources` after guard pipeline; **never** player text / narrative parsing. `prepare_action_turn` before provider (tick, mature, fire, frozen directives); `finalize_action_turn` after guards. Policy A legacy skip. |
| **Alternatives considered** | Store in `rolling_state` (reject — LLM merge risk); keyword echo scheduling from player text (reject — not state-as-truth); `engine_events` as second history (reject — duplicates rolling_state). |
| **Consequences** | `SessionRecord.replayability_state`; rollback restores field; player serializers exclude field; raw admin export includes full session. |
| **Risks** | Unsupported echo categories (theft/violence/promise) remain unsupported until structured guard outputs exist; qualitative surfacing remains provider-dependent; not a Living World Test. |
| **Files affected** | `backend/replayability.py`, `backend/run_identity.py`, `backend/opening_state.py`, `backend/pressure_graph.py`, `backend/consequence_echoes.py`, `backend/server.py`, `backend/tests/test_*replayability*`, `docs/*`, `.gitignore` |
| **Tests required** | Five replayability test modules ✅; full deterministic bundle ✅ |
| **Evidence** | 390 deterministic tests passed 2026-06-20 on `emergent` (contract-correction pass) |

---

## ADR-020: Living Cast Engine v1 (NPC agendas + world moves + arc diversity)

| Field | Detail |
|-------|--------|
| **Date** | 2026-06-20 |
| **Status** | Accepted — **provisional integrated local substitute on `recovery/living-cast-working-tree` only** (unmerged, not deployed, not covered by emergent CI, not merge-ready) |
| **Branch** | `recovery/living-cast-working-tree` @ `4dadb3f` — **absent on `emergent` HEAD** @ `d8b9caf` |
| **Context** | NPCs only reacted when the player addressed them. Chronicles needed deterministic independent world movement, persistent NPC priorities, and narrative variety without extra provider calls or LLM-owned simulation truth. PRD Ch 25 (Actor Resolution) and Ch 27 (Utility AI) modules are not present in the repo. |
| **Decision** | Add three pure modules: `npc_agendas.py` (engine-owned agendas in `replayability_state["npc_agendas"]`; closed enums; **canonical `npc_id` stable across run seeds**; agenda selection uses `run_seed + npc_id + namespace`; evolve from structured events only), `npc_world_moves.py` (bounded move catalog; **local** tier eligibility + utility scoring — not PRD Ch 25/27; explicit move targets; real effects on relationship vectors, faction ticks, pressure graph; **bounded transition receipts** in `replayability_state["npc_move_receipts"]` — not rolling_state; `[NPC_WORLD_MOVE_V1]` directive), `arc_diversity.py` (engine beat history; primary emphasis only). Orchestrate in `replayability.prepare_action_turn` **before** provider: tick agendas → select/commit ≤1 move with targets → apply effects → append receipt → schedule qualifying echoes → select primary beat → freeze directives. Policy A legacy skip inherited. **No canonical event-sourcing module exists** — receipts are idempotency/transition records, not world-event history. |
| **Why engine-owned agendas** | Agendas must survive model merge and must not leak to players; `rolling_state` is LLM-merged each turn. |
| **Why local scoring/tier policy (not Utility AI / Actor Resolution)** | PRD Ch 25/27 full Bible contracts are absent — only PRD tracker summaries exist for Chapters 22–32; Living Cast v1 uses bounded **local substitutes** until canonical systems land. |
| **Why canonical NPC IDs exclude run seed** | Run seed varies agenda priorities, not actor identity; same scenario NPC must keep the same `npc_id` across chronicles. |
| **Why moves require real state effects and explicit targets** | State-as-truth: no invented gather/defect outcomes; ineligible when no authoritative target exists. |
| **Why arc diversity tracks engine beats** | Model prose cannot be classified reliably; variety governs directive emphasis only — not truth. |
| **Why critical consequences override variety** | Urgent pressure and fired echoes must not be suppressed for cosmetic rotation. |
| **Why echoes reference receipt IDs** | `npc_move_receipts` + `transition_receipts` dedupe; no rolling_state event log; no player-text sources. |
| **Alternatives considered** | LLM-chosen NPC actions (reject); agendas in `rolling_state` (reject); offline background sim (reject — v1 scope); inventory transfers without ledger API (reject). |
| **Consequences** | `npc_move_receipts` on session document only; `engine_world_events` removed from rolling_state; player serializers omit Living Cast fields; reset clears receipts with replayability; directive order: pacing → opening (t1) → secret → world → pressure → echo; `investigate` not a universal fallback. |
| **v1 proves** | NPCs may act during player turns; agendas persist/evolve from structured events; moves alter state before narration; runs diverge by seed; low-urgency beat repetition penalized; qualifying move events schedule echoes; no extra provider calls. |
| **v1 does not prove** | Offline/real-time sim; every NPC every turn; semantic free-text; full social sim; arbitrary inventory; every move echoes; perfect variety; live provider quality. |
| **Files affected** | `npc_agendas.py`, `npc_world_moves.py`, `arc_diversity.py`, `replayability.py`, `consequence_echoes.py`, `server.py`, Living Cast test modules, `docs/*` |
| **Tests required** | Recovery branch: `test_npc_agendas.py`, `test_npc_world_moves.py`, `test_arc_diversity.py`, `test_living_cast_integration.py` ✅ locally — **not covered by emergent CI** |
| **Evidence** | Recovery branch local pytest passes 2026-06-20; **not verified on `emergent` HEAD**; golden-path blockers remain (pressure authority, relationship provenance) |

---

## ADR-021: Chapter 14 P1 stress substrate

| Field | Detail |
|-------|--------|
| **Date** | Accepted on `emergent` 2026-06-24 via PR #1 / merge commit `5c042fb` |
| **Status** | Accepted — **`TURN_INTEGRATION_VERIFIED` / `UTILITY_STRESS_INPUT_COMPLETE`** |
| **Context** | Foundation Utility AI required an authoritative accumulated `stress_level`; model-authored or stateless stress would violate state authority and Chapter 14 accumulation. |
| **Decision** | Persist deterministic per-actor stress in `rolling_state["actor_stress"]`; derive seeded capacity; update only living actors carrying active agendas; reassert engine ownership after model consolidation; emit stress into foundation utility inputs. |
| **Identity boundary** | When authoritative stress values are present, their stress and capacity values are committed into foundation snapshot identity. Stress-absent fixtures preserve the pre-P1 hash. |
| **Scope** | P1 remains limited to living actors with active agendas. Widening updates to every scene-present actor is deferred to a separate future design decision. |
| **Utility consequence** | The authoritative stress input is complete, but Utility AI remains shadow-mode and is not authorised to drive live NPC actions. Activation requires a separate decision and proof. |
| **Files affected** | `backend/stress.py`, `backend/foundation_snapshot.py`, `backend/replayability.py`, `backend/server.py`, focused tests, ADR/runbook/canon-delta evidence |
| **Verification** | Four touched backend files compiled; focused suite 69 passed; turn-path integration 2 passed; stress-free hash matched pre-P1; deterministic GitHub CI passed. |
| **Authority note** | Runtime code and passing tests on `emergent` are controlling evidence. Agent summaries, old PR descriptions, and unmerged branches do not override them. |


---

## ADR-022: Chapter 14 P2 stress behavioural bands + Utility AI integration

| Field | Detail |
|-------|--------|
| **Date** | Proposed 2026-06-24 (unmerged draft PR on `codex/ch14-stress-behaviour`, base `02646ab`) |
| **Status** | Proposed — **shadow-only; not merged, not authorised for production** |
| **Context** | P1 (ADR-021) made `stress_level` authoritative and snapshot-emitted. P2 consumes it: derive a behavioural band on read and modify canonical Ch 27 utility weights (goal-narrowing 14.24/14.27). Ch 14 is non-numerical, so all cut-points/modifiers are designed extensions. |
| **Decision** | Add pure `stress.evaluate_stress_behaviour` (4 bands CALM/ELEVATED/STRAINED/OVERLOADED at 25/50/75; lower-inclusive, OVERLOADED includes 100). Apply per-band weight modifiers exactly once in `utility_ai.select_action` after `compute_dimension_weights`. `stress_reduction` stays x1.0 (Ch 27.4.2 already scales by stress/100). |
| **Supersedes** | The ADR-021 6-band "Proposed constants" table (Stable/.../Collapse); P2 ratifies a 4-band model. The Critical/Collapse archetype end moves to P3. |
| **Fail-closed** | Missing/invalid stress is never CALM: no band, identity modifiers, `stress_input_valid=False`, `replacement_authorised` forced False, blocker code recorded, candidate visible in shadow but never an authorised replacement, no max/emergency bonus. Codes: MISSING/INVALID/NONFINITE/OUT_OF_RANGE_STRESS_LEVEL. |
| **Determinism** | Pure functions; candidate not mutated -> `candidate_set_hash`/noise/tie-break stable; P2 diagnostics excluded from `state_hash`; CALM/invalid apply x1.0 so weights/utility/hash byte-identical to pre-P2. |
| **Scope** | P1 accumulation/capacity/decay/actor-scope/off-screen unchanged. Utility AI stays shadow-only. P3 breaking points and P4 collective stress deferred. |
| **Files affected** | `backend/stress.py`, `backend/utility_ai.py`, `backend/tests/test_stress_behaviour.py`, `docs/adr-022-stress-behaviour-bands.md`, canon-delta / feature-status / failure-mode / current-state docs |
| **Verification** | Both touched files compile; focused non-live bundle 139 passed + 1 pre-existing unrelated failure (`test_prompt_fingerprint` server.py commit-range vs `9da1ae2`); `test_stress_behaviour.py` 66 passed; determinism/hash-boundary green. Turn-path tests needing fastapi+MongoDB not run in this sandbox. |
| **Authority note** | Proposal only. Runtime code + passing tests on `emergent` remain controlling; this unmerged branch does not override them. |



---

## ADR-023: Pressure authority — `pressure_graph` canonical, `active_pressures` derived

| Field | Detail |
|-------|--------|
| **Date** | Proposed 2026-06-24 |
| **Status** | Proposed — decision recorded; implementation deferred (documentation-only ADR). On `emergent` via a dedicated docs branch; not part of the Ch 14 stress PR #3. |
| **Context** | Pressure has two competing sources: engine-owned causal `replayability_state.pressure_graph` (sole source for stress / Utility AI / snapshot identity) and LLM-authored prose `rolling_state.active_pressures` (pacing gate, persisted, not causal, not player-facing). The latter is a narrative-derived pressure authority — violates "State is truth, narrative is output". |
| **Decision** | `pressure_graph` is the single canonical pressure authority. `active_pressures` becomes a derived, engine-owned, read-only projection of the `pressure_graph` foreground; model-emitted values are stripped/overwritten in consolidation. The `active_pressures` key is preserved for compatibility and snapshot `rolling_keys` stability. No pressure authority may come from narrative/prose/LLM output. |
| **Amends** | ADR-019 (Replayability / `pressure_graph`), ADR-016 (Early-Game Pacing / `active_pressures` validation). |
| **Determinism** | `active_pressures` values are not in `source_state_hash`; key retained so `rolling_keys` and snapshot identity are unchanged. Projection must be pure/deterministic over `pressure_graph`. Causal paths already read only `pressure_graph`. |
| **Migration** | (1) ADR; (2) engine `project_active_pressures` + strip/overwrite in consolidation; (3) repoint pacing Stage-1 to engine pressure; (4) drop LLM `active_pressures` prompt obligation. Steps 2-3 core; Step 4 prompt-only follow-up. |
| **Files (impl task)** | `replayability.py`, `pressure_graph.py`, `pacing.py`, `server.py`, `memory.py`, `opening_state.py`; tests `test_early_game_pacing.py` (+ regression). No change to `foundation_snapshot.py`, `stress.py`, `utility_ai.py`, `hud.py`, frontend. |
| **T2** | Live turn-path verification sequencing is owner-directed; current decision is to run the T2 static turn-path trace before implementing ADR-023. Status stays `TURN_INTEGRATION_UNVERIFIED`; this ADR does not promote it. |
| **Non-goals** | No P3; no relationship provenance remediation; no full event sourcing; no unrelated doc reconciliation; no code/test changes (documentation only). |
| **Full ADR** | `docs/adr-023-pressure-authority.md` |
