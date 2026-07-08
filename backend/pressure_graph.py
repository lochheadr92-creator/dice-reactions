"""
Pressure Graph Lite v1 — bounded causal pressure nodes with deterministic movement.

Max 8 active nodes. Foreground selection uses engine scoring, not LLM input.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Tuple

from run_identity import select_from_namespace

PRESSURE_DIRECTIVE_MARKER = "[REPLAYABILITY_PRESSURE_V1]"
MAX_ACTIVE_NODES = 8
MAX_TOTAL_NODES = 16
MAX_LINKS_PER_NODE = 4
MAX_REF_IDS = 8
MAX_TAGS = 8
MAX_EVIDENCE_REFS = 8
MAX_THRESHOLD_RECEIPTS = 24
MAX_PROMPT_PRESSURE_NODES = 4
MAX_PROMPT_THRESHOLD_RECEIPTS = 3
MAX_PRESSURE_EVOLUTIONS_PER_TICK = 4
MAX_SPAWNED_EVENTS_PER_NODE = 2
MAX_PRESSURE_EVENTS_PER_TICK = 2
MAX_PRESSURE_EVOLUTION_RECEIPTS = 32
DEFAULT_THRESHOLD = 70
EVOLUTION_EVENT_THRESHOLD = 72
EVOLUTION_RESOLVE_THRESHOLD = 4
EVOLUTION_DECAY_AGE_TURNS = 4
EVOLUTION_DECAY_DELTA = 2
INACTIVE_ARCHIVE_AFTER_TURNS = 8
TREND_VALUES = (-1, 0, 1)
TREND_LABELS = {-1: "falling", 0: "stable", 1: "rising"}
TREND_BY_LABEL = {v: k for k, v in TREND_LABELS.items()}
SCOPES = ("local", "faction", "personal", "environmental")
STATUSES = ("active", "reduced", "resolved", "archived")
THRESHOLD_STATES = ("below", "rising", "crossed")
EVOLUTION_RECEIPT_TYPES = (
    "pressure_escalated",
    "pressure_reduced",
    "pressure_resolved",
    "pressure_spawned_event",
    "pressure_link_created",
    "pressure_link_removed",
)

PRESSURE_EVENT_KIND_BY_GROUP = {
    "danger": ("accident", "attack", "collapse", "injury", "evacuation"),
    "scarcity": ("supplies_exhausted", "theft", "price_increase", "resource_discovery"),
    "conflict": ("argument", "protest", "raid", "retaliation", "alliance_fracture"),
    "opportunity": ("trader_arrival", "rumor_spread", "abandoned_cache", "recruitment"),
    "unknown": ("strange_evidence", "unexplained_disappearance", "mysterious_signal"),
}

PRESSURE_KIND_GROUPS = {
    "danger": "danger",
    "environmental": "danger",
    "environmental_threat": "danger",
    "pursuit": "danger",
    "injury_or_fatigue": "danger",
    "resource": "scarcity",
    "resource_pressure": "scarcity",
    "scarcity": "scarcity",
    "social": "conflict",
    "social_tension": "conflict",
    "conflict": "conflict",
    "suspicion": "conflict",
    "opportunity": "opportunity",
    "unresolved_thread": "unknown",
}

WORLD_EVENT_PRESSURE_KIND = {
    "resource_shortage": "resource",
    "trade_disruption": "resource",
    "investigation": "suspicion",
    "search_operation": "pursuit",
    "disease_outbreak": "environmental",
    "infrastructure_failure": "environmental",
    "settlement_recovery": "opportunity",
    "bandit_activity": "danger",
    "political_unrest": "social",
    "migration": "social",
    "military_mobilisation": "conflict",
    "construction": "opportunity",
    "fire": "environmental",
    "flood": "environmental",
    "crop_failure": "resource",
    "guard_patrol": "social",
    "refugee_movement": "social",
    "wildlife_migration": "environmental",
    "environmental_hazard": "environmental",
}
WORLD_EVENT_TERMINAL_STATUSES = frozenset({"resolved", "failed", "archived"})

ORIGIN_TYPES = (
    "opening_state",
    "run_identity",
    "scenario_pressure",
    "structured_event",
    "pressure_genesis",
)

TICK_MAGNITUDE_DELTA = 4
RECENCY_PENALTY = 18
FOREGROUND_RECENCY_TURNS = 2


def stable_pressure_id(run_seed: str, kind: str, origin_type: str, origin_id: str, slot: str) -> str:
    digest = hashlib.sha256(
        f"{run_seed}:pressure:{kind}:{origin_type}:{origin_id}:{slot}".encode("utf-8")
    ).hexdigest()
    return f"pressure-{digest[:12]}"


def _clamp_magnitude(value: int) -> int:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        raw = 0
    return max(0, min(100, raw))


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_trend(value: Any) -> int:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in TREND_BY_LABEL:
            return TREND_BY_LABEL[lowered]
    try:
        trend = int(value)
    except (TypeError, ValueError):
        trend = 0
    return trend if trend in TREND_VALUES else 0


def _trend_label(value: Any) -> str:
    return TREND_LABELS[_coerce_trend(value)]


def _bounded_str_list(values: Optional[List[Any]], limit: int) -> List[str]:
    out: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text[:120])
        if len(out) >= limit:
            break
    return out


def _normalise_node(node: Dict[str, Any]) -> Dict[str, Any]:
    origin = node.get("origin") if isinstance(node.get("origin"), dict) else {}
    origin_type = str(node.get("origin_type") or origin.get("type") or "structured_event")
    origin_id = str(node.get("origin_id") or origin.get("id") or node.get("id") or "")
    scope = str(node.get("scope") or "local")
    if scope not in SCOPES:
        scope = "local"
    trend = _coerce_trend(node.get("trend"))
    status = str(node.get("status") or "active").strip().lower()
    if status not in STATUSES:
        status = "active"
    links = _bounded_str_list(
        node.get("linked_node_ids") or node.get("linked_pressure_ids") or [],
        MAX_LINKS_PER_NODE,
    )
    node["origin_type"] = origin_type
    node["origin_id"] = origin_id
    node["origin"] = {"type": origin_type, "id": origin_id}
    node["scope"] = scope
    node["magnitude"] = _clamp_magnitude(node.get("magnitude", 0))
    node["trend"] = trend
    node["trend_label"] = _trend_label(trend)
    node["status"] = status
    node["actor_ids"] = _bounded_str_list(node.get("actor_ids") or [], MAX_REF_IDS)
    node["location_ids"] = _bounded_str_list(node.get("location_ids") or [], MAX_REF_IDS)
    node["faction_ids"] = _bounded_str_list(node.get("faction_ids") or [], MAX_REF_IDS)
    node["tags"] = _bounded_str_list(node.get("tags") or [], MAX_TAGS)
    node["linked_node_ids"] = links
    node["linked_pressure_ids"] = links
    node["evidence_refs"] = _bounded_str_list(node.get("evidence_refs") or node.get("evidence") or [], MAX_EVIDENCE_REFS)
    created_turn = _coerce_int(node.get("created_turn"), 0)
    updated_turn = _coerce_int(node.get("updated_turn"), created_turn)
    node["created_turn"] = max(0, created_turn)
    node["updated_turn"] = max(0, updated_turn)
    node["age_turns"] = max(0, _coerce_int(node.get("age_turns"), 0))
    last_evolved = node.get("last_evolved_turn")
    node["last_evolved_turn"] = None if last_evolved is None else max(0, _coerce_int(last_evolved, 0))
    node["spawned_event_ids"] = _bounded_str_list(
        node.get("spawned_event_ids") or [],
        MAX_SPAWNED_EVENTS_PER_NODE,
    )
    return node


def _new_node(
    node_id: str,
    *,
    kind: str,
    origin_type: str,
    origin_id: str,
    scope: str = "local",
    magnitude: int = 20,
    trend: int = 0,
    created_turn: int = 1,
    linked_pressure_ids: Optional[List[str]] = None,
    actor_ids: Optional[List[str]] = None,
    location_ids: Optional[List[str]] = None,
    faction_ids: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    evidence_refs: Optional[List[str]] = None,
    label: str = "",
) -> Dict[str, Any]:
    trend = _coerce_trend(trend)
    scope = scope if scope in SCOPES else "local"
    links = _bounded_str_list(linked_pressure_ids, MAX_LINKS_PER_NODE)
    return _normalise_node({
        "id": node_id,
        "kind": kind,
        "origin": {"type": origin_type, "id": origin_id},
        "origin_type": origin_type,
        "origin_id": origin_id,
        "scope": scope,
        "magnitude": _clamp_magnitude(magnitude),
        "trend": trend,
        "trend_label": _trend_label(trend),
        "status": "active",
        "actor_ids": _bounded_str_list(actor_ids, MAX_REF_IDS),
        "location_ids": _bounded_str_list(location_ids, MAX_REF_IDS),
        "faction_ids": _bounded_str_list(faction_ids, MAX_REF_IDS),
        "tags": _bounded_str_list(tags, MAX_TAGS),
        "linked_node_ids": links,
        "linked_pressure_ids": links,
        "created_turn": created_turn,
        "updated_turn": created_turn,
        "last_foreground_turn": None,
        "age_turns": 0,
        "last_evolved_turn": None,
        "spawned_event_ids": [],
        "threshold": DEFAULT_THRESHOLD,
        "last_threshold": "below",
        "evidence_refs": _bounded_str_list(evidence_refs, MAX_EVIDENCE_REFS),
        "label": (label or kind.replace("_", " "))[:80],
    })


def _link_nodes(nodes: List[Dict[str, Any]], a_id: str, b_id: str) -> None:
    by_id = {n["id"]: n for n in nodes if isinstance(n, dict)}
    if a_id not in by_id or b_id not in by_id or a_id == b_id:
        return
    for nid, other in ((a_id, b_id), (b_id, a_id)):
        node = _normalise_node(by_id[nid])
        links = node.setdefault("linked_node_ids", [])
        if other not in links and len(links) < MAX_LINKS_PER_NODE:
            links.append(other)
        node["linked_pressure_ids"] = list(links)


def init_pressure_graph(
    run_seed: str,
    identity: Mapping[str, Any],
    opening: Mapping[str, Any],
    *,
    created_turn: int = 1,
) -> Dict[str, Any]:
    """Seed active pressure nodes from identity + opening structured origins."""
    nodes: List[Dict[str, Any]] = []
    primary_kind = str(identity.get("primary_pressure_kind") or "resource")
    secondary_kind = str(identity.get("secondary_pressure_kind") or "social")
    scarcity = str(identity.get("scarcity_axis") or "time")
    fault = str(identity.get("relationship_fault_line") or "loyalty")

    origins = opening.get("pressure_origins") or []
    if not origins:
        origins = [
            {"origin_id": opening.get("fact_ids", {}).get("problem", "opening-problem"), "kind": primary_kind, "slot": "primary"},
            {"origin_id": opening.get("fact_ids", {}).get("resource", "opening-resource"), "kind": secondary_kind, "slot": "secondary"},
        ]

    trend_slots = ("0", "1", "-1", "1", "0")
    magnitude_base = 28 + int(6 * float(identity.get("severity_multiplier") or 1.0))

    for i, origin in enumerate(origins[:MAX_ACTIVE_NODES]):
        if not isinstance(origin, dict):
            continue
        kind = str(origin.get("kind") or primary_kind)
        origin_id = str(origin.get("origin_id") or f"opening-{i}")
        slot = str(origin.get("slot") or i)
        trend = int(select_from_namespace(run_seed, f"pressure_trend_{slot}", trend_slots))
        node_id = stable_pressure_id(run_seed, kind, "opening_state", origin_id, slot)
        mag = magnitude_base + (i * 5)
        if kind == primary_kind:
            mag += 4
        nodes.append(
            _new_node(
                node_id,
                kind=kind,
                origin_type="opening_state",
                origin_id=origin_id,
                scope="local" if kind in ("resource", "bodily") else "personal",
                magnitude=mag,
                trend=trend,
                created_turn=created_turn,
                label=f"{scarcity} {kind}".replace("_", " ")[:80],
            )
        )

    if len(nodes) < 2:
        extra_id = stable_pressure_id(run_seed, secondary_kind, "run_identity", fault, "fault")
        nodes.append(
            _new_node(
                extra_id,
                kind=secondary_kind,
                origin_type="run_identity",
                origin_id=fault,
                scope="personal",
                magnitude=magnitude_base - 4,
                trend=int(select_from_namespace(run_seed, "pressure_trend_fault", ("0", "1", "-1"))),
                created_turn=created_turn,
                label=f"{fault} tension",
            )
        )

    if len(nodes) >= 2:
        _link_nodes(nodes, nodes[0]["id"], nodes[1]["id"])

    graph = {
        "nodes": nodes[:MAX_ACTIVE_NODES],
        "foreground_node_id": None,
        "tick": 0,
        "threshold_crossings": [],
        "evolution_receipts": [],
    }
    select_foreground(graph, identity=identity, turn_number=created_turn)
    return graph


def _active_nodes(graph: Mapping[str, Any]) -> List[Dict[str, Any]]:
    nodes = graph.get("nodes") or []
    return [_normalise_node(n) for n in nodes if isinstance(n, dict) and n.get("status") == "active"]


def _identity_bias(node: Mapping[str, Any], identity: Mapping[str, Any]) -> int:
    kind = str(node.get("kind") or "")
    bias = 0
    if kind == identity.get("primary_pressure_kind"):
        bias += 8
    if kind == identity.get("secondary_pressure_kind"):
        bias += 4
    return bias


def _foreground_score(
    node: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    turn_number: int,
    linked_active: int,
) -> int:
    magnitude = int(node.get("magnitude") or 0)
    trend = _coerce_trend(node.get("trend"))
    score = magnitude
    if trend > 0:
        score += 6
    score += _identity_bias(node, identity)
    score += min(8, linked_active * 2)
    last_fg = node.get("last_foreground_turn")
    if isinstance(last_fg, int) and turn_number - last_fg <= FOREGROUND_RECENCY_TURNS:
        score -= RECENCY_PENALTY
    return score


def select_foreground(
    graph: Dict[str, Any],
    *,
    identity: Optional[Mapping[str, Any]] = None,
    turn_number: int = 1,
) -> Optional[str]:
    """Deterministic foreground selection — no bonus for already being foreground."""
    active = _active_nodes(graph)
    if not active:
        graph["foreground_node_id"] = None
        return None

    id_map = {n["id"]: n for n in active}
    scored: List[Tuple[int, str, str]] = []
    for node in active:
        links = node.get("linked_node_ids") or node.get("linked_pressure_ids") or []
        linked_active = sum(1 for lid in links if lid in id_map)
        score = _foreground_score(
            node,
            identity=identity or {},
            turn_number=turn_number,
            linked_active=linked_active,
        )
        scored.append((score, str(node.get("id") or ""), str(node.get("kind") or "")))

    scored.sort(key=lambda row: (-row[0], row[1]))
    winner_id = scored[0][1]
    graph["foreground_node_id"] = winner_id
    for node in active:
        if node.get("id") == winner_id:
            node["last_foreground_turn"] = turn_number
            break
    return winner_id


def _threshold_crossing_event_id(node_id: str, turn_number: int, crossing_index: int) -> str:
    digest = hashlib.sha256(f"{node_id}:threshold:{turn_number}:{crossing_index}".encode("utf-8")).hexdigest()
    return f"evt-threshold-{digest[:12]}"


def _apply_trend_movement(node: Dict[str, Any], turn_number: int) -> None:
    _normalise_node(node)
    trend = _coerce_trend(node.get("trend"))
    if trend == 0:
        node["trend_label"] = _trend_label(trend)
        return
    before = int(node.get("magnitude") or 0)
    delta = trend * TICK_MAGNITUDE_DELTA
    node["magnitude"] = _clamp_magnitude(before + delta)
    node["trend_label"] = _trend_label(trend)
    node["updated_turn"] = turn_number


def _evaluate_threshold(node: Dict[str, Any], turn_number: int, crossing_index: int) -> Optional[Dict[str, Any]]:
    """
    Threshold policy:
    - Emit once when magnitude crosses upward through threshold from below/rising.
    - While crossed and still above: no repeat.
    - When magnitude falls below threshold: last_threshold becomes 'below'.
    - Re-crossing from below emits a new event (new crossing_index).
    """
    threshold = int(node.get("threshold") or DEFAULT_THRESHOLD)
    magnitude = int(node.get("magnitude") or 0)
    state = str(node.get("last_threshold") or "below")

    if magnitude < threshold:
        node["last_threshold"] = "below"
        return None

    if state == "crossed":
        return None

    node["last_threshold"] = "crossed"
    event_id = _threshold_crossing_event_id(str(node.get("id")), turn_number, crossing_index)
    return {
        "event_id": event_id,
        "turn": turn_number,
        "node_id": node.get("id"),
        "kind": "pressure_threshold_crossed",
        "pressure_kind": node.get("kind"),
        "origin_id": node.get("origin_id"),
        "magnitude": magnitude,
    }


def tick_pressure_graph(
    graph: Dict[str, Any],
    turn_number: int,
    *,
    identity: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Apply trend-based movement only. Neutral pressures do not move.
    Returns newly fired threshold crossing events for this tick.
    """
    graph["tick"] = int(graph.get("tick") or 0) + 1
    fired: List[Dict[str, Any]] = []
    receipts = graph.setdefault("threshold_crossings", [])
    crossing_serial = len(receipts)

    for node in graph.get("nodes") or []:
        if not isinstance(node, dict) or node.get("status") != "active":
            continue
        _apply_trend_movement(node, turn_number)
        evt = _evaluate_threshold(node, turn_number, crossing_serial)
        if evt:
            receipts.append(evt)
            fired.append(evt)
            crossing_serial += 1

    if len(receipts) > MAX_THRESHOLD_RECEIPTS:
        graph["threshold_crossings"] = receipts[-MAX_THRESHOLD_RECEIPTS:]

    select_foreground(graph, identity=identity, turn_number=turn_number)
    cap_pressure_graph(graph)
    return fired


