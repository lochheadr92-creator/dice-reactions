"""
Utility AI v0.1 — canonical score composition, ranking, tie handling, seeded noise.

Canon: Source_of_Truth_v1.2.md Ch 27 + Appendix A.4.
Domain modules retain action catalogues and target generation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import situation_engine
import stress
from engine_determinism import (
    NUMERIC_CONTRACT_VERSION,
    build_seed_material,
    candidate_set_hash,
    derive_rng_range,
    evaluate_weighted_average,
    reject_non_finite,
    stable_hash,
)
from foundation_snapshot import FoundationTurnSnapshot
from utility_dimensions import (
    DimensionScore,
    compute_dimension_scores,
    dimension_scores_to_aggregate_map,
)

UTILITY_AI_SCHEMA_VERSION = 2
DECISION_VERSION = 1
PRESSURE_SCORING_BRIDGE_VERSION = 1
SITUATION_SCORING_BRIDGE_VERSION = 1

# Appendix A.4 base weights (Ch 27.4.2)
BASE_WEIGHTS = {
    "survival": 100.0,
    "goal_progression": 50.0,
    "pressure_relief": 30.0,
    "stress_reduction": 20.0,
    "relationship_impact": 40.0,
    "resource_gain_loss": 25.0,
    "memory_avoidance": 15.0,
}

WHIM_NOISE_LOW = -0.5
WHIM_NOISE_HIGH = 0.5
TIE_WINDOW = 0.01

DIMENSION_ORDER = tuple(sorted(BASE_WEIGHTS.keys()))

# Stage 2 Pressure Graph bridge: conservative bounded score modifiers only.
# Pressure never selects actions directly; it can only adjust the candidate score
# that Utility AI already ranks.
MAX_PRESSURE_NODES_PER_UTILITY_ACTOR = 4
MAX_PRESSURE_NODE_SCORE_MODIFIER = 4.0
MAX_PRESSURE_TOTAL_SCORE_MODIFIER = 8.0
MAX_SITUATIONS_PER_UTILITY_ACTOR = 4
MAX_SITUATION_SCORE_MODIFIER = 3.0
MAX_SITUATION_TOTAL_SCORE_MODIFIER = 5.0

PRESSURE_ACTION_MODIFIERS: Dict[str, Dict[str, float]] = {
    "danger": {
        "investigate": 4.0,
        "withdraw": 3.0,
        "flee": 3.0,
        "fortify": 2.5,
        "prepare": 2.5,
        "protect": 2.0,
        "idle": -3.0,
    },
    "opportunity": {
        "pursue": 4.0,
        "explore": 3.0,
        "trade": 2.5,
        "negotiate": 2.0,
        "gather": 1.5,
        "idle": -1.5,
    },
    "conflict": {
        "confront": 3.0,
        "avoid": 3.0,
        "pressure": 2.5,
        "withdraw": 2.0,
        "negotiate": 1.5,
        "conceal": 1.0,
        "idle": -2.0,
    },
    "scarcity": {
        "gather": 4.0,
        "steal": 3.0,
        "request_help": 3.0,
        "trade": 2.5,
        "negotiate": 1.5,
        "idle": -2.0,
    },
    "unknown": {
        "investigate": 4.0,
        "explore": 2.0,
        "idle": -1.5,
    },
}

PRESSURE_KIND_GROUPS = {
    "danger": "danger",
    "environmental": "danger",
    "environmental_threat": "danger",
    "pursuit": "danger",
    "injury_or_fatigue": "danger",
    "opportunity": "opportunity",
    "social_tension": "conflict",
    "conflict": "conflict",
    "suspicion": "conflict",
    "resource": "scarcity",
    "resource_pressure": "scarcity",
    "scarcity": "scarcity",
    "unresolved_thread": "unknown",
    "unknown": "unknown",
}

_PRESSURE_SCORE_KEYS = (
    "pressure_modifier",
    "pressure_node_ids",
    "pressure_bridge_version",
)

SITUATION_ACTION_MODIFIERS: Dict[str, Dict[str, float]] = {
    "murder_investigation": {
        "investigate": 3.0,
        "gather": 1.5,
        "protect": 1.0,
        "conceal": -1.0,
    },
    "missing_child": {
        "investigate": 3.0,
        "protect": 2.0,
        "gather": 1.5,
        "withdraw": -1.0,
    },
    "search_party": {
        "investigate": 2.5,
        "gather": 2.0,
        "protect": 1.5,
        "withdraw": -1.0,
    },
    "food_shortage": {
        "gather": 3.0,
        "negotiate": 1.5,
        "pressure": 1.0,
        "conceal": 1.0,
    },
    "gang_turf_war": {
        "protect": 2.5,
        "fortify": 2.5,
        "pressure": 2.0,
        "negotiate": 1.5,
        "withdraw": 1.0,
    },
    "political_unrest": {
        "negotiate": 2.5,
        "protect": 2.0,
        "pressure": 1.5,
        "withdraw": 1.0,
    },
    "disease_outbreak": {
        "protect": 2.5,
        "gather": 2.0,
        "withdraw": 1.5,
        "pressure": -1.0,
    },
    "flood_recovery": {
        "fortify": 3.0,
        "gather": 2.0,
        "protect": 1.5,
        "investigate": 1.0,
    },
    "bandit_activity": {
        "protect": 2.5,
        "fortify": 2.0,
        "investigate": 2.0,
        "withdraw": 1.5,
    },
    "trade_opportunity": {
        "negotiate": 2.5,
        "gather": 1.5,
        "investigate": 1.0,
        "protect": 0.5,
    },
}

_SITUATION_SCORE_KEYS = (
    "situation_modifier",
    "situation_ids",
    "situation_bridge_version",
)


# --- P2 stress behavioural integration (Ch 14 P2 -- shadow-only) -----------
# Diagnostic-only keys attached to each evaluated candidate for shadow tracing.
# They are EXCLUDED from the prepared decision hash (see _hashable_candidate):
# recording a band must not change canonical decision identity. A *valid* band's
# weight change DOES flow into the hash via "weights"/"base_utility" -- that is
# real scoring, not a diagnostic -- but CALM and any invalid/missing stress apply
# x1.0 modifiers and so leave the hash byte-identical.
_P2_SHADOW_KEYS = ("stress_band", "stress_input_valid", "stress_blocker_code")


def apply_stress_band_modifiers(
    weights: Mapping[str, float], modifiers: Mapping[str, float]
) -> Dict[str, float]:
    """Multiply canonical Ch 27 weights by P2 band modifiers exactly once.

    Identity (all-1.0) modifiers return bit-identical weights, so CALM and every
    fail-closed (invalid/missing) input leave the canonical weights unchanged.
    The band never selects an action directly -- it only reshapes the weighting.
    """
    return {
        name: float(weight) * float(modifiers.get(name, 1.0))
        for name, weight in weights.items()
    }


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _str_list(values: Any) -> List[str]:
    if values is None:
        return []
    if isinstance(values, (str, int, float)):
        values = [values]
    if not isinstance(values, Sequence) or isinstance(values, (bytes, bytearray)):
        return []
    out: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _token_set(*values: Any) -> set:
    tokens = set()
    for value in values:
        for text in _str_list(value):
            tokens.add(text)
            tokens.add(text.lower())
    return {token for token in tokens if token}


def _pressure_kind_group(kind: Any) -> str:
    return PRESSURE_KIND_GROUPS.get(str(kind or "").strip().lower(), "unknown")


def _actor_row(snapshot: FoundationTurnSnapshot, actor_id: str) -> Dict[str, Any]:
    for actor in snapshot.actor_registry:
        if str(actor.get("actor_id") or "") == actor_id:
            return dict(actor)
    return {"actor_id": actor_id}


def _pressure_context(
    snapshot: FoundationTurnSnapshot,
    *,
    actor_id: str,
    target_kind: str = "",
    target_id: str = "",
) -> Dict[str, set]:
    actor = _actor_row(snapshot, actor_id)
    target_kind = str(target_kind or "")
    target_id = str(target_id or "")
    actor_tokens = _token_set(actor_id, actor.get("display_name"), actor.get("name"))
    location_tokens = _token_set(
        snapshot.location_ref,
        actor.get("location_id"),
        actor.get("location"),
        actor.get("last_seen"),
    )
    faction_tokens = _token_set(
        actor.get("faction_id"),
        actor.get("faction"),
        actor.get("factions"),
    )
    event_tokens = set()
    pressure_tokens = set()
    if target_id:
        if target_kind in {"actor", "npc", "character"}:
            actor_tokens.update(_token_set(target_id))
        elif target_kind in {"location", "region", "place"}:
            location_tokens.update(_token_set(target_id))
        elif target_kind == "faction":
            faction_tokens.update(_token_set(target_id))
        elif target_kind in {"event", "world_event"}:
            event_tokens.update(_token_set(target_id))
        elif target_kind == "pressure":
            pressure_tokens.update(_token_set(target_id))
    return {
        "actor": actor_tokens,
        "location": location_tokens,
        "faction": faction_tokens,
        "event": event_tokens,
        "pressure": pressure_tokens,
    }


def _pressure_node_ref_sets(node: Mapping[str, Any]) -> Dict[str, set]:
    return {
        "actor": _token_set(node.get("actor_ids"), node.get("linked_actor_ids")),
        "location": _token_set(
            node.get("location_ids"),
            node.get("region_ids"),
            node.get("linked_location_ids"),
            node.get("linked_region_ids"),
        ),
        "faction": _token_set(node.get("faction_ids"), node.get("linked_faction_ids")),
        "event": _token_set(node.get("event_ids"), node.get("linked_event_ids")),
        "pressure": _token_set(node.get("id"), node.get("linked_node_ids"), node.get("linked_pressure_ids")),
    }


def _pressure_node_applies(node: Mapping[str, Any], context: Mapping[str, set]) -> bool:
    refs = _pressure_node_ref_sets(node)
    # Every node has a pressure id; that should support direct pressure-target
    # matches, but must not make otherwise-global pressure actor-specific.
    has_specific_refs = any(refs[key] for key in ("actor", "location", "faction", "event"))
    for key, values in refs.items():
        if values and values.intersection(context.get(key, set())):
            return True
    return not has_specific_refs


def _pressure_equivalence_key(node: Mapping[str, Any]) -> Tuple[str, str, str, str]:
    origin = node.get("origin") if isinstance(node.get("origin"), Mapping) else {}
    return (
        str(node.get("kind") or ""),
        str(node.get("origin_type") or origin.get("type") or ""),
        str(node.get("origin_id") or origin.get("id") or node.get("id") or ""),
        str(node.get("scope") or ""),
    )


def _active_pressure_nodes_for_actor(
    snapshot: FoundationTurnSnapshot,
    *,
    actor_id: str,
    target_kind: str = "",
    target_id: str = "",
) -> List[Dict[str, Any]]:
    graph = snapshot.pressure_state_ref if isinstance(snapshot.pressure_state_ref, Mapping) else {}
    context = _pressure_context(
        snapshot,
        actor_id=actor_id,
        target_kind=target_kind,
        target_id=target_id,
    )
    candidates: List[Dict[str, Any]] = []
    for raw in graph.get("nodes") or []:
        if not isinstance(raw, Mapping) or raw.get("status") != "active":
            continue
        node = dict(raw)
        if not _pressure_node_applies(node, context):
            continue
        try:
            node["_magnitude"] = _clamp(float(node.get("magnitude") or 0.0), 0.0, 100.0)
        except (TypeError, ValueError):
            node["_magnitude"] = 0.0
        candidates.append(node)

    deduped: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for node in sorted(
        candidates,
        key=lambda n: (-float(n.get("_magnitude") or 0.0), str(n.get("id") or "")),
    ):
        deduped.setdefault(_pressure_equivalence_key(node), node)

    ordered = sorted(
        deduped.values(),
        key=lambda n: (-float(n.get("_magnitude") or 0.0), str(n.get("id") or "")),
    )
    return ordered[:MAX_PRESSURE_NODES_PER_UTILITY_ACTOR]


def _action_modifier_for_pressure(
    *,
    pressure_kind: str,
    action_kind: str,
    personality_order: Sequence[str],
) -> float:
    action = str(action_kind or "").strip().lower()
    group = _pressure_kind_group(pressure_kind)
    if group == "conflict" and action in {"confront", "avoid"}:
        order = [str(item) for item in personality_order or []]
        if "confront" in order and "avoid" in order:
            preferred = "confront" if order.index("confront") < order.index("avoid") else "avoid"
            return 3.0 if action == preferred else 1.0
    return PRESSURE_ACTION_MODIFIERS.get(group, {}).get(action, 0.0)


def pressure_score_modifier(
    snapshot: FoundationTurnSnapshot,
    *,
    actor_id: str,
    action_kind: str,
    target_kind: str = "",
    target_id: str = "",
    personality_order: Sequence[str] = (),
) -> Dict[str, Any]:
    """Return the bounded deterministic Utility AI score adjustment from pressure.

    This is a read-only bridge over the authoritative pressure graph. It never
    mutates pressure and never chooses an action; callers add the returned
    modifier to an already computed Utility AI score before normal ranking.
    """
    matched = _active_pressure_nodes_for_actor(
        snapshot,
        actor_id=actor_id,
        target_kind=target_kind,
        target_id=target_id,
    )
    total = 0.0
    contributing_ids: List[str] = []
    for node in matched:
        raw_modifier = _action_modifier_for_pressure(
            pressure_kind=str(node.get("kind") or ""),
            action_kind=action_kind,
            personality_order=personality_order,
        )
        if raw_modifier == 0.0:
            continue
        magnitude_factor = _clamp(float(node.get("_magnitude") or 0.0) / 100.0, 0.0, 1.0)
        contribution = _clamp(
            raw_modifier * magnitude_factor,
            -MAX_PRESSURE_NODE_SCORE_MODIFIER,
            MAX_PRESSURE_NODE_SCORE_MODIFIER,
        )
        if contribution == 0.0:
            continue
        total += contribution
        node_id = str(node.get("id") or "")
        if node_id and node_id not in contributing_ids:
            contributing_ids.append(node_id)

    total = _clamp(
        total,
        -MAX_PRESSURE_TOTAL_SCORE_MODIFIER,
        MAX_PRESSURE_TOTAL_SCORE_MODIFIER,
    )
    return {
        "bridge_version": PRESSURE_SCORING_BRIDGE_VERSION,
        "modifier": round(total, 4),
        "node_ids": contributing_ids,
    }


def situation_score_modifier(
    snapshot: FoundationTurnSnapshot,
    *,
    actor_id: str,
    action_kind: str,
    target_kind: str = "",
    target_id: str = "",
) -> Dict[str, Any]:
    """Return bounded deterministic Utility AI score adjustment from situations."""
    actor = _actor_row(snapshot, actor_id)
    target_kind = str(target_kind or "")
    target_id = str(target_id or "")
    actor_ids = [actor_id, actor.get("display_name") or "", actor.get("name") or ""]
    location_ids = [
        snapshot.location_ref,
        actor.get("location_id") or "",
        actor.get("location") or "",
        actor.get("last_seen") or "",
    ]
    faction_ids = [actor.get("faction_id") or "", actor.get("faction") or ""]
    situation_ids: List[str] = []
    if target_id:
        if target_kind in {"actor", "npc", "character"}:
            actor_ids.append(target_id)
        elif target_kind in {"location", "region", "place"}:
            location_ids.append(target_id)
        elif target_kind == "faction":
            faction_ids.append(target_id)
        elif target_kind == "situation":
            situation_ids.append(target_id)
    matched = situation_engine.active_situations_for_context(
        snapshot.situation_state_ref,
        actor_ids=actor_ids,
        location_ids=location_ids,
        faction_ids=faction_ids,
        situation_ids=situation_ids,
        limit=MAX_SITUATIONS_PER_UTILITY_ACTOR,
    )
    action = str(action_kind or "").strip().lower()
    total = 0.0
    contributing_ids: List[str] = []
    for row in matched:
        raw_modifier = SITUATION_ACTION_MODIFIERS.get(str(row.get("type") or ""), {}).get(action, 0.0)
        if raw_modifier == 0.0:
            continue
        severity_factor = _clamp(float(row.get("severity") or 0.0) / 10.0, 0.0, 1.0)
        contribution = _clamp(
            raw_modifier * severity_factor,
            -MAX_SITUATION_SCORE_MODIFIER,
            MAX_SITUATION_SCORE_MODIFIER,
        )
        if contribution == 0.0:
            continue
        total += contribution
        situation_id = str(row.get("situation_id") or "")
        if situation_id and situation_id not in contributing_ids:
            contributing_ids.append(situation_id)

    total = _clamp(total, -MAX_SITUATION_TOTAL_SCORE_MODIFIER, MAX_SITUATION_TOTAL_SCORE_MODIFIER)
    return {
        "bridge_version": SITUATION_SCORING_BRIDGE_VERSION,
        "modifier": round(total, 4),
        "situation_ids": contributing_ids,
    }


def _hashable_candidate(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluated-candidate projection excluding P2 diagnostic-only keys."""
    return {key: value for key, value in row.items() if key not in _P2_SHADOW_KEYS}


