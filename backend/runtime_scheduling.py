"""
Runtime scheduling v0.1 — live Actor Resolution + Gravity attention layer.

Promotes the shadow foundation evaluators into turn-path scheduling: which actors
update, cadence, simulation budget, and compression/archive disposition metadata.

Schedulers only — never mutates canonical truth collections (situations, goals,
npc_actions, engine_world_events, etc.). Compression is reversible via the existing
memory_retrieval pipeline; source_truth_preserved is always True.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

import actor_resolution
import foundation_promotion
import gravity_governance
from engine_determinism import stable_hash
from foundation_snapshot import FoundationTurnSnapshot

RUNTIME_SCHEDULING_SCHEMA_VERSION = 2
MAX_SCHEDULING_RECEIPTS = 20
_MAX_RECEIPT_DETAIL = 72
_DURABLE_SCHEDULING_RECEIPT_TYPES = frozenset(
    {
        "actor_promoted",
        "actor_demoted",
        "actor_deferred",
        "gravity_keep_active",
        "gravity_compress",
        "gravity_archive",
        "gravity_fade",
    }
)

SCHEDULING_RECEIPT_TYPES = (
    "actor_promoted",
    "actor_demoted",
    "actor_updated",
    "actor_deferred",
    "gravity_keep_active",
    "gravity_compress",
    "gravity_archive",
    "gravity_fade",
)

# Projection bands excluded from active_situations when Gravity scheduling is live.
_PROJECTION_FADED_BANDS = frozenset({"archive", "eligible_for_deletion"})

# Bands that compress from prompt projection but remain retrievable.
_PROJECTION_COMPRESSED_BANDS = frozenset({"compress", "light_summarisation"})

_TIER_RANK = actor_resolution.TIER_RANK


def scheduling_enabled() -> bool:
    """True when either canonical AR or Gravity promotion flag is on."""
    return foundation_promotion.actor_resolution_enabled() or foundation_promotion.gravity_enabled()


def empty_runtime_scheduling_state() -> Dict[str, Any]:
    return {
        "schema_version": RUNTIME_SCHEDULING_SCHEMA_VERSION,
        "receipts": [],
        "actor_last_action_turn": {},
        "item_bands": {},
    }


def _stable_receipt_id(receipt_type: str, turn_number: int, subject_id: str, detail: str = "") -> str:
    material = f"{receipt_type}|{turn_number}|{subject_id}|{detail}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"sched-{digest[:16]}"


def _append_receipt(
    receipts: List[Dict[str, Any]],
    *,
    receipt_type: str,
    turn_number: int,
    subject_id: str,
    detail: str,
    after: Optional[Mapping[str, Any]] = None,
) -> bool:
    _ = after
    if receipt_type not in SCHEDULING_RECEIPT_TYPES:
        return False
    rid = _stable_receipt_id(receipt_type, turn_number, subject_id, detail)
    if any(row.get("receipt_id") == rid for row in receipts):
        return False
    receipt = {
        "receipt_id": rid,
        "receipt_type": receipt_type,
        "turn": turn_number,
        "subject_id": subject_id,
        "detail": str(detail or "")[:_MAX_RECEIPT_DETAIL],
    }
    receipts.append(receipt)
    if len(receipts) > MAX_SCHEDULING_RECEIPTS:
        receipts[:] = receipts[-MAX_SCHEDULING_RECEIPTS:]
    return True


def _prior_actor_tiers(prior: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    if not isinstance(prior, Mapping):
        return {}
    ar_state = prior.get("actor_resolution_state") or prior.get("actor_resolution") or {}
    if isinstance(ar_state, Mapping):
        prepared = ar_state.get("prepared_state") or ar_state
        actors = prepared.get("actors") or {}
        if isinstance(actors, Mapping):
            return {
                str(actor_id): str(row.get("tier") or "unknown")
                for actor_id, row in actors.items()
                if isinstance(row, Mapping)
            }
    tiers = prior.get("tiers_by_actor_id") or {}
    if isinstance(tiers, Mapping):
        return {str(k): str(v) for k, v in tiers.items()}
    return {}


def _prior_item_bands(prior: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    if not isinstance(prior, Mapping):
        return {}
    gravity_state = prior.get("gravity_state") or prior.get("gravity") or {}
    if isinstance(gravity_state, Mapping):
        items = gravity_state.get("items") or {}
        if isinstance(items, Mapping):
            return {
                str(item_id): str(row.get("band") or "keep_active")
                for item_id, row in items.items()
                if isinstance(row, Mapping) and row.get("band")
            }
    bands = dict(prior.get("item_bands") or {})
    return {str(k): str(v) for k, v in bands.items()}


def _slim_item_bands(item_bands: Mapping[str, str]) -> Dict[str, str]:
    """Persist only bands that affect projection/cadence; missing means keep_active."""
    return {
        str(item_id): str(band)
        for item_id, band in item_bands.items()
        if str(band) not in ("keep_active", "")
    }


def scheduling_item_bands(replayability_state: Mapping[str, Any]) -> Dict[str, str]:
    """Read projection bands from compact runtime scheduling persistence."""
    if not isinstance(replayability_state, Mapping):
        return {}
    rs = replayability_state.get("runtime_scheduling_v1") or {}
    if not isinstance(rs, Mapping):
        return {}
    legacy = rs.get("item_bands") or {}
    if isinstance(legacy, Mapping) and legacy:
        return {str(k): str(v) for k, v in legacy.items()}
    items = (rs.get("gravity_state") or {}).get("items") or {}
    if not isinstance(items, Mapping):
        return {}
    return {
        str(item_id): str(row.get("band") or "keep_active")
        for item_id, row in items.items()
        if isinstance(row, Mapping)
    }


def _compact_durable_receipt(receipt: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "receipt_id": receipt.get("receipt_id"),
        "receipt_type": receipt.get("receipt_type"),
        "turn": receipt.get("turn"),
        "subject_id": receipt.get("subject_id"),
        "detail": str(receipt.get("detail") or "")[:_MAX_RECEIPT_DETAIL],
    }


def _should_append_durable_receipt(
    durable: Sequence[Mapping[str, Any]],
    receipt: Mapping[str, Any],
) -> bool:
    """Skip duplicate consecutive defer/gravity receipts for the same subject."""
    subject = str(receipt.get("subject_id") or "")
    rtype = str(receipt.get("receipt_type") or "")
    detail = str(receipt.get("detail") or "")
    for prior in reversed(durable):
        if str(prior.get("subject_id") or "") != subject:
            continue
        if str(prior.get("receipt_type") or "") != rtype:
            break
        return str(prior.get("detail") or "") != detail
    return True


def _last_action_turn_by_actor(replayability_state: Mapping[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in replayability_state.get("npc_actions") or []:
        if not isinstance(row, Mapping):
            continue
        actor_id = str(row.get("actor_id") or "")
        if not actor_id:
            continue
        resolved = int(row.get("resolved_turn") or row.get("created_turn") or 0)
        out[actor_id] = max(out.get(actor_id, 0), resolved)
    return out


def _scheduling_items_from_snapshot(snapshot: FoundationTurnSnapshot) -> List[Dict[str, Any]]:
    """Extend default gravity items with situations and goals for scheduling metadata."""
    items = list(gravity_governance._default_items_from_snapshot(snapshot))  # noqa: SLF001
    seen = {str(row.get("item_id") or "") for row in items}
    for row in (snapshot.situation_state_ref.get("situations") or []):
        if not isinstance(row, Mapping):
            continue
        situation_id = str(row.get("situation_id") or "")
        if not situation_id:
            continue
        item_id = f"situation:{situation_id}"
        if item_id in seen:
            continue
        seen.add(item_id)
        priority = float(row.get("priority") or 5) / 10.0
        severity = float(row.get("severity") or 5) / 10.0
        gravity = min(1.0, max(0.2, (priority + severity) / 2.0))
        protected = str(row.get("status") or "") in ("active", "forming", "resolving")
        items.append(
            {
                "item_id": item_id,
                "kind": "situation",
                "gravity": gravity,
                "connectivity": min(1.0, len(row.get("involved_actors") or []) / 5.0),
                "protected": protected,
                "unresolved_consequence": protected,
            }
        )
    for row in (snapshot.goal_state_ref.get("goals") or []):
        if not isinstance(row, Mapping):
            continue
        goal_id = str(row.get("goal_id") or "")
        if not goal_id:
            continue
        item_id = f"goal:{goal_id}"
        if item_id in seen:
            continue
        seen.add(item_id)
        status = str(row.get("status") or "")
        if status in ("completed", "failed", "abandoned"):
            continue
        priority = float(row.get("priority") or 5) / 10.0
        items.append(
            {
                "item_id": item_id,
                "kind": "goal",
                "gravity": min(1.0, max(0.15, priority)),
                "connectivity": 0.1,
            }
        )
    return items


def _evaluate_gravity(
    snapshot: FoundationTurnSnapshot,
    *,
    prior: Optional[Mapping[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], Dict[str, str]]:
    if not foundation_promotion.gravity_enabled():
        return None, _prior_item_bands(prior)
    prior_gravity = {}
    if isinstance(prior, Mapping):
        gs = prior.get("gravity_state") or {}
        if isinstance(gs, Mapping):
            prior_gravity = gs
    prepared = gravity_governance.evaluate_gravity_governance(
        snapshot,
        prior_state=prior_gravity or None,
        items=_scheduling_items_from_snapshot(snapshot),
    )
    bands = {
        str(row.get("item_id") or ""): str(row.get("band") or "")
        for row in prepared.get("dispositions") or []
        if isinstance(row, Mapping) and row.get("item_id")
    }
    return prepared, bands


def _evaluate_actor_resolution(
    snapshot: FoundationTurnSnapshot,
    *,
    prior: Optional[Mapping[str, Any]],
    retention_scores: Mapping[str, float],
) -> Optional[Dict[str, Any]]:
    if not foundation_promotion.actor_resolution_enabled():
        return None
    prior_ar = {}
    if isinstance(prior, Mapping):
        ars = prior.get("actor_resolution_state") or {}
        if isinstance(ars, Mapping):
            prior_ar = ars
    return actor_resolution.evaluate_actor_resolution(
        snapshot,
        prior_state=(prior_ar.get("prepared_state") if isinstance(prior_ar, Mapping) else None)
        or (prior_ar if isinstance(prior_ar, Mapping) and prior_ar.get("actors") else None),
        retention_scores=retention_scores,
    )


def _tier_change_receipts(
    receipts: List[Dict[str, Any]],
    *,
    prior_tiers: Mapping[str, str],
    new_tiers: Mapping[str, str],
    turn_number: int,
) -> int:
    emitted = 0
    for actor_id in sorted(set(prior_tiers.keys()) | set(new_tiers.keys())):
        old = str(prior_tiers.get(actor_id) or "unknown")
        new = str(new_tiers.get(actor_id) or "unknown")
        if old == new:
            continue
        old_rank = _TIER_RANK.get(old, 99)
        new_rank = _TIER_RANK.get(new, 99)
        if new_rank < old_rank:
            if _append_receipt(
                receipts,
                receipt_type="actor_promoted",
                turn_number=turn_number,
                subject_id=actor_id,
                detail=f"{old}->{new}",
                after={"tier": new, "prior_tier": old},
            ):
                emitted += 1
        elif new_rank > old_rank:
            if _append_receipt(
                receipts,
                receipt_type="actor_demoted",
                turn_number=turn_number,
                subject_id=actor_id,
                detail=f"{old}->{new}",
                after={"tier": new, "prior_tier": old},
            ):
                emitted += 1
    return emitted


def _gravity_change_receipts(
    receipts: List[Dict[str, Any]],
    *,
    prior_bands: Mapping[str, str],
    new_bands: Mapping[str, str],
    turn_number: int,
) -> int:
    emitted = 0
    for item_id in sorted(set(prior_bands.keys()) | set(new_bands.keys())):
        old = str(prior_bands.get(item_id) or "")
        new = str(new_bands.get(item_id) or "")
        if not new or old == new:
            continue
        # Initial band assignment is not a disposition transition.
        if not old:
            continue
        if new == "keep_active":
            rtype = "gravity_keep_active"
        elif new in _PROJECTION_COMPRESSED_BANDS:
            rtype = "gravity_compress"
        elif new == "archive":
            rtype = "gravity_archive"
        elif new == "eligible_for_deletion":
            rtype = "gravity_fade"
        else:
            rtype = "gravity_compress"
        if _append_receipt(
            receipts,
            receipt_type=rtype,
            turn_number=turn_number,
            subject_id=item_id,
            detail=f"{old or 'new'}->{new}",
            after={"band": new, "prior_band": old, "source_truth_preserved": True},
        ):
            emitted += 1
    return emitted


def should_update_actor(
    actor_id: str,
    *,
    actor_prepared: Mapping[str, Any],
    turn_number: int,
    last_action_turn: int,
) -> Tuple[bool, str]:
    """Return (eligible, reason) for npc_action / utility cadence gating."""
    acting_ids = set(actor_prepared.get("acting_actor_ids") or [])
    tiers = actor_prepared.get("tiers_by_actor_id") or {}
    tier = str(tiers.get(actor_id) or "unknown")
    if actor_id not in acting_ids:
        return False, f"non_acting_tier:{tier}"
    if not actor_resolution.is_actor_eligible_for_action(
        actor_id,
        actor_prepared,
        turn_sequence=turn_number,
        last_action_turn=last_action_turn,
    ):
        cadence = actor_resolution.TIER_CADENCE_TURNS.get(tier, 99)
        return False, f"cadence_deferred:tier={tier}:cadence={cadence}"
    return True, f"acting_tier:{tier}"


def situation_projection_eligible(
    situation_id: str,
    gravity_metadata: Optional[Mapping[str, Any]],
    *,
    item_bands: Optional[Mapping[str, str]] = None,
) -> bool:
    """True when a situation may appear in active_situations projection."""
    if not foundation_promotion.gravity_enabled():
        return True
    bands: Dict[str, str] = {}
    if isinstance(item_bands, Mapping):
        bands = {str(k): str(v) for k, v in item_bands.items()}
    elif isinstance(gravity_metadata, Mapping):
        legacy = gravity_metadata.get("item_bands") or {}
        if isinstance(legacy, Mapping):
            bands = {str(k): str(v) for k, v in legacy.items()}
    item_id = f"situation:{situation_id}"
    band = str(bands.get(item_id) or "keep_active")
    return band not in _PROJECTION_FADED_BANDS


def evaluate_runtime_scheduling(
    snapshot: FoundationTurnSnapshot,
    replayability_state: Mapping[str, Any],
    *,
    turn_number: int,
    prior: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluate live scheduling metadata from snapshot. Pure — does not mutate inputs.
    """
    diagnostics: Dict[str, Any] = {
        "runtime_scheduling_enabled": scheduling_enabled(),
        "runtime_scheduling_applied": False,
        "runtime_scheduling_actor_gated": False,
        "runtime_scheduling_gravity_applied": False,
    }
    if not scheduling_enabled():
        return {
            "actor_resolution": None,
            "gravity": None,
            "item_bands": {},
            "receipts": [],
            "diagnostics": diagnostics,
            "acting_actor_ids": [],
            "tiers_by_actor_id": {},
        }

    prior_tiers = _prior_actor_tiers(prior)
    prior_bands = _prior_item_bands(prior)
    receipts: List[Dict[str, Any]] = []

    gravity_prepared, item_bands = _evaluate_gravity(snapshot, prior=prior)
    if gravity_prepared is not None:
        diagnostics["runtime_scheduling_gravity_applied"] = True
        _gravity_change_receipts(
            receipts,
            prior_bands=prior_bands,
            new_bands=item_bands,
            turn_number=turn_number,
        )

    retention_scores = (
        gravity_governance.retention_scores_by_actor(gravity_prepared)
        if gravity_prepared
        else {}
    )
    actor_prepared = _evaluate_actor_resolution(
        snapshot,
        prior=prior,
        retention_scores=retention_scores,
    )
    new_tiers: Dict[str, str] = {}
    acting_ids: List[str] = []
    if actor_prepared is not None:
        diagnostics["runtime_scheduling_actor_gated"] = True
        new_tiers = dict(actor_prepared.get("tiers_by_actor_id") or {})
        acting_ids = list(actor_prepared.get("acting_actor_ids") or [])
        _tier_change_receipts(
            receipts,
            prior_tiers=prior_tiers,
            new_tiers=new_tiers,
            turn_number=turn_number,
        )

    last_action_turn = _last_action_turn_by_actor(replayability_state)
    deferred: List[Dict[str, str]] = []
    updated: List[str] = []
    if actor_prepared is not None:
        goals = replayability_state.get("goals") or []
        actors_with_goals = sorted(
            {
                str(goal.get("owner_id") or "")
                for goal in goals
                if isinstance(goal, Mapping)
                and str(goal.get("owner_id") or "")
                and str(goal.get("status") or "") not in ("completed", "failed", "abandoned")
            }
        )
        for actor_id in actors_with_goals:
            eligible, reason = should_update_actor(
                actor_id,
                actor_prepared=actor_prepared,
                turn_number=turn_number,
                last_action_turn=int(last_action_turn.get(actor_id, 0)),
            )
            if eligible:
                updated.append(actor_id)
                _append_receipt(
                    receipts,
                    receipt_type="actor_updated",
                    turn_number=turn_number,
                    subject_id=actor_id,
                    detail=reason,
                    after={"tier": new_tiers.get(actor_id, "unknown")},
                )
            else:
                deferred.append({"actor_id": actor_id, "reason": reason})
                _append_receipt(
                    receipts,
                    receipt_type="actor_deferred",
                    turn_number=turn_number,
                    subject_id=actor_id,
                    detail=reason,
                    after={"tier": new_tiers.get(actor_id, "unknown")},
                )

    diagnostics.update(
        {
            "runtime_scheduling_applied": True,
            "runtime_scheduling_acting_count": len(acting_ids),
            "runtime_scheduling_updated_count": len(updated),
            "runtime_scheduling_deferred_count": len(deferred),
            "runtime_scheduling_receipt_count": len(receipts),
        }
    )

    state_hash = stable_hash(
        "runtime_scheduling",
        {
            "turn": turn_number,
            "acting_actor_ids": acting_ids,
            "item_bands": item_bands,
            "source_state_hash": snapshot.source_state_hash,
        },
    )

    return {
        "actor_resolution": actor_prepared,
        "gravity": gravity_prepared,
        "item_bands": item_bands,
        "receipts": receipts,
        "diagnostics": diagnostics,
        "acting_actor_ids": acting_ids,
        "tiers_by_actor_id": new_tiers,
        "actor_last_action_turn": last_action_turn,
        "state_hash": state_hash,
        "deferred_actors": deferred,
        "updated_actors": updated,
    }


