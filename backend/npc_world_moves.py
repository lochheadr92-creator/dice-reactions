"""
Living Cast local move eligibility and scoring v1.

Bounded move catalog with real state effects. This module provides local
tier eligibility and utility scoring — not PRD Ch 25 Actor Resolution or
Ch 27 Utility AI. No canonical event-sourcing module exists; committed moves
record bounded transition receipts in replayability_state only.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Tuple

import npc_agendas as agendas
import npc_liveness
import pressure_graph

NPC_WORLD_MOVE_MARKER = "[NPC_WORLD_MOVE_V1]"
NPC_MOVE_RECEIPT_VERSION = 1
MAX_CANDIDATES = 8
MAX_NPC_MOVE_RECEIPTS = 24
MAX_RELATIONSHIP_EFFECT_RECEIPTS = 32

EFFECT_TYPES = (
    "relationship_delta",
    "faction_tick",
    "pressure_magnitude",
    "agenda_progress",
)

TARGET_TYPES = ("player", "npc", "faction", "location", "pressure", "opening_fact")

ACTOR_TIERS = ("hero", "active", "relevant", "dormant", "archived", "unknown")
TIER_PRIORITY = {"hero": 40, "active": 30, "relevant": 18, "dormant": 5, "archived": 0, "unknown": 0}
TIER_CADENCE = {"hero": 1, "active": 1, "relevant": 2, "dormant": 4, "archived": 99, "unknown": 99}

MOVE_KINDS = (
    "gather",
    "protect",
    "investigate",
    "negotiate",
    "pressure",
    "conceal",
    "fortify",
    "withdraw",
    "defect",
)

MOVE_GOAL_ALIGN = {
    "gather": frozenset({"secure_resources", "restore_loss", "repay_debt"}),
    "protect": frozenset({"protect_person", "protect_location", "preserve_faction"}),
    "investigate": frozenset({"uncover_truth", "remove_rival"}),
    "negotiate": frozenset({"gain_influence", "repay_debt", "preserve_faction"}),
    "pressure": frozenset({"remove_rival", "gain_influence"}),
    "conceal": frozenset({"secure_resources", "escape_danger"}),
    "fortify": frozenset({"protect_location", "preserve_faction"}),
    "withdraw": frozenset({"escape_danger", "protect_person"}),
    "defect": frozenset({"preserve_faction", "escape_danger"}),
}

MOVE_MIN_TIER = {
    "gather": "relevant",
    "protect": "active",
    "investigate": "relevant",
    "negotiate": "active",
    "pressure": "active",
    "conceal": "relevant",
    "fortify": "active",
    "withdraw": "relevant",
    "defect": "active",
}

OBSERVABLE_TEMPLATES = {
    "gather_resource": "Someone secures or consolidates scarce supplies nearby.",
    "protect_player": "Someone takes a protective stance toward the player.",
    "protect_location": "Someone reinforces vigilance over a specific place.",
    "protect_faction": "Someone rallies support for a faction's position.",
    "investigate_opening": "Someone probes an unresolved opening tension.",
    "investigate_pressure": "Someone pursues answers tied to active pressure.",
    "negotiate_faction": "Someone opens or presses a negotiation with a faction.",
    "pressure_player": "Someone applies visible social pressure toward the player.",
    "conceal_from_player": "Someone withholds something important from the player.",
    "fortify_pressure": "Someone hardens defences against an active threat.",
    "withdraw_location": "Someone pulls back from the current location.",
    "defect_faction": "Someone's allegiance visibly shifts toward another faction.",
}


def _tier_rank(tier: str) -> int:
    order = {t: i for i, t in enumerate(ACTOR_TIERS)}
    return order.get(tier, 99)


def resolve_actor_tier(
    npc_id: str,
    display_name: str,
    rolling: Mapping[str, Any],
    turn_number: int,
) -> str:
    """
    Local tier eligibility from rolling_state registries only.

    Sources: deceased registry, npcs[], npc_memory[], relationship_vectors[].
    Unknown/ungrounded actors are ineligible (unknown tier).
    """
    _ = npc_id
    name_key = agendas.normalize_npc_name(display_name)
    if not name_key:
        return "unknown"

    deceased = {agendas.normalize_npc_name(str(d)) for d in (rolling.get("deceased") or [])}
    if name_key in deceased:
        return "archived"

    in_npcs = False
    stance = ""
    last_seen = ""
    for row in rolling.get("npcs") or []:
        if isinstance(row, dict) and agendas.normalize_npc_name(str(row.get("name", ""))) == name_key:
            in_npcs = True
            stance = str(row.get("stance") or "")
            last_seen = str(row.get("last_seen") or "")
            break

    recent_memory = False
    for row in rolling.get("npc_memory") or []:
        if not isinstance(row, dict):
            continue
        if agendas.normalize_npc_name(str(row.get("name", ""))) != name_key:
            continue
        for mem in row.get("remembers") or []:
            if isinstance(mem, dict) and int(mem.get("since_turn") or 0) >= turn_number - 3:
                recent_memory = True
                break

    has_relationship = any(
        isinstance(v, dict) and agendas.normalize_npc_name(str(v.get("name", ""))) == name_key
        for v in rolling.get("relationship_vectors") or []
    )

    if not in_npcs and not recent_memory and not has_relationship:
        return "unknown"

    if in_npcs and (stance in ("ally", "hostile") or last_seen or recent_memory):
        return "hero"
    if in_npcs:
        return "active"
    if recent_memory or has_relationship:
        return "relevant"
    return "dormant"


def _cadence_allows(tier: str, agenda: Mapping[str, Any], turn_number: int) -> bool:
    if tier in ("archived", "unknown"):
        return False
    cadence = TIER_CADENCE.get(tier, 99)
    last = int(agenda.get("last_move_turn") or 0)
    return turn_number - last >= cadence


def _faction_id(name: str) -> str:
    norm = agendas.normalize_npc_name(name)
    digest = hashlib.sha256(f"faction:{norm}".encode("utf-8")).hexdigest()
    return f"faction-{digest[:12]}"


def _location_id(rolling: Mapping[str, Any]) -> Optional[str]:
    scene = str(rolling.get("scene") or rolling.get("location") or "").strip()
    if scene:
        digest = hashlib.sha256(f"location:{agendas.normalize_npc_name(scene)}".encode()).hexdigest()
        return f"location-{digest[:12]}"
    rooms = rolling.get("known_rooms") or []
    if rooms and isinstance(rooms[0], str) and rooms[0].strip():
        digest = hashlib.sha256(
            f"location:{agendas.normalize_npc_name(rooms[0])}".encode("utf-8")
        ).hexdigest()
        return f"location-{digest[:12]}"
    return None


def _player_present(rolling: Mapping[str, Any]) -> bool:
    return bool(str(rolling.get("scene") or rolling.get("location") or "").strip())


def _active_pressure_nodes(
    replayability_state: Mapping[str, Any],
    *,
    kind: Optional[str] = None,
) -> List[Dict[str, Any]]:
    pg = replayability_state.get("pressure_graph") or {}
    out = []
    for node in pg.get("nodes") or []:
        if not isinstance(node, dict) or node.get("status") != "active":
            continue
        if kind and node.get("kind") != kind:
            continue
        out.append(node)
    return out


def _opening_fact_target(replayability_state: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
    opening = replayability_state.get("opening") or {}
    fact_ids = opening.get("fact_ids") or {}
    tension_id = str(fact_ids.get("tension") or "").strip()
    if tension_id:
        return ("opening_fact", tension_id)
    return None


def resolve_move_target(
    move_kind: str,
    agenda: Mapping[str, Any],
    rolling: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
) -> Optional[Tuple[str, str]]:
    """Resolve bounded target from authoritative state. None means ineligible."""
    goal = str(agenda.get("goal_kind") or "")

    if move_kind == "gather":
        nodes = _active_pressure_nodes(replayability_state, kind="resource")
        if nodes:
            return ("pressure", str(nodes[0]["id"]))
        return None

    if move_kind == "protect":
        if goal == "protect_person" and _player_present(rolling):
            return ("player", "player")
        if goal == "protect_location":
            loc = _location_id(rolling)
            if loc:
                return ("location", loc)
        if goal == "preserve_faction":
            factions = rolling.get("faction_pressure") or []
            if factions and isinstance(factions[0], dict) and factions[0].get("name"):
                return ("faction", _faction_id(str(factions[0]["name"])))
        if _player_present(rolling):
            return ("player", "player")
        return None

    if move_kind == "investigate":
        if goal not in MOVE_GOAL_ALIGN["investigate"]:
            return None
        opening = _opening_fact_target(replayability_state)
        if opening:
            return opening
        nodes = _active_pressure_nodes(replayability_state)
        if nodes:
            return ("pressure", str(nodes[0]["id"]))
        return None

    if move_kind == "negotiate":
        factions = rolling.get("faction_pressure") or []
        if factions and isinstance(factions[0], dict) and factions[0].get("name"):
            return ("faction", _faction_id(str(factions[0]["name"])))
        return None

    if move_kind == "pressure":
        if not _player_present(rolling):
            return None
        vec, err = agendas.resolve_relationship_vector(
            str(agenda.get("npc_id") or ""), agenda, rolling
        )
        if err or not vec:
            return None
        return ("player", "player")

    if move_kind == "conceal":
        if not _player_present(rolling):
            return None
        vec, err = agendas.resolve_relationship_vector(
            str(agenda.get("npc_id") or ""), agenda, rolling
        )
        if err or not vec or int(vec.get("trust") or 0) <= 0:
            return None
        return ("player", "player")

    if move_kind == "fortify":
        nodes = _active_pressure_nodes(replayability_state, kind="environmental")
        if nodes:
            return ("pressure", str(nodes[0]["id"]))
        loc = _location_id(rolling)
        if loc:
            return ("location", loc)
        return None

    if move_kind == "withdraw":
        loc = _location_id(rolling)
        if not loc:
            return None
        vec, err = agendas.resolve_relationship_vector(
            str(agenda.get("npc_id") or ""), agenda, rolling
        )
        if err or not vec:
            return None
        return ("location", loc)

    if move_kind == "defect":
        if not (agenda.get("breaking_fired") or agenda.get("status") == "breaking"):
            return None
        factions = rolling.get("faction_pressure") or []
        if factions and isinstance(factions[0], dict) and factions[0].get("name"):
            return ("faction", _faction_id(str(factions[0]["name"])))
        return None

    return None


def observable_template_id(move_kind: str, target_type: str, target_id: str) -> str:
    if move_kind == "gather":
        return "gather_resource"
    if move_kind == "protect":
        if target_type == "player":
            return "protect_player"
        if target_type == "location":
            return "protect_location"
        if target_type == "faction":
            return "protect_faction"
    if move_kind == "investigate":
        return "investigate_opening" if target_type == "opening_fact" else "investigate_pressure"
    if move_kind == "negotiate":
        return "negotiate_faction"
    if move_kind == "pressure":
        return "pressure_player"
    if move_kind == "conceal":
        return "conceal_from_player"
    if move_kind == "fortify":
        return "fortify_pressure"
    if move_kind == "withdraw":
        return "withdraw_location"
    if move_kind == "defect":
        return "defect_faction"
    return f"{move_kind}_{target_type}"


def build_effect_ids(move_kind: str, target_type: str, target_id: str) -> List[str]:
    return [f"fx:{move_kind}:{target_type}:{target_id}"]


def _effect_id(move_kind: str, effect_type: str, target_id: str, *, dimension: str = "") -> str:
    suffix = f":{dimension}" if dimension else ""
    return f"fx:{move_kind}:{effect_type}:{target_id}{suffix}"


def _relationship_deltas_for_move(
    move_kind: str,
    target_type: str,
) -> Dict[str, int]:
    if move_kind == "protect" and target_type == "player":
        return {"loyalty": 6, "trust": 4}
    if move_kind == "pressure" and target_type == "player":
        return {"fear": 5, "resentment": 4}
    if move_kind == "withdraw" and target_type == "location":
        return {"trust": -3}
    if move_kind == "conceal" and target_type == "player":
        return {"trust": -3}
    if move_kind == "defect" and target_type == "faction":
        return {"loyalty": -10, "resentment": 8}
    return {}


def stable_receipt_id(
    run_seed: str,
    npc_id: str,
    agenda_id_value: str,
    move_kind: str,
    turn_number: int,
    target_id: str,
) -> str:
    digest = hashlib.sha256(
        f"{run_seed}:{npc_id}:{agenda_id_value}:{move_kind}:{turn_number}:{target_id}".encode()
    ).hexdigest()
    return f"npc-move-{digest[:12]}"


def score_move(
    move_kind: str,
    agenda: Mapping[str, Any],
    *,
    tier: str,
    target_type: str,
    target_id: str,
    rolling: Mapping[str, Any],
    identity: Mapping[str, Any],
    turn_number: int,
) -> int:
    """Local deterministic utility score — subtracts for repetition/recency."""
    if move_kind not in MOVE_KINDS:
        return -1
    if tier in ("archived", "unknown"):
        return -1
    min_tier = MOVE_MIN_TIER.get(move_kind, "active")
    if _tier_rank(tier) > _tier_rank(min_tier):
        return -1
    goals = MOVE_GOAL_ALIGN.get(move_kind, frozenset())
    if agenda.get("goal_kind") not in goals:
        return -1
    if not target_type or not target_id:
        return -1

    score = TIER_PRIORITY.get(tier, 0)
    if agenda.get("goal_kind") in goals:
        score += 20
    fear = str(agenda.get("fear_kind") or "")
    if move_kind == "withdraw" and fear in ("captivity", "injury", "abandonment"):
        score += 12
    if move_kind == "conceal" and fear in ("exposure", "hidden_truth_revealed"):
        score += 10
    if move_kind == "defect" and agenda.get("breaking_fired"):
        score += 25

    vec, _ = agendas.resolve_relationship_vector(
        str(agenda.get("npc_id") or ""), agenda, rolling
    )
    if vec:
        resentment = int(vec.get("resentment") or 0)
        loyalty = int(vec.get("loyalty") or 0)
        if move_kind == "pressure":
            score += min(15, resentment // 5)
        if move_kind == "protect" and target_type == "player":
            score += min(12, loyalty // 8)

    if identity.get("echo_bias") == "betrayals" and move_kind == "defect":
        score += 6
    if identity.get("primary_pressure_kind") == "social" and move_kind in ("negotiate", "pressure"):
        score += 5

    last = int(agenda.get("last_move_turn") or 0)
    if turn_number - last <= 2:
        score -= 15

    return score


def receipt_to_stub(receipt: Mapping[str, Any]) -> Dict[str, Any]:
    """Minimal receipt summary — effects[] intentionally omitted."""
    return {
        "version": receipt.get("version", NPC_MOVE_RECEIPT_VERSION),
        "receipt_id": receipt.get("receipt_id"),
        "receipt_type": receipt.get("receipt_type"),
        "turn": receipt.get("turn"),
        "npc_id": receipt.get("npc_id"),
        "agenda_id": receipt.get("agenda_id"),
        "move_kind": receipt.get("move_kind"),
        "target_type": receipt.get("target_type"),
        "target_id": receipt.get("target_id"),
        "effect_ids": list(receipt.get("effect_ids") or []),
        "compressed": True,
    }


def enforce_npc_move_receipt_cap(receipts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Hard cap for npc_move_receipts.

    Policy:
    - Never exceed MAX_NPC_MOVE_RECEIPTS entries.
    - Compress oldest full receipts to stubs (drop effects[]) first.
    - Drop oldest stubs when still over cap.
    - Echoes retain required identity via source_provenance on the echo record;
      receipt storage does not grow because echoes reference old receipts.
    """
    out = [dict(r) for r in receipts]
    while len(out) > MAX_NPC_MOVE_RECEIPTS:
        compress_idx = next(
            (i for i, r in enumerate(out) if not r.get("compressed")),
            None,
        )
        if compress_idx is not None:
            out[compress_idx] = receipt_to_stub(out[compress_idx])
            continue
        out.pop(0)
    return out