class UtilityAIError(ValueError):
    pass


def compute_dimension_weights(
    *,
    pressure_intensity: float = 0.0,
    stress: float = 0.0,
    goal_priority: float = 5.0,
    relationship_importance: float = 5.0,
    resource_scarcity: float = 0.0,
    trauma_intensity: float = 0.0,
    starving: bool = False,
) -> Dict[str, float]:
    """Dynamic weights per Ch 27.4.2 table."""
    weights = dict(BASE_WEIGHTS)
    if starving:
        weights["survival"] = 200.0
    else:
        weights["survival"] *= 1.0 + max(0.0, pressure_intensity)
    weights["goal_progression"] *= max(0.1, goal_priority / 10.0)
    weights["pressure_relief"] *= max(0.0, 1.0 + pressure_intensity)
    weights["stress_reduction"] *= max(0.0, stress / 100.0)
    weights["relationship_impact"] *= max(0.1, relationship_importance / 5.0)
    weights["resource_gain_loss"] *= 1.0 + max(0.0, resource_scarcity)
    if trauma_intensity > 0:
        weights["memory_avoidance"] *= 1.0 + min(2.0, trauma_intensity)
    return weights


def compute_utility_score(
    dimension_scores: Mapping[str, float],
    weights: Mapping[str, float],
) -> float:
    """U(a) = Σ(score × weight) / Σ(weight), bounded 0–100 when inputs are 0–100."""
    components = []
    for name in DIMENSION_ORDER:
        if name not in dimension_scores:
            continue
        score = float(dimension_scores[name])
        weight = float(weights.get(name, 0.0))
        reject_non_finite(score)
        reject_non_finite(weight)
        components.append((name, score, weight))
    if not components:
        raise UtilityAIError("no dimension scores supplied")
    utility = evaluate_weighted_average(components)
    return max(0.0, min(100.0, utility))


