# Foundation Acceptance Harness v1

**Package:** `backend/tests/foundation_acceptance/`  
**Branch:** `reimplementation/foundation-systems-v01`  
**Base:** `9da1ae2`  
**Verdict:** `HARNESS_STRUCTURE_READY`  
**Replacement:** **Not authorised**

## Components

| Module | Role |
|--------|------|
| `models.py` | `DeltaEntry`, `ComparisonInput`, classification types |
| `delta_ledger.py` | Versioned executable ledger + hash |
| `comparison.py` | Divergence collection + classifier |
| `coverage.py` | Applicability / witness tracking |
| `artifact.py` | Byte-stable artifact serializer |
| `adapters.py` | Corpus source interfaces (no DB) |
| `utility_oracle.py` | Independent Ch 27 oracle (no production imports) |

## Corpus sources (interfaces only)

- `SyntheticFixtureSource`
- `ExistingTestFixtureSource`
- `LocalTurnSnapshotSource`
- `LocalSessionSnapshotSource`
- `OptionalPersistedDecisionSource`

No `DbEventsSource`. No live database queries.

## Artifact fields

`schema_version`, `harness_version`, `ledger_version`, `ledger_hash`, `corpus_version`, `corpus_hash`, `commit_sha`, `comparison_count`, `bucket_counts`, `coverage`, `records`

Excluded: timestamps, paths, secrets, narrative, unordered maps.

## Tests

`python -m pytest backend/tests/foundation_acceptance -q`