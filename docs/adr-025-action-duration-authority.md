# ADR-025: Action-duration authority — engine-owned structured time commands, zero-day ordinary actions

**Status:** Accepted (owner amendments applied 2026-07-04; NO implementation in this ADR — documentation only)
**Date:** 2026-07-04 (drafted); 2026-07-04 (owner amendments ratified; Accepted)
**Deciders:** Ryan
**Branch target:** `emergent` (docs-only commit; no production code or test changes)
**Resolves blocker:** `D_ACTION_DURATION_AUTHORITY` — the blocker stays OPEN until the Phase 2A runtime implementation and its tests land and are verified
**First implementation scope (Phase 2A):** `WAIT_ONE_DAY` only — a single approved structured command advancing exactly 1 simulation day. `rest`, `travel`, arbitrary N-day commands, sub-day accumulation, and any broad action-duration inference remain deferred.
**Amends / relates:** Chapter 33 Phase 1 clock seam (`backend/simulation_clock.py`, `replayability.prepare_action_turn`), `docs/ch33-action-duration-authority-brief.md`, ADR-019 (replayability state ownership)
**Source material:** `docs/ch33-action-duration-authority-brief.md` (code-inspection brief, commit `027d2bd`); owner policy decisions recorded 2026-07-04; owner amendment set ratified 2026-07-04 (pipeline correction, duration limit, Phase 2A scope, `ENABLE_TIME_COMMANDS` flag, event identity, sub-day reaffirmation)

---

## 1. Context / problem

Chapter 33 Phase 1 shipped a replay-safe integer simulation-day clock with a single consumer (`simulation_clock.integrate_turn`, called from `replayability.prepare_action_turn`, `replayability.py:723`) that only consumes a pre-existing engine-owned `replayability_state["pending_time_advance"]`. There is **no approved producer**: no deterministic, engine-owned contract maps an accepted player action to elapsed simulation days. Blocker `D_ACTION_DURATION_AUTHORITY` forbids inferring time from client payloads, player wording, LLM output, parsed model fields, wall-clock time, or `turn_number * duration`.

The brief (§11) also records that the repository defines **no** numeric duration mappings (conversation/search/combat/travel/etc.), no min/max elapsed time, no source-of-truth rule, and no sub-day policy. This ADR supplies those decisions.

## 2. Decision (owner-ratified policy, v1)

1. **Ordinary actions advance exactly 0 simulation days.** No action-category → duration mapping exists in v1. The engine never infers duration from action text, LLM output, parsed fields, wall-clock, or turn arithmetic. The Phase 1 invariant — "an ordinary turn advances the clock by zero" — is ratified as the permanent v1 rule, not a stopgap.
2. **Time advances only via an explicit structured time command.** The future command family is `wait` / `rest` / `travel`. The player declares intent through a schema-validated structured field — never free text, never LLM parsing. The **engine is the sole authority**: it owns command validation, the approved duration, event construction, and clock mutation. Invalid input is **rejected, never silently clamped**. The client's requested command is a *request*; the engine-produced event is the *authority*. The client must not provide the event ID.
3. **Same-turn, pre-provider integration.** The validated command's time advance is produced onto the in-memory working state and consumed through the EXISTING `simulation_clock` seam inside `replayability.prepare_action_turn` — so clock/lifecycle updates exist BEFORE provider narration, and the provider narrates against the updated authoritative working state. The advance becomes **authoritative only when the existing `_persist_story_action_turn` CAS persistence succeeds**. Any failure (provider generation, parsing, validation, lease ownership, CAS) persists no clock advance; a retry sees the previously persisted clock and safely recreates the same deterministic event.
4. **Duration limit:** `MAX_TIME_COMMAND_DAYS = 30` is **approved** — a hard safety ceiling, not a default duration. Commands requesting fewer than 1 or more than 30 whole days are rejected. This numeric constant must be added to the appropriate authoritative constants/configuration location during implementation.
5. **Phase 2A implementation scope:** the first runtime implementation enables ONLY `WAIT_ONE_DAY` → 1 approved simulation day. `rest`, `travel`, arbitrary N-day commands, sub-day accumulation, and broad action-duration inference remain deferred.
6. **Feature flags:** a separate `ENABLE_TIME_COMMANDS` flag (default OFF) gates acceptance of structured time commands and authoritative clock advancement. `ENABLE_NPC_LIFECYCLE` (default OFF) gates NPC aging, mortality, and lifecycle processing after a clock advance. Clock progression must not conceptually depend on NPC lifecycle being enabled.
7. **Sub-day policy (v1, exact owner wording):** Sub-day actions advance 0 simulation days. Do not round them up. Do not accumulate fractional days. Ordinary actions stage no time event. Optional explicit zero-day audit events are allowed **only when genuinely required for traceability** (not implemented in v1). Fractional/sub-day clock support stays deferred to a later schema change (brief §10).

