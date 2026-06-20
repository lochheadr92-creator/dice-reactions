# Foundation Systems v0.1 — Integration

**Branch:** `reimplementation/foundation-systems-v01`  
**Base SHA:** `4dadb3feb3737b28a4e5fbb1ef71aa0d56b365a5`  
**Merged:** No | **Deployed:** No | **Live tests:** Not run

## Architecture

1. `FoundationTurnSnapshot` (`foundation_snapshot.py`) — frozen pre-action input
2. `evaluate_foundation_turn` (`foundation_integration.py`) — Actor → Gravity → Utility → Retrieval
3. `replayability.prepare_action_turn` — stages `foundation_prepared_v1` on working copy; diagnostics only to bounded debug
4. `engine_projection.py` — no player/prompt projection for foundation internals

## Determinism

- `engine_determinism.py` — canonical JSON, SHA-256 hashes, counter-based RNG v1
- Replay invariant: identical snapshot + seed + subsystem versions → byte-equivalent `prepared_bytes`

## Shadow mode

Memory retrieval runs in shadow mode unless `developer_mode` enables telemetry comparison. NPC move selection remains provisional.

## Persistence

- No new Mongo collections
- No retrieval/utility sidecars
- `foundation_prepared_v1` nested in `replayability_state` transaction only

## Prompt freeze

`server.py` model-facing directive construction unchanged in this increment.

## Acceptance harness

`backend/tests/foundation_acceptance/` — `HARNESS_STRUCTURE_READY`. Executable ledger v1.0.0. No production replacement.

## Utility dimension contract

`backend/utility_dimensions.py` — Ch 27.4.1 formulas; fail-closed on missing inputs. D_SEL `PLACEHOLDER_BLOCKED` for production agendas.

## Test status

598 non-live tests passed (34 live deselected).

## Next increment

- Provisional equivalence report automation
- Canon replacement flag for actor tier + utility selection
- Simulation clock for grace periods
- Gravity destructive migration behind explicit flag