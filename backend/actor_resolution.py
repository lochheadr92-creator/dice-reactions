"""
Actor Resolution Scaling v0.1 — tiers, promotion, demotion, caps, cadence.

Canon: Source_of_Truth_v1.2.md Ch 25 + Appendix A.3.
Does not select actions, score actions, retrieve memories, or call the model.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from engine_determinism import NUMERIC_CONTRACT_VERSION, stable_hash
from foundation_snapshot import FoundationTurnSnapshot

ACTOR_RESOLUTION_SCHEMA_VERSION = 1

TIERS = ("hero", "active", "relevant", "dormant", "archived", "unknown")
TIER_RANK = {tier: index for index, tier in enumerate(TIERS)}

# Appendix A.3
TIER_CEILINGS = {
    "hero": 16,
    "active": 200,
    "relevant": 2000,
}

# Appendix A.3 — simulation minutes (v0.1: 1 turn = 60 simulation minutes)
DEMOTION_GRACE_MINUTES = {
    ("hero", "active"): 5,
    ("active", "relevant"): 24 * 60,
    ("relevant", "dormant"): 7 * 24 * 60,
    ("dormant", "archived"): 30 * 24 * 60,
}

RETENTION_TIER_ELIGIBILITY = (
    (0.7, "hero"),
    (0.5, "active"),
    (0.3, "relevant"),
)

GRAVITY_TIER_ELIGIBILITY = (
    (0.8, "hero"),
    (0.5, "active"),
    (0.2, "relevant"),
)

# Appendix A.4 cadence proxy — turns between ordinary actions by tier
TIER_CADENCE_TURNS = {
    "hero": 1,
    "active": 1,
    "relevant": 2,
    "dormant": 4,
    "archived": 99,
    "unknown": 99,
}

SIMULATION_MINUTES_PER_TURN = 60


class ActorResolutionError(ValueError):
    pass


def empty_actor_resolution_state() -> Dict[str, Any]:
    return {
        "schema_version": ACTOR_RESOLUTION_SCHEMA_VERSION,
        "actors": {},
    }


def normalize_actor_resolution_state(raw: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_actor_resolution_state()
    version = int(raw.get("schema_version") or 0)
    if version > ACTOR_RESOLUTION_SCHEMA_VERSION:
        raise ActorResolutionError(
            f"unsupported actor_resolution schema {version} > {ACTOR_RESOLUTION_SCHEMA_VERSION}"
        )
    if version < ACTOR_RESOLUTION_SCHEMA_VERSION:
        return empty_actor_resolution_state()
    return {
        "schema_version": ACTOR_RESOLUTION_SCHEMA_VERSION,
        "actors": copy.deepcopy(raw.get("actors") or {}),
    }


def _simulation_minutes(turn_sequence: int) -> int:
    return max(0, turn_sequence) * SIMULATION_MINUTES_PER_TURN


def _eligible_tier_from_signals(
    *,
    retention_score: float,
    gravity_score: float,
) -> str:
    retention_tier = "dormant"
    for threshold, tier in RETENTION_TIER_ELIGIBILITY:
        if retention_score > threshold:
            retention_tier = tier
            break
    gravity_tier = "dormant"
    for threshold, tier in GRAVITY_TIER_ELIGIBILITY:
        if gravity_score > threshold:
            gravity_tier = tier
            break
    return retention_tier if TIER_RANK[retention_tier] >= TIER_RANK[gravity_tier] else gravity_tier


def _apply_ceiling(
    proposed: Dict[str, str],
    *,
    referenceable_ids: Sequence[str],
) -> Dict[str, str]:
    result = dict(proposed)
    for tier, ceiling in TIER_CEILINGS.items():
        members = [actor_id for actor_id, value in result.items() if value == tier]
        if len(members) <= ceiling:
            continue
        # Demote lowest-gravity actors first (stable sort by actor_id)
        overflow = sorted(members)[ceiling:]
        demote_to = {
            "hero": "active",
            "active": "relevant",
            "relevant": "dormant",
        }.get(tier, "dormant")
        for actor_id in overflow:
            if actor_id not in referenceable_ids:
                result[actor_id] = "unknown"
            else:
                result[actor_id] = demote_to
    return result


def evaluate_actor_resolution(
    snapshot: FoundationTurnSnapshot,
    *,
    prior_state: Optional[Mapping[str, Any]] = None,
    gravity_scores: Optional[Mapping[str, float]] = None,
    retention_scores: Optional[Mapping[str, float]] = None,
) -> Dict[str, Any]:
    """
    Compute tier assignments, acting set, and referenceable registry from snapshot.

    Returns serializable prepared output — not persisted until transaction commit.
    """
    state = normalize_actor_resolution_state(prior_state)
    actors_state = state["actors"]
    gravity_scores = dict(gravity_scores or {})
    retention_scores = dict(retention_scores or {})
    now_minutes = _simulation_minutes(snapshot.turn_sequence)

    referenceable_registry: List[Dict[str, Any]] = []
    proposed_tiers: Dict[str, str] = {}

    for row in snapshot.actor_registry:
        actor_id = str(row.get("actor_id") or "")
        if not actor_id:
            continue
        life_status = str(row.get("life_status") or "alive")
        referenceable = True
        if life_status == "deceased":
            proposed_tiers[actor_id] = "archived"
        else:
            retention = float(retention_scores.get(actor_id, row.get("retention_score", 0.35)))
            gravity = float(gravity_scores.get(actor_id, row.get("gravity_score", 0.25)))
            proposed_tiers[actor_id] = _eligible_tier_from_signals(
                retention_score=retention,
                gravity_score=gravity,
            )
        prior = actors_state.get(actor_id) or {}
        last_interaction_minutes = int(
            prior.get("last_interaction_sim_minutes")
            or row.get("last_interaction_sim_minutes")
            or now_minutes
        )
        current_tier = str(prior.get("tier") or proposed_tiers[actor_id])
        tier_after_grace = _apply_demotion_grace(
            current_tier=current_tier,
            proposed_tier=proposed_tiers[actor_id],
            last_interaction_minutes=last_interaction_minutes,
            now_minutes=now_minutes,
        )
        proposed_tiers[actor_id] = tier_after_grace
        actors_state[actor_id] = {
            "tier": tier_after_grace,
            "last_interaction_sim_minutes": last_interaction_minutes,
            "referenceable": referenceable,
            "life_status": life_status,
        }
        referenceable_registry.append(
            {
                "actor_id": actor_id,
                "display_name": row.get("display_name"),
                "referenceable": referenceable,
                "life_status": life_status,
                "tier": tier_after_grace,
            }
        )

    referenceable_ids = [row["actor_id"] for row in referenceable_registry]
    proposed_tiers = _apply_ceiling(proposed_tiers, referenceable_ids=referenceable_ids)
    for actor_id, tier in proposed_tiers.items():
        if actor_id in actors_state:
            actors_state[actor_id]["tier"] = tier

    acting_set = [
        actor_id
        for actor_id in sorted(proposed_tiers.keys())
        if proposed_tiers[actor_id] in ("hero", "active", "relevant")
        and actors_state.get(actor_id, {}).get("life_status") != "deceased"
    ]

    tier_counts = {tier: 0 for tier in TIERS}
    for tier in proposed_tiers.values():
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    prepared = {
        "schema_version": ACTOR_RESOLUTION_SCHEMA_VERSION,
        "numeric_contract_version": NUMERIC_CONTRACT_VERSION,
        "source_state_hash": snapshot.source_state_hash,
        "referenceable_registry": referenceable_registry,
        "acting_actor_ids": acting_set,
        "tiers_by_actor_id": proposed_tiers,
        "tier_counts": tier_counts,
        "tier_ceilings": dict(TIER_CEILINGS),
        "tier_cadence_turns": dict(TIER_CADENCE_TURNS),
        "prepared_state": state,
        "state_hash": stable_hash(
            "actor_resolution_prepared",
            {
                "acting_actor_ids": acting_set,
                "tiers_by_actor_id": proposed_tiers,
                "source_state_hash": snapshot.source_state_hash,
            },
        ),
    }
    return prepared


def _apply_demotion_grace(
    *,
    current_tier: str,
    proposed_tier: str,
    last_interaction_minutes: int,
    now_minutes: int,
) -> str:
    if TIER_RANK.get(proposed_tier, 99) <= TIER_RANK.get(current_tier, 99):
        return proposed_tier
    transition = (current_tier, proposed_tier)
    grace = DEMOTION_GRACE_MINUTES.get(transition)
    if grace is None:
        return proposed_tier
    elapsed = max(0, now_minutes - last_interaction_minutes)
    if elapsed < grace:
        return current_tier
    return proposed_tier


def is_actor_eligible_for_action(
    actor_id: str,
    prepared: Mapping[str, Any],
    *,
    turn_sequence: int,
    last_action_turn: int = 0,
) -> bool:
    tiers = prepared.get("tiers_by_actor_id") or {}
    tier = tiers.get(actor_id, "unknown")
    if tier not in ("hero", "active", "relevant"):
        return False
    cadence = TIER_CADENCE_TURNS.get(tier, 99)
    return turn_sequence - last_action_turn >= cadence


def provisional_tier_for_comparison(
    npc_id: str,
    display_name: str,
    rolling: Mapping[str, Any],
    turn_number: int,
) -> str:
    """Bridge to legacy npc_world_moves.resolve_actor_tier for equivalence reports."""
    import npc_world_moves as world_moves

    _ = npc_id
    return world_moves.resolve_actor_tier(npc_id, display_name, rolling, turn_number)