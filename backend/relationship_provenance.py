"""
Relationship provenance — Phase 1 State-is-truth remediation (Ch 29 / Ch 31).

Every relationship mutation must originate from a STRUCTURED EVENT and expose
provenance. Generated prose (narrative) is NEVER read here. A player action is
resolved deterministically into structured events; those events — not the prose
that renders them — drive the vectors:

    player action --resolve_player_action_events--> structured events
                  --apply_relationship_events----> vectors + provenance

Provenance answers, for every mutation: what event, when, who caused it, which
vector, by how much, and why. It is developer-diagnostic only and is never
written into ``rolling_state``, so it cannot reach the prompt.

Primitives (deltas, detection, clamp, decay, state) are reused from
``relationships`` to keep a single canonical source of truth.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Mapping, Optional, Tuple

import relationships as _rc

DIMENSIONS = _rc.DIMENSIONS

# Canonical application order for events sharing a target: follows the
# ``_EVENT_VERBS`` declaration order so per-dimension clamping is order-stable
# and independent of the caller's input ordering.
_KIND_ORDER: Dict[str, int] = {kind: i for i, kind in enumerate(_rc._EVENT_VERBS)}

PROVENANCE_FIELDS = (
    "event_id", "turn", "target_name", "source_kind", "cause",
    "kind", "reason", "requested_deltas", "applied_deltas", "before", "after",
)


def _event_id(turn: int, target: str, kind: str, source_kind: str, ordinal: int) -> str:
    """Deterministic event id — no RNG, no wall-clock (replay-stable)."""
    raw = f"{int(turn)}|{str(target).strip().lower()}|{kind}|{source_kind}|{int(ordinal)}"
    return "relev-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _gather_names(
    prior_rolling: Optional[Mapping[str, Any]],
    merged_rolling: Optional[Mapping[str, Any]],
) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    """Candidate NPC names + authoritative prior vectors keyed by lowercased name."""
    prior_vectors: Dict[str, Dict[str, Any]] = {}
    src = prior_rolling.get("relationship_vectors") if isinstance(prior_rolling, dict) else None
    for row in src or []:
        if isinstance(row, dict) and row.get("name"):
            prior_vectors[str(row["name"]).strip().lower()] = dict(row)

    names = _rc._candidate_names(prior_rolling, merged_rolling)
    seen = {n.lower() for n in names}
    # Keep any prior-tracked NPC even if absent this turn (so they keep decaying).
    for key in prior_vectors:
        if key not in seen:
            names.append(prior_vectors[key].get("name", key))
            seen.add(key)
    return names, prior_vectors


def resolve_player_action_events(
    player_action: Optional[str],
    names: List[str],
    current_turn: int,
) -> List[Dict[str, Any]]:
    """Deterministically resolve the PLAYER'S declared action into structured events.

    Reads only ``player_action`` — never generated prose. This is the Phase-1
    "simulation resolution" step: the literal player action is mapped to
    canonical Ch 29.8 events. Returns structured events (not applied yet).
    """
    import re as _re

    action_text = str(player_action or "")
    events: List[Dict[str, Any]] = []
    if not action_text.strip():
        return events
    for name in names:
        kinds = _rc._detect_events(action_text, _re.escape(name))
        for ordinal, kind in enumerate(kinds):
            events.append(
                {
                    "event_id": _event_id(current_turn, name, kind, "player_action", ordinal),
                    "kind": kind,
                    "target_name": name,
                    "source_kind": "player_action",
                    "cause": "player",
                    "deltas": dict(_rc.EVENT_DELTAS[kind]),
                    "reason": f"player action resolved: {kind} toward {name}",
                    "turn": current_turn,
                }
            )
    return events


def _validate_event(ev: Any, turn: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return (normalised_event, None) or (None, rejection_reason)."""
    if not isinstance(ev, dict):
        return None, "not_a_dict"
    target = str(ev.get("target_name") or ev.get("target_id") or "").strip()
    if not target:
        return None, "missing_target"
    kind = str(ev.get("kind") or "").strip()
    if not kind:
        return None, "missing_kind"
    raw_deltas = ev.get("deltas")
    if not isinstance(raw_deltas, dict):
        return None, "missing_deltas"
    deltas: Dict[str, int] = {}
    for d, val in raw_deltas.items():
        if d not in DIMENSIONS:
            continue
        if isinstance(val, bool):
            return None, "bad_delta"
        try:
            deltas[d] = int(val)
        except (TypeError, ValueError):
            return None, "bad_delta"
    if not deltas:
        return None, "no_valid_dimensions"
    source_kind = str(ev.get("source_kind") or "event")
    eid = str(ev.get("event_id") or _event_id(turn, target, kind, source_kind, 0))
    return (
        {
            "event_id": eid,
            "kind": kind,
            "target_name": target,
            "source_kind": source_kind,
            "cause": str(ev.get("cause") or ""),
            "deltas": deltas,
            "reason": str(ev.get("reason") or f"{source_kind}: {kind} toward {target}"),
            "turn": int(turn),
        },
        None,
    )


