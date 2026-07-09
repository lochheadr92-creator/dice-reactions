"""
Internal causal visibility projection.

This module normalises existing engine-owned receipts into a small, bounded
"what changed and why" shape. It is read-only: it does not create authority,
persist state, touch prompts, or inspect narrative output.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

CAUSAL_VISIBILITY_SCHEMA_VERSION = 1
MAX_CAUSAL_VISIBILITY_ENTRIES = 32
MAX_CAUSAL_VISIBILITY_SOURCE_IDS = 8
MAX_CAUSAL_VISIBILITY_METADATA_KEYS = 8
MAX_CAUSAL_VISIBILITY_TEXT = 160

_NARRATIVE_ONLY_KEYS = frozenset(
    {
        "action_text",
        "choices",
        "completion",
        "debug",
        "description",
        "label",
        "narrative",
        "player_action",
        "prompt",
        "prose",
        "raw_output",
        "raw_text",
        "rendered_text",
        "story",
        "summary",
        "text",
    }
)
_NARRATIVE_MARKERS = re.compile(
    r"\b(player said|you chose|the narrative|story text|generated prose|model output)\b",
    re.IGNORECASE,
)

_GRAVITY_RECEIPT_TYPES = frozenset(
    {
        "gravity_keep_active",
        "gravity_compress",
        "gravity_archive",
        "gravity_fade",
    }
)
_ACTOR_RECEIPT_TYPES = frozenset(
    {
        "actor_promoted",
        "actor_demoted",
        "actor_updated",
        "actor_deferred",
    }
)
_CATEGORY_ORDER = {
    "relationship": 0,
    "pressure": 1,
    "gravity": 2,
    "actor": 3,
    "memory": 4,
}


def _clean_text(value: Any, limit: int = MAX_CAUSAL_VISIBILITY_TEXT) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _safe_reason(value: Any) -> str:
    text = _clean_text(value)
    if not text or _NARRATIVE_MARKERS.search(text):
        return ""
    return text


def _coerce_turn(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _bounded_str_list(
    values: Optional[Sequence[Any]],
    limit: int = MAX_CAUSAL_VISIBILITY_SOURCE_IDS,
) -> List[str]:
    out: List[str] = []
    for value in values or []:
        text = _clean_text(value)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _safe_scalar(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    if isinstance(value, str):
        return _clean_text(value)
    return None


def _safe_mapping(
    value: Any,
    *,
    max_keys: int = MAX_CAUSAL_VISIBILITY_METADATA_KEYS,
) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    out: Dict[str, Any] = {}
    for key in sorted(value.keys(), key=str):
        key_text = str(key)
        if key_text in _NARRATIVE_ONLY_KEYS:
            continue
        scalar = _safe_scalar(value.get(key))
        if scalar is None:
            continue
        out[key_text[:80]] = scalar
        if len(out) >= max_keys:
            break
    return out


def _metadata_from(
    source: Mapping[str, Any],
    keys: Sequence[str],
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in keys:
        if key in _NARRATIVE_ONLY_KEYS:
            continue
        value = source.get(key)
        if isinstance(value, (list, tuple)):
            bounded = _bounded_str_list(value)
            if bounded:
                out[key] = bounded
        else:
            scalar = _safe_scalar(value)
            if scalar is not None and scalar != "":
                out[key] = scalar
        if len(out) >= MAX_CAUSAL_VISIBILITY_METADATA_KEYS:
            break
    return out


def _safe_metadata(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    out: Dict[str, Any] = {}
    for key in sorted(value.keys(), key=str):
        key_text = str(key)
        if key_text in _NARRATIVE_ONLY_KEYS:
            continue
        raw = value.get(key)
        if isinstance(raw, (list, tuple)):
            bounded = _bounded_str_list(raw)
            if bounded:
                out[key_text[:80]] = bounded
        else:
            scalar = _safe_scalar(raw)
            if scalar is not None and scalar != "":
                out[key_text[:80]] = scalar
        if len(out) >= MAX_CAUSAL_VISIBILITY_METADATA_KEYS:
            break
    return out


def _stable_entry_id(*parts: Any) -> str:
    material = "|".join(_clean_text(part, 240) for part in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"causal-{digest[:16]}"


def _magnitude_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> Dict[str, Any]:
    delta: Dict[str, Any] = {}
    if "magnitude" in before and "magnitude" in after:
        delta["magnitude"] = _coerce_turn(after.get("magnitude")) - _coerce_turn(
            before.get("magnitude")
        )
    before_status = str(before.get("status") or "")
    after_status = str(after.get("status") or "")
    if before_status and after_status and before_status != after_status:
        delta["status"] = f"{before_status}->{after_status}"[:80]
    return delta


def _base_entry(
    *,
    source_system: str,
    effect_category: str,
    effect_type: str,
    affected_entity_type: str,
    affected_entity_id: str,
    turn: int,
    source_ids: Optional[Sequence[Any]] = None,
    source_receipt_id: str = "",
    before: Optional[Mapping[str, Any]] = None,
    after: Optional[Mapping[str, Any]] = None,
    delta: Optional[Mapping[str, Any]] = None,
    reason: str = "",
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    source_ids_bounded = _bounded_str_list(source_ids)
    before_safe = _safe_mapping(before or {})
    after_safe = _safe_mapping(after or {})
    delta_safe = _safe_mapping(delta or {})
    metadata_safe = _safe_metadata(metadata or {})
    entry = {
        "schema_version": CAUSAL_VISIBILITY_SCHEMA_VERSION,
        "entry_id": _stable_entry_id(
            source_system,
            effect_category,
            effect_type,
            affected_entity_type,
            affected_entity_id,
            turn,
            source_receipt_id,
            ",".join(source_ids_bounded),
        ),
        "turn": int(turn),
        "source_system": _clean_text(source_system, 80),
        "source_receipt_id": _clean_text(source_receipt_id, 160),
        "source_ids": source_ids_bounded,
        "affected_entity_type": _clean_text(affected_entity_type, 80),
        "affected_entity_id": _clean_text(affected_entity_id, 160),
        "effect_category": _clean_text(effect_category, 80),
        "effect_type": _clean_text(effect_type, 80),
        "before": before_safe,
        "after": after_safe,
        "delta": delta_safe,
        "reason": _safe_reason(reason),
        "metadata": metadata_safe,
    }
    return entry


def _pressure_entries(replayability_state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    graph = replayability_state.get("pressure_graph") or {}
    if not isinstance(graph, Mapping):
        return []
    out: List[Dict[str, Any]] = []
    for receipt in graph.get("evolution_receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        receipt_type = _clean_text(receipt.get("receipt_type"), 80)
        if not receipt_type.startswith("pressure_"):
            continue
        before = _safe_mapping(receipt.get("before") or {})
        after = _safe_mapping(receipt.get("after") or {})
        source_ids = []
        if receipt.get("event_id"):
            source_ids.append(receipt.get("event_id"))
        source_ids.extend(receipt.get("source_event_ids") or [])
        metadata = _metadata_from(
            receipt,
            (
                "pressure_kind",
                "source_kind",
                "qualifier",
                "linked_node_id",
                "affected_actor_ids",
                "affected_faction_ids",
                "affected_location_ids",
            ),
        )
        out.append(
            _base_entry(
                source_system="pressure_graph",
                effect_category="pressure",
                effect_type=receipt_type,
                affected_entity_type="pressure_node",
                affected_entity_id=str(receipt.get("node_id") or ""),
                turn=_coerce_turn(receipt.get("turn")),
                source_ids=source_ids,
                source_receipt_id=str(receipt.get("receipt_id") or ""),
                before=before,
                after=after,
                delta=_magnitude_delta(before, after),
                reason=str(receipt.get("reason") or ""),
                metadata=metadata,
            )
        )
    return out


def _relationship_receipt_entries(
    replayability_state: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for receipt in replayability_state.get("relationship_effect_receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        receipt_type = _clean_text(receipt.get("receipt_type"), 80)
        if not receipt_type:
            continue
        npc_name = _clean_text(receipt.get("npc_name") or receipt.get("target_name"), 160)
        before_state = _clean_text(receipt.get("before_state"), 80)
        after_state = _clean_text(receipt.get("after_state"), 80)
        source_ids = [
            receipt.get("source_event_id"),
            receipt.get("source_effect_id"),
        ]
        source_ids.extend(receipt.get("source_event_ids") or [])
        delta = _safe_mapping(receipt.get("dimension_deltas") or {})
        if before_state or after_state:
            delta["state"] = f"{before_state or 'unknown'}->{after_state or 'unknown'}"[:80]
        out.append(
            _base_entry(
                source_system="relationship",
                effect_category="relationship",
                effect_type=receipt_type,
                affected_entity_type="npc",
                affected_entity_id=npc_name,
                turn=_coerce_turn(receipt.get("turn")),
                source_ids=source_ids,
                source_receipt_id=str(receipt.get("receipt_id") or ""),
                before={"state": before_state} if before_state else {},
                after={"state": after_state} if after_state else {},
                delta=delta,
                metadata=_metadata_from(receipt, ("source_kind",)),
            )
        )
    return out


def _relationship_provenance_entries(
    relationship_provenance: Optional[Sequence[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in relationship_provenance or []:
        if not isinstance(row, Mapping) or row.get("rejected"):
            continue
        source_id = _clean_text(row.get("event_id"), 160)
        target = _clean_text(row.get("target_name"), 160)
        if not source_id or not target:
            continue
        effect_type = _clean_text(row.get("kind") or "relationship_delta", 80)
        out.append(
            _base_entry(
                source_system="relationship_provenance",
                effect_category="relationship",
                effect_type=effect_type,
                affected_entity_type="npc",
                affected_entity_id=target,
                turn=_coerce_turn(row.get("turn")),
                source_ids=[source_id],
                source_receipt_id=source_id,
                before=row.get("before") or {},
                after=row.get("after") or {},
                delta=row.get("applied_deltas") or {},
                reason=str(row.get("reason") or ""),
                metadata=_metadata_from(row, ("source_kind", "cause")),
            )
        )
    return out


def _parse_transition_detail(detail: Any) -> Dict[str, str]:
    text = _clean_text(detail, 120)
    if "->" not in text:
        return {}
    before, after = text.split("->", 1)
    return {"before": before.strip()[:80], "after": after.strip()[:80]}


def _entity_type_from_subject(subject_id: str) -> str:
    if ":" in subject_id:
        prefix, _ = subject_id.split(":", 1)
        if prefix:
            return prefix[:80]
    return "actor" if subject_id.startswith("npc-") else "item"


def _scheduling_entries(replayability_state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for receipt in replayability_state.get("scheduling_receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        receipt_type = _clean_text(receipt.get("receipt_type"), 80)
        if receipt_type in _GRAVITY_RECEIPT_TYPES:
            category = "gravity"
        elif receipt_type in _ACTOR_RECEIPT_TYPES:
            category = "actor"
        else:
            continue
        subject_id = _clean_text(receipt.get("subject_id"), 160)
        transition = _parse_transition_detail(receipt.get("detail"))
        before = {"band": transition["before"]} if category == "gravity" and transition else {}
        after = {"band": transition["after"]} if category == "gravity" and transition else {}
        if category == "actor" and transition:
            before = {"tier": transition["before"]}
            after = {"tier": transition["after"]}
        out.append(
            _base_entry(
                source_system="runtime_scheduling",
                effect_category=category,
                effect_type=receipt_type,
                affected_entity_type=_entity_type_from_subject(subject_id),
                affected_entity_id=subject_id,
                turn=_coerce_turn(receipt.get("turn")),
                source_receipt_id=str(receipt.get("receipt_id") or ""),
                before=before,
                after=after,
                delta={"transition": receipt.get("detail")} if transition else {},
                reason=str(receipt.get("detail") or ""),
            )
        )
    return out


def _memory_retrieval_entries(
    retrieval_prepared: Optional[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    if not isinstance(retrieval_prepared, Mapping):
        return []
    out: List[Dict[str, Any]] = []
    for trace in retrieval_prepared.get("retrieval_traces") or []:
        if not isinstance(trace, Mapping):
            continue
        selected = _bounded_str_list(trace.get("selected_memory_ids") or [])
        if not selected:
            continue
        actor_id = _clean_text(trace.get("actor_id"), 160)
        metadata = _metadata_from(trace, ("tier", "working_memory_size", "shadow_mode"))
        out.append(
            _base_entry(
                source_system="memory_retrieval",
                effect_category="memory",
                effect_type="memory_retrieved",
                affected_entity_type="actor",
                affected_entity_id=actor_id,
                turn=_coerce_turn(retrieval_prepared.get("turn") or trace.get("turn")),
                source_ids=selected,
                source_receipt_id=_stable_entry_id("memory_retrieval", actor_id, ",".join(selected)),
                after={"selected_memory_count": len(selected)},
                delta={"selected_memory_count": len(selected)},
                metadata=metadata,
            )
        )
    return out


def _entry_sort_key(entry: Mapping[str, Any]) -> tuple:
    category = str(entry.get("effect_category") or "")
    return (
        _coerce_turn(entry.get("turn")),
        _CATEGORY_ORDER.get(category, 99),
        str(entry.get("effect_type") or ""),
        str(entry.get("affected_entity_type") or ""),
        str(entry.get("affected_entity_id") or ""),
        str(entry.get("entry_id") or ""),
    )


def _dedupe(entries: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for entry in entries:
        entry_id = str(entry.get("entry_id") or "")
        if not entry_id or entry_id in seen:
            continue
        seen.add(entry_id)
        out.append(dict(entry))
    return out


def project_causal_visibility(
    replayability_state: Mapping[str, Any],
    *,
    relationship_provenance: Optional[Sequence[Mapping[str, Any]]] = None,
    retrieval_prepared: Optional[Mapping[str, Any]] = None,
    limit: int = MAX_CAUSAL_VISIBILITY_ENTRIES,
) -> Dict[str, Any]:
    """
    Return a bounded, deterministic causal visibility projection.

    The projection is derived only from existing authoritative receipts and
    diagnostics. It does not mutate inputs and is not player-safe by itself.
    """
    state = replayability_state if isinstance(replayability_state, Mapping) else {}
    entries = []
    entries.extend(_relationship_receipt_entries(state))
    entries.extend(_relationship_provenance_entries(relationship_provenance))
    entries.extend(_pressure_entries(state))
    entries.extend(_scheduling_entries(state))
    entries.extend(_memory_retrieval_entries(retrieval_prepared))
    ordered = _dedupe(sorted(entries, key=_entry_sort_key))

    try:
        bounded_limit = max(0, min(int(limit), MAX_CAUSAL_VISIBILITY_ENTRIES))
    except (TypeError, ValueError):
        bounded_limit = MAX_CAUSAL_VISIBILITY_ENTRIES
    truncated = len(ordered) > bounded_limit
    if bounded_limit == 0:
        visible: List[Dict[str, Any]] = []
    else:
        visible = ordered[-bounded_limit:]

    return {
        "schema_version": CAUSAL_VISIBILITY_SCHEMA_VERSION,
        "max_entries": bounded_limit,
        "entry_count": len(visible),
        "truncated": truncated,
        "entries": visible,
    }
