# Failure Modes

For each mode: detection, prevention, recovery, and **current protection status** based on code/tests on the **`emergent`** branch.

**Protection status:** Protected / Partial / Unprotected / N/A

---

## FM-01: LLM inventing state

| Field | Detail |
|-------|--------|
| **Trigger** | Model emits new `rolling_state` fields, objects, or consequences not grounded in play. |
| **Effect** | Simulation drift; contradictions across turns. |
| **Detection** | Guard adjustment logs; gateway strip messages; player reports; dev panel compare. |
| **Prevention** | `build_immutable_truth_block` in prompt; `strip_illegal_state_changes`; `consolidate_rolling_state` protected keys; object canonicalization; ledger guards. |
| **Recovery** | Guards rewrite parsed turn before persist; contradiction retry; manual session reset. |
| **Files** | `gateway.py`, `memory.py`, `server.py` |
| **Tests** | `verify_p0_object_permanence.py` ✅, `test_anti_hallucination_gateway.py` ✅, `test_gateway_e2e.py` ✅ |
| **Status** | **Partial** — gateway + protected lists merged; many fields still LLM-authored |

---

## FM-02: Hidden mechanics leaking into narration

| Field | Detail |
|-------|--------|
| **Trigger** | Model puts `Roll:`, modifiers, or meta language inside `<narrative>`. |
| **Effect** | Immersion break; players see machinery. |
| **Detection** | `_validate_parsed` regexes; `detect_prose_contradictions`; frontend `MECHANIC_LINE_RE`; manual chronicle review. |
| **Prevention** | System prompt concealment rules; validation retry; `sanitizeParagraphs`. |
| **Recovery** | Retry once (format or hallucination); strip on render; dev fix prompt. |
| **Files** | `server.py`, `gateway.py`, `frontend/src/sanitize.ts` |
| **Tests** | `verify_p1_immersion_integrity.py` (P1-A) ✅, `verify_p15_microfixes.py` ✅ |
| **Status** | **Partial** — validator blocks many cases; not all live LLM outputs tested |

---

## FM-03: Hallucinated inventory or objects

| Field | Detail |
|-------|--------|
| **Trigger** | Model adds items to `ledger` or `inventory_objects` without prior presence. |
| **Effect** | Player gains unearned items. |
| **Detection** | Ledger vs `object_locations` mismatch; room audit drift flags; destruction registry. |
| **Prevention** | Object permanence guards; `update_destruction_registry`; canonical registry. |
| **Recovery** | `_apply_object_permanence`, `_apply_ledger_object_permanence`, gateway strip; manual edit **Unknown** (no admin edit route). |
| **Files** | `server.py`, `memory.py`, `gateway.py` |
| **Tests** | `verify_p0_object_permanence.py` ✅, `test_gateway_e2e.py` ✅ |
| **Status** | **Partial** — dedup/contradiction focus; novel item injection not fully blocked |

---

## FM-04: Destroyed objects reappearing

| Field | Detail |
|-------|--------|
| **Trigger** | Model re-lists destroyed/consumed items as carried. |
| **Effect** | Object permanence violation. |
| **Detection** | P0 scenarios; gateway strip; ledger cross-category check. |
| **Prevention** | Status priority in canonicalization; `strip_illegal_state_changes`; ledger dedup against `object_locations`. |
| **Recovery** | Guards remove duplicate carried rows. |
| **Files** | `server.py`, `memory.py`, `gateway.py` |
| **Tests** | `verify_p0_object_permanence.py` ✅, `test_gateway_e2e.py` ✅ |
| **Status** | **Protected** (deterministic scenarios + gateway e2e) |

---

## FM-05: Duplicate inventory entries

| Field | Detail |
|-------|--------|
| **Trigger** | Label drift creates multiple rows for same object. |
| **Effect** | Memory bloat; contradictory locations. |
| **Detection** | Row count on `object_locations` after N turns. |
| **Prevention** | `canonicalize_object_registry`. |
| **Recovery** | Merge on each turn. |
| **Files** | `memory.py` |
| **Tests** | P0 Scenario 2 (10 cycles) ✅ |
| **Status** | **Protected** (deterministic) |

---

## FM-06: Actor identity confusion

