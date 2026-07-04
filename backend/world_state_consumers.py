"""
Deterministic consumers for engine-owned world events.

Pressure remains owned by pressure_graph. Replayability owns the event history.
This module consumes engine events into generic structured rolling_state fields.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Tuple

WORLD_STATE_CONSUMER_VERSION = 1
MAX_WORLD_STATE_CONSUMER_EVENTS_PER_TICK = 4
MAX_WORLD_STATE_MUTATIONS_PER_EVENT = 3
MAX_WORLD_STATE_RECEIPTS = 48
MAX_PROCESSED_WORLD_EVENTS = 96
MAX_WORLD_STATE_ROWS = 24
MAX_SOURCE_EVENT_IDS_PER_ROW = 8

WORLD_STATE_RECEIPT_TYPES = (
    "location_updated",
    "resource_changed",
    "faction_changed",
    "infrastructure_changed",
    "settlement_changed",
    "travel_network_changed",
)
CONSUMABLE_EVENT_TYPES = frozenset({"pressure_world_event", "npc_action_event"})
WORLD_STATE_GUARD_RECEIPT_TYPES = (
    "world_state_row_reinserted",
    "world_state_row_restored",
    "world_state_field_restored",
)
CONSUMER_OWNED_COLLECTIONS = (
    "locations",
    "world_resources",
    "market_state",
    "infrastructure_state",
    "travel_routes",
    "settlement_conditions",
    "faction_pressure",
    "actor_health_registry",
    "actor_location_registry",
)
PROMPT_HIDDEN_ROW_FIELDS = frozenset({"source_event_ids", "updated_turn"})
MAX_WORLD_STATE_GUARD_RECEIPTS = 48
MAX_GUARD_SUMMARY_CHARS = 240


def _stable_id(prefix: str, *parts: Any) -> str:
    material = ":".join(str(part or "") for part in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:12]}"


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bounded_str(value: Any, limit: int = 120) -> str:
    return str(value or "").strip()[:limit]


def _bounded_str_list(values: Any, limit: int) -> List[str]:
    out: List[str] = []
    raw = values if isinstance(values, list) else [values]
    for value in raw or []:
        text = _bounded_str(value)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _append_unique(row: Dict[str, Any], key: str, value: str, *, limit: int = 8) -> None:
    values = _bounded_str_list(row.get(key) or [], limit)
    if value and value not in values:
        values.append(value[:120])
    row[key] = values[-limit:]


def _collection(rolling_state: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    rows = rolling_state.get(key)
    if not isinstance(rows, list):
        rows = []
    clean = [row for row in rows if isinstance(row, dict)]
    rolling_state[key] = clean[:MAX_WORLD_STATE_ROWS]
    return rolling_state[key]


def _find_or_create_row(
    rolling_state: Dict[str, Any],
    collection_key: str,
    row_id: str,
    *,
    defaults: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    rows = _collection(rolling_state, collection_key)
    for row in rows:
        if str(row.get("id") or row.get("name") or "") == row_id:
            row.setdefault("id", row_id)
            return row
    row = {"id": row_id}
    if defaults:
        row.update(copy.deepcopy(dict(defaults)))
    rows.append(row)
    if len(rows) > MAX_WORLD_STATE_ROWS:
        del rows[:-MAX_WORLD_STATE_ROWS]
    return row


def _receipt_id(receipt_type: str, event_id: str, target_kind: str, target_id: str) -> str:
    return _stable_id("world-receipt", receipt_type, event_id, target_kind, target_id)


def _append_world_state_receipt(
    replayability_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    receipt_type: str,
    event_id: str,
    turn_number: int,
    target_kind: str,
    target_id: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> None:
    if receipt_type not in WORLD_STATE_RECEIPT_TYPES:
        return
    rid = _receipt_id(receipt_type, event_id, target_kind, target_id)
    receipts = replayability_state.setdefault("world_state_receipts", [])
    if any(isinstance(row, dict) and row.get("receipt_id") == rid for row in receipts):
        return
    receipt = {
        "version": WORLD_STATE_CONSUMER_VERSION,
        "receipt_id": rid,
        "receipt_type": receipt_type,
        "event_id": event_id,
        "turn": turn_number,
        "target_kind": target_kind,
        "target_id": target_id,
        "before": dict(before),
        "after": dict(after),
    }
    receipts.append(receipt)
    if len(receipts) > MAX_WORLD_STATE_RECEIPTS:
        replayability_state["world_state_receipts"] = receipts[-MAX_WORLD_STATE_RECEIPTS:]
    local_receipts.append(receipt)


def _guard_receipt_id(receipt_type: str, turn_number: int, collection: str, row_id: str, detail: str) -> str:
    return _stable_id("world-guard", receipt_type, turn_number, collection, row_id, detail)


def _append_world_state_guard_receipt(
    replayability_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    receipt_type: str,
    turn_number: int,
    collection: str,
    row_id: str,
    detail: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    source_event_ids: Optional[List[str]] = None,
    attempted_value: Any = None,
    authoritative_value: Any = None,
) -> None:
    if receipt_type not in WORLD_STATE_GUARD_RECEIPT_TYPES:
        return
    rid = _guard_receipt_id(receipt_type, turn_number, collection, row_id, detail)
    receipts = replayability_state.setdefault("world_state_guard_receipts", [])
    if any(isinstance(row, dict) and row.get("receipt_id") == rid for row in receipts):
        return
    receipt = {
        "version": WORLD_STATE_CONSUMER_VERSION,
        "receipt_id": rid,
        "receipt_type": receipt_type,
        "turn": turn_number,
        "collection": collection,
        "row_id": row_id,
        "detail": detail,
        "before": dict(before),
        "after": dict(after),
    }
    if source_event_ids:
        receipt["source_event_ids"] = _bounded_str_list(source_event_ids, MAX_SOURCE_EVENT_IDS_PER_ROW)
    if attempted_value is not None:
        receipt["attempted_value_summary"] = _bounded_summary(attempted_value)
    if authoritative_value is not None:
        receipt["authoritative_value_summary"] = _bounded_summary(authoritative_value)
    receipts.append(receipt)
    if len(receipts) > MAX_WORLD_STATE_GUARD_RECEIPTS:
        replayability_state["world_state_guard_receipts"] = receipts[-MAX_WORLD_STATE_GUARD_RECEIPTS:]
    local_receipts.append(receipt)


def _event_id(event: Mapping[str, Any]) -> str:
    return _bounded_str(event.get("event_id"), 160)


def _bounded_summary(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, (str, int, float, bool)):
        return _bounded_str(value, MAX_GUARD_SUMMARY_CHARS)
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except TypeError:
        text = _bounded_str(value, MAX_GUARD_SUMMARY_CHARS)
    return text[:MAX_GUARD_SUMMARY_CHARS]


def _event_kind(event: Mapping[str, Any]) -> str:
    return _bounded_str(event.get("pressure_event_kind") or event.get("event_kind"), 80)


def _first_target(event: Mapping[str, Any], key: str, fallback: str = "") -> str:
    values = _bounded_str_list(event.get(key) or [], 8)
    return values[0] if values else fallback


def _mark_source(row: Dict[str, Any], event_id: str) -> None:
    _append_unique(row, "source_event_ids", event_id, limit=MAX_SOURCE_EVENT_IDS_PER_ROW)


def prompt_safe_world_state(rolling_state: Mapping[str, Any]) -> Dict[str, Any]:
    """Remove consumer metadata while preserving structured world state."""
    if not isinstance(rolling_state, Mapping):
        return {}
    safe = copy.deepcopy(dict(rolling_state))
    for key in CONSUMER_OWNED_COLLECTIONS:
        rows = safe.get(key)
        if not isinstance(rows, list):
            continue
        cleaned: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            cleaned.append({k: copy.deepcopy(v) for k, v in row.items() if k not in PROMPT_HIDDEN_ROW_FIELDS})
        safe[key] = cleaned
    return safe


def _mutate_location(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    event: Mapping[str, Any],
    turn_number: int,
    location_id: str,
    status: str,
    condition: str,
) -> int:
    event_id = _event_id(event)
    row = _find_or_create_row(
        rolling_state,
        "locations",
        location_id,
        defaults={"status": "known", "conditions": []},
    )
    before = copy.deepcopy(row)
    row["status"] = status
    _append_unique(row, "conditions", condition, limit=8)
    row["updated_turn"] = turn_number
    _mark_source(row, event_id)
    _append_world_state_receipt(
        replayability_state,
        local_receipts,
        receipt_type="location_updated",
        event_id=event_id,
        turn_number=turn_number,
        target_kind="location",
        target_id=location_id,
        before=before,
        after=row,
    )
    return 1


def _mutate_infrastructure(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    event: Mapping[str, Any],
    turn_number: int,
    location_id: str,
    status: str,
    condition: str,
) -> int:
    event_id = _event_id(event)
    infra_id = _stable_id("infrastructure", location_id)
    row = _find_or_create_row(
        rolling_state,
        "infrastructure_state",
        infra_id,
        defaults={"location_id": location_id, "status": "usable", "conditions": []},
    )
    before = copy.deepcopy(row)
    row["location_id"] = location_id
    row["status"] = status
    _append_unique(row, "conditions", condition, limit=8)
    row["updated_turn"] = turn_number
    _mark_source(row, event_id)
    _append_world_state_receipt(
        replayability_state,
        local_receipts,
        receipt_type="infrastructure_changed",
        event_id=event_id,
        turn_number=turn_number,
        target_kind="infrastructure",
        target_id=infra_id,
        before=before,
        after=row,
    )
    return 1


def _mutate_travel_route(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    event: Mapping[str, Any],
    turn_number: int,
    location_id: str,
    status: str,
    condition: str,
) -> int:
    event_id = _event_id(event)
    route_id = _stable_id("route", location_id)
    row = _find_or_create_row(
        rolling_state,
        "travel_routes",
        route_id,
        defaults={"location_id": location_id, "status": "open", "conditions": []},
    )
    before = copy.deepcopy(row)
    row["location_id"] = location_id
    row["status"] = status
    _append_unique(row, "conditions", condition, limit=8)
    row["updated_turn"] = turn_number
    _mark_source(row, event_id)
    _append_world_state_receipt(
        replayability_state,
        local_receipts,
        receipt_type="travel_network_changed",
        event_id=event_id,
        turn_number=turn_number,
        target_kind="travel_route",
        target_id=route_id,
        before=before,
        after=row,
    )
    return 1


def _mutate_resource(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    event: Mapping[str, Any],
    turn_number: int,
    resource_id: str,
    delta: int,
    trend: str,
    status: str,
) -> int:
    event_id = _event_id(event)
    row = _find_or_create_row(
        rolling_state,
        "world_resources",
        resource_id,
        defaults={"status": "stable", "quantity_delta": 0, "trend": "stable"},
    )
    before = copy.deepcopy(row)
    row["quantity_delta"] = _coerce_int(row.get("quantity_delta"), 0) + delta
    row["trend"] = trend
    row["status"] = status
    row["updated_turn"] = turn_number
    _mark_source(row, event_id)
    _append_world_state_receipt(
        replayability_state,
        local_receipts,
        receipt_type="resource_changed",
        event_id=event_id,
        turn_number=turn_number,
        target_kind="resource",
        target_id=resource_id,
        before=before,
        after=row,
    )
    return 1


def _mutate_faction(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    event: Mapping[str, Any],
    turn_number: int,
    faction_id: str,
    security_delta: int = 0,
    influence_delta: int = 0,
) -> int:
    event_id = _event_id(event)
    rows = rolling_state.get("faction_pressure")
    if not isinstance(rows, list):
        rows = []
    rolling_state["faction_pressure"] = rows
    row = None
    for candidate in rows:
        if isinstance(candidate, dict) and str(candidate.get("id") or candidate.get("name") or "") == faction_id:
            row = candidate
            break
    if row is None:
        row = {"id": faction_id, "name": faction_id, "ticks": {}}
        rows.append(row)
    del rows[:-MAX_WORLD_STATE_ROWS]
    before = copy.deepcopy(row)
    ticks = row.setdefault("ticks", {})
    if isinstance(ticks, dict):
        ticks["security"] = _coerce_int(ticks.get("security"), 0) + security_delta
        ticks["influence"] = _coerce_int(ticks.get("influence"), 0) + influence_delta
    row["updated_turn"] = turn_number
    _mark_source(row, event_id)
    _append_world_state_receipt(
        replayability_state,
        local_receipts,
        receipt_type="faction_changed",
        event_id=event_id,
        turn_number=turn_number,
        target_kind="faction",
        target_id=faction_id,
        before=before,
        after=row,
    )
    return 1


def _mutate_settlement(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    event: Mapping[str, Any],
    turn_number: int,
    location_id: str,
    condition: str,
    status: str,
) -> int:
    event_id = _event_id(event)
    settlement_id = _stable_id("settlement", location_id or "local")
    row = _find_or_create_row(
        rolling_state,
        "settlement_conditions",
        settlement_id,
        defaults={"location_id": location_id, "status": "stable", "conditions": []},
    )
    before = copy.deepcopy(row)
    row["location_id"] = location_id
    row["status"] = status
    _append_unique(row, "conditions", condition, limit=8)
    row["updated_turn"] = turn_number
    _mark_source(row, event_id)
    _append_world_state_receipt(
        replayability_state,
        local_receipts,
        receipt_type="settlement_changed",
        event_id=event_id,
        turn_number=turn_number,
        target_kind="settlement",
        target_id=settlement_id,
        before=before,
        after=row,
    )
    return 1


def _mutate_actor_health(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    event: Mapping[str, Any],
    turn_number: int,
    actor_id: str,
    status: str,
) -> int:
    event_id = _event_id(event)
    row = _find_or_create_row(
        rolling_state,
        "actor_health_registry",
        actor_id,
        defaults={"health_status": "stable"},
    )
    before = copy.deepcopy(row)
    row["health_status"] = status
    row["updated_turn"] = turn_number
    _mark_source(row, event_id)
    _append_world_state_receipt(
        replayability_state,
        local_receipts,
        receipt_type="settlement_changed",
        event_id=event_id,
        turn_number=turn_number,
        target_kind="actor_health",
        target_id=actor_id,
        before=before,
        after=row,
    )
    return 1


def _mutate_actor_location(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    event: Mapping[str, Any],
    turn_number: int,
    actor_id: str,
    location_id: str,
    status: str,
) -> int:
    event_id = _event_id(event)
    row = _find_or_create_row(
        rolling_state,
        "actor_location_registry",
        actor_id,
        defaults={"location_id": location_id, "status": "present"},
    )
    before = copy.deepcopy(row)
    row["location_id"] = location_id
    row["status"] = status
    row["updated_turn"] = turn_number
    _mark_source(row, event_id)
    _append_world_state_receipt(
        replayability_state,
        local_receipts,
        receipt_type="location_updated",
        event_id=event_id,
        turn_number=turn_number,
        target_kind="actor_location",
        target_id=actor_id,
        before=before,
        after=row,
    )
    return 1


def _resource_id(event: Mapping[str, Any]) -> str:
    location = _first_target(event, "location_ids", "local")
    return _stable_id("resource", location, "general_supplies")


def _consume_collapse(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    event: Mapping[str, Any],
    turn_number: int,
) -> Tuple[int, int]:
    location_id = _first_target(event, "location_ids")
    if not location_id:
        return 0, 1
    count = 0
    count += _mutate_location(
        replayability_state, rolling_state, local_receipts,
        event=event, turn_number=turn_number, location_id=location_id,
        status="blocked", condition="collapsed",
    )
    count += _mutate_infrastructure(
        replayability_state, rolling_state, local_receipts,
        event=event, turn_number=turn_number, location_id=location_id,
        status="damaged", condition="structural_failure",
    )
    count += _mutate_travel_route(
        replayability_state, rolling_state, local_receipts,
        event=event, turn_number=turn_number, location_id=location_id,
        status="blocked", condition="route_obstructed",
    )
    return min(count, MAX_WORLD_STATE_MUTATIONS_PER_EVENT), 0


def _consume_raid(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    event: Mapping[str, Any],
    turn_number: int,
) -> Tuple[int, int]:
    count = _mutate_resource(
        replayability_state, rolling_state, local_receipts,
        event=event, turn_number=turn_number, resource_id=_resource_id(event),
        delta=-2, trend="decreasing", status="reduced",
    )
    faction_id = _first_target(event, "faction_ids")
    if faction_id and count < MAX_WORLD_STATE_MUTATIONS_PER_EVENT:
        count += _mutate_faction(
            replayability_state, rolling_state, local_receipts,
            event=event, turn_number=turn_number, faction_id=faction_id,
            security_delta=-1, influence_delta=-1,
        )
    location_id = _first_target(event, "location_ids")
    if location_id and count < MAX_WORLD_STATE_MUTATIONS_PER_EVENT:
        count += _mutate_settlement(
            replayability_state, rolling_state, local_receipts,
            event=event, turn_number=turn_number, location_id=location_id,
            condition="security_decreased", status="unstable",
        )
    return min(count, MAX_WORLD_STATE_MUTATIONS_PER_EVENT), 0


def _consume_trader_arrival(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    event: Mapping[str, Any],
    turn_number: int,
) -> Tuple[int, int]:
    count = _mutate_resource(
        replayability_state, rolling_state, local_receipts,
        event=event, turn_number=turn_number, resource_id=_resource_id(event),
        delta=2, trend="increasing", status="improving",
    )
    location_id = _first_target(event, "location_ids", "local")
    market = _find_or_create_row(
        rolling_state,
        "market_state",
        _stable_id("market", location_id),
        defaults={"location_id": location_id, "status": "quiet", "conditions": []},
    )
    before = copy.deepcopy(market)
    market["location_id"] = location_id
    market["status"] = "active"
    _append_unique(market, "conditions", "trader_arrived", limit=8)
    market["updated_turn"] = turn_number
    _mark_source(market, _event_id(event))
    _append_world_state_receipt(
        replayability_state,
        local_receipts,
        receipt_type="resource_changed",
        event_id=_event_id(event),
        turn_number=turn_number,
        target_kind="market",
        target_id=str(market.get("id") or ""),
        before=before,
        after=market,
    )
    count += 1
    if location_id and count < MAX_WORLD_STATE_MUTATIONS_PER_EVENT:
        count += _mutate_settlement(
            replayability_state, rolling_state, local_receipts,
            event=event, turn_number=turn_number, location_id=location_id,
            condition="trade_available", status="improving",
        )
    return min(count, MAX_WORLD_STATE_MUTATIONS_PER_EVENT), 0


def _consume_resource_loss(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    event: Mapping[str, Any],
    turn_number: int,
    *,
    delta: int,
    condition: str,
) -> Tuple[int, int]:
    count = _mutate_resource(
        replayability_state, rolling_state, local_receipts,
        event=event, turn_number=turn_number, resource_id=_resource_id(event),
        delta=delta, trend="decreasing", status="shortage",
    )
    location_id = _first_target(event, "location_ids")
    if location_id and count < MAX_WORLD_STATE_MUTATIONS_PER_EVENT:
        count += _mutate_settlement(
            replayability_state, rolling_state, local_receipts,
            event=event, turn_number=turn_number, location_id=location_id,
            condition=condition, status="strained",
        )
    return count, 0


def _consume_fire(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    event: Mapping[str, Any],
    turn_number: int,
) -> Tuple[int, int]:
    location_id = _first_target(event, "location_ids")
    if not location_id:
        return 0, 1
    count = _mutate_location(
        replayability_state, rolling_state, local_receipts,
        event=event, turn_number=turn_number, location_id=location_id,
        status="unstable", condition="fire",
    )
    count += _mutate_infrastructure(
        replayability_state, rolling_state, local_receipts,
        event=event, turn_number=turn_number, location_id=location_id,
        status="damaged", condition="fire_damage",
    )
    if count < MAX_WORLD_STATE_MUTATIONS_PER_EVENT:
        count += _mutate_settlement(
            replayability_state, rolling_state, local_receipts,
            event=event, turn_number=turn_number, location_id=location_id,
            condition="evacuation_marker", status="unstable",
        )
    return min(count, MAX_WORLD_STATE_MUTATIONS_PER_EVENT), 0


def _consume_disease(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    event: Mapping[str, Any],
    turn_number: int,
) -> Tuple[int, int]:
    location_id = _first_target(event, "location_ids", "local")
    count = _mutate_settlement(
        replayability_state, rolling_state, local_receipts,
        event=event, turn_number=turn_number, location_id=location_id,
        condition="health_decreased", status="strained",
    )
    actor_id = _first_target(event, "actor_ids")
    if actor_id and count < MAX_WORLD_STATE_MUTATIONS_PER_EVENT:
        count += _mutate_actor_health(
            replayability_state, rolling_state, local_receipts,
            event=event, turn_number=turn_number, actor_id=actor_id, status="sick",
        )
    return count, 0


def _consume_faction_or_location_tension(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    event: Mapping[str, Any],
    turn_number: int,
    *,
    condition: str,
) -> Tuple[int, int]:
    faction_id = _first_target(event, "faction_ids")
    if faction_id:
        return _mutate_faction(
            replayability_state, rolling_state, local_receipts,
            event=event, turn_number=turn_number, faction_id=faction_id,
            security_delta=-1, influence_delta=-1,
        ), 0
    return _consume_generic_location(
        replayability_state, rolling_state, local_receipts, event, turn_number,
        status="unstable", condition=condition,
    )


def _consume_generic_location(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    event: Mapping[str, Any],
    turn_number: int,
    *,
    status: str,
    condition: str,
) -> Tuple[int, int]:
    location_id = _first_target(event, "location_ids")
    if not location_id:
        return 0, 1
    return _mutate_location(
        replayability_state, rolling_state, local_receipts,
        event=event, turn_number=turn_number, location_id=location_id,
        status=status, condition=condition,
    ), 0


def _consume_npc_travel(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    event: Mapping[str, Any],
    turn_number: int,
) -> Tuple[int, int]:
    actor_id = _first_target(event, "actor_ids")
    location_id = _first_target(event, "location_ids", "local")
    if not actor_id:
        return 0, 1
    return _mutate_actor_location(
        replayability_state, rolling_state, local_receipts,
        event=event, turn_number=turn_number, actor_id=actor_id,
        location_id=location_id, status="present",
    ), 0


def _consume_npc_resource_gain(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    event: Mapping[str, Any],
    turn_number: int,
) -> Tuple[int, int]:
    count = _mutate_resource(
        replayability_state, rolling_state, local_receipts,
        event=event, turn_number=turn_number, resource_id=_resource_id(event),
        delta=1, trend="increasing", status="improving",
    )
    location_id = _first_target(event, "location_ids")
    if location_id and count < MAX_WORLD_STATE_MUTATIONS_PER_EVENT:
        count += _mutate_settlement(
            replayability_state, rolling_state, local_receipts,
            event=event, turn_number=turn_number, location_id=location_id,
            condition="resource_secured", status="improving",
        )
    return count, 0


def _consume_npc_repair(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    event: Mapping[str, Any],
    turn_number: int,
) -> Tuple[int, int]:
    location_id = _first_target(event, "location_ids")
    if not location_id:
        return 0, 1
    count = _mutate_infrastructure(
        replayability_state, rolling_state, local_receipts,
        event=event, turn_number=turn_number, location_id=location_id,
        status="repairing", condition="repair_progress",
    )
    if count < MAX_WORLD_STATE_MUTATIONS_PER_EVENT:
        count += _mutate_travel_route(
            replayability_state, rolling_state, local_receipts,
            event=event, turn_number=turn_number, location_id=location_id,
            status="improving", condition="route_repair",
        )
    return count, 0


def _consume_npc_warning_or_defense(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    event: Mapping[str, Any],
    turn_number: int,
) -> Tuple[int, int]:
    location_id = _first_target(event, "location_ids")
    faction_id = _first_target(event, "faction_ids")
    count = 0
    skipped = 0
    if location_id:
        count += _mutate_settlement(
            replayability_state, rolling_state, local_receipts,
            event=event, turn_number=turn_number, location_id=location_id,
            condition="prepared", status="guarded",
        )
    else:
        skipped += 1
    if faction_id and count < MAX_WORLD_STATE_MUTATIONS_PER_EVENT:
        count += _mutate_faction(
            replayability_state, rolling_state, local_receipts,
            event=event, turn_number=turn_number, faction_id=faction_id,
            security_delta=1, influence_delta=0,
        )
    return count, skipped


def _consume_npc_retreat(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    event: Mapping[str, Any],
    turn_number: int,
) -> Tuple[int, int]:
    actor_id = _first_target(event, "actor_ids")
    location_id = _first_target(event, "location_ids", "local")
    if not actor_id:
        return 0, 1
    return _mutate_actor_location(
        replayability_state, rolling_state, local_receipts,
        event=event, turn_number=turn_number, actor_id=actor_id,
        location_id=location_id, status="retreated",
    ), 0


def _consume_event(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    event: Mapping[str, Any],
    turn_number: int,
) -> Tuple[int, int]:
    kind = _event_kind(event)
    if kind == "collapse":
        return _consume_collapse(replayability_state, rolling_state, local_receipts, event, turn_number)
    if kind == "raid":
        return _consume_raid(replayability_state, rolling_state, local_receipts, event, turn_number)
    if kind == "trader_arrival":
        return _consume_trader_arrival(replayability_state, rolling_state, local_receipts, event, turn_number)
    if kind in {"supplies_exhausted", "theft"}:
        return _consume_resource_loss(
            replayability_state, rolling_state, local_receipts, event, turn_number,
            delta=-3 if kind == "supplies_exhausted" else -1,
            condition="shortage_flag",
        )
    if kind == "resource_discovery" or kind == "abandoned_cache":
        return _mutate_resource(
            replayability_state, rolling_state, local_receipts,
            event=event, turn_number=turn_number, resource_id=_resource_id(event),
            delta=3 if kind == "resource_discovery" else 1,
            trend="increasing", status="improving",
        ), 0
    if kind == "price_increase":
        return _consume_generic_location(
            replayability_state, rolling_state, local_receipts, event, turn_number,
            status="strained", condition="prices_rising",
        )
    if kind == "fire":
        return _consume_fire(replayability_state, rolling_state, local_receipts, event, turn_number)
    if kind == "disease":
        return _consume_disease(replayability_state, rolling_state, local_receipts, event, turn_number)
    if kind == "argument":
        return _consume_faction_or_location_tension(
            replayability_state, rolling_state, local_receipts, event, turn_number,
            condition="argument",
        )
    if kind == "alliance_fracture":
        return _consume_faction_or_location_tension(
            replayability_state, rolling_state, local_receipts, event, turn_number,
            condition="alliance_fracture",
        )
    if kind in {"injury", "accident"}:
        actor_id = _first_target(event, "actor_ids")
        if actor_id:
            return _mutate_actor_health(
                replayability_state, rolling_state, local_receipts,
                event=event, turn_number=turn_number, actor_id=actor_id, status="injured",
            ), 0
    if kind in {"accident", "attack", "injury", "evacuation", "protest", "retaliation"}:
        count, skipped = _consume_generic_location(
            replayability_state, rolling_state, local_receipts, event, turn_number,
            status="unstable", condition=kind,
        )
        if kind in {"evacuation"}:
            actor_id = _first_target(event, "actor_ids")
            location_id = _first_target(event, "location_ids", "local")
            if actor_id and count < MAX_WORLD_STATE_MUTATIONS_PER_EVENT:
                count += _mutate_actor_location(
                    replayability_state, rolling_state, local_receipts,
                    event=event, turn_number=turn_number, actor_id=actor_id,
                    location_id=location_id, status="relocated",
                )
        return count, skipped
    if kind in {"strange_evidence", "unexplained_disappearance", "mysterious_signal", "rumor_spread"}:
        count, skipped = _consume_generic_location(
            replayability_state, rolling_state, local_receipts, event, turn_number,
            status="uncertain", condition=kind,
        )
        if kind == "unexplained_disappearance":
            actor_id = _first_target(event, "actor_ids")
            location_id = _first_target(event, "location_ids", "unknown")
            if actor_id and count < MAX_WORLD_STATE_MUTATIONS_PER_EVENT:
                count += _mutate_actor_location(
                    replayability_state, rolling_state, local_receipts,
                    event=event, turn_number=turn_number, actor_id=actor_id,
                    location_id=location_id, status="missing",
                )
        return count, skipped
    if kind == "npc_travelled":
        return _consume_npc_travel(replayability_state, rolling_state, local_receipts, event, turn_number)
    if kind in {"npc_gathered_food", "npc_secured_resource", "npc_delivered_resource"}:
        return _consume_npc_resource_gain(replayability_state, rolling_state, local_receipts, event, turn_number)
    if kind == "npc_repaired_bridge":
        return _consume_npc_repair(replayability_state, rolling_state, local_receipts, event, turn_number)
    if kind in {"npc_warned_settlement", "npc_defended_area", "npc_recruited_member"}:
        return _consume_npc_warning_or_defense(replayability_state, rolling_state, local_receipts, event, turn_number)
    if kind == "npc_retreated":
        return _consume_npc_retreat(replayability_state, rolling_state, local_receipts, event, turn_number)
    if kind in {"npc_found_clue", "npc_failed_search", "npc_observed", "npc_negotiated"}:
        return _consume_generic_location(
            replayability_state, rolling_state, local_receipts, event, turn_number,
            status="active", condition=kind,
        )
    if kind in {"npc_attacked", "npc_action_failed"}:
        return _consume_generic_location(
            replayability_state, rolling_state, local_receipts, event, turn_number,
            status="unstable", condition=kind,
        )
    if kind in {"npc_hid_evidence", "npc_waited"}:
        return 0, 0
    return 0, 1


def consume_pressure_world_events(
    replayability_state: Dict[str, Any],
    rolling_state: Dict[str, Any],
    turn_number: int,
) -> Dict[str, Any]:
    """Consume engine-owned world events into bounded structured world state."""
    diagnostics = {
        "world_state_consumer_executed": False,
        "world_state_events_consumed": 0,
        "world_state_mutation_count": 0,
        "world_state_skipped_mutations": 0,
        "world_state_duplicate_suppressed": 0,
        "world_state_replay_suppressed": 0,
    }
    if not isinstance(replayability_state, dict) or not isinstance(rolling_state, dict):
        return {"receipts": [], "diagnostics": diagnostics}

    processed = _bounded_str_list(
        replayability_state.get("world_state_consumed_event_ids") or [],
        MAX_PROCESSED_WORLD_EVENTS,
    )
    replayability_state["world_state_consumed_event_ids"] = processed
    processed_set = set(processed)
    seen_this_pass = set()
    local_receipts: List[Dict[str, Any]] = []
    events = [
        event for event in replayability_state.get("engine_world_events") or []
        if isinstance(event, Mapping)
    ]
    events.sort(key=lambda row: (_coerce_int(row.get("turn"), 0), _event_id(row)))

    attempted = 0
    for event in events:
        if attempted >= MAX_WORLD_STATE_CONSUMER_EVENTS_PER_TICK:
            break
        if event.get("event_type") not in CONSUMABLE_EVENT_TYPES:
            continue
        eid = _event_id(event)
        if not eid:
            diagnostics["world_state_skipped_mutations"] += 1
            continue
        if eid in seen_this_pass:
            diagnostics["world_state_duplicate_suppressed"] += 1
            continue
        seen_this_pass.add(eid)
        if eid in processed_set:
            diagnostics["world_state_replay_suppressed"] += 1
            continue

        attempted += 1
        before_receipt_count = len(local_receipts)
        mutations, skipped = _consume_event(
            replayability_state,
            rolling_state,
            local_receipts,
            event,
            turn_number,
        )
        mutations = min(mutations, MAX_WORLD_STATE_MUTATIONS_PER_EVENT)
        diagnostics["world_state_mutation_count"] += mutations
        diagnostics["world_state_skipped_mutations"] += skipped
        diagnostics["world_state_events_consumed"] += 1
        diagnostics["world_state_consumer_executed"] = True
        processed.append(eid)
        processed_set.add(eid)
        if len(local_receipts) - before_receipt_count > MAX_WORLD_STATE_MUTATIONS_PER_EVENT:
            del local_receipts[before_receipt_count + MAX_WORLD_STATE_MUTATIONS_PER_EVENT:]

    if len(processed) > MAX_PROCESSED_WORLD_EVENTS:
        replayability_state["world_state_consumed_event_ids"] = processed[-MAX_PROCESSED_WORLD_EVENTS:]
    return {"receipts": local_receipts, "diagnostics": diagnostics}


def _row_key(collection: str, row: Mapping[str, Any]) -> str:
    if collection == "faction_pressure":
        return _bounded_str(row.get("id") or row.get("name"), 160)
    return _bounded_str(row.get("id"), 160)


def _owned_row(row: Mapping[str, Any]) -> bool:
    return bool(_bounded_str_list(row.get("source_event_ids") or [], MAX_SOURCE_EVENT_IDS_PER_ROW))


def _row_source_event_ids(row: Mapping[str, Any]) -> List[str]:
    return _bounded_str_list(row.get("source_event_ids") or [], MAX_SOURCE_EVENT_IDS_PER_ROW)


def _row_map(rolling_state: Mapping[str, Any], collection: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    rows = rolling_state.get(collection)
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = _row_key(collection, row)
        if row_id:
            out[row_id] = row
    return out


def _restore_full_row(authoritative: Mapping[str, Any], candidate: Mapping[str, Any]) -> Dict[str, Any]:
    restored = copy.deepcopy(dict(candidate))
    for key, value in authoritative.items():
        restored[key] = copy.deepcopy(value)
    return restored


def _restore_faction_row(authoritative: Mapping[str, Any], candidate: Mapping[str, Any]) -> Dict[str, Any]:
    restored = copy.deepcopy(dict(candidate))
    for key in ("id", "name", "movement", "player_reputation", "updated_turn", "source_event_ids"):
        if key in authoritative:
            restored[key] = copy.deepcopy(authoritative[key])
    auth_ticks = authoritative.get("ticks") if isinstance(authoritative.get("ticks"), dict) else {}
    cand_ticks = candidate.get("ticks") if isinstance(candidate.get("ticks"), dict) else {}
    ticks = dict(cand_ticks)
    for key, value in auth_ticks.items():
        ticks[key] = copy.deepcopy(value)
    restored["ticks"] = ticks
    return restored


def _restore_owned_row(collection: str, authoritative: Mapping[str, Any], candidate: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if collection == "faction_pressure":
        return _restore_faction_row(authoritative, candidate or {})
    return _restore_full_row(authoritative, candidate or {})


def enforce_consumer_world_state(
    merged_rolling: Dict[str, Any],
    authoritative_rolling: Mapping[str, Any],
    replayability_state: Dict[str, Any],
    turn_number: int,
) -> Dict[str, Any]:
    """Restore engine-owned consumer rows after model rolling_state merge."""
    local_receipts: List[Dict[str, Any]] = []
    adjustments: List[str] = []
    diagnostics = {
        "world_state_guard_receipts": 0,
        "world_state_guard_rows_restored": 0,
        "world_state_guard_rows_reinserted": 0,
    }
    if not isinstance(merged_rolling, dict) or not isinstance(authoritative_rolling, Mapping):
        return {"receipts": [], "adjustments": [], "diagnostics": diagnostics}

    for collection in CONSUMER_OWNED_COLLECTIONS:
        auth_rows = _row_map(authoritative_rolling, collection)
        if not auth_rows:
            continue
        merged_rows = _row_map(merged_rolling, collection)
        merged_list = _collection(merged_rolling, collection)
        for row_id in sorted(auth_rows.keys()):
            authoritative_row = auth_rows[row_id]
            if not _owned_row(authoritative_row):
                continue
            merged_row = merged_rows.get(row_id)
            if merged_row is None:
                restored = copy.deepcopy(dict(authoritative_row))
                merged_list.append(restored)
                if len(merged_list) > MAX_WORLD_STATE_ROWS:
                    del merged_list[:-MAX_WORLD_STATE_ROWS]
                _append_world_state_guard_receipt(
                    replayability_state,
                    local_receipts,
                    receipt_type="world_state_row_reinserted",
                    turn_number=turn_number,
                    collection=collection,
                    row_id=row_id,
                    detail="missing_row",
                    before={},
                    after=restored,
                    source_event_ids=_row_source_event_ids(authoritative_row),
                    attempted_value={"attempt": "delete_or_omit"},
                    authoritative_value=restored,
                )
                adjustments.append(f"{collection}:{row_id}:reinserted")
                diagnostics["world_state_guard_rows_reinserted"] += 1
                continue
            restored = _restore_owned_row(collection, authoritative_row, merged_row)
            if restored != merged_row:
                before = copy.deepcopy(dict(merged_row))
                merged_row.clear()
                merged_row.update(restored)
                detail = "restored_row"
                receipt_type = "world_state_row_restored"
                if collection == "faction_pressure":
                    detail = "restored_owned_ticks"
                    receipt_type = "world_state_field_restored"
                _append_world_state_guard_receipt(
                    replayability_state,
                    local_receipts,
                    receipt_type=receipt_type,
                    turn_number=turn_number,
                    collection=collection,
                    row_id=row_id,
                    detail=detail,
                    before=before,
                    after=merged_row,
                    source_event_ids=_row_source_event_ids(authoritative_row),
                    attempted_value=before,
                    authoritative_value=restored,
                )
                adjustments.append(f"{collection}:{row_id}:restored")
                diagnostics["world_state_guard_rows_restored"] += 1

    diagnostics["world_state_guard_receipts"] = len(local_receipts)
    return {"receipts": local_receipts, "adjustments": adjustments, "diagnostics": diagnostics}
