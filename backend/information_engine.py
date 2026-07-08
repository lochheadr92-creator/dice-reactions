"""
Deterministic Information, Rumour, and Reputation Engine.

Information state is canonical engine state under replayability_state. It stores
beliefs, rumours, evidence summaries, and reputation signals as distinct from
objective truth. Narrative may render these facts, but it never creates or
mutates them.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

INFORMATION_ENGINE_VERSION = 1

MAX_INFORMATION_ITEMS = 24
MAX_REPUTATION_SIGNALS = 24
MAX_INFORMATION_RECEIPTS = 64
MAX_INFORMATION_CHANGES_PER_TICK = 8
MAX_INFORMATION_REFS = 8
MAX_KNOWN_BY = 8
MAX_OBSERVER_ACCESS = 12
MAX_SUBJECT_REFS = 8
MAX_PROJECTED_INFORMATION = 6
MAX_PROJECTED_REPUTATION = 6
MAX_PROMPT_INFORMATION = 4
MAX_PROMPT_REPUTATION = 4
MAX_CONTEXT_INFORMATION = 4
MAX_CONTEXT_REPUTATION = 4
MAX_PROPAGATION_CHANGES_PER_TICK = 4
DECAY_INTERVAL_TURNS = 8
STALE_RUMOUR_TURNS = 16
LOW_GRAVITY_DECAY_THRESHOLD = 3

INFORMATION_TYPES = frozenset(
    {"truth", "rumour", "claim", "evidence_summary", "reputation_signal"}
)
VISIBILITY_SCOPES = frozenset(
    {"private", "witnessed", "settlement", "faction", "public", "case", "unknown", "archived"}
)
ACCESS_TYPES = frozenset(
    {
        "direct_witness",
        "participant",
        "local_community",
        "faction_channel",
        "settlement_scope",
        "investigation_channel",
        "player_known",
        "unknown_unobserved",
        "secondary_source",
    }
)
REPUTATION_DIMENSIONS = frozenset(
    {"trustworthy", "dangerous", "competent", "generous", "cruel", "suspicious"}
)
INFORMATION_RECEIPT_TYPES = (
    "information_created",
    "information_reinforced",
    "information_propagated",
    "information_decayed",
    "reputation_signal_created",
    "reputation_signal_updated",
    "reputation_signal_decayed",
)

HIGH_GRAVITY_WORLD_EVENT_SEVERITY = 7
PRESSURE_SIGNAL_MAX = 8
PRESSURE_INFORMATION_MIN_GRAVITY = 6
PRESSURE_RUMOUR_MIN_GRAVITY = 7
PRESSURE_INFORMATION_MIN_RELIABILITY = 72
PRESSURE_RUMOUR_MIN_RELIABILITY = 68
PRESSURE_REPUTATION_MIN_CONFIDENCE = 70
PRESSURE_REPUTATION_MIN_RELIABILITY = 70
PRESSURE_REPUTATION_MIN_SCORE = 22

EVENT_REPUTATION_MAP: Dict[str, Tuple[str, int]] = {
    "attack": ("dangerous", 25),
    "raid": ("dangerous", 30),
    "retaliation": ("dangerous", 22),
    "npc_attacked": ("dangerous", 22),
    "npc_defended_area": ("trustworthy", 18),
    "npc_warned_settlement": ("trustworthy", 18),
    "npc_repaired_bridge": ("competent", 18),
    "npc_secured_resource": ("competent", 16),
    "npc_gathered_food": ("generous", 12),
    "npc_delivered_resource": ("generous", 18),
    "resource_discovery": ("generous", 12),
    "trader_arrival": ("generous", 10),
    "theft": ("suspicious", 25),
    "strange_evidence": ("suspicious", 18),
    "mysterious_signal": ("suspicious", 18),
    "unexplained_disappearance": ("suspicious", 22),
    "protest": ("suspicious", 10),
    "argument": ("suspicious", 8),
    "alliance_fracture": ("trustworthy", -18),
}


def _stable_id(prefix: str, *parts: Any) -> str:
    material = ":".join(str(part or "") for part in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:12]}"


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp_int(value: Any, low: int, high: int, default: int = 0) -> int:
    return max(low, min(high, _coerce_int(value, default)))


def _bounded_str(value: Any, limit: int = 120) -> str:
    return str(value or "").strip()[:limit]


def _bounded_str_list(values: Any, limit: int = MAX_INFORMATION_REFS) -> List[str]:
    out: List[str] = []
    raw = values if isinstance(values, (list, tuple, set)) else [values]
    for value in raw or []:
        text = _bounded_str(value, 160)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _turn_stamp(value: Any, fallback_turn: int = 0) -> Dict[str, int]:
    if isinstance(value, Mapping):
        return {"turn": max(0, _coerce_int(value.get("turn"), fallback_turn))}
    return {"turn": max(0, _coerce_int(value, fallback_turn))}


def _stamp_turn(row: Mapping[str, Any], key: str, fallback_turn: int = 0) -> int:
    value = row.get(key)
    if isinstance(value, Mapping):
        return max(0, _coerce_int(value.get("turn"), fallback_turn))
    return max(0, _coerce_int(value, fallback_turn))


def _normalise_information_type(value: Any) -> str:
    info_type = _bounded_str(value, 80).lower()
    return info_type if info_type in INFORMATION_TYPES else "claim"


def _normalise_visibility(value: Any) -> str:
    visibility = _bounded_str(value, 80).lower()
    return visibility if visibility in VISIBILITY_SCOPES else "private"


def _reliability_band(value: Any) -> str:
    reliability = _clamp_int(value, 0, 100, default=0)
    if reliability >= 85:
        return "verified"
    if reliability >= 65:
        return "high"
    if reliability >= 40:
        return "medium"
    return "low"


def _score_band(value: Any) -> str:
    score = _clamp_int(value, -100, 100, default=0)
    if score >= 40:
        return "strong_positive"
    if score >= 15:
        return "positive"
    if score <= -40:
        return "strong_negative"
    if score <= -15:
        return "negative"
    return "neutral"


def _normalise_ref(row: Any, *, type_key: str = "subject_type", id_key: str = "subject_id") -> Optional[Dict[str, str]]:
    if isinstance(row, Mapping):
        ref_type = _bounded_str(row.get(type_key) or row.get("type") or row.get("scope_type"), 80)
        ref_id = _bounded_str(row.get(id_key) or row.get("id") or row.get("scope_id"), 160)
    else:
        ref_type = "entity"
        ref_id = _bounded_str(row, 160)
    if not ref_type or not ref_id:
        return None
    return {type_key: ref_type, id_key: ref_id}


def _normalise_refs(
    values: Any,
    *,
    type_key: str = "subject_type",
    id_key: str = "subject_id",
    limit: int = MAX_SUBJECT_REFS,
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    raw = values if isinstance(values, (list, tuple, set)) else [values]
    for value in raw or []:
        ref = _normalise_ref(value, type_key=type_key, id_key=id_key)
        if not ref:
            continue
        key = (ref[type_key], ref[id_key])
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)
        if len(out) >= limit:
            break
    return sorted(out, key=lambda row: (row[type_key], row[id_key]))


def _normalise_known_by(values: Any) -> List[Dict[str, str]]:
    return _normalise_refs(values, type_key="scope_type", id_key="scope_id", limit=MAX_KNOWN_BY)


def _normalise_access_type(value: Any) -> str:
    access_type = _bounded_str(value, 80).lower()
    return access_type if access_type in ACCESS_TYPES else "secondary_source"


def _default_access_type_for_scope(scope_type: Any) -> str:
    scope = _bounded_str(scope_type, 80).lower()
    if scope == "actor":
        return "direct_witness"
    if scope == "player":
        return "player_known"
    if scope == "faction":
        return "faction_channel"
    if scope == "settlement":
        return "local_community"
    if scope == "case":
        return "investigation_channel"
    if scope in {"unknown", "unobserved"}:
        return "unknown_unobserved"
    return "secondary_source"


def _access_sort_key(row: Mapping[str, Any]) -> Tuple[str, str, str]:
    return (
        str(row.get("scope_type") or ""),
        str(row.get("scope_id") or ""),
        str(row.get("access_type") or ""),
    )


def _normalise_access_row(
    row: Any,
    *,
    default_access_type: str = "secondary_source",
    default_source_event_ids: Sequence[str] = (),
    default_turn: int = 0,
    default_reliability: int = 50,
    default_distortion: int = 0,
) -> Optional[Dict[str, Any]]:
    if isinstance(row, Mapping):
        scope_type = _bounded_str(row.get("scope_type") or row.get("type"), 80)
        scope_id = _bounded_str(row.get("scope_id") or row.get("id"), 160)
        access_type = _normalise_access_type(row.get("access_type") or default_access_type)
        source_ids = _bounded_str_list(row.get("source_event_ids") or default_source_event_ids, MAX_INFORMATION_REFS)
        acquired_turn = _stamp_turn(
            row,
            "acquired_at",
            _coerce_int(row.get("acquired_turn"), default_turn),
        )
        reliability = _clamp_int(row.get("reliability"), 0, 100, default=default_reliability)
        distortion = _clamp_int(row.get("distortion_level"), 0, 100, default=default_distortion)
    else:
        ref = _normalise_ref(row, type_key="scope_type", id_key="scope_id")
        if not ref:
            return None
        scope_type = ref["scope_type"]
        scope_id = ref["scope_id"]
        access_type = _normalise_access_type(default_access_type)
        source_ids = _bounded_str_list(default_source_event_ids, MAX_INFORMATION_REFS)
        acquired_turn = max(0, default_turn)
        reliability = _clamp_int(default_reliability, 0, 100, default=50)
        distortion = _clamp_int(default_distortion, 0, 100, default=0)
    if not scope_type or not scope_id:
        return None
    return {
        "access_type": access_type,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "source_event_ids": source_ids,
        "reliability": reliability,
        "distortion_level": distortion,
        "acquired_at": {"turn": max(0, acquired_turn)},
    }


def _normalise_observer_access(
    values: Any,
    *,
    default_source_event_ids: Sequence[str] = (),
    default_turn: int = 0,
    default_reliability: int = 50,
    default_distortion: int = 0,
    limit: int = MAX_OBSERVER_ACCESS,
) -> List[Dict[str, Any]]:
    raw = values if isinstance(values, (list, tuple, set)) else [values]
    out: List[Dict[str, Any]] = []
    seen = set()
    for value in raw or []:
        default_type = "secondary_source"
        if isinstance(value, Mapping):
            default_type = _default_access_type_for_scope(value.get("scope_type") or value.get("type"))
        access = _normalise_access_row(
            value,
            default_access_type=default_type,
            default_source_event_ids=default_source_event_ids,
            default_turn=default_turn,
            default_reliability=default_reliability,
            default_distortion=default_distortion,
        )
        if not access:
            continue
        key = _access_sort_key(access)
        if key in seen:
            continue
        seen.add(key)
        out.append(access)
        if len(out) >= limit:
            break
    return sorted(out, key=_access_sort_key)


def _access_from_scope(
    scope_type: str,
    scope_id: str,
    access_type: str,
    *,
    source_event_ids: Sequence[str],
    turn_number: int,
    reliability: int,
    distortion_level: int,
) -> Optional[Dict[str, Any]]:
    return _normalise_access_row(
        {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "access_type": access_type,
            "source_event_ids": list(source_event_ids),
            "reliability": reliability,
            "distortion_level": distortion_level,
            "acquired_at": {"turn": turn_number},
        },
        default_source_event_ids=source_event_ids,
        default_turn=turn_number,
        default_reliability=reliability,
        default_distortion=distortion_level,
    )


def _known_by_from_access(access_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, str]]:
    return _normalise_known_by(
        [
            {"scope_type": row.get("scope_type"), "scope_id": row.get("scope_id")}
            for row in access_rows
            if isinstance(row, Mapping)
        ]
    )


def _access_from_known_by(
    known_by: Sequence[Mapping[str, Any]],
    *,
    source_event_ids: Sequence[str],
    turn_number: int,
    reliability: int,
    distortion_level: int,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in known_by:
        if not isinstance(row, Mapping):
            continue
        access = _access_from_scope(
            _bounded_str(row.get("scope_type"), 80),
            _bounded_str(row.get("scope_id"), 160),
            _default_access_type_for_scope(row.get("scope_type")),
            source_event_ids=source_event_ids,
            turn_number=turn_number,
            reliability=reliability,
            distortion_level=distortion_level,
        )
        if access:
            out.append(access)
    return _normalise_observer_access(out, default_source_event_ids=source_event_ids, default_turn=turn_number)


def _truth_status(info_type: str) -> str:
    if info_type == "truth":
        return "truth"
    if info_type == "evidence_summary":
        return "evidence"
    return "belief"


def _normalise_information_item(row: Mapping[str, Any], *, run_seed: str = "") -> Dict[str, Any]:
    info_type = _normalise_information_type(row.get("information_type"))
    source_event_ids = _bounded_str_list(row.get("source_event_ids"), MAX_INFORMATION_REFS)
    subject_refs = _normalise_refs(row.get("subject_refs") or row.get("subjects"))
    known_by = _normalise_known_by(row.get("known_by"))
    created_turn = _stamp_turn(row, "created_at", _coerce_int(row.get("created_turn"), 0))
    updated_turn = _stamp_turn(row, "updated_at", _coerce_int(row.get("updated_turn"), created_turn))
    source_key = ",".join(source_event_ids) or _bounded_str(row.get("summary"), 160) or info_type
    subject_key = ",".join(f"{ref['subject_type']}:{ref['subject_id']}" for ref in subject_refs)
    reliability = _clamp_int(row.get("reliability"), 0, 100, default=50)
    distortion = _clamp_int(row.get("distortion_level"), 0, 100, default=0)
    observer_access = _normalise_observer_access(
        row.get("observer_access"),
        default_source_event_ids=source_event_ids,
        default_turn=created_turn,
        default_reliability=reliability,
        default_distortion=distortion,
    )
    if not observer_access and known_by:
        observer_access = _access_from_known_by(
            known_by,
            source_event_ids=source_event_ids,
            turn_number=created_turn,
            reliability=reliability,
            distortion_level=distortion,
        )
    if observer_access and not known_by:
        known_by = _known_by_from_access(observer_access)
    if not known_by:
        known_by = [{"scope_type": "unknown", "scope_id": "unobserved"}]
    if not observer_access:
        unknown_access = _access_from_scope(
            "unknown",
            "unobserved",
            "unknown_unobserved",
            source_event_ids=source_event_ids,
            turn_number=created_turn,
            reliability=reliability,
            distortion_level=distortion,
        )
        observer_access = [unknown_access] if unknown_access else []
    return {
        "version": INFORMATION_ENGINE_VERSION,
        "information_id": _bounded_str(
            row.get("information_id") or _stable_id("information", run_seed or "information", info_type, source_key, subject_key),
            160,
        ),
        "information_type": info_type,
        "truth_status": _truth_status(info_type),
        "summary": _bounded_str(row.get("summary") or info_type.replace("_", " "), 160),
        "subject_refs": subject_refs,
        "known_by": known_by,
        "observer_access": observer_access[:MAX_OBSERVER_ACCESS],
        "source_event_ids": source_event_ids,
        "reliability": reliability,
        "reliability_band": _reliability_band(reliability),
        "distortion_level": distortion,
        "visibility_scope": _normalise_visibility(row.get("visibility_scope")),
        "created_at": _turn_stamp(row.get("created_at"), created_turn),
        "updated_at": _turn_stamp(row.get("updated_at"), max(created_turn, updated_turn)),
        "gravity": _clamp_int(row.get("gravity"), 0, 10, default=1),
        "stale": bool(row.get("stale")),
        "decay_ready": bool(row.get("decay_ready")),
        "last_decay_turn": max(0, _coerce_int(row.get("last_decay_turn"), 0)),
    }


def _normalise_dimension(value: Any) -> str:
    dimension = _bounded_str(value, 80).lower()
    return dimension if dimension in REPUTATION_DIMENSIONS else "suspicious"


def _normalise_reputation_signal(row: Mapping[str, Any], *, run_seed: str = "") -> Dict[str, Any]:
    subject_type = _bounded_str(row.get("subject_type"), 80) or "entity"
    subject_id = _bounded_str(row.get("subject_id"), 160)
    scope = _normalise_ref(row.get("observer_scope") or {}, type_key="scope_type", id_key="scope_id")
    if not scope:
        scope = {"scope_type": "public", "scope_id": "public"}
    dimension = _normalise_dimension(row.get("dimension"))
    source_event_ids = _bounded_str_list(row.get("source_event_ids"), MAX_INFORMATION_REFS)
    created_turn = _stamp_turn(row, "created_at", _coerce_int(row.get("created_turn"), 0))
    updated_turn = _stamp_turn(row, "updated_at", _coerce_int(row.get("updated_turn"), created_turn))
    score = _clamp_int(row.get("score"), -100, 100, default=_coerce_int(row.get("value_delta"), 0))
    confidence = _clamp_int(row.get("confidence"), 0, 100, default=_coerce_int(row.get("reliability"), 50))
    return {
        "version": INFORMATION_ENGINE_VERSION,
        "signal_id": _bounded_str(
            row.get("signal_id")
            or _stable_id(
                "reputation",
                run_seed or "information",
                subject_type,
                subject_id,
                scope["scope_type"],
                scope["scope_id"],
                dimension,
            ),
            160,
        ),
        "subject_type": subject_type,
        "subject_id": subject_id,
        "observer_scope": scope,
        "dimension": dimension,
        "score": score,
        "value_delta": _clamp_int(row.get("value_delta"), -100, 100, default=score),
        "score_band": _score_band(score),
        "source_event_ids": source_event_ids,
        "confidence": confidence,
        "reliability": _clamp_int(row.get("reliability"), 0, 100, default=confidence),
        "reliability_band": _reliability_band(row.get("reliability") if row.get("reliability") is not None else confidence),
        "created_at": _turn_stamp(row.get("created_at"), created_turn),
        "updated_at": _turn_stamp(row.get("updated_at"), max(created_turn, updated_turn)),
        "decay_ready": bool(row.get("decay_ready")),
        "last_decay_turn": max(0, _coerce_int(row.get("last_decay_turn"), 0)),
    }


def _information_sort_key(row: Mapping[str, Any]) -> Tuple[int, int, int, int, str]:
    return (
        1 if row.get("stale") else 0,
        -_clamp_int(row.get("gravity"), 0, 10),
        -_clamp_int(row.get("reliability"), 0, 100),
        -_stamp_turn(row, "updated_at", 0),
        str(row.get("information_id") or ""),
    )


def _reputation_sort_key(row: Mapping[str, Any]) -> Tuple[int, int, str]:
    return (
        -abs(_clamp_int(row.get("score"), -100, 100)),
        -_clamp_int(row.get("confidence"), 0, 100),
        str(row.get("signal_id") or ""),
    )


def _cap_information_items(items: Sequence[Mapping[str, Any]], *, run_seed: str = "") -> List[Dict[str, Any]]:
    rows = [_normalise_information_item(row, run_seed=run_seed) for row in items if isinstance(row, Mapping)]
    if len(rows) > MAX_INFORMATION_ITEMS:
        rows = sorted(rows, key=_information_sort_key)[:MAX_INFORMATION_ITEMS]
    return sorted(rows, key=_information_sort_key)


def _cap_reputation_signals(signals: Sequence[Mapping[str, Any]], *, run_seed: str = "") -> List[Dict[str, Any]]:
    rows = [_normalise_reputation_signal(row, run_seed=run_seed) for row in signals if isinstance(row, Mapping)]
    if len(rows) > MAX_REPUTATION_SIGNALS:
        rows = sorted(rows, key=_reputation_sort_key)[:MAX_REPUTATION_SIGNALS]
    return sorted(rows, key=_reputation_sort_key)


def _merge_unique_refs(
    existing: Dict[str, Any],
    incoming: Mapping[str, Any],
    key: str,
    *,
    type_key: str,
    id_key: str,
    limit: int,
) -> bool:
    before = _normalise_refs(existing.get(key), type_key=type_key, id_key=id_key, limit=limit)
    merged = _normalise_refs(before + list(incoming.get(key) or []), type_key=type_key, id_key=id_key, limit=limit)
    existing[key] = merged
    return merged != before


def _merge_unique_strings(existing: Dict[str, Any], incoming: Mapping[str, Any], key: str, limit: int) -> bool:
    before = _bounded_str_list(existing.get(key), limit)
    merged = _bounded_str_list(before + list(incoming.get(key) or []), limit)
    existing[key] = merged
    return merged != before


def _visibility_rank(scope: str) -> int:
    return {"private": 0, "witnessed": 1, "case": 2, "faction": 3, "settlement": 4, "public": 5}.get(scope, 0)


def _merge_information_item(existing: Dict[str, Any], candidate: Mapping[str, Any], turn_number: int) -> bool:
    changed = False
    changed = _merge_unique_strings(existing, candidate, "source_event_ids", MAX_INFORMATION_REFS) or changed
    changed = _merge_unique_refs(
        existing,
        candidate,
        "subject_refs",
        type_key="subject_type",
        id_key="subject_id",
        limit=MAX_SUBJECT_REFS,
    ) or changed
    changed = _merge_unique_refs(
        existing,
        candidate,
        "known_by",
        type_key="scope_type",
        id_key="scope_id",
        limit=MAX_KNOWN_BY,
    ) or changed
    before_access = _normalise_observer_access(
        existing.get("observer_access"),
        default_source_event_ids=existing.get("source_event_ids") or [],
        default_turn=_stamp_turn(existing, "created_at", 0),
        default_reliability=_clamp_int(existing.get("reliability"), 0, 100, default=50),
        default_distortion=_clamp_int(existing.get("distortion_level"), 0, 100, default=0),
    )
    merged_access = _normalise_observer_access(
        before_access + list(candidate.get("observer_access") or []),
        default_source_event_ids=existing.get("source_event_ids") or [],
        default_turn=_stamp_turn(existing, "created_at", 0),
        default_reliability=_clamp_int(existing.get("reliability"), 0, 100, default=50),
        default_distortion=_clamp_int(existing.get("distortion_level"), 0, 100, default=0),
    )
    if merged_access != before_access:
        existing["observer_access"] = merged_access
        existing["known_by"] = _known_by_from_access(merged_access)
        changed = True
    for key in ("reliability", "gravity"):
        value = _clamp_int(candidate.get(key), 0, 100 if key == "reliability" else 10)
        if value > _clamp_int(existing.get(key), 0, 100 if key == "reliability" else 10):
            existing[key] = value
            changed = True
    distortion = _clamp_int(candidate.get("distortion_level"), 0, 100)
    if distortion > _clamp_int(existing.get("distortion_level"), 0, 100):
        existing["distortion_level"] = distortion
        changed = True
    visibility = _normalise_visibility(candidate.get("visibility_scope"))
    if _visibility_rank(visibility) > _visibility_rank(str(existing.get("visibility_scope") or "")):
        existing["visibility_scope"] = visibility
        changed = True
    if changed:
        existing["updated_at"] = {"turn": max(0, turn_number)}
        existing["reliability_band"] = _reliability_band(existing.get("reliability"))
    return changed


def _merge_reputation_signal(existing: Dict[str, Any], candidate: Mapping[str, Any], turn_number: int) -> bool:
    new_sources = [
        source_id
        for source_id in _bounded_str_list(candidate.get("source_event_ids"), MAX_INFORMATION_REFS)
        if source_id not in (existing.get("source_event_ids") or [])
    ]
    if not new_sources:
        return False
    changed = _merge_unique_strings(existing, {"source_event_ids": new_sources}, "source_event_ids", MAX_INFORMATION_REFS)
    existing["score"] = _clamp_int(
        _coerce_int(existing.get("score"), 0) + _coerce_int(candidate.get("value_delta"), 0),
        -100,
        100,
    )
    existing["value_delta"] = _clamp_int(candidate.get("value_delta"), -100, 100)
    existing["confidence"] = max(
        _clamp_int(existing.get("confidence"), 0, 100),
        _clamp_int(candidate.get("confidence"), 0, 100),
    )
    existing["reliability"] = max(
        _clamp_int(existing.get("reliability"), 0, 100),
        _clamp_int(candidate.get("reliability"), 0, 100),
    )
    existing["score_band"] = _score_band(existing.get("score"))
    existing["reliability_band"] = _reliability_band(existing.get("reliability"))
    existing["updated_at"] = {"turn": max(0, turn_number)}
    return changed or bool(new_sources)


def _receipt_id(
    receipt_type: str,
    *,
    turn_number: int,
    target_id: str,
    source_event_ids: Sequence[str],
    receipt_context: str = "",
) -> str:
    return _stable_id(
        "information-receipt",
        receipt_type,
        turn_number,
        target_id,
        ",".join(sorted(source_event_ids)),
        receipt_context,
    )


def _append_receipt(
    replayability_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    receipt_type: str,
    turn_number: int,
    target_key: str,
    target_id: str,
    source_event_ids: Sequence[str],
    receipt_context: str = "",
    details: Optional[Mapping[str, Any]] = None,
) -> bool:
    if receipt_type not in INFORMATION_RECEIPT_TYPES:
        return False
    if not target_id:
        return False
    source_ids = _bounded_str_list(source_event_ids, MAX_INFORMATION_REFS)
    rid = _receipt_id(
        receipt_type,
        turn_number=turn_number,
        target_id=target_id,
        source_event_ids=source_ids,
        receipt_context=receipt_context,
    )
    receipts = replayability_state.setdefault("information_receipts", [])
    if any(isinstance(row, Mapping) and row.get("receipt_id") == rid for row in receipts):
        return False
    receipt: Dict[str, Any] = {
        "version": INFORMATION_ENGINE_VERSION,
        "receipt_id": rid,
        "receipt_type": receipt_type,
        "turn": turn_number,
        target_key: target_id,
    }
    if source_ids:
        receipt["source_event_ids"] = source_ids
    if isinstance(details, Mapping):
        for key in ("access_type", "scope_type", "scope_id"):
            if details.get(key):
                receipt[key] = _bounded_str(details.get(key), 160)
    receipts.append(receipt)
    if len(receipts) > MAX_INFORMATION_RECEIPTS:
        replayability_state["information_receipts"] = receipts[-MAX_INFORMATION_RECEIPTS:]
    local_receipts.append(receipt)
    return True


def _subject_refs_from_event(event: Mapping[str, Any]) -> List[Dict[str, str]]:
    refs: List[Dict[str, str]] = []
    for actor_id in _bounded_str_list(event.get("actor_ids"), MAX_INFORMATION_REFS):
        refs.append({"subject_type": "npc", "subject_id": actor_id})
    for faction_id in _bounded_str_list(event.get("faction_ids"), MAX_INFORMATION_REFS):
        refs.append({"subject_type": "faction", "subject_id": faction_id})
    for location_id in _bounded_str_list(event.get("location_ids"), MAX_INFORMATION_REFS):
        refs.append({"subject_type": "location", "subject_id": location_id})
    event_id = _event_id(event)
    if event_id:
        refs.append({"subject_type": "event", "subject_id": event_id})
    return _normalise_refs(refs)


def _actor_ids_from_values(values: Any) -> List[str]:
    raw = values if isinstance(values, (list, tuple, set)) else [values]
    out: List[str] = []
    for value in raw or []:
        if isinstance(value, Mapping):
            actor_id = _bounded_str(
                value.get("actor_id") or value.get("npc_id") or value.get("id") or value.get("name"),
                160,
            )
        else:
            actor_id = _bounded_str(value, 160)
        if actor_id and actor_id not in out:
            out.append(actor_id)
        if len(out) >= MAX_INFORMATION_REFS:
            break
    return out


def _witness_ids_from_event(event: Mapping[str, Any]) -> List[str]:
    witnesses: List[str] = []
    for key in ("witness_ids", "witnesses", "observer_ids", "source_actor_ids", "source_actor_id"):
        for actor_id in _actor_ids_from_values(event.get(key)):
            if actor_id not in witnesses:
                witnesses.append(actor_id)
            if len(witnesses) >= MAX_INFORMATION_REFS:
                return witnesses
    return witnesses


def _observer_access_from_event(
    event: Mapping[str, Any],
    *,
    turn_number: int,
    source_event_ids: Sequence[str],
    reliability: int,
    distortion_level: int,
) -> List[Dict[str, Any]]:
    access_rows: List[Dict[str, Any]] = []
    participant_ids = _actor_ids_from_values(event.get("actor_ids") or event.get("participant_ids"))
    witness_ids = [actor_id for actor_id in _witness_ids_from_event(event) if actor_id not in participant_ids]
    for actor_id in participant_ids:
        access = _access_from_scope(
            "actor",
            actor_id,
            "participant",
            source_event_ids=source_event_ids,
            turn_number=turn_number,
            reliability=max(45, reliability),
            distortion_level=distortion_level,
        )
        if access:
            access_rows.append(access)
    for actor_id in witness_ids:
        access = _access_from_scope(
            "actor",
            actor_id,
            "direct_witness",
            source_event_ids=source_event_ids,
            turn_number=turn_number,
            reliability=reliability,
            distortion_level=distortion_level,
        )
        if access:
            access_rows.append(access)
    if event.get("player_known") or event.get("player_visible") or event.get("visible_to_player"):
        access = _access_from_scope(
            "player",
            "player",
            "player_known",
            source_event_ids=source_event_ids,
            turn_number=turn_number,
            reliability=reliability,
            distortion_level=distortion_level,
        )
        if access:
            access_rows.append(access)
    for faction_id in _bounded_str_list(event.get("faction_ids"), MAX_INFORMATION_REFS):
        access = _access_from_scope(
            "faction",
            faction_id,
            "faction_channel",
            source_event_ids=source_event_ids,
            turn_number=turn_number,
            reliability=max(30, reliability - 6),
            distortion_level=min(100, distortion_level + 4),
        )
        if access:
            access_rows.append(access)
    if not access_rows:
        for location_id in _bounded_str_list(event.get("location_ids"), MAX_INFORMATION_REFS):
            access = _access_from_scope(
                "settlement",
                location_id,
                "local_community",
                source_event_ids=source_event_ids,
                turn_number=turn_number,
                reliability=max(25, reliability - 8),
                distortion_level=min(100, distortion_level + 6),
            )
            if access:
                access_rows.append(access)
    if not access_rows:
        access = _access_from_scope(
            "unknown",
            "unobserved",
            "unknown_unobserved",
            source_event_ids=source_event_ids,
            turn_number=turn_number,
            reliability=reliability,
            distortion_level=distortion_level,
        )
        if access:
            access_rows.append(access)
    return _normalise_observer_access(
        access_rows,
        default_source_event_ids=source_event_ids,
        default_turn=turn_number,
        default_reliability=reliability,
        default_distortion=distortion_level,
    )


def _known_by_from_event(event: Mapping[str, Any]) -> List[Dict[str, str]]:
    event_id = _event_id(event)
    access = _observer_access_from_event(
        event,
        turn_number=_coerce_int(event.get("turn"), 0),
        source_event_ids=[event_id] if event_id else [],
        reliability=55,
        distortion_level=10,
    )
    return _known_by_from_access(access)


def _visibility_from_event(event: Mapping[str, Any]) -> str:
    if event.get("actor_ids"):
        return "witnessed"
    if event.get("faction_ids"):
        return "faction"
    if event.get("location_ids"):
        return "settlement"
    return "unknown"


def _event_id(event: Mapping[str, Any]) -> str:
    return _bounded_str(
        event.get("event_id")
        or event.get("world_event_id")
        or event.get("action_id")
        or event.get("source_event_id"),
        160,
    )


def _event_kind(event: Mapping[str, Any]) -> str:
    return _bounded_str(
        event.get("pressure_event_kind")
        or event.get("event_kind")
        or event.get("world_event_type")
        or event.get("event_type"),
        80,
    ).lower()


def _information_from_engine_event(
    event: Mapping[str, Any],
    *,
    turn_number: int,
    run_seed: str,
) -> Optional[Dict[str, Any]]:
    event_id = _event_id(event)
    if not event_id:
        return None
    event_type = _bounded_str(event.get("event_type"), 80)
    if event_type not in {"pressure_world_event", "npc_action_event", "world_event"}:
        return None
    kind = _event_kind(event)
    magnitude = _clamp_int(event.get("magnitude"), 0, 100, default=45)
    reliability = min(82, max(35, 42 + magnitude // 3))
    distortion = 18 if event_type == "pressure_world_event" else 12
    observer_access = _observer_access_from_event(
        event,
        turn_number=turn_number,
        source_event_ids=[event_id],
        reliability=reliability,
        distortion_level=distortion,
    )
    return _normalise_information_item(
        {
            "information_id": _stable_id("information", run_seed, "event", event_id),
            "information_type": "rumour",
            "summary": f"{(kind or event_type).replace('_', ' ')} reported",
            "subject_refs": _subject_refs_from_event(event),
            "known_by": _known_by_from_access(observer_access),
            "observer_access": observer_access,
            "source_event_ids": [event_id],
            "reliability": reliability,
            "distortion_level": distortion,
            "visibility_scope": _visibility_from_event(event),
            "created_at": {"turn": turn_number},
            "updated_at": {"turn": turn_number},
            "gravity": min(10, max(1, magnitude // 12)),
        },
        run_seed=run_seed,
    )


def _information_from_world_event(row: Mapping[str, Any], *, turn_number: int, run_seed: str) -> Optional[Dict[str, Any]]:
    if str(row.get("status") or "") in {"resolved", "failed", "archived"}:
        return None
    severity = _clamp_int(row.get("severity"), 0, 10, default=0)
    if severity < HIGH_GRAVITY_WORLD_EVENT_SEVERITY:
        return None
    world_event_id = _bounded_str(row.get("world_event_id"), 160)
    if not world_event_id:
        return None
    subject_refs = []
    for actor_id in _bounded_str_list(row.get("affected_actor_ids"), MAX_INFORMATION_REFS):
        subject_refs.append({"subject_type": "npc", "subject_id": actor_id})
    for faction_id in _bounded_str_list(row.get("affected_factions"), MAX_INFORMATION_REFS):
        subject_refs.append({"subject_type": "faction", "subject_id": faction_id})
    for location_id in _bounded_str_list(row.get("affected_locations"), MAX_INFORMATION_REFS):
        subject_refs.append({"subject_type": "location", "subject_id": location_id})
    subject_refs.append({"subject_type": "event", "subject_id": world_event_id})
    known_by = []
    for faction_id in _bounded_str_list(row.get("affected_factions"), MAX_INFORMATION_REFS):
        known_by.append({"scope_type": "faction", "scope_id": faction_id})
    for location_id in _bounded_str_list(row.get("affected_locations"), MAX_INFORMATION_REFS):
        known_by.append({"scope_type": "settlement", "scope_id": location_id})
    reliability = min(90, 45 + severity * 5)
    distortion = max(5, 25 - severity)
    observer_access = _access_from_known_by(
        _normalise_known_by(known_by),
        source_event_ids=[world_event_id] + list(row.get("source_event_ids") or []),
        turn_number=turn_number,
        reliability=reliability,
        distortion_level=distortion,
    )
    return _normalise_information_item(
        {
            "information_id": _stable_id("information", run_seed, "world", world_event_id),
            "information_type": "claim",
            "summary": _bounded_str(row.get("title") or row.get("event_type") or "world event", 160),
            "subject_refs": subject_refs,
            "known_by": _known_by_from_access(observer_access),
            "observer_access": observer_access,
            "source_event_ids": [world_event_id] + list(row.get("source_event_ids") or []),
            "reliability": reliability,
            "distortion_level": distortion,
            "visibility_scope": "settlement" if row.get("affected_locations") else "faction" if row.get("affected_factions") else "unknown",
            "created_at": {"turn": turn_number},
            "updated_at": {"turn": turn_number},
            "gravity": severity,
        },
        run_seed=run_seed,
    )


def _information_from_evidence(row: Mapping[str, Any], *, turn_number: int, run_seed: str) -> Optional[Dict[str, Any]]:
    evidence_id = _bounded_str(row.get("evidence_id"), 160)
    if not evidence_id or row.get("archived"):
        return None
    reliability = _clamp_int(row.get("reliability"), 0, 100, default=_coerce_int(row.get("confidence"), 50))
    subject_refs = [{"subject_type": "evidence", "subject_id": evidence_id}]
    for case_id in _bounded_str_list(row.get("related_case_ids"), MAX_INFORMATION_REFS):
        subject_refs.append({"subject_type": "case", "subject_id": case_id})
    for actor_id in _bounded_str_list(row.get("actor_ids"), MAX_INFORMATION_REFS):
        subject_refs.append({"subject_type": "npc", "subject_id": actor_id})
    if row.get("location_id"):
        subject_refs.append({"subject_type": "location", "subject_id": _bounded_str(row.get("location_id"), 160)})
    known_by = [
        {"scope_type": "actor", "scope_id": actor_id}
        for actor_id in _bounded_str_list(row.get("discovered_by"), MAX_INFORMATION_REFS)
    ]
    observer_access = _access_from_known_by(
        known_by or [{"scope_type": "case", "scope_id": evidence_id}],
        source_event_ids=[evidence_id] + list(row.get("source_event_ids") or []),
        turn_number=_coerce_int(row.get("discovered_turn"), turn_number),
        reliability=reliability,
        distortion_level=max(0, 25 - reliability // 4),
    )
    return _normalise_information_item(
        {
            "information_id": _stable_id("information", run_seed, "evidence", evidence_id),
            "information_type": "evidence_summary",
            "summary": f"{_bounded_str(row.get('evidence_type'), 80) or 'evidence'} noted",
            "subject_refs": subject_refs,
            "known_by": _known_by_from_access(observer_access),
            "observer_access": observer_access,
            "source_event_ids": [evidence_id] + list(row.get("source_event_ids") or []),
            "reliability": reliability,
            "distortion_level": max(0, 25 - reliability // 4),
            "visibility_scope": "private" if known_by else "case",
            "created_at": {"turn": _coerce_int(row.get("discovered_turn"), turn_number)},
            "updated_at": {"turn": turn_number},
            "gravity": min(10, max(1, _clamp_int(row.get("confidence"), 0, 100, default=reliability) // 12)),
        },
        run_seed=run_seed,
    )


def _information_from_investigation(row: Mapping[str, Any], *, turn_number: int, run_seed: str) -> Optional[Dict[str, Any]]:
    investigation_id = _bounded_str(row.get("investigation_id"), 160)
    if not investigation_id or row.get("archived"):
        return None
    status = _bounded_str(row.get("status"), 80)
    if status in {"failed", "archived"}:
        return None
    confidence = _clamp_int(row.get("confidence"), 0, 100, default=0)
    subject_refs = [{"subject_type": "case", "subject_id": investigation_id}]
    for actor_id in _bounded_str_list(row.get("suspect_ids"), MAX_INFORMATION_REFS):
        subject_refs.append({"subject_type": "npc", "subject_id": actor_id})
    known_by = [
        {"scope_type": "actor", "scope_id": actor_id}
        for actor_id in _bounded_str_list(row.get("assigned_actor_ids"), MAX_INFORMATION_REFS)
    ]
    observer_access = _access_from_known_by(
        known_by or [{"scope_type": "case", "scope_id": investigation_id}],
        source_event_ids=[investigation_id],
        turn_number=_coerce_int(row.get("created_turn"), turn_number),
        reliability=max(35, confidence),
        distortion_level=20 if confidence < 70 else 8,
    )
    return _normalise_information_item(
        {
            "information_id": _stable_id("information", run_seed, "case", investigation_id),
            "information_type": "claim",
            "summary": f"case {status or 'active'}",
            "subject_refs": subject_refs,
            "known_by": _known_by_from_access(observer_access),
            "observer_access": observer_access,
            "source_event_ids": [investigation_id],
            "reliability": max(35, confidence),
            "distortion_level": 20 if confidence < 70 else 8,
            "visibility_scope": "case",
            "created_at": {"turn": _coerce_int(row.get("created_turn"), turn_number)},
            "updated_at": {"turn": turn_number},
            "gravity": min(10, max(1, _clamp_int(row.get("priority"), 0, 10, default=5))),
        },
        run_seed=run_seed,
    )


def _information_from_structured_source(source: Mapping[str, Any], *, turn_number: int, run_seed: str) -> Optional[Dict[str, Any]]:
    source_id = _bounded_str(source.get("source_event_id"), 160)
    if not source_id:
        return None
    source_kind = _bounded_str(source.get("source_kind"), 100)
    label = _bounded_str(source.get("label") or source_kind or "structured source", 160)
    scope_ref = _normalise_ref(source.get("observer_scope") or {}, type_key="scope_type", id_key="scope_id")
    if not scope_ref and (source.get("public") or source.get("visibility_scope") == "public"):
        scope_ref = {"scope_type": "public", "scope_id": "public"}
    if not scope_ref:
        scope_ref = {"scope_type": "unknown", "scope_id": "unobserved"}
    access_type = _default_access_type_for_scope(scope_ref.get("scope_type"))
    if scope_ref.get("scope_type") == "public":
        access_type = "secondary_source"
    observer_access = _normalise_observer_access(
        [
            {
                "scope_type": scope_ref.get("scope_type"),
                "scope_id": scope_ref.get("scope_id"),
                "access_type": access_type,
                "source_event_ids": [source_id],
                "reliability": 55,
                "distortion_level": 24,
                "acquired_at": {"turn": turn_number},
            }
        ],
        default_source_event_ids=[source_id],
        default_turn=turn_number,
        default_reliability=55,
        default_distortion=24,
    )
    return _normalise_information_item(
        {
            "information_id": _stable_id("information", run_seed, "source", source_id),
            "information_type": "rumour" if source_kind else "claim",
            "summary": label,
            "subject_refs": [{"subject_type": "event", "subject_id": source_id}],
            "known_by": _known_by_from_access(observer_access),
            "observer_access": observer_access,
            "source_event_ids": [source_id],
            "reliability": 55,
            "distortion_level": 24,
            "visibility_scope": _normalise_visibility(source.get("visibility_scope") or scope_ref.get("scope_type")),
            "created_at": {"turn": turn_number},
            "updated_at": {"turn": turn_number},
            "gravity": 6 if "relationship" in source_kind or "faction" in source_kind else 4,
        },
        run_seed=run_seed,
    )


def _observer_scope_from_event(event: Mapping[str, Any]) -> Dict[str, str]:
    factions = _bounded_str_list(event.get("faction_ids"), MAX_INFORMATION_REFS)
    if factions:
        return {"scope_type": "faction", "scope_id": factions[0]}
    locations = _bounded_str_list(event.get("location_ids"), MAX_INFORMATION_REFS)
    if locations:
        return {"scope_type": "settlement", "scope_id": locations[0]}
    actors = _bounded_str_list(event.get("actor_ids"), MAX_INFORMATION_REFS)
    if actors:
        return {"scope_type": "actor", "scope_id": actors[0]}
    return {"scope_type": "public", "scope_id": "public"}


def _reputation_from_event(event: Mapping[str, Any], *, turn_number: int, run_seed: str) -> List[Dict[str, Any]]:
    source_id = _event_id(event)
    if not source_id:
        return []
    dimension_delta = EVENT_REPUTATION_MAP.get(_event_kind(event))
    if not dimension_delta:
        return []
    dimension, delta = dimension_delta
    subjects: List[Tuple[str, str]] = []
    for actor_id in _bounded_str_list(event.get("actor_ids"), MAX_INFORMATION_REFS):
        subjects.append(("npc", actor_id))
    for faction_id in _bounded_str_list(event.get("faction_ids"), MAX_INFORMATION_REFS):
        subjects.append(("faction", faction_id))
    if not subjects:
        for location_id in _bounded_str_list(event.get("location_ids"), MAX_INFORMATION_REFS):
            subjects.append(("settlement", location_id))
    magnitude = _clamp_int(event.get("magnitude"), 0, 100, default=50)
    out = []
    for subject_type, subject_id in subjects[:MAX_INFORMATION_REFS]:
        out.append(
            _normalise_reputation_signal(
                {
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "observer_scope": _observer_scope_from_event(event),
                    "dimension": dimension,
                    "score": delta,
                    "value_delta": delta,
                    "source_event_ids": [source_id],
                    "confidence": min(90, max(35, magnitude)),
                    "reliability": min(90, max(35, magnitude)),
                    "created_at": {"turn": turn_number},
                    "updated_at": {"turn": turn_number},
                },
                run_seed=run_seed,
            )
        )
    return out


def _reputation_from_evidence(row: Mapping[str, Any], *, turn_number: int, run_seed: str) -> List[Dict[str, Any]]:
    evidence_id = _bounded_str(row.get("evidence_id"), 160)
    if not evidence_id or row.get("archived"):
        return []
    actors = _bounded_str_list(row.get("actor_ids"), MAX_INFORMATION_REFS)
    if not actors:
        return []
    confidence = _clamp_int(row.get("confidence"), 0, 100, default=_coerce_int(row.get("reliability"), 50))
    location = _bounded_str(row.get("location_id"), 160)
    scope = {"scope_type": "settlement", "scope_id": location} if location else {"scope_type": "case", "scope_id": evidence_id}
    return [
        _normalise_reputation_signal(
            {
                "subject_type": "npc",
                "subject_id": actor_id,
                "observer_scope": scope,
                "dimension": "suspicious",
                "score": min(30, max(8, confidence // 4)),
                "value_delta": min(30, max(8, confidence // 4)),
                "source_event_ids": [evidence_id] + list(row.get("source_event_ids") or []),
                "confidence": confidence,
                "reliability": _clamp_int(row.get("reliability"), 0, 100, default=confidence),
                "created_at": {"turn": turn_number},
                "updated_at": {"turn": turn_number},
            },
            run_seed=run_seed,
        )
        for actor_id in actors
    ]


def _reputation_from_relationship_receipt(row: Mapping[str, Any], *, turn_number: int, run_seed: str) -> Optional[Dict[str, Any]]:
    receipt_id = _bounded_str(row.get("receipt_id"), 160)
    npc_name = _bounded_str(row.get("npc_name"), 160)
    after_state = _bounded_str(row.get("after_state"), 80)
    if not receipt_id or not npc_name or after_state not in {"collapsed", "betrayal_risk"}:
        return None
    delta = -35 if after_state == "collapsed" else -22
    return _normalise_reputation_signal(
        {
            "subject_type": "player",
            "subject_id": "player",
            "observer_scope": {"scope_type": "actor", "scope_id": npc_name},
            "dimension": "trustworthy",
            "score": delta,
            "value_delta": delta,
            "source_event_ids": [receipt_id],
            "confidence": 75,
            "reliability": 75,
            "created_at": {"turn": turn_number},
            "updated_at": {"turn": turn_number},
        },
        run_seed=run_seed,
    )


def _pressure_scope_from_visibility(scope: str) -> str:
    normalised = _normalise_visibility(scope)
    if normalised == "faction":
        return "faction"
    if normalised == "actor":
        return "personal"
    return "local"


def _pressure_targets_from_subjects(
    subject_refs: Sequence[Mapping[str, Any]],
) -> Dict[str, List[str]]:
    actor_ids: List[str] = []
    faction_ids: List[str] = []
    location_ids: List[str] = []
    for ref in subject_refs or []:
        if not isinstance(ref, Mapping):
            continue
        subject_type = _bounded_str(ref.get("subject_type"), 80).lower()
        subject_id = _bounded_str(ref.get("subject_id"), 160)
        if not subject_id:
            continue
        if subject_type in {"actor", "npc", "player"} and subject_id not in actor_ids:
            actor_ids.append(subject_id)
        elif subject_type == "faction" and subject_id not in faction_ids:
            faction_ids.append(subject_id)
        elif subject_type in {"location", "settlement"} and subject_id not in location_ids:
            location_ids.append(subject_id)
    return {
        "actor_ids": actor_ids[:MAX_INFORMATION_REFS],
        "faction_ids": faction_ids[:MAX_INFORMATION_REFS],
        "location_ids": location_ids[:MAX_INFORMATION_REFS],
    }


def _pressure_known_scope_count(row: Mapping[str, Any]) -> int:
    seen = set()
    for access in row.get("observer_access") or []:
        if not isinstance(access, Mapping):
            continue
        scope_type = _bounded_str(access.get("scope_type"), 80)
        scope_id = _bounded_str(access.get("scope_id"), 160)
        if scope_type and scope_id:
            seen.add((scope_type, scope_id))
    for scope in row.get("known_by") or []:
        if not isinstance(scope, Mapping):
            continue
        scope_type = _bounded_str(scope.get("scope_type"), 80)
        scope_id = _bounded_str(scope.get("scope_id"), 160)
        if scope_type and scope_id:
            seen.add((scope_type, scope_id))
    return len(seen)


def _pressure_anchor_id(
    *,
    scope: str,
    actor_ids: Sequence[str],
    faction_ids: Sequence[str],
    location_ids: Sequence[str],
) -> str:
    if scope == "personal" and actor_ids:
        return f"actor:{actor_ids[0]}"
    if scope == "faction" and faction_ids:
        return f"faction:{faction_ids[0]}"
    if location_ids:
        return f"location:{location_ids[0]}"
    if faction_ids:
        return f"faction:{faction_ids[0]}"
    if actor_ids:
        return f"actor:{actor_ids[0]}"
    return "public"


def _pressure_candidate_sort_key(row: Mapping[str, Any]) -> Tuple[int, int, int, str]:
    return (
        -_clamp_int(row.get("magnitude"), 0, 100),
        -_clamp_int(row.get("priority"), 0, 100),
        -_stamp_turn(row, "updated_at", _coerce_int(row.get("turn"), 0)),
        str(row.get("source_signal_id") or ""),
    )


def _information_pressure_candidate(row: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    info_id = _bounded_str(row.get("information_id"), 160)
    if not info_id or bool(row.get("stale")):
        return None
    info_type = _normalise_information_type(row.get("information_type"))
    visibility = _normalise_visibility(row.get("visibility_scope"))
    reliability = _clamp_int(row.get("reliability"), 0, 100, default=50)
    gravity = _clamp_int(row.get("gravity"), 0, 10, default=1)
    reach = _pressure_known_scope_count(row)
    subject_targets = _pressure_targets_from_subjects(row.get("subject_refs") or [])
    actor_ids = subject_targets["actor_ids"]
    faction_ids = subject_targets["faction_ids"]
    location_ids = subject_targets["location_ids"]
    scope = "personal" if actor_ids else _pressure_scope_from_visibility(visibility)
    pressure_kind = ""
    reason = ""
    priority = 0

    if info_type == "rumour":
        if (
            gravity < PRESSURE_RUMOUR_MIN_GRAVITY
            or reliability < PRESSURE_RUMOUR_MIN_RELIABILITY
            or visibility not in {"settlement", "faction", "public"}
            or reach < 2
        ):
            return None
        pressure_kind = "social_tension"
        priority = 24 + gravity + reach
        reason = (
            f"spreading rumour reached {reach} scopes with gravity {gravity} "
            f"and reliability {reliability}"
        )
    elif info_type == "evidence_summary":
        if (
            gravity < PRESSURE_INFORMATION_MIN_GRAVITY
            or reliability < PRESSURE_INFORMATION_MIN_RELIABILITY
            or visibility in {"private", "case", "unknown", "archived"}
        ):
            return None
        pressure_kind = "suspicion"
        priority = 26 + gravity
        reason = f"evidence exposure is public enough to travel with gravity {gravity}"
    else:
        if (
            gravity < PRESSURE_INFORMATION_MIN_GRAVITY
            or reliability < PRESSURE_INFORMATION_MIN_RELIABILITY
            or visibility not in {"settlement", "faction", "public", "witnessed", "actor"}
        ):
            return None
        pressure_kind = "suspicion" if actor_ids else "social_tension"
        priority = 22 + gravity
        reason = f"high-confidence claim became visible at {visibility} scope"

    magnitude = min(
        82,
        18
        + gravity * 5
        + max(0, reliability - 60) // 3
        + min(10, reach * 2),
    )
    anchor_id = _pressure_anchor_id(
        scope=scope,
        actor_ids=actor_ids,
        faction_ids=faction_ids,
        location_ids=location_ids,
    )
    return {
        "source_signal_id": info_id,
        "source_kind": "information_item",
        "pressure_kind": pressure_kind,
        "scope": scope,
        "priority": priority,
        "magnitude": magnitude,
        "actor_ids": actor_ids,
        "faction_ids": faction_ids,
        "location_ids": location_ids,
        "anchor_id": anchor_id,
        "origin_id": f"{pressure_kind}:{scope}:{anchor_id}",
        "label": _bounded_str(row.get("summary") or info_type.replace("_", " "), 80),
        "reason": reason,
        "qualifier": info_type,
        "source_event_ids": _bounded_str_list(
            [info_id] + list(row.get("source_event_ids") or []),
            MAX_INFORMATION_REFS,
        ),
        "evidence_refs": _bounded_str_list(
            [f"information:{info_id}"] + list(row.get("source_event_ids") or []),
            MAX_INFORMATION_REFS,
        ),
        "updated_at": row.get("updated_at"),
        "turn": _stamp_turn(row, "updated_at", 0),
    }


def _reputation_pressure_candidate(row: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    signal_id = _bounded_str(row.get("signal_id"), 160)
    if not signal_id:
        return None
    dimension = _normalise_dimension(row.get("dimension"))
    score = _clamp_int(row.get("score"), -100, 100, default=0)
    confidence = _clamp_int(row.get("confidence"), 0, 100, default=50)
    reliability = _clamp_int(row.get("reliability"), 0, 100, default=confidence)
    if (
        confidence < PRESSURE_REPUTATION_MIN_CONFIDENCE
        or reliability < PRESSURE_REPUTATION_MIN_RELIABILITY
        or abs(score) < PRESSURE_REPUTATION_MIN_SCORE
    ):
        return None

    pressure_kind = ""
    reason = ""
    priority = 0
    if dimension == "dangerous" and score >= PRESSURE_REPUTATION_MIN_SCORE:
        pressure_kind = "danger"
        reason = f"dangerous reputation crossed severity threshold at score {score}"
        priority = 34 + score // 4
    elif dimension == "suspicious" and score >= PRESSURE_REPUTATION_MIN_SCORE:
        pressure_kind = "suspicion"
        reason = f"suspicious reputation crossed threshold at score {score}"
        priority = 30 + score // 4
    elif dimension == "trustworthy" and score <= -PRESSURE_REPUTATION_MIN_SCORE:
        pressure_kind = "social_tension"
        reason = f"reputation damage pushed trustworthiness to {score}"
        priority = 28 + abs(score) // 4
    elif dimension == "cruel" and score >= PRESSURE_REPUTATION_MIN_SCORE:
        pressure_kind = "social_tension"
        reason = f"cruel reputation crossed threshold at score {score}"
        priority = 28 + score // 4
    else:
        return None

    observer_scope = _normalise_ref(
        row.get("observer_scope") or {},
        type_key="scope_type",
        id_key="scope_id",
    )
    scope_type = _bounded_str(observer_scope.get("scope_type"), 80)
    scope_id = _bounded_str(observer_scope.get("scope_id"), 160)
    subject_type = _bounded_str(row.get("subject_type"), 80).lower()
    subject_id = _bounded_str(row.get("subject_id"), 160)
    actor_ids = [subject_id] if subject_type in {"actor", "npc", "player"} and subject_id else []
    if actor_ids:
        scope = "personal"
    elif scope_type == "faction":
        scope = "faction"
    else:
        scope = "local"
    faction_ids = [subject_id] if subject_type == "faction" and subject_id else []
    location_ids = [scope_id] if scope_type == "settlement" and scope_id else []
    if scope == "faction" and scope_id and scope_id not in faction_ids:
        faction_ids = [scope_id] + faction_ids
    anchor_id = _pressure_anchor_id(
        scope=scope,
        actor_ids=actor_ids,
        faction_ids=faction_ids,
        location_ids=location_ids,
    )
    magnitude = min(
        86,
        22 + abs(score) // 2 + max(0, confidence - 60) // 4 + max(0, reliability - 60) // 4,
    )
    return {
        "source_signal_id": signal_id,
        "source_kind": "reputation_signal",
        "pressure_kind": pressure_kind,
        "scope": scope,
        "priority": priority,
        "magnitude": magnitude,
        "actor_ids": actor_ids,
        "faction_ids": faction_ids,
        "location_ids": location_ids,
        "anchor_id": anchor_id,
        "origin_id": f"{pressure_kind}:{scope}:{anchor_id}",
        "label": _bounded_str(f"{subject_id or subject_type} {dimension}", 80),
        "reason": reason,
        "qualifier": dimension,
        "source_event_ids": _bounded_str_list(
            [signal_id] + list(row.get("source_event_ids") or []),
            MAX_INFORMATION_REFS,
        ),
        "evidence_refs": _bounded_str_list(
            [f"reputation:{signal_id}"] + list(row.get("source_event_ids") or []),
            MAX_INFORMATION_REFS,
        ),
        "updated_at": row.get("updated_at"),
        "turn": _stamp_turn(row, "updated_at", 0),
    }


def _relationship_pressure_candidate(row: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    receipt_id = _bounded_str(row.get("receipt_id"), 160)
    npc_name = _bounded_str(row.get("npc_name"), 160)
    after_state = _bounded_str(row.get("after_state"), 80)
    before_state = _bounded_str(row.get("before_state"), 80)
    if not receipt_id or not npc_name or after_state not in {"collapsed", "betrayal_risk"}:
        return None
    pressure_kind = "social_tension" if after_state == "collapsed" else "suspicion"
    magnitude = 54 if after_state == "collapsed" else 42
    reason = (
        f"relationship threshold moved from {before_state or 'neutral'} "
        f"to {after_state}"
    )
    return {
        "source_signal_id": receipt_id,
        "source_kind": "relationship_receipt",
        "pressure_kind": pressure_kind,
        "scope": "personal",
        "priority": 40 if after_state == "collapsed" else 32,
        "magnitude": magnitude,
        "actor_ids": ["player", npc_name],
        "faction_ids": [],
        "location_ids": [],
        "anchor_id": f"actor:{npc_name}",
        "origin_id": f"{pressure_kind}:personal:actor:{npc_name}",
        "label": _bounded_str(f"{npc_name} {after_state.replace('_', ' ')}", 80),
        "reason": reason,
        "qualifier": after_state,
        "source_event_ids": _bounded_str_list(
            [receipt_id, row.get("source_event_id")] + list(row.get("source_event_ids") or []),
            MAX_INFORMATION_REFS,
        ),
        "evidence_refs": _bounded_str_list([f"relationship:{receipt_id}"], MAX_INFORMATION_REFS),
        "updated_at": {"turn": _coerce_int(row.get("turn"), 0)},
        "turn": _coerce_int(row.get("turn"), 0),
    }


def _pressure_signal_source_turn(row: Mapping[str, Any]) -> int:
    if str(row.get("receipt_type") or "") == "relationship_threshold_crossed":
        return _coerce_int(row.get("turn"), 0)
    return _stamp_turn(row, "updated_at", _stamp_turn(row, "created_at", 0))


def _pressure_signal_eligible(
    row: Mapping[str, Any],
    *,
    eligible_before_turn: Optional[int] = None,
    allow_same_turn_signals: bool = False,
) -> bool:
    if eligible_before_turn is None:
        return True
    source_turn = _pressure_signal_source_turn(row)
    if str(row.get("receipt_type") or "") == "relationship_threshold_crossed":
        return source_turn <= int(eligible_before_turn)
    if allow_same_turn_signals:
        return source_turn <= int(eligible_before_turn)
    return source_turn < int(eligible_before_turn)


def pressure_signal_candidates(
    replayability_state: Mapping[str, Any],
    *,
    limit: int = PRESSURE_SIGNAL_MAX,
    eligible_before_turn: Optional[int] = None,
    allow_same_turn_signals: bool = False,
) -> List[Dict[str, Any]]:
    if not isinstance(replayability_state, Mapping):
        return []
    candidates: List[Dict[str, Any]] = []
    for item in replayability_state.get("information_items") or []:
        if isinstance(item, Mapping) and _pressure_signal_eligible(
            item,
            eligible_before_turn=eligible_before_turn,
            allow_same_turn_signals=allow_same_turn_signals,
        ):
            candidate = _information_pressure_candidate(item)
            if candidate:
                candidates.append(candidate)
    for signal in replayability_state.get("reputation_signals") or []:
        if isinstance(signal, Mapping) and _pressure_signal_eligible(
            signal,
            eligible_before_turn=eligible_before_turn,
            allow_same_turn_signals=allow_same_turn_signals,
        ):
            candidate = _reputation_pressure_candidate(signal)
            if candidate:
                candidates.append(candidate)
    for receipt in replayability_state.get("relationship_effect_receipts") or []:
        if isinstance(receipt, Mapping) and _pressure_signal_eligible(
            receipt,
            eligible_before_turn=eligible_before_turn,
            allow_same_turn_signals=allow_same_turn_signals,
        ):
            candidate = _relationship_pressure_candidate(receipt)
            if candidate:
                candidates.append(candidate)
    ordered = sorted(candidates, key=_pressure_candidate_sort_key)
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for row in ordered:
        source_signal_id = str(row.get("source_signal_id") or "")
        if not source_signal_id or source_signal_id in seen:
            continue
        seen.add(source_signal_id)
        deduped.append(row)
        if len(deduped) >= max(0, min(PRESSURE_SIGNAL_MAX, int(limit or 0))):
            break
    return deduped


def _actor_context_from_rolling(rolling_state: Mapping[str, Any]) -> Dict[str, Dict[str, List[str]]]:
    out: Dict[str, Dict[str, List[str]]] = {}
    if not isinstance(rolling_state, Mapping):
        return out

    def add(actor_id: str, *, locations: Sequence[str] = (), factions: Sequence[str] = (), aliases: Sequence[str] = ()) -> None:
        aid = _bounded_str(actor_id, 160)
        if not aid:
            return
        row = out.setdefault(aid.lower(), {"locations": [], "factions": [], "aliases": []})
        for key, values in (("locations", locations), ("factions", factions), ("aliases", aliases)):
            for value in _bounded_str_list(values, MAX_INFORMATION_REFS):
                if value and value not in row[key]:
                    row[key].append(value)

    scene = _bounded_str(rolling_state.get("scene") or rolling_state.get("location"), 160)
    for npc in rolling_state.get("npcs") or []:
        if not isinstance(npc, Mapping):
            continue
        actor_id = _bounded_str(npc.get("npc_id") or npc.get("actor_id") or npc.get("id") or npc.get("name"), 160)
        add(
            actor_id,
            locations=[
                npc.get("location_id") or "",
                npc.get("location") or "",
                npc.get("last_seen") or "",
                scene,
            ],
            factions=[npc.get("faction_id") or "", npc.get("faction") or ""],
            aliases=[npc.get("name") or "", npc.get("display_name") or ""],
        )
        for alias in _bounded_str_list([npc.get("name"), npc.get("display_name")], MAX_INFORMATION_REFS):
            add(
                alias,
                locations=[
                    npc.get("location_id") or "",
                    npc.get("location") or "",
                    npc.get("last_seen") or "",
                    scene,
                ],
                factions=[npc.get("faction_id") or "", npc.get("faction") or ""],
                aliases=[actor_id],
            )
    for row in rolling_state.get("actor_location_registry") or []:
        if not isinstance(row, Mapping):
            continue
        add(
            row.get("actor_id") or row.get("npc_id") or row.get("id") or row.get("name") or "",
            locations=[row.get("location_id") or row.get("location") or row.get("last_seen") or ""],
        )
    return out


def _scope_present(access_rows: Sequence[Mapping[str, Any]], scope_type: str, scope_id: str) -> bool:
    stype = _bounded_str(scope_type, 80).lower()
    sid = _bounded_str(scope_id, 160).lower()
    if not stype or not sid:
        return False
    for row in access_rows:
        if not isinstance(row, Mapping):
            continue
        if _bounded_str(row.get("scope_type"), 80).lower() == stype and _bounded_str(row.get("scope_id"), 160).lower() == sid:
            return True
    return False


def _refs_by_type(refs: Sequence[Mapping[str, Any]], ref_type: str) -> List[str]:
    out: List[str] = []
    for ref in refs:
        if not isinstance(ref, Mapping) or str(ref.get("subject_type") or "").lower() != ref_type:
            continue
        value = _bounded_str(ref.get("subject_id"), 160)
        if value and value not in out:
            out.append(value)
    return out


def _propagation_candidates_for_item(
    item: Mapping[str, Any],
    rolling_state: Mapping[str, Any],
    *,
    turn_number: int,
) -> List[Dict[str, Any]]:
    row = _normalise_information_item(item)
    if row.get("truth_status") == "truth" or row.get("visibility_scope") == "archived":
        return []
    source_ids = row.get("source_event_ids") or []
    access_rows = row.get("observer_access") or []
    reliability = max(10, _clamp_int(row.get("reliability"), 0, 100, default=50) - 8)
    distortion = min(100, _clamp_int(row.get("distortion_level"), 0, 100, default=0) + 6)
    actor_context = _actor_context_from_rolling(rolling_state)

    candidate_rows: List[Dict[str, Any]] = []
    candidate_locations: List[str] = []
    candidate_factions: List[str] = []
    candidate_cases: List[str] = []

    can_spread_from_subjects = row.get("visibility_scope") not in {"private", "case", "unknown", "archived"}
    if can_spread_from_subjects:
        for location_id in _refs_by_type(row.get("subject_refs") or [], "location"):
            if location_id not in candidate_locations:
                candidate_locations.append(location_id)
        for faction_id in _refs_by_type(row.get("subject_refs") or [], "faction"):
            if faction_id not in candidate_factions:
                candidate_factions.append(faction_id)
    if row.get("visibility_scope") == "case":
        for case_id in _refs_by_type(row.get("subject_refs") or [], "case"):
            if case_id not in candidate_cases:
                candidate_cases.append(case_id)

    for access in access_rows:
        if not isinstance(access, Mapping):
            continue
        scope_type = _bounded_str(access.get("scope_type"), 80).lower()
        scope_id = _bounded_str(access.get("scope_id"), 160)
        if scope_type == "actor":
            actor_row = actor_context.get(scope_id.lower()) or {}
            for location_id in actor_row.get("locations") or []:
                if location_id and location_id not in candidate_locations:
                    candidate_locations.append(location_id)
            for faction_id in actor_row.get("factions") or []:
                if faction_id and faction_id not in candidate_factions:
                    candidate_factions.append(faction_id)
        elif scope_type == "settlement" and scope_id not in candidate_locations:
            candidate_locations.append(scope_id)
        elif scope_type == "faction" and scope_id not in candidate_factions:
            candidate_factions.append(scope_id)
        elif scope_type == "case" and scope_id not in candidate_cases:
            candidate_cases.append(scope_id)

    for location_id in sorted(candidate_locations):
        if not _scope_present(access_rows, "settlement", location_id):
            access = _access_from_scope(
                "settlement",
                location_id,
                "local_community",
                source_event_ids=source_ids,
                turn_number=turn_number,
                reliability=reliability,
                distortion_level=distortion,
            )
            if access:
                candidate_rows.append(access)

    if _clamp_int(row.get("gravity"), 0, 10, default=1) >= 4 or row.get("visibility_scope") in {"faction", "settlement"}:
        for faction_id in sorted(candidate_factions):
            if not _scope_present(access_rows, "faction", faction_id):
                access = _access_from_scope(
                    "faction",
                    faction_id,
                    "faction_channel",
                    source_event_ids=source_ids,
                    turn_number=turn_number,
                    reliability=max(10, reliability - 5),
                    distortion_level=min(100, distortion + 5),
                )
                if access:
                    candidate_rows.append(access)

    if row.get("information_type") in {"evidence_summary", "claim"}:
        for case_id in sorted(candidate_cases):
            if not _scope_present(access_rows, "case", case_id):
                access = _access_from_scope(
                    "case",
                    case_id,
                    "investigation_channel",
                    source_event_ids=source_ids,
                    turn_number=turn_number,
                    reliability=max(10, reliability - 3),
                    distortion_level=min(100, distortion + 3),
                )
                if access:
                    candidate_rows.append(access)

    return _normalise_observer_access(
        sorted(candidate_rows, key=_access_sort_key),
        default_source_event_ids=source_ids,
        default_turn=turn_number,
        default_reliability=reliability,
        default_distortion=distortion,
        limit=MAX_PROPAGATION_CHANGES_PER_TICK,
    )


def _merge_access_into_item(item: Dict[str, Any], access: Mapping[str, Any], turn_number: int) -> bool:
    before = _normalise_observer_access(item.get("observer_access"), default_source_event_ids=item.get("source_event_ids") or [])
    merged = _normalise_observer_access(
        before + [access],
        default_source_event_ids=item.get("source_event_ids") or [],
        default_turn=turn_number,
        default_reliability=_clamp_int(item.get("reliability"), 0, 100, default=50),
        default_distortion=_clamp_int(item.get("distortion_level"), 0, 100, default=0),
    )
    if merged == before:
        return False
    item["observer_access"] = merged
    item["known_by"] = _known_by_from_access(merged)
    item["updated_at"] = {"turn": max(0, turn_number)}
    visibility = _default_access_type_for_scope(access.get("scope_type"))
    if access.get("scope_type") == "settlement":
        visibility_scope = "settlement"
    elif access.get("scope_type") == "faction":
        visibility_scope = "faction"
    elif access.get("scope_type") == "case":
        visibility_scope = "case"
    elif access.get("scope_type") in {"actor", "player"}:
        visibility_scope = "witnessed"
    elif visibility == "secondary_source":
        visibility_scope = "public"
    else:
        visibility_scope = str(item.get("visibility_scope") or "private")
    if _visibility_rank(visibility_scope) > _visibility_rank(str(item.get("visibility_scope") or "")):
        item["visibility_scope"] = visibility_scope
    return True


def _apply_information_decay(item: Dict[str, Any], turn_number: int) -> bool:
    row = _normalise_information_item(item)
    if row.get("truth_status") == "truth":
        return False
    last_decay = _coerce_int(row.get("last_decay_turn"), 0)
    if last_decay > 0 or row.get("decay_ready"):
        return False
    if last_decay >= turn_number:
        return False
    updated_turn = _stamp_turn(row, "updated_at", 0)
    age = max(0, turn_number - updated_turn)
    if age < DECAY_INTERVAL_TURNS:
        return False
    gravity = _clamp_int(row.get("gravity"), 0, 10, default=1)
    if gravity > LOW_GRAVITY_DECAY_THRESHOLD and row.get("information_type") != "rumour":
        return False
    reliability = _clamp_int(row.get("reliability"), 0, 100, default=50)
    distortion = _clamp_int(row.get("distortion_level"), 0, 100, default=0)
    new_reliability = max(10, reliability - (8 if gravity <= LOW_GRAVITY_DECAY_THRESHOLD else 4))
    new_distortion = min(100, distortion + (10 if row.get("information_type") == "rumour" else 5))
    stale = bool(row.get("stale")) or age >= STALE_RUMOUR_TURNS or new_reliability < 35
    changed = (
        new_reliability != reliability
        or new_distortion != distortion
        or stale != bool(row.get("stale"))
        or row.get("decay_ready") is not True
    )
    if not changed:
        return False
    item["reliability"] = new_reliability
    item["reliability_band"] = _reliability_band(new_reliability)
    item["distortion_level"] = new_distortion
    item["stale"] = stale
    item["decay_ready"] = True
    item["last_decay_turn"] = max(0, turn_number)
    return True


def _apply_reputation_decay(signal: Dict[str, Any], turn_number: int) -> bool:
    row = _normalise_reputation_signal(signal)
    last_decay = _coerce_int(row.get("last_decay_turn"), 0)
    if last_decay > 0 or row.get("decay_ready"):
        return False
    if last_decay >= turn_number:
        return False
    updated_turn = _stamp_turn(row, "updated_at", 0)
    age = max(0, turn_number - updated_turn)
    if age < DECAY_INTERVAL_TURNS:
        return False
    confidence = _clamp_int(row.get("confidence"), 0, 100, default=50)
    reliability = _clamp_int(row.get("reliability"), 0, 100, default=confidence)
    new_confidence = max(10, confidence - 4)
    new_reliability = max(10, reliability - 3)
    if new_confidence == confidence and new_reliability == reliability:
        return False
    signal["confidence"] = new_confidence
    signal["reliability"] = new_reliability
    signal["reliability_band"] = _reliability_band(new_reliability)
    signal["decay_ready"] = new_confidence < 45
    signal["last_decay_turn"] = max(0, turn_number)
    return True


def evolve_information(
    replayability_state: Dict[str, Any],
    rolling_state: Mapping[str, Any],
    turn_number: int,
    *,
    run_seed: str = "",
    structured_sources: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    diagnostics = {
        "information_engine_executed": False,
        "information_candidates_evaluated": 0,
        "information_created": 0,
        "information_reinforced": 0,
        "information_duplicate_suppressed": 0,
        "information_propagation_candidates_evaluated": 0,
        "information_propagated": 0,
        "information_propagation_duplicate_suppressed": 0,
        "information_decay_applied": 0,
        "reputation_candidates_evaluated": 0,
        "reputation_signal_created": 0,
        "reputation_signal_updated": 0,
        "reputation_duplicate_suppressed": 0,
        "reputation_decay_applied": 0,
    }
    if not isinstance(replayability_state, dict):
        return {"items": [], "reputation_signals": [], "receipts": [], "diagnostics": diagnostics}

    seed = run_seed or str(replayability_state.get("run_seed") or "information-engine")
    information_items = _cap_information_items(replayability_state.get("information_items") or [], run_seed=seed)
    reputation_signals = _cap_reputation_signals(replayability_state.get("reputation_signals") or [], run_seed=seed)
    replayability_state["information_items"] = information_items
    replayability_state["reputation_signals"] = reputation_signals
    replayability_state.setdefault("information_receipts", [])
    local_receipts: List[Dict[str, Any]] = []
    remaining_changes = MAX_INFORMATION_CHANGES_PER_TICK

    candidates: List[Dict[str, Any]] = []
    for event in replayability_state.get("engine_world_events") or []:
        if isinstance(event, Mapping):
            candidate = _information_from_engine_event(event, turn_number=turn_number, run_seed=seed)
            if candidate:
                candidates.append(candidate)
    for event in replayability_state.get("world_events") or []:
        if isinstance(event, Mapping):
            candidate = _information_from_world_event(event, turn_number=turn_number, run_seed=seed)
            if candidate:
                candidates.append(candidate)
    for evidence in replayability_state.get("evidence") or []:
        if isinstance(evidence, Mapping):
            candidate = _information_from_evidence(evidence, turn_number=turn_number, run_seed=seed)
            if candidate:
                candidates.append(candidate)
    for investigation in replayability_state.get("investigations") or []:
        if isinstance(investigation, Mapping):
            candidate = _information_from_investigation(investigation, turn_number=turn_number, run_seed=seed)
            if candidate:
                candidates.append(candidate)
    for source in structured_sources or []:
        if isinstance(source, Mapping):
            candidate = _information_from_structured_source(source, turn_number=turn_number, run_seed=seed)
            if candidate:
                candidates.append(candidate)

    by_id = {str(row.get("information_id") or ""): row for row in information_items if row.get("information_id")}
    seen_candidates = set()
    for candidate in sorted(candidates, key=_information_sort_key):
        diagnostics["information_candidates_evaluated"] += 1
        info_id = str(candidate.get("information_id") or "")
        if not info_id or info_id in seen_candidates:
            diagnostics["information_duplicate_suppressed"] += 1
            continue
        seen_candidates.add(info_id)
        existing = by_id.get(info_id)
        if existing is None:
            if remaining_changes <= 0 or len(information_items) >= MAX_INFORMATION_ITEMS:
                diagnostics["information_duplicate_suppressed"] += 1
                continue
            information_items.append(candidate)
            by_id[info_id] = candidate
            if _append_receipt(
                replayability_state,
                local_receipts,
                receipt_type="information_created",
                turn_number=turn_number,
                target_key="information_id",
                target_id=info_id,
                source_event_ids=candidate.get("source_event_ids") or [],
            ):
                diagnostics["information_created"] += 1
                remaining_changes -= 1
            continue
        if remaining_changes <= 0:
            continue
        if _merge_information_item(existing, candidate, turn_number):
            if _append_receipt(
                replayability_state,
                local_receipts,
                receipt_type="information_reinforced",
                turn_number=turn_number,
                target_key="information_id",
                target_id=info_id,
                source_event_ids=candidate.get("source_event_ids") or [],
            ):
                diagnostics["information_reinforced"] += 1
                remaining_changes -= 1
        else:
            diagnostics["information_duplicate_suppressed"] += 1

    propagation_remaining = MAX_PROPAGATION_CHANGES_PER_TICK
    for item in sorted(information_items, key=_information_sort_key):
        if propagation_remaining <= 0:
            break
        if not isinstance(item, dict):
            continue
        for access in _propagation_candidates_for_item(item, rolling_state, turn_number=turn_number):
            diagnostics["information_propagation_candidates_evaluated"] += 1
            if propagation_remaining <= 0:
                diagnostics["information_propagation_duplicate_suppressed"] += 1
                break
            context = ":".join(
                [
                    _bounded_str(access.get("access_type"), 80),
                    _bounded_str(access.get("scope_type"), 80),
                    _bounded_str(access.get("scope_id"), 160),
                ]
            )
            if not _merge_access_into_item(item, access, turn_number):
                diagnostics["information_propagation_duplicate_suppressed"] += 1
                continue
            if _append_receipt(
                replayability_state,
                local_receipts,
                receipt_type="information_propagated",
                turn_number=turn_number,
                target_key="information_id",
                target_id=str(item.get("information_id") or ""),
                source_event_ids=item.get("source_event_ids") or [],
                receipt_context=context,
                details=access,
            ):
                diagnostics["information_propagated"] += 1
                propagation_remaining -= 1

    decay_remaining = MAX_PROPAGATION_CHANGES_PER_TICK
    for item in sorted(information_items, key=_information_sort_key):
        if decay_remaining <= 0:
            break
        if not isinstance(item, dict):
            continue
        if not _apply_information_decay(item, turn_number):
            continue
        if _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type="information_decayed",
            turn_number=turn_number,
            target_key="information_id",
            target_id=str(item.get("information_id") or ""),
            source_event_ids=item.get("source_event_ids") or [],
        ):
            diagnostics["information_decay_applied"] += 1
            decay_remaining -= 1

    signal_candidates: List[Dict[str, Any]] = []
    for event in replayability_state.get("engine_world_events") or []:
        if isinstance(event, Mapping):
            signal_candidates.extend(_reputation_from_event(event, turn_number=turn_number, run_seed=seed))
    for evidence in replayability_state.get("evidence") or []:
        if isinstance(evidence, Mapping):
            signal_candidates.extend(_reputation_from_evidence(evidence, turn_number=turn_number, run_seed=seed))
    for receipt in replayability_state.get("relationship_effect_receipts") or []:
        if isinstance(receipt, Mapping):
            signal = _reputation_from_relationship_receipt(receipt, turn_number=turn_number, run_seed=seed)
            if signal:
                signal_candidates.append(signal)

    signals_by_id = {str(row.get("signal_id") or ""): row for row in reputation_signals if row.get("signal_id")}
    seen_signal_candidates = set()
    for candidate in sorted(signal_candidates, key=_reputation_sort_key):
        diagnostics["reputation_candidates_evaluated"] += 1
        signal_id = str(candidate.get("signal_id") or "")
        if not signal_id or signal_id in seen_signal_candidates:
            diagnostics["reputation_duplicate_suppressed"] += 1
            continue
        seen_signal_candidates.add(signal_id)
        existing = signals_by_id.get(signal_id)
        if existing is None:
            if remaining_changes <= 0 or len(reputation_signals) >= MAX_REPUTATION_SIGNALS:
                diagnostics["reputation_duplicate_suppressed"] += 1
                continue
            reputation_signals.append(candidate)
            signals_by_id[signal_id] = candidate
            if _append_receipt(
                replayability_state,
                local_receipts,
                receipt_type="reputation_signal_created",
                turn_number=turn_number,
                target_key="signal_id",
                target_id=signal_id,
                source_event_ids=candidate.get("source_event_ids") or [],
            ):
                diagnostics["reputation_signal_created"] += 1
                remaining_changes -= 1
            continue
        if remaining_changes <= 0:
            continue
        if _merge_reputation_signal(existing, candidate, turn_number):
            if _append_receipt(
                replayability_state,
                local_receipts,
                receipt_type="reputation_signal_updated",
                turn_number=turn_number,
                target_key="signal_id",
                target_id=signal_id,
                source_event_ids=candidate.get("source_event_ids") or [],
            ):
                diagnostics["reputation_signal_updated"] += 1
                remaining_changes -= 1
        else:
            diagnostics["reputation_duplicate_suppressed"] += 1

    reputation_decay_remaining = MAX_PROPAGATION_CHANGES_PER_TICK
    for signal in sorted(reputation_signals, key=_reputation_sort_key):
        if reputation_decay_remaining <= 0:
            break
        if not isinstance(signal, dict):
            continue
        if not _apply_reputation_decay(signal, turn_number):
            continue
        if _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type="reputation_signal_decayed",
            turn_number=turn_number,
            target_key="signal_id",
            target_id=str(signal.get("signal_id") or ""),
            source_event_ids=signal.get("source_event_ids") or [],
        ):
            diagnostics["reputation_decay_applied"] += 1
            reputation_decay_remaining -= 1

    replayability_state["information_items"] = _cap_information_items(information_items, run_seed=seed)
    replayability_state["reputation_signals"] = _cap_reputation_signals(reputation_signals, run_seed=seed)
    diagnostics["information_engine_executed"] = bool(
        local_receipts or replayability_state["information_items"] or replayability_state["reputation_signals"]
    )
    return {
        "items": replayability_state["information_items"],
        "reputation_signals": replayability_state["reputation_signals"],
        "receipts": local_receipts,
        "diagnostics": diagnostics,
    }


def _project_information_item(row: Mapping[str, Any]) -> Dict[str, Any]:
    item = _normalise_information_item(row)
    return {
        "information_type": item.get("information_type"),
        "summary": item.get("summary"),
        "reliability_band": item.get("reliability_band"),
        "distortion_level": item.get("distortion_level"),
        "visibility_scope": item.get("visibility_scope"),
        "gravity": item.get("gravity"),
        "subjects": [
            {"type": ref.get("subject_type"), "id": ref.get("subject_id")}
            for ref in item.get("subject_refs") or []
        ][:MAX_SUBJECT_REFS],
    }


def _project_reputation_signal(row: Mapping[str, Any]) -> Dict[str, Any]:
    signal = _normalise_reputation_signal(row)
    return {
        "subject_type": signal.get("subject_type"),
        "subject_id": signal.get("subject_id"),
        "observer_scope": dict(signal.get("observer_scope") or {}),
        "dimension": signal.get("dimension"),
        "score_band": signal.get("score_band"),
        "confidence_band": _reliability_band(signal.get("confidence")),
    }


def project_active_information_for_rolling(
    replayability_state: Mapping[str, Any],
    *,
    rolling_state: Optional[Mapping[str, Any]] = None,
    limit: int = MAX_PROJECTED_INFORMATION,
) -> List[Dict[str, Any]]:
    if not isinstance(replayability_state, Mapping):
        return []
    seed = str(replayability_state.get("run_seed") or "information-engine")
    rows = _cap_information_items(replayability_state.get("information_items") or [], run_seed=seed)
    if isinstance(rolling_state, Mapping):
        context = _observer_context_from_rolling(rolling_state)
        rows = information_visible_to_observer(
            {"information_items": rows},
            actor_ids=context["actor_ids"],
            location_ids=context["location_ids"],
            faction_ids=context["faction_ids"],
            include_public=True,
            limit=MAX_INFORMATION_ITEMS,
        )
    ordered = sorted(rows, key=_information_sort_key)[: max(0, min(MAX_PROJECTED_INFORMATION, int(limit or 0)))]
    return [_project_information_item(row) for row in ordered]


def project_reputation_for_rolling(
    replayability_state: Mapping[str, Any],
    *,
    rolling_state: Optional[Mapping[str, Any]] = None,
    limit: int = MAX_PROJECTED_REPUTATION,
) -> List[Dict[str, Any]]:
    if not isinstance(replayability_state, Mapping):
        return []
    seed = str(replayability_state.get("run_seed") or "information-engine")
    rows = _cap_reputation_signals(replayability_state.get("reputation_signals") or [], run_seed=seed)
    if isinstance(rolling_state, Mapping):
        context = _observer_context_from_rolling(rolling_state)
        rows = reputation_visible_to_observer(
            {"reputation_signals": rows},
            observer_scope_ids=context["actor_ids"] + context["location_ids"] + context["faction_ids"],
            include_public=True,
            limit=MAX_REPUTATION_SIGNALS,
        )
    ordered = sorted(rows, key=_reputation_sort_key)[: max(0, min(MAX_PROJECTED_REPUTATION, int(limit or 0)))]
    return [_project_reputation_signal(row) for row in ordered]


def project_information_for_prompt(replayability_state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return project_active_information_for_rolling(replayability_state, limit=MAX_PROMPT_INFORMATION)


def project_reputation_for_prompt(replayability_state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return project_reputation_for_rolling(replayability_state, limit=MAX_PROMPT_REPUTATION)


def prompt_safe_rolling_state(rolling_state: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(rolling_state, Mapping):
        return {}
    safe = copy.deepcopy(dict(rolling_state))
    for key in ("information_items", "information_receipts", "reputation_signals"):
        safe.pop(key, None)
    if isinstance(safe.get("active_information"), list):
        safe["active_information"] = [
            _project_information_item(row)
            for row in safe.get("active_information") or []
            if isinstance(row, Mapping)
        ][:MAX_PROMPT_INFORMATION]
    if isinstance(safe.get("active_reputation"), list):
        safe["active_reputation"] = [
            _project_reputation_signal(row)
            for row in safe.get("active_reputation") or []
            if isinstance(row, Mapping)
        ][:MAX_PROMPT_REPUTATION]
    return safe


def copy_information_state(replayability_state: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(replayability_state, Mapping):
        return {"information_items": [], "reputation_signals": []}
    seed = str(replayability_state.get("run_seed") or "information-engine")
    return {
        "information_items": _cap_information_items(replayability_state.get("information_items") or [], run_seed=seed),
        "reputation_signals": _cap_reputation_signals(replayability_state.get("reputation_signals") or [], run_seed=seed),
    }


def _token_set(*values: Any) -> set:
    out = set()
    for value in values:
        raw = value if isinstance(value, (list, tuple, set)) else [value]
        for item in raw:
            text = str(item or "").strip().lower()
            if text:
                out.add(text)
    return out


def _observer_context_from_rolling(rolling_state: Mapping[str, Any]) -> Dict[str, List[str]]:
    actor_ids: List[str] = ["player"]
    location_ids: List[str] = []
    faction_ids: List[str] = []
    if not isinstance(rolling_state, Mapping):
        return {"actor_ids": actor_ids, "location_ids": location_ids, "faction_ids": faction_ids}
    for value in (rolling_state.get("scene"), rolling_state.get("location")):
        text = _bounded_str(value, 160)
        if text and text not in location_ids:
            location_ids.append(text)
    for npc in rolling_state.get("npcs") or []:
        if not isinstance(npc, Mapping):
            continue
        for value in (
            npc.get("npc_id"),
            npc.get("actor_id"),
            npc.get("id"),
            npc.get("name"),
            npc.get("display_name"),
        ):
            text = _bounded_str(value, 160)
            if text and text not in actor_ids:
                actor_ids.append(text)
        for value in (npc.get("location_id"), npc.get("location"), npc.get("last_seen")):
            text = _bounded_str(value, 160)
            if text and text not in location_ids:
                location_ids.append(text)
        for value in (npc.get("faction_id"), npc.get("faction")):
            text = _bounded_str(value, 160)
            if text and text not in faction_ids:
                faction_ids.append(text)
    return {"actor_ids": actor_ids, "location_ids": location_ids, "faction_ids": faction_ids}


def _observer_tokens(
    *,
    actor_ids: Sequence[str] = (),
    location_ids: Sequence[str] = (),
    faction_ids: Sequence[str] = (),
    case_ids: Sequence[str] = (),
    include_public: bool = True,
) -> Dict[str, set]:
    actors = _token_set(actor_ids)
    if "player" in actors:
        actors.add("player")
    return {
        "actor": actors,
        "player": actors if "player" in actors else set(),
        "settlement": _token_set(location_ids),
        "location": _token_set(location_ids),
        "faction": _token_set(faction_ids),
        "case": _token_set(case_ids),
        "public": {"public"} if include_public else set(),
    }


def _access_visible_to_tokens(access: Mapping[str, Any], tokens: Mapping[str, set]) -> bool:
    scope_type = _bounded_str(access.get("scope_type"), 80).lower()
    scope_id = _bounded_str(access.get("scope_id"), 160).lower()
    if not scope_type or not scope_id or scope_type in {"unknown", "unobserved"}:
        return False
    if scope_type == "public":
        return bool(tokens.get("public"))
    if scope_type == "player":
        return "player" in tokens.get("actor", set())
    return scope_id in tokens.get(scope_type, set())


def _information_visible_to_tokens(
    row: Mapping[str, Any],
    tokens: Mapping[str, set],
    *,
    information_ids: Sequence[str] = (),
) -> bool:
    item = _normalise_information_item(row)
    if _token_set(item.get("information_id")).intersection(_token_set(information_ids)):
        return True
    for access in item.get("observer_access") or []:
        if isinstance(access, Mapping) and _access_visible_to_tokens(access, tokens):
            return True
    for known in item.get("known_by") or []:
        if isinstance(known, Mapping) and _access_visible_to_tokens(known, tokens):
            return True
    return False


def information_visible_to_observer(
    information_state: Mapping[str, Any],
    *,
    actor_ids: Sequence[str] = (),
    location_ids: Sequence[str] = (),
    faction_ids: Sequence[str] = (),
    case_ids: Sequence[str] = (),
    information_ids: Sequence[str] = (),
    include_public: bool = True,
    limit: int = MAX_CONTEXT_INFORMATION,
) -> List[Dict[str, Any]]:
    if not isinstance(information_state, Mapping):
        return []
    tokens = _observer_tokens(
        actor_ids=actor_ids,
        location_ids=location_ids,
        faction_ids=faction_ids,
        case_ids=case_ids,
        include_public=include_public,
    )
    matched: List[Dict[str, Any]] = []
    for raw in information_state.get("information_items") or []:
        if not isinstance(raw, Mapping):
            continue
        row = _normalise_information_item(raw)
        if _information_visible_to_tokens(row, tokens, information_ids=information_ids):
            matched.append(row)
    return sorted(matched, key=_information_sort_key)[: max(0, min(MAX_INFORMATION_ITEMS, int(limit or 0)))]


def information_visible_to_actor(
    information_state: Mapping[str, Any],
    actor_id: str,
    *,
    location_id: str = "",
    faction_id: str = "",
    case_ids: Sequence[str] = (),
    include_public: bool = True,
    limit: int = MAX_CONTEXT_INFORMATION,
) -> List[Dict[str, Any]]:
    return information_visible_to_observer(
        information_state,
        actor_ids=[actor_id],
        location_ids=[location_id],
        faction_ids=[faction_id],
        case_ids=case_ids,
        include_public=include_public,
        limit=limit,
    )


def rumours_visible_in_settlement(
    information_state: Mapping[str, Any],
    settlement_id: str,
    *,
    include_claims: bool = True,
    limit: int = MAX_CONTEXT_INFORMATION,
) -> List[Dict[str, Any]]:
    visible = information_visible_to_observer(
        information_state,
        location_ids=[settlement_id],
        include_public=True,
        limit=MAX_INFORMATION_ITEMS,
    )
    allowed = {"rumour", "claim"} if include_claims else {"rumour"}
    return [
        row
        for row in visible
        if row.get("information_type") in allowed
    ][: max(0, min(MAX_CONTEXT_INFORMATION, int(limit or 0)))]


def reputation_visible_to_observer(
    information_state: Mapping[str, Any],
    *,
    subject_ids: Sequence[str] = (),
    observer_scope_ids: Sequence[str] = (),
    include_public: bool = True,
    limit: int = MAX_CONTEXT_REPUTATION,
) -> List[Dict[str, Any]]:
    if not isinstance(information_state, Mapping):
        return []
    subjects = _token_set(subject_ids)
    scopes = _token_set(observer_scope_ids)
    if include_public:
        scopes.add("public")
    matched: List[Dict[str, Any]] = []
    for raw in information_state.get("reputation_signals") or []:
        if not isinstance(raw, Mapping):
            continue
        row = _normalise_reputation_signal(raw)
        scope = row.get("observer_scope") or {}
        subject_match = not subjects or bool(_token_set(row.get("subject_id")).intersection(subjects))
        scope_id = _bounded_str(scope.get("scope_id"), 160).lower()
        scope_type = _bounded_str(scope.get("scope_type"), 80).lower()
        scope_match = (
            scope_id in scopes
            or (scope_type == "public" and include_public)
            or (scope_type == "player" and "player" in scopes)
        )
        if subject_match and scope_match:
            matched.append(row)
    return sorted(matched, key=_reputation_sort_key)[: max(0, min(MAX_REPUTATION_SIGNALS, int(limit or 0)))]


def active_information_for_context(
    information_state: Mapping[str, Any],
    *,
    actor_ids: Sequence[str] = (),
    location_ids: Sequence[str] = (),
    faction_ids: Sequence[str] = (),
    case_ids: Sequence[str] = (),
    information_ids: Sequence[str] = (),
    limit: int = MAX_CONTEXT_INFORMATION,
) -> List[Dict[str, Any]]:
    return information_visible_to_observer(
        information_state,
        actor_ids=actor_ids,
        location_ids=location_ids,
        faction_ids=faction_ids,
        case_ids=case_ids,
        information_ids=information_ids,
        include_public=True,
        limit=limit,
    )


def reputation_for_context(
    information_state: Mapping[str, Any],
    *,
    subject_ids: Sequence[str] = (),
    observer_scope_ids: Sequence[str] = (),
    limit: int = MAX_CONTEXT_REPUTATION,
) -> List[Dict[str, Any]]:
    return reputation_visible_to_observer(
        information_state,
        subject_ids=subject_ids,
        observer_scope_ids=observer_scope_ids,
        include_public=True,
        limit=limit,
    )
