# Foundation Canon Deltas — v0.1

| System | Canon requirement | v0.1 behaviour | Reason | Reconciliation path |
|--------|-------------------|----------------|--------|---------------------|
| Actor Resolution | Promotion/demotion from spatial/event triggers (Ch 25.3) | Tier from retention+gravity signals on registry rows | No simulation clock / spatial graph in checkpoint base | Wire heartbeat + location graph in next increment |
| Actor Resolution | Grace periods in simulation minutes | `turn_sequence × 60` simulation-minute proxy | Canon clock exists; runtime lacks continuous sim clock | Add `simulation_minutes` to session state |
| Actor Resolution | Replace provisional `resolve_actor_tier` | Provisional path retained; foundation runs in parallel | Equivalence + canon gates not yet approved for replacement | Enable replacement flag after gate report |
| Gravity Governance | Periodic recalculation by heartbeat tier | On-demand per turn snapshot evaluation | Heartbeat not implemented | Hook to macro/regional ticks |
| Gravity Governance | Destructive compress/archive migration | Metadata-only dispositions; no state migration | Directive: no destructive migration in v0.1 | Migration increment with event compression |
| Utility AI | Full dimension scores from state | Heuristic dimension scores from agenda/relationship context | Domain feasibility layer incomplete | Domain modules supply dimension scores |
| Utility AI | Replace `score_move` | Provisional scorer still selects NPC moves | Replacement gated | Shadow compare + flip flag |
| Memory Retrieval | Prompt inclusion of retrieved memories | Shadow mode default; prompt unchanged | Directive: retrieval begins shadow-only | Enable `developer_mode` shadow telemetry only |
| Memory Retrieval | Denominator normalisation over all memories | Weighted sampling pool uses positive-weight candidates | Equivalent selection intent; pool excludes zero-weight | Add normalisation audit test vs canon example |
| Numeric contract | Rounding at boundaries | Full float precision until clamp | Canon silent on IEEE rounding | Approve `NUMERIC_CONTRACT_VERSION` rounding table |

**Overall classification:** DOCUMENTED DIVERGENCE FROM CANON for runtime integration; module formulas/constants match Appendix A where implemented.