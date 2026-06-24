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
MAX_LINKS_PER_NODE = 4
MAX_THRESHOLD_RECEIPTS = 24
DEFAULT_THRESHOLD = 70
TREND_VALUES = (-1, 0, 1)
SCOPES = ("local", "faction", "personal", "environmental")
STATUSES = ("active", "resolved", "archived")
THRESHOLD_STATES = ("below", "rising", "crossed")

ORIGIN_TYPES = (
    "opening_state",
    "run_identity",
    "scenario_pressure",
    "structured_event",
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
    return max(0, min(100, int(value)))


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
    label: str = "",
) -> Dict[str, Any]:
    trend = int(trend)
    if trend not in TREND_VALUES:
        trend = 0
    scope = scope if scope in SCOPES else "local"
    return {
        "id": node_id,
        "kind": kind,
        "origin_type": origin_type,
        "origin_id": origin_id,
        "scope": scope,
        "magnitude": _clamp_magnitude(magnitude),
        "trend": trend,
        "status": "active",
        "linked_pressure_ids": list(linked_pressure_ids or [])[:MAX_LINKS_PER_NODE],
        "created_turn": created_turn,
        "updated_turn": created_turn,
        "last_foreground_turn": None,
        "threshold": DEFAULT_THRESHOLD,
        "last_threshold": "below",
        "label": (label or kind.replace("_", " "))[:80],
    }


def _link_nodes(nodes: List[Dict[str, Any]], a_id: str, b_id: str) -> None:
    by_id = {n["id"]: n for n in nodes if isinstance(n, dict)}
    if a_id not in by_id or b_id not in by_id or a_id == b_id:
        return
    for nid, other in ((a_id, b_id), (b_id, a_id)):
        links = by_id[nid].setdefault("linked_pressure_ids", [])
        if other not in links and len(links) < MAX_LINKS_PER_NODE:
            links.append(other)


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
    }
    select_foreground(graph, identity=identity, turn_number=created_turn)
    return graph


def _active_nodes(graph: Mapping[str, Any]) -> List[Dict[str, Any]]:
    nodes = graph.get("nodes") or []
    return [n for n in nodes if isinstance(n, dict) and n.get("status") == "active"]


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
    trend = int(node.get("trend") or 0)
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
        links = node.get("linked_pressure_ids") or []
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
    trend = int(node.get("trend") or 0)
    if trend == 0:
        return
    before = int(node.get("magnitude") or 0)
    delta = trend * TICK_MAGNITUDE_DELTA
    node["magnitude"] = _clamp_magnitude(before + delta)
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
    return fired


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
    return node


def deactivate_pressure_node(graph: Dict[str, Any], node_id: str) -> bool:
    for node in graph.get("nodes") or []:
        if isinstance(node, dict) and node.get("id") == node_id:
            node["status"] = "resolved"
            if graph.get("foreground_node_id") == node_id:
                select_foreground(graph)
            return True
    return False


def strip_model_pressure_mutations(graph: Dict[str, Any], authoritative: Mapping[str, Any]) -> List[str]:
    """Restore engine-owned node fields if model attempted mutation via rolling_state."""
    adjustments: List[str] = []
    auth_nodes = {
        n.get("id"): n
        for n in (authoritative.get("nodes") or [])
        if isinstance(n, dict) and n.get("id")
    }
    protected = (
        "kind", "origin_type", "origin_id", "scope", "magnitude", "trend",
        "status", "linked_pressure_ids", "threshold", "last_threshold",
    )
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        auth = auth_nodes.get(node.get("id"))
        if not auth:
            continue
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
    actives = [
        n for n in (graph.get("nodes") or [])
        if isinstance(n, dict) and n.get("status") == "active"
    ]
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
    trend = int(fg_node.get("trend") or 0)
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
    return copy.deepcopy(graph) if isinstance(graph, dict) else {"nodes": [], "tick": 0, "threshold_crossings": []}