def append_npc_move_receipt(
    replayability_state: Dict[str, Any],
    receipt: Mapping[str, Any],
) -> bool:
    """Bounded transition receipt — not canonical event history."""
    receipts = replayability_state.setdefault("npc_move_receipts", [])
    rid = receipt.get("receipt_id")
    if rid and any(isinstance(r, dict) and r.get("receipt_id") == rid for r in receipts):
        return False
    receipts.append(dict(receipt))
    if len(receipts) > MAX_NPC_MOVE_RECEIPTS:
        replayability_state["npc_move_receipts"] = enforce_npc_move_receipt_cap(receipts)
    return True


def _find_faction_row(rolling: Mapping[str, Any], faction_target_id: str) -> Optional[Dict[str, Any]]:
    for fac in rolling.get("faction_pressure") or []:
        if not isinstance(fac, dict) or not fac.get("name"):
            continue
        if _faction_id(str(fac["name"])) == faction_target_id:
            return fac
    return None


def _find_pressure_node(replayability_state: Mapping[str, Any], pressure_id: str) -> Optional[Dict[str, Any]]:
    for node in (replayability_state.get("pressure_graph") or {}).get("nodes") or []:
        if isinstance(node, dict) and node.get("id") == pressure_id:
            return node
    return None


def _check_move_preconditions(
    move: Mapping[str, Any],
    agenda: Mapping[str, Any],
    rolling: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
) -> Optional[str]:
    """Return error reason when any precondition fails."""
    npc_id = str(move.get("npc_id") or agenda.get("npc_id") or "")
    eligible, reason = npc_liveness.is_actor_eligible(npc_id, agenda, rolling)
    if not eligible:
        return reason
    target_type = str(move.get("target_type") or "")
    target_id = str(move.get("target_id") or "")
    if not npc_liveness.is_target_valid(
        target_type,
        target_id,
        actor_npc_id=npc_id,
        rolling=rolling,
        replayability_state=replayability_state,
    ):
        return "invalid_target"
    if target_type == "npc" and target_id == npc_id:
        return "self_target_unsupported"
    return None