def _compact_actor_state(actor_prepared: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(actor_prepared, Mapping):
        return {"schema_version": actor_resolution.ACTOR_RESOLUTION_SCHEMA_VERSION, "actors": {}}
    raw = actor_prepared.get("prepared_state") or {}
    actors = raw.get("actors") if isinstance(raw, Mapping) else {}
    compact: Dict[str, Any] = {}
    if isinstance(actors, Mapping):
        for actor_id, row in actors.items():
            if not isinstance(row, Mapping):
                continue
            entry: Dict[str, Any] = {"tier": row.get("tier")}
            last = row.get("last_interaction_sim_minutes")
            if last is not None:
                entry["last_interaction_sim_minutes"] = last
            compact[str(actor_id)] = entry
    return {
        "schema_version": actor_resolution.ACTOR_RESOLUTION_SCHEMA_VERSION,
        "actors": compact,
    }


def _compact_gravity_state(
    gravity_prepared: Optional[Mapping[str, Any]],
    *,
    slim_bands: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    if isinstance(slim_bands, Mapping) and slim_bands:
        return {
            "schema_version": gravity_governance.GRAVITY_GOVERNANCE_SCHEMA_VERSION,
            "items": {str(item_id): {"band": str(band)} for item_id, band in slim_bands.items()},
        }
    if not isinstance(gravity_prepared, Mapping):
        return {"schema_version": gravity_governance.GRAVITY_GOVERNANCE_SCHEMA_VERSION, "items": {}}
    raw = gravity_prepared.get("prepared_state") or {}
    items = raw.get("items") if isinstance(raw, Mapping) else {}
    compact: Dict[str, Any] = {}
    if isinstance(items, Mapping):
        for item_id, row in items.items():
            if not isinstance(row, Mapping):
                continue
            band = str(row.get("band") or "keep_active")
            if band == "keep_active":
                continue
            compact[str(item_id)] = {"band": band}
    return {
        "schema_version": gravity_governance.GRAVITY_GOVERNANCE_SCHEMA_VERSION,
        "items": compact,
    }


def apply_runtime_scheduling(
    replayability_state: Dict[str, Any],
    scheduling_result: Mapping[str, Any],
    *,
    turn_number: int,
) -> Dict[str, Any]:
    """Persist scheduling metadata on the action working copy. Canonical collections untouched."""
    if not scheduling_enabled() or not scheduling_result.get("diagnostics", {}).get(
        "runtime_scheduling_applied"
    ):
        return replayability_state

    state = replayability_state
    actor_prepared = scheduling_result.get("actor_resolution")
    gravity_prepared = scheduling_result.get("gravity")
    item_bands = dict(scheduling_result.get("item_bands") or {})
    slim_bands = _slim_item_bands(item_bands)

    state["runtime_scheduling_v1"] = {
        "schema_version": RUNTIME_SCHEDULING_SCHEMA_VERSION,
        "turn": turn_number,
        "state_hash": scheduling_result.get("state_hash"),
        "actor_resolution_state": _compact_actor_state(
            actor_prepared if isinstance(actor_prepared, Mapping) else None
        ),
        "gravity_state": _compact_gravity_state(
            gravity_prepared if isinstance(gravity_prepared, Mapping) else None,
            slim_bands=slim_bands,
        ),
    }

    # Scheduling-layer gravity metadata — counts only; bands live in gravity_state.items.
    faded_ids = [item_id for item_id, band in item_bands.items() if band in _PROJECTION_FADED_BANDS]
    compressed_ids = [
        item_id for item_id, band in item_bands.items() if band in _PROJECTION_COMPRESSED_BANDS
    ]
    state["gravity_metadata"] = {
        "schema_version": RUNTIME_SCHEDULING_SCHEMA_VERSION,
        "turn": turn_number,
        "source_truth_preserved": True,
        "compressed_count": len(compressed_ids),
        "faded_count": len(faded_ids),
        "active_count": sum(1 for band in item_bands.values() if band == "keep_active"),
    }

    durable = state.setdefault("scheduling_receipts", [])
    for receipt in scheduling_result.get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        if str(receipt.get("receipt_type") or "") not in _DURABLE_SCHEDULING_RECEIPT_TYPES:
            continue
        rid = str(receipt.get("receipt_id") or "")
        compact = _compact_durable_receipt(receipt)
        if not rid or any(isinstance(r, Mapping) and r.get("receipt_id") == rid for r in durable):
            continue
        if not _should_append_durable_receipt(durable, compact):
            continue
        durable.append(compact)
    if len(durable) > MAX_SCHEDULING_RECEIPTS:
        state["scheduling_receipts"] = durable[-MAX_SCHEDULING_RECEIPTS:]

    return state


def deferred_actor_ids(scheduling_result: Optional[Mapping[str, Any]]) -> Set[str]:
    if not isinstance(scheduling_result, Mapping):
        return set()
    if not foundation_promotion.actor_resolution_enabled():
        return set()
    return {
        str(row.get("actor_id") or "")
        for row in scheduling_result.get("deferred_actors") or []
        if isinstance(row, Mapping) and row.get("actor_id")
    }