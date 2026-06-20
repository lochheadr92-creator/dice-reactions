# Story Engine

The story engine lives primarily in `backend/server.py` with supporting modules `gateway.py`, `relationships.py`, `hud.py`, `memory.py`, `ai_service.py`, `ai_config.py`, `scenarios.py`, `pacing.py`, `secrets.py`, and `replayability.py` (+ `run_identity.py`, `opening_state.py`, `pressure_graph.py`, `consequence_echoes.py`).

**Branch:** `emergent` HEAD @ `d8b9caf` — gateway, relationship calculus, HUD, and replayability modules are runtime truth here; absent on `main`. Living Cast modules (`npc_agendas.py`, `npc_world_moves.py`, `arc_diversity.py`) exist only on unmerged `recovery/living-cast-working-tree` — see [Recovery branch appendix](#recovery-branch-appendix-living-cast-provisional).

## Turn output format

Each LLM response must contain tagged blocks:

| Tag | Required | Purpose |
|-----|----------|---------|
| `<narrative>` | yes | 2–4 short paragraphs (~1200 chars total) |
| `<choices>` | yes | 4–6 lines labelled A.–F. |
| `<state>` | yes | Key-value player-visible state chips (shaped to DNG/MOM/PRS by `hud.py`) |
| `<ledger>` | yes | Consequence / delayed-trigger ledger |
| `<rolling_state>` | yes | Full simulation state JSON |
| `<debug>` | only when `[DEV_MODE: ON]` | Internal roll/mechanic readouts |

`parse_turn()` in `server.py` extracts these blocks into a `ParsedTurn` model.

## LLM invocation (approved path)

All provider calls route through **`gateway.invoke_llm`** — the sole chokepoint (Ch 31.11). `_generate_turn` and validation retries must not call `ai_service` directly.

Before each call, `_build_messages` may prepend internal system directives (non-persisted), in order:

1. Early-game pacing (`pacing.build_early_game_directive`)
2. Replayability opening (`opening_state` — turn 1 only, when `replayability_state` present)
3. Secret reveal continuity (`secrets.build_revealed_secret_directive`)
4. Replayability pressure foreground (`pressure_graph.build_pressure_directive`)
5. Replayability consequence echo (`consequence_echoes.build_echo_directive`)

On `recovery/living-cast-working-tree` only, directive 4 may be `arc_diversity.build_world_development_directive` (with `[NPC_WORLD_MOVE_V1]`), shifting pressure/echo omission rules — not on `emergent` HEAD.

Then replay/history and, in the final user message:
- `gateway.build_immutable_truth_block(rolling)` — established object/injury/death facts
- `relationships.build_relationship_block(rolling)` — engine-owned NPC→player feelings (for prompt only)
- `<prior_state>` JSON block

**Policy A:** Sessions without `replayability_state` skip replayability directives (legacy chronicles).

## Simulation modes

| Mode | Choice range | Token cap |
|------|--------------|-----------|
| `basic` | 3–4 | 1100 max_tokens cap |
| `advanced` | 4–6 | no cap beyond global `max_tokens` |

Mode is set at story creation and can be changed via `POST /story/session/{id}/mode`.

## Difficulty

Player messages include `[DIFFICULTY: <level>]` markers. Levels: `soft`, `standard`, `hard`, `brutal`. The system prompt defines hidden D20 modifiers per level. These modifiers are never exposed in player-facing prose.

## System prompt governance

`STORY_ENGINE_SYSTEM_PROMPT` (v3.6 in comments) enforces:

- Absolute internal concealment of rolls, modifiers, triggers, subsystem labels
- Hard output validation rules (paragraph/choice counts, no mechanic lines in narrative)
- Difficulty enforcement (internal only)
- Runtime governance: anti-loop, forward pressure, topic ledger, choice freshness
- Narrative immersion rules (no tutorial/system exposition)
- NPC realism, world momentum, failure doctrine

## Validation and retry

`_full_validate()` runs:

1. `_validate_parsed()` — paragraph count (2–4), narrative length (≤1200 chars), choice bounds, required labels A–D, mechanic leak patterns (`_LEAK_LABEL_RE`), direct inspection violations
2. `gateway.detect_prose_contradictions()` — prose vs immutable truth (destroyed objects, deceased NPCs, etc.)

On failure, `_generate_validated_turn()` retries once with a format or hallucination correction hint. Persistent failure raises HTTP error.

## Anti-Hallucination Gateway (post-parse, `gateway.py`)

| Step | Function | When |
|------|----------|------|
| STRIP | `strip_illegal_state_changes` | After state supremacy + object permanence, before consolidation (action turns) |
| REGISTRY | `update_death_registry` | After rolling hygiene, before persist |
| REGISTRY | `update_destruction_registry` | After rolling hygiene, before persist |
| DETECT | `detect_prose_contradictions` | During `_full_validate` before accept |

`build_immutable_truth_block` runs at prompt build (PREVENT).

## Deterministic guards (post-parse)

These run after parsing and before persistence. Order on **`story_action`** matters:

1. `_apply_state_supremacy` — Health/Fatigue cannot improve without cause
2. `_apply_object_permanence` — inventory vs locations
3. `gateway.strip_illegal_state_changes` — revert illegal mutations vs prior truth
4. `consolidate_rolling_state` — protected-key union merge
5. `_apply_ledger_object_permanence` — cross-category dedup
6. `_apply_room_audit` — known_rooms reconciliation
7. `_apply_npc_memory_bounds` — cap NPC memory
8. `_apply_faction_consequence_tick` — local faction pressure
9. `_apply_delayed_consequence_tick` / `_apply_rumour_propagation_tick`
10. `_apply_rolling_state_hygiene` — meta scrub
11. `gateway.update_death_registry`
12. `gateway.update_destruction_registry`
13. `relationships.update_relationship_calculus` — NPC→player vectors
14. `hud.shape_hud` — DNG/MOM/PRS; strip Objective
15. `replayability.enforce_authoritative` — strip model replayability keys from `rolling_state` (when session has `replayability_state`)

Turn 1 (`new_story`) skips state supremacy and gateway STRIP (no prior rolling state) but runs the remainder.

## Replayability Engine v1 (`replayability.py`)

**Storage:** `sessions.replayability_state` — **not** in `rolling_state`. Player serializers exclude the field.

| Submodule | Role |
|-----------|------|
| `run_identity.py` | Narrative + causal closed enums; `has_secret` bool; difficulty → `severity_multiplier` only |
| `opening_state.py` | 14 archetypes with structured facts (`immediate_problem`, `pressure_origins`, `fact_ids`); turn-1 directive |
| `pressure_graph.py` | Causal nodes (`magnitude`, `trend`, `kind`, links); trend-only movement; foreground scoring; `threshold_crossings` |
| `consequence_echoes.py` | Schedule from confirmed source events (`source_event_id`); mature; fire max 1/turn |

**Canonical transitions:** `rolling_state` structures (delayed consequences, relationship vectors, faction ticks, destruction registry) plus `pressure_graph.threshold_crossings`. Replayability stores `transition_receipts` (idempotency only) — **LOCAL SUBSTITUTE** bounded receipts on the recovery branch are not canonical event sourcing; full event sourcing remains **DEFERRED** (PRD Ch 22 summary only).

**Pressure authority (unresolved on `emergent` HEAD):** `replayability_state.pressure_graph` and `rolling_state.active_pressures` both exist — duplicate authority; golden-path blocker.

**Echo sources (v1 on `emergent` HEAD):** pressure threshold crossed; delayed consequence fired; relationship threshold (`betrayal_risk`/`collapsed`); faction hostility tick; destruction confirmed; opening unresolved tension. Raw player text, narrative, and choices are **never** parsed.

**Turn flow (`emergent` HEAD):**

- `_create_new_story`: `init_new_story` → persist `replayability_state` → frozen directives → enforce after consolidation
- `story_action`: `prepare_action_turn` **before** provider (tick pressure, mature/fire echo, frozen directives on retry) → guards → `collect_qualifying_echo_sources` → `finalize_action_turn` → persist
- `reset_session`: clears `replayability_state` with turns and rolling state

### State supremacy (`_apply_state_supremacy`)

Prevents Health and Fatigue from improving turn-over-turn without a justified cause tracked in prior state.

### Object permanence (`_apply_object_permanence`, `_apply_ledger_object_permanence`)

Reduces contradictions between carried, hidden, dropped, consumed, and destroyed items. Seeds `object_locations` independently from `inventory_objects`.

### Room audit (`_apply_room_audit`)

Maintains `known_rooms` for revisit reconciliation.

### NPC memory bounds (`_apply_npc_memory_bounds`)

Caps and prunes NPC memory entries to prevent unbounded growth.

### Faction consequence tick (`_apply_faction_consequence_tick`)

Advances faction pressure based on ledger events.

### Rolling state hygiene (`_apply_rolling_state_hygiene`)

Scrubs meta-language from rolling state text fields.

## Relationship calculus (`relationships.py`)

**Directionality:** NPC → player only. Each NPC has a vector toward the player:

| Dimension | Range | Meaning |
|-----------|-------|---------|
| trust | −100..+100 | Predictability / non-harm |
| loyalty | 0..100 | Commitment / sacrifice |
| fear | 0..100 | Yielding to avoid harm |
| resentment | 0..100 | Desire to hurt player |

**Storage:** `rolling_state['relationship_vectors']` — protected list key in `memory.py`.

**Authority:** Prior turn vectors are authoritative; LLM-injected vector values are ignored on merge (`test_engine_owns_vectors_ignores_llm_injection`).

**Per turn:** neglect decay toward neutral; regex-detected events apply `EVENT_DELTAS`; derived `state` (`neutral`, `trusting`, `hostile`, etc.); optional stance sync on `npcs` rows.

**Limits (current):**
- No NPC↔NPC relationship edges
- No actor resolution — candidate names from `npcs`, `npc_memory`, `relationship_threads`
- Event detection is regex + co-occurrence window, not semantic parsing
- `relationship_threads` still seeded in Custom World but not used for vector mechanics
- Deceased NPCs (in `deceased` registry) excluded from vector updates

**Prompt:** `build_relationship_block` — up to 12 NPC summaries with behavioural guidance; numbers visible to model only, not player UI.

## HUD shaping (`hud.py`)

Player-facing status after guards:

| Presentation | State key | Values |
|--------------|-----------|--------|
| **DNG** (Danger) | `Danger` | `none`, `low`, `elevated`, `high`, `critical` |
| **MOM** (Momentum) | `Momentum` | `surging`, `steady`, `stalling`, `declining`, `lost` |
| **PRS** (Pressure) | `Pressure` | Single phrase ≤64 chars; non-prescriptive |

`shape_hud`:
- Removes `Objective`, `objective`, `Goal`, `Goals`
- Derives Danger from health/stress/threats if LLM value invalid
- Defaults Momentum to `steady` if invalid
- `derive_pressure`: survival flags win; then LLM phrase if non-prescriptive; then engine fallbacks

Frontend `play/[id].tsx` renders chips labelled DNG, MOM, PRS.

## Rolling memory (`memory.py`)

### Protected list keys (never silently dropped)

Union-merged from prior turn if the model omits unresolved entries:

`active_consequences`, `delayed_consequences`, `latent_triggers`, `unresolved_threats`, `active_threats`, `unresolved`, `injuries`, `inventory_objects`, `object_locations`, `route_continuity`, `npc_memory`, `relationship_threads`, `relationship_vectors`, `faction_pressure`, `world_instability`, `simulation_hooks`, `promises`, `clues`, `known_rooms`

### Authoritative list keys (model prunes intentionally)

`topic_ledger`, `recent_choice_signatures`, `active_pressures`, `recent_beats`, `archived`

### Object canonicalization (`canonicalize_object_registry`)

Collapses `object_locations` and `inventory_objects` to one row per normalized object identity. Status priority: destroyed > consumed > dropped > hidden > stored > worn > carried.

### Compression metrics (`compute_compression_metrics`)

Diagnostics only: `raw_turns_kept`, `compressed_turns_count`, `estimated_context_savings_*`.

## Context budget governor

Before each LLM call, `enforce_context_budget()`:

1. Compresses `<prior_state>` JSON in the final user message
2. Strips engine blocks from older assistant messages (keeps narrative)
3. Drops oldest trimmable messages if still over budget

Protected: system message, final user message, last `memory_depth * 2` replay messages, all protected rolling-state items.

Budget resolved by `resolve_context_budget(cost_mode, mode)`:

| Condition | Budget tokens |
|-----------|---------------|
| `cost_mode=low` | 7000 |
| `mode=advanced` | 16000 |
| otherwise | 12000 |

**Not present:** gravity-based retention governance beyond this budget trim.

## Custom World seeding

When `custom_world_setup` is provided (no `scenario_id`), `_seed_custom_setup_into_rolling()` injects answers into:

- `simulation_hooks`
- `world_instability`
- `story_focus`
- `relationship_threads`
- `inventory_objects`
- `object_locations`

Setup block is also embedded in the opening prompt via `_build_custom_world_setup_block()`. Relationship **vectors** are initialized on turn 1 by `update_relationship_calculus`, not from setup answers directly.

## Curated scenarios

`scenarios.py` defines three presets with full seed paragraphs passed to the engine on turn 1. The public API omits `seed` from list responses.

## AI routing per session

At `POST /story/new`, the session snapshots:

- `active_model` from current admin settings
- `fallback_chain` from settings or env defaults
- `cost_mode`

Model switches during fallback are recorded in `model_switches` and trigger `[FALLBACK_ACTIVE: ...]` hints on subsequent turns. All calls go through `gateway.invoke_llm`.

## Player vs developer payloads

When `developer_mode` is false (default in code):

- API strips `rolling_state`, `debug`, `raw` from turns
- Internal state keys (latent, delayed trigger, active systems, etc.) removed from `state`
- Session `rolling_state` omitted

Frontend `sanitize.ts` adds a presentation-only filter on paragraphs and choices regardless of API sanitization.

## Planned / not present on `emergent` HEAD

| System | Status |
|--------|--------|
| Utility AI | Planned (PRD Ch 27 summary only) — not on `emergent` HEAD; recovery has **local substitute** in `npc_world_moves.py` (unmerged) |
| Actor resolution | Planned (PRD Ch 25 summary only) — not on `emergent` HEAD; recovery has **local substitute** tier policy (unmerged) |
| Formal event sourcing | **DEFERRED** — full contract unavailable beyond PRD summary; turn log only on `emergent` HEAD |
| Living Cast | **Provisional integrated local substitute** on `recovery/living-cast-working-tree` only — unmerged, not deployed |
| Scoring / NaN ranking guards | N/A — never existed in this repo |

---

## Recovery branch appendix (Living Cast — provisional)

**Branch:** `recovery/living-cast-working-tree` @ `4dadb3f` — **unmerged**, **not deployed**, **not covered by emergent CI**, **not merge-ready**.

Living Cast adds `npc_agendas.py`, `npc_world_moves.py`, `arc_diversity.py` orchestrated in `replayability.prepare_action_turn` with world execution mode `TURN_COUPLED_AUTONOMY_ONLY`. Actor Resolution and Utility AI are **local substitutes** — not full PRD Ch 25/27 modules (Bible full text ends at Chapter 21; Chapters 22–32 are PRD tracker summaries only).

Bounded `npc_move_receipts` and `transition_receipts` are **LOCAL SUBSTITUTE** — they provide idempotency and causal pointers but do not provide canonical reconstruction or durable complete event history.

**Blockers before merge:** pressure authority unresolved; relationship provenance unresolved (vectors mutated from player intent + generated prose); golden-path blockers remain. Feature development remains frozen.