def _node_snapshot(node: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "status": str(node.get("status") or ""),
        "magnitude": _clamp_magnitude(node.get("magnitude", 0)),
    }


def _receipt_id(
    receipt_type: str,
    *,
    turn_number: int,
    node_id: str,
    detail: str = "",
) -> str:
    digest = hashlib.sha256(
        f"{receipt_type}:{turn_number}:{node_id}:{detail}".encode("utf-8")
    ).hexdigest()
    return f"pressure-receipt-{digest[:12]}"


def _record_evolution_receipt(
    graph: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    receipt_type: str,
    turn_number: int,
    node_id: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    event_id: str = "",
    linked_node_id: str = "",
    source_event_ids: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    if receipt_type not in EVOLUTION_RECEIPT_TYPES:
        return None
    detail = event_id or linked_node_id or ",".join(source_event_ids or [])
    rid = _receipt_id(receipt_type, turn_number=turn_number, node_id=node_id, detail=detail)
    all_receipts = graph.setdefault("evolution_receipts", [])
    if any(isinstance(r, dict) and r.get("receipt_id") == rid for r in all_receipts):
        return None
    receipt: Dict[str, Any] = {
        "receipt_id": rid,
        "receipt_type": receipt_type,
        "turn": turn_number,
        "node_id": node_id,
        "before": dict(before),
        "after": dict(after),
    }
    if event_id:
        receipt["event_id"] = event_id
    if linked_node_id:
        receipt["linked_node_id"] = linked_node_id
    if source_event_ids:
        receipt["source_event_ids"] = list(source_event_ids)
    all_receipts.append(receipt)
    if len(all_receipts) > MAX_PRESSURE_EVOLUTION_RECEIPTS:
        graph["evolution_receipts"] = all_receipts[-MAX_PRESSURE_EVOLUTION_RECEIPTS:]
    local_receipts.append(receipt)
    return receipt


def _pressure_group(kind: Any) -> str:
    return PRESSURE_KIND_GROUPS.get(str(kind or "").strip().lower(), "unknown")


def _pressure_event_kind(node: Mapping[str, Any], spawn_index: int) -> str:
    group = _pressure_group(node.get("kind"))
    kinds = PRESSURE_EVENT_KIND_BY_GROUP.get(group) or PRESSURE_EVENT_KIND_BY_GROUP["unknown"]
    return kinds[spawn_index % len(kinds)]


def _pressure_world_event_id(
    *,
    run_seed: str,
    node_id: str,
    turn_number: int,
    event_kind: str,
    spawn_index: int,
) -> str:
    digest = hashlib.sha256(
        f"{run_seed}:pressure-world:{node_id}:{turn_number}:{event_kind}:{spawn_index}".encode("utf-8")
    ).hexdigest()
    return f"evt-pressure-{digest[:12]}"


def _pressure_event_from_node(
    node: Mapping[str, Any],
    *,
    run_seed: str,
    turn_number: int,
    spawn_index: int,
) -> Dict[str, Any]:
    event_kind = _pressure_event_kind(node, spawn_index)
    event_id = _pressure_world_event_id(
        run_seed=run_seed,
        node_id=str(node.get("id") or ""),
        turn_number=turn_number,
        event_kind=event_kind,
        spawn_index=spawn_index,
    )
    return {
        "event_id": event_id,
        "event_type": "pressure_world_event",
        "pressure_event_kind": event_kind,
        "pressure_node_id": str(node.get("id") or ""),
        "pressure_kind": str(node.get("kind") or ""),
        "turn": turn_number,
        "magnitude": _clamp_magnitude(node.get("magnitude", 0)),
        "actor_ids": list(node.get("actor_ids") or []),
        "location_ids": list(node.get("location_ids") or []),
        "faction_ids": list(node.get("faction_ids") or []),
        "tags": _bounded_str_list(list(node.get("tags") or []) + ["pressure_world_event"], MAX_TAGS),
    }


def _mitigations_by_node(recent_mitigations: Optional[List[Mapping[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in recent_mitigations or []:
        if not isinstance(row, Mapping):
            continue
        node_id = str(row.get("pressure_node_id") or row.get("target_id") or "").strip()
        if not node_id:
            continue
        delta = _coerce_int(row.get("delta"), 0)
        if delta >= 0:
            continue
        entry = out.setdefault(
            node_id,
            {"delta": 0, "before": None, "after": None, "source_event_ids": []},
        )
        entry["delta"] += delta
        if row.get("before") is not None:
            before = _clamp_magnitude(row.get("before"))
            entry["before"] = before if entry["before"] is None else max(entry["before"], before)
        if row.get("after") is not None:
            after = _clamp_magnitude(row.get("after"))
            entry["after"] = after if entry["after"] is None else min(entry["after"], after)
        source = str(row.get("source_event_id") or row.get("effect_id") or "").strip()
        if source and source not in entry["source_event_ids"]:
            entry["source_event_ids"].append(source[:160])
    for entry in out.values():
        entry["source_event_ids"].sort()
    return out


def _update_node_age(node: Dict[str, Any], turn_number: int) -> None:
    created_turn = _coerce_int(node.get("created_turn"), turn_number)
    node["created_turn"] = max(0, created_turn)
    node["age_turns"] = max(0, turn_number - node["created_turn"])


def _remove_stale_links(
    graph: Dict[str, Any],
    *,
    turn_number: int,
    local_receipts: List[Dict[str, Any]],
) -> None:
    nodes = [_normalise_node(n) for n in graph.get("nodes") or [] if isinstance(n, dict)]
    active_ids = {n.get("id") for n in nodes if n.get("status") == "active"}
    for node in nodes:
        before_links = list(node.get("linked_node_ids") or [])
        kept = [lid for lid in before_links if lid in active_ids and lid != node.get("id")]
        if kept == before_links:
            continue
        before = _node_snapshot(node)
        node["linked_node_ids"] = kept[:MAX_LINKS_PER_NODE]
        node["linked_pressure_ids"] = list(node["linked_node_ids"])
        node["updated_turn"] = turn_number
        removed = sorted(set(before_links) - set(kept))
        for linked_id in removed[:MAX_LINKS_PER_NODE]:
            _record_evolution_receipt(
                graph,
                local_receipts,
                receipt_type="pressure_link_removed",
                turn_number=turn_number,
                node_id=str(node.get("id") or ""),
                linked_node_id=linked_id,
                before=before,
                after=_node_snapshot(node),
            )


def _shared_structured_ref(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    for key in ("actor_ids", "location_ids", "faction_ids"):
        if set(a.get(key) or []) & set(b.get(key) or []):
            return True
    return False


def _create_one_structured_link(
    graph: Dict[str, Any],
    *,
    turn_number: int,
    local_receipts: List[Dict[str, Any]],
) -> None:
    active = sorted(_active_nodes(graph), key=lambda n: str(n.get("id") or ""))
    for idx, a in enumerate(active):
        a_links = set(a.get("linked_node_ids") or [])
        if len(a_links) >= MAX_LINKS_PER_NODE:
            continue
        for b in active[idx + 1:]:
            b_links = set(b.get("linked_node_ids") or [])
            if len(b_links) >= MAX_LINKS_PER_NODE:
                continue
            if b.get("id") in a_links or not _shared_structured_ref(a, b):
                continue
            before_a = _node_snapshot(a)
            before_b = _node_snapshot(b)
            _link_nodes(graph.get("nodes") or [], str(a.get("id") or ""), str(b.get("id") or ""))
            _record_evolution_receipt(
                graph,
                local_receipts,
                receipt_type="pressure_link_created",
                turn_number=turn_number,
                node_id=str(a.get("id") or ""),
                linked_node_id=str(b.get("id") or ""),
                before=before_a,
                after=_node_snapshot(a),
            )
            _record_evolution_receipt(
                graph,
                local_receipts,
                receipt_type="pressure_link_created",
                turn_number=turn_number,
                node_id=str(b.get("id") or ""),
                linked_node_id=str(a.get("id") or ""),
                before=before_b,
                after=_node_snapshot(b),
            )
            return


def _archive_old_inactive_nodes(graph: Dict[str, Any], turn_number: int) -> None:
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        _normalise_node(node)
        if node.get("status") not in ("reduced", "resolved"):
            continue
        if turn_number - _coerce_int(node.get("updated_turn"), turn_number) >= INACTIVE_ARCHIVE_AFTER_TURNS:
            node["status"] = "archived"
            node["trend"] = 0
            node["trend_label"] = "stable"
            node["updated_turn"] = turn_number


def evolve_pressure_graph(
    graph: Dict[str, Any],
    turn_number: int,
    *,
    run_seed: str = "",
    recent_mitigations: Optional[List[Mapping[str, Any]]] = None,
    existing_event_ids: Optional[List[str]] = None,
    identity: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Deterministically evolve authoritative pressure into bounded consequences."""
    if not isinstance(graph, dict):
        return {"receipts": [], "events": [], "evaluated_node_ids": []}

    cap_pressure_graph(graph)
    local_receipts: List[Dict[str, Any]] = []
    spawned_events: List[Dict[str, Any]] = []
    evaluated_node_ids: List[str] = []
    known_event_ids = set(_bounded_str_list(existing_event_ids or [], 256))
    mitigations = _mitigations_by_node(recent_mitigations)

    for node in graph.get("nodes") or []:
        if isinstance(node, dict):
            _normalise_node(node)
            _update_node_age(node, turn_number)

    _archive_old_inactive_nodes(graph, turn_number)
    _remove_stale_links(graph, turn_number=turn_number, local_receipts=local_receipts)
    _create_one_structured_link(graph, turn_number=turn_number, local_receipts=local_receipts)

    candidates = [
        _normalise_node(n)
        for n in graph.get("nodes") or []
        if isinstance(n, dict)
        and n.get("status") == "active"
        and n.get("last_evolved_turn") != turn_number
    ]
    candidates.sort(
        key=lambda n: (
            -_clamp_magnitude(n.get("magnitude", 0)),
            -_coerce_trend(n.get("trend")),
            str(n.get("id") or ""),
        )
    )

    for node in candidates[:MAX_PRESSURE_EVOLUTIONS_PER_TICK]:
        node_id = str(node.get("id") or "")
        before = _node_snapshot(node)
        mitigation = mitigations.get(node_id)
        evaluated_node_ids.append(node_id)

        if mitigation:
            target_after = mitigation.get("after")
            if target_after is None:
                target_after = _clamp_magnitude(node.get("magnitude", 0) + int(mitigation.get("delta") or 0))
            target_after = _clamp_magnitude(target_after)
            if node.get("magnitude") == mitigation.get("before"):
                node["magnitude"] = target_after
            else:
                node["magnitude"] = min(_clamp_magnitude(node.get("magnitude", 0)), target_after)
            node["trend"] = -1 if node["magnitude"] > EVOLUTION_RESOLVE_THRESHOLD else 0
            node["trend_label"] = _trend_label(node["trend"])
            node["status"] = "resolved" if node["magnitude"] <= EVOLUTION_RESOLVE_THRESHOLD else "active"
            node["updated_turn"] = turn_number
            node["last_evolved_turn"] = turn_number
            after = _node_snapshot(node)
            receipt_before = dict(before)
            if mitigation.get("before") is not None:
                receipt_before["magnitude"] = _clamp_magnitude(mitigation.get("before"))
            receipt_type = "pressure_resolved" if node["status"] == "resolved" else "pressure_reduced"
            _record_evolution_receipt(
                graph,
                local_receipts,
                receipt_type=receipt_type,
                turn_number=turn_number,
                node_id=node_id,
                before=receipt_before,
                after=after,
                source_event_ids=list(mitigation.get("source_event_ids") or []),
            )
            continue

        magnitude = _clamp_magnitude(node.get("magnitude", 0))
        trend = _coerce_trend(node.get("trend"))
        age = _coerce_int(node.get("age_turns"), 0)

        if magnitude <= EVOLUTION_RESOLVE_THRESHOLD:
            node["magnitude"] = 0
            node["trend"] = 0
            node["trend_label"] = "stable"
            node["status"] = "resolved"
            node["updated_turn"] = turn_number
            node["last_evolved_turn"] = turn_number
            _record_evolution_receipt(
                graph,
                local_receipts,
                receipt_type="pressure_resolved",
                turn_number=turn_number,
                node_id=node_id,
                before=before,
                after=_node_snapshot(node),
            )
            continue

        if trend < 0 or (trend == 0 and age >= EVOLUTION_DECAY_AGE_TURNS):
            node["magnitude"] = _clamp_magnitude(magnitude - EVOLUTION_DECAY_DELTA)
            if node["magnitude"] <= EVOLUTION_RESOLVE_THRESHOLD:
                node["magnitude"] = 0
                node["trend"] = 0
                node["trend_label"] = "stable"
                node["status"] = "resolved"
                receipt_type = "pressure_resolved"
            else:
                node["trend"] = -1
                node["trend_label"] = "falling"
                receipt_type = "pressure_reduced"
            node["updated_turn"] = turn_number
            node["last_evolved_turn"] = turn_number
            _record_evolution_receipt(
                graph,
                local_receipts,
                receipt_type=receipt_type,
                turn_number=turn_number,
                node_id=node_id,
                before=before,
                after=_node_snapshot(node),
            )
            continue

        if magnitude >= EVOLUTION_EVENT_THRESHOLD or (trend > 0 and age >= 2):
            spawned_ids = _bounded_str_list(node.get("spawned_event_ids") or [], MAX_SPAWNED_EVENTS_PER_NODE)
            node_can_spawn = len(spawned_ids) < MAX_SPAWNED_EVENTS_PER_NODE
            if not node_can_spawn and age >= EVOLUTION_DECAY_AGE_TURNS:
                node["magnitude"] = _clamp_magnitude(magnitude - EVOLUTION_DECAY_DELTA)
                if node["magnitude"] <= EVOLUTION_RESOLVE_THRESHOLD:
                    node["magnitude"] = 0
                    node["trend"] = 0
                    node["trend_label"] = "stable"
                    node["status"] = "resolved"
                    receipt_type = "pressure_resolved"
                else:
                    node["trend"] = -1
                    node["trend_label"] = "falling"
                    receipt_type = "pressure_reduced"
                node["updated_turn"] = turn_number
                node["last_evolved_turn"] = turn_number
                _record_evolution_receipt(
                    graph,
                    local_receipts,
                    receipt_type=receipt_type,
                    turn_number=turn_number,
                    node_id=node_id,
                    before=before,
                    after=_node_snapshot(node),
                )
                continue

            node["magnitude"] = _clamp_magnitude(magnitude + (2 if trend > 0 else 0))
            node["trend"] = 1 if trend > 0 else trend
            node["trend_label"] = _trend_label(node["trend"])
            node["updated_turn"] = turn_number
            node["last_evolved_turn"] = turn_number
            after_escalation = _node_snapshot(node)
            _record_evolution_receipt(
                graph,
                local_receipts,
                receipt_type="pressure_escalated",
                turn_number=turn_number,
                node_id=node_id,
                before=before,
                after=after_escalation,
            )
            if (
                len(spawned_ids) < MAX_SPAWNED_EVENTS_PER_NODE
                and len(spawned_events) < MAX_PRESSURE_EVENTS_PER_TICK
            ):
                spawn_index = len(spawned_ids)
                event = _pressure_event_from_node(
                    node,
                    run_seed=run_seed,
                    turn_number=turn_number,
                    spawn_index=spawn_index,
                )
                event_id = str(event.get("event_id") or "")
                if event_id and event_id not in known_event_ids:
                    spawned_ids.append(event_id)
                    known_event_ids.add(event_id)
                    node["spawned_event_ids"] = spawned_ids
                    spawned_events.append(event)
                    _record_evolution_receipt(
                        graph,
                        local_receipts,
                        receipt_type="pressure_spawned_event",
                        turn_number=turn_number,
                        node_id=node_id,
                        before=after_escalation,
                        after=_node_snapshot(node),
                        event_id=event_id,
                    )
            continue

        node["last_evolved_turn"] = turn_number

    select_foreground(graph, identity=identity, turn_number=turn_number)
    cap_pressure_graph(graph)
    return {
        "receipts": local_receipts,
        "events": spawned_events,
        "evaluated_node_ids": evaluated_node_ids,
    }


def _pressure_equivalence_key(node: Mapping[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(node.get("kind") or ""),
        str(node.get("origin_type") or ""),
        str(node.get("origin_id") or ""),
        str(node.get("scope") or ""),
    )


def _find_equivalent_node(graph: Mapping[str, Any], candidate: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    wanted_id = str(candidate.get("id") or "")
    wanted_key = _pressure_equivalence_key(candidate)
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        _normalise_node(node)
        if wanted_id and node.get("id") == wanted_id:
            return node
        if _pressure_equivalence_key(node) == wanted_key:
            return node
    return None


def _compact_inactive_node(node: Dict[str, Any]) -> Dict[str, Any]:
    if node.get("status") == "active":
        return node
    keep = (
        "id",
        "kind",
        "origin_type",
        "origin_id",
        "scope",
        "status",
        "magnitude",
        "trend",
        "trend_label",
        "created_turn",
        "updated_turn",
        "spawned_event_ids",
        "label",
    )
    compact: Dict[str, Any] = {}
    for key in keep:
        value = node.get(key)
        if value is None or value == "" or value == []:
            continue
        compact[key] = copy.deepcopy(value)
    return compact


def _merge_refs(existing: Dict[str, Any], incoming: Mapping[str, Any]) -> None:
    for key, cap in (
        ("actor_ids", MAX_REF_IDS),
        ("location_ids", MAX_REF_IDS),
        ("faction_ids", MAX_REF_IDS),
        ("tags", MAX_TAGS),
        ("linked_node_ids", MAX_LINKS_PER_NODE),
        ("evidence_refs", MAX_EVIDENCE_REFS),
    ):
        merged = _bounded_str_list(list(existing.get(key) or []) + list(incoming.get(key) or []), cap)
        existing[key] = merged
    existing["linked_pressure_ids"] = list(existing.get("linked_node_ids") or [])


def cap_pressure_graph(graph: Dict[str, Any]) -> Dict[str, Any]:
    nodes = [_normalise_node(n) for n in (graph.get("nodes") or []) if isinstance(n, dict)]
    active = [n for n in nodes if n.get("status") == "active"]
    if len(active) > MAX_ACTIVE_NODES:
        overflow = sorted(
            active,
            key=lambda n: (int(n.get("magnitude") or 0), int(n.get("updated_turn") or 0), str(n.get("id") or "")),
        )[: len(active) - MAX_ACTIVE_NODES]
        for node in overflow:
            node["status"] = "archived"
            node["trend"] = 0
            node["trend_label"] = "stable"

    if len(nodes) > MAX_TOTAL_NODES:
        nodes = sorted(
            nodes,
            key=lambda n: (
                0 if n.get("status") == "active" else 1,
                -int(n.get("magnitude") or 0),
                -int(n.get("updated_turn") or 0),
                str(n.get("id") or ""),
            ),
        )[:MAX_TOTAL_NODES]
        nodes.sort(key=lambda n: (int(n.get("created_turn") or 0), str(n.get("id") or "")))
    nodes = [_compact_inactive_node(n) for n in nodes]
    graph["nodes"] = nodes
    if graph.get("foreground_node_id") not in {n.get("id") for n in _active_nodes(graph)}:
        graph["foreground_node_id"] = None
    receipts = graph.get("threshold_crossings")
    if isinstance(receipts, list) and len(receipts) > MAX_THRESHOLD_RECEIPTS:
        graph["threshold_crossings"] = receipts[-MAX_THRESHOLD_RECEIPTS:]
    evolution_receipts = graph.get("evolution_receipts")
    if isinstance(evolution_receipts, list) and len(evolution_receipts) > MAX_PRESSURE_EVOLUTION_RECEIPTS:
        graph["evolution_receipts"] = evolution_receipts[-MAX_PRESSURE_EVOLUTION_RECEIPTS:]
    return graph


def add_pressure_node(
    graph: Dict[str, Any],
    *,
    node_id: str,
    kind: str,
    origin_type: str,
    origin_id: str,
    magnitude: int = 25,
    trend: int = 0,
    turn_number: int = 1,
    linked_pressure_ids: Optional[List[str]] = None,
    label: str = "",
) -> Optional[Dict[str, Any]]:
    """Add a node if active count is below MAX_ACTIVE_NODES."""
    cap_pressure_graph(graph)
    active = _active_nodes(graph)
    if len(active) >= MAX_ACTIVE_NODES:
        return None
    existing_ids = {n.get("id") for n in graph.get("nodes") or [] if isinstance(n, dict)}
    valid_links = [
        lid for lid in (linked_pressure_ids or [])
        if lid in existing_ids
    ][:MAX_LINKS_PER_NODE]
    node = _new_node(
        node_id,
        kind=kind,
        origin_type=origin_type,
        origin_id=origin_id,
        magnitude=magnitude,
        trend=trend,
        created_turn=turn_number,
        linked_pressure_ids=valid_links,
        label=label,
    )
    graph.setdefault("nodes", []).append(node)
    cap_pressure_graph(graph)
    return node


def upsert_pressure_node(
    graph: Dict[str, Any],
    *,
    node_id: Optional[str] = None,
    run_seed: str = "",
    kind: str,
    origin_type: str,
    origin_id: str,
    scope: str = "local",
    magnitude: int = 25,
    trend: Any = None,
    turn_number: int = 1,
    actor_ids: Optional[List[str]] = None,
    location_ids: Optional[List[str]] = None,
    faction_ids: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    linked_node_ids: Optional[List[str]] = None,
    evidence_refs: Optional[List[str]] = None,
    label: str = "",
) -> Dict[str, Any]:
    """Create or update an equivalent pressure node deterministically."""
    if not node_id:
        seed = run_seed or "pressure-graph"
        node_id = stable_pressure_id(seed, kind, origin_type, origin_id, scope)
    candidate = _new_node(
        node_id,
        kind=kind,
        origin_type=origin_type,
        origin_id=origin_id,
        scope=scope,
        magnitude=magnitude,
        trend=_coerce_trend(trend) if trend is not None else 0,
        created_turn=turn_number,
        linked_pressure_ids=linked_node_ids,
        actor_ids=actor_ids,
        location_ids=location_ids,
        faction_ids=faction_ids,
        tags=tags,
        evidence_refs=evidence_refs,
        label=label,
    )
    existing = _find_equivalent_node(graph, candidate)
    if existing is None:
        graph.setdefault("nodes", []).append(candidate)
        cap_pressure_graph(graph)
        return candidate

    _normalise_node(existing)
    existing["magnitude"] = max(_clamp_magnitude(existing.get("magnitude", 0)), _clamp_magnitude(magnitude))
    if trend is not None:
        existing["trend"] = _coerce_trend(trend)
        existing["trend_label"] = _trend_label(trend)
    existing["status"] = "active"
    existing["updated_turn"] = max(int(existing.get("updated_turn") or 0), turn_number)
    if label and not existing.get("label"):
        existing["label"] = label[:80]
    _merge_refs(existing, candidate)
    cap_pressure_graph(graph)
    return existing


def _world_event_scope(event: Mapping[str, Any], event_type: str) -> str:
    if event.get("faction_ids"):
        return "faction"
    if event.get("actor_ids"):
        return "personal"
    if event_type in {"environmental_hazard", "fire", "flood", "wildlife_migration"}:
        return "environmental"
    return "local"


def _world_event_pressure_node_id(
    *,
    run_seed: str,
    event_type: str,
    world_event_id: str,
    scope: str,
) -> str:
    return stable_pressure_id(
        run_seed or "pressure-graph",
        WORLD_EVENT_PRESSURE_KIND.get(event_type, "unresolved_thread"),
        "world_event",
        world_event_id,
        scope,
    )


def apply_world_event_engine_events(
    graph: Dict[str, Any],
    events: List[Mapping[str, Any]],
    turn_number: int,
    *,
    run_seed: str = "",
) -> Dict[str, Any]:
    """Convert world-event engine events into pressure changes.

    The world-event engine emits structured engine events; pressure_graph is
    still the only code that creates, reinforces, reduces, or resolves pressure.
    """
    if not isinstance(graph, dict):
        return {"receipts": [], "applied_event_ids": []}
    local_receipts: List[Dict[str, Any]] = []
    applied_event_ids: List[str] = []
    for event in (events or [])[:MAX_PRESSURE_EVOLUTIONS_PER_TICK]:
        if not isinstance(event, Mapping) or event.get("event_type") != "world_event":
            continue
        event_id = str(event.get("event_id") or "")
        world_event_id = str(event.get("world_event_id") or "")
        event_type = str(event.get("world_event_type") or "").strip().lower()
        if not event_id or not world_event_id:
            continue
        pressure_kind = WORLD_EVENT_PRESSURE_KIND.get(event_type, "unresolved_thread")
        scope = _world_event_scope(event, event_type)
        node_id = _world_event_pressure_node_id(
            run_seed=run_seed,
            event_type=event_type,
            world_event_id=world_event_id,
            scope=scope,
        )
        before_node = None
        for row in graph.get("nodes") or []:
            if isinstance(row, dict) and str(row.get("id") or "") == node_id:
                before_node = row
                break
        before = _node_snapshot(before_node) if isinstance(before_node, Mapping) else {}
        status = str(event.get("world_event_status") or "")
        source_ids = _bounded_str_list(
            [event_id, world_event_id] + list(event.get("source_event_ids") or []),
            MAX_REF_IDS,
        )
        originating_pressure_ids = _bounded_str_list(
            event.get("originating_pressure_ids") or [],
            MAX_REF_IDS,
        )
        if originating_pressure_ids:
            existing_source = None
            for row in graph.get("nodes") or []:
                if isinstance(row, dict) and str(row.get("id") or "") == originating_pressure_ids[0]:
                    existing_source = row
                    break
            if existing_source is not None:
                _normalise_node(existing_source)
                before_source = _node_snapshot(existing_source)
                if status in WORLD_EVENT_TERMINAL_STATUSES:
                    existing_source["magnitude"] = _clamp_magnitude(
                        int(existing_source.get("magnitude") or 0)
                        - max(4, int(event.get("magnitude") or 0) // 5)
                    )
                    existing_source["status"] = (
                        "resolved"
                        if existing_source["magnitude"] <= EVOLUTION_RESOLVE_THRESHOLD
                        else "active"
                    )
                    existing_source["trend"] = -1 if existing_source["status"] == "active" else 0
                else:
                    existing_source["magnitude"] = max(
                        _clamp_magnitude(existing_source.get("magnitude", 0)),
                        max(20, _clamp_magnitude(event.get("magnitude", 0))),
                    )
                    existing_source["status"] = "active"
                    existing_source["trend"] = max(_coerce_trend(existing_source.get("trend")), 0)
                existing_source["trend_label"] = _trend_label(existing_source["trend"])
                existing_source["updated_turn"] = turn_number
                _merge_refs(
                    existing_source,
                    {
                        "actor_ids": list(event.get("actor_ids") or []),
                        "location_ids": list(event.get("location_ids") or []),
                        "faction_ids": list(event.get("faction_ids") or []),
                        "tags": ["world_event", event_type, pressure_kind],
                        "evidence_refs": [f"world_event:{world_event_id}", f"engine_event:{event_id}"],
                    },
                )
                if status in WORLD_EVENT_TERMINAL_STATUSES:
                    receipt_type = "pressure_resolved" if existing_source["status"] == "resolved" else "pressure_reduced"
                else:
                    receipt_type = "pressure_escalated"
                _record_evolution_receipt(
                    graph,
                    local_receipts,
                    receipt_type=receipt_type,
                    turn_number=turn_number,
                    node_id=str(existing_source.get("id") or ""),
                    before=before_source,
                    after=_node_snapshot(existing_source),
                    event_id=event_id,
                    source_event_ids=source_ids,
                )
                applied_event_ids.append(event_id)
                continue
        if status in WORLD_EVENT_TERMINAL_STATUSES:
            if not before_node:
                continue
            _normalise_node(before_node)
            if status == "resolved":
                before_node["magnitude"] = 0
                before_node["status"] = "resolved"
            else:
                before_node["magnitude"] = _clamp_magnitude(
                    int(before_node.get("magnitude") or 0)
                    - max(6, int(event.get("magnitude") or 0) // 4)
                )
                before_node["status"] = "resolved" if before_node["magnitude"] <= EVOLUTION_RESOLVE_THRESHOLD else "active"
            before_node["trend"] = -1 if before_node["status"] == "active" else 0
            before_node["trend_label"] = _trend_label(before_node["trend"])
            before_node["updated_turn"] = turn_number
            _record_evolution_receipt(
                graph,
                local_receipts,
                receipt_type="pressure_resolved" if before_node["status"] == "resolved" else "pressure_reduced",
                turn_number=turn_number,
                node_id=node_id,
                before=before,
                after=_node_snapshot(before_node),
                event_id=event_id,
                source_event_ids=source_ids,
            )
            applied_event_ids.append(event_id)
            continue

        node = upsert_pressure_node(
            graph,
            node_id=node_id,
            run_seed=run_seed,
            kind=pressure_kind,
            origin_type="world_event",
            origin_id=world_event_id,
            scope=scope,
            magnitude=max(20, _clamp_magnitude(event.get("magnitude", 0))),
            trend=1,
            turn_number=turn_number,
            actor_ids=list(event.get("actor_ids") or []),
            location_ids=list(event.get("location_ids") or []),
            faction_ids=list(event.get("faction_ids") or []),
            tags=_bounded_str_list(["world_event", event_type, pressure_kind], MAX_TAGS),
            evidence_refs=[f"world_event:{world_event_id}", f"engine_event:{event_id}"],
            label=str(event_type or pressure_kind).replace("_", " ")[:80],
        )
        _record_evolution_receipt(
            graph,
            local_receipts,
            receipt_type="pressure_escalated",
            turn_number=turn_number,
            node_id=str(node.get("id") or node_id),
            before=before,
            after=_node_snapshot(node),
            event_id=event_id,
            source_event_ids=source_ids,
        )
        applied_event_ids.append(event_id)
    if applied_event_ids:
        select_foreground(graph, turn_number=turn_number)
    cap_pressure_graph(graph)
    return {"receipts": local_receipts, "applied_event_ids": applied_event_ids}


def reduce_pressure_node(
    graph: Dict[str, Any],
    node_id: str,
    *,
    amount: int = 10,
    turn_number: int = 1,
) -> bool:
    for node in graph.get("nodes") or []:
        if isinstance(node, dict) and node.get("id") == node_id:
            _normalise_node(node)
            before = _clamp_magnitude(node.get("magnitude", 0))
            node["magnitude"] = _clamp_magnitude(before - max(0, int(amount or 0)))
            node["trend"] = -1 if node["magnitude"] > 0 else 0
            node["trend_label"] = _trend_label(node["trend"])
            node["status"] = "active" if node["magnitude"] > 0 else "reduced"
            node["updated_turn"] = turn_number
            if graph.get("foreground_node_id") == node_id:
                select_foreground(graph, turn_number=turn_number)
            return True
    return False


def resolve_pressure_node(graph: Dict[str, Any], node_id: str, *, turn_number: int = 1) -> bool:
    for node in graph.get("nodes") or []:
        if isinstance(node, dict) and node.get("id") == node_id:
            _normalise_node(node)
            node["magnitude"] = 0
            node["trend"] = 0
            node["trend_label"] = "stable"
            node["status"] = "resolved"
            node["updated_turn"] = turn_number
            if graph.get("foreground_node_id") == node_id:
                select_foreground(graph, turn_number=turn_number)
            return True
    return False


def deactivate_pressure_node(graph: Dict[str, Any], node_id: str) -> bool:
    return resolve_pressure_node(graph, node_id)


def link_pressure_nodes(graph: Dict[str, Any], a_id: str, b_id: str) -> bool:
    before = copy.deepcopy(graph.get("nodes") or [])
    _link_nodes(graph.get("nodes") or [], a_id, b_id)
    return before != (graph.get("nodes") or [])


def strip_model_pressure_mutations(graph: Dict[str, Any], authoritative: Mapping[str, Any]) -> List[str]:
    """Restore engine-owned node fields if model attempted mutation via rolling_state."""
    cap_pressure_graph(graph)
    adjustments: List[str] = []
    auth_nodes = {
        n.get("id"): n
        for n in (authoritative.get("nodes") or [])
        if isinstance(n, dict) and n.get("id")
    }
    protected = (
        "kind", "origin_type", "origin_id", "scope", "magnitude", "trend",
        "trend_label", "status", "actor_ids", "location_ids", "faction_ids",
        "tags", "linked_node_ids", "linked_pressure_ids", "threshold",
        "last_threshold", "evidence_refs",
    )
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        _normalise_node(node)
        auth = auth_nodes.get(node.get("id"))
        if not auth:
            continue
        _normalise_node(auth)
        for field in protected:
            if node.get(field) != auth.get(field):
                node[field] = auth.get(field)
                adjustments.append(f"pressure_{node.get('id')}_{field}_restored")
    return adjustments


def project_active_pressures(graph: Mapping[str, Any], *, limit: int = 3) -> List[str]:
    """ADR-023: engine-derived, read-only projection of the canonical pressure_graph
    foreground into rolling_state.active_pressures prose phrases.

    Pure and deterministic: the foreground node first, then remaining active nodes by
    descending magnitude then id; deduplicated; capped. pressure_graph is the single
    canonical pressure authority -- active_pressures is never model-authored.
    """
    if not isinstance(graph, dict):
        return []
    fg_id = graph.get("foreground_node_id")
    actives = _active_nodes(graph)

    def _key(n: Mapping[str, Any]):
        return (0 if n.get("id") == fg_id else 1, -int(n.get("magnitude") or 0), str(n.get("id") or ""))
    out: List[str] = []
    for n in sorted(actives, key=_key):
        label = str(n.get("label") or n.get("kind") or "rising pressure").strip()
        if label and label not in out:
            out.append(label)
        if len(out) >= limit:
            break
    return out


def build_pressure_directive(graph: Mapping[str, Any]) -> str:
    """Non-persisted guidance to surface the foreground pressure."""
    fg_id = graph.get("foreground_node_id")
    if not fg_id:
        return ""

    fg_node = None
    for node in graph.get("nodes") or []:
        if isinstance(node, dict) and node.get("id") == fg_id:
            fg_node = node
            break
    if not fg_node or fg_node.get("status") != "active":
        return ""

    label = str(fg_node.get("label") or fg_node.get("kind") or "rising pressure").strip()
    trend = _coerce_trend(fg_node.get("trend"))
    trend_word = "rising" if trend > 0 else "steady" if trend == 0 else "easing"
    lines = [
        PRESSURE_DIRECTIVE_MARKER,
        "INTERNAL — foreground pressure (engine guidance; do not expose graph labels):",
        f"- Surface '{label}' through sensory detail this turn ({trend_word} pressure).",
        "- Do not invent a wholly new crisis unrelated to established state.",
    ]
    recent = (graph.get("threshold_crossings") or [])[-1:]
    if recent:
        evt = recent[-1]
        lines.append(
            f"- A threshold was crossed for '{evt.get('pressure_kind', 'pressure')}' — let consequences feel nearer."
        )
    return "\n".join(lines)


def copy_pressure_graph(graph: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    copied = copy.deepcopy(graph) if isinstance(graph, dict) else {
        "nodes": [],
        "tick": 0,
        "threshold_crossings": [],
        "evolution_receipts": [],
    }
    copied.setdefault("evolution_receipts", [])
    return cap_pressure_graph(copied)


_PROMPT_NODE_FIELDS = (
    "id", "kind", "origin", "scope", "magnitude", "trend", "trend_label",
    "actor_ids", "location_ids", "faction_ids", "tags", "linked_node_ids",
    "status", "created_turn", "updated_turn", "evidence_refs", "label",
)


def project_pressure_graph_for_rolling(graph: Mapping[str, Any], *, limit: int = MAX_ACTIVE_NODES) -> Dict[str, Any]:
    if not isinstance(graph, dict):
        return {"nodes": [], "foreground_node_id": None, "tick": 0, "threshold_crossings": []}
    working = copy_pressure_graph(graph)
    fg_id = working.get("foreground_node_id")
    nodes = sorted(
        _active_nodes(working),
        key=lambda n: (0 if n.get("id") == fg_id else 1, -int(n.get("magnitude") or 0), str(n.get("id") or "")),
    )[: max(0, min(MAX_ACTIVE_NODES, int(limit or 0)))]
    node_ids = {n.get("id") for n in nodes}
    return {
        "nodes": [
            {field: copy.deepcopy(node.get(field)) for field in _PROMPT_NODE_FIELDS if field in node}
            for node in nodes
        ],
        "foreground_node_id": fg_id if fg_id in node_ids else None,
        "tick": int(working.get("tick") or 0),
        "threshold_crossings": copy.deepcopy((working.get("threshold_crossings") or [])[-MAX_THRESHOLD_RECEIPTS:]),
    }


def project_pressure_graph_for_prompt(
    graph: Mapping[str, Any],
    *,
    limit: int = MAX_PROMPT_PRESSURE_NODES,
) -> Dict[str, Any]:
    projected = project_pressure_graph_for_rolling(graph, limit=limit)
    nodes = []
    for node in projected.get("nodes") or []:
        nodes.append({field: copy.deepcopy(node.get(field)) for field in _PROMPT_NODE_FIELDS if field in node})
    projected["nodes"] = nodes
    projected["threshold_crossings"] = (projected.get("threshold_crossings") or [])[-MAX_PROMPT_THRESHOLD_RECEIPTS:]
    return projected
