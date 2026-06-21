"""
Gravity Governance Layer v0.1 — retention scoring and disposition metadata.

Canon: Source_of_Truth_v1.2.md Ch 26 + Appendix A.2.
Does not delete authoritative truth or select prompt top-N retrieval subsets.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Mapping, Optional, Tuple

from engine_determinism import NUMERIC_CONTRACT_VERSION, reject_non_finite, stable_hash
from foundation_snapshot import FoundationTurnSnapshot

GRAVITY_GOVERNANCE_SCHEMA_VERSION = 1

# Appendix A.2 retention bands
RETENTION_BANDS = (
    (0.8, "keep_active"),
    (0.6, "light_summarisation"),
    (0.4, "compress"),
    (0.2, "archive"),
    (0.0, "eligible_for_deletion"),
)

CONTEXT_BUDGET_MAX_PROTECTED_ITEMS = 512


class GravityGovernanceError(ValueError):
    pass


class GravityBudgetOverflow(GravityGovernanceError):
    pass


def empty_gravity_governance_state() -> Dict[str, Any]:
    return {
        "schema_version": GRAVITY_GOVERNANCE_SCHEMA_VERSION,
        "items": {},
    }


def normalize_gravity_governance_state(raw: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_gravity_governance_state()
    version = int(raw.get("schema_version") or 0)
    if version > GRAVITY_GOVERNANCE_SCHEMA_VERSION:
        raise GravityGovernanceError(
            f"unsupported gravity_governance schema {version} > {GRAVITY_GOVERNANCE_SCHEMA_VERSION}"
        )
    if version < GRAVITY_GOVERNANCE_SCHEMA_VERSION:
        return empty_gravity_governance_state()
    return {
        "schema_version": GRAVITY_GOVERNANCE_SCHEMA_VERSION,
        "items": copy.deepcopy(raw.get("items") or {}),
    }


def compute_retention_score(
    *,
    gravity: float,
    connectivity: float,
    player_relevance: float,
    age_years: float,
) -> float:
    """
    R = G × (1 + 0.5C) × (1 + 0.5P) × D / 2.25, clamped 0–1.
    Appendix A.2 / Ch 26.3.
    """
    reject_non_finite(gravity)
    reject_non_finite(connectivity)
    reject_non_finite(player_relevance)
    reject_non_finite(age_years)
    g = max(0.0, min(1.0, gravity))
    c = max(0.0, min(1.0, connectivity))
    p = max(0.0, min(1.0, player_relevance))
    if g >= 0.7:
        d = min(1.2, 1.0 + age_years / 500.0)
    else:
        d = max(0.8, 1.0 - age_years / 200.0)
    r = g * (1.0 + 0.5 * c) * (1.0 + 0.5 * p) * d / 2.25
    reject_non_finite(r)
    return max(0.0, min(1.0, r))


def retention_band(score: float) -> str:
    reject_non_finite(score)
    for threshold, band in RETENTION_BANDS:
        if score >= threshold:
            return band
    return "eligible_for_deletion"


def player_relevance_factor(days_since_encounter: Optional[float], *, player_exists: bool) -> float:
    if not player_exists or days_since_encounter is None:
        return 0.0
    reject_non_finite(days_since_encounter)
    return math.exp(-days_since_encounter / 7.0)


def evaluate_gravity_governance(
    snapshot: FoundationTurnSnapshot,
    *,
    prior_state: Optional[Mapping[str, Any]] = None,
    items: Optional[Sequence[Mapping[str, Any]]] = None,
    context_budget_items: int = 0,
) -> Dict[str, Any]:
    """
    Evaluate retention metadata for bounded items. No destructive migration in v0.1.
    """
    state = normalize_gravity_governance_state(prior_state)
    evaluated: List[Dict[str, Any]] = []
    protected_count = 0

    candidate_items = list(items or [])
    if not candidate_items:
        candidate_items = _default_items_from_snapshot(snapshot)

    for item in candidate_items:
        item_id = str(item.get("item_id") or "")
        if not item_id:
            continue
        protected = bool(item.get("protected"))
        unresolved = bool(item.get("unresolved_consequence"))
        active_pressure = bool(item.get("active_pressure"))
        secret = bool(item.get("secret"))
        player_created = bool(item.get("player_created"))
        investigation = bool(item.get("active_investigation"))
        defining_scar = bool(item.get("defining_scar"))

        gravity = float(item.get("gravity", 0.3))
        connectivity = float(item.get("connectivity", 0.0))
        age_years = float(item.get("age_years", 0.0))
        days_since = item.get("days_since_player_encounter")
        player_exists = bool(snapshot.actor_resolution_inputs.get("player_location"))
        p_factor = player_relevance_factor(
            float(days_since) if days_since is not None else None,
            player_exists=player_exists,
        )
        score = compute_retention_score(
            gravity=gravity,
            connectivity=connectivity,
            player_relevance=p_factor,
            age_years=age_years,
        )
        if player_created:
            score = max(score, 0.5)
        if investigation:
            score = max(score, 0.6)
        if defining_scar and gravity > 0.7:
            score = max(score, 0.8)
        if unresolved or active_pressure or secret:
            protected = True
            protected_count += 1

        band = retention_band(score)
        if protected and band in ("archive", "eligible_for_deletion"):
            band = "compress" if score >= 0.4 else "light_summarisation"

        disposition = {
            "item_id": item_id,
            "retention_score": score,
            "band": band,
            "protected": protected,
            "source_truth_preserved": True,
        }
        evaluated.append(disposition)
        state["items"][item_id] = disposition

    overflow = False
    if context_budget_items > 0 and protected_count > CONTEXT_BUDGET_MAX_PROTECTED_ITEMS:
        overflow = True
    if overflow and protected_count > context_budget_items:
        raise GravityBudgetOverflow(
            f"protected/unresolved truth ({protected_count}) exceeds context budget ({context_budget_items})"
        )

    prepared = {
        "schema_version": GRAVITY_GOVERNANCE_SCHEMA_VERSION,
        "numeric_contract_version": NUMERIC_CONTRACT_VERSION,
        "source_state_hash": snapshot.source_state_hash,
        "evaluated_count": len(evaluated),
        "protected_count": protected_count,
        "overflow": overflow,
        "dispositions": evaluated,
        "prepared_state": state,
        "state_hash": stable_hash(
            "gravity_governance_prepared",
            {"dispositions": evaluated, "source_state_hash": snapshot.source_state_hash},
        ),
    }
    return prepared


def _default_items_from_snapshot(snapshot: FoundationTurnSnapshot) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for actor in snapshot.actor_registry:
        actor_id = str(actor.get("actor_id") or "")
        if not actor_id:
            continue
        items.append(
            {
                "item_id": f"actor:{actor_id}",
                "kind": "actor",
                "gravity": float(actor.get("gravity_score", 0.25)),
                "connectivity": 0.1 if actor.get("has_relationship") else 0.0,
                "age_years": 0.0,
            }
        )
    for ref in snapshot.confirmed_consequence_refs:
        items.append(
            {
                "item_id": f"consequence:{ref}",
                "kind": "consequence",
                "gravity": 0.55,
                "unresolved_consequence": True,
                "protected": True,
            }
        )
    for node in snapshot.pressure_state_ref.get("nodes") or []:
        if not isinstance(node, dict) or node.get("status") != "active":
            continue
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        items.append(
            {
                "item_id": f"pressure:{node_id}",
                "kind": "pressure",
                "gravity": min(1.0, float(node.get("magnitude", 40)) / 100.0),
                "active_pressure": True,
                "protected": True,
            }
        )
    return items


def retention_scores_by_actor(prepared: Mapping[str, Any]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for row in prepared.get("dispositions") or []:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("item_id") or "")
        if item_id.startswith("actor:"):
            scores[item_id.split(":", 1)[1]] = float(row.get("retention_score", 0.0))
    return scores