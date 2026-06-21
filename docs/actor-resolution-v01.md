# Actor Resolution v0.1

**Canonical source:** `Source_of_Truth_v1.2.md:L18252-L18588`, Appendix A.3 `L20854-L20861`  
**Module:** `backend/actor_resolution.py`  
**Branch:** `reimplementation/foundation-systems-v01`  
**Merged:** No | **Deployed:** No

## Conformance

- Tier ceilings, retention/gravity eligibility thresholds, cadence table: **canon constants**
- Promotion trigger evaluation from spatial/events: **not implemented** (delta)
- Grace periods: **simulation-minute proxy** (delta)

## Deliberate deltas

See `foundation-canon-deltas.md`.

## Known limitations

- `unknown` tier for ungrounded actors preserved from provisional doctrine
- Does not call model or mutate relationships

## Tests

`backend/tests/test_actor_resolution.py`