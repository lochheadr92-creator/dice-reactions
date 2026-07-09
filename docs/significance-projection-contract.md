# Significance Projection Contract

**Status:** contract only. Significance is not implemented, wired, cached, or
persisted by this document.

## Purpose

Significance is a future read-only projection for current contextual importance.
It answers: "Which recent causal changes matter right now, to whom, and why?"

It must consume causal evidence from `backend/causal_visibility.py`; it must not
become a new authority over pressure, relationships, memory, Gravity, Utility AI,
prompts, or narrative output.

## Gravity vs Significance

Gravity is long-term retention and relevance weight. It decides whether
engine-owned items remain active, compressed, archived, or protected for
retention and context-budget purposes.

Significance is current contextual importance. It may rank or band recent
effects for a specific actor, location, faction, UI view, or future decision
surface. It does not determine retention, archival, deletion, canonical truth,
or whether an event happened.

## Allowed Inputs

A Significance evaluator may consume only bounded, sanitized causal visibility
projection data plus explicit evaluation context.

Allowed causal visibility fields:

- `schema_version`
- `entries[].entry_id`
- `entries[].turn`
- `entries[].source_system`
- `entries[].source_receipt_id`
- `entries[].source_ids`
- `entries[].affected_entity_type`
- `entries[].affected_entity_id`
- `entries[].effect_category`
- `entries[].effect_type`
- `entries[].before`
- `entries[].after`
- `entries[].delta`
- `entries[].reason`
- `entries[].metadata`

Allowed evaluation context:

- `run_seed`
- `turn_sequence`
- actor, location, faction, goal, situation, investigation, information, memory,
  or pressure IDs already present in engine-authoritative state
- caller-owned limits such as max entries, max source references, and requested
  scope

Forbidden inputs:

- generated prose, rendered text, model output, prompts, choices, debug blobs, or
  raw provider responses
- direct mutation targets such as live `rolling_state`, live `pressure_graph`,
  relationship vectors, memory rows, or persistence handles
- wall-clock time, random numbers, unordered set iteration, external network
  data, or process-global counters

## Output Shape

A future implementation should return a new bounded projection, for example
`significance_projection_v1`, with this minimum shape:

```json
{
  "schema_version": 1,
  "source_visibility_schema_version": 1,
  "turn": 0,
  "scope": {
    "actor_id": "",
    "location_id": "",
    "faction_id": ""
  },
  "entries": [
    {
      "entry_id": "",
      "source_causal_entry_ids": [],
      "source_ids": [],
      "affected_entity_type": "",
      "affected_entity_id": "",
      "effect_category": "",
      "significance_band": "medium",
      "significance_score": 0.0,
      "reason_codes": [],
      "metadata": {}
    }
  ],
  "entry_count": 0,
  "max_entries": 0,
  "truncated": false
}
```

Allowed outputs:

- bounded per-entity or per-effect importance score, clamped to `0.0..1.0`
- bounded band such as `none`, `low`, `medium`, `high`, or `critical`
- source causal entry IDs and source IDs used as evidence
- deterministic reason codes, not prose-generated explanations
- bounded metadata copied only from allowed causal visibility metadata or from
  explicit evaluation context

Forbidden outputs:

- new facts, events, pressure nodes, relationship deltas, memories, goals,
  ambitions, or narrative claims
- prompt text or model-facing instructions
- persistent state patches
- unbounded explanations, raw debug payloads, probabilities from memory
  retrieval, or generated story text

## Derived, Cached, Persisted

Significance values are derived.

They may be recomputed from the same causal visibility projection and context.
They may be cached only as disposable diagnostics inside the caller's prepared
bundle, with source schema/version/hash metadata sufficient to invalidate the
cache. They must not be persisted as canonical truth or used as evidence that a
world event happened.

## Evaluation Order

To prevent feedback loops, Significance must run after the authoritative systems
whose receipts it reads.

Required order:

1. Engine systems mutate authoritative state and emit receipts.
2. `project_causal_visibility(...)` derives bounded causal visibility.
3. Future Significance derives bounded importance from causal visibility.
4. Downstream consumers may read Significance as advisory projection only.

Same-turn feedback is forbidden. Significance must not write back into Pressure,
Gravity, relationships, memory retrieval, Utility AI candidate generation, NPC
ambitions, situations, goals, investigations, world events, prompts, or
`rolling_state` in the same evaluation pass.

If a later system needs Significance-informed behaviour, it must consume a
completed projection at a defined seam and then produce its own structured,
engine-authoritative event/receipt through that system's normal authority path.

## Future Consumers

Permitted future consumers:

- UI consequence feedback, if displayed as an explanation of existing causal
  evidence rather than as new truth
- developer diagnostics and replay inspection
- future NPC ambition or Utility AI evaluators as read-only input, provided they
  remain deterministic and do not mutate Significance
- future pressure feedback, only through a separate engine-owned candidate seam
  with explicit receipts and duplicate suppression
- retrieval or memory diagnostics, only as a shadow/projection input unless a
  later acceptance gate explicitly promotes it

Systems Significance must not mutate:

- `pressure_graph` nodes, threshold crossings, and evolution receipts
- relationship vectors, relationship provenance, and relationship receipts
- Gravity governance state, retention bands, and scheduling receipts
- memory rows, retrieval traces, and selected memory IDs
- Utility AI candidates or selected actions
- NPC ambitions, situations, goals, investigations, world events, and world
  state consumers
- prompts, model routing, narrative rendering, and frontend state

## Replay Safety

A future implementation must be pure and deterministic:

- identical causal visibility input plus identical evaluation context must
  produce byte-equivalent output
- ordering must be stable by turn, category, affected entity, source causal
  entry ID, and source ID
- scores and bands must be clamped and finite
- all output lists and metadata must have fixed caps
- no wall-clock time, process randomness, network data, model output, or
  persistence reads outside the supplied inputs
- malformed entries must fail closed by being ignored or downgraded, not by
  widening authority

## Bounded Metadata

Allowed metadata is limited to small scalar or short-list values needed to
explain ranking:

- pressure kind, source kind, qualifier
- affected actor, faction, and location IDs
- relationship state transition labels
- memory selected-count diagnostics
- evaluation scope IDs
- reason codes from the Significance evaluator

Metadata must not include narrative text, prompt fragments, raw debug payloads,
unbounded probabilities, provider output, full memory summaries, or raw
relationship vectors.

## Minimum Future Tests

A future Significance implementation must add focused tests proving:

- it consumes only allowed causal visibility fields
- it emits the contracted shape and caps entries, source IDs, metadata, and text
- identical inputs produce identical output
- input order does not affect output
- malformed or narrative-only fields are ignored or sanitized
- output does not mutate replayability state, rolling state, Pressure, Gravity,
  relationships, memory retrieval, Utility AI, prompts, or frontend state
- default/canonical-off behaviour leaves existing runtime fingerprints unchanged
- same-turn feedback loops are impossible at the wired seam
- Gravity and Significance remain distinct: Gravity retention bands are not
  derived from Significance, and Significance scores are not retention bands