## 3. Resolution of the brief's undefined decisions (§11)

| Open question (brief §11) | v1 decision |
|---|---|
| Duration mapping for conversations, searches, combat, travel, rest, crafting, waiting, projects | **None.** All ordinary actions = 0 days. Only structured time commands advance time (family: `wait`/`rest`/`travel`; Phase 2A enables only `WAIT_ONE_DAY` = 1 day). |
| Minimum / maximum elapsed time per action | Ordinary: exactly 0. Structured command: whole days, `1 <= requested_days <= MAX_TIME_COMMAND_DAYS = 30` (**approved** hard safety ceiling, not a default). Requests outside the range are **rejected — never silently clamped**. The constant must live in the authoritative constants/configuration location (implementation task). |
| Player-declared, rule-derived, location-derived, or scenario-derived? | Player-declared **through a structured schema field**. The engine owns command validation, the approved duration, event construction, and clock mutation; the engine-produced event is the only authority. |
| Conflicting duration sources | Not possible: single producer, single structured source. Any duration-like content in prose/LLM output/parsed fields is ignored (existing strip/guard posture). |
| Sub-day accumulation / expiry | None. 0 days, no rounding, no accumulation (Decision §2.7). |
| Variation by mode, difficulty, region, story phase | None in v1. Uniform rule everywhere. |

## 4. Structured command schema (contract for the implementation task)

Request side — a new **optional** structured field on `ActionRequest` (`server.py:537`):

```text
time_command = {
    "command_type": "wait" | "rest" | "travel",   # future family; Phase 2A accepts ONLY "wait"
    "requested_days": int                          # 1..MAX_TIME_COMMAND_DAYS (30); Phase 2A accepts ONLY 1
}
```

- Absent field → ordinary action → no event, 0 days (the overwhelmingly common path; byte-identical behaviour to today).
- Schema/bounds violations are rejected **fail-closed at request validation time** (HTTP 400, before lease/provider cost). Fewer than 1 or more than 30 whole days is rejected — **never silently clamped**. An invalid command never silently degrades to "0 days"; the whole action is rejected so the player is never misled.
- **Phase 2A enablement:** only the closed command `WAIT_ONE_DAY` (`command_type = "wait"`, `requested_days = 1`) is accepted at runtime; any other family member or day count is rejected as not-yet-enabled, even though this ADR defines the full family.
- The client may request an approved closed command, but the **engine owns command validation, the approved duration, event construction, and clock mutation**. The client must not provide the event ID. Extra/unknown client fields remain ignored; the client can never write the clock, `pending_time_advance`, or any `replayability_state` key directly (existing ownership boundaries, brief §2).

Produced event — reuses the existing Phase 1 contract shape unchanged (brief §5):

```text
pending_time_advance = {
    event_id: "time_advance:{session_id}:{turn_number}:{command_kind}:{approved_days}",  # engine-constructed, deterministic, retry-stable
    elapsed_simulation_days: <engine-approved whole days>,   # Phase 2A: always 1
    reason: "player_time_command:{command_kind}",
    source_type: "player_time_command",
    source_event_ids: [],
    expected_previous_simulation_day: <previously persisted clock day>,
    target_simulation_day: <expected_previous + elapsed>,
}
```

`event_id` derives from the accepted action identity plus the engine-approved command — `(session_id, turn_number, command_kind, approved_days)` — fixed under the action lease: stable across provider retries, at most one event per accepted action, and permanently guarded by the existing `expected_previous_simulation_day` compare-and-advance barrier plus the bounded receipt window (`simulation_clock.apply_time_advance`, `require_precondition=True`).

## 5. Production and consumption points (owner-corrected same-turn, pre-provider design)

