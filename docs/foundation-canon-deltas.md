# Foundation Canon Deltas — Executable Ledger v1.0.0

**Harness:** `backend/tests/foundation_acceptance/` (test-owned, not production policy)  
**Ledger hash:** computed at test time from `delta_ledger.ledger_hash()`  
**Branch:** `reimplementation/foundation-systems-v01`  
**Not merged. Not deployed. No production replacement authorised.**

## Executable delta registry

| Delta ID | System | Facet | Status | Canon ref | Replacement |
|----------|--------|-------|--------|-----------|-------------|
| `D_SEL` | utility_ai | action_kind | PLACEHOLDER_BLOCKED | Ch 27.5 L18949–L18956 | Blocked until oracle + inputs complete |
| `D_UTILITY_PLACEHOLDER` | utility_ai | dimension_score | PLACEHOLDER_BLOCKED | Ch 27.4.1 L18910–L18927 | Diagnostic only |
| `D_TIER_ASSIGNMENT` | actor_resolution | tier | NOT_MACHINE_CHECKABLE | Ch 25.8 L18521–L18530 | Missing Context Gravity |
| `D_ACTING_ELIGIBILITY` | actor_resolution | eligibility | ACTIVE | Ch 25.3 | Witness required |
| `D_TIER_PROCESSING_CADENCE` | actor_resolution | processing_eligibility | ACTIVE | Ch 27.6 L18966–L18974 | Witness required |
| `D_GRACE` | actor_resolution | tier | PLACEHOLDER_BLOCKED | Ch 25.6 L18490–L18495 | `BLOCKED_BY_MISSING_AUTHORITATIVE_INPUT — SIMULATION_TIME` |
| `D_MEMORY_RETRIEVAL_SHADOW` | memory_retrieval | retrieval_membership | NOT_MACHINE_CHECKABLE | Ch 28.3 L19118–L19133 | `SEPARATE_SHADOW_ACCEPTANCE_REQUIRED` |

## Documented divergences (descriptive)

| System | Canon requirement | v0.1 behaviour | Reason | Reconciliation path |
|--------|-------------------|----------------|--------|---------------------|
| Actor Resolution | Promotion from spatial/event triggers | Retention+gravity signals; no Ch 20 Context Gravity | Context Gravity not computed | Compute G_peak per Ch 20.17 |
| Actor Resolution | Grace in simulation minutes | Explicit-time fixtures only; turn×60 proxy in production | No simulation clock | Add `simulation_minutes` authority |
| Utility AI | Full dimension inputs | Canon formulas; stress/SVU blocked without inputs | Missing authoritative fields | Extend utility_input_refs |
| Utility AI | Replace `score_move` | Provisional path retained | Harness not PASS_FOR_REPLACEMENT | Frozen corpus + coverage |
| Memory Retrieval | Prompt inclusion | Shadow only | Increment scope | Separate shadow acceptance |
| Numeric contract | IEEE rounding | Full float until clamp | Canon silent | Approve rounding table |

## Harness verdict

`HARNESS_STRUCTURE_READY` — corpus execution deferred.

## Utility verdict

`UTILITY_INPUTS_INCOMPLETE — D_SEL_BLOCKED` for production agendas missing `stress_level`.  
`UTILITY_CANON_CONTRACT_COMPLETE` applies only to fixtures with complete authoritative inputs (see `utility_oracle_complete_v1`).