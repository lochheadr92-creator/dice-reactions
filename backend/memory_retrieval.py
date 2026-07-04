"""
Memory Retrieval System v0.1 — relevance scoring and seeded weighted sampling.

Canon: Source_of_Truth_v1.2.md Ch 28 + Appendix A.5.
Shadow mode by default; does not mutate authoritative memory truth.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from engine_determinism import (
    NUMERIC_CONTRACT_VERSION,
    build_seed_material,
    derive_rng_unit,
    reject_non_finite,
    stable_hash,
)
from foundation_snapshot import FoundationTurnSnapshot
import pressure_graph
import situation_engine

MEMORY_RETRIEVAL_SCHEMA_VERSION = 1
MAX_RETRIEVAL_PRESSURE_NODES = 3
MAX_RETRIEVAL_SITUATIONS = 3

# Appendix A.5
WORKING_MEMORY_SIZE = {
    "hero": 7,
    "active": 5,
    "relevant": 3,
    "dormant": 1,
    "archived": 0,
    "unknown": 0,
}

RECENCY_HALF_LIFE_DAYS = {
    "major": 30.0,
    "minor": 3.0,
    "defining": 30.0,
    "moderate": 7.0,
}

BASE_RETRIEVAL_PROBABILITY = {
    "defining": 0.9,
    "major": 0.5,
    "minor": 0.01,
    "moderate": 0.1,
}

EMOTIONAL_BIAS = {
    "defining": 2.0,
    "major": 1.5,
    "moderate": 1.0,
    "minor": 0.5,
}

MEMORY_WEIGHT_CLASS = {
    "defining": 1.0,
    "major": 0.7,
    "moderate": 0.4,
    "minor": 0.1,
}


class MemoryRetrievalError(ValueError):
    pass


def _situation_ids(context: Mapping[str, Any]) -> set:
    values = []
    if context.get("situation_id"):
        values.append(context.get("situation_id"))
    raw = context.get("situation_ids") or context.get("active_situation_ids") or []
    if isinstance(raw, (list, tuple, set)):
        values.extend(raw)
    else:
        values.append(raw)
    return {str(value or "").strip() for value in values if str(value or "").strip()}


def recency_factor(days_since_event: float, *, weight_class: str) -> float:
    reject_non_finite(days_since_event)
    half_life = RECENCY_HALF_LIFE_DAYS.get(weight_class, RECENCY_HALF_LIFE_DAYS["minor"])
    return math.exp(-days_since_event / half_life)


def cue_relevance(current_context: Mapping[str, Any], memory_context: Mapping[str, Any]) -> float:
    """Weighted cue average — location and actors weighted highest (Ch 28.4)."""
    cues: List[Tuple[float, float]] = []
    loc = str(current_context.get("location") or "")
    mem_loc = str(memory_context.get("location") or "")
    if loc and mem_loc:
        cues.append((1.0, 1.0 if loc == mem_loc else 0.5))
    actors = set(current_context.get("actors_present") or [])
    mem_actors = set(memory_context.get("actors_present") or [])
    if actors and mem_actors:
        overlap = actors.intersection(mem_actors)
        cues.append((1.0, 1.0 if overlap else 0.3))
    activity = str(current_context.get("activity") or "")
    mem_activity = str(memory_context.get("activity") or "")
    if activity and mem_activity:
        cues.append((0.8, 1.0 if activity == mem_activity else 0.6))
    pressure = str(current_context.get("pressure_kind") or "")
    mem_pressure = str(memory_context.get("pressure_kind") or "")
    if pressure and mem_pressure:
        cues.append((0.4, 1.0 if pressure == mem_pressure else 0.0))
    situations = _situation_ids(current_context)
    mem_situations = _situation_ids(memory_context)
    if situations and mem_situations:
        cues.append((0.8, 1.0 if situations.intersection(mem_situations) else 0.0))
    if not cues:
        return 0.0
    weighted = sum(weight * value for weight, value in cues)
    total_weight = sum(weight for weight, _ in cues)
    return weighted / total_weight


def memory_retrieval_weight(
    memory: Mapping[str, Any],
    *,
    current_context: Mapping[str, Any],
    turn_sequence: int,
) -> float:
    weight_class = str(memory.get("weight_class") or "minor")
    days_since = float(memory.get("days_since_event", max(0, turn_sequence - int(memory.get("since_turn", 0)))))
    r = recency_factor(days_since, weight_class=weight_class)
    e = float(MEMORY_WEIGHT_CLASS.get(weight_class, 0.1))
    e *= float(EMOTIONAL_BIAS.get(weight_class, 1.0))
    c = cue_relevance(current_context, memory.get("context") or {})
    p_base = float(BASE_RETRIEVAL_PROBABILITY.get(weight_class, 0.01))
    if memory.get("pattern_count"):
        count = max(1, int(memory["pattern_count"]))
        p_base *= 1.0 + math.log10(count)
    weight = r * e * c * p_base
    reject_non_finite(weight)
    return max(0.0, weight)


def sample_memories(
    memories: Sequence[Mapping[str, Any]],
    *,
    sample_count: int,
    seed_material: str,
    draw_start: int = 0,
) -> Tuple[List[Dict[str, Any]], List[int]]:
    """
    Seeded weighted sampling without replacement until sample_count reached.
    Zero-weight memories are excluded.
    """
    pool = [dict(m) for m in memories if float(m.get("_weight") or 0.0) > 0.0]
    weights = [float(mem.get("_weight") or 0.0) for mem in pool]
    selected: List[Dict[str, Any]] = []
    draws: List[int] = []
    available = list(range(len(pool)))
    draw_index = draw_start
    while available and len(selected) < sample_count:
        active_weights = [weights[i] for i in available]
        total = sum(active_weights)
        if total <= 0:
            break
        unit = derive_rng_unit(seed_material, draw_index)
        draw_index += 1
        draws.append(draw_index - 1)
        threshold = unit * total
        cumulative = 0.0
        chosen_idx = available[-1]
        for idx in available:
            cumulative += weights[idx]
            if cumulative >= threshold:
                chosen_idx = idx
                break
        selected.append(pool[chosen_idx])
        available.remove(chosen_idx)
    return selected, draws


def evaluate_memory_retrieval(
    snapshot: FoundationTurnSnapshot,
    *,
    actor_resolution: Mapping[str, Any],
    gravity: Mapping[str, Any],
    rolling_state: Mapping[str, Any],
    shadow_mode: bool = True,
    developer_mode: bool = False,
) -> Dict[str, Any]:
    """
    Select bounded retrieval set. Shadow mode leaves prompt path unchanged.
    """
    # The prompt-injection safety gate is governed SOLELY by ``shadow_mode`` (the
    # caller/seam derives it from the acceptance gate, which is blocked by
    # default). ``developer_mode`` is a diagnostics-verbosity flag and must NEVER
    # weaken this gate: coupling them let a dev-only flag silently report the
    # block as lifted (fail-open), contradicting the D_MEMORY_RETRIEVAL_SHADOW
    # invariant. Retrieval data is present in the output regardless, so devs lose
    # nothing. Fail-closed: shadow stays on unless injection is truly accepted.
    effective_shadow = bool(shadow_mode)
    tiers = actor_resolution.get("tiers_by_actor_id") or {}
    traces: List[Dict[str, Any]] = []
    all_selected_ids: List[str] = []
    pressure_context = pressure_graph.project_pressure_graph_for_prompt(
        snapshot.pressure_state_ref,
        limit=MAX_RETRIEVAL_PRESSURE_NODES,
    )
    pressure_node_ids = [
        str(node.get("id") or "")
        for node in pressure_context.get("nodes") or []
        if isinstance(node, dict) and node.get("id")
    ]

    for actor in snapshot.actor_registry:
        actor_id = str(actor.get("actor_id") or "")
        if not actor_id:
            continue
        tier = tiers.get(actor_id, "dormant")
        budget = WORKING_MEMORY_SIZE.get(tier, 0)
        if budget <= 0:
            continue
        actor_situations = situation_engine.active_situations_for_context(
            snapshot.situation_state_ref,
            actor_ids=[actor_id, actor.get("display_name") or ""],
            location_ids=[
                snapshot.location_ref,
                actor.get("location_id") or "",
                actor.get("last_seen") or "",
            ],
            faction_ids=[actor.get("faction_id") or "", actor.get("faction") or ""],
            limit=MAX_RETRIEVAL_SITUATIONS,
        )
        situation_ids = [
            str(row.get("situation_id") or "")
            for row in actor_situations
            if row.get("situation_id")
        ]
        memories = _memories_for_actor(actor, rolling_state, snapshot.turn_sequence)
        current_context = {
            "location": snapshot.location_ref,
            "actors_present": [actor_id],
            "activity": "decision",
            "pressure_kind": _primary_pressure_kind(snapshot),
            "pressure_node_ids": pressure_node_ids,
            "pressure_nodes": pressure_context.get("nodes") or [],
            "situation_ids": situation_ids,
            "active_situations": [
                {
                    "situation_id": row.get("situation_id"),
                    "type": row.get("type"),
                    "severity": row.get("severity"),
                    "status": row.get("status"),
                }
                for row in actor_situations
            ],
        }
        weighted: List[Dict[str, Any]] = []
        numerators: List[float] = []
        for mem in memories:
            if mem.get("concealed") and not _actor_has_secret_access(actor_id, snapshot):
                continue
            w = memory_retrieval_weight(mem, current_context=current_context, turn_sequence=snapshot.turn_sequence)
            if w <= 0:
                continue
            numerators.append(w)
            row = dict(mem)
            row["_weight"] = w
            weighted.append(row)
        total = sum(numerators)
        probabilities = [w / total for w in numerators] if total > 0 else []
        seed_material = build_seed_material(
            run_seed=snapshot.run_seed,
            turn_sequence=snapshot.turn_sequence,
            subsystem="memory_retrieval",
            actor_id=actor_id,
            candidate_set_hash_value=stable_hash("retrieval_candidates", weighted),
        )
        selected, draw_indices = sample_memories(
            weighted,
            sample_count=budget,
            seed_material=seed_material,
        )
        selected_ids = [str(row.get("memory_id") or "") for row in selected]
        all_selected_ids.extend(selected_ids)
        traces.append(
            {
                "actor_id": actor_id,
                "tier": tier,
                "working_memory_size": budget,
                "candidate_count": len(weighted),
                "probabilities": probabilities,
                "selected_memory_ids": selected_ids,
                "draw_indices": draw_indices,
                "situation_ids": situation_ids,
                "shadow_mode": effective_shadow,
            }
        )

    prepared = {
        "schema_version": MEMORY_RETRIEVAL_SCHEMA_VERSION,
        "numeric_contract_version": NUMERIC_CONTRACT_VERSION,
        "source_state_hash": snapshot.source_state_hash,
        "shadow_mode": effective_shadow,
        "selected_memory_ids": all_selected_ids,
        "pressure_context": pressure_context,
        "situation_context": {
            "max_situations": MAX_RETRIEVAL_SITUATIONS,
            "active": situation_engine.project_situations_for_prompt(
                {"situations": snapshot.situation_state_ref.get("situations") or []}
            )[:MAX_RETRIEVAL_SITUATIONS],
        },
        "working_memory_size": sum(trace["working_memory_size"] for trace in traces),
        "retrieval_traces": traces,
        "state_hash": stable_hash(
            "memory_retrieval_prepared",
            {"selected_memory_ids": all_selected_ids, "source_state_hash": snapshot.source_state_hash},
        ),
    }
    return prepared


def _memories_for_actor(
    actor: Mapping[str, Any],
    rolling_state: Mapping[str, Any],
    turn_sequence: int,
) -> List[Dict[str, Any]]:
    name = str(actor.get("display_name") or "").strip().lower()
    out: List[Dict[str, Any]] = []
    for row in rolling_state.get("npc_memory") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("name") or "").strip().lower() != name:
            continue
        for idx, mem in enumerate(row.get("remembers") or []):
            if not isinstance(mem, dict):
                continue
            weight_class = str(mem.get("weight") or mem.get("severity") or "minor").lower()
            if weight_class not in MEMORY_WEIGHT_CLASS:
                if weight_class in ("high", "severe"):
                    weight_class = "major"
                else:
                    weight_class = "minor"
            since_turn = int(mem.get("since_turn") or 0)
            memory_id = stable_hash(
                "memory",
                {"actor": name, "idx": idx, "summary": mem.get("summary") or mem.get("text")},
            )[:16]
            out.append(
                {
                    "memory_id": memory_id,
                    "weight_class": weight_class,
                    "since_turn": since_turn,
                    "days_since_event": float(max(0, turn_sequence - since_turn)),
                    "context": mem.get("context") or {},
                    "summary": str(mem.get("summary") or mem.get("text") or ""),
                    "concealed": bool(mem.get("concealed") or mem.get("secret")),
                    "pattern_count": int(mem.get("pattern_count") or 0),
                }
            )
    return out


def _primary_pressure_kind(snapshot: FoundationTurnSnapshot) -> str:
    fg = snapshot.pressure_state_ref.get("foreground_node_id")
    for node in snapshot.pressure_state_ref.get("nodes") or []:
        if isinstance(node, dict) and node.get("id") == fg:
            return str(node.get("kind") or "")
    return ""


def _actor_has_secret_access(actor_id: str, snapshot: FoundationTurnSnapshot) -> bool:
    _ = actor_id
    return "player_has_secret" not in snapshot.secret_access_facts