def _group_events(
    events: Optional[List[Mapping[str, Any]]],
    turn: int,
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    """Validate, dedupe (by event_id), and canonically order events per target."""
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    rejected: List[Dict[str, Any]] = []
    seen_ids: set = set()
    for raw in events or []:
        norm, reason = _validate_event(raw, turn)
        if norm is None:
            rejected.append({"reason": reason})
            continue
        if norm["event_id"] in seen_ids:
            continue  # no duplicate application
        seen_ids.add(norm["event_id"])
        by_name.setdefault(norm["target_name"].strip().lower(), []).append(norm)
    for _key, evs in by_name.items():
        evs.sort(key=lambda e: (_KIND_ORDER.get(e["kind"], 999), e["event_id"]))
    return by_name, rejected


def apply_relationship_events(
    prior_rolling: Optional[Mapping[str, Any]],
    merged_rolling: Optional[Dict[str, Any]],
    events: Optional[List[Mapping[str, Any]]],
    *,
    current_turn: int = 0,
    decay: bool = True,
    provenance_sink: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """Single authoritative relationship mutation path.

    Applies structured ``events`` (from any deterministic source) on top of the
    AUTHORITATIVE prior vectors, decays untouched relationships, derives state,
    and writes ``merged_rolling['relationship_vectors']``. Records one provenance
    record per applied event into ``provenance_sink`` (dev-diagnostic only).

    Prose is never read here. Malformed events are rejected. Duplicate events
    (same ``event_id``) are applied once. Application order is canonical, so
    replay and input reordering yield identical vectors.
    """
    if not isinstance(merged_rolling, dict):
        return []

    deceased = {str(d).strip().lower() for d in (merged_rolling.get("deceased") or [])}
    names, prior_vectors = _gather_names(prior_rolling, merged_rolling)
    events_by_name, rejected = _group_events(events, current_turn)

    # New NPCs referenced only by a structured event still get a vector.
    seen = {n.lower() for n in names}
    for key, evs in events_by_name.items():
        if key not in seen and key not in deceased:
            names.append(evs[0]["target_name"])
            seen.add(key)

    out: List[Dict[str, Any]] = []
    adjustments: List[str] = []
    provenance: List[Dict[str, Any]] = []

    for name in names:
        key = name.strip().lower()
        if key in deceased:
            continue
        vec = prior_vectors.get(key) or _rc._new_vector(name, current_turn)
        for d in DIMENSIONS:
            vec[d] = _rc._clamp(d, vec.get(d, 0))
        vec.setdefault("bond", "neutral")
        identity = vec.get("bond") == "identity"

        evs = events_by_name.get(key) or []
        if evs:
            for ev in evs:
                before = {d: int(vec[d]) for d in DIMENSIONS}
                for d, delta in ev["deltas"].items():
                    vec[d] = _rc._clamp(d, vec[d] + delta)
                after = {d: int(vec[d]) for d in DIMENSIONS}
                provenance.append(
                    {
                        "event_id": ev["event_id"],
                        "turn": current_turn,
                        "target_name": name,
                        "source_kind": ev["source_kind"],
                        "cause": ev.get("cause", ""),
                        "kind": ev["kind"],
                        "reason": ev.get("reason", ""),
                        "requested_deltas": dict(ev["deltas"]),
                        "applied_deltas": {
                            d: after[d] - before[d]
                            for d in DIMENSIONS
                            if after[d] != before[d]
                        },
                        "before": before,
                        "after": after,
                    }
                )
            vec["last_turn"] = current_turn
            adjustments.append(f"{name}:{'+'.join(ev['kind'] for ev in evs)}")
        elif decay:
            factor = 0.1 if identity else 1.0
            for d in DIMENSIONS:
                vec[d] = _rc._clamp(d, vec[d] * (1 - _rc._DECAY[d] * factor))

        vec["state"] = _rc._derive_state(vec)
        out.append(vec)

    merged_rolling["relationship_vectors"] = out
    _rc._sync_stance(merged_rolling, out)

    if provenance_sink is not None:
        provenance_sink.extend(provenance)
        for rej in rejected:
            provenance_sink.append(
                {
                    "event_id": None,
                    "turn": current_turn,
                    "rejected": True,
                    "reason": rej.get("reason"),
                    "source_kind": "rejected_event",
                }
            )

    if adjustments:
        return ["rel:" + " | ".join(adjustments[:8])]
    return []


def update_from_player_action(
    prior_rolling: Optional[Mapping[str, Any]],
    merged_rolling: Optional[Dict[str, Any]],
    player_action: Optional[str],
    current_turn: int,
    *,
    provenance_sink: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """Resolve the player's action into structured events and apply them.

    Generated prose is never consulted. This is the delegate used by
    ``relationships.update_relationship_calculus``.
    """
    if not isinstance(merged_rolling, dict):
        return []
    names, _prior = _gather_names(prior_rolling, merged_rolling)
    events = resolve_player_action_events(player_action, names, current_turn)
    return apply_relationship_events(
        prior_rolling,
        merged_rolling,
        events,
        current_turn=current_turn,
        decay=True,
        provenance_sink=provenance_sink,
    )


def living_cast_effect_provenance(
    effects: Optional[List[Mapping[str, Any]]],
    turn_number: int,
) -> List[Dict[str, Any]]:
    """Normalise applied Living Cast relationship effects into provenance records.

    Living Cast effects are already structured and engine-owned (SAFE). After
    ``relationships.apply_living_cast_relationship_effects`` runs, each effect
    carries ``before``/``after``; this exposes them in the same shape as the
    calculus provenance so developer diagnostics are uniform. Dev-diagnostic
    only — never written to ``rolling_state``.
    """
    records: List[Dict[str, Any]] = []
    for raw in effects or []:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("effect_type") or "") != "relationship_delta":
            continue
        name = str(raw.get("target_name") or raw.get("target_id") or "").strip()
        if not name:
            continue
        before = raw.get("before") if isinstance(raw.get("before"), dict) else {}
        after = raw.get("after") if isinstance(raw.get("after"), dict) else {}
        applied = {
            d: int(after.get(d, 0)) - int(before.get(d, 0))
            for d in DIMENSIONS
            if int(after.get(d, 0)) != int(before.get(d, 0))
        }
        records.append(
            {
                "event_id": str(raw.get("effect_id") or ""),
                "turn": turn_number,
                "target_name": name,
                "source_kind": "living_cast_effect",
                "cause": str(raw.get("source_id") or raw.get("actor_id") or "living_cast"),
                "kind": "relationship_delta",
                "reason": str(raw.get("reason") or "living cast relationship effect"),
                "requested_deltas": _rc._applied_delta(raw),
                "applied_deltas": applied,
                "before": {d: int(before.get(d, 0)) for d in DIMENSIONS} if before else {},
                "after": {d: int(after.get(d, 0)) for d in DIMENSIONS} if after else {},
            }
        )
    return records
