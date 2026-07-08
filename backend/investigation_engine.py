"""
Deterministic Investigation & Evidence Engine.

Investigations and evidence are engine-owned canonical state. Narration may
describe discovered facts, but it never creates proof, solves cases, alters
confidence, or owns truth.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

INVESTIGATION_ENGINE_VERSION = 1

MAX_EVIDENCE = 3
MAX_INVESTIGATIONS = 3
MAX_ACTIVE_INVESTIGATIONS = 4
MAX_INVESTIGATION_INPUTS_PER_TICK = 8
MAX_INVESTIGATION_CHANGES_PER_TICK = 5
MAX_INVESTIGATION_RECEIPTS = 2
MAX_INVESTIGATION_REFS = 6
MAX_EVIDENCE_REFS = 6
MAX_EVIDENCE_TAGS = 6
MAX_PROJECTED_INVESTIGATIONS = 4
MAX_PROMPT_INVESTIGATIONS = 3
MAX_CONTEXT_INVESTIGATIONS = 3
MAX_CONTEXT_EVIDENCE = 4
MAX_EVIDENCE_EXPOSURE_SIGNALS = 6
MIN_EVIDENCE_EXPOSURE_CONFIDENCE = 40
PUBLIC_EVIDENCE_VISIBILITY_SCOPES = frozenset({"settlement", "faction", "public", "witnessed"})

EVIDENCE_EXPOSURE_BRIDGE_VERSION = 1

EVIDENCE_EXPOSURE_KINDS = (
    "implicated_private",
    "implicated_public",
    "investigating",
    "accused_pressure",
)

EVIDENCE_EXPOSURE_BEHAVIOURS = {
    "implicated_private": ("hide", "flee", "bribe"),
    "implicated_public": ("flee", "retaliate", "bribe", "confess"),
    "investigating": ("investigate", "accuse", "warn", "cooperate"),
    "accused_pressure": ("retaliate", "accuse", "bribe", "hide"),
}

STALL_AFTER_INACTIVE_TURNS = 6
FAIL_AFTER_INACTIVE_TURNS = 14
ARCHIVE_AFTER_TERMINAL_TURNS = 8

INVESTIGATION_STATUSES = ("open", "active", "stalled", "closed", "failed", "archived")
TERMINAL_STATUSES = frozenset({"closed", "failed", "archived"})

EVIDENCE_TYPES = frozenset(
    {"trace", "witness_statement", "physical_clue", "lead", "pattern", "absence"}
)

CASE_WORLD_EVENT_TYPES = frozenset(
    {"investigation", "search_operation", "bandit_activity", "political_unrest"}
)
CASE_SITUATION_TYPES = frozenset(
    {"murder_investigation", "missing_child", "search_party", "gang_turf_war", "political_unrest"}
)
CLUE_EVENT_KINDS = frozenset({"npc_found_clue", "npc_failed_search"})

INVESTIGATION_RECEIPT_TYPES = (
    "investigation_created",
    "investigation_reinforced",
    "investigation_progressed",
    "investigation_closed",
    "investigation_failed",
    "investigation_archived",
    "evidence_created",
    "evidence_reinforced",
)

PROMPT_INVESTIGATION_FIELDS = frozenset(
    {"status", "priority", "confidence", "known_evidence_count", "case_status", "progress"}
)


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


def _bounded_str_list(values: Any, limit: int = MAX_INVESTIGATION_REFS) -> List[str]:
    out: List[str] = []
    raw = values if isinstance(values, (list, tuple, set)) else [values]
    for value in raw or []:
        text = _bounded_str(value)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _normalise_status(value: Any, confidence: int = 0, archived: bool = False) -> str:
    status = _bounded_str(value, 40).lower()
    if archived:
        return "archived"
    if status in INVESTIGATION_STATUSES:
        return status
    if confidence >= 85:
        return "closed"
    return "active" if confidence > 0 else "open"


def _normalise_evidence_type(value: Any) -> str:
    evidence_type = _bounded_str(value, 80).lower()
    return evidence_type if evidence_type in EVIDENCE_TYPES else "lead"


def _investigation_id(run_seed: str, source_kind: str, source_id: str) -> str:
    return _stable_id("investigation", run_seed, source_kind, source_id)


def _evidence_id(run_seed: str, source_kind: str, source_id: str, evidence_type: str) -> str:
    return _stable_id("evidence", run_seed, source_kind, source_id, evidence_type)


def _normalise_evidence(row: Mapping[str, Any], *, run_seed: str = "") -> Dict[str, Any]:
    evidence_type = _normalise_evidence_type(row.get("evidence_type"))
    source_event_ids = _bounded_str_list(row.get("source_event_ids"), MAX_EVIDENCE_REFS)
    source_action_ids = _bounded_str_list(row.get("source_action_ids"), MAX_EVIDENCE_REFS)
    source_key = source_event_ids[0] if source_event_ids else source_action_ids[0] if source_action_ids else "evidence"
    discovered_turn = max(0, _coerce_int(row.get("discovered_turn"), 0))
    reliability = _clamp_int(row.get("reliability"), 0, 100, default=50)
    confidence = _clamp_int(row.get("confidence"), 0, 100, default=reliability)
    return {
        "evidence_id": _bounded_str(
            row.get("evidence_id")
            or _evidence_id(run_seed or "investigation-engine", "source", source_key, evidence_type),
            160,
        ),
        "evidence_type": evidence_type,
        "source_event_ids": source_event_ids,
        "source_action_ids": source_action_ids,
        "discovered_turn": discovered_turn,
        "discovered_by": _bounded_str_list(row.get("discovered_by"), MAX_INVESTIGATION_REFS),
        "location_id": _bounded_str(row.get("location_id"), 160),
        "actor_ids": _bounded_str_list(row.get("actor_ids"), MAX_INVESTIGATION_REFS),
        "reliability": reliability,
        "confidence": confidence,
        "related_case_ids": _bounded_str_list(row.get("related_case_ids"), MAX_INVESTIGATION_REFS),
        "related_evidence_ids": _bounded_str_list(row.get("related_evidence_ids"), MAX_EVIDENCE_REFS),
        "tags": _bounded_str_list(row.get("tags"), MAX_EVIDENCE_TAGS),
        "archived": bool(row.get("archived")),
    }


def _normalise_investigation(row: Mapping[str, Any], *, run_seed: str = "") -> Dict[str, Any]:
    world_event_id = _bounded_str(row.get("world_event_id"), 160)
    situation_id = _bounded_str(row.get("situation_id"), 160)
    source_kind = "world_event" if world_event_id else "situation" if situation_id else "case"
    source_id = world_event_id or situation_id or _bounded_str(row.get("investigation_id"), 160) or "case"
    created_turn = max(0, _coerce_int(row.get("created_turn"), 0))
    updated_turn = max(created_turn, _coerce_int(row.get("updated_turn"), created_turn))
    confidence = _clamp_int(row.get("confidence"), 0, 100, default=0)
    archived = bool(row.get("archived"))
    status = _normalise_status(row.get("status"), confidence, archived)
    solved = bool(row.get("solved")) or status == "closed"
    return {
        "investigation_id": _bounded_str(
            row.get("investigation_id")
            or _investigation_id(run_seed or "investigation-engine", source_kind, source_id),
            160,
        ),
        "world_event_id": world_event_id,
        "situation_id": situation_id,
        "status": status,
        "priority": _clamp_int(row.get("priority"), 0, 10, default=5),
        "assigned_actor_ids": _bounded_str_list(row.get("assigned_actor_ids"), MAX_INVESTIGATION_REFS),
        "suspect_ids": _bounded_str_list(row.get("suspect_ids"), MAX_INVESTIGATION_REFS),
        "evidence_ids": _bounded_str_list(row.get("evidence_ids"), MAX_INVESTIGATION_REFS),
        "confidence": confidence,
        "progress": _clamp_int(row.get("progress"), 0, 100, default=0),
        "created_turn": created_turn,
        "updated_turn": updated_turn,
        "solved": solved,
        "archived": archived or status == "archived",
    }


def _summary(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key: row.get(key)
        for key in ("status", "confidence", "progress", "solved", "archived")
        if row.get(key) is not None
    }


def _summary_change(before: Mapping[str, Any], after: Mapping[str, Any]) -> Dict[str, List[Any]]:
    change: Dict[str, List[Any]] = {}
    for key in sorted(set(before) | set(after)):
        before_value = before.get(key)
        after_value = after.get(key)
        if before_value != after_value:
            change[key] = [before_value, after_value]
    return change


def _receipt_id(
    receipt_type: str,
    *,
    turn_number: int,
    investigation_id: str,
    detail: str = "",
    source_ids: Optional[Sequence[str]] = None,
) -> str:
    sources = ",".join(sorted(_bounded_str_list(source_ids or [], MAX_INVESTIGATION_REFS)))
    return _stable_id("investigation-receipt", receipt_type, turn_number, investigation_id, detail, sources)


def _append_receipt(
    replayability_state: Dict[str, Any],
    local_receipts: List[Dict[str, Any]],
    *,
    receipt_type: str,
    turn_number: int,
    investigation: Mapping[str, Any],
    before: Optional[Mapping[str, Any]] = None,
    after: Optional[Mapping[str, Any]] = None,
    detail: str = "",
    source_ids: Optional[Sequence[str]] = None,
) -> bool:
    if receipt_type not in INVESTIGATION_RECEIPT_TYPES:
        return False
    investigation_id = _bounded_str(investigation.get("investigation_id"), 160)
    if not investigation_id:
        return False
    rid = _receipt_id(
        receipt_type,
        turn_number=turn_number,
        investigation_id=investigation_id,
        detail=detail,
        source_ids=source_ids,
    )
    receipts = replayability_state.setdefault("investigation_receipts", [])
    if any(isinstance(row, Mapping) and row.get("receipt_id") == rid for row in receipts):
        return False
    receipt: Dict[str, Any] = {
        "version": INVESTIGATION_ENGINE_VERSION,
        "receipt_id": rid,
        "receipt_type": receipt_type,
        "turn": turn_number,
        "investigation_id": investigation_id,
        "status": investigation.get("status"),
        "detail": _bounded_str(detail, 120),
    }
    change = _summary_change(_summary(before or {}), _summary(after or investigation))
    if change:
        receipt["change"] = change
    source_event_ids = _bounded_str_list(source_ids or [], MAX_INVESTIGATION_REFS)
    if source_event_ids:
        receipt["source_event_ids"] = source_event_ids
    receipts.append(receipt)
    if len(receipts) > MAX_INVESTIGATION_RECEIPTS:
        replayability_state["investigation_receipts"] = receipts[-MAX_INVESTIGATION_RECEIPTS:]
    local_receipts.append(receipt)
    return True


def _merge_unique(existing: Dict[str, Any], incoming: Mapping[str, Any], key: str, limit: int) -> bool:
    before = list(existing.get(key) or [])
    merged = _bounded_str_list(before + list(incoming.get(key) or []), limit)
    existing[key] = merged
    return merged != before


def _merge_investigation(existing: Dict[str, Any], candidate: Mapping[str, Any], turn_number: int) -> bool:
    changed = False
    for key in ("assigned_actor_ids", "suspect_ids", "evidence_ids"):
        changed = _merge_unique(existing, candidate, key, MAX_INVESTIGATION_REFS) or changed
    for key in ("world_event_id", "situation_id"):
        if not existing.get(key) and candidate.get(key):
            existing[key] = candidate.get(key)
            changed = True
    priority = max(_clamp_int(existing.get("priority"), 0, 10), _clamp_int(candidate.get("priority"), 0, 10))
    if priority != existing.get("priority"):
        existing["priority"] = priority
        changed = True
    confidence = max(_clamp_int(existing.get("confidence"), 0, 100), _clamp_int(candidate.get("confidence"), 0, 100))
    if confidence != existing.get("confidence"):
        existing["confidence"] = confidence
        changed = True
    if existing.get("status") == "open" and confidence > 0:
        existing["status"] = "active"
        changed = True
    if changed:
        existing["updated_turn"] = turn_number
    return changed


def _world_event_candidate(
    world_event: Mapping[str, Any],
    *,
    turn_number: int,
    run_seed: str,
) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    if str(world_event.get("status") or "") in {"resolved", "failed", "archived"}:
        return None
    event_type = _bounded_str(world_event.get("event_type"), 80)
    if event_type not in CASE_WORLD_EVENT_TYPES:
        return None
    world_event_id = _bounded_str(world_event.get("world_event_id"), 160)
    if not world_event_id:
        return None
    severity = _clamp_int(world_event.get("severity"), 0, 10, default=4)
    actors = _bounded_str_list(world_event.get("affected_actor_ids"), MAX_INVESTIGATION_REFS)
    if not actors:
        return None
    locations = _bounded_str_list(world_event.get("affected_locations"), MAX_INVESTIGATION_REFS)
    evidence_type = "lead" if event_type in {"investigation", "search_operation"} else "pattern"
    investigation_id = _investigation_id(run_seed, "world_event", world_event_id)
    reliability = min(95, 45 + severity * 5)
    confidence = min(90, 30 + severity * 5)
    evidence_id = _evidence_id(run_seed, "world_event", world_event_id, evidence_type)
    investigation = _normalise_investigation(
        {
            "investigation_id": investigation_id,
            "world_event_id": world_event_id,
            "status": "active",
            "priority": max(4, severity),
            "assigned_actor_ids": actors[:2],
            "suspect_ids": actors[2:4] if event_type in {"bandit_activity", "political_unrest"} else [],
            "evidence_ids": [evidence_id],
            "confidence": confidence,
            "progress": min(80, 15 + severity * 4),
            "created_turn": turn_number,
            "updated_turn": turn_number,
        },
        run_seed=run_seed,
    )
    evidence = _normalise_evidence(
        {
            "evidence_id": evidence_id,
            "evidence_type": evidence_type,
            "source_event_ids": [world_event_id] + list(world_event.get("source_event_ids") or []),
            "source_action_ids": [],
            "discovered_turn": turn_number,
            "discovered_by": actors[:2],
            "location_id": locations[0] if locations else "",
            "actor_ids": actors,
            "reliability": reliability,
            "confidence": confidence,
            "related_case_ids": [investigation_id],
            "related_evidence_ids": [],
            "tags": ["world_event", event_type],
            "archived": False,
        },
        run_seed=run_seed,
    )
    return investigation, evidence


def _situation_candidate(
    situation: Mapping[str, Any],
    *,
    turn_number: int,
    run_seed: str,
) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    if str(situation.get("status") or "") in {"resolved", "failed", "archived"}:
        return None
    situation_type = _bounded_str(situation.get("type"), 80)
    if situation_type not in CASE_SITUATION_TYPES:
        return None
    situation_id = _bounded_str(situation.get("situation_id"), 160)
    if not situation_id:
        return None
    severity = _clamp_int(situation.get("severity"), 0, 10, default=4)
    actors = _bounded_str_list(situation.get("involved_actor_ids"), MAX_INVESTIGATION_REFS)
    if not actors:
        return None
    locations = _bounded_str_list(situation.get("involved_locations"), MAX_INVESTIGATION_REFS)
    investigation_id = _investigation_id(run_seed, "situation", situation_id)
    evidence_id = _evidence_id(run_seed, "situation", situation_id, "witness_statement")
    confidence = min(85, 35 + severity * 4)
    investigation = _normalise_investigation(
        {
            "investigation_id": investigation_id,
            "situation_id": situation_id,
            "status": "active",
            "priority": max(4, _clamp_int(situation.get("priority"), 0, 10, default=severity)),
            "assigned_actor_ids": actors[:2],
            "suspect_ids": actors[2:4] if situation_type in {"murder_investigation", "gang_turf_war"} else [],
            "evidence_ids": [evidence_id],
            "confidence": confidence,
            "progress": min(75, 20 + severity * 3),
            "created_turn": turn_number,
            "updated_turn": turn_number,
        },
        run_seed=run_seed,
    )
    evidence = _normalise_evidence(
        {
            "evidence_id": evidence_id,
            "evidence_type": "witness_statement",
            "source_event_ids": [situation_id] + list(situation.get("source_event_ids") or []),
            "source_action_ids": [],
            "discovered_turn": turn_number,
            "discovered_by": actors[:2],
            "location_id": locations[0] if locations else "",
            "actor_ids": actors,
            "reliability": min(90, 45 + severity * 4),
            "confidence": confidence,
            "related_case_ids": [investigation_id],
            "related_evidence_ids": [],
            "tags": ["situation", situation_type],
            "archived": False,
        },
        run_seed=run_seed,
    )
    return investigation, evidence


def _matching_investigation_for_action(
    action_event: Mapping[str, Any],
    investigations: Sequence[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    situation_id = _bounded_str(action_event.get("situation_id"), 160)
    goal_id = _bounded_str(action_event.get("goal_id"), 160)
    actors = set(_bounded_str_list(action_event.get("actor_ids"), MAX_INVESTIGATION_REFS))
    locations = set(_bounded_str_list(action_event.get("location_ids"), MAX_INVESTIGATION_REFS))
    candidates: List[Dict[str, Any]] = []
    for row in investigations:
        if row.get("status") in TERMINAL_STATUSES or row.get("archived"):
            continue
        inv = dict(row)
        if situation_id and inv.get("situation_id") == situation_id:
            return inv
        assigned = set(_bounded_str_list(inv.get("assigned_actor_ids"), MAX_INVESTIGATION_REFS))
        if actors and assigned.intersection(actors):
            candidates.append(inv)
            continue
        if goal_id and goal_id in set(_bounded_str_list(inv.get("evidence_ids"), MAX_INVESTIGATION_REFS)):
            candidates.append(inv)
            continue
        inv_locs = set()
        for value in inv.get("evidence_locations") or []:
            if value:
                inv_locs.add(str(value))
        if locations and inv_locs.intersection(locations):
            candidates.append(inv)
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            -_clamp_int(row.get("priority"), 0, 10),
            -_clamp_int(row.get("confidence"), 0, 100),
            str(row.get("investigation_id") or ""),
        )
    )
    return candidates[0]


def _action_evidence_candidate(
    action_event: Mapping[str, Any],
    investigations: Sequence[Mapping[str, Any]],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    *,
    turn_number: int,
    run_seed: str,
) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    if str(action_event.get("event_type") or "") != "npc_action_event":
        return None
    event_kind = _bounded_str(action_event.get("event_kind"), 80)
    tags = {str(tag or "").lower() for tag in action_event.get("tags") or []}
    if event_kind not in CLUE_EVENT_KINDS and not tags.intersection({"search", "investigate"}):
        return None
    event_id = _bounded_str(action_event.get("event_id"), 160)
    action_id = _bounded_str(action_event.get("action_id"), 160)
    if not event_id or not action_id:
        return None
    target = _matching_investigation_for_action(action_event, investigations)
    if not target:
        return None
    investigation_id = _bounded_str(target.get("investigation_id"), 160)
    actors = _bounded_str_list(action_event.get("actor_ids"), MAX_INVESTIGATION_REFS)
    locations = _bounded_str_list(action_event.get("location_ids"), MAX_INVESTIGATION_REFS)
    existing_case_evidence = [
        evidence_by_id[eid]
        for eid in target.get("evidence_ids") or []
        if eid in evidence_by_id
    ]
    related_evidence = [
        str(row.get("evidence_id") or "")
        for row in existing_case_evidence[-MAX_EVIDENCE_REFS:]
        if row.get("evidence_id")
    ]
    confidence = min(90, 55 + _clamp_int(action_event.get("magnitude"), 0, 100) // 10)
    evidence_id = _evidence_id(run_seed, "action", action_id, "physical_clue")
    evidence = _normalise_evidence(
        {
            "evidence_id": evidence_id,
            "evidence_type": "physical_clue",
            "source_event_ids": [event_id],
            "source_action_ids": [action_id],
            "discovered_turn": turn_number,
            "discovered_by": actors,
            "location_id": locations[0] if locations else "",
            "actor_ids": actors,
            "reliability": min(95, confidence + 5),
            "confidence": confidence,
            "related_case_ids": [investigation_id],
            "related_evidence_ids": related_evidence,
            "tags": ["npc_action", event_kind or "investigation"],
            "archived": False,
        },
        run_seed=run_seed,
    )
    investigation = dict(target)
    investigation["evidence_ids"] = _bounded_str_list(
        list(investigation.get("evidence_ids") or []) + [evidence_id],
        MAX_INVESTIGATION_REFS,
    )
    investigation["assigned_actor_ids"] = _bounded_str_list(
        list(investigation.get("assigned_actor_ids") or []) + actors,
        MAX_INVESTIGATION_REFS,
    )
    investigation["confidence"] = max(_clamp_int(investigation.get("confidence"), 0, 100), confidence)
    investigation["updated_turn"] = turn_number
    return _normalise_investigation(investigation, run_seed=run_seed), evidence


def _add_or_reinforce_evidence(
    evidence: List[Dict[str, Any]],
    evidence_by_id: Dict[str, Dict[str, Any]],
    candidate: Mapping[str, Any],
    *,
    turn_number: int,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    evidence_id = _bounded_str(candidate.get("evidence_id"), 160)
    if not evidence_id:
        return None, False
    existing = evidence_by_id.get(evidence_id)
    if existing is None:
        if len(evidence) >= MAX_EVIDENCE:
            return None, False
        row = _normalise_evidence(candidate)
        evidence.append(row)
        evidence_by_id[evidence_id] = row
        return row, True
    changed = False
    for key, limit in (
        ("source_event_ids", MAX_EVIDENCE_REFS),
        ("source_action_ids", MAX_EVIDENCE_REFS),
        ("discovered_by", MAX_INVESTIGATION_REFS),
        ("actor_ids", MAX_INVESTIGATION_REFS),
        ("related_case_ids", MAX_INVESTIGATION_REFS),
        ("related_evidence_ids", MAX_EVIDENCE_REFS),
        ("tags", MAX_EVIDENCE_TAGS),
    ):
        changed = _merge_unique(existing, candidate, key, limit) or changed
    for key in ("reliability", "confidence"):
        value = max(_clamp_int(existing.get(key), 0, 100), _clamp_int(candidate.get(key), 0, 100))
        if value != existing.get(key):
            existing[key] = value
            changed = True
    if not existing.get("location_id") and candidate.get("location_id"):
        existing["location_id"] = _bounded_str(candidate.get("location_id"), 160)
        changed = True
    if existing.get("archived") and not candidate.get("archived"):
        existing["archived"] = False
        changed = True
    if changed and not existing.get("discovered_turn"):
        existing["discovered_turn"] = turn_number
    return existing if changed else None, False


def _progress_investigation(
    investigation: Dict[str, Any],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    *,
    turn_number: int,
) -> Optional[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    if investigation.get("status") == "archived" or investigation.get("archived"):
        return None
    before = copy.deepcopy(investigation)
    receipt_type = ""
    case_evidence = [
        evidence_by_id[eid]
        for eid in investigation.get("evidence_ids") or []
        if eid in evidence_by_id and not evidence_by_id[eid].get("archived")
    ]
    if case_evidence:
        avg_confidence = sum(_clamp_int(row.get("confidence"), 0, 100) for row in case_evidence) // len(case_evidence)
        max_confidence = max(_clamp_int(row.get("confidence"), 0, 100) for row in case_evidence)
        confidence = min(100, max(max_confidence, avg_confidence + (len(case_evidence) - 1) * 10))
        progress = min(100, max(_clamp_int(investigation.get("progress"), 0, 100), 20 + len(case_evidence) * 20 + confidence // 4))
        if confidence != investigation.get("confidence"):
            investigation["confidence"] = confidence
        if progress != investigation.get("progress"):
            investigation["progress"] = progress
        if investigation.get("status") in {"open", "stalled"}:
            investigation["status"] = "active"
        if confidence >= 85 and len(case_evidence) >= 2:
            investigation["status"] = "closed"
            investigation["progress"] = 100
            investigation["solved"] = True
            receipt_type = "investigation_closed"
    inactive = turn_number - _coerce_int(before.get("updated_turn"), turn_number)
    if not receipt_type and investigation.get("status") not in TERMINAL_STATUSES:
        if inactive >= FAIL_AFTER_INACTIVE_TURNS and _clamp_int(investigation.get("confidence"), 0, 100) < 70:
            investigation["status"] = "failed"
            investigation["solved"] = False
            receipt_type = "investigation_failed"
        elif inactive >= STALL_AFTER_INACTIVE_TURNS and investigation.get("status") == "active":
            investigation["status"] = "stalled"
            receipt_type = "investigation_progressed"
    if not receipt_type and investigation.get("status") in {"closed", "failed"}:
        if inactive >= ARCHIVE_AFTER_TERMINAL_TURNS:
            investigation["status"] = "archived"
            investigation["archived"] = True
            receipt_type = "investigation_archived"
    if before != investigation:
        investigation["updated_turn"] = turn_number
        return receipt_type or "investigation_progressed", before, copy.deepcopy(investigation)
    return None


def _cap_evidence(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [_normalise_evidence(row) for row in evidence if isinstance(row, Mapping)]
    if len(rows) > MAX_EVIDENCE:
        rows = sorted(
            rows,
            key=lambda row: (
                1 if row.get("archived") else 0,
                -_clamp_int(row.get("confidence"), 0, 100),
                -_coerce_int(row.get("discovered_turn"), 0),
                str(row.get("evidence_id") or ""),
            ),
        )[:MAX_EVIDENCE]
    return sorted(rows, key=lambda row: (_coerce_int(row.get("discovered_turn"), 0), str(row.get("evidence_id") or "")))


def _cap_investigations(investigations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [_normalise_investigation(row) for row in investigations if isinstance(row, Mapping)]
    if len(rows) > MAX_INVESTIGATIONS:
        rows = sorted(
            rows,
            key=lambda row: (
                1 if row.get("status") in TERMINAL_STATUSES else 0,
                1 if row.get("archived") else 0,
                -_clamp_int(row.get("priority"), 0, 10),
                -_clamp_int(row.get("confidence"), 0, 100),
                -_coerce_int(row.get("updated_turn"), 0),
                str(row.get("investigation_id") or ""),
            ),
        )[:MAX_INVESTIGATIONS]
    return sorted(rows, key=lambda row: (_coerce_int(row.get("created_turn"), 0), str(row.get("investigation_id") or "")))


def evolve_investigations(
    replayability_state: Dict[str, Any],
    rolling_state: Mapping[str, Any],
    turn_number: int,
    *,
    run_seed: str = "",
) -> Dict[str, Any]:
    diagnostics = {
        "investigation_engine_executed": False,
        "investigation_candidates_evaluated": 0,
        "investigations_created": 0,
        "investigations_reinforced": 0,
        "investigations_progressed": 0,
        "investigations_closed": 0,
        "investigations_failed": 0,
        "investigations_archived": 0,
        "evidence_created": 0,
        "evidence_reinforced": 0,
        "evidence_duplicate_suppressed": 0,
        "investigation_duplicate_suppressed": 0,
    }
    if not isinstance(replayability_state, dict):
        return {"receipts": [], "diagnostics": diagnostics}

    seed = run_seed or str(replayability_state.get("run_seed") or "investigation-engine")
    evidence = [
        _normalise_evidence(row, run_seed=seed)
        for row in replayability_state.get("evidence") or []
        if isinstance(row, Mapping)
    ]
    investigations = [
        _normalise_investigation(row, run_seed=seed)
        for row in replayability_state.get("investigations") or []
        if isinstance(row, Mapping)
    ]
    replayability_state["evidence"] = evidence
    replayability_state["investigations"] = investigations
    replayability_state.setdefault("investigation_receipts", [])
    evidence_by_id = {str(row.get("evidence_id") or ""): row for row in evidence if row.get("evidence_id")}
    investigations_by_id = {
        str(row.get("investigation_id") or ""): row
        for row in investigations
        if row.get("investigation_id")
    }
    local_receipts: List[Dict[str, Any]] = []
    remaining_changes = MAX_INVESTIGATION_CHANGES_PER_TICK

    candidates: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for world_event in sorted(
        [row for row in replayability_state.get("world_events") or [] if isinstance(row, Mapping)],
        key=lambda row: (-_clamp_int(row.get("severity"), 0, 10), str(row.get("world_event_id") or "")),
    ):
        if len(candidates) >= MAX_INVESTIGATION_INPUTS_PER_TICK:
            break
        candidate = _world_event_candidate(world_event, turn_number=turn_number, run_seed=seed)
        if candidate:
            candidates.append(candidate)
    for situation in sorted(
        [row for row in replayability_state.get("situations") or [] if isinstance(row, Mapping)],
        key=lambda row: (-_clamp_int(row.get("priority"), 0, 10), str(row.get("situation_id") or "")),
    ):
        if len(candidates) >= MAX_INVESTIGATION_INPUTS_PER_TICK:
            break
        candidate = _situation_candidate(situation, turn_number=turn_number, run_seed=seed)
        if candidate:
            candidates.append(candidate)

    seen_candidate_ids = set()
    for investigation_candidate, evidence_candidate in candidates:
        diagnostics["investigation_candidates_evaluated"] += 1
        investigation_id = str(investigation_candidate.get("investigation_id") or "")
        if not investigation_id:
            continue
        if investigation_id in seen_candidate_ids:
            diagnostics["investigation_duplicate_suppressed"] += 1
            continue
        seen_candidate_ids.add(investigation_id)
        existing = investigations_by_id.get(investigation_id)
        candidate_evidence_id = _bounded_str(evidence_candidate.get("evidence_id"), 160)
        evidence_missing = bool(candidate_evidence_id and candidate_evidence_id not in evidence_by_id)
        if (
            evidence_missing
            and remaining_changes < 2
            and (
                existing is None
                or candidate_evidence_id not in (existing.get("evidence_ids") or [])
            )
        ):
            diagnostics["investigation_duplicate_suppressed"] += 1
            continue
        if existing is None:
            if remaining_changes <= 0 or len(investigations) >= MAX_INVESTIGATIONS:
                diagnostics["investigation_duplicate_suppressed"] += 1
                continue
            investigations.append(investigation_candidate)
            investigations_by_id[investigation_id] = investigation_candidate
            _append_receipt(
                replayability_state,
                local_receipts,
                receipt_type="investigation_created",
                turn_number=turn_number,
                investigation=investigation_candidate,
                before={},
                after=investigation_candidate,
                detail="created_from_engine_source",
                source_ids=[investigation_candidate.get("world_event_id") or investigation_candidate.get("situation_id")],
            )
            diagnostics["investigations_created"] += 1
            remaining_changes -= 1
            existing = investigation_candidate
        else:
            before = copy.deepcopy(existing)
            if _merge_investigation(existing, investigation_candidate, turn_number):
                _append_receipt(
                    replayability_state,
                    local_receipts,
                    receipt_type="investigation_reinforced",
                    turn_number=turn_number,
                    investigation=existing,
                    before=before,
                    after=existing,
                    detail="reinforced_from_engine_source",
                    source_ids=[investigation_candidate.get("world_event_id") or investigation_candidate.get("situation_id")],
                )
                diagnostics["investigations_reinforced"] += 1
                remaining_changes = max(0, remaining_changes - 1)
            else:
                diagnostics["investigation_duplicate_suppressed"] += 1
        if remaining_changes <= 0:
            continue
        evidence_row, created = _add_or_reinforce_evidence(
            evidence,
            evidence_by_id,
            evidence_candidate,
            turn_number=turn_number,
        )
        if evidence_row is None:
            diagnostics["evidence_duplicate_suppressed"] += 1
            continue
        before_existing = copy.deepcopy(existing)
        _merge_unique(existing, {"evidence_ids": [evidence_row["evidence_id"]]}, "evidence_ids", MAX_INVESTIGATION_REFS)
        existing["updated_turn"] = turn_number
        if created:
            diagnostics["evidence_created"] += 1
            receipt_type = "evidence_created"
        else:
            diagnostics["evidence_reinforced"] += 1
            receipt_type = "evidence_reinforced"
        _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type=receipt_type,
            turn_number=turn_number,
            investigation=existing,
            before=before_existing,
            after=existing,
            detail=str(evidence_row.get("evidence_id") or "evidence"),
            source_ids=evidence_row.get("source_event_ids") or evidence_row.get("source_action_ids") or [],
        )
        remaining_changes -= 1

    action_candidates: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for event in sorted(
        [row for row in replayability_state.get("engine_world_events") or [] if isinstance(row, Mapping)],
        key=lambda row: (_coerce_int(row.get("turn"), 0), str(row.get("event_id") or "")),
    ):
        if len(action_candidates) >= MAX_INVESTIGATION_INPUTS_PER_TICK:
            break
        candidate = _action_evidence_candidate(
            event,
            investigations,
            evidence_by_id,
            turn_number=turn_number,
            run_seed=seed,
        )
        if candidate:
            action_candidates.append(candidate)
    for investigation_candidate, evidence_candidate in action_candidates:
        if remaining_changes <= 0:
            break
        diagnostics["investigation_candidates_evaluated"] += 1
        investigation_id = str(investigation_candidate.get("investigation_id") or "")
        existing = investigations_by_id.get(investigation_id)
        if existing is None:
            diagnostics["investigation_duplicate_suppressed"] += 1
            continue
        evidence_row, created = _add_or_reinforce_evidence(
            evidence,
            evidence_by_id,
            evidence_candidate,
            turn_number=turn_number,
        )
        if evidence_row is None:
            diagnostics["evidence_duplicate_suppressed"] += 1
            continue
        before = copy.deepcopy(existing)
        _merge_investigation(existing, investigation_candidate, turn_number)
        _merge_unique(existing, {"evidence_ids": [evidence_row["evidence_id"]]}, "evidence_ids", MAX_INVESTIGATION_REFS)
        receipt_type = "evidence_created" if created else "evidence_reinforced"
        diagnostics["evidence_created" if created else "evidence_reinforced"] += 1
        _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type=receipt_type,
            turn_number=turn_number,
            investigation=existing,
            before=before,
            after=existing,
            detail=str(evidence_row.get("evidence_id") or "evidence"),
            source_ids=evidence_row.get("source_event_ids") or evidence_row.get("source_action_ids") or [],
        )
        remaining_changes -= 1

    for investigation in sorted(
        investigations,
        key=lambda row: (-_clamp_int(row.get("priority"), 0, 10), str(row.get("investigation_id") or "")),
    ):
        if remaining_changes <= 0:
            break
        progressed = _progress_investigation(
            investigation,
            evidence_by_id,
            turn_number=turn_number,
        )
        if not progressed:
            continue
        receipt_type, before, after = progressed
        _append_receipt(
            replayability_state,
            local_receipts,
            receipt_type=receipt_type,
            turn_number=turn_number,
            investigation=investigation,
            before=before,
            after=after,
            detail="progressed_from_evidence_graph",
            source_ids=investigation.get("evidence_ids") or [],
        )
        if receipt_type == "investigation_closed":
            diagnostics["investigations_closed"] += 1
        elif receipt_type == "investigation_failed":
            diagnostics["investigations_failed"] += 1
        elif receipt_type == "investigation_archived":
            diagnostics["investigations_archived"] += 1
        else:
            diagnostics["investigations_progressed"] += 1
        remaining_changes -= 1

    archived_case_ids = {
        str(row.get("investigation_id") or "")
        for row in investigations
        if row.get("status") == "archived" or row.get("archived")
    }
    for row in evidence:
        case_ids = {str(cid) for cid in row.get("related_case_ids") or [] if cid}
        if case_ids and case_ids.issubset(archived_case_ids):
            row["archived"] = True

    capped_investigations = _cap_investigations(investigations)
    kept_case_ids = {
        str(row.get("investigation_id") or "")
        for row in capped_investigations
        if row.get("investigation_id")
    }
    kept_case_evidence_ids = {
        str(evidence_id)
        for row in capped_investigations
        for evidence_id in row.get("evidence_ids") or []
        if evidence_id
    }
    pruned_evidence = []
    for row in evidence:
        evidence_id = str(row.get("evidence_id") or "")
        related = [cid for cid in row.get("related_case_ids") or [] if cid in kept_case_ids]
        if evidence_id not in kept_case_evidence_ids and not related:
            continue
        row["related_case_ids"] = _bounded_str_list(related, MAX_INVESTIGATION_REFS)
        pruned_evidence.append(row)
    capped_evidence = _cap_evidence(pruned_evidence)
    kept_evidence_ids = {
        str(row.get("evidence_id") or "")
        for row in capped_evidence
        if row.get("evidence_id")
    }
    for row in capped_investigations:
        row["evidence_ids"] = _bounded_str_list(
            [eid for eid in row.get("evidence_ids") or [] if eid in kept_evidence_ids],
            MAX_INVESTIGATION_REFS,
        )
    replayability_state["evidence"] = capped_evidence
    replayability_state["investigations"] = capped_investigations
    diagnostics["investigation_engine_executed"] = bool(
        local_receipts or candidates or action_candidates or replayability_state["investigations"]
    )
    return {"receipts": local_receipts, "diagnostics": diagnostics}


def project_active_investigations_for_rolling(
    replayability_state: Mapping[str, Any],
    *,
    limit: int = MAX_PROJECTED_INVESTIGATIONS,
) -> List[Dict[str, Any]]:
    if not isinstance(replayability_state, Mapping):
        return []
    seed = str(replayability_state.get("run_seed") or "investigation-engine")
    investigations = [
        _normalise_investigation(row, run_seed=seed)
        for row in replayability_state.get("investigations") or []
        if isinstance(row, Mapping)
        and row.get("status") not in TERMINAL_STATUSES
        and not row.get("archived")
    ]
    ordered = sorted(
        investigations,
        key=lambda row: (
            -_clamp_int(row.get("priority"), 0, 10),
            -_clamp_int(row.get("confidence"), 0, 100),
            str(row.get("investigation_id") or ""),
        ),
    )[: max(0, min(MAX_PROJECTED_INVESTIGATIONS, int(limit or 0)))]
    return [
        {
            "status": row.get("status"),
            "priority": row.get("priority"),
            "confidence": row.get("confidence"),
            "known_evidence_count": len(row.get("evidence_ids") or []),
            "case_status": "solved" if row.get("solved") else row.get("status"),
            "progress": row.get("progress"),
        }
        for row in ordered
    ]


def project_investigations_for_prompt(replayability_state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return project_active_investigations_for_rolling(
        replayability_state,
        limit=MAX_PROMPT_INVESTIGATIONS,
    )


def prompt_safe_rolling_state(rolling_state: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(rolling_state, Mapping):
        return {}
    safe = copy.deepcopy(dict(rolling_state))
    for key in ("evidence", "investigations", "investigation_receipts"):
        safe.pop(key, None)
    rows = safe.get("active_investigations")
    if not isinstance(rows, list):
        return safe
    cleaned: List[Dict[str, Any]] = []
    for row in rows[:MAX_PROMPT_INVESTIGATIONS]:
        if not isinstance(row, Mapping):
            continue
        cleaned.append(
            {
                key: copy.deepcopy(row.get(key))
                for key in sorted(PROMPT_INVESTIGATION_FIELDS)
                if key in row
            }
        )
    safe["active_investigations"] = cleaned
    return safe


def copy_investigation_state(replayability_state: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(replayability_state, Mapping):
        return {"investigations": [], "evidence": []}
    seed = str(replayability_state.get("run_seed") or "investigation-engine")
    investigations = [
        _normalise_investigation(row, run_seed=seed)
        for row in replayability_state.get("investigations") or []
        if isinstance(row, Mapping)
    ]
    evidence = [
        _normalise_evidence(row, run_seed=seed)
        for row in replayability_state.get("evidence") or []
        if isinstance(row, Mapping)
    ]
    bounded_investigations = []
    for row in _cap_investigations(investigations):
        bounded_investigations.append(
            {
                "investigation_id": row.get("investigation_id"),
                "world_event_id": row.get("world_event_id"),
                "situation_id": row.get("situation_id"),
                "status": row.get("status"),
                "priority": row.get("priority"),
                "assigned_actor_ids": list(row.get("assigned_actor_ids") or [])[:MAX_INVESTIGATION_REFS],
                "suspect_ids": list(row.get("suspect_ids") or [])[:MAX_INVESTIGATION_REFS],
                "evidence_ids": list(row.get("evidence_ids") or [])[:MAX_INVESTIGATION_REFS],
                "confidence": row.get("confidence"),
                "progress": row.get("progress"),
                "created_turn": row.get("created_turn"),
                "updated_turn": row.get("updated_turn"),
                "solved": bool(row.get("solved")),
                "archived": bool(row.get("archived")),
            }
        )
    bounded_evidence = []
    for row in _cap_evidence(evidence):
        bounded_evidence.append(
            {
                "evidence_id": row.get("evidence_id"),
                "evidence_type": row.get("evidence_type"),
                "discovered_turn": row.get("discovered_turn"),
                "discovered_by": list(row.get("discovered_by") or [])[:MAX_INVESTIGATION_REFS],
                "location_id": row.get("location_id"),
                "actor_ids": list(row.get("actor_ids") or [])[:MAX_INVESTIGATION_REFS],
                "reliability": row.get("reliability"),
                "confidence": row.get("confidence"),
                "related_case_ids": list(row.get("related_case_ids") or [])[:MAX_INVESTIGATION_REFS],
                "related_evidence_ids": list(row.get("related_evidence_ids") or [])[:MAX_EVIDENCE_REFS],
                "tags": list(row.get("tags") or [])[:MAX_EVIDENCE_TAGS],
                "archived": bool(row.get("archived")),
            }
        )
    return {"investigations": bounded_investigations, "evidence": bounded_evidence}


def _token_set(*values: Any) -> set:
    out = set()
    for value in values:
        raw = value if isinstance(value, (list, tuple, set)) else [value]
        for item in raw:
            text = str(item or "").strip().lower()
            if text:
                out.add(text)
    return out


def _evidence_by_id(investigation_state: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(row.get("evidence_id") or ""): dict(row)
        for row in investigation_state.get("evidence") or []
        if isinstance(row, Mapping) and row.get("evidence_id")
    }


def active_investigations_for_context(
    investigation_state: Mapping[str, Any],
    *,
    actor_ids: Sequence[str] = (),
    location_ids: Sequence[str] = (),
    evidence_ids: Sequence[str] = (),
    investigation_ids: Sequence[str] = (),
    limit: int = MAX_CONTEXT_INVESTIGATIONS,
) -> List[Dict[str, Any]]:
    if not isinstance(investigation_state, Mapping):
        return []
    evidence_lookup = _evidence_by_id(investigation_state)
    context_actor = _token_set(actor_ids)
    context_location = _token_set(location_ids)
    context_evidence = _token_set(evidence_ids)
    context_case = _token_set(investigation_ids)
    matched: List[Dict[str, Any]] = []
    for raw in investigation_state.get("investigations") or []:
        if not isinstance(raw, Mapping):
            continue
        row = _normalise_investigation(raw)
        if row.get("status") in TERMINAL_STATUSES or row.get("archived"):
            continue
        case_id = _token_set(row.get("investigation_id"))
        evidence_refs = _token_set(row.get("evidence_ids"))
        assigned = _token_set(row.get("assigned_actor_ids"))
        evidence_locations = set()
        for evidence_id in row.get("evidence_ids") or []:
            evidence = evidence_lookup.get(str(evidence_id) or "")
            if evidence and evidence.get("location_id"):
                evidence_locations.add(str(evidence.get("location_id")).strip().lower())
        applies = (
            case_id.intersection(context_case)
            or evidence_refs.intersection(context_evidence)
            or assigned.intersection(context_actor)
        )
        if applies:
            matched.append(row)
    matched.sort(
        key=lambda row: (
            -_clamp_int(row.get("priority"), 0, 10),
            -_clamp_int(row.get("confidence"), 0, 100),
            str(row.get("investigation_id") or ""),
        )
    )
    return matched[: max(0, min(MAX_CONTEXT_INVESTIGATIONS, int(limit or 0)))]


def known_evidence_for_context(
    investigation_state: Mapping[str, Any],
    *,
    actor_ids: Sequence[str] = (),
    location_ids: Sequence[str] = (),
    evidence_ids: Sequence[str] = (),
    limit: int = MAX_CONTEXT_EVIDENCE,
) -> List[Dict[str, Any]]:
    if not isinstance(investigation_state, Mapping):
        return []
    context_actor = _token_set(actor_ids)
    context_location = _token_set(location_ids)
    context_evidence = _token_set(evidence_ids)
    matched: List[Dict[str, Any]] = []
    for raw in investigation_state.get("evidence") or []:
        if not isinstance(raw, Mapping):
            continue
        row = _normalise_evidence(raw)
        if row.get("archived"):
            continue
        applies = (
            _token_set(row.get("evidence_id")).intersection(context_evidence)
            or _token_set(row.get("discovered_by")).intersection(context_actor)
        )
        if applies:
            matched.append(row)
    matched.sort(
        key=lambda row: (
            -_clamp_int(row.get("confidence"), 0, 100),
            -_coerce_int(row.get("discovered_turn"), 0),
            str(row.get("evidence_id") or ""),
        )
    )
    return matched[: max(0, min(MAX_CONTEXT_EVIDENCE, int(limit or 0)))]


def _investigations_by_id(investigation_state: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for raw in investigation_state.get("investigations") or []:
        if not isinstance(raw, Mapping):
            continue
        row = _normalise_investigation(raw)
        investigation_id = _bounded_str(row.get("investigation_id"), 160)
        if investigation_id:
            out[investigation_id] = row
    return out


def _evidence_publicly_exposed(
    evidence_id: str,
    information_state: Optional[Mapping[str, Any]],
) -> bool:
    if not evidence_id or not isinstance(information_state, Mapping):
        return False
    for raw in information_state.get("information_items") or []:
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("information_type") or "") != "evidence_summary":
            continue
        if evidence_id not in _bounded_str_list(raw.get("source_event_ids"), MAX_EVIDENCE_REFS):
            continue
        if str(raw.get("visibility_scope") or "").lower() in PUBLIC_EVIDENCE_VISIBILITY_SCOPES:
            return True
    return False


def _append_exposure_signal(
    signals: List[Dict[str, Any]],
    *,
    exposure_kind: str,
    signal_id: str,
    evidence_id: str = "",
    investigation_id: str = "",
    actor_id: str = "",
    actor_role: str = "",
    confidence: int = 0,
    severity: int = 5,
    public: bool = False,
) -> None:
    if exposure_kind not in EVIDENCE_EXPOSURE_KINDS:
        return
    bounded_signal_id = _bounded_str(signal_id, 160)
    if any(
        row.get("exposure_kind") == exposure_kind and row.get("signal_id") == bounded_signal_id
        for row in signals
    ):
        return
    behaviours = EVIDENCE_EXPOSURE_BEHAVIOURS.get(exposure_kind, ())
    signals.append(
        {
            "exposure_kind": exposure_kind,
            "signal_id": bounded_signal_id,
            "evidence_id": _bounded_str(evidence_id, 160),
            "investigation_id": _bounded_str(investigation_id, 160),
            "actor_id": _bounded_str(actor_id, 120),
            "actor_role": _bounded_str(actor_role, 40),
            "behaviours": list(behaviours),
            "severity": max(1, min(10, int(severity))),
            "confidence": max(0, min(100, int(confidence))),
            "public": bool(public),
        }
    )


def evidence_exposure_signals_for_context(
    investigation_state: Mapping[str, Any],
    *,
    information_state: Optional[Mapping[str, Any]] = None,
    actor_ids: Sequence[str] = (),
    location_ids: Sequence[str] = (),
    limit: int = MAX_EVIDENCE_EXPOSURE_SIGNALS,
) -> List[Dict[str, Any]]:
    """Deterministic read-side projection of evidence exposure pressures for engine bridges."""
    if not isinstance(investigation_state, Mapping):
        return []
    context_actors = _token_set(actor_ids)
    context_locations = _token_set(location_ids)
    investigations = _investigations_by_id(investigation_state)
    signals: List[Dict[str, Any]] = []

    for raw in investigation_state.get("evidence") or []:
        if not isinstance(raw, Mapping):
            continue
        evidence = _normalise_evidence(raw)
        if evidence.get("archived"):
            continue
        evidence_id = _bounded_str(evidence.get("evidence_id"), 160)
        confidence = _clamp_int(evidence.get("confidence"), 0, 100, default=0)
        if not evidence_id or confidence < MIN_EVIDENCE_EXPOSURE_CONFIDENCE:
            continue
        location_id = _bounded_str(evidence.get("location_id"), 120)
        if context_locations and location_id and location_id.lower() not in context_locations:
            continue
        is_public = _evidence_publicly_exposed(evidence_id, information_state)
        related_cases = _bounded_str_list(evidence.get("related_case_ids"), MAX_INVESTIGATION_REFS)
        investigation_id = related_cases[0] if related_cases else ""
        severity = max(4, min(10, confidence // 10 + (2 if is_public else 0)))

        implicated = _token_set(evidence.get("actor_ids"))
        investigators = _token_set(evidence.get("discovered_by"))
        for actor in sorted(implicated):
            if context_actors and actor not in context_actors:
                continue
            exposure_kind = "implicated_public" if is_public else "implicated_private"
            _append_exposure_signal(
                signals,
                exposure_kind=exposure_kind,
                signal_id=f"{exposure_kind}:{evidence_id}:{actor}",
                evidence_id=evidence_id,
                investigation_id=investigation_id,
                actor_id=actor,
                actor_role="suspect",
                confidence=confidence,
                severity=severity,
                public=is_public,
            )
        for actor in sorted(investigators):
            if context_actors and actor not in context_actors:
                continue
            _append_exposure_signal(
                signals,
                exposure_kind="investigating",
                signal_id=f"investigating:{evidence_id}:{actor}",
                evidence_id=evidence_id,
                investigation_id=investigation_id,
                actor_id=actor,
                actor_role="investigator",
                confidence=confidence,
                severity=severity,
                public=is_public,
            )

    for investigation in investigations.values():
        if investigation.get("status") in TERMINAL_STATUSES or investigation.get("archived"):
            continue
        investigation_id = _bounded_str(investigation.get("investigation_id"), 160)
        confidence = _clamp_int(investigation.get("confidence"), 0, 100, default=0)
        if not investigation_id or confidence < MIN_EVIDENCE_EXPOSURE_CONFIDENCE:
            continue
        if not investigation.get("evidence_ids"):
            continue
        suspects = _token_set(investigation.get("suspect_ids"))
        for actor in sorted(suspects):
            if context_actors and actor not in context_actors:
                continue
            public = any(
                _evidence_publicly_exposed(str(eid), information_state)
                for eid in investigation.get("evidence_ids") or []
            )
            _append_exposure_signal(
                signals,
                exposure_kind="accused_pressure",
                signal_id=f"accused_pressure:{investigation_id}:{actor}",
                evidence_id=_bounded_str((investigation.get("evidence_ids") or [""])[0], 160),
                investigation_id=investigation_id,
                actor_id=actor,
                actor_role="suspect",
                confidence=confidence,
                severity=max(5, min(10, confidence // 10 + (1 if public else 0))),
                public=public,
            )

    ordered = sorted(
        signals,
        key=lambda row: (
            -_coerce_int(row.get("severity"), 0),
            str(row.get("exposure_kind") or ""),
            str(row.get("signal_id") or ""),
        ),
    )
    return ordered[: max(0, min(MAX_EVIDENCE_EXPOSURE_SIGNALS, int(limit or 0)))]


def evidence_exposure_opportunity_labels(signals: Sequence[Mapping[str, Any]]) -> List[str]:
    mapping = {
        "hide": "conceal compromising evidence",
        "flee": "withdraw before exposure spreads",
        "bribe": "buy silence or cooperation",
        "retaliate": "push back against accusation",
        "confess": "come clean under pressure",
        "accuse": "name a suspect publicly",
        "warn": "alert others to the danger",
        "cooperate": "share what you know",
        "investigate": "pursue leads before they vanish",
    }
    labels: List[str] = []
    for row in signals:
        for behaviour in row.get("behaviours") or []:
            label = mapping.get(str(behaviour or ""))
            if label and label not in labels:
                labels.append(label)
        if len(labels) >= 4:
            break
    return labels[:4]