def apply_whim_noise(
    utility: float,
    *,
    seed_material: str,
    draw_index: int,
) -> float:
    noise = derive_rng_range(seed_material, draw_index, WHIM_NOISE_LOW, WHIM_NOISE_HIGH)
    return utility + noise


def personality_tie_key(
    *,
    actor_id: str,
    action_kind: str,
    personality_order: Sequence[str],
) -> int:
    try:
        return list(personality_order).index(action_kind)
    except ValueError:
        return len(personality_order) + hash_stable_action(actor_id, action_kind)


def hash_stable_action(actor_id: str, action_kind: str) -> int:
    digest = stable_hash("personality_tie", {"actor_id": actor_id, "action_kind": action_kind})
    return int(digest[:8], 16)


def build_canonical_dimension_bundle(
    snapshot: FoundationTurnSnapshot,
    *,
    actor_id: str,
    action_kind: str,
    target_kind: str,
    aligned_goals: frozenset[str],
    relationship_deltas: Mapping[str, int],
) -> Dict[str, Any]:
    scores = compute_dimension_scores(
        snapshot,
        actor_id=actor_id,
        action_kind=action_kind,
        target_kind=target_kind,
        aligned_goals=aligned_goals,
        relationship_deltas=relationship_deltas,
    )
    numeric, authorised, blockers = dimension_scores_to_aggregate_map(scores)
    return {
        "dimension_scores": numeric,
        "dimension_score_records": [ _score_record(row) for row in scores ],
        "replacement_authorised": authorised,
        "blocker_codes": blockers,
    }


