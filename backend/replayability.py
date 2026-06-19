"""
Replayability Engine v1 — orchestration, state container, directives, enforcement.

Session document field ``replayability_state`` (NOT rolling_state).
Legacy sessions without the field skip replayability processing (Policy A).

Canonical event history lives in rolling_state structures and pressure
``threshold_crossings`` receipts — not in a second replayability event log.
"""

from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

import consequence_echoes as echoes
import opening_state
import pressure_graph
from run_identity import derive_run_identity, is_closed_enum_identity

REPLAYABILITY_VERSION = 1
TRANSITION_RECEIPTS_MAX = 32

# Keys the LLM must never own in rolling_state.
ROLLING_REPLAYABILITY_KEYS = frozenset({
    "replayability_identity",
    "run_identity",
    "run_seed",
    "opening_archetype",
    "opening_state",
    "pressure_graph",
    "consequence_echoes",
    "transition_receipts",
    "engine_events",
})

DIRECTIVE_MARKERS = (
    opening_state.OPENING_DIRECTIVE_MARKER,
    pressure_graph.PRESSURE_DIRECTIVE_MARKER,
    echoes.ECHO_DIRECTIVE_MARKER,
)

DIRECTIVE_PROSE_PATTERNS = (
    r"INTERNAL\s+—\s+replayability\s+opening\s+contract",
    r"INTERNAL\s+—\s+foreground\s+pressure",
    r"INTERNAL\s+—\s+consequence\s+echo",
    r"Immediate\s+problem:",
    r"Primary\s+pressure\s+kind:",
)

RELATIONSHIP_ECHO_STATES = frozenset({"betrayal_risk", "collapsed"})

_FACTION_HOSTILITY_THRESHOLD = 3
_DELAYED_FIRED_RE = re.compile(r"^delayed_fired:(\d+)$")
_DESTRUCTION_RE = re.compile(
    r"^(?:dest(?:ruction|royed|royed_registry)|gateway:object_terminal_recorded)[:_]",
    re.IGNORECASE,
)


def empty_replayability_state() -> Dict[str, Any]:
    return {
        "version": REPLAYABILITY_VERSION,
        "run_seed": "",
        "identity": {},
        "opening": {},
        "pressure_graph": pressure_graph.copy_pressure_graph(None),
        "consequence_echoes": echoes.init_consequence_echoes(),
        "transition_receipts": [],
    }


def _append_transition_receipt(
    state: Dict[str, Any],
    *,
    source_event_id: str,
    receipt_type: str,
    turn_number: int,
) -> bool:
    """Idempotent non-authoritative receipt — not event history."""
    receipts = state.setdefault("transition_receipts", [])
    if any(
        isinstance(r, dict)
        and r.get("source_event_id") == source_event_id
        and r.get("receipt_type") == receipt_type
        for r in receipts
    ):
        return False
    receipts.append(
        {
            "source_event_id": source_event_id,
            "receipt_type": receipt_type,
            "turn": turn_number,
        }
    )
    if len(receipts) > TRANSITION_RECEIPTS_MAX:
        state["transition_receipts"] = receipts[-TRANSITION_RECEIPTS_MAX:]
    return True


def _build_setup_context(
    *,
    genre: Optional[str],
    role: Optional[str],
    tone: Optional[str],
    difficulty: Optional[str],
    scenario_id: Optional[str],
    custom_premise: Optional[str],
    custom_world_setup: Optional[Dict[str, Any]],
    scenario: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "genre": genre,
        "role": role,
        "tone": tone,
        "difficulty": difficulty,
        "scenario_id": scenario_id,
        "custom_premise": custom_premise,
        "custom_world_setup": custom_world_setup,
    }
    if scenario and scenario.get("hidden_threat"):
        ctx["hidden_threat"] = scenario.get("hidden_threat")
    return ctx