| Field | Detail |
|-------|--------|
| **Trigger** | NPC name variants treated as different actors. |
| **Effect** | Split memory, inconsistent relationships. |
| **Detection** | Manual review of `npc_memory` keys. |
| **Prevention** | **None dedicated** — no actor resolver in code (PRD Ch 25 planned). |
| **Recovery** | **Unknown** |
| **Files** | — |
| **Tests** | — |
| **Status** | **Unprotected** |

---

## FM-07: Relationship drift or LLM vector injection

| Field | Detail |
|-------|--------|
| **Trigger** | Model injects `relationship_vectors` or flips social dynamic without detected events. |
| **Effect** | Social state incoherence; wrong NPC behaviour. |
| **Detection** | `test_engine_owns_vectors_ignores_llm_injection`; dev panel `relationship_vectors` review. |
| **Prevention** | Engine reads prior `relationship_vectors` as authority; `update_relationship_calculus` recomputes from events + decay; protected merge key in `memory.py`. |
| **Recovery** | Deterministic revert on each turn; no NPC↔NPC edge repair. |
| **Files** | `relationships.py`, `memory.py`, `server.py` |
| **Tests** | `test_relationship_calculus.py` ✅ |
| **Status** | **Partial** — NPC→player only; regex event detection; `relationship_threads` not guarded |

---

## FM-08: Retrieval repetition (prompt)

| Field | Detail |
|-------|--------|
| **Trigger** | Same turns replayed; topic ledger exhausted but history repeats. |
| **Effect** | Looping dialogue; wasted tokens. |
| **Detection** | `topic_ledger`, `recent_choice_signatures` in rolling_state; player perception. |
| **Prevention** | Prompt anti-loop rules; `topic_ledger` authoritative pruning. |
| **Recovery** | Context trim drops old messages. |
| **Files** | `server.py` (prompt), `memory.py` |
| **Tests** | `qa_live_20turn_hostile.py` (not run) |
| **Status** | **Partial** |

---

## FM-09: Retrieval starvation (prompt)

| Field | Detail |
|-------|--------|
| **Trigger** | `enforce_context_budget` drops too much history. |
| **Effect** | Model forgets recent causality. |
| **Detection** | `debug` context_budget fields; continuity breaks in play. |
| **Prevention** | Protected recent messages; protected state item count in diagnostics. |
| **Recovery** | Increase budget env vars or reduce `memory_depth`. |
| **Files** | `memory.py`, `ai_config.py` |
| **Tests** | None dedicated |
| **Status** | **Partial** |

---

## FM-10: Prose contradicting immutable truth

| Field | Detail |
|-------|--------|
| **Trigger** | Model narrates using destroyed objects, deceased NPCs, or illegal state despite truth block. |
| **Effect** | Player sees impossible actions; immersion break. |
| **Detection** | `detect_prose_contradictions` in `_full_validate`. |
| **Prevention** | `build_immutable_truth_block` in prompt; single retry with hallucination hint. |
| **Recovery** | Retry turn; if still failing, HTTP 502. |
| **Files** | `gateway.py`, `server.py` |
| **Tests** | `test_anti_hallucination_gateway.py` ✅ |
| **Status** | **Partial** — retry once; regex/heuristic detection only |

---

## FM-11: HUD steering player toward objectives

| Field | Detail |
|-------|--------|
| **Trigger** | Model emits Objective/Goal chips or prescriptive Pressure text. |
| **Effect** | Quest-marker UX; reduces emergent play. |
| **Detection** | `hud._PRESCRIPTIVE_RE`; frontend chip inspection. |
| **Prevention** | `shape_hud` strips Objective/Goal; `derive_pressure` rejects prescriptive phrases. |
| **Recovery** | Engine overwrites DNG/MOM; replaces or drops PRS. |
| **Files** | `hud.py`, `frontend/app/play/[id].tsx` |
| **Tests** | `test_hud.py` ✅ |
| **Status** | **Protected** (deterministic unit tests) |

---

## FM-12: Event sequence or ordering drift

