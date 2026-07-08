"""
Stage 6C-1 — Pressure Genesis: deterministic candidate derivation + commit.

Architecture: docs/stage-6c-pressure-genesis-brief.md. Motivating problem:
burn-in data shows the world reaching total equilibrium (no active
pressures/situations/goals) a few dozen turns in, because nothing re-seeds
pressure roots without player input. Genesis derives new pressure roots from
EXISTING canonical engine state -- never from narrative, prose, prompt text,
or LLM output -- and commits them through pressure_graph.upsert_pressure_node,
which remains the single canonical authority for pressure node identity,
dedup, capacity, and subsequent evolution (escalation/decay/resolution).
Genesis's job ends at "does this canonical signal deserve a pressure root
to exist" -- it never touches situations, goals, or events directly, and it
never re-derives a value pressure_graph itself already owns (trend movement,
threshold crossings, spawned events).

Signal sources (6C-1 scope):
  - blocked goals lacking supporting pressure (state["goals"])
  - open/active/stalled investigations (state["investigations"])
  - actor stress classified OVERLOADED (rolling_state["actor_stress"], via
    stress.evaluate_stress_behaviour -- the same read-only classifier Utility
    AI uses, never re-implemented here)

World events are deliberately excluded: world_state_consumers already owns
converting world-event-engine output into pressure
(pressure_graph.apply_world_event_engine_events); Genesis must not open a
second, competing write path over the same signal (single source of truth).
Information/reputation signals are deferred to keep this rule table small
and reviewable -- a natural, separately-reviewed follow-on.

Flag: ai_config.ENABLE_PRESSURE_GENESIS, default OFF. With the flag OFF,
evolve_pressure_genesis returns immediately and does not read or write
`state` at all -- the flag-off byte-identity fingerprint gate
(backend/tools/simulate_world.py) is the acceptance test for this invariant,
not a unit test mock.

Determinism: candidate ordering, magnitude, node ids, and trend are pure
functions of (run_seed, turn_number, existing canonical state). No
wall-clock, no random module, no unordered dict/set iteration reaches an
output value. Candidates are sorted by (-magnitude, source_signal,
source_id) before the per-turn cap is applied, so the same input always
produces the same created/deduped/linked/capped/skipped outcome for the
same candidates in the same order.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Mapping, Optional

import ai_config
import pressure_graph
import stress

GENESIS_VERSION = 1

# Hard per-turn ceiling on NEW pressure creation/reinforcement attempts. This
# is deliberately independent of pressure_graph.MAX_ACTIVE_NODES/MAX_TOTAL_NODES
# (which pressure_graph already enforces on every upsert) -- it exists so
# Genesis itself cannot flood the graph's own capacity logic with too many
# candidates in a single turn, which would churn out organically-created nodes.
MAX_GENESIS_CANDIDATES_PER_TURN = 2

# Bounds the receipts kept in state["pressure_genesis"]["receipts"] so the
# block itself can never grow unbounded across a long run.
MAX_GENESIS_RECEIPTS_STORED = 40

GENESIS_INVESTIGATION_MIN_PRIORITY = 4
GENESIS_INVESTIGATION_LIVE_STATUSES = ("open", "active", "stalled")
GENESIS_GOAL_MIN_PRIORITY = 4
GENESIS_STRESS_QUALIFYING_BANDS = ("OVERLOADED",)

RECEIPT_TYPES = (
    "genesis_created",
    "genesis_deduped",
    "genesis_linked",
    "genesis_capped",
    "genesis_skipped",
)


def genesis_enabled() -> bool:
    """Call-time flag read (matches the foundation_promotion reader pattern)."""
    return bool(ai_config.ENABLE_PRESSURE_GENESIS)


def empty_genesis_state() -> Dict[str, Any]:
    """State-block shape. `receipts` is bounded by MAX_GENESIS_RECEIPTS_STORED."""
    return {
        "version": GENESIS_VERSION,
        "receipts": [],
    }


def _bounded_unique(values: Any, limit: int) -> List[str]:
    out: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _receipt_id(receipt_type: str, *, turn_number: int, source_signal: str, source_id: str) -> str:
    digest = hashlib.sha256(
        f"{receipt_type}:{turn_number}:{source_signal}:{source_id}".encode("utf-8")
    ).hexdigest()
    return f"pressure-genesis-receipt-{digest[:12]}"


def _make_receipt(
    receipt_type: str,
    *,
    turn_number: int,
    source_signal: str,
    source_id: str,
    node_id: str = "",
    linked_node_id: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    receipt: Dict[str, Any] = {
        "receipt_id": _receipt_id(
            receipt_type,
            turn_number=turn_number,
            source_signal=source_signal,
            source_id=source_id,
        ),
        "receipt_type": receipt_type,
        "turn": turn_number,
        "source_signal": source_signal,
        "source_id": source_id,
    }
    if node_id:
        receipt["node_id"] = node_id
    if linked_node_id:
        receipt["linked_node_id"] = linked_node_id
    if reason:
        receipt["reason"] = reason
    return receipt


def _investigation_candidates(investigations: Any) -> List[Dict[str, Any]]:
    """Open/active/stalled investigations lacking a genesis pressure node yet."""
    out: List[Dict[str, Any]] = []
    for row in investigations or []:
        if not isinstance(row, Mapping):
            continue
        status = str(row.get("status") or "").strip().lower()
        if status not in GENESIS_INVESTIGATION_LIVE_STATUSES:
            continue
        source_id = str(row.get("investigation_id") or "").strip()
        if not source_id:
            continue
        priority = _as_int(row.get("priority"), 0)
        actor_ids = _bounded_unique(
            list(row.get("assigned_actor_ids") or []) + list(row.get("suspect_ids") or []),
            pressure_graph.MAX_REF_IDS,
        )
        qualifies = priority >= GENESIS_INVESTIGATION_MIN_PRIORITY
        out.append(
            {
                "source_signal": "investigation",
                "source_id": source_id,
                "qualifies": qualifies,
                "skip_reason": "" if qualifies else "below_priority_threshold",
                "kind": "suspicion",
                "scope": "personal" if actor_ids else "local",
                "magnitude": 20 + min(max(priority, 0), 10) * 3,
                "actor_ids": actor_ids,
                "location_ids": [],
                "faction_ids": [],
                "label": "unresolved investigation",
            }
        )
    return out


def _goal_candidates(goals: Any) -> List[Dict[str, Any]]:
    """Blocked goals with no supporting pressure yet -- the field goal_engine
    already carries (`supporting_pressure_ids`) for exactly this linkage."""
    out: List[Dict[str, Any]] = []
    for row in goals or []:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("status") or "").strip().lower() != "blocked":
            continue
        source_id = str(row.get("goal_id") or "").strip()
        if not source_id:
            continue
        priority = _as_int(row.get("priority"), 0)
        owner_type = str(row.get("owner_type") or "world")
        owner_id = str(row.get("owner_id") or "")
        actor_ids = _bounded_unique(
            ([owner_id] if owner_type == "npc" else []) + list(row.get("target_actor_ids") or []),
            pressure_graph.MAX_REF_IDS,
        )
        faction_ids = _bounded_unique(
            [owner_id] if owner_type == "faction" else [], pressure_graph.MAX_REF_IDS
        )
        location_ids = _bounded_unique(list(row.get("target_location_ids") or []), pressure_graph.MAX_REF_IDS)

        if row.get("supporting_pressure_ids"):
            qualifies, skip_reason = False, "already_supported"
        elif priority < GENESIS_GOAL_MIN_PRIORITY:
            qualifies, skip_reason = False, "below_priority_threshold"
        else:
            qualifies, skip_reason = True, ""

        out.append(
            {
                "source_signal": "goal",
                "source_id": source_id,
                "qualifies": qualifies,
                "skip_reason": skip_reason,
                "kind": "social_tension",
                "scope": (
                    "faction" if owner_type == "faction" else "personal" if owner_type == "npc" else "local"
                ),
                "magnitude": 20 + min(max(priority, 0), 10) * 3,
                "actor_ids": actor_ids,
                "location_ids": location_ids,
                "faction_ids": faction_ids,
                "label": "blocked goal",
            }
        )
    return out


def _stress_candidates(actor_stress: Any) -> List[Dict[str, Any]]:
    """Actors whose current stress classifies OVERLOADED (stress.evaluate_stress_behaviour
    is the same read-only classifier Utility AI already uses -- not re-derived here)."""
    out: List[Dict[str, Any]] = []
    if not isinstance(actor_stress, Mapping):
        return out
    for actor_id in sorted(str(k) for k in actor_stress.keys()):
        row = actor_stress.get(actor_id)
        if not isinstance(row, Mapping):
            continue
        behaviour = stress.evaluate_stress_behaviour(row.get("stress_level"))
        if not behaviour.get("valid"):
            continue
        band = behaviour.get("band")
        qualifies = band in GENESIS_STRESS_QUALIFYING_BANDS
        level = float(behaviour.get("stress_level") or 0.0)
        out.append(
            {
                "source_signal": "stress",
                "source_id": actor_id,
                "qualifies": qualifies,
                "skip_reason": "" if qualifies else "below_band_threshold",
                "kind": "injury_or_fatigue",
                "scope": "personal",
                "magnitude": int(max(0.0, min(100.0, level)) * 0.5),
                "actor_ids": [actor_id],
                "location_ids": [],
                "faction_ids": [],
                "label": "overloaded actor stress",
            }
        )
    return out


def _find_link_target(pg: Mapping[str, Any], candidate_node: Mapping[str, Any]) -> Optional[str]:
    """Deterministically find one existing active node sharing a structural ref
    (actor/location/faction) with the candidate -- mirrors pressure_graph's own
    structured-link convention (_create_one_structured_link), applied only to
    genesis's own new/reinforced node so linking stays bounded and explicit."""
    node_id = str(candidate_node.get("id") or "")
    c_actors = set(candidate_node.get("actor_ids") or [])
    c_locations = set(candidate_node.get("location_ids") or [])
    c_factions = set(candidate_node.get("faction_ids") or [])
    if not (c_actors or c_locations or c_factions):
        return None
    rows = [row for row in (pg.get("nodes") or []) if isinstance(row, Mapping)]
    for row in sorted(rows, key=lambda n: str(n.get("id") or "")):
        if row.get("id") == node_id or row.get("status") != "active":
            continue
        if (
            (c_actors & set(row.get("actor_ids") or []))
            or (c_locations & set(row.get("location_ids") or []))
            or (c_factions & set(row.get("faction_ids") or []))
        ):
            return str(row.get("id") or "")
    return None


