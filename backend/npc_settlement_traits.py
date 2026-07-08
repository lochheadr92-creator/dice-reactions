"""
Passive NPC and settlement traits — deterministic, engine-owned metadata.

Traits are seeded at story init from existing setup/state signals. They do not
drive behaviour, prompts, or player-facing payloads in this stage.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from run_identity import select_from_namespace

TRAITS_VERSION = 1

LEVELS = ("low", "medium", "high")

SOCIAL_ROLES = (
    "leader",
    "guardian",
    "operator",
    "mediator",
    "outsider",
    "authority",
    "laborer",
    "witness",
)

LOYALTY_ANCHORS = (
    "player",
    "faction",
    "family",
    "duty",
    "self",
    "place",
)

PERSONAL_STAKES = (
    "survival",
    "reputation",
    "relationship",
    "resources",
    "truth",
    "control",
    "safety",
)

CULTURE_TAGS = (
    "frontier",
    "urban",
    "institutional",
    "maritime",
    "rural",
    "industrial",
    "isolated",
    "cosmopolitan",
)

LOCAL_STAKES = (
    "shelter",
    "supply",
    "order",
    "trade",
    "faith",
    "infrastructure",
    "safety",
    "identity",
)

_GOAL_AMBITION = {
    "gain_influence": "high",
    "remove_rival": "high",
    "secure_resources": "medium",
    "protect_person": "medium",
    "protect_location": "medium",
    "uncover_truth": "medium",
    "escape_danger": "low",
    "repay_debt": "low",
    "preserve_faction": "medium",
    "restore_loss": "medium",
}

_FEAR_LABELS = {
    "abandonment": "abandonment",
    "starvation": "scarcity",
    "exposure": "exposure",
    "loss_of_control": "loss_of_control",
    "betrayal": "betrayal",
    "captivity": "captivity",
    "disgrace": "disgrace",
    "injury": "injury",
    "faction_collapse": "faction_collapse",
    "hidden_truth_revealed": "hidden_truth",
}

_STANCE_RISK = {
    "ally": "low",
    "hostile": "high",
    "neutral": "medium",
    "neutral, suspicious": "high",
    "unknown": "medium",
}


def init_npc_traits_state() -> Dict[str, Any]:
    return {"version": TRAITS_VERSION, "by_npc_id": {}}


def init_settlement_traits_state() -> Dict[str, Any]:
    return {"version": TRAITS_VERSION, "by_location_id": {}}


def canonical_location_id(starting_location: str) -> str:
    text = re.sub(r"\s+", " ", (starting_location or "").strip().lower())[:160]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"loc-{digest[:12]}"


def settlement_row_id(location_id: str) -> str:
    digest = hashlib.sha256(f"settlement:{location_id}".encode("utf-8")).hexdigest()
    return f"settlement-{digest[:12]}"


def _trait_namespace(run_seed: str, entity_id: str, field: str) -> str:
    return hashlib.sha256(f"{run_seed}:{entity_id}:trait:{field}".encode("utf-8")).hexdigest()


def _level_from_namespace(seed_material: str, namespace: str, *, bias: str = "medium") -> str:
    order = list(LEVELS)
    if bias == "low":
        order = ("low", "medium", "high")
    elif bias == "high":
        order = ("high", "medium", "low")
    return select_from_namespace(seed_material, namespace, order)


def derive_npc_traits(
    run_seed: str,
    npc_id: str,
    *,
    display_name: str = "",
    role_hint: str = "",
    stance: str = "",
    agenda: Optional[Mapping[str, Any]] = None,
    relationship: Optional[Mapping[str, Any]] = None,
    identity: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    agenda = agenda or {}
    relationship = relationship or {}
    identity = identity or {}
    mixed = _trait_namespace(run_seed, npc_id, "base")

    goal_kind = str(agenda.get("goal_kind") or "")
    fear_kind = str(agenda.get("fear_kind") or "")
    ambition = _GOAL_AMBITION.get(goal_kind) or _level_from_namespace(mixed, "ambition")
    fear = _FEAR_LABELS.get(fear_kind) or select_from_namespace(mixed, "fear", tuple(_FEAR_LABELS.values()))

    loyalty_anchor = str(agenda.get("loyalty_target_id") or "").strip() or select_from_namespace(
        mixed, "loyalty_anchor", LOYALTY_ANCHORS
    )
    bond = str(relationship.get("bond") or "").strip().lower()
    if bond in ("devoted", "trusted"):
        loyalty_anchor = "player"
    elif bond in ("cowed", "wary"):
        loyalty_anchor = select_from_namespace(mixed, "loyalty_wary", ("self", "place", "faction"))

    stake_shape = str(identity.get("stake_shape") or "")
    personal_stakes = select_from_namespace(mixed, "personal_stakes", PERSONAL_STAKES)
    if stake_shape == "relational":
        personal_stakes = "relationship"
    elif stake_shape == "survival":
        personal_stakes = "survival"
    elif goal_kind in ("protect_person", "protect_location"):
        personal_stakes = "safety"

    rel_state = str(relationship.get("state") or "neutral").lower()
    stance_key = re.sub(r"\s+", " ", (stance or "").strip().lower())
    risk_tolerance = _STANCE_RISK.get(stance_key) or _STANCE_RISK.get(rel_state) or _level_from_namespace(
        mixed, "risk_tolerance"
    )
    if rel_state in ("hostile", "betrayal_risk", "collapsed"):
        risk_tolerance = "high"

    pressure_kind = str(identity.get("primary_pressure_kind") or "resource")
    pressure_sensitivity = _level_from_namespace(
        mixed,
        f"pressure_sensitivity:{pressure_kind}",
        bias="high" if pressure_kind in ("bodily", "environmental") else "medium",
    )

    role_text = (role_hint or "").lower()
    if any(token in role_text for token in ("guard", "soldier", "military", "warden")):
        social_role = "guardian"
    elif any(token in role_text for token in ("leader", "captain", "chief", "mayor")):
        social_role = "leader"
    elif any(token in role_text for token in ("nurse", "doctor", "mediator", "clerk")):
        social_role = "mediator"
    elif any(token in role_text for token in ("merchant", "trader", "engineer", "operator")):
        social_role = "operator"
    else:
        social_role = select_from_namespace(mixed, "social_role", SOCIAL_ROLES)

    return {
        "ambition": ambition,
        "fear": fear,
        "loyalty_anchor": loyalty_anchor,
        "personal_stakes": personal_stakes,
        "risk_tolerance": risk_tolerance,
        "pressure_sensitivity": pressure_sensitivity,
        "social_role": social_role,
        "display_name": (display_name or "")[:80],
    }


def derive_settlement_traits(
    run_seed: str,
    location_id: str,
    *,
    identity: Optional[Mapping[str, Any]] = None,
    opening: Optional[Mapping[str, Any]] = None,
    scenario: Optional[Mapping[str, Any]] = None,
    custom_world_setup: Optional[Mapping[str, Any]] = None,
    setup: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    identity = identity or {}
    opening = opening or {}
    scenario = scenario or {}
    custom_world_setup = custom_world_setup if isinstance(custom_world_setup, dict) else {}
    setup = setup or {}
    mixed = _trait_namespace(run_seed, location_id, "settlement")

    scarcity = str(identity.get("scarcity_axis") or "food")
    prosperity = "low" if scarcity in ("medicine", "food", "fuel", "shelter") else "medium"
    if scarcity in ("trust", "information"):
        prosperity = "medium"
    prosperity = _level_from_namespace(mixed, f"prosperity:{scarcity}", bias=prosperity)

    tension = str(identity.get("tension_profile") or "slow_burn")
    stability = "low" if tension in ("volatile", "acute") else "medium"
    if tension == "slow_burn":
        stability = "high"
    stability = _level_from_namespace(mixed, f"stability:{tension}", bias=stability)

    hidden = bool(setup.get("hidden_threat") or scenario.get("hidden_threat"))
    fear = "high" if hidden else _level_from_namespace(mixed, "settlement_fear", bias="medium")

    complication = str(identity.get("complication_style") or "social")
    crime = "high" if complication in ("political", "social") else "medium"
    if complication == "environmental":
        crime = "low"
    crime = _level_from_namespace(mixed, f"crime:{complication}", bias=crime)

    genre = str(setup.get("genre") or scenario.get("genre") or "").lower()
    tone = str(setup.get("tone") or scenario.get("tone") or "").lower()
    if "urban" in genre or "city" in tone:
        culture_tag = "urban"
    elif "frontier" in genre or "western" in genre:
        culture_tag = "frontier"
    elif "maritime" in genre or "sea" in genre or "coast" in tone:
        culture_tag = "maritime"
    elif "post-apocalyptic" in genre or "isolated" in tone:
        culture_tag = "isolated"
    else:
        culture_tag = select_from_namespace(mixed, "culture_tag", CULTURE_TAGS)

    dominant_pressure = str(identity.get("primary_pressure_kind") or "resource")

    threatened = str(opening.get("threatened_resource") or "").strip().lower()
    local_stakes = select_from_namespace(mixed, "local_stakes", LOCAL_STAKES)
    if threatened:
        if any(token in threatened for token in ("water", "food", "fuel", "medicine")):
            local_stakes = "supply"
        elif any(token in threatened for token in ("shelter", "home", "house")):
            local_stakes = "shelter"
        elif any(token in threatened for token in ("order", "law", "safety")):
            local_stakes = "order"

    return {
        "prosperity": prosperity,
        "stability": stability,
        "fear": fear,
        "crime": crime,
        "culture_tag": culture_tag,
        "dominant_pressure": dominant_pressure,
        "local_stakes": local_stakes,
        "settlement_id": settlement_row_id(location_id),
    }


def seed_npc_traits(
    run_seed: str,
    npc_records: Sequence[Mapping[str, Any]],
    *,
    agendas_state: Optional[Mapping[str, Any]] = None,
    identity: Optional[Mapping[str, Any]] = None,
    relationship_vectors: Optional[Sequence[Mapping[str, Any]]] = None,
    scenario_id: str = "",
) -> Dict[str, Any]:
    import npc_agendas  # noqa: WPS433 — local import avoids cycle at load

    state = init_npc_traits_state()
    agendas_by_id = {
        str(row.get("npc_id")): row
        for row in (agendas_state or {}).get("active") or []
        if isinstance(row, dict) and row.get("npc_id")
    }
    rel_by_name = {
        npc_agendas.normalize_npc_name(str(v.get("name", ""))): v
        for v in relationship_vectors or []
        if isinstance(v, dict) and v.get("name")
    }
    for idx, raw in enumerate(npc_records or []):
        if not isinstance(raw, dict):
            continue
        npc_id = str(raw.get("npc_id") or "").strip()
        if not npc_id.startswith("npc-"):
            npc_id = npc_agendas.derive_canonical_npc_id(
                raw, source_slot=idx, scenario_id=scenario_id
            ) or ""
        if not npc_id:
            continue
        name = str(raw.get("name") or raw.get("display_name") or "").strip()
        rel = rel_by_name.get(npc_agendas.normalize_npc_name(name), {})
        state["by_npc_id"][npc_id] = derive_npc_traits(
            run_seed,
            npc_id,
            display_name=name,
            role_hint=str(raw.get("role") or "")[:80],
            stance=str(raw.get("stance") or ""),
            agenda=agendas_by_id.get(npc_id),
            relationship=rel,
            identity=identity,
        )
    return state


def seed_settlement_traits(
    run_seed: str,
    *,
    identity: Optional[Mapping[str, Any]] = None,
    opening: Optional[Mapping[str, Any]] = None,
    scenario: Optional[Mapping[str, Any]] = None,
    custom_world_setup: Optional[Mapping[str, Any]] = None,
    setup: Optional[Mapping[str, Any]] = None,
    starting_location: str = "",
) -> Dict[str, Any]:
    state = init_settlement_traits_state()
    location_text = starting_location
    if not location_text and isinstance(scenario, dict):
        location_text = str(scenario.get("starting_location") or "")
    if not location_text and isinstance(custom_world_setup, dict):
        location_text = str(custom_world_setup.get("starting_location") or custom_world_setup.get("location") or "")
    location_id = canonical_location_id(location_text or run_seed)
    state["by_location_id"][location_id] = derive_settlement_traits(
        run_seed,
        location_id,
        identity=identity,
        opening=opening,
        scenario=scenario,
        custom_world_setup=custom_world_setup,
        setup=setup,
    )
    return state


def seed_traits_for_new_story(
    *,
    run_seed: str,
    identity: Mapping[str, Any],
    opening: Mapping[str, Any],
    npc_seed_records: Sequence[Mapping[str, Any]],
    agendas_state: Optional[Mapping[str, Any]],
    scenario: Optional[Mapping[str, Any]] = None,
    custom_world_setup: Optional[Mapping[str, Any]] = None,
    setup: Optional[Mapping[str, Any]] = None,
    scenario_id: str = "",
) -> Dict[str, Any]:
    npc_traits = seed_npc_traits(
        run_seed,
        npc_seed_records,
        agendas_state=agendas_state,
        identity=identity,
        scenario_id=scenario_id,
    )
    settlement_traits = seed_settlement_traits(
        run_seed,
        identity=identity,
        opening=opening,
        scenario=scenario,
        custom_world_setup=custom_world_setup,
        setup=setup,
        starting_location=str((scenario or {}).get("starting_location") or ""),
    )
    return {"npc_traits": npc_traits, "settlement_traits": settlement_traits}