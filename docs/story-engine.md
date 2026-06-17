# Story Engine

The story engine lives primarily in `backend/server.py` with supporting modules `memory.py`, `ai_service.py`, `ai_config.py`, and `scenarios.py`.

## Turn output format

Each LLM response must contain tagged blocks:

| Tag | Required | Purpose |
|-----|----------|---------|
| `<narrative>` | yes | 2–4 short paragraphs (~1200 chars total) |
| `<choices>` | yes | 4–6 lines labelled A.–F. |
| `<state>` | yes | Key-value player-visible state chips |
| `<ledger>` | yes | Consequence / delayed-trigger ledger |
| `<rolling_state>` | yes | Full simulation state JSON |
| `<debug>` | only when `[DEV_MODE: ON]` | Internal roll/mechanic readouts |

`parse_turn()` in `server.py` extracts these blocks into a `ParsedTurn` model.

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

`_validate_parsed()` checks:

- Paragraph count (2–4) and total narrative length (≤1200 chars)
- Choice count within mode profile bounds
- Required choice labels A–D present
- No mechanic leak patterns in narrative (`_LEAK_LABEL_RE`)
- Direct inspection violations (player asked to see hidden state)

On failure, `_generate_validated_turn()` retries once with a correction hint. Persistent failure raises HTTP error.

## Deterministic guards (post-parse)

These run after parsing and before persistence. They correct LLM drift without exposing mechanics to the player.

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

## Rolling memory (`memory.py`)

### Protected list keys (never silently dropped)

Union-merged from prior turn if the model omits unresolved entries:

`active_consequences`, `delayed_consequences`, `latent_triggers`, `unresolved_threats`, `active_threats`, `unresolved`, `injuries`, `inventory_objects`, `object_locations`, `route_continuity`, `npc_memory`, `relationship_threads`, `faction_pressure`, `world_instability`, `simulation_hooks`, `promises`, `clues`, `known_rooms`

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

## Custom World seeding

When `custom_world_setup` is provided (no `scenario_id`), `_seed_custom_setup_into_rolling()` injects answers into:

- `simulation_hooks`
- `world_instability`
- `story_focus`
- `relationship_threads`
- `inventory_objects`
- `object_locations`

Setup block is also embedded in the opening prompt via `_build_custom_world_setup_block()`.

## Curated scenarios

`scenarios.py` defines three presets with full seed paragraphs passed to the engine on turn 1. The public API omits `seed` from list responses.

## AI routing per session

At `POST /story/new`, the session snapshots:

- `active_model` from current admin settings
- `fallback_chain` from settings or env defaults
- `cost_mode`

Model switches during fallback are recorded in `model_switches` and trigger `[FALLBACK_ACTIVE: ...]` hints on subsequent turns.

## Player vs developer payloads

When `developer_mode` is false (default in code):

- API strips `rolling_state`, `debug`, `raw` from turns
- Internal state keys (latent, delayed trigger, active systems, etc.) removed from `state`
- Session `rolling_state` omitted

Frontend `sanitize.ts` adds a presentation-only filter on paragraphs and choices regardless of API sanitization.