| Field | Detail |
|-------|--------|
| **Trigger** | Turns fetched out of order; concurrent `story_action` writes (mitigated for `story_action` only as of v1). |
| **Effect** | Wrong chronicle display; duplicate turn numbers (mitigated when unique index present). |
| **Detection** | `sort("turn_number", 1)` on queries; HTTP **409** on lease conflict. |
| **Prevention** | Mongo-backed action lease before provider work; `next_turn_number` from locked session; final CAS on lease token + `turn_count`; optional unique `(session_id, turn_number)` index. |
| **Recovery** | Re-fetch session; stale lease expires (default 600s) and may be reclaimed; rejected concurrent action makes zero provider calls. |
| **Files** | `action_concurrency.py`, `server.py` |
| **Tests** | `test_action_concurrency.py` ✅ |
| **Status** | **Partial** — `story_action` protected; reset/delete/mode unguarded |

---

## FM-12b: Concurrent story_action overlap

| Field | Detail |
|-------|--------|
| **Trigger** | Duplicate tab submit, network retry, or second worker while an action is in flight. |
| **Effect** | Without guard: duplicate turns, clobbered rolling state, double secret reveals, wasted provider spend. |
| **Detection** | Lease acquire miss → HTTP **409** `An action is already in progress for this chronicle`. |
| **Prevention** | Atomic lease acquire before reveal/provider; token-scoped release; CAS before session commit. |
| **Recovery** | Client retries after first action completes; expired lease auto-recovers. |
| **Files** | `action_concurrency.py`, `server.py` (`story_action`) |
| **Tests** | `test_action_concurrency.py` ✅ |
| **Status** | **Protected** for `POST /story/action` only (deterministic tests) |

---

## FM-13: Invalid model fallback

| Field | Detail |
|-------|--------|
| **Trigger** | Primary model 404/429/402; all fallbacks fail. |
| **Effect** | 502 to client; turn not created. |
| **Detection** | `AIServiceError`; `fallback_events` in meta; `friendlyError` on client. |
| **Prevention** | Fallback chain via `gateway.invoke_llm`; retries with backoff. |
| **Recovery** | User switches model in Settings; add credits. |
| **Files** | `ai_service.py`, `gateway.py`, `frontend/src/errors.ts` |
| **Tests** | PRD P1 deliberate fallback drill (not run) |
| **Status** | **Partial** |

---

## FM-14: Developer data exposure

| Field | Detail |
|-------|--------|
| **Trigger** | Attacker obtains session UUID or guesses IDs; operator misconfigures admin key. |
| **Effect** | Raw state exposure via admin routes only; player routes remain sanitised. |
| **Detection** | API response inspection; `test_security.py` player-route cases. |
| **Prevention** | All player routes use `player_api` allowlists; `/export/raw` and diagnostics require admin key only; admin routes require `X-Admin-Api-Key`. |
| **Recovery** | Rotate `ADMIN_API_KEY`; restrict network; use operator curl only for diagnostics. |
| **Files** | `server.py`, `security.py` |
| **Tests** | `test_security.py` cases 16–25 ✅ |
| **Status** | **Protected** on player routes; admin raw export gated |

---

## FM-15: Admin endpoints lacking real authentication

| Field | Detail |
|-------|--------|
| **Trigger** | Client calls `/api/admin/*` without valid `X-Admin-Api-Key`. |
| **Effect** | Request rejected — no settings change. |
| **Detection** | HTTP 401/503 responses. |
| **Prevention** | `security.require_admin` — constant-time key compare; fails closed when `ADMIN_API_KEY` unset. |
| **Recovery** | Configure `ADMIN_API_KEY`; restore settings via authenticated admin call or MongoDB. |
| **Files** | `security.py`, `server.py` admin routes |
| **Tests** | `test_security.py` cases 11–15 ✅ |
| **Status** | **Protected** (server-side); client UI admin panel non-functional without operator proxy |

---

## FM-16: Session hijack via leaked `session_id`

| Field | Detail |
|-------|--------|
| **Trigger** | Attacker obtains session UUID but not owner `device_id`. |
| **Effect** | **404** identical to unknown session — no chronicle data, no ownership hint. |
| **Detection** | `test_security.py` enumeration case (wrong device vs missing session). |
| **Prevention** | `fetch_owned_session` on all protected routes; `X-Device-Id` header (not URL). |
| **Recovery** | Attacker with both `session_id` and `device_id` still has access — device isolation only. |
| **Files** | `security.py`, `server.py` |
| **Tests** | `test_security.py` cases 2–7, 10 ✅ |
| **Status** | **Protected** (device-scoped, anti-enumeration); not full account security |