The v1 draft placed event production AFTER the guards — too late, because provider narration would already have been generated against a stale clock. The ratified sequence produces and consumes the advance BEFORE the provider, so narration reflects the updated authoritative working state, while authority still attaches only at CAS persistence:

1. **Request accepted:** `ActionRequest` schema validation, including `time_command` shape/bounds and the `ENABLE_TIME_COMMANDS` flag check. Violations reject 400 (no lease, no provider cost, no state touched).
2. **Action lease acquired** (`acquire_action_lease`, unchanged).
3. **Structured time command validated** against session state (flag on, closed command enabled in the current phase, replayability state present).
4. **Production (engine-owned):** the engine creates `pending_time_advance` on the **in-memory working** `replayability_state` copy (`server.py:3442`), with `expected_previous_simulation_day` read from the previously persisted clock and the deterministic `event_id` of §4. Production refuses to overwrite an existing pending event (fail-closed diagnostic; brief §8).
5. **Consumption (existing seam, unchanged location):** `replayability.prepare_action_turn` consumes the event through the existing `simulation_clock.integrate_turn` call (`replayability.py:723`) — clock advance and (if `ENABLE_NPC_LIFECYCLE` is on) lifecycle catch-up are applied to the working state **before provider narration**.
6. **Provider runs against the updated authoritative working state**; a deterministic prompt directive ("N simulation days pass") may align prose with engine truth — narrative is output, never authority.
7. **Output is parsed and guarded** (existing validation + guard pipeline, unchanged).
8. **Atomic persistence:** the turn and the updated session state (including the advanced clock inside `update_set["replayability_state"]`) are persisted through the existing `_persist_story_action_turn` lease-guarded CAS path. **The advance is only authoritative once CAS persistence succeeds** (brief §7: time commits with the accepted outcome, never before it).

## 6. Failure, retry, concurrency, idempotency semantics (brief §8)

- **Invalid command / flag OFF** → 400 at request validation; no lease, no provider call, no time.
- **Provider generation, parsing, validation, lease-ownership, or CAS persistence failure** → the produced event and consumed clock live only in in-memory working copies that are discarded; **no clock advance is persisted**.
- **Retry after any failure** → `turn_count` is unchanged, so the retry sees the previously persisted clock and safely **recreates the same deterministic event** (same `session_id`, `turn_number`, `command_kind`, `approved_days` → same `event_id`, same `expected_previous_simulation_day`) → at most one persisted advance per accepted action.
- **Duplicate player submission** that wins a NEW turn is a new accepted action; advancing again is correct (the player waited twice). Replay of an OLD event remains blocked permanently by `expected_previous_simulation_day` (stale → duplicate no-op) regardless of receipt-window eviction.
- **Existing pending event present at production time** → production refuses to overwrite; fail-closed diagnostic; no silent replacement.

## 7. Feature gating (owner decision: separate flags)

A separate flag **`ENABLE_TIME_COMMANDS`** (default OFF) is introduced. Responsibilities are split:

- **`ENABLE_TIME_COMMANDS`** gates acceptance of structured time commands and authoritative clock advancement. Flag OFF → a request carrying `time_command` is **rejected deterministically** (feature-disabled error), never silently ignored.
- **`ENABLE_NPC_LIFECYCLE`** gates NPC aging, mortality, and lifecycle processing after a clock advance.
- **Clock progression must not conceptually depend on NPC lifecycle being enabled.** The current `simulation_clock.integrate_turn` no-ops entirely when `ENABLE_NPC_LIFECYCLE` is off; the implementation task must split that gating so clock consumption is governed by `ENABLE_TIME_COMMANDS` while lifecycle processing remains governed by `ENABLE_NPC_LIFECYCLE`.
- **Both flags remain default OFF.** Default deployed behaviour stays byte-identical to today.

## 8. Determinism / hash / state implications

- Ordinary turns (no `time_command`) follow a byte-identical path: no event, zero advance, no new `replayability_state` keys → existing regression, determinism, and snapshot-identity suites stay green unchanged.
- The event is a pure function of `(session_id, turn_number, command_kind, approved_days, previously persisted clock day)` — no wall-clock, no RNG, no provider data. The client never supplies the event ID.
- All clock/lifecycle state remains inside `replayability_state` (never player-visible, never LLM-authored, stripped by existing leakage guards). No new player/prompt surfaces beyond the optional deterministic narrative directive.
- Production (step 4) happens before the single existing `integrate_turn` consumption point (step 5); no second integration call exists, so one event can never be double-applied — consumption removes the event, and the `expected_previous_simulation_day` barrier blocks any replay.

