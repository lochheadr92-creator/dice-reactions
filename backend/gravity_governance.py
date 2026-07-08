"""
Gravity Governance Layer v0.1 — retention scoring and disposition metadata.

Canon: Source_of_Truth_v1.2.md Ch 26 + Appendix A.2.
Does not delete authoritative truth or select prompt top-N retrieval subsets.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Sequence
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

# Stage 6D-1B designed-extension weights. These are intentionally small,
# deterministic, and clamped before they enter the canonical retention formula.
MAX_TRAIT_GRAVITY_MODIFIER = 0.08
MAX_TRAIT_CONNECTIVITY_MODIFIER = 0.05

NPC_TRAIT_GRAVITY_WEIGHTS = {
    "ambition": 0.025,
    "risk_tolerance": 0.015,
    "pressure_sensitivity": 0.020,
    "personal_stakes": 0.012,
    "fear_match": 0.018,
}

NPC_TRAIT_CONNECTIVITY_WEIGHTS = {
    "loyalty_anchor": 0.012,
    "social_role": 0.012,
}

SETTLEMENT_TRAIT_GRAVITY_WEIGHTS = {
    "dominant_pressure_match": 0.020,
    "prosperity": 0.018,
    "stability": 0.018,
    "crime": 0.016,
}

SETTLEMENT_TRAIT_CONNECTIVITY_WEIGHTS = {
    "local_stakes_match": 0.016,
}

_LEVEL_SIGNAL = {"low": -1.0, "medium": 0.0, "high": 1.0}
_LOW_LEVEL_SIGNIFICANCE = {"low": 1.0, "medium": 0.0, "high": -0.5}
_HIGH_LEVEL_SIGNIFICANCE = {"low": -0.5, "medium": 0.0, "high": 1.0}

_PERSONAL_STAKE_SIGNAL = {
    "survival": 1.0,
    "safety": 1.0,
    "truth": 0.8,
    "relationship": 0.6,
    "resources": 0.6,
    "control": 0.5,
    "reputation": 0.4,
}

_LOYALTY_ANCHOR_SIGNAL = {
    "player": 1.0,
    "family": 0.7,
    "duty": 0.7,
    "place": 0.6,
    "faction": 0.5,
    "self": -0.3,
}

_SOCIAL_ROLE_SIGNAL = {
    "leader": 1.0,
    "authority": 0.9,
    "guardian": 0.8,
    "mediator": 0.6,
    "operator": 0.5,
    "witness": 0.5,
    "laborer": 0.2,
    "outsider": 0.1,
}

_FEAR_MATCH_TOKENS = {
    "abandonment": ("abandon", "alone", "left behind"),
    "scarcity": ("scarcity", "starv", "food", "water", "fuel", "medicine", "supply"),
    "exposure": ("exposure", "shelter", "cold", "storm", "weather"),
    "loss_of_control": ("control", "order", "chaos", "command"),
    "betrayal": ("betray", "traitor", "deceive", "double-cross"),
    "captivity": ("captive", "prison", "locked", "trapped"),
    "disgrace": ("disgrace", "shame", "humiliation", "reputation"),
    "injury": ("injury", "wound", "hurt", "blood", "violence"),
    "faction_collapse": ("faction", "collapse", "mutiny", "split"),
    "hidden_truth": ("truth", "secret", "revealed", "evidence"),
}

_STAKE_MATCH_TOKENS = {
    "shelter": ("shelter", "home", "house", "refuge"),
    "supply": ("supply", "food", "water", "fuel", "medicine", "resource"),
    "order": ("order", "law", "guard", "safety", "crime"),
    "trade": ("trade", "market", "merchant", "goods"),
    "faith": ("faith", "temple", "priest", "ritual"),
    "infrastructure": ("bridge", "road", "power", "infrastructure"),
    "safety": ("safety", "danger", "threat", "violence"),
    "identity": ("identity", "culture", "name", "heritage"),
}


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


def trait_significance_modifier(
    item: Mapping[str, Any],
    *,
    npc_trait_refs: Optional[Mapping[str, Any]] = None,
    settlement_trait_refs: Optional[Mapping[str, Any]] = None,
    location_ref: str = "",
) -> Dict[str, float]:
    """Bounded deterministic modifier derived from existing trait records."""
    if not isinstance(item, Mapping):
        return {"gravity": 0.0, "connectivity": 0.0}

    text = _item_match_text(item)
    gravity_delta = 0.0
    connectivity_delta = 0.0

    npc_traits = _npc_traits_for_item(item, npc_trait_refs)
    if npc_traits:
        gravity_delta += _level_signal(npc_traits.get("ambition")) * NPC_TRAIT_GRAVITY_WEIGHTS["ambition"]
        gravity_delta += _level_signal(npc_traits.get("risk_tolerance")) * NPC_TRAIT_GRAVITY_WEIGHTS["risk_tolerance"]
        gravity_delta += _level_signal(npc_traits.get("pressure_sensitivity")) * NPC_TRAIT_GRAVITY_WEIGHTS["pressure_sensitivity"]
        gravity_delta += _mapped_signal(
            npc_traits.get("personal_stakes"),
            _PERSONAL_STAKE_SIGNAL,
        ) * NPC_TRAIT_GRAVITY_WEIGHTS["personal_stakes"]
        if _matches_trait_tokens(npc_traits.get("fear"), text, _FEAR_MATCH_TOKENS):
            gravity_delta += NPC_TRAIT_GRAVITY_WEIGHTS["fear_match"]
        connectivity_delta += _mapped_signal(
            npc_traits.get("loyalty_anchor"),
            _LOYALTY_ANCHOR_SIGNAL,
        ) * NPC_TRAIT_CONNECTIVITY_WEIGHTS["loyalty_anchor"]
        connectivity_delta += _mapped_signal(
            npc_traits.get("social_role"),
            _SOCIAL_ROLE_SIGNAL,
        ) * NPC_TRAIT_CONNECTIVITY_WEIGHTS["social_role"]

    settlement_traits = _settlement_traits_for_item(
        item,
        settlement_trait_refs,
        location_ref=location_ref,
    )
    if settlement_traits:
        if _matches_trait_tokens(settlement_traits.get("dominant_pressure"), text):
            gravity_delta += SETTLEMENT_TRAIT_GRAVITY_WEIGHTS["dominant_pressure_match"]
        gravity_delta += _low_level_significance(
            settlement_traits.get("prosperity")
        ) * SETTLEMENT_TRAIT_GRAVITY_WEIGHTS["prosperity"]
        gravity_delta += _low_level_significance(
            settlement_traits.get("stability")
        ) * SETTLEMENT_TRAIT_GRAVITY_WEIGHTS["stability"]
        gravity_delta += _high_level_significance(
            settlement_traits.get("crime")
        ) * SETTLEMENT_TRAIT_GRAVITY_WEIGHTS["crime"]
        if _matches_trait_tokens(
            settlement_traits.get("local_stakes"),
            text,
            _STAKE_MATCH_TOKENS,
        ):
            connectivity_delta += SETTLEMENT_TRAIT_CONNECTIVITY_WEIGHTS["local_stakes_match"]

    return {
        "gravity": _clamp_modifier(gravity_delta, MAX_TRAIT_GRAVITY_MODIFIER),
        "connectivity": _clamp_modifier(connectivity_delta, MAX_TRAIT_CONNECTIVITY_MODIFIER),
    }


def evaluate_gravity_governance(
    snapshot: FoundationTurnSnapshot,
    *,
    prior_state: Optional[Mapping[str, Any]] = None,
    items: Optional[Sequence[Mapping[str, Any]]] = None,
    context_budget_items: int = 0,
    trait_significance_enabled: bool = False,
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

    trait_modified_count = 0
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
        if trait_significance_enabled:
            modifier = trait_significance_modifier(
                item,
                npc_trait_refs=snapshot.npc_trait_refs,
                settlement_trait_refs=snapshot.settlement_trait_refs,
                location_ref=snapshot.location_ref,
            )
            if modifier["gravity"] or modifier["connectivity"]:
                trait_modified_count += 1
            gravity = max(0.0, min(1.0, gravity + modifier["gravity"]))
            connectivity = max(0.0, min(1.0, connectivity + modifier["connectivity"]))
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
    if trait_significance_enabled and trait_modified_count:
        prepared["trait_modified_count"] = trait_modified_count
        prepared["trait_modifier_bounds"] = {
            "gravity": MAX_TRAIT_GRAVITY_MODIFIER,
            "connectivity": MAX_TRAIT_CONNECTIVITY_MODIFIER,
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
                "actor_id": actor_id,
                "display_name": actor.get("display_name"),
                "location_id": actor.get("location_id"),
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
                "pressure_kind": node.get("kind"),
                "location_ids": list(node.get("location_ids") or []),
                "gravity": min(1.0, float(node.get("magnitude", 40)) / 100.0),
                "active_pressure": True,
                "protected": True,
            }
        )
    return items


def _clamp_modifier(value: float, limit: float) -> float:
    reject_non_finite(value)
    return round(max(-limit, min(limit, value)), 6)


def _level_signal(value: Any) -> float:
    return _LEVEL_SIGNAL.get(str(value or "").strip().lower(), 0.0)


def _low_level_significance(value: Any) -> float:
    return _LOW_LEVEL_SIGNIFICANCE.get(str(value or "").strip().lower(), 0.0)


def _high_level_significance(value: Any) -> float:
    return _HIGH_LEVEL_SIGNIFICANCE.get(str(value or "").strip().lower(), 0.0)


def _mapped_signal(value: Any, mapping: Mapping[str, float]) -> float:
    return float(mapping.get(str(value or "").strip().lower(), 0.0))


def _normalise_text(value: Any) -> str:
    return " ".join(str(value or "").replace("_", " ").strip().lower().split())


def _item_match_text(item: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key in (
        "item_id",
        "kind",
        "actor_id",
        "npc_id",
        "display_name",
        "name",
        "title",
        "description",
        "label",
        "event",
        "pressure_kind",
        "target_type",
        "target_id",
    ):
        if item.get(key):
            parts.append(str(item.get(key)))
    for key in ("location_ids", "involved_locations", "target_location_ids"):
        values = item.get(key)
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            parts.extend(str(value) for value in values if value)
    remembers = item.get("remembers")
    if isinstance(remembers, Sequence) and not isinstance(remembers, (str, bytes)):
        for row in remembers:
            if isinstance(row, Mapping):
                parts.append(str(row.get("event") or ""))
                parts.append(str(row.get("severity") or ""))
    return _normalise_text(" ".join(parts))


def _matches_trait_tokens(
    value: Any,
    text: str,
    token_map: Optional[Mapping[str, Sequence[str]]] = None,
) -> bool:
    key = _normalise_text(value)
    if not key or not text:
        return False
    if key in text:
        return True
    if token_map:
        lookup_key = str(value or "").strip().lower()
        for token in token_map.get(lookup_key, ()):
            if _normalise_text(token) in text:
                return True
    return False


def _trait_index(refs: Optional[Mapping[str, Any]], index_key: str) -> Dict[str, Mapping[str, Any]]:
    if not isinstance(refs, Mapping):
        return {}
    raw = refs.get(index_key) if isinstance(refs.get(index_key), Mapping) else refs
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(key): value
        for key, value in raw.items()
        if isinstance(value, Mapping)
    }


def _npc_traits_for_item(
    item: Mapping[str, Any],
    refs: Optional[Mapping[str, Any]],
) -> Optional[Mapping[str, Any]]:
    rows = _trait_index(refs, "by_npc_id")
    if not rows:
        return None
    ids = [
        item.get("npc_id"),
        item.get("actor_id"),
    ]
    item_id = str(item.get("item_id") or "")
    if item_id.startswith("actor:"):
        ids.append(item_id.split(":", 1)[1])
    for candidate in ids:
        key = str(candidate or "")
        if key in rows:
            return rows[key]

    name = _normalise_text(item.get("display_name") or item.get("name") or "")
    if not name:
        return None
    matches = [
        row
        for row in rows.values()
        if _normalise_text(row.get("display_name") or "") == name
    ]
    return matches[0] if len(matches) == 1 else None


def _settlement_traits_for_item(
    item: Mapping[str, Any],
    refs: Optional[Mapping[str, Any]],
    *,
    location_ref: str = "",
) -> Optional[Mapping[str, Any]]:
    rows = _trait_index(refs, "by_location_id")
    if not rows:
        return None
    candidates = [
        item.get("location_id"),
        location_ref,
    ]
    for key in ("location_ids", "involved_locations", "target_location_ids"):
        values = item.get(key)
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            candidates.extend(values)
    for candidate in candidates:
        key = str(candidate or "")
        if key in rows:
            return rows[key]
    if len(rows) == 1:
        return next(iter(rows.values()))
    return None


def retention_scores_by_actor(prepared: Mapping[str, Any]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for row in prepared.get("dispositions") or []:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("item_id") or "")
        if item_id.startswith("actor:"):
            scores[item_id.split(":", 1)[1]] = float(row.get("retention_score", 0.0))
    return scores