def evolve_pressure_genesis(
    state: Dict[str, Any],
    rolling_state: Mapping[str, Any],
    turn_number: int,
    *,
    run_seed: str = "",
) -> Dict[str, Any]:
    """Flag-gated. OFF: returns immediately, `state` is not read or written
    (byte-identity gate). ON: derives bounded pressure candidates from
    existing canonical signals, commits them through
    pressure_graph.upsert_pressure_node (the only writer of pressure
    identity/dedup/capacity), and returns receipts + diagnostics for the
    caller to fold into transition_receipts/diagnostics exactly like every
    other engine in prepare_action_turn.
    """
    if not genesis_enabled():
        return {"receipts": [], "diagnostics": {}}

    genesis_block = state.setdefault("pressure_genesis", empty_genesis_state())
    pg = state.get("pressure_graph")
    if not isinstance(pg, dict):
        return {"receipts": [], "diagnostics": {}}

    seed = run_seed or str(state.get("run_seed") or "pressure-genesis")
    actor_stress = rolling_state.get("actor_stress") if isinstance(rolling_state, Mapping) else None

    candidates: List[Dict[str, Any]] = []
    candidates.extend(_investigation_candidates(state.get("investigations")))
    candidates.extend(_goal_candidates(state.get("goals")))
    candidates.extend(_stress_candidates(actor_stress))

    candidates.sort(
        key=lambda c: (-int(c.get("magnitude") or 0), str(c["source_signal"]), str(c["source_id"]))
    )

    receipts: List[Dict[str, Any]] = []
    created = deduped = linked = capped = skipped = 0
    remaining = MAX_GENESIS_CANDIDATES_PER_TURN

    for cand in candidates:
        if not cand.get("qualifies"):
            skipped += 1
            receipts.append(
                _make_receipt(
                    "genesis_skipped",
                    turn_number=turn_number,
                    source_signal=cand["source_signal"],
                    source_id=cand["source_id"],
                    reason=cand.get("skip_reason") or "unqualified",
                )
            )
            continue

        if remaining <= 0:
            capped += 1
            receipts.append(
                _make_receipt(
                    "genesis_capped",
                    turn_number=turn_number,
                    source_signal=cand["source_signal"],
                    source_id=cand["source_id"],
                    reason="per_turn_cap_reached",
                )
            )
            continue

        candidate_id = pressure_graph.stable_pressure_id(
            seed, cand["kind"], "pressure_genesis", cand["source_id"], cand["scope"]
        )
        before_ids = {n.get("id") for n in (pg.get("nodes") or []) if isinstance(n, Mapping)}
        is_new = candidate_id not in before_ids

        node = pressure_graph.upsert_pressure_node(
            pg,
            node_id=candidate_id,
            run_seed=seed,
            kind=cand["kind"],
            origin_type="pressure_genesis",
            origin_id=cand["source_id"],
            scope=cand["scope"],
            magnitude=cand["magnitude"],
            # Only impose a trend on first creation. A dedup/reinforce pass
            # must not overwrite a trend pressure_graph's own evolution has
            # already set (e.g. a mitigation-driven decay) -- that would
            # fight the engine's sole authority over node lifecycle.
            trend=1 if is_new else None,
            turn_number=turn_number,
            actor_ids=cand["actor_ids"],
            location_ids=cand["location_ids"],
            faction_ids=cand["faction_ids"],
            tags=["pressure_genesis", cand["source_signal"]],
            evidence_refs=[f"{cand['source_signal']}:{cand['source_id']}"],
            label=cand["label"],
        )
        node_id = str(node.get("id") or candidate_id)
        remaining -= 1

        if is_new:
            created += 1
            receipts.append(
                _make_receipt(
                    "genesis_created",
                    turn_number=turn_number,
                    source_signal=cand["source_signal"],
                    source_id=cand["source_id"],
                    node_id=node_id,
                )
            )
        else:
            deduped += 1
            receipts.append(
                _make_receipt(
                    "genesis_deduped",
                    turn_number=turn_number,
                    source_signal=cand["source_signal"],
                    source_id=cand["source_id"],
                    node_id=node_id,
                )
            )

        link_target = _find_link_target(pg, node)
        if link_target and pressure_graph.link_pressure_nodes(pg, node_id, link_target):
            linked += 1
            receipts.append(
                _make_receipt(
                    "genesis_linked",
                    turn_number=turn_number,
                    source_signal=cand["source_signal"],
                    source_id=cand["source_id"],
                    node_id=node_id,
                    linked_node_id=link_target,
                )
            )

    stored = list(genesis_block.get("receipts") or []) + receipts
    genesis_block["receipts"] = stored[-MAX_GENESIS_RECEIPTS_STORED:]

    diagnostics = {
        "pressure_genesis_candidates_evaluated": len(candidates),
        "pressure_genesis_created": created,
        "pressure_genesis_deduped": deduped,
        "pressure_genesis_linked": linked,
        "pressure_genesis_capped": capped,
        "pressure_genesis_skipped": skipped,
    }
    return {"receipts": receipts, "diagnostics": diagnostics}