---

## FM-20: Paid story-creation abuse

| Field | Detail |
|-------|--------|
| **Trigger** | Automated or scripted `POST /story/new` spam; device UUID rotation. |
| **Effect** | OpenRouter cost exhaustion; MongoDB session bloat. |
| **Detection** | 429 rate on creation; `rate_limits` collection growth; ops monitoring. |
| **Prevention** | MongoDB-backed per-IP, per-device, and concurrent limits before LLM/insert; generic 429; fail closed on limiter errors. `TRUSTED_PROXY_COUNT` for accurate IP behind proxy. |
| **Recovery** | Tune env limits; block abusive IPs at edge; prune old `rate_limits` buckets (auto-pruned on check). |
| **Files** | `rate_limit.py`, `server.py` |
| **Tests** | `test_rate_limit.py` ✅ |
| **Status** | **Protected** (deterministic); not a substitute for full user auth |

---

## FM-17: Configuration values differing (code vs DB vs env)

| Field | Detail |
|-------|--------|
| **Trigger** | `admin_settings` overrides env; PRD documents deployment-specific values. |
| **Effect** | Docs/ops mismatch; debugging confusion. |
| **Detection** | Compare `/api/health` vs `ai_config.py` defaults. |
| **Prevention** | Document source-of-truth order: DB > env > code defaults. |
| **Recovery** | `GET /admin/settings`; reset DB document. |
| **Files** | `server.py` `get_ai_settings`, `ai_config.py` |
| **Tests** | None |
| **Status** | **Partial** — health endpoint exposes effective settings |

---

## FM-18: Export/reset schema mismatch

| Field | Detail |
|-------|--------|
| **Trigger** | Client expects different export shape; reset without re-seed. |
| **Effect** | Broken share UX; empty chronicle after reset. |
| **Detection** | Contract tests **missing**. |
| **Prevention** | Documented schema in `api.md`. |
| **Recovery** | `new_story` or first `story_action` after reset. |
| **Files** | `server.py`, `frontend/app/play/[id].tsx` |
| **Tests** | None |
| **Status** | **Partial** — code documented; no automated contract test |

---

## FM-21: Slow or atmospheric early-game openings

| Field | Detail |
|-------|--------|
| **Trigger** | LLM emits setup-heavy Turn 1 prose despite genesis contract; Stages 2–4 guidance ignored. |
| **Effect** | Player spends several turns in low-yield exploration before encountering a concrete situation. |
| **Detection** | Live play review; optional qualitative opening probe (provider-dependent). |
| **Prevention** | Stage 1 genesis directive + structural field-presence validation (`pacing.validate_opening_structure`); strengthened `_create_new_story` opening contract; Stages 2–4 non-persisted continuity guidance. |
| **Recovery** | Single pacing retry on Stage 1 structural failure; player action still resolves normally on later turns. |
| **Files** | `pacing.py`, `server.py` |
| **Tests** | `test_early_game_pacing.py` ✅ (directive routing, validation, retry budget, leak safety) |
| **Status** | **Partial** — deterministic field-presence enforced on Stage 1 only; semantic pacing quality not deterministically proven; no autonomous heartbeat |

---

## FM-23: Onboarding secret leaked before player confession

| Field | Detail |
|-------|--------|
| **Trigger** | Secret text or `secret_registry` reaches LLM `<prior_state>`, player API, or exports before deliberate reveal. |
| **Effect** | Spoiler; immersion break; trust loss. |
| **Detection** | `test_onboarding_hooks.py`, `test_secret_reveal.py`, player export audits. |
| **Prevention** | `_prompt_safe_rolling` strips registry; `player_api` blocks `secret_registry`; reveal only via `secrets.prepare_turn_reveal` on explicit confession; model registry mutations stripped post-consolidation. |
| **Recovery** | N/A for leaked sessions — prevention-only; admin raw export for operators. |
| **Files** | `backend/secrets.py`, `backend/server.py`, `backend/player_api.py` |
| **Tests** | `test_onboarding_hooks.py` ✅, `test_secret_reveal.py` ✅ |
| **Status** | **Protected** (deterministic v1 — explicit confession only) |

