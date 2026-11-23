# Story Engine

The story engine lives primarily in `backend/server.py` with supporting modules `gateway.py`, `relationships.py`, `hud.py`, `memory.py`, `ai_service.py`, `ai_config.py`, `scenarios.py`, `pacing.py`, `secrets.py`, and `replayability.py` (+ `run_identity.py`, `opening_state.py`, `pressure_graph.py`, `consequence_echoes.py`).

**Branch:** `emergent` HEAD @ `d8b9caf` — gateway, relationship calculus, HUD, and replayability modules are runtime truth here; absent on `main`. Living Cast modules (`npc_agendas.py`, `npc_world_moves.py`, `arc_diversity.py`) exist only on unmerged `recovery/living-cast-working-tree` — see [Recovery branch appendix](#recovery-branch-appendix-living-cast-provisional).

## Turn output format

Each LLM response must contain tagged blocks:

| Tag | Required | Purpose |
|-----|----------|---------|
| `<narrative>` | yes | Paragraph count set by the story's turn length: brief 1 to 2, standard 2 to 4, story 4 to 6, cinematic 6 to 8 (`prose_modes.py`) |
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
- Output validation rules (choice counts, no mechanic lines in narrative). Paragraph count and length are handled at delivery, see below
- Difficulty enforcement (internal only)
- Runtime governance: anti-loop, forward pressure, topic ledger, choice freshness
- Narrative immersion rules (no tutorial/system exposition)
- NPC realism, world momentum, failure doctrine

## Validation and retry

`_full_validate()` runs:

1. `_validate_parsed()` — non-empty narrative, choice bounds, required labels A–D, mechanic leak patterns (`_LEAK_LABEL_RE`), direct inspection violations. Over-long prose is trimmed locally to the mode's character budget. Paragraph count is not a reason to reject or retry a turn
2. `gateway.detect_prose_contradictions()` — prose vs immutable truth (destroyed objects, deceased NPCs, etc.)

When `_full_validate()` passes, `_echo_validate()` runs two **soft** checks (`_validate_turn()` runs both, hard first). They report kind `echo`:

- A standing communication limit retold in more than one sentence (two in the opening, which has to establish it). `world_constraints.restatement_reason`.
- A run of 16 or more words in a row shared with the last three committed turns. `repetition_guard.copied_passage_reason`. The turns are read from `db.turns` for the check only (`_recent_narratives`); nothing is stored.

Both thresholds are starting values from a small sample (30 recorded turns for the first, 47 Grok turns for the second), not proven limits.

On failure, `_generate_validated_turn()` retries once with a format, hallucination, pacing or echo correction hint. After the retry, a hard failure is replaced by the fallback turn (below). A soft failure, including `echo`, keeps the model's own turn and never produces a fallback.

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

## What every turn request carries

Sent with every turn, opening included (`_generate_turn`, `_build_messages`):

- the prose mode directive (paragraph range and character budget for the story's turn length)
- the writing style directive (`plain`, `balanced`, `rich`)
- `turn_rules.TURN_CLARITY_RULES`: plain stakes, plain words, movement, and choices that are real actions. A choice never states a number, a name or an agreement the story has not shown
- on the opening, `opening_state.OPENING_ORIENTATION_RULE`
- for Guided and Advanced stories, the creation directive (`creation_contract.build_later_turn_creation_directive`) and the hook directive
- standing constraints, when the premise has any (below)

## Player text is story data

Everything the player types (world type, role, tone, premise, custom answers, a seeded pressure) is placed in one `<player_story_data>` JSON block in the final user message. Each value is bounded (`creation_contract.PLAYER_DATA_BOUNDS`) and `<` and `>` are escaped, so typed text cannot close the block or look like a tag. Engine instructions carry only engine tokens or phrases from fixed engine tables. Where an instruction needs a typed value it names the reference, for example `player_story_data.premise`. `<prior_state>` is escaped the same way and the rule covers it. Catalog values (a known genre, a known role) stay inline. Nothing in a save is rewritten: the bounding happens when the request is built, so an over-long stored value is still readable and still bounded.

## Delivery guards

`_generate_validated_turn` runs `_apply_delivery_guards` on every turn that will be shown and stored, model-written or fallback (`delivery_guards.py`). No model call, no retry. Notes are recorded in the turn meta under `delivery_guards`.

- **Requested footer.** If the player's setup asked the narrator to end turns with a word or phrase, a last line that is only that phrase is removed. The check reads the request. It is not a word list, and the same word inside real prose is kept.
- **Turn length.** Paragraph breaks are moved so the count is inside the mode's range: neighbours are merged, or the paragraph with the most sentences is split. Words and their order never change and nothing is added. A turn with fewer sentences than the minimum paragraph count is delivered short and noted as `paragraph_range_unmet`.
- **Unsupported counts in choices.** "the three names" loses its number unless a sentence the player has seen, or the accepted state, counts that noun ("three names"). Only definite counts are checked.
- **Standing constraint status** is stamped into `rolling_state.world_constraints` (below).

## Standing constraints

`world_constraints.py`. A premise sentence that states a limit ("cannot", "can no longer", "unable to", "no way to") is a standing constraint. A sentence addressed to the narrator is not. The list is read from the stored premise each turn, so older saves get it without being rewritten.

- Status is engine state in `rolling_state.world_constraints`. The model's copy is discarded each turn. Anything not recorded as lifted is active.
- Every request restates each constraint and its status in a system message. The wording of the constraint travels in the player story data block. For a communication constraint the message says no meaning passes, then tells the model to mention the limit in at most one sentence a turn and not to list what fails to arrive. It carries no phrase list: the earlier wording ("no recognised sign, no words made out, no answer, no agreement") was repeated back in the prose, turn after turn.
- A constraint is lifted only when the model proposes it (`"constraint_lifted":[{"id","how"}]` in `rolling_state`) on a turn that answers a player action. A proposal in the opening or on a fallback turn is refused. The turn number, how, and the player's action are stored, and later requests say so.
- For a communication constraint (the limit is on signalling, speaking, calling, hearing, sending word and similar), `_full_validate` rejects a turn in which a sign both sides already know, or an exchange stated as received, crosses to the far side or the named parties while the constraint is active. The turn is retried once, then replaced by the fallback. Seeing a light with no meaning is allowed.
- Retelling: a communication constraint that is retold in more than one sentence of a turn (a denial and a word for meaning in one sentence, such as "no word came") is an `echo` defect. It costs one retry at most and never a fallback turn.
- Limits: whether a player action is a plausible way to lift a constraint is the model's judgement. The breach check and the retelling check are narrow English pattern checks for the communication class only. Other kinds of constraint are carried forward and restated but not checked. Whether Grok follows the "one sentence" wording is not proven by the tests, which replay recorded turns.

## Fallback turn

When a turn is rejected twice, `_build_fail_forward_parsed_turn` writes a turn from the last accepted state strip only (Position, Pressure, Conditions). It restates them unchanged, says nothing is settled, answers no question, and offers four complete choices built from fixed sentences plus a carried item or a companion the last state places with the player. Long state text is cut between words. One turn is committed.

## Custom World seeding

When `custom_world_setup` is provided (no `scenario_id`), `_seed_custom_setup_into_rolling()` injects answers into:

- `simulation_hooks`
- `world_instability`
- `story_focus`
- `relationship_threads`
- `inventory_objects`
- `object_locations`

The opening prompt carries the engine instructions from `_build_custom_world_setup_block()`; the answers themselves go in the player story data block. The player's premise (`custom_world_setup.premise`), the time period (mapped to an era by `TIME_PERIOD_ERAS`) and the recent change also shape the opening: the recent change narrows the opening archetype pool (`opening_state.RECENT_CHANGE_ARCHETYPES`) and is stated to the model as an established past event whose effect must be visible in the opening (`creation_contract.RECENT_CHANGE_FACTS`). A second threat may arrive on top of it and never replaces it. Run identity and opening are rolled once at creation and never again. Relationship **vectors** are initialized on turn 1 by `update_relationship_calculus`, not from setup answers directly.

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

## Current foundation/runtime status on `emergent`

| System | Status |
|--------|--------|
| Utility AI | Implemented; canonical selection defaults ON through `ENABLE_CANONICAL_UTILITY`; deterministic live routing verified; fail-closed heuristic fallback retained; provider-backed gameplay acceptance unverified |
| Actor resolution | Canonical module present in shadow/default-off promotion mode; the existing `npc_world_moves` tier resolver remains the live local substitute |
| Formal event sourcing | **DEFERRED** — full contract unavailable beyond PRD summary; turn log only on `emergent` HEAD. Accepted as the current design on 2026-11-24: state is kept as snapshots, and no `db.events` collection exists. The state added on 2026-11-23 follows the same rule: `claim_state`, `order_state`, `npc_ledger` and `play_state` are overwritten on the session document inside the turn commit, and `duets` holds its world as a snapshot with one `duet_turns` row per turn. None of it is rebuilt from a log. |
| Living Cast | Merged and live on `emergent` as a local substitute for the unavailable full PRD contract |
| Scoring / NaN ranking guards | N/A — never existed in this repo |

---

## Historical recovery branch appendix (superseded)

The snapshot below is retained as historical merge context. Current runtime
status is the table above; do not treat the default-off/unmerged wording below
as operational truth.

**Branch:** `recovery/living-cast-working-tree` @ `4dadb3f` — **unmerged**, **not deployed**, **not covered by emergent CI**, **not merge-ready**.

At that point, Living Cast added `npc_agendas.py`, `npc_world_moves.py`, `arc_diversity.py` orchestrated in `replayability.prepare_action_turn` with world execution mode `TURN_COUPLED_AUTONOMY_ONLY`. Actor Resolution and Utility AI were classified as **local substitutes** rather than full PRD Ch 25/27 modules (Bible full text ends at Chapter 21; Chapters 22–32 are PRD tracker summaries only).

Bounded `npc_move_receipts` and `transition_receipts` are **LOCAL SUBSTITUTE** — they provide idempotency and causal pointers but do not provide canonical reconstruction or durable complete event history.

**Historical blockers before merge (superseded):** pressure authority unresolved; relationship provenance unresolved (vectors mutated from player intent + generated prose); golden-path blockers remained at that snapshot.

## Branching, notebook and chapter handover

Three player features share the existing save, lease and commit machinery. None of them calls the narrator or spends credit.

- **Branch** (`story_branching.py`): copies one committed state under the source action lease in one transaction. Scene, choices, visible history, world state, cast, protagonist, equipment, settings and persisted seed or random state carry over. The branch gets a deterministic id, a `branch_label` and `branched_from`. Pending requests, locks and retry records stay behind. The notebook starts empty.
- **Notebook** (`notebook.py`, collection `notebook_items`): pins and theories are private to the player and the save. Pins are validated against `build_player_paragraphs` output, so only text the player was shown can be pinned. The narrator path and the default export never read the collection. Reset and delete remove its rows inside their transactions. A handover within a save keeps the notebook.
- **Chapter handover** (`chapter_handover.py`): an engine written turn (`turn_kind: "handover"`) that moves control to a living NPC with at least two published appearances. One handover per save in this version. The former protagonist becomes an engine controlled NPC row (`former_protagonist: true`), the successor leaves the NPC list and keeps their own items, condition and knowledge. Items in the knowledge lists (clues, unresolved, promises, relationship_threads, known_rooms, route_continuity) are fingerprinted at the boundary and hidden from the narrator unless the item names the successor or is public. Stored state keeps them. `_build_messages` swaps in the successor view, floors replay at the boundary turn and adds a `[CONTROLLED_CHARACTER]` system message. Relationship vectors are stashed in `handover.former.vectors`. Older saves without a protagonist name fall back to the role, and unknown facts stay unknown.

Known limits: the narrator schema does not record NPC inventory, condition or knowledge, so a successor's possessions read as unknown unless the NPC row carries `inventory`, `condition` or `knows`. The UI pins whole paragraphs. Mature-content re-render and replayability secret directives were not audited for handover leaks.


## Claims, standing orders and two-player stories

The engine owns what happened and who could observe it. The narrator describes the result.

- `claim_engine.py`: a directed ledger of who was told what, and who overheard. Narrator context goes through the secret reveal directive. State lives in the session as `claim_state`, so branching copies it.
- `order_engine.py`: `order_state` holds orders, a small world (gauges and the ferry) and `last_tick_turn`. It ticks before the narrator on the pre-narrator rolling state, and its effects are re-projected after the merge every turn because the narrator's `npcs` replaces the list wholesale. Vocabulary is small: water mark or person arrives, cut ferry or deliver parcel. A person refuses when trust is below 25.
- `duet.py` and `duet_api.py`: one built-in setting with two seats. The engine understands signal flashes and launching the one boat; other actions are narrated to the actor only. Observers are decided by line of sight. Concurrency uses an action lease, a revision check, a unique `(duet_id, turn_number)` index and a partial unique `(duet_id, request_id)` index. The identity of a seat is the device id.

Known limits: claims need known places and `within_earshot` for witnesses; the duet comparison shows each seat's actions and narration, never notebooks or engine records.

### NPC possessions

`npc_possessions.py` keeps what each NPC carries (`inventory`), their `condition` and `contacts` on the save as `npc_ledger`. The narrator replaces `rolling_state["npcs"]` every turn, so after the merge and the order projection the engine restores any of those fields the narrator left out. A row that carries a field updates the ledger. A field nobody recorded stays absent, so unknown possessions stay unknown. The ledger is bounded (64 rows, 12 items of 80 characters), copied by branching, and never shown raw in player responses.

**Who knows what an NPC carries.** The player is not told what someone else has unless it was handed over, or they asked and the person chose to answer. The ledger keeps a `known` list per NPC. The narrator is sent `inventory_known` instead of `inventory`, plus a standing `[NPC_POSSESSIONS_V1]` rule. A direct question ("ask Mara what she is carrying", "ask Mara if she has a knife") or a request ("ask Mara to give me the knife") is decided by the engine before the narrator runs. The person answers or hands over only when trust is at least 40 (`DISCLOSE_MIN_TRUST`), they are not hostile, and they are present. With no trust data, only an ally or friendly stance answers. Otherwise the narrator is told to show a refusal in character and name nothing. The narrator can add items (they become known) and drop items the player already knows about, but cannot erase hidden ones. Limits: questions are matched by phrasing and by the last word of an item name, searching or stealing is not covered, and the opening turn is written before the ledger exists.

## Player moves

Code: `backend/play_moves.py` (registry and shared plumbing), `play_moves_api.py` (reads and preview), `play_facts.py` (what a scene contains: people present, shown passages, held items, trust), and one engine per move: `challenge_engine`, `bargain_engine`, `route_engine`, `regard_engine`, `build_engine`.

Rules every engine follows:

- Availability comes from the save, never from genre or scenario. A new or custom story gets people, places and items from the narrator's `rolling_state` and the published prose, so a move becomes possible once the story has supplied what it needs. If something is missing the move says what, takes no turn, and writes nothing.
- The engine decides ownership, knowledge, access, success and consequences. The narrator only receives directives for the turn and cannot decide them. Items an engine takes or hands over are enforced on the ledger after the narrator replies (`project_ledger`).
- Each engine keeps its own state under `play_state[kind]` and exposes `apply`, `options`, `narrator_context`, and optionally `tick` and `project`.
- Idempotency: ids are derived from `(kind, request_id)` and kept in the record, so a retry cannot spend or award twice or leave half a transaction.
- Knowledge: a route or a building is known only to the characters who learned it. After a chapter handover the new character has only what they know.
- Private notes (for example on something built) are shown only to the builder.

Known limits: two-player signals can only be settled before the first lamp is lit; narrator behaviour is verified against offline fixtures only.
