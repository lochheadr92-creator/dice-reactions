# Memory Retrieval v0.1

**Canonical source:** `Source_of_Truth_v1.2.md:L19059-L19279`, Appendix A.5 `L20873-L20882`  
**Module:** `backend/memory_retrieval.py`  
**Branch:** `reimplementation/foundation-systems-v01`  
**Merged:** No | **Deployed:** No

## Conformance

- Probability components, working-memory sizes, pattern bonus, emotional bias: **canon constants**
- Seeded weighted sampling without replacement: **implemented**
- Shadow mode default: **does not alter prompts**

## Deliberate deltas

- Archive gate delegated to gravity metadata; no memory deletion

## Tests

`backend/tests/test_memory_retrieval.py`