def _score_record(row: DimensionScore) -> Dict[str, Any]:
    return {
        "dimension": row.dimension.value,
        "value": row.value,
        "source_status": row.source_status.value,
        "source_ids": list(row.source_ids),
        "canon_rule_id": row.canon_rule_id,
        "blocker_code": row.blocker_code,
    }


def _selected_output(row: Mapping[str, Any]) -> Dict[str, Any]:
    out = {
        "actor_id": row["actor_id"],
        "action_kind": row["action_kind"],
        "target_kind": row["target_kind"],
        "target_id": row["target_id"],
        "base_utility": row["base_utility"],
        "noisy_utility": row["noisy_utility"],
        "replacement_authorised": row.get("replacement_authorised"),
        "stress_band": row.get("stress_band"),
        "stress_input_valid": row.get("stress_input_valid"),
        "stress_blocker_code": row.get("stress_blocker_code"),
    }
    for key in _PRESSURE_SCORE_KEYS:
        if key in row:
            out[key] = row[key]
    for key in _SITUATION_SCORE_KEYS:
        if key in row:
            out[key] = row[key]
    return out


def _score_table_output(row: Mapping[str, Any]) -> Dict[str, Any]:
    out = {
        "actor_id": row["actor_id"],
        "action_kind": row["action_kind"],
        "target_kind": row["target_kind"],
        "target_id": row["target_id"],
        "base_utility": row["base_utility"],
        "noisy_utility": row["noisy_utility"],
        "replacement_authorised": row.get("replacement_authorised"),
        "stress_band": row.get("stress_band"),
        "stress_input_valid": row.get("stress_input_valid"),
        "stress_blocker_code": row.get("stress_blocker_code"),
    }
    for key in _PRESSURE_SCORE_KEYS:
        if key in row:
            out[key] = row[key]
    for key in _SITUATION_SCORE_KEYS:
        if key in row:
            out[key] = row[key]
    return out