---

## FM-22: Pacing directive leak into player-visible persistence

| Field | Detail |
|-------|--------|
| **Trigger** | Internal pacing system message mistakenly stored in turn/session/export payloads. |
| **Effect** | Engine instructions visible in chronicle, exports, or API responses. |
| **Detection** | `test_early_game_pacing.py` persistence/export assertions. |
| **Prevention** | Directive injected only as ephemeral system message in `_build_messages`; never appended to `player_action` or rolling state. |
| **Recovery** | N/A — prevented by construction. |
| **Files** | `pacing.py`, `server.py` |
| **Tests** | `test_early_game_pacing.py` ✅ |
| **Status** | **Protected** (deterministic leak tests) |

---

## FM-25: Replayability state unbounded growth

**Scope:** `recovery/living-cast-working-tree` only — Living Cast modules are **not on `emergent` HEAD**; unmerged, not deployed.

| Field | Detail |
|-------|--------|
| **Trigger** | Agendas, receipts, echoes, or beat history append without cap enforcement; echo references pin full move receipts indefinitely. |
| **Effect** | Session document grows without bound; Mongo payload bloat; nondeterministic eviction. |
| **Detection** | `living_cast_state_metrics`; `test_living_cast_bounded_state.py`; `REPLAYABILITY_STATE_BUDGET_BYTES` assertion. |
| **Prevention** | Documented hard caps on every slice; `enforce_npc_move_receipt_cap` (compress then drop); echo `source_provenance` copied at schedule (receipts not pinned); relationship threshold receipts separate from move bundles. |
| **Recovery** | Cap functions are deterministic and idempotent; reset clears `replayability_state`. |
| **Files** | `living_cast_bounded_fixtures.py`, `npc_world_moves.py`, `consequence_echoes.py`, `replayability.py`, `arc_diversity.py`, `npc_agendas.py` |
| **Tests** | `test_living_cast_bounded_state.py` ✅ |
| **Status** | **Protected** (deterministic, measured at cap) |

---

## FM-24: NPC agenda or world-move leak

**Scope:** `recovery/living-cast-working-tree` only — provisional integrated local substitute; **not covered by emergent CI**.

| Field | Detail |
|-------|--------|
| **Trigger** | LLM emits `npc_agendas`, `arc_diversity`, `npc_move_receipts`, or `[NPC_WORLD_MOVE_V1]` into player-visible fields; model rewrites selected move or agenda progress. |
| **Effect** | Hidden simulation exposed; player sees engine terminology; contradictory independent NPC actions. |
| **Detection** | `enforce_authoritative` + `strip_model_agenda_mutations`; `_scrub_meta_from_text` marker rejection; player serializer excludes `replayability_state`; prompt `_prompt_safe_rolling` hides injected receipt/event keys. |
| **Prevention** | Agendas/receipts on session document only; move computed once pre-provider and frozen on retry; explicit targets required; no move when infeasible; directive uses template IDs not receipt internals. |
| **Recovery** | Strip illegal rolling keys; restore authoritative `replayability_state`; rollback turn on CAS failure (no move persist). |
| **Files** | `npc_agendas.py`, `npc_world_moves.py`, `replayability.py`, `server.py` |
| **Tests** | `test_npc_world_moves.py`, `test_living_cast_integration.py` ✅ |
| **Status** | **Protected** (deterministic) |

---

## FM-20: Replayability state drift or leak

| Field | Detail |
|-------|--------|
| **Trigger** | LLM emits `replayability_*` / `pressure_graph` keys in `rolling_state`; treating player text as echo source; duplicate `engine_events` history; legacy session mixed with new code paths. |
| **Effect** | Engine truth in wrong layer; false echoes; player export or prompt pollution; inconsistent run identity across turns. |
| **Detection** | `replayability.enforce_authoritative` + `strip_model_pressure_mutations`; player serializer excludes `replayability_state`; integration tests reject keyword echo sources. |
| **Prevention** | Store replayability only on session document; echoes from `collect_qualifying_echo_sources` after guards only; `transition_receipts` idempotency (not event history); Policy A skip; strip rolling keys post-consolidation; `reset_session` clears field. |
| **Recovery** | Guards strip illegal rolling keys; rollback restores `replayability_state` snapshot; session reset. |
| **Files** | `replayability.py`, `server.py`, `player_api.py` |
| **Tests** | `test_replayability_integration.py` ✅ |
| **Status** | **Protected** (deterministic) |

