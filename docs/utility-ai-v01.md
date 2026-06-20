# Utility AI v0.1

**Canonical source:** `Source_of_Truth_v1.2.md:L18805-L19055`, Appendix A.4 `L20863-L20871`  
**Module:** `backend/utility_ai.py`  
**Branch:** `reimplementation/foundation-systems-v01`  
**Merged:** No | **Deployed:** No

## Conformance

- Weighted average utility, base weights, whim noise ±0.5, tie window 0.01: **canon**
- Seeded RNG via `engine_determinism`: **replay-stable**

## Deliberate deltas

- Domain dimension scores are heuristic; `npc_world_moves.score_move` still owns selection

## Tests

`backend/tests/test_utility_ai.py`