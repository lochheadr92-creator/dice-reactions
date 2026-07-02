# Chapter 33 Action-Duration Authority Brief

Blocker code: `D_ACTION_DURATION_AUTHORITY`

## 1. Exact Action Pipeline And Call Order

The live player-action path in `backend/server.py` is:

1. `story_action` accepts `ActionRequest`.
2. The action lease is acquired with `acquire_action_lease`.
3. `req.action_text` is copied into the prompt input; the request schema has no authoritative duration field.
4. `secrets.prepare_turn_reveal` runs as a deterministic pre-generation system and returns a guarded working rolling state for secret reveal only.
5. `replayability.prepare_action_turn` runs before provider generation. It can tick replayability systems, choose NPC moves, update stress/foundation diagnostics, and then calls `simulation_clock.integrate_turn`.
6. `simulation_clock.integrate_turn` consumes only a pre-existing `replayability_state["pending_time_advance"]`; ordinary turns advance zero days.
7. `_generate_validated_turn` invokes the provider, parses output, validates it, and may retry.
8. Engine guards merge/restore state: supremacy, object permanence, gateway death/destruction registries, relationship calculus, memory bounds, and related rolling-state safeguards.
9. Replayability finalization collects qualifying echo sources and calls `replayability.finalize_action_turn`.
10. `TurnRecord` and the session update payload are built.
11. `_persist_story_action_turn` inserts the turn and CAS-updates the session under the lease token and expected turn count.
12. The player response is built from sanitized player-facing state.

This means the current clock integration point occurs before the accepted action outcome exists.

## 2. Existing Ownership Boundaries

- Client-owned: HTTP request body and any extra fields the client attempts to send.
- Player-authored text: `ActionRequest.action_text`.
- LLM-authored: provider raw output, generated narrative, generated choices, and generated rolling-state blocks.
- Parser-derived: structured `parsed` turn data produced from the LLM response.
- Gateway-approved: specific guarded registries such as death/destruction permanence after engine validation.
- Deterministic engine-owned: action lease/CAS state, secret reveal preparation, replayability ticks, NPC move selection, foundation/stress updates, `pending_time_advance` consumption, and lifecycle catch-up.
- Persisted authoritative state: the accepted session document, turn document, `replayability_state["simulation_clock"]`, `replayability_state["npc_lifecycle"]`, and any unconsumed `replayability_state["pending_time_advance"]`.

## 3. Why Unsafe Sources Are Rejected

- Client-owned fields cannot be trusted to mutate simulation time.
- Player-authored text is intent/prose, not an accepted engine result.
- LLM narrative and generated rolling state are model-authored and must not own time.
- Parser-derived fields only reflect model output shape; parsing does not create authority.
- Gateway-approved death/destruction registries authorize those permanence facts only, not elapsed time.
- Provider latency, wall-clock time, and `turn_number * duration` are external or synthetic and violate replay determinism.

## 4. Missing Authoritative Action-Result Contract

There is no existing deterministic structured action result that states: this accepted player action consumed exactly N simulation days.

The current code has a replay-safe clock consumer and lifecycle catch-up, but no approved producer that maps an accepted action outcome to elapsed simulation time.

## 5. Smallest Recommended Structured Schema

The existing clock seam should remain the contract shape:

```text
pending_time_advance = {
    event_id,
    elapsed_simulation_days,
    reason,
    source_type,
    source_event_ids,
    expected_previous_simulation_day,
    target_simulation_day,
}
```

The missing producer must be deterministic, engine-owned, and based on a future structured accepted-action result, not text or model prose.

## 6. Recommended Production And Consumption Locations

Production should happen only after the action outcome is accepted and engine-guarded, because rejected or uncommitted actions must not advance time.

Consumption should remain inside `simulation_clock.integrate_turn`. If same-action aging is required, the server/replayability path needs an explicit post-acceptance clock integration step before the session update is built. If next-turn aging is acceptable, finalization can stage a pending event for the following `prepare_action_turn` call.

Either approach needs an explicit contract and tests; it should not be inferred from the current provider output.

## 7. Persistence Timing

Time should be committed with the accepted action outcome in the same session CAS update, not before outcome persistence.

If persistence fails, the staged or consumed time advance must not survive independently. The current `_persist_story_action_turn` CAS pattern is the right persistence boundary because lease loss rolls back the inserted turn and prevents the session update.

## 8. Retry, Concurrency, And Idempotency Behaviour

A future producer must:

- Generate a deterministic `event_id` stable across retries for the same accepted action.
- Stage at most one authoritative event per accepted action.
- Refuse to silently overwrite an existing pending event.
- Leave state unchanged when validation, parsing, lease ownership, or persistence fails.
- Keep stale, duplicate, and out-of-order events blocked by `expected_previous_simulation_day`.
- Preserve the existing behavior where duplicate accepted inputs cannot advance the clock twice.

## 9. Sub-Day Actions And The Integer-Day Clock

The Phase 1 clock is an integer simulation-day clock. Sub-day actions should not be rounded or invented by the engine without an approved policy.

Until such a policy exists, unsupported or sub-day actions should stage no time advance.

## 10. Sub-Day Accumulation And Schema Migration

Supporting accumulated sub-day time would require a clock schema migration or adjacent authoritative accumulator, such as explicit remainder units and unit metadata.

That migration must define replay behavior, target-day calculation, persistence, and how fractional or remainder units become whole simulation days. It is outside the current Phase 1 closure.

## 11. Undefined Numeric Duration Decisions

The repository does not currently define approved mappings for:

- Conversations, searches, combat, travel, rest, crafting, waiting, or multi-step projects.
- Minimum and maximum elapsed time per action.
- Whether durations are player-declared, rule-derived, location-derived, or scenario-derived.
- How conflicting duration sources are resolved.
- How sub-day values accumulate or expire.
- Whether action duration is allowed to differ by mode, difficulty, region, or story phase.

No implementation should choose values such as "conversation = 10 minutes" or "travel = 1 day" without an approved source of truth.

## 12. Implementation Files And Tests For The Next Task

Likely implementation files:

- `backend/server.py`
- `backend/replayability.py`
- `backend/simulation_clock.py`
- A new or existing deterministic action-result module, if one is approved

Likely focused tests:

- `backend/tests/test_simulation_clock.py`
- `backend/tests/test_simulation_clock_hardening.py`
- Replayability action-turn tests covering staged event production and consumption
- Server action tests covering invalid/rejected/uncommitted actions
- Concurrency tests covering lease conflict and CAS rollback
- Gateway/parser/player-payload tests proving client/LLM duration injection is ignored and clock internals stay hidden

## 13. Blocker

`D_ACTION_DURATION_AUTHORITY`

Chapter 33 cannot safely connect accepted action duration to simulation time until an engine-owned structured action-result contract defines elapsed simulation days and its deterministic source.
