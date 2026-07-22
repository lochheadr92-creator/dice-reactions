# Foundation Promotion — Phase 2 (Foundation Completion)

**Branch:** `emergent`
**Status:** Promotion infrastructure landed; Utility defaults ON, while Actor
Resolution, Gravity, and Memory Retrieval default OFF.
**Scope:** Promote the canonical foundation subsystems from *shadow evaluation*
into the *authoritative* decision path, one explicit feature flag at a time,
with legacy fallback, fail-closed error handling, and comparison diagnostics.

This is an **architectural promotion**, not a gameplay feature. With every flag
off, the turn path is byte-identical to pre-promotion behaviour; the canonical
systems continue running as shadow diagnostics exactly as before.

---

## Evidence tags

| Tag | Meaning |
|-----|---------|
| **VERIFIED** | Directly confirmed by executing tests/code in this pass |
| **LIKELY** | Reviewed by reading code; not executed end-to-end here |
| **UNKNOWN** | Not verified |

---

## Subsystem implementation status

| Subsystem | Module | Present | Shadow (runs every turn) | Promoted (authoritative when flag ON) | Deprecated / legacy fallback |
|-----------|--------|:------:|:------:|:------:|------|
| Actor Resolution | `actor_resolution.py` | ✅ | ✅ (`foundation_integration`) | ✅ `ENABLE_CANONICAL_ACTOR_RESOLUTION` | `npc_world_moves.resolve_actor_tier` remains the fallback |
| Gravity Governance | `gravity_governance.py` | ✅ | ✅ | ✅ `ENABLE_CANONICAL_GRAVITY` (prompt-projection ordering of `npc_memory` only) | legacy recency heuristic in `memory._cap_prompt_registry` |
| Utility AI | `utility_ai.py` | ✅ | ✅ (comparison always) | ✅ `ENABLE_CANONICAL_UTILITY` (or legacy `ENABLE_UTILITY_AI_LIVE_SELECTION`) | heuristic `npc_world_moves.score_move` winner |
| Memory Retrieval | `memory_retrieval.py` | ✅ | ✅ (`shadow_mode=True`) | ⛔ **BLOCKED** — flag + diagnostics only; prompt injection gated OFF | legacy history-window replay retrieval |

The earlier `current-state.md` "Planned or not present" rows that described
Gravity Governance and Memory Retrieval as **absent** are **stale** — both
modules exist and execute every turn via `foundation_integration.evaluate_foundation_turn`
(called from `replayability.prepare_action_turn`). See the correction in
`current-state.md`.

---

## Feature flags

Defined in `ai_config.py`. Read-only helpers live in `foundation_promotion.py`.

| Flag | Env var | Default | Effect when ON |
|------|---------|:------:|----------------|
| Actor Resolution | `ENABLE_CANONICAL_ACTOR_RESOLUTION` | `false` | Canonical Actor Resolution is the authority over *who* acts each turn (veto + re-pick within the existing candidate set). |
| Gravity Governance | `ENABLE_CANONICAL_GRAVITY` | `false` | Canonical retention scoring ranks the `npc_memory` prompt projection (persisted state untouched). |
| Utility AI | `ENABLE_CANONICAL_UTILITY` | `true` | Authorised `utility_ai.select_action` winner drives the live NPC move (canonical name for the ADR-024 handoff). |
| Memory Retrieval | `ENABLE_CANONICAL_MEMORY_RETRIEVAL` | `false` | Surfaces canonical retrieval in diagnostics. **Does not** feed the prompt (see blocker). |

Non-env code constant:

| Constant | Value | Meaning |
|----------|-------|---------|
| `CANONICAL_MEMORY_RETRIEVAL_PROMPT_INJECTION_ACCEPTED` | `False` | Gate for Memory Retrieval prompt injection. Requires a code change **plus** separate shadow acceptance to grant. |

---

## Promotion contract

Every promotion helper in `foundation_promotion.py` is **pure** and **fail-closed**:

- **Flag OFF** → returns the legacy result unchanged; surrounding code path is
  byte-identical to pre-promotion behaviour.
- **Canonical error / missing data / unmapped entity** → returns the legacy
  result and records an error field in the diagnostic. The routing layer never
  raises out and never mutates inputs.
- **Deterministic** → no new RNG source, no I/O, no LLM. Identical inputs yield
  identical outputs and identical diagnostics.

### Comparison diagnostics (dev/admin only)

Recorded into turn `debug` (never player-visible), alongside the existing
Utility AI shadow diagnostics:

- `foundation_promotion_flags` — snapshot of active flags.
- Actor Resolution: `actor_resolution_enabled/applied/changed`, legacy vs
  canonical tier, `actor_resolution_reason`, authoritative actor.
- Memory Retrieval: `memory_retrieval_promotion` → enabled, injection-allowed,
  `memory_retrieval_blocker_code`, canonical selected ids, shadow mode.
- Utility AI: existing `utility_ai_shadow_*` agreement/divergence fields.

### Rollback

Set any flag back to its default (`false`). The next turn uses the legacy path.
No persisted state migration is involved, so rollback is immediate and total.

---

## Per-stage scope and known divergences

**Stage 1 — Actor Resolution.** Canonical tiers are derived Gravity → Actor
(retention feeds tiers), matching `foundation_integration`. The promotion applies
a **veto**: if canonical explicitly classifies the heuristic-chosen actor as
non-acting (`dormant`/`archived`/`unknown`), the highest-scoring canonically-acting
candidate is chosen instead; if none, the move is suppressed. An actor unmapped
in the canonical registry is **not** vetoed (fail-open on mapping gaps). Known
divergence (from `foundation-canon-deltas` `D_GRACE`): demotion grace uses the
`turn × 60` simulation-minute proxy, not a real simulation clock.

**Stage 2 — Gravity Governance.** Governs **only** the `npc_memory` prompt
projection ordering, which is the sole capped registry whose items
(actors) Gravity models. Persisted `rolling_state` is never touched and the
retained item count (the caller's cap) is unchanged — **State Is Truth** and the
context-budget contract are preserved. The per-row Gravity inputs
(`_GRAVITY_MAJOR`/`_GRAVITY_BASE`/connectivity saturation) are **DESIGNED
EXTENSIONS** (canon Ch 14/26 is non-numerical), consistent with the `stress.py`
constants convention. Object/room registries have no Gravity model and always
use the legacy heuristic.

**Stage 3 — Utility AI.** Reuses the existing ADR-024 `living_cast_shadow`
handoff. `ENABLE_CANONICAL_UTILITY` is the canonical name; the legacy
`ENABLE_UTILITY_AI_LIVE_SELECTION` remains an accepted alias (either engages the
live winner). Shadow comparison and fail-closed authorisation are unchanged.

**Stage 4 — Memory Retrieval (BLOCKED).** `foundation-canon-deltas`
`D_MEMORY_RETRIEVAL_SHADOW` requires `SEPARATE_SHADOW_ACCEPTANCE_REQUIRED` before
canonical retrieval may feed prompt construction. This phase adds the flag and
comparison diagnostics but keeps prompt injection gated OFF behind
`CANONICAL_MEMORY_RETRIEVAL_PROMPT_INJECTION_ACCEPTED = False`. Even with the
flag ON, `evaluate_memory_retrieval` runs `shadow_mode=True` and the prompt is
unaffected. **Turning Memory Retrieval authoritative is the remaining blocker
before this promotion is complete.**

---

## Acceptance checklist

| Criterion | State |
|-----------|-------|
| Actor Resolution authoritative behind flag | ✅ (default OFF) |
| Gravity Governance authoritative behind flag | ✅ (prompt projection; default OFF) |
| Utility AI authoritative behind flag | ✅ (default ON; deterministic routing verified, provider-backed acceptance pending) |
| Memory Retrieval authoritative | ⛔ blocked by `SEPARATE_SHADOW_ACCEPTANCE_REQUIRED` |
| Legacy implementations available behind flags | ✅ |
| Replay deterministic | ✅ (pure, no new RNG) |
| Prompt budget stable | ✅ (cap count unchanged) |
| Prompt leakage impossible | ✅ (memory injection gated OFF; diagnostics dev-only) |
| Diagnostics expose canonical vs legacy | ✅ |
| Existing regression suites green (OFF path) | VERIFIED offline (see report) |

---

## Files

- `backend/ai_config.py` — flags + acceptance constant + `get_runtime_config`.
- `backend/foundation_promotion.py` — pure routing/comparison helpers (NEW).
- `backend/replayability.py` — Stage 1 veto + Stage 3 flag wiring.
- `backend/memory.py` — Stage 2 `npc_memory` gravity ordering branch.
- `backend/foundation_integration.py` — Stage 4 diagnostics + injection gate.
- `backend/tests/test_foundation_promotion.py` — deterministic promotion tests (NEW).