def select_action(
    candidates: Sequence[Mapping[str, Any]],
    *,
    snapshot: FoundationTurnSnapshot,
    actor_resolution: Mapping[str, Any],
    seed_draw_start: int = 0,
) -> Dict[str, Any]:
    acting_ids = set(actor_resolution.get("acting_actor_ids") or [])
    feasible: List[Dict[str, Any]] = []
    for raw in candidates:
        actor_id = str(raw.get("actor_id") or "")
        if actor_id not in acting_ids:
            continue
        action_kind = str(raw.get("action_kind") or "")
        target_kind = str(raw.get("target_kind") or "")
        target_id = str(raw.get("target_id") or "")
        if not action_kind or not target_kind or not target_id:
            continue
        dimension_scores = dict(raw.get("dimension_scores") or {})
        baseline_weights = compute_dimension_weights(
            pressure_intensity=float(raw.get("pressure_intensity", 0.0)),
            stress=float(raw.get("stress", 0.0)),
            goal_priority=float(raw.get("goal_priority", 5.0)),
            relationship_importance=float(raw.get("relationship_importance", 5.0)),
            resource_scarcity=float(raw.get("resource_scarcity", 0.0)),
            trauma_intensity=float(raw.get("trauma_intensity", 0.0)),
            starving=bool(raw.get("starving")),
        )
        # Ch 14 P2 (shadow-only): derive the behavioural profile from the
        # AUTHORITATIVE stress_level on the snapshot -- not the candidate "stress"
        # field, which candidates_from_agendas flattens missing -> 0.0 and would
        # misread as a valid CALM band. Modifiers apply EXACTLY ONCE here on top of
        # the canonical Ch 27 weights; missing/invalid stress yields identity
        # (x1.0) modifiers, so weights stay byte-identical.
        authoritative_stress = _utility_inputs_for_actor(snapshot, actor_id).get("stress_level")
        stress_behaviour = stress.evaluate_stress_behaviour(authoritative_stress)
        stress_input_valid = bool(stress_behaviour["valid"])
        weights = apply_stress_band_modifiers(baseline_weights, stress_behaviour["modifiers"])
        # Fail closed: missing/invalid authoritative stress can NEVER authorise a
        # replacement. The band never forces an action -- it only gates
        # authorisation and reshapes weights; selection stays argmax-with-noise.
        replacement_authorised = bool(raw.get("replacement_authorised")) and stress_input_valid
        base_utility = compute_utility_score(dimension_scores, weights)
        pressure_adjustment = pressure_score_modifier(
            snapshot,
            actor_id=actor_id,
            action_kind=action_kind,
            target_kind=target_kind,
            target_id=target_id,
            personality_order=raw.get("personality_order") or (),
        )
        pressure_modifier = float(pressure_adjustment.get("modifier") or 0.0)
        if pressure_modifier != 0.0:
            base_utility = _clamp(base_utility + pressure_modifier, 0.0, 100.0)
        situation_adjustment = situation_score_modifier(
            snapshot,
            actor_id=actor_id,
            action_kind=action_kind,
            target_kind=target_kind,
            target_id=target_id,
        )
        situation_modifier = float(situation_adjustment.get("modifier") or 0.0)
        if situation_modifier != 0.0:
            base_utility = _clamp(base_utility + situation_modifier, 0.0, 100.0)
        c_hash = candidate_set_hash(
            actor_id=actor_id,
            action_kind=action_kind,
            target_kind=target_kind,
            target_id=target_id,
            decision_version=DECISION_VERSION,
            candidates=[raw],
        )
        seed_material = build_seed_material(
            run_seed=snapshot.run_seed,
            turn_sequence=snapshot.turn_sequence,
            subsystem="utility_ai",
            actor_id=actor_id,
            candidate_set_hash_value=c_hash,
        )
        noisy = apply_whim_noise(base_utility, seed_material=seed_material, draw_index=seed_draw_start)
        evaluated = {
            "actor_id": actor_id,
            "action_kind": action_kind,
            "target_kind": target_kind,
            "target_id": target_id,
            "base_utility": base_utility,
            "noisy_utility": noisy,
            "weights": weights,
            "dimension_scores": dimension_scores,
            "dimension_score_records": list(raw.get("dimension_score_records") or []),
            "replacement_authorised": replacement_authorised,
            "personality_order": list(raw.get("personality_order") or []),
            "candidate_set_hash": c_hash,
            "seed_material": seed_material,
            # P2 diagnostic-only (shadow) -- excluded from state_hash.
            "stress_band": stress_behaviour["band"],
            "stress_input_valid": stress_input_valid,
            "stress_blocker_code": stress_behaviour["blocker_code"],
        }
        if pressure_modifier != 0.0:
            evaluated.update(
                pressure_modifier=pressure_modifier,
                pressure_node_ids=list(pressure_adjustment.get("node_ids") or []),
                pressure_bridge_version=pressure_adjustment.get("bridge_version"),
            )
        if situation_modifier != 0.0:
            evaluated.update(
                situation_modifier=situation_modifier,
                situation_ids=list(situation_adjustment.get("situation_ids") or []),
                situation_bridge_version=situation_adjustment.get("bridge_version"),
            )
        feasible.append(evaluated)

    if not feasible:
        return {
            "schema_version": UTILITY_AI_SCHEMA_VERSION,
            "selected": None,
            "candidates_evaluated": 0,
            "source_state_hash": snapshot.source_state_hash,
        }

    max_utility = max(row["noisy_utility"] for row in feasible)
    tied = [row for row in feasible if abs(row["noisy_utility"] - max_utility) <= TIE_WINDOW]
    if len(tied) == 1:
        winner = tied[0]
    else:
        tied_sorted = sorted(
            tied,
            key=lambda row: (
                personality_tie_key(
                    actor_id=row["actor_id"],
                    action_kind=row["action_kind"],
                    personality_order=row.get("personality_order") or [],
                ),
                row["actor_id"],
                row["action_kind"],
                row["target_kind"],
                row["target_id"],
            ),
        )
        winner = tied_sorted[0]

    return {
        "schema_version": UTILITY_AI_SCHEMA_VERSION,
        "numeric_contract_version": NUMERIC_CONTRACT_VERSION,
        "source_state_hash": snapshot.source_state_hash,
        "selected": _selected_output(winner),
        "selected_actor_id": winner["actor_id"],
        "selected_action_kind": winner["action_kind"],
        "selected_target_kind": winner["target_kind"],
        "selected_target_id": winner["target_id"],
        "candidate_set_hash": winner["candidate_set_hash"],
        "candidates_evaluated": len(feasible),
        "score_table": [
            _score_table_output(row)
            for row in sorted(
                feasible,
                key=lambda r: (
                    -r["noisy_utility"],
                    r["actor_id"],
                    r["action_kind"],
                    r["target_kind"],
                    r["target_id"],
                ),
            )
        ],
        "state_hash": stable_hash("utility_ai_prepared", _hashable_candidate(winner)),
    }