---

## FM-19: Stale documentation treated as runtime truth

| Field | Detail |
|-------|--------|
| **Trigger** | Stale docs, old PR descriptions, agent summaries, chat handoffs, or unmerged feature branches are treated as canonical after runtime has moved. |
| **Effect** | False feature status, unsafe activation decisions, or proposal behaviour reported as shipped. |
| **Detection** | Compare the claim to runtime code and passing tests on canonical `emergent`, then to the operational documentation hierarchy. |
| **Prevention** | Enforce this order: runtime code/tests on `emergent` → `current-state.md` → `system-doctrine.md` → this catalogue → `feature-status.md` → decision log/accepted ADRs → verification evidence → agent/chat summaries. Feature branches are proposals until merged. |
| **Recovery** | Reconcile operational docs from updated `emergent`; downgrade unsupported agent or PR claims. |
| **Files** | `memory/PRD.md`, `/docs/*` |
| **Tests** | `release-checklist.md` |
| **Status** | **Protected procedurally** — requires discipline on every publication/reconciliation pass |

---

## FM-26: Actor stress ownership, identity, or scope drift

| Field | Detail |
|-------|--------|
| **Trigger** | Model output overwrites `actor_stress`; nondeterministic inputs alter stress; snapshot identity omits present authoritative stress; or P1 silently widens beyond living actors with active agendas. |
| **Effect** | Replay divergence, untrustworthy Utility AI inputs, incorrect recovery/generation, or behaviour outside the accepted P1 scope. |
| **Detection** | Stress unit/determinism tests, turn-path integration, clobber-protection test, and snapshot hash comparison. |
| **Prevention** | Deterministic seeded capacity and update order; persisted `rolling_state["actor_stress"]`; `enforce_authoritative_stress` after consolidation; commit present stress into foundation snapshot identity; agenda-bearing living-actor predicate. |
| **Recovery** | Restore engine-owned persisted stress, rerun focused P1 and hash evidence, and handle any scope widening through a separate design decision. |
| **Files** | `stress.py`, `foundation_snapshot.py`, `replayability.py`, `server.py` |
| **Tests** | `test_stress.py`, `test_stress_integration.py`, foundation acceptance and determinism suites ✅ |
| **Status** | **Protected — P1 `TURN_INTEGRATION_VERIFIED`; widening deferred** |

---

## FM-27: Invalid authoritative stress mis-banded or awarded a bonus (P2)

**Scope:** `codex/ch14-stress-behaviour` (P2) only — unmerged draft PR; shadow-only.

| Field | Detail |
|-------|--------|
| **Trigger** | Authoritative `stress_level` is missing, wrong-type, NaN/inf, negative, or > 100 when the P2 band layer reads it. |
| **Effect** | Without fail-closing: corrupt stress treated as CALM, or a high band fabricated, silently authorising a replacement or producing a maximum/emergency weighting. |
| **Detection** | `stress.evaluate_stress_behaviour` validity + blocker code; `select_action` `stress_input_valid`/`stress_blocker_code` in shadow `score_table`; `test_stress_behaviour.py`. |
| **Prevention** | Fail-closed pure layer: no band, identity (x1.0) modifiers, distinct blocker code (MISSING/INVALID/NONFINITE/OUT_OF_RANGE_STRESS_LEVEL); `replacement_authorised` forced False; band derived from the authoritative snapshot input, not the coerced candidate field. |
| **Recovery** | Candidate remains visible in shadow diagnostics but cannot be an authorised replacement; selection unchanged (identity weights). |
| **Files** | `stress.py`, `utility_ai.py` |
| **Tests** | `test_stress_behaviour.py` (66 passed) |
| **Status** | **Protected (proposed/unmerged)** — deterministic fail-closed unit + integration tests |

---

## Removed from catalogue (N/A)

Historical pre-foundation scoring equivalence remains **N/A** because that implementation never existed. Foundation Utility AI scoring now exists in shadow mode; determinism and non-finite-input protection are covered by its focused tests and must be revisited before any live/load-bearing activation.