def compute_effect_bundle(
    move: Mapping[str, Any],
    agenda: Mapping[str, Any],
    rolling: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
    turn_number: int,
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    Compute deterministic effect bundle without persisting.

    Relationship effects are deferred to finalize; all preconditions must pass.
    """
    err = _check_move_preconditions(move, agenda, rolling, replayability_state)
    if err:
        return None, err

    kind = str(move.get("move_kind") or "")
    target_type = str(move.get("target_type") or "")
    target_id = str(move.get("target_id") or "")
    effects: List[Dict[str, Any]] = []

    vec, vec_err = agendas.resolve_relationship_vector(
        str(agenda.get("npc_id") or ""), agenda, rolling
    )
    rel_name = str(vec.get("name") or agenda.get("display_name") or "") if vec else ""
    rel_deltas = _relationship_deltas_for_move(kind, target_type)
    if rel_deltas and (not vec or vec_err):
        return None, "relationship_vector_unresolved"
    for dim, delta in sorted(rel_deltas.items()):
        before = int((vec or {}).get(dim) or 0)
        effects.append(
            {
                "effect_id": _effect_id(kind, "relationship_delta", target_id, dimension=dim),
                "effect_type": "relationship_delta",
                "target_id": rel_name,
                "target_name": rel_name,
                "dimension": dim,
                "delta": delta,
                "before": before,
                "after": before + delta,
                "defer_finalize": True,
            }
        )

    if kind == "defect" and target_type == "faction":
        fac = _find_faction_row(rolling, target_id)
        if not fac:
            return None, "faction_target_missing"
        tick = fac.get("ticks") or {}
        before = int((tick or {}).get("suspicion", 0))
        effects.append(
            {
                "effect_id": _effect_id(kind, "faction_tick", target_id, dimension="suspicion"),
                "effect_type": "faction_tick",
                "target_id": target_id,
                "dimension": "suspicion",
                "delta": 1,
                "before": before,
                "after": before + 1,
            }
        )

    if kind == "negotiate" and target_type == "faction":
        fac = _find_faction_row(rolling, target_id)
        if not fac:
            return None, "faction_target_missing"
        tick = fac.get("ticks") or {}
        before = int((tick or {}).get("goodwill", 0))
        effects.append(
            {
                "effect_id": _effect_id(kind, "faction_tick", target_id, dimension="goodwill"),
                "effect_type": "faction_tick",
                "target_id": target_id,
                "dimension": "goodwill",
                "delta": 1,
                "before": before,
                "after": before + 1,
            }
        )

    if kind == "fortify" and target_type == "pressure":
        node = _find_pressure_node(replayability_state, target_id)
        if not node or node.get("kind") != "environmental":
            return None, "pressure_target_invalid"
        before = int(node.get("magnitude") or 0)
        effects.append(
            {
                "effect_id": _effect_id(kind, "pressure_magnitude", target_id),
                "effect_type": "pressure_magnitude",
                "target_id": target_id,
                "delta": -4,
                "before": before,
                "after": max(0, before - 4),
            }
        )

    if kind == "gather" and target_type == "pressure":
        node = _find_pressure_node(replayability_state, target_id)
        if not node or node.get("kind") != "resource":
            return None, "pressure_target_invalid"
        before = int(node.get("magnitude") or 0)
        effects.append(
            {
                "effect_id": _effect_id(kind, "pressure_magnitude", target_id),
                "effect_type": "pressure_magnitude",
                "target_id": target_id,
                "delta": -3,
                "before": before,
                "after": max(0, before - 3),
            }
        )

    progress_before = int(agenda.get("progress") or 0)
    progress_delta = 4 if kind == "investigate" else 8
    effects.append(
        {
            "effect_id": _effect_id(kind, "agenda_progress", str(agenda.get("agenda_id") or "")),
            "effect_type": "agenda_progress",
            "target_id": str(agenda.get("agenda_id") or ""),
            "delta": progress_delta,
            "before": progress_before,
            "after": agendas._clamp_progress(progress_before + progress_delta),
        }
    )

    effects.sort(key=lambda e: str(e.get("effect_id") or ""))
    return effects, None


def apply_immediate_effects(
    effects: List[Mapping[str, Any]],
    agenda: Dict[str, Any],
    rolling: Dict[str, Any],
    replayability_state: Dict[str, Any],
    turn_number: int,
) -> None:
    """Apply non-deferred effects to working copies."""
    for effect in effects:
        effect_type = str(effect.get("effect_type") or "")
        if effect.get("defer_finalize"):
            continue
        target_id = str(effect.get("target_id") or "")
        delta = int(effect.get("delta") or 0)
        if effect_type == "faction_tick":
            fac = _find_faction_row(rolling, target_id)
            if not fac:
                raise ValueError("faction_tick_failed")
            tick = fac.setdefault("ticks", {})
            dim = str(effect.get("dimension") or "")
            if isinstance(tick, dict) and dim:
                tick[dim] = int(tick.get(dim, 0)) + delta
        elif effect_type == "pressure_magnitude":
            node = _find_pressure_node(replayability_state, target_id)
            if not node:
                raise ValueError("pressure_magnitude_failed")
            node["magnitude"] = max(0, int(node.get("magnitude") or 0) + delta)
            if int(effect.get("before") or 0) > int(effect.get("after") or 0):
                node["trend"] = min(0, int(node.get("trend") or 0) - 1)
        elif effect_type == "agenda_progress":
            agenda["progress"] = agendas._clamp_progress(int(agenda.get("progress") or 0) + delta)
    agenda["last_move_turn"] = turn_number
    agenda["move_count"] = int(agenda.get("move_count") or 0) + 1


def apply_move_effects(
    move: Mapping[str, Any],
    agenda: Dict[str, Any],
    rolling: Dict[str, Any],
    replayability_state: Dict[str, Any],
    turn_number: int,
) -> List[str]:
    """Legacy helper — immediate effects only (relationship deferred to finalize)."""
    bundle, err = compute_effect_bundle(move, agenda, rolling, replayability_state, turn_number)
    if err or not bundle:
        return []
    apply_immediate_effects(bundle, agenda, rolling, replayability_state, turn_number)
    return [str(e.get("effect_id") or "") for e in bundle]


def enumerate_move_candidates(
    run_seed: str,
    agendas_state: Mapping[str, Any],
    rolling: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
    identity: Mapping[str, Any],
    turn_number: int,
) -> List[Dict[str, Any]]:
    """All scored candidates before MAX_CANDIDATES truncation."""
    candidates: List[Dict[str, Any]] = []
    for agenda in (agendas_state.get("active") or [])[:agendas.MAX_ACTIVE_AGENDAS]:
        if not isinstance(agenda, dict) or agenda.get("status") not in ("active", "breaking"):
            continue
        npc_id = str(agenda.get("npc_id") or "")
        agenda_id_value = str(agenda.get("agenda_id") or agendas.agenda_id(npc_id))
        name = str(agenda.get("display_name") or "")
        tier = resolve_actor_tier(npc_id, name, rolling, turn_number)
        if not _cadence_allows(tier, agenda, turn_number):
            continue
        eligible, _ = npc_liveness.is_actor_eligible(npc_id, agenda, rolling)
        if not eligible:
            continue
        for move_kind in MOVE_KINDS:
            target = resolve_move_target(move_kind, agenda, rolling, replayability_state)
            if not target:
                continue
            target_type, target_id = target
            if not npc_liveness.is_target_valid(
                target_type,
                target_id,
                actor_npc_id=npc_id,
                rolling=rolling,
                replayability_state=replayability_state,
            ):
                continue
            score = score_move(
                move_kind,
                agenda,
                tier=tier,
                target_type=target_type,
                target_id=target_id,
                rolling=rolling,
                identity=identity,
                turn_number=turn_number,
            )
            if score < 0:
                continue
            digest = hashlib.sha256(
                f"{run_seed}:{npc_id}:{move_kind}:{turn_number}:{target_id}".encode()
            ).hexdigest()
            tie = int(digest[:6], 16)
            template_id = observable_template_id(move_kind, target_type, target_id)
            candidates.append(
                {
                    "npc_id": npc_id,
                    "agenda_id": agenda_id_value,
                    "display_name": name,
                    "move_kind": move_kind,
                    "target_type": target_type,
                    "target_id": target_id,
                    "effect_ids": build_effect_ids(move_kind, target_type, target_id),
                    "observable_template_id": template_id,
                    "tier": tier,
                    "score": score,
                    "tie": tie,
                }
            )
    candidates.sort(key=lambda c: (-c["score"], -c["tie"], c["npc_id"], c["move_kind"]))
    return candidates


def select_npc_move(
    run_seed: str,
    agendas_state: Mapping[str, Any],
    rolling: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
    identity: Mapping[str, Any],
    turn_number: int,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Evaluate candidates; return (selected_move_or_none, scored_candidates)."""
    candidates = enumerate_move_candidates(
        run_seed, agendas_state, rolling, replayability_state, identity, turn_number
    )
    candidates = candidates[:MAX_CANDIDATES]
    if not candidates:
        return None, []
    winner = candidates[0]
    receipt_id = stable_receipt_id(
        run_seed,
        winner["npc_id"],
        winner["agenda_id"],
        winner["move_kind"],
        turn_number,
        winner["target_id"],
    )
    source_pressure_id = winner["target_id"] if winner["target_type"] == "pressure" else None
    move = {
        **winner,
        "receipt_id": receipt_id,
        "turn": turn_number,
    }
    return move, candidates


def commit_npc_move(
    move: Mapping[str, Any],
    agenda: Dict[str, Any],
    rolling: Dict[str, Any],
    replayability_state: Dict[str, Any],
    run_seed: str,
    turn_number: int,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """
    Atomic effect bundle commit.

    Either all immediate effects persist with a receipt, or nothing changes.
    Relationship deltas are frozen for finalize. Returns (rolling, prepared_move).
    """
    _ = run_seed
    bundle, err = compute_effect_bundle(move, agenda, rolling, replayability_state, turn_number)
    if err or not bundle:
        return rolling, None

    rolling_copy = copy.deepcopy(rolling)
    rb_snapshot = copy.deepcopy(replayability_state)
    agenda_snapshot = copy.deepcopy(agenda)
    try:
        apply_immediate_effects(bundle, agenda, rolling_copy, replayability_state, turn_number)
    except ValueError:
        agenda.clear()
        agenda.update(agenda_snapshot)
        return rolling, None

    effect_ids = [str(e.get("effect_id") or "") for e in bundle]
    receipt = {
        "version": NPC_MOVE_RECEIPT_VERSION,
        "receipt_id": move.get("receipt_id"),
        "receipt_type": "npc_move_committed",
        "turn": turn_number,
        "npc_id": move.get("npc_id"),
        "agenda_id": move.get("agenda_id"),
        "move_kind": move.get("move_kind"),
        "target_type": move.get("target_type"),
        "target_id": move.get("target_id"),
        "effects": bundle,
        "effect_ids": effect_ids,
        "source_pressure_id": move.get("target_id") if move.get("target_type") == "pressure" else None,
        "observable_template_id": move.get("observable_template_id"),
    }
    if not append_npc_move_receipt(replayability_state, receipt):
        agenda.clear()
        agenda.update(agenda_snapshot)
        replayability_state.clear()
        replayability_state.update(rb_snapshot)
        return rolling, None

    prepared = {**dict(move), "effects": bundle, "receipt": receipt}
    return rolling_copy, prepared


def build_move_directive(move: Mapping[str, Any]) -> str:
    """Compact observable guidance — no agenda internals or receipt IDs."""
    if not move:
        return ""
    name = str(move.get("display_name") or "Someone")
    template_id = str(move.get("observable_template_id") or "")
    observable = OBSERVABLE_TEMPLATES.get(
        template_id, "Someone acts independently in the scene."
    )
    lines = [
        NPC_WORLD_MOVE_MARKER,
        "INTERNAL — world development (engine-applied; narrate as fact, not optional):",
        f"- {name}: {observable}",
        "- This action already happened in simulation state; describe its visible consequences.",
        "- Do not invent a conflicting independent NPC action this turn.",
    ]
    return "\n".join(lines)


def move_to_echo_source(move: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Map committed move receipt to consequence echo source when supported."""
    kind = str(move.get("move_kind") or "")
    mapping = {
        "negotiate": ("obligation_returns", 3),
        "pressure": ("retaliation", 2),
        "defect": ("faction_shift_echo", 2),
        "fortify": ("defence_cost", 3),
        "withdraw": ("absence_consequence", 2),
        "conceal": ("hidden_cost", 3),
        "protect": ("debt_or_loyalty_echo", 3),
    }
    if kind not in mapping:
        return None
    echo_kind, mature = mapping[kind]
    return {
        "source_kind": "npc_world_move",
        "source_event_id": move.get("receipt_id"),
        "echo_kind": echo_kind,
        "label": kind.replace("_", " ")[:80],
        "mature_in": mature,
        "source_provenance": {
            "npc_id": str(move.get("npc_id") or ""),
            "agenda_id": str(move.get("agenda_id") or ""),
            "move_kind": kind,
            "target_type": str(move.get("target_type") or ""),
            "target_id": str(move.get("target_id") or ""),
        },
    }