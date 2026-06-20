# Utility AI v0.1 — Canon Dimension Contract

**Canonical source:** `Source_of_Truth_v1.2.md:L18805-L19055`, Appendix A.4 `L20863-L20871`  
**Modules:** `backend/utility_ai.py`, `backend/utility_dimensions.py`  
**Branch:** `reimplementation/foundation-systems-v01`  
**Merged:** No | **Deployed:** No | **Replacement:** Not authorised

## Dimension input map

| Dimension | Canon rule | Runtime source | Source class | On snapshot? | Blocker |
|-----------|------------|----------------|--------------|--------------|---------|
| Survival | 27.4.1 Δ×25 | `MOVE_SURVIVAL_DELTAS` catalog | DERIVED_CANONICAL_VALUE | via action_kind | — |
| Goal progression | 27.4.1 priority×movement | `utility_input_refs.goal_kind` + align table | AUTHORITATIVE_ENGINE_STATE | yes | MISSING_GOAL_KIND |
| Pressure relief | 27.4.1 reduction×100 | `utility_input_refs.highest_pressure_intensity` | DERIVED_CANONICAL_VALUE | yes | NOT_APPLICABLE if no pressure |
| Stress reduction | 27.4.1 reduction×stress | `utility_input_refs.stress_level` | AUTHORITATIVE_ENGINE_STATE | partial | MISSING_STRESS_LEVEL |
| Relationship impact | 27.4.1 Δ weighted | effect catalog + `relationship_importance` | CONFIRMED_STRUCTURED_OUTCOME | yes | MISSING_RELATIONSHIP_IMPORTANCE |
| Resource gain/loss | 27.4.1 SVU | scarcity + move SVU catalog | DERIVED_CANONICAL_VALUE | partial | MISSING_RESOURCE_SCARCITY |
| Memory avoidance | 27.4.1 context match | `utility_input_refs.memory_signatures` | AUTHORITATIVE_ENGINE_STATE | yes | — |

## Pipeline order (canon)

1. Candidate construction → 2. Feasibility → 3. Raw extraction → 4. Per-dimension formula → 5. Clamp → 6. Dynamic weights → 7. Weighted aggregate → 8. Personality (tie only) → 9. Seeded noise → 10. Tie window → 11. Tie resolution → 12. Canonical fallback order

## D_SEL status

`PLACEHOLDER_BLOCKED` — production agendas lack `stress_level`; harness oracle agrees on complete fixtures only.

## Tests

- `backend/tests/test_utility_dimensions.py`
- `backend/tests/foundation_acceptance/test_utility_oracle.py`