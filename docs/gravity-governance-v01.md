# Gravity Governance v0.1

**Canonical source:** `Source_of_Truth_v1.2.md:L18592-L18801`, Appendix A.2 `L20841-L20852`  
**Module:** `backend/gravity_governance.py`  
**Branch:** `reimplementation/foundation-systems-v01`  
**Merged:** No | **Deployed:** No

## Conformance

- Retention formula, bands, player-relevance bonus semantics: **canon formula**
- Protected categories (unresolved consequence, active pressure, secrets): **enforced in metadata**
- Budget overflow: **deterministic `GravityBudgetOverflow`**

## Deliberate deltas

- No destructive archive/compress migration on live state (v0.1 shadow metadata only)

## Tests

`backend/tests/test_gravity_governance.py`