def candidates_from_agendas(
    snapshot: FoundationTurnSnapshot,
    *,
    rolling_state: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
    run_seed: str,
) -> List[Dict[str, Any]]:
    import npc_agendas as agenda_mod
    import npc_world_moves as world_moves

    out: List[Dict[str, Any]] = []
    agendas_state = replayability_state.get("npc_agendas") or {}
    agenda_rows = agendas_state.get("agendas") or agendas_state.get("active") or []
    for agenda in agenda_rows:
        if not isinstance(agenda, dict):
            continue
        npc_id = str(agenda.get("npc_id") or "")
        display_name = str(agenda.get("display_name") or "")
        tier = world_moves.resolve_actor_tier(npc_id, display_name, rolling_state, snapshot.turn_sequence)
        inputs = _utility_inputs_for_actor(snapshot, npc_id)
        for move_kind in world_moves.MOVE_KINDS:
            target = world_moves.resolve_move_target(
                move_kind, agenda, rolling_state, replayability_state
            )
            if not target:
                continue
            target_type, target_id = target
            rel_deltas = world_moves._relationship_deltas_for_move(move_kind, target_type)
            bundle = build_canonical_dimension_bundle(
                snapshot,
                actor_id=npc_id,
                action_kind=move_kind,
                target_kind=target_type,
                aligned_goals=world_moves.MOVE_GOAL_ALIGN.get(move_kind, frozenset()),
                relationship_deltas=rel_deltas,
            )
            out.append(
                {
                    "actor_id": npc_id,
                    "action_kind": move_kind,
                    "target_kind": target_type,
                    "target_id": target_id,
                    "dimension_scores": bundle["dimension_scores"],
                    "dimension_score_records": bundle["dimension_score_records"],
                    "replacement_authorised": bundle["replacement_authorised"],
                    "blocker_codes": bundle["blocker_codes"],
                    "goal_priority": 10.0 if agenda.get("goal_kind") in world_moves.MOVE_GOAL_ALIGN.get(move_kind, ()) else 3.0,
                    "pressure_intensity": float(inputs.get("highest_pressure_intensity") or 0.0),
                    "stress": float(inputs.get("stress_level") or 0.0),
                    "relationship_importance": float(inputs.get("relationship_importance") or 5.0),
                    "resource_scarcity": float(inputs.get("resource_scarcity") or 0.0),
                    "trauma_intensity": _max_trauma(inputs.get("memory_signatures") or ()),
                    "starving": bool(inputs.get("starving")),
                    "personality_order": _personality_order(run_seed, npc_id),
                    "provisional_tier": tier,
                }
            )
    return out


def _utility_inputs_for_actor(snapshot: FoundationTurnSnapshot, actor_id: str) -> Dict[str, Any]:
    for ref in snapshot.utility_input_refs:
        if ref.get("actor_id") == actor_id:
            return dict(ref)
    return {}


def _max_trauma(signatures: Sequence[Mapping[str, Any]]) -> float:
    peak = 0.0
    for sig in signatures:
        if isinstance(sig, dict) and sig.get("negative"):
            peak = max(peak, float(sig.get("trauma_intensity", 0.0)))
    return peak


def _personality_order(run_seed: str, actor_id: str) -> List[str]:
    from run_identity import select_from_namespace

    import npc_world_moves as world_moves

    options = tuple(sorted(list(world_moves.MOVE_KINDS)))
    primary = select_from_namespace(run_seed, f"personality:{actor_id}", options)
    rest = [opt for opt in options if opt != primary]
    return [primary, *rest]
