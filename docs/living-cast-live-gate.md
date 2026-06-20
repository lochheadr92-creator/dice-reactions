# Living Cast Live Gate — Seeded Scenario & Acceptance

Deterministic preflight for early turn-2 NPC move proof. **No live provider calls in preflight.**

## Seeded scenario

| Field | Value |
|-------|-------|
| Scenario ID | `living-cast-proof` |
| Engine run seed | `lc-proof-aaaa-aaaa-aaaa-aaaaaaaaaaaa` |
| Canonical NPC | Marlene Cho (`proof_canonical_npc_id()` in `living_cast_seeded_scenario.py`) |
| Intended move | `gather` → resource pressure `pressure-resource-lcproof01` |
| Earliest eligible turn | **2** (turn 1 opening does not call `prepare_action_turn`) |
| Effect | `pressure_magnitude` **decrease** (−3) |

**Fixture guarantees:**

- One living NPC, stable canonical ID, single agenda (`goal_kind=secure_resources`)
- Hero tier, `trust=0` (blocks competing `conceal` which needs trust > 0)
- `last_move_turn=-10` (avoids false recency penalty on first move at turn 2)
- Injected resource pressure node; no environmental/location competitors
- **No relationship-dependent scoring** for `gather`

**Neutral turn-1 actions** (do not manipulate selection inputs):

- `I wait and listen.`
- `I look around the room.`
- `I stay where I am and observe.`

## Preflight

```bash
cd backend
python -m pytest tests/test_living_cast_seeded_preflight.py -q
```

`run_move_preflight()` records: canonical IDs, candidate score table, margin, drift checks, effect direction, `selection_inputs_hash`.

## Move-selection deviation taxonomy

| Class | Meaning |
|-------|---------|
| `PREFLIGHT_ERROR` | Harness/fixture defect |
| `EXPECTED_ENGINE_DRIFT` | Documented deterministic drift changed winner (fixture design) |
| `UNEXPECTED_ENGINE_DRIFT` | Undocumented engine mutation |
| `PROSE_DERIVED_STATE_PERTURBATION` | Doctrine P0 — prose/text altered authoritative inputs |
| `SELECTION_IMPLEMENTATION_DEFECT` | Same inputs, different winner |
| `UNVERIFIED` | Insufficient state lineage |

Do **not** add a production regression for `EXPECTED_ENGINE_DRIFT` (fixture design failure).

## Narrative surfacing

| Class | Gate result |
|-------|-------------|
| Correctly narrated | PASS |
| Weakly / indirectly narrated | PASS WITH WARNINGS |
| Omitted (state correct, no contradiction) | PASS WITH WARNINGS — not statistically validated |
| Contradicted (wrong actor/target/effect) | **FAIL** |

## Live acceptance (n=1)

**PASS:** `1/1 live run clean — commit gate passed, directive adherence not statistically validated`

**PASS WITH WARNINGS:** engine state correct, move committed, no contradiction, no leaks

**FAIL:** contradiction, leak, persistence mismatch, guaranteed move not committed (production defect), untriaged prose perturbation

## Sampling provenance

| Parameter | Source | Tag |
|-----------|--------|-----|
| model | `ai_config.DEFAULT_MODEL` | `PINNED_IN_CONFIG` |
| temperature | `ai_service.DEFAULT_TEMPERATURE` | `PINNED_IN_CONFIG` |
| max_tokens | `ai_service.DEFAULT_MAX_TOKENS` | `PINNED_IN_CONFIG` |
| timeout | `ai_config.PROVIDER_TIMEOUT` | `PINNED_IN_CONFIG` |
| max_retries | `ai_config.MAX_RETRIES` | `PINNED_IN_CONFIG` |
| fallback_models | `ai_config.FALLBACK_MODELS` | `PINNED_IN_CONFIG` |
| top_p | not in request payload | `INHERITED_PROVIDER_DEFAULT` |
| provider_seed | not sent | `UNVERIFIED` |

**Engine run seed ≠ model sampling seed.** Engine seed pins replayability only; model output is not fully reproducible at the sampling layer when `top_p` is provider-default.

## Unanticipated P0 stop rule

If Stage 1 finds an unanticipated P0 (unsafe lease, second pressure store, narrative mutating authoritative relationships, rollback failure, duplicate provider execution, etc.):

1. Stop before live run  
2. Record lineage  
3. Classify defect  
4. Minimal fix + failing deterministic regression  
5. Full non-live suite  
6. Re-audit lineage  

## Forged-output pressure test

Design **after** Stage 1 opens every model-writable pressure path. Mark `UNVERIFIED — source not read` for any path not traced. See `story-engine.md` bounded-state section for authoritative pressure ownership.

## Manifest

`living_cast_seeded_scenario.live_gate_manifest()` — engine seed, preflight record, sampling table, taxonomy enums.