def _opening_unresolved_source(opening: Mapping[str, Any], run_seed: str) -> Dict[str, Any]:
    fact_id = (opening.get("fact_ids") or {}).get("tension") or f"opening-{run_seed[:8]}"
    return {
        "source_kind": "opening_unresolved_tension",
        "source_event_id": f"evt-opening-{fact_id}",
        "echo_kind": "pressure_escalation",
        "label": str(opening.get("relationship_tension") or "unresolved opening tension")[:80],
        "mature_in": 2,
    }


def init_new_story(
    *,
    genre: Optional[str],
    role: Optional[str],
    tone: Optional[str],
    difficulty: Optional[str],
    scenario_id: Optional[str],
    custom_premise: Optional[str],
    custom_world_setup: Optional[Dict[str, Any]],
    scenario: Optional[Mapping[str, Any]] = None,
    run_seed: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Create replayability_state and frozen directives for turn 1.

    Returns (replayability_state, directives) where directives has keys
    opening, pressure, echo.
    """
    seed = run_seed or str(uuid.uuid4())
    setup = _build_setup_context(
        genre=genre,
        role=role,
        tone=tone,
        difficulty=difficulty,
        scenario_id=scenario_id,
        custom_premise=custom_premise,
        custom_world_setup=custom_world_setup,
        scenario=scenario,
    )
    identity = derive_run_identity(seed, setup)
    opening = opening_state.select_opening_archetype(seed, setup, identity=identity, scenario=scenario)
    pg = pressure_graph.init_pressure_graph(seed, identity, opening, created_turn=1)
    echo_state = echoes.init_consequence_echoes()

    state: Dict[str, Any] = {
        "version": REPLAYABILITY_VERSION,
        "run_seed": seed,
        "identity": identity,
        "opening": opening,
        "pressure_graph": pg,
        "consequence_echoes": echo_state,
        "transition_receipts": [],
    }

    opening_source = _opening_unresolved_source(opening, seed)
    echoes.schedule_from_structured_events(
        echo_state,
        [opening_source],
        turn_number=1,
        processed_source_ids=echoes.processed_source_event_ids(echo_state),
    )
    _append_transition_receipt(
        state,
        source_event_id=opening_source["source_event_id"],
        receipt_type="echo_scheduled",
        turn_number=1,
    )

    directives = {
        "opening": opening_state.build_opening_directive(opening, identity, scenario=scenario),
        "pressure": pressure_graph.build_pressure_directive(pg),
        "echo": "",
    }
    return state, directives


def prepare_action_turn(
    replayability_state: Optional[Mapping[str, Any]],
    turn_number: int,
) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, Any], List[Dict[str, Any]]]:
    """
    Tick pressure, mature echoes, fire at most one echo, build directives.

    Does NOT schedule new echoes from player text or narrative.
    Returns (updated_state, frozen_directives, diagnostics, threshold_events).
    """
    diagnostics: Dict[str, Any] = {}
    if not isinstance(replayability_state, dict) or not replayability_state.get("run_seed"):
        return {}, {"opening": "", "pressure": "", "echo": ""}, diagnostics, []

    state = copy.deepcopy(replayability_state)
    identity = state.get("identity") or {}
    pg = state.setdefault("pressure_graph", pressure_graph.copy_pressure_graph(None))
    echo_state = state.setdefault("consequence_echoes", echoes.init_consequence_echoes())

    threshold_fired = pressure_graph.tick_pressure_graph(pg, turn_number, identity=identity)
    if threshold_fired:
        diagnostics["pressure_threshold_events"] = len(threshold_fired)
        processed = echoes.processed_source_event_ids(echo_state)
        for evt in threshold_fired:
            source = {
                "source_kind": "pressure_threshold_crossed",
                "source_event_id": evt["event_id"],
                "echo_kind": "pressure_escalation",
                "label": str(evt.get("pressure_kind") or "pressure").replace("_", " "),
            }
            added = echoes.schedule_from_structured_events(
                echo_state, [source], turn_number, processed_source_ids=processed
            )
            if added:
                processed.add(evt["event_id"])
                _append_transition_receipt(
                    state,
                    source_event_id=evt["event_id"],
                    receipt_type="echo_scheduled",
                    turn_number=turn_number,
                )

    matured = echoes.mature_echoes(echo_state, turn_number)
    if matured:
        diagnostics["echoes_matured"] = len(matured)

    fired_echo, did_fire = echoes.fire_echo(echo_state, turn_number)
    if did_fire and fired_echo:
        diagnostics["echo_fired"] = fired_echo.get("id")
        src = fired_echo.get("source_event_id")
        if src:
            _append_transition_receipt(
                state,
                source_event_id=src,
                receipt_type="echo_fired",
                turn_number=turn_number,
            )

    pressure_graph.select_foreground(pg, identity=identity, turn_number=turn_number)

    directives = {
        "opening": "",
        "pressure": pressure_graph.build_pressure_directive(pg),
        "echo": echoes.build_echo_directive(echo_state, fired_this_turn=fired_echo if did_fire else None),
    }
    return state, directives, diagnostics, threshold_fired


def collect_qualifying_echo_sources(
    *,
    prior_rolling: Optional[Mapping[str, Any]],
    merged_rolling: Optional[Mapping[str, Any]],
    turn_number: int,
    guard_adjustments: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Extract confirmed engine-owned structured events from rolling_state transitions.

    Never parses player action text, narrative, or provider output.
    """
    sources: List[Dict[str, Any]] = []
    prior = prior_rolling if isinstance(prior_rolling, dict) else {}
    merged = merged_rolling if isinstance(merged_rolling, dict) else {}

    for adj in guard_adjustments or []:
        m = _DELAYED_FIRED_RE.match(str(adj))
        if m:
            idx = m.group(1)
            delayed = merged.get("delayed_consequences") or []
            entry = delayed[int(idx)] if int(idx) < len(delayed) else {}
            desc = str(entry.get("description") or entry.get("name") or "delayed consequence")[:80]
            sources.append(
                {
                    "source_kind": "delayed_consequence_fired",
                    "source_event_id": f"evt-delayed-{idx}-turn-{turn_number}",
                    "echo_kind": "delayed_consequence",
                    "label": desc,
                }
            )
            continue
        if _DESTRUCTION_RE.search(str(adj)):
            sources.append(
                {
                    "source_kind": "destruction_confirmed",
                    "source_event_id": f"evt-destruction-turn-{turn_number}-{len(sources)}",
                    "echo_kind": "resource_loss",
                    "label": "something destroyed or consumed",
                }
            )

    prior_vecs = {
        str(v.get("name", "")).strip().lower(): v
        for v in prior.get("relationship_vectors") or []
        if isinstance(v, dict) and v.get("name")
    }
    for vec in merged.get("relationship_vectors") or []:
        if not isinstance(vec, dict) or not vec.get("name"):
            continue
        key = str(vec["name"]).strip().lower()
        before = prior_vecs.get(key, {})
        after_state = str(vec.get("state") or "")
        before_state = str(before.get("state") or "")
        if after_state in RELATIONSHIP_ECHO_STATES and after_state != before_state:
            sources.append(
                {
                    "source_kind": "relationship_threshold_crossed",
                    "source_event_id": f"evt-rel-{key}-turn-{turn_number}",
                    "echo_kind": "relationship_fracture",
                    "label": f"{vec.get('name')} — {after_state.replace('_', ' ')}",
                }
            )

    prior_factions = {
        str(f.get("name", "")).strip().lower(): f
        for f in prior.get("faction_pressure") or []
        if isinstance(f, dict) and f.get("name")
    }
    for fac in merged.get("faction_pressure") or []:
        if not isinstance(fac, dict) or not fac.get("name"):
            continue
        key = str(fac["name"]).strip().lower()
        before_ticks = (prior_factions.get(key) or {}).get("ticks") or {}
        after_ticks = fac.get("ticks") or {}
        if not isinstance(after_ticks, dict):
            continue
        for tick_key, after_val in after_ticks.items():
            before_val = int((before_ticks or {}).get(tick_key, 0))
            after_int = int(after_val or 0)
            if before_val < _FACTION_HOSTILITY_THRESHOLD <= after_int and tick_key in (
                "suspicion", "guard_attention", "hostility"
            ):
                sources.append(
                    {
                        "source_kind": "faction_hostility_shift",
                        "source_event_id": f"evt-faction-{key}-{tick_key}-turn-{turn_number}",
                        "echo_kind": "alliance_shift",
                        "label": f"{fac.get('name')} — {tick_key} rising",
                    }
                )

    return sources[:6]


def finalize_action_turn(
    replayability_state: Dict[str, Any],
    qualifying_sources: List[Mapping[str, Any]],
    turn_number: int,
) -> Dict[str, Any]:
    """Schedule echoes from post-guard structured sources; idempotent receipts only."""
    state = copy.deepcopy(replayability_state)
    echo_state = state.setdefault("consequence_echoes", echoes.init_consequence_echoes())
    processed = echoes.processed_source_event_ids(echo_state)
    added = echoes.schedule_from_structured_events(
        echo_state,
        qualifying_sources,
        turn_number,
        processed_source_ids=processed,
    )
    for entry in added:
        src = entry.get("source_event_id")
        if src:
            _append_transition_receipt(
                state,
                source_event_id=src,
                receipt_type="echo_scheduled",
                turn_number=turn_number,
            )
    return state


def merge_replayability_diagnostics(meta: Dict[str, Any], diagnostics: Dict[str, Any]) -> None:
    for key, value in diagnostics.items():
        meta[f"replayability_{key}"] = value


def strip_replayability_from_rolling(merged_rolling: Dict[str, Any]) -> List[str]:
    """Remove any model-emitted replayability fields from rolling_state."""
    if not isinstance(merged_rolling, dict):
        return []
    stripped: List[str] = []
    for key in list(merged_rolling.keys()):
        if key in ROLLING_REPLAYABILITY_KEYS:
            del merged_rolling[key]
            stripped.append(f"rolling_{key}_stripped")
    return stripped


def enforce_authoritative(
    merged_rolling: Dict[str, Any],
    authoritative_replayability: Optional[Mapping[str, Any]],
) -> List[str]:
    """
    Ensure rolling_state does not contain replayability engine ownership.

    Replayability truth lives on the session document only.
    """
    adjustments = strip_replayability_from_rolling(merged_rolling)
    if authoritative_replayability:
        auth_pg = (authoritative_replayability or {}).get("pressure_graph")
        if isinstance(auth_pg, dict) and isinstance(merged_rolling.get("pressure_graph"), dict):
            adjustments.extend(
                pressure_graph.strip_model_pressure_mutations(
                    merged_rolling["pressure_graph"], auth_pg
                )
            )
            del merged_rolling["pressure_graph"]
            adjustments.append("rolling_pressure_graph_stripped")
        if not is_closed_enum_identity((authoritative_replayability or {}).get("identity")):
            adjustments.append("replayability_identity_invalid_ignored")
    return adjustments


def replayability_active(session: Mapping[str, Any]) -> bool:
    """Policy A — only sessions with persisted replayability_state participate."""
    rb = session.get("replayability_state")
    return isinstance(rb, dict) and bool(rb.get("run_seed"))


def combine_directive_messages(directives: Mapping[str, str], *, include_opening: bool) -> List[str]:
    """Ordered directive bodies for _build_messages."""
    parts: List[str] = []
    if include_opening:
        opening = (directives.get("opening") or "").strip()
        if opening:
            parts.append(opening)
    pressure = (directives.get("pressure") or "").strip()
    if pressure:
        parts.append(pressure)
    echo = (directives.get("echo") or "").strip()
    if echo:
        parts.append(echo)
    return parts


# Explicitly unsupported in v1 — retained only so tests can assert zero events.
def structured_events_from_action(action_text: str) -> List[Dict[str, Any]]:
    """Deprecated no-op. Raw player text is never an authoritative event source."""
    return []