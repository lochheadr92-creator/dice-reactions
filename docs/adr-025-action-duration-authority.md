# ADR-025: Action-duration authority — engine-owned structured time commands, zero-day ordinary actions

**Status:** Proposed (decision drafted for owner approval; NO implementation in this ADR — documentation only)
**Date:** 2026-07-04
**Deciders:** Ryan
**Branch target:** `emergent` (docs-only commit; no production code or test changes)
**Resolves blocker:** `D_ACTION_DURATION_AUTHORITY` (on acceptance + implementation; the blocker stays open until the implementation task lands and is verified)
**Amends / relates:** Chapter 33 Phase 1 clock seam (`backend/simulation_clock.py`, `replayability.prepare_action_turn`), `docs/ch33-action-duration-authority-brief.md`, ADR-019 (replayability state ownership)
**Source material:** `docs/ch33-action-duration-authority-brief.md` (code-inspection brief, commit `027d2bd`); owner policy decisions recorded 2026-07-04

---

## 1. Context / problem

Chapter 33 Phase 1 shipped a replay-safe integer simulation-day clock with a single consumer (`simulation_clock.integrate_turn`, called from `replayability.prepare_action_turn`, `replayability.py:723`) that only consumes a pre-existing engine-owned `replayability_state["pending_time_advance"]`. There is **no approved producer**: no deterministic, engine-owned contract maps an accepted player action to elapsed simulation days. Blocker `D_ACTION_DURATION_AUTHORITY` forbids inferring time from client payloads, player wording, LLM output, parsed model fields, wall-clock time, or `turn_number * duration`.

The brief (§11) also records that the repository defines **no** numeric duration mappings (conversation/search/combat/travel/etc.), no min/max elapsed time, no source-of-truth rule, and no sub-day policy. This ADR supplies those decisions.

## 2. Decision (owner-ratified policy, v1)

1. **Ordinary actions advance exactly 0 simulation days.** No action-category → duration mapping exists in v1. The engine never infers duration from action text, LLM output, parsed fields, wall-clock, or turn arithmetic. The Phase 1 invariant — "an ordinary turn advances the clock by zero" — is ratified as the permanent v1 rule, not a stopgap.
2. **Time advances only via an explicit structured time command** ("rest / wait / travel N days" style). The player declares intent through a schema-validated structured field — never free text, never LLM parsing. The **engine is the sole authority**: it validates, bounds-clamps, accepts or rejects, and deterministically produces the structured `pending_time_advance` event. The client's requested value is a *request*; the engine-produced event is the *authority*.
3. **Same-turn integration.** The accepted action's time advance is consumed in the SAME turn: an explicit post-acceptance clock-integration step runs after the action outcome is accepted and engine-guarded, before the session update payload is built, and is committed atomically in the existing `_persist_story_action_turn` CAS update.
4. **Sub-day policy (v1, exact owner wording):** Sub-day actions advance 0 simulation days. Do not round them up. Do not accumulate fractional days. Ordinary actions stage no time event. An explicit structured sub-day command may stage a deterministic zero-day no-op **only if audit traceability is needed** (not implemented in v1). Fractional/sub-day clock support stays deferred to a later schema change (brief §10).

## 3. Resolution of the brief's undefined decisions (§11)

| Open question (brief §11) | v1 decision |
|---|---|
| Duration mapping for conversations, searches, combat, travel, rest, crafting, waiting, projects | **None.** All ordinary actions = 0 days. Only structured `rest`/`wait`/`travel` commands advance time. |
| Minimum / maximum elapsed time per action | Ordinary: exactly 0. Structured command: integer days, `1 <= requested_days <= MAX_TIME_COMMAND_DAYS` (proposed constant `30`; requires owner approval before implementation). |
| Player-declared, rule-derived, location-derived, or scenario-derived? | Player-declared **through a structured schema field**, engine-validated and engine-clamped. The engine-produced event is the only authority. |
| Conflicting duration sources | Not possible: single producer, single structured source. Any duration-like content in prose/LLM output/parsed fields is ignored (existing strip/guard posture). |
| Sub-day accumulation / expiry | None. 0 days, no rounding, no accumulation (Decision §2.4). |
| Variation by mode, difficulty, region, story phase | None in v1. Uniform rule everywhere. |

## 4. Structured command schema (contract for the implementation task)

Request side — a new **optional** structured field on `ActionRequest` (`server.py:537`):

```text
time_command = {
    "command_type": "rest" | "wait" | "travel",
    "requested_days": int   # 1..MAX_TIME_COMMAND_DAYS
}
```

- Absent field → ordinary action → no event, 0 days (the overwhelmingly common path; byte-identical behaviour to today).
- Schema/bounds violations are rejected **fail-closed at request validation time** (HTTP 400, before lease/provider cost). An invalid command never silently degrades to "0 days"; the whole action is rejected so the player is never misled.
- Extra/unknown client fields remain ignored; the client can never write the clock, `pending_time_advance`, or any `replayability_state` key directly (existing ownership boundaries, brief §2).

Produced event — reuses the existing Phase 1 contract shape unchanged (brief §5):

```text
pending_time_advance = {
    event_id: "time_advance:{session_id}:{next_turn_number}",   # deterministic, retry-stable
    elapsed_simulation_days: <engine-clamped int>,
    reason: "player_time_command:{command_type}",
    source_type: "player_time_command",
    source_event_ids: [],
    expected_previous_simulation_day: <post-prepare working clock day>,
    target_simulation_day: <expected_previous + elapsed>,
}
```

`event_id` derives from the accepted action identity `(session_id, next_turn_number)`, which is fixed under the action lease — stable across provider retries, at most one event per accepted action, and permanently guarded by the existing `expected_previous_simulation_day` compare-and-advance barrier plus the bounded receipt window (`simulation_clock.apply_time_advance`, `require_precondition=True`).

## 5. Production and consumption points (same-turn design)

Pipeline positions refer to the brief §1 numbering and `server.py` `story_action`:

1. **Request validation (new, early):** validate `time_command` shape/bounds when `ActionRequest` is parsed. Reject 400 on violation. No state touched.
2. **Steps 2–8 unchanged:** lease, secret reveal, `prepare_action_turn` (whose pre-provider `integrate_turn` call still consumes only *legacy/pre-existing* pending events and performs lifecycle catch-up — it cannot see the new event, which does not exist yet), provider generation, validation, and all engine guards.
3. **Production (new, post-acceptance):** after `_generate_validated_turn` succeeds and all guards/merges complete (i.e., the action outcome is accepted and engine-guarded, after `finalize_action_turn`, ~`server.py:3552`), the engine produces the `pending_time_advance` event from the validated `time_command`, reading `expected_previous_simulation_day` from the **post-prepare working** `replayability_state` clock (not the stale persisted session). Production refuses to overwrite an existing pending event (fail-closed diagnostic; brief §8).
4. **Consumption (new, post-acceptance):** an explicit second integration step — e.g. `replayability.integrate_accepted_action_time(...)` wrapping `simulation_clock.integrate_turn` with the approved receipt helper — consumes the event into the working `replayability_state` (clock advance + same-turn lifecycle catch-up), before `update_set`/`session_snapshot` are built (~`server.py:3595`).
5. **Persistence (unchanged boundary):** `_persist_story_action_turn` commits turn + session (including the advanced clock inside `update_set["replayability_state"]`) in the existing lease-guarded CAS update. This satisfies brief §7: time commits with the accepted outcome, never before it.

**Narrative alignment (output, not authority):** the implementation may inject a deterministic prompt directive ("N simulation days pass") so prose matches engine truth — mirroring existing directive patterns. The LLM never authors time.

## 6. Failure, retry, concurrency, idempotency semantics (brief §8)

- **Invalid command** → 400 at request validation; no lease, no provider call, no time.
- **Provider/validation/parse failure** → exception raised before production (step 3 above) → no event exists → no time.
- **Lease loss / CAS failure** → the produced event and consumed clock live only in working copies that are discarded; the persisted session is untouched → no time survives independently (brief §7).
- **Retry of the same turn** under the same lease → same `next_turn_number` → same deterministic `event_id` → at most one advance.
- **Duplicate player submission** that wins a NEW turn is a new accepted action; advancing again is correct (the player rested twice). Replay of an OLD event remains blocked permanently by `expected_previous_simulation_day` (stale → duplicate no-op) regardless of receipt-window eviction.
- **Existing pending event present at production time** → production refuses to overwrite; fail-closed diagnostic; no silent replacement.

## 7. Feature gating

The structured time command is gated behind `ENABLE_NPC_LIFECYCLE` (the existing default-OFF Chapter 33 flag): with the flag OFF, `simulation_clock.integrate_turn` is a complete no-op, so a request carrying `time_command` is **rejected deterministically** (feature-disabled error) rather than silently ignored. Default behaviour of the deployed app is therefore byte-identical to today. (Alternative — a separate `ENABLE_TIME_COMMANDS` flag — noted for owner preference at implementation time.)

## 8. Determinism / hash / state implications

- Ordinary turns (no `time_command`) follow a byte-identical path: no event, zero advance, no new `replayability_state` keys → existing regression, determinism, and snapshot-identity suites stay green unchanged.
- The event is a pure function of `(session_id, next_turn_number, command_type, engine-clamped days, working clock day)` — no wall-clock, no RNG, no provider data.
- All clock/lifecycle state remains inside `replayability_state` (never player-visible, never LLM-authored, stripped by existing leakage guards). No new player/prompt surfaces beyond the optional deterministic narrative directive.
- The same-turn second `integrate_turn` call reuses the existing idempotency machinery; the pre-provider call and the post-acceptance call can never double-apply one event (production happens after the first call; consumption removes the event; the barrier blocks any replay).

## 9. Rejected alternatives

- **Action-category duration table** (conversation = X, travel = Y): no approved source of truth exists (brief §11); invented values would encode unratified game design. **Rejected for v1.**
- **LLM/parser-derived duration:** model-authored time violates "State is truth, narrative is output" and replay determinism (brief §3). **Rejected permanently.**
- **Trusting the client's requested value directly:** client-owned fields cannot mutate simulation time (brief §3); hence engine validation + clamping + engine-produced event as the sole authority. **Rejected.**
- **Next-turn (staged) consumption:** smaller diff, but the player who rests 3 days would see aging/lifecycle effects only on the following action — a visible cause/effect mismatch. Owner selected same-turn. **Rejected.**
- **Rounding or accumulating sub-day time:** requires a clock schema migration (brief §10); explicitly deferred. **Rejected for v1.**

## 10. Implementation task outline (separate task; NOT this ADR)

Files (per brief §12): `backend/server.py` (schema + validation + production/consumption wiring), `backend/replayability.py` (post-acceptance integration seam), `backend/simulation_clock.py` (expected unchanged — the existing primitive already enforces the contract), possibly a small `backend/time_commands.py` producer module.

Tests (per brief §12): producer unit tests (determinism, bounds, clamp, refuse-overwrite, retry-stable `event_id`); server action tests (invalid/rejected/uncommitted actions stage nothing; ordinary actions byte-identical); same-turn consumption + lifecycle catch-up; lease-conflict/CAS-rollback leaves no time; gateway/parser/player-payload tests proving client/LLM duration injection is ignored and clock internals stay hidden; flag-OFF rejection.

## 11. Non-goals

- No production code or test changes in this ADR (documentation only).
- No sub-day/fractional clock schema, no accumulation, no rounding.
- No action-category duration mappings; no per-mode/difficulty/region variation.
- No births/pregnancy, inheritance, succession, or 200-year burn-in (still deferred, `docs/next-work.md` Ch 33 status).
- No default flag activation; no `TURN_INTEGRATION_VERIFIED` claim.
- No frontend UI for time commands (follows implementation acceptance).

## Action items

1. [ ] Owner approves/amends this ADR — in particular `MAX_TIME_COMMAND_DAYS = 30` (§3) and the flag-gating choice (§7).
2. [ ] On acceptance, implement §5 + §10 as a separate task with the full test plan.
3. [ ] On verified implementation, close blocker `D_ACTION_DURATION_AUTHORITY` in `docs/next-work.md` and update the Ch 33 status section.
