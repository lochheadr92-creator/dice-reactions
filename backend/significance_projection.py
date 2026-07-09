"""
Passive Significance projection.

Significance is a derived, advisory view over causal visibility entries. It does
not mutate inputs, persist state, create truth, or wire itself into runtime
consumers.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SIGNIFICANCE_PROJECTION_SCHEMA_VERSION = 1
SIGNIFICANCE_SOURCE_VISIBILITY_SCHEMA_VERSION = 1
MAX_SIGNIFICANCE_ENTRIES = 24
MAX_SIGNIFICANCE_SOURCE_IDS = 8
MAX_SIGNIFICANCE_REASON_CODES = 8
MAX_SIGNIFICANCE_METADATA_KEYS = 8
MAX_SIGNIFICANCE_TEXT = 160

SIGNIFICANCE_BANDS = ("none", "low", "medium", "high", "critical")

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
        "probabilities",
        "probability",
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

_CATEGORY_BASE = {
    "relationship": 0.46,
    "pressure": 0.40,
    "memory": 0.30,
    "gravity": 0.28,
    "actor": 0.24,
}
_CATEGORY_ORDER = {
    "relationship": 0,
    "pressure": 1,
    "gravity": 2,
    "actor": 3,
    "memory": 4,
}
_EFFECT_BONUS = {
    "relationship_threshold_crossed": 0.20,
    "living_cast_relationship_threshold": 0.20,
    "pressure_spawned_event": 0.18,
    "pressure_escalated": 0.12,
    "pressure_reduced": 0.06,
    "pressure_resolved": 0.05,
    "memory_retrieved": 0.06,
    "gravity_keep_active": 0.06,
    "gravity_compress": 0.04,
    "gravity_archive": 0.03,
    "gravity_fade": 0.03,
    "actor_promoted": 0.08,
    "actor_demoted": 0.08,
    "actor_updated": 0.04,
    "actor_deferred": 0.03,
}


def _clean_text(value: Any, limit: int = MAX_SIGNIFICANCE_TEXT) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if not math.isfinite(value):
        return low
    return max(low, min(high, value))


def _safe_scalar(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        text = _clean_text(value)
        if _NARRATIVE_MARKERS.search(text):
            return None
        return text
    return None


def _bounded_str_list(
    values: Optional[Sequence[Any]],
    limit: int = MAX_SIGNIFICANCE_SOURCE_IDS,
) -> List[str]:
    out: List[str] = []
    for value in values or []:
        text = _clean_text(value)
        if _NARRATIVE_MARKERS.search(text):
            continue
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
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
            items = _bounded_str_list(raw)
            if items:
                out[key_text[:80]] = items
        else:
            scalar = _safe_scalar(raw)
            if scalar is not None and scalar != "":
                out[key_text[:80]] = scalar
        if len(out) >= MAX_SIGNIFICANCE_METADATA_KEYS:
            break
    return out


def _safe_context(context: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(context, Mapping):
        return {}
    allowed = (
        "run_seed",
        "turn_sequence",
        "actor_id",
        "actor_ids",
        "location_id",
        "location_ids",
        "faction_id",
        "faction_ids",
        "goal_id",
        "situation_id",
        "investigation_id",
        "information_id",
        "memory_id",
        "pressure_id",
        "scope",
        "max_entries",
    )
    out: Dict[str, Any] = {}
    for key in allowed:
        value = context.get(key)
        if isinstance(value, (list, tuple)):
            items = _bounded_str_list(value)
            if items:
                out[key] = items
        else:
            scalar = _safe_scalar(value)
            if scalar is not None and scalar != "":
                out[key] = scalar
    return out


def _scope_from_context(context: Mapping[str, Any]) -> Dict[str, str]:
    return {
        "actor_id": _clean_text(context.get("actor_id")),
        "location_id": _clean_text(context.get("location_id")),
        "faction_id": _clean_text(context.get("faction_id")),
    }


def _stable_id(*parts: Any) -> str:
    material = json.dumps([_clean_text(part, 240) for part in parts], sort_keys=True)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"sig-{digest[:16]}"


def _band(score: float) -> str:
    if score >= 0.80:
        return "critical"
    if score >= 0.60:
        return "high"
    if score >= 0.35:
        return "medium"
    if score > 0.0:
        return "low"
    return "none"


def _reason_append(codes: List[str], code: str) -> None:
    if code and code not in codes and len(codes) < MAX_SIGNIFICANCE_REASON_CODES:
        codes.append(code)


def _source_context_ids(context: Mapping[str, Any]) -> List[str]:
    values: List[Any] = []
    for key in (
        "actor_id",
        "location_id",
        "faction_id",
        "goal_id",
        "situation_id",
        "investigation_id",
        "information_id",
        "memory_id",
        "pressure_id",
    ):
        values.append(context.get(key))
    for key in ("actor_ids", "location_ids", "faction_ids"):
        raw = context.get(key)
        if isinstance(raw, list):
            values.extend(raw)
    return _bounded_str_list(values, limit=32)


def _context_list(context: Mapping[str, Any], key: str) -> List[Any]:
    raw = context.get(key)
    if isinstance(raw, list):
        return list(raw)
    if raw:
        return [raw]
    return []


def _context_score(
    entry: Mapping[str, Any],
    context: Mapping[str, Any],
    reason_codes: List[str],
) -> float:
    if not context:
        return 0.0
    score = 0.0
    affected_id = _clean_text(entry.get("affected_entity_id"))
    affected_type = _clean_text(entry.get("affected_entity_type"))
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}

    actor_ids = set(_bounded_str_list([context.get("actor_id")] + _context_list(context, "actor_ids"), 32))
    location_ids = set(
        _bounded_str_list([context.get("location_id")] + _context_list(context, "location_ids"), 32)
    )
    faction_ids = set(
        _bounded_str_list([context.get("faction_id")] + _context_list(context, "faction_ids"), 32)
    )

    if affected_id and affected_type in {"actor", "npc"} and affected_id in actor_ids:
        score += 0.20
        _reason_append(reason_codes, "affected_actor_matches_scope")
    if affected_id and affected_type == "location" and affected_id in location_ids:
        score += 0.18
        _reason_append(reason_codes, "affected_location_matches_scope")
    if affected_id and affected_type == "faction" and affected_id in faction_ids:
        score += 0.18
        _reason_append(reason_codes, "affected_faction_matches_scope")

    meta_actor_ids = set(_bounded_str_list(metadata.get("affected_actor_ids") or [], 32))
    meta_location_ids = set(_bounded_str_list(metadata.get("affected_location_ids") or [], 32))
    meta_faction_ids = set(_bounded_str_list(metadata.get("affected_faction_ids") or [], 32))
    if actor_ids and actor_ids.intersection(meta_actor_ids):
        score += 0.16
        _reason_append(reason_codes, "metadata_actor_matches_scope")
    if location_ids and location_ids.intersection(meta_location_ids):
        score += 0.14
        _reason_append(reason_codes, "metadata_location_matches_scope")
    if faction_ids and faction_ids.intersection(meta_faction_ids):
        score += 0.14
        _reason_append(reason_codes, "metadata_faction_matches_scope")

    context_ids = set(_source_context_ids(context))
    source_ids = set(_bounded_str_list(entry.get("source_ids") or [], 32))
    if context_ids and source_ids.intersection(context_ids):
        score += 0.10
        _reason_append(reason_codes, "source_id_matches_scope")
    return score


def _recency_score(
    entry: Mapping[str, Any],
    context: Mapping[str, Any],
    reason_codes: List[str],
) -> float:
    if "turn_sequence" not in context:
        return 0.0
    current_turn = _coerce_int(context.get("turn_sequence"))
    entry_turn = _coerce_int(entry.get("turn"))
    if current_turn <= 0 or entry_turn <= 0:
        return 0.0
    age = current_turn - entry_turn
    if age < 0:
        return 0.0
    if age == 0:
        _reason_append(reason_codes, "same_turn")
        return 0.12
    if age <= 2:
        _reason_append(reason_codes, "recent_turn")
        return 0.06
    if age >= 8:
        _reason_append(reason_codes, "older_context")
        return -0.06
    return 0.0


def _delta_score(delta: Mapping[str, Any], reason_codes: List[str]) -> float:
    score = 0.0
    if "magnitude" in delta:
        magnitude = abs(_coerce_float(delta.get("magnitude")))
        if magnitude:
            score += min(0.18, magnitude / 100.0 * 0.30)
            _reason_append(reason_codes, "magnitude_delta")
    if delta.get("state"):
        score += 0.12
        _reason_append(reason_codes, "state_transition")
    selected = _coerce_int(delta.get("selected_memory_count"), 0)
    if selected > 0:
        score += min(0.08, selected * 0.03)
        _reason_append(reason_codes, "memory_selected")
    if delta.get("transition"):
        score += 0.04
        _reason_append(reason_codes, "projection_transition")
    return score


def _score_entry(
    entry: Mapping[str, Any],
    context: Mapping[str, Any],
) -> Tuple[float, List[str]]:
    reason_codes: List[str] = []
    category = _clean_text(entry.get("effect_category"))
    effect_type = _clean_text(entry.get("effect_type"))
    score = _CATEGORY_BASE.get(category, 0.10)
    if category in _CATEGORY_BASE:
        _reason_append(reason_codes, f"category_{category}")
    score += _EFFECT_BONUS.get(effect_type, 0.0)
    if effect_type in _EFFECT_BONUS:
        _reason_append(reason_codes, f"effect_{effect_type}")
    delta = entry.get("delta") if isinstance(entry.get("delta"), Mapping) else {}
    score += _delta_score(delta, reason_codes)
    score += _context_score(entry, context, reason_codes)
    score += _recency_score(entry, context, reason_codes)
    return round(_clamp(score), 6), reason_codes


def _entry_sort_key(entry: Mapping[str, Any]) -> tuple:
    return (
        -_coerce_float(entry.get("significance_score")),
        _coerce_int(entry.get("turn")),
        _CATEGORY_ORDER.get(str(entry.get("effect_category") or ""), 99),
        str(entry.get("affected_entity_type") or ""),
        str(entry.get("affected_entity_id") or ""),
        str((entry.get("source_causal_entry_ids") or [""])[0]),
        str(entry.get("entry_id") or ""),
    )


def _normalise_entry(
    raw: Mapping[str, Any],
    context: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, Mapping):
        return None
    causal_entry_id = _clean_text(raw.get("entry_id"), 160)
    affected_entity_type = _clean_text(raw.get("affected_entity_type"), 80)
    affected_entity_id = _clean_text(raw.get("affected_entity_id"), 160)
    effect_category = _clean_text(raw.get("effect_category"), 80)
    if not causal_entry_id or not affected_entity_type or not effect_category:
        return None

    score, reason_codes = _score_entry(raw, context)
    source_ids = _bounded_str_list(raw.get("source_ids") or [])
    metadata = _safe_metadata(raw.get("metadata") or {})
    entry_id = _stable_id(
        causal_entry_id,
        affected_entity_type,
        affected_entity_id,
        effect_category,
        score,
        ",".join(source_ids),
    )
    return {
        "entry_id": entry_id,
        "turn": _coerce_int(raw.get("turn")),
        "source_causal_entry_ids": [causal_entry_id],
        "source_ids": source_ids,
        "affected_entity_type": affected_entity_type,
        "affected_entity_id": affected_entity_id,
        "effect_category": effect_category,
        "significance_band": _band(score),
        "significance_score": score,
        "reason_codes": reason_codes,
        "metadata": metadata,
    }


def project_significance(
    causal_entries: Sequence[Mapping[str, Any]],
    context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Derive bounded current-importance records from causal visibility entries.

    This function is pure and passive. It reads only supplied causal entries and
    explicit context, and it returns a projection without mutating inputs.
    """
    safe_context = _safe_context(context)
    try:
        max_entries = int(safe_context.get("max_entries") or MAX_SIGNIFICANCE_ENTRIES)
    except (TypeError, ValueError):
        max_entries = MAX_SIGNIFICANCE_ENTRIES
    max_entries = max(0, min(max_entries, MAX_SIGNIFICANCE_ENTRIES))

    if not isinstance(causal_entries, Sequence) or isinstance(causal_entries, (str, bytes)):
        raw_entries: Sequence[Mapping[str, Any]] = []
    else:
        raw_entries = causal_entries

    entries: List[Dict[str, Any]] = []
    seen_causal_ids = set()
    for raw in raw_entries:
        entry = _normalise_entry(raw, safe_context)
        if not entry:
            continue
        causal_id = entry["source_causal_entry_ids"][0]
        if causal_id in seen_causal_ids:
            continue
        seen_causal_ids.add(causal_id)
        entries.append(entry)

    ordered = sorted(entries, key=_entry_sort_key)
    truncated = len(ordered) > max_entries
    visible = ordered[:max_entries] if max_entries else []
    turn = _coerce_int(safe_context.get("turn_sequence"))
    if turn <= 0 and visible:
        turn = max(_coerce_int(entry.get("turn")) for entry in visible)

    return {
        "schema_version": SIGNIFICANCE_PROJECTION_SCHEMA_VERSION,
        "source_visibility_schema_version": SIGNIFICANCE_SOURCE_VISIBILITY_SCHEMA_VERSION,
        "turn": turn,
        "scope": _scope_from_context(safe_context),
        "entries": visible,
        "entry_count": len(visible),
        "max_entries": max_entries,
        "truncated": truncated,
    }