## 9. Rejected alternatives

- **Action-category duration table** (conversation = X, travel = Y): no approved source of truth exists (brief §11); invented values would encode unratified game design. **Rejected for v1.**
- **LLM/parser-derived duration:** model-authored time violates "State is truth, narrative is output" and replay determinism (brief §3). **Rejected permanently.**
- **Trusting the client's requested value directly (or silently clamping it):** client-owned fields cannot mutate simulation time (brief §3); silent clamping misleads the player. Hence strict engine validation with rejection + engine-produced event as the sole authority. **Rejected.**
- **Post-guard event production (the v1 draft pipeline):** producing/consuming the advance after `_generate_validated_turn` means provider narration is generated against a stale clock, so prose and authoritative state diverge within the same turn. Owner corrected to pre-provider production/consumption with authority attaching at CAS persistence. **Rejected.**
- **Next-turn (staged) consumption:** smaller diff, but the player who waits a day would see aging/lifecycle effects only on the following action — a visible cause/effect mismatch. Owner selected same-turn. **Rejected.**
- **Rounding or accumulating sub-day time:** requires a clock schema migration (brief §10); explicitly deferred. **Rejected for v1.**

## 10. Phase 2A implementation task outline (separate task; NOT this ADR)

Scope: enable ONLY `WAIT_ONE_DAY` (→ 1 approved simulation day) behind `ENABLE_TIME_COMMANDS` (default OFF).

Files (per brief §12): `backend/server.py` (schema + request validation + pre-lease/pre-provider wiring per §5), `backend/replayability.py` (production seam before the existing consumption point), `backend/simulation_clock.py` (split flag gating per §7 — clock consumption under `ENABLE_TIME_COMMANDS`, lifecycle under `ENABLE_NPC_LIFECYCLE`), possibly a small `backend/time_commands.py` producer module. `MAX_TIME_COMMAND_DAYS = 30` must be added to the appropriate authoritative constants/configuration location.

Tests (per brief §12): producer unit tests (determinism, bounds rejection — no clamping, refuse-overwrite, retry-stable `event_id` including `command_kind`/`approved_days`); server action tests (invalid/rejected/uncommitted actions stage nothing; ordinary actions byte-identical; Phase 2A rejects `rest`/`travel`/N≠1); same-turn pre-provider consumption + lifecycle catch-up under both flag combinations (clock advance with lifecycle OFF must work); lease-conflict/CAS-rollback persists no time and retry recreates the identical event; gateway/parser/player-payload tests proving client/LLM duration injection is ignored and clock internals stay hidden; flag-OFF rejection.

## 11. Non-goals

- No production code or test changes in this ADR (documentation only).
- No `rest`, `travel`, or arbitrary N-day commands in Phase 2A (family defined, not enabled).
- No sub-day/fractional clock schema, no accumulation, no rounding.
- No action-category duration mappings; no broad action-duration inference; no per-mode/difficulty/region variation.
- No births/pregnancy, inheritance, succession, or 200-year burn-in (still deferred, `docs/next-work.md` Ch 33 status).
- No default flag activation; no `TURN_INTEGRATION_VERIFIED` claim.
- No frontend UI for time commands (follows implementation acceptance).

## Action items

1. [x] Owner approved with amendments 2026-07-04: corrected pre-provider pipeline; `MAX_TIME_COMMAND_DAYS = 30` (hard ceiling, reject not clamp); Phase 2A = `WAIT_ONE_DAY` only; separate `ENABLE_TIME_COMMANDS` flag; event identity `time_advance:{session_id}:{turn_number}:{command_kind}:{approved_days}`; sub-day policy reaffirmed. **ADR-025 Accepted.**
2. [ ] Implement Phase 2A (§5 + §10) as a separate task with the full test plan.
3. [ ] On verified Phase 2A implementation, close blocker `D_ACTION_DURATION_AUTHORITY` in `docs/next-work.md` and update the Ch 33 status section. Until then the blocker remains OPEN.
