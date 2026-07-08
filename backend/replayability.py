"""
Replayability Engine v1 — orchestration, state container, directives, enforcement.

Session document field ``replayability_state`` owns replayability truth.
Legacy sessions without the field skip replayability processing (Policy A).

Canonical transitions live in rolling_state structures (relationship vectors,
faction ticks, delayed consequences) and pressure ``threshold_crossings``.
NPC move transition receipts live in ``replayability_state`` only — not
rolling_state and not a canonical event-sourcing log.
"""

from __future__ import annotations

import copy
import logging
import re
import uuid
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

import arc_diversity as arc
import ai_config
import consequence_echoes as echoes
import foundation_integration
import foundation_promotion
from foundation_snapshot import FoundationTurnSnapshot
import goal_engine
import information_engine
import investigation_engine
import living_cast_shadow
import living_cast_provenance as provenance
import npc_agendas as agendas
import npc_action_engine
import npc_world_moves as world_moves
import opening_state
import pressure_genesis
import pressure_graph
import relationships
import simulation_clock
import situation_engine
import stress
import world_event_engine
import world_state_consumers as world_consumers
from run_identity import derive_run_identity, is_closed_enum_identity

logger = logging.getLogger(__name__)

REPLAYABILITY_VERSION = 1
TRANSITION_RECEIPTS_MAX = 32
RELATIONSHIP_EFFECT_RECEIPTS_MAX = 32
MAX_ENGINE_WORLD_EVENTS = 24
# Documented hard budget for full replayability_state at simultaneous caps.
# Stage 5F adds bounded information/reputation state. The 500-turn harness peaks
# below 69 KiB with simultaneous late-stage receipts; 72 KiB preserves a strict
# envelope without forcing information caps to a non-useful size.
REPLAYABILITY_STATE_BUDGET_BYTES = 73_728

# Keys the LLM must never own in rolling_state. `pressure_graph` is stripped here
# and then re-added by `enforce_authoritative` as an engine-owned projection.
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
    "npc_agendas",
    "npc_actions",
    "active_npc_actions",
    "npc_action_receipts",
    "arc_diversity",
    "pending_npc_move",
    "engine_world_events",
    "world_events",
    "active_world_events",
    "world_event_receipts",
    "evidence",
    "investigations",
    "active_investigations",
    "investigation_receipts",
    "information_items",
    "active_information",
    "information_receipts",
    "reputation_signals",
    "active_reputation",
    "situations",
    "active_situations",
    "situation_receipts",
    "goals",
    "active_goals",
    "goal_receipts",
    "world_state_consumed_event_ids",
    "world_state_receipts",
    "world_state_guard_receipts",
    "npc_move_receipts",
})

DIRECTIVE_MARKERS = (
    opening_state.OPENING_DIRECTIVE_MARKER,
    pressure_graph.PRESSURE_DIRECTIVE_MARKER,
    echoes.ECHO_DIRECTIVE_MARKER,
    world_moves.NPC_WORLD_MOVE_MARKER,
)

DIRECTIVE_PROSE_PATTERNS = (
    r"INTERNAL\s+—\s+replayability\s+opening\s+contract",
    r"INTERNAL\s+—\s+foreground\s+pressure",
    r"INTERNAL\s+—\s+consequence\s+echo",
    r"INTERNAL\s+—\s+world\s+development",
    r"INTERNAL\s+—\s+primary\s+world\s+development",
    r"Immediate\s+problem:",
    r"Primary\s+pressure\s+kind:",
    r"Primary\s+beat:",
)


def _pick_diagnostic_identity(pick: Any) -> Dict[str, Optional[str]]:
    if not isinstance(pick, Mapping):
        return {"actor": None, "move": None, "target": None}
    actor = pick.get("actor_id") or pick.get("npc_id")
    move = pick.get("move_kind") or pick.get("action_kind")
    target = pick.get("target_id")
    return {
        "actor": str(actor) if actor else None,
        "move": str(move) if move else None,
        "target": str(target) if target else None,
    }


def _first_blocker_code(pick: Any) -> Optional[str]:
    if not isinstance(pick, Mapping):
        return None
    for key in ("blocker_code", "stress_blocker_code"):
        value = pick.get(key)
        if value:
            return str(value)
    blockers = pick.get("blocker_codes") or []
    if isinstance(blockers, (list, tuple)) and blockers:
        return str(blockers[0])
    if isinstance(blockers, str) and blockers:
        return blockers
    return None


def _build_utility_ai_live_diagnostics(
    comparison: Mapping[str, Any],
    *,
    enabled: bool,
    applied: bool,
    selected_move: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    heuristic = _pick_diagnostic_identity(comparison.get("heuristic_pick"))
    utility_pick = comparison.get("utility_pick") or {}
    utility = _pick_diagnostic_identity(utility_pick)
    replacement_authorised = utility_pick.get("replacement_authorised")
    selected_source = "utility_ai" if applied else "heuristic"
    diagnostics: Dict[str, Any] = {
        "utility_ai_shadow_comparison_exists": True,
        "utility_ai_shadow_candidate_count": int(comparison.get("candidate_count") or 0),
        "utility_ai_live_selection_enabled": bool(enabled),
        "utility_ai_live_selection_applied": bool(applied),
        "utility_ai_heuristic_winner_actor": heuristic["actor"],
        "utility_ai_heuristic_winner_move": heuristic["move"],
        "utility_ai_heuristic_winner_target": heuristic["target"],
        "utility_ai_utility_winner_actor": utility["actor"],
        "utility_ai_utility_winner_move": utility["move"],
        "utility_ai_utility_winner_target": utility["target"],
        "utility_ai_shadow_agreement": bool(comparison.get("agree")),
        "utility_ai_shadow_divergence": not bool(comparison.get("agree")),
        "utility_ai_replacement_authorised": replacement_authorised,
        "utility_ai_selected_live_winner_source": selected_source,
    }
    if replacement_authorised is False:
        diagnostics["utility_ai_replacement_blocker_code"] = (
            _first_blocker_code(utility_pick) or "replacement_not_authorised"
        )
    if isinstance(selected_move, Mapping) and selected_move.get("receipt_id"):
        diagnostics["utility_ai_selected_move_receipt_id"] = str(selected_move.get("receipt_id"))
    return {key: value for key, value in diagnostics.items() if value is not None}


def _attach_utility_ai_committed_move_diagnostics(
    diagnostics: Dict[str, Any],
    committed_move: Optional[Mapping[str, Any]],
) -> None:
    if not isinstance(committed_move, Mapping):
        return
    receipt_id = committed_move.get("receipt_id")
    if receipt_id:
        diagnostics["utility_ai_committed_move_receipt_id"] = str(receipt_id)


def _log_utility_ai_live_diagnostics(diagnostics: Mapping[str, Any]) -> None:
    if not ai_config.ENABLE_UTILITY_AI_DIAGNOSTIC_LOGS:
        return
    if "utility_ai_shadow_comparison" not in diagnostics:
        fields = {
            key: value
            for key, value in diagnostics.items()
            if key.startswith("utility_ai_")
        }
        logger.info("Utility AI live-selection diagnostic: no comparison this turn: %s", fields)
        return
    fields = {
        key: value
        for key, value in diagnostics.items()
        if key.startswith("utility_ai_") or key == "npc_move_receipt_emitted"
    }
    if diagnostics.get("utility_ai_shadow_candidate_count") == 0:
        logger.info(
            "Utility AI live-selection diagnostic: no eligible NPC move candidates this turn: %s",
            fields,
        )
        return
    logger.info("Utility AI live-selection diagnostic: %s", fields)

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
        "npc_agendas": agendas.init_npc_agendas(),
        "arc_diversity": arc.init_arc_diversity(),
        "frozen_npc_move": None,
        "npc_move_receipts": [],
        "npc_actions": [],
        "npc_action_receipts": [],
        "engine_world_events": [],
        "world_events": [],
        "world_event_receipts": [],
        "evidence": [],
        "investigations": [],
        "investigation_receipts": [],
        "information_items": [],
        "information_receipts": [],
        "reputation_signals": [],
        "situations": [],
        "situation_receipts": [],
        "goals": [],
        "goal_receipts": [],
        "world_state_consumed_event_ids": [],
        "world_state_receipts": [],
        "world_state_guard_receipts": [],
        "relationship_effect_receipts": [],
        "lc_relationship_applied_receipt_id": None,
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


def _append_engine_world_event(state: Dict[str, Any], event: Mapping[str, Any]) -> bool:
    event_id = str(event.get("event_id") or "").strip()
    if not event_id:
        return False
    events = state.setdefault("engine_world_events", [])
    if any(isinstance(row, dict) and row.get("event_id") == event_id for row in events):
        return False
    events.append(dict(event))
    if len(events) > MAX_ENGINE_WORLD_EVENTS:
        state["engine_world_events"] = events[-MAX_ENGINE_WORLD_EVENTS:]
    return True


def _engine_world_event_ids(state: Mapping[str, Any]) -> List[str]:
    return [
        str(row.get("event_id") or "")
        for row in state.get("engine_world_events") or []
        if isinstance(row, dict) and row.get("event_id")
    ]


def _pressure_mitigations_from_committed_move(
    committed_move: Optional[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    if not isinstance(committed_move, Mapping):
        return []
    effects = committed_move.get("effects") or (committed_move.get("receipt") or {}).get("effects") or []
    out: List[Dict[str, Any]] = []
    for effect in effects:
        if not isinstance(effect, Mapping) or effect.get("effect_type") != "pressure_magnitude":
            continue
        delta = int(effect.get("delta") or 0)
        if delta >= 0:
            continue
        out.append(
            {
                "pressure_node_id": str(effect.get("target_id") or ""),
                "delta": delta,
                "before": effect.get("before"),
                "after": effect.get("after"),
                "source_event_id": str(effect.get("effect_id") or committed_move.get("receipt_id") or ""),
            }
        )
    out.sort(key=lambda row: (row["pressure_node_id"], row["source_event_id"]))
    return out


def _pressure_event_to_echo_source(event: Mapping[str, Any]) -> Dict[str, Any]:
    label = str(event.get("pressure_event_kind") or "pressure consequence").replace("_", " ")
    return {
        "source_kind": "pressure_spawned_event",
        "source_event_id": str(event.get("event_id") or ""),
        "echo_kind": "pressure_world_consequence",
        "label": label[:80],
        "mature_in": 1,
    }


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


def _seed_structured_pressure_inputs(
    graph: Dict[str, Any],
    *,
    run_seed: str,
    custom_world_setup: Optional[Mapping[str, Any]],
    scenario: Optional[Mapping[str, Any]],
    created_turn: int = 1,
) -> None:
    if scenario and scenario.get("starting_pressure"):
        pressure_graph.upsert_pressure_node(
            graph,
            run_seed=run_seed,
            kind="danger",
            origin_type="scenario_pressure",
            origin_id=str(scenario.get("id") or "scenario_starting_pressure"),
            scope="local",
            magnitude=44,
            trend=0,
            turn_number=created_turn,
            tags=["scenario", "starting_pressure"],
            evidence_refs=[f"scenario:{scenario.get('id') or 'unknown'}:starting_pressure"],
            label=str(scenario.get("starting_pressure") or "")[:80],
        )

    if not isinstance(custom_world_setup, dict):
        pressure_graph.cap_pressure_graph(graph)
        return

    danger = custom_world_setup.get("danger")
    if danger:
        pressure_graph.upsert_pressure_node(
            graph,
            run_seed=run_seed,
            kind="danger",
            origin_type="custom_setup",
            origin_id="danger",
            scope="local",
            magnitude=46,
            trend=1,
            turn_number=created_turn,
            tags=["custom_setup", "danger"],
            evidence_refs=["custom_setup:danger"],
            label=str(danger)[:80],
        )

    pressures = custom_world_setup.get("pressures")
    if isinstance(pressures, list):
        for idx, item in enumerate(pressures[:3]):
            if not item:
                continue
            pressure_graph.upsert_pressure_node(
                graph,
                run_seed=run_seed,
                kind="unresolved_thread",
                origin_type="custom_setup",
                origin_id=f"pressure:{idx}",
                scope="local",
                magnitude=34 + idx * 3,
                trend=0,
                turn_number=created_turn,
                tags=["custom_setup", "pressure"],
                evidence_refs=[f"custom_setup:pressures:{idx}"],
                label=str(item)[:80],
            )
    pressure_graph.cap_pressure_graph(graph)


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
    npc_seed_records: Optional[List[Mapping[str, Any]]] = None,
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
    _seed_structured_pressure_inputs(
        pg,
        run_seed=seed,
        custom_world_setup=custom_world_setup,
        scenario=scenario,
        created_turn=1,
    )
    pressure_graph.select_foreground(pg, identity=identity, turn_number=1)
    echo_state = echoes.init_consequence_echoes()

    state: Dict[str, Any] = {
        "version": REPLAYABILITY_VERSION,
        "run_seed": seed,
        "identity": identity,
        "opening": opening,
        "pressure_graph": pg,
        "consequence_echoes": echo_state,
        "transition_receipts": [],
        "npc_agendas": agendas.init_npc_agendas(),
        "arc_diversity": arc.init_arc_diversity(),
        "frozen_npc_move": None,
        "npc_move_receipts": [],
        "npc_actions": [],
        "npc_action_receipts": [],
        "engine_world_events": [],
        "world_events": [],
        "world_event_receipts": [],
        "evidence": [],
        "investigations": [],
        "investigation_receipts": [],
        "information_items": [],
        "information_receipts": [],
        "reputation_signals": [],
        "situations": [],
        "situation_receipts": [],
        "goals": [],
        "goal_receipts": [],
        "world_state_consumed_event_ids": [],
        "world_state_receipts": [],
        "world_state_guard_receipts": [],
        "relationship_effect_receipts": [],
        "lc_relationship_applied_receipt_id": None,
    }

    effective_scenario_id = str(scenario_id or (scenario or {}).get("id") or "")
    seed_npcs: List[Mapping[str, Any]] = []
    if npc_seed_records:
        for idx, row in enumerate(npc_seed_records):
            if isinstance(row, dict):
                entry = dict(row)
                entry.setdefault("source_type", "seed_record")
                entry.setdefault("source_slot", idx)
                if effective_scenario_id:
                    entry.setdefault("scenario_id", effective_scenario_id)
                seed_npcs.append(entry)
    if scenario:
        for idx, row in enumerate(scenario.get("key_npcs") or []):
            if isinstance(row, dict) and row.get("name"):
                seed_npcs.append(
                    {
                        "name": row["name"],
                        "role": row.get("role"),
                        "source_type": "scenario",
                        "source_slot": idx,
                        "scenario_id": effective_scenario_id,
                    }
                )
    if seed_npcs:
        state["npc_agendas"] = agendas.seed_agendas_from_npcs(
            seed,
            seed_npcs,
            identity=identity,
            scenario_id=effective_scenario_id,
        )

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

    arc.record_beat(
        state["arc_diversity"],
        turn_number=1,
        kind="opening",
        subkind=str(opening.get("archetype_id") or "opening"),
        urgency=70,
    )

    directives = {
        "opening": opening_state.build_opening_directive(opening, identity, scenario=scenario),
        "world": "",
        "pressure": pressure_graph.build_pressure_directive(pg),
        "echo": "",
    }
    return state, directives


def _summarize_turn_authority(diagnostics: Mapping[str, Any]) -> Dict[str, Any]:
    """Compact per-turn authority summary — developer diagnostics only.

    Consolidates the actor/utility routing diagnostics already recorded this turn
    into a single authority-source view for replay inspection. Pure: reads only
    existing diagnostic values, never gameplay state and never the prompt. The
    surrounding turn.debug dict is developer-gated and excluded from player turns
    (see player_api.PLAYER_TURN_FIELDS), so this never leaks into the prompt.
    """
    actor_applied = bool(diagnostics.get("actor_resolution_applied"))
    actor_changed = bool(diagnostics.get("actor_resolution_changed"))
    memory = diagnostics.get("memory_retrieval_promotion") or {}
    return {
        "actor": {
            "enabled": bool(diagnostics.get("actor_resolution_enabled")),
            "applied": actor_applied,
            "changed": actor_changed,
            "source": (
                "canonical"
                if actor_changed
                else "canonical_confirmed"
                if actor_applied
                else "legacy"
            ),
            "reason": diagnostics.get("actor_resolution_reason"),
        },
        "utility": {
            "enabled": bool(diagnostics.get("utility_ai_live_selection_enabled")),
            "applied": bool(diagnostics.get("utility_ai_live_selection_applied")),
            "source": (
                "canonical"
                if diagnostics.get("utility_ai_live_selection_applied")
                else "legacy"
            ),
            "winner_source": diagnostics.get("utility_ai_selected_live_winner_source"),
            "diverged": bool(diagnostics.get("utility_ai_shadow_divergence")),
        },
        "memory": memory.get("memory_retrieval_blocker_code") or "shadow",
        "flags": diagnostics.get("foundation_promotion_flags"),
    }


def prepare_action_turn(
    replayability_state: Optional[Mapping[str, Any]],
    turn_number: int,
    rolling_state: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Tick pressure, mature echoes, fire at most one echo, build directives.

    Does NOT schedule new echoes from player text or narrative.
    Returns (updated_state, frozen_directives, diagnostics, threshold_events).
    """
    diagnostics: Dict[str, Any] = {}
    if not isinstance(replayability_state, dict) or not replayability_state.get("run_seed"):
        return {}, {"opening": "", "world": "", "pressure": "", "echo": ""}, diagnostics, [], {}

    state = copy.deepcopy(replayability_state)
    run_seed = str(state.get("run_seed") or "")
    identity = state.get("identity") or {}
    pg = state.setdefault("pressure_graph", pressure_graph.copy_pressure_graph(None))
    echo_state = state.setdefault("consequence_echoes", echoes.init_consequence_echoes())
    agendas_state = state.setdefault("npc_agendas", agendas.init_npc_agendas())
    arc_state = state.setdefault("arc_diversity", arc.init_arc_diversity())
    working_rolling = copy.deepcopy(rolling_state) if isinstance(rolling_state, dict) else {}

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

    agendas.tick_eligible_agendas(agendas_state, turn_number)
    committed_move: Optional[Dict[str, Any]] = None
    npc_action_result: Dict[str, Any] = {"actions": [], "events": [], "receipts": [], "diagnostics": {}}
    npc_action_recent: Optional[Dict[str, Any]] = None
    move, _candidates = world_moves.select_npc_move(
        run_seed, agendas_state, working_rolling, state, identity, turn_number
    )
    comparison: Optional[Dict[str, Any]] = None
    # Stage 3 promotion: canonical Utility AI live handoff. Either the canonical
    # flag or the legacy ENABLE_UTILITY_AI_LIVE_SELECTION alias engages it; the
    # shadow comparison below always runs regardless of the flag.
    utility_live = foundation_promotion.utility_live_enabled()
    try:
        selection_snapshot = FoundationTurnSnapshot.build(
            run_seed=run_seed,
            turn_sequence=turn_number,
            rolling_state=working_rolling,
            replayability_state=state,
        )
        comparison = living_cast_shadow.compare_move_scoring(
            selection_snapshot, _candidates, move
        )
        diagnostics["utility_ai_shadow_comparison"] = comparison
        move, utility_applied = living_cast_shadow.choose_live_move(
            _candidates,
            move,
            comparison,
            enabled=utility_live,
            run_seed=run_seed,
            turn_number=turn_number,
        )
        diagnostics.update(
            _build_utility_ai_live_diagnostics(
                comparison,
                enabled=utility_live,
                applied=utility_applied,
                selected_move=move,
            )
        )
    except Exception as exc:
        # Failed or unauthorised handoff falls back to the existing heuristic.
        diagnostics["utility_ai_shadow_error"] = str(exc)[:200]
        diagnostics["utility_ai_live_selection_enabled"] = utility_live
        diagnostics["utility_ai_live_selection_applied"] = False
        if isinstance(comparison, Mapping):
            diagnostics.update(
                _build_utility_ai_live_diagnostics(
                    comparison,
                    enabled=utility_live,
                    applied=False,
                    selected_move=move,
                )
            )
    # Stage 1 promotion: canonical Actor Resolution is the authority over WHO
    # acts this turn. Fail-closed — flag off or any error leaves the move
    # untouched. A re-picked candidate is given a receipt exactly like
    # select_npc_move so the commit path is unaffected.
    if foundation_promotion.actor_resolution_enabled():
        try:
            actor_snapshot = FoundationTurnSnapshot.build(
                run_seed=run_seed,
                turn_sequence=turn_number,
                rolling_state=working_rolling,
                replayability_state=state,
            )
            actor_prepared = foundation_promotion.compute_actor_resolution_prepared(
                actor_snapshot
            )
            routed_move, actor_diag = foundation_promotion.route_actor_move(
                move, _candidates, actor_prepared
            )
            diagnostics.update(actor_diag)
            if routed_move is not None and not routed_move.get("receipt_id"):
                routed_move = dict(routed_move)
                routed_move["receipt_id"] = world_moves.stable_receipt_id(
                    run_seed,
                    str(routed_move.get("npc_id") or ""),
                    str(routed_move.get("agenda_id") or ""),
                    str(routed_move.get("move_kind") or ""),
                    turn_number,
                    str(routed_move.get("target_id") or ""),
                )
                routed_move["turn"] = turn_number
            move = routed_move
        except Exception as exc:
            diagnostics["actor_resolution_error"] = str(exc)[:200]

    if move:
        agenda = agendas.get_agenda_by_npc_id(agendas_state, str(move.get("npc_id") or ""))
        if agenda and agendas.get_agenda_by_agenda_id(agendas_state, str(move.get("agenda_id") or "")):
            working_rolling, prepared = world_moves.commit_npc_move(
                move, agenda, working_rolling, state, run_seed, turn_number
            )
            if not prepared:
                committed_move = None
            else:
                committed_move = prepared
                state["frozen_npc_move"] = prepared
                diagnostics["npc_move_kind"] = move.get("move_kind")
                diagnostics["npc_move_receipt_emitted"] = True
                _attach_utility_ai_committed_move_diagnostics(
                    diagnostics,
                    committed_move,
                )
                _append_transition_receipt(
                    state,
                    source_event_id=str(move.get("receipt_id")),
                    receipt_type="npc_move_committed",
                    turn_number=turn_number,
                )
                echo_src = world_moves.move_to_echo_source(move)
                if echo_src and provenance.validate_provenance(echo_src):
                    processed = echoes.processed_source_event_ids(echo_state)
                    added = echoes.schedule_from_structured_events(
                        echo_state, [echo_src], turn_number, processed_source_ids=processed
                    )
                    if added:
                        _append_transition_receipt(
                            state,
                            source_event_id=echo_src["source_event_id"],
                            receipt_type="echo_scheduled",
                            turn_number=turn_number,
                        )

    npc_action_result = npc_action_engine.evolve_npc_actions(
        state,
        working_rolling,
        turn_number,
        run_seed=run_seed,
    )
    npc_action_diag = npc_action_result.get("diagnostics") or {}
    diagnostics.update(
        {
            key: value
            for key, value in npc_action_diag.items()
            if value not in (False, 0, None, [], {})
        }
    )
    added_action_events: List[Dict[str, Any]] = []
    for event in npc_action_result.get("events") or []:
        if isinstance(event, Mapping) and _append_engine_world_event(state, event):
            added_action_events.append(dict(event))
    if added_action_events:
        diagnostics["npc_action_engine_events_appended"] = len(added_action_events)
    for receipt in npc_action_result.get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        receipt_id = str(receipt.get("receipt_id") or "")
        if receipt_id:
            _append_transition_receipt(
                state,
                source_event_id=receipt_id,
                receipt_type=str(receipt.get("receipt_type") or "npc_action_evolved"),
                turn_number=turn_number,
            )
    npc_action_recent = npc_action_engine.latest_action_for_goal_engine(
        npc_action_result.get("actions") or []
    )

    pressure_mitigations = _pressure_mitigations_from_committed_move(committed_move)
    pressure_mitigations.extend(
        npc_action_engine.pressure_mitigations_from_events(added_action_events)
    )
    pressure_evolution = pressure_graph.evolve_pressure_graph(
        pg,
        turn_number,
        run_seed=run_seed,
        recent_mitigations=pressure_mitigations,
        existing_event_ids=_engine_world_event_ids(state),
        identity=identity,
    )
    pressure_evolution_receipts = pressure_evolution.get("receipts") or []
    pressure_spawned_events = pressure_evolution.get("events") or []
    if pressure_evolution_receipts:
        diagnostics["pressure_evolution_receipts"] = len(pressure_evolution_receipts)
    if pressure_evolution.get("evaluated_node_ids"):
        diagnostics["pressure_evolution_evaluated"] = len(pressure_evolution.get("evaluated_node_ids") or [])
    for receipt in pressure_evolution_receipts:
        if not isinstance(receipt, Mapping):
            continue
        source_id = str(receipt.get("event_id") or receipt.get("receipt_id") or "")
        if source_id:
            _append_transition_receipt(
                state,
                source_event_id=source_id,
                receipt_type=str(receipt.get("receipt_type") or "pressure_evolved"),
                turn_number=turn_number,
            )

    added_pressure_events: List[Dict[str, Any]] = []
    for event in pressure_spawned_events:
        if isinstance(event, Mapping) and _append_engine_world_event(state, event):
            added_pressure_events.append(dict(event))
    if added_pressure_events:
        diagnostics["pressure_spawned_events"] = len(added_pressure_events)
        processed = echoes.processed_source_event_ids(echo_state)
        echo_sources = [_pressure_event_to_echo_source(event) for event in added_pressure_events]
        echo_sources = [src for src in echo_sources if provenance.validate_provenance(src)]
        added = echoes.schedule_from_structured_events(
            echo_state,
            echo_sources,
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

    # Stage 6C-1: flag-gated deterministic pressure generation from existing
    # canonical signals (blocked goals, open investigations, overloaded actor
    # stress). With ENABLE_PRESSURE_GENESIS off (default), evolve_pressure_genesis
    # returns immediately and `state` is untouched -- the flag-off byte-identity
    # fingerprint gate (backend/tools/simulate_world.py) is the acceptance test
    # for this invariant, not a unit test mock.
    genesis_result = pressure_genesis.evolve_pressure_genesis(
        state,
        working_rolling,
        turn_number,
        run_seed=run_seed,
    )
    genesis_diag = genesis_result.get("diagnostics") or {}
    diagnostics.update(
        {
            key: value
            for key, value in genesis_diag.items()
            if value not in (False, 0, None, [], {})
        }
    )
    for receipt in genesis_result.get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        receipt_id = str(receipt.get("receipt_id") or "")
        if receipt_id:
            _append_transition_receipt(
                state,
                source_event_id=receipt_id,
                receipt_type=str(receipt.get("receipt_type") or "pressure_genesis_evolved"),
                turn_number=turn_number,
            )

    world_consumption = world_consumers.consume_pressure_world_events(
        state,
        working_rolling,
        turn_number,
    )
    world_diag = world_consumption.get("diagnostics") or {}
    diagnostics.update(
        {
            key: value
            for key, value in world_diag.items()
            if value not in (False, 0, None, [], {})
        }
    )
    for receipt in world_consumption.get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        receipt_id = str(receipt.get("receipt_id") or "")
        if receipt_id:
            _append_transition_receipt(
                state,
                source_event_id=receipt_id,
                receipt_type=str(receipt.get("receipt_type") or "world_state_consumed"),
                    turn_number=turn_number,
                )

    world_event_result = world_event_engine.evolve_world_events(
        state,
        working_rolling,
        turn_number,
        run_seed=run_seed,
    )
    world_event_diag = world_event_result.get("diagnostics") or {}
    diagnostics.update(
        {
            key: value
            for key, value in world_event_diag.items()
            if value not in (False, 0, None, [], {})
        }
    )
    added_world_event_events: List[Dict[str, Any]] = []
    for event in world_event_result.get("events") or []:
        if isinstance(event, Mapping) and _append_engine_world_event(state, event):
            added_world_event_events.append(dict(event))
    if added_world_event_events:
        diagnostics["world_event_engine_events_appended"] = len(added_world_event_events)
    for receipt in world_event_result.get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        receipt_id = str(receipt.get("receipt_id") or "")
        if receipt_id:
            _append_transition_receipt(
                state,
                source_event_id=receipt_id,
                receipt_type=str(receipt.get("receipt_type") or "world_event_evolved"),
                turn_number=turn_number,
            )

    if added_world_event_events:
        world_event_consumption = world_consumers.consume_pressure_world_events(
            state,
            working_rolling,
            turn_number,
        )
        world_event_consumer_diag = world_event_consumption.get("diagnostics") or {}
        diagnostics.update(
            {
                f"world_event_{key}": value
                for key, value in world_event_consumer_diag.items()
                if value not in (False, 0, None, [], {})
            }
        )
        for receipt in world_event_consumption.get("receipts") or []:
            if not isinstance(receipt, Mapping):
                continue
            receipt_id = str(receipt.get("receipt_id") or "")
            if receipt_id:
                _append_transition_receipt(
                    state,
                    source_event_id=receipt_id,
                    receipt_type=str(receipt.get("receipt_type") or "world_state_consumed"),
                    turn_number=turn_number,
                )

        pressure_from_world_events = pressure_graph.apply_world_event_engine_events(
            pg,
            added_world_event_events,
            turn_number,
            run_seed=run_seed,
        )
        pressure_world_event_receipts = pressure_from_world_events.get("receipts") or []
        if pressure_world_event_receipts:
            diagnostics["world_event_pressure_receipts"] = len(pressure_world_event_receipts)
        if pressure_from_world_events.get("applied_event_ids"):
            diagnostics["world_event_pressure_events_applied"] = len(
                pressure_from_world_events.get("applied_event_ids") or []
            )
        for receipt in pressure_world_event_receipts:
            if not isinstance(receipt, Mapping):
                continue
            source_id = str(receipt.get("event_id") or receipt.get("receipt_id") or "")
            if source_id:
                _append_transition_receipt(
                    state,
                    source_event_id=source_id,
                    receipt_type=str(receipt.get("receipt_type") or "pressure_evolved"),
                    turn_number=turn_number,
                )

    active_world_events = world_event_engine.project_active_world_events_for_rolling(state)
    if active_world_events:
        working_rolling["active_world_events"] = active_world_events
    else:
        working_rolling.pop("active_world_events", None)

    investigation_result = investigation_engine.evolve_investigations(
        state,
        working_rolling,
        turn_number,
        run_seed=run_seed,
    )
    investigation_diag = investigation_result.get("diagnostics") or {}
    diagnostics.update(
        {
            key: value
            for key, value in investigation_diag.items()
            if value not in (False, 0, None, [], {})
        }
    )
    for receipt in investigation_result.get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        receipt_id = str(receipt.get("receipt_id") or "")
        if receipt_id:
            _append_transition_receipt(
                state,
                source_event_id=receipt_id,
                receipt_type=str(receipt.get("receipt_type") or "investigation_evolved"),
                turn_number=turn_number,
            )
    active_investigations = investigation_engine.project_active_investigations_for_rolling(state)
    if active_investigations:
        working_rolling["active_investigations"] = active_investigations
    else:
        working_rolling.pop("active_investigations", None)

    information_result = information_engine.evolve_information(
        state,
        working_rolling,
        turn_number,
        run_seed=run_seed,
    )
    information_diag = information_result.get("diagnostics") or {}
    diagnostics.update(
        {
            key: value
            for key, value in information_diag.items()
            if value not in (False, 0, None, [], {})
        }
    )
    for receipt in information_result.get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        receipt_id = str(receipt.get("receipt_id") or "")
        if receipt_id:
            _append_transition_receipt(
                state,
                source_event_id=receipt_id,
                receipt_type=str(receipt.get("receipt_type") or "information_evolved"),
                turn_number=turn_number,
            )
    active_information = information_engine.project_active_information_for_rolling(
        state,
        rolling_state=working_rolling,
    )
    if active_information:
        working_rolling["active_information"] = active_information
    else:
        working_rolling.pop("active_information", None)
    active_reputation = information_engine.project_reputation_for_rolling(
        state,
        rolling_state=working_rolling,
    )
    if active_reputation:
        working_rolling["active_reputation"] = active_reputation
    else:
        working_rolling.pop("active_reputation", None)

    situation_result = situation_engine.evolve_situations(
        state,
        working_rolling,
        turn_number,
        run_seed=run_seed,
    )
    situation_diag = situation_result.get("diagnostics") or {}
    diagnostics.update(
        {
            key: value
            for key, value in situation_diag.items()
            if value not in (False, 0, None, [], {})
        }
    )
    for receipt in situation_result.get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        receipt_id = str(receipt.get("receipt_id") or "")
        if receipt_id:
            _append_transition_receipt(
                state,
                source_event_id=receipt_id,
                receipt_type=str(receipt.get("receipt_type") or "situation_evolved"),
                turn_number=turn_number,
            )
    active_situations = situation_engine.project_active_situations_for_rolling(state)
    if active_situations:
        working_rolling["active_situations"] = active_situations
    else:
        working_rolling.pop("active_situations", None)

    goal_result = goal_engine.evolve_goals(
        state,
        working_rolling,
        turn_number,
        run_seed=run_seed,
        recent_action=npc_action_recent or committed_move,
    )
    goal_diag = goal_result.get("diagnostics") or {}
    diagnostics.update(
        {
            key: value
            for key, value in goal_diag.items()
            if value not in (False, 0, None, [], {})
        }
    )
    for receipt in goal_result.get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        receipt_id = str(receipt.get("receipt_id") or "")
        if receipt_id:
            _append_transition_receipt(
                state,
                source_event_id=receipt_id,
                receipt_type=str(receipt.get("receipt_type") or "goal_evolved"),
                turn_number=turn_number,
            )
    active_goals = goal_engine.project_active_goals_for_rolling(state)
    if active_goals:
        working_rolling["active_goals"] = active_goals
    else:
        working_rolling.pop("active_goals", None)
    active_npc_actions = npc_action_engine.project_active_npc_actions_for_rolling(state)
    if active_npc_actions:
        working_rolling["active_npc_actions"] = active_npc_actions
    else:
        working_rolling.pop("active_npc_actions", None)

    _log_utility_ai_live_diagnostics(diagnostics)

    pressure_body = pressure_graph.build_pressure_directive(pg)
    echo_body = echoes.build_echo_directive(echo_state, fired_this_turn=fired_echo if did_fire else None)
    move_body = world_moves.build_move_directive(committed_move) if committed_move else ""

    beat_candidates: List[Dict[str, Any]] = []
    if committed_move:
        beat_candidates.append(
            {
                "kind": "npc_move",
                "subkind": str(committed_move.get("move_kind") or ""),
                "urgency": 75 if committed_move.get("move_kind") == "defect" else 55,
                "directive": move_body,
            }
        )
    if fired_echo and did_fire:
        beat_candidates.append(
            {
                "kind": "echo",
                "subkind": str(fired_echo.get("kind") or "echo"),
                "urgency": 85,
                "directive": echo_body,
            }
        )
    fg_id = pg.get("foreground_node_id")
    if fg_id:
        for node in pg.get("nodes") or []:
            if isinstance(node, dict) and node.get("id") == fg_id:
                beat_candidates.append(
                    {
                        "kind": "pressure",
                        "subkind": str(node.get("kind") or "pressure"),
                        "urgency": int(node.get("magnitude") or 40),
                        "directive": pressure_body,
                    }
                )
                break

    primary = arc.select_primary_beat(beat_candidates, arc_state, identity=identity)
    supporting: Dict[str, str] = {}
    if primary:
        arc.record_beat(
            arc_state,
            turn_number=turn_number,
            kind=str(primary.get("kind") or ""),
            subkind=str(primary.get("subkind") or ""),
            urgency=int(primary.get("urgency") or 50),
        )
    pk = str((primary or {}).get("kind") or "")
    if pressure_body and pk != "pressure":
        supporting["pressure"] = pressure_body
    if echo_body and did_fire and pk != "echo":
        supporting["echo"] = echo_body

    world_directive = arc.build_world_development_directive(primary, supporting)
    if primary and primary.get("directive") and pk == "npc_move":
        world_directive = str(primary.get("directive") or world_directive)

    directives = {
        "opening": "",
        "world": world_directive,
        "pressure": pressure_body if pk == "pressure" else "",
        "echo": echo_body if pk == "echo" and did_fire else "",
    }

    # Ch 14 P1 — authoritative per-actor stress update. Runs before the
    # foundation snapshot is built so stress_level flows into utility inputs.
    # Pure/deterministic; intentionally NOT inside the foundation swallow-all
    # try/except — a stress failure is a real determinism bug we must surface.
    agendas_by_actor = {
        str(row.get("npc_id") or ""): row
        for row in (agendas_state.get("agendas") or agendas_state.get("active") or [])
        if isinstance(row, dict) and row.get("npc_id")
    }
    stress.update_actor_stress(
        working_rolling,
        pg,
        run_seed=run_seed,
        turn_sequence=turn_number,
        agendas_by_actor=agendas_by_actor,
    )

    try:
        foundation_bundle, foundation_diag = foundation_integration.evaluate_foundation_turn(
            run_seed=run_seed,
            turn_sequence=turn_number,
            rolling_state=working_rolling,
            replayability_state=state,
            prior_foundation_state=state.get("foundation_prepared_v1"),
            developer_mode=False,
        )
        diagnostics.update(foundation_diag)
        state = foundation_integration.apply_prepared_to_replayability_state(state, foundation_bundle)
    except Exception as exc:
        diagnostics["foundation_eval_error"] = str(exc)[:200]

    # Developer-only consolidated authority view (dev debug; never player-visible).
    diagnostics["foundation_turn_authority"] = _summarize_turn_authority(diagnostics)

    # Chapter 33 lifecycle structured-clock seam.
    # Flag-gated (ENABLE_NPC_LIFECYCLE, default OFF -> complete no-op) and
    # fail-closed. Time advances only from an engine-owned structured event in
    # state["pending_time_advance"]; ordinary turns advance the clock by zero.
    try:
        state, working_rolling, sim_lifecycle_diag = simulation_clock.integrate_turn(
            state,
            working_rolling,
            run_seed=run_seed,
            turn_number=turn_number,
            append_receipt=_append_transition_receipt,
        )
        diagnostics.update(sim_lifecycle_diag)
    except Exception as exc:
        diagnostics["simulation_lifecycle_error"] = str(exc)[:200]

    return state, directives, diagnostics, threshold_fired, working_rolling


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


def evolve_agendas_from_sources(
    replayability_state: Dict[str, Any],
    sources: List[Mapping[str, Any]],
    turn_number: int,
) -> None:
    agendas_state = replayability_state.setdefault("npc_agendas", agendas.init_npc_agendas())
    validated = provenance.filter_provenance_sources(sources, turn_number)
    for agenda in agendas_state.get("active") or []:
        if not isinstance(agenda, dict):
            continue
        for src in validated:
            agendas.evolve_agenda_from_structured_event(agenda, src, turn_number)


def _append_relationship_effect_receipt(
    state: Dict[str, Any],
    receipt: Mapping[str, Any],
) -> bool:
    receipts = state.setdefault("relationship_effect_receipts", [])
    rid = receipt.get("receipt_id")
    if rid and any(isinstance(r, dict) and r.get("receipt_id") == rid for r in receipts):
        return False
    receipts.append(dict(receipt))
    if len(receipts) > RELATIONSHIP_EFFECT_RECEIPTS_MAX:
        state["relationship_effect_receipts"] = receipts[-RELATIONSHIP_EFFECT_RECEIPTS_MAX:]
    return True


def finalize_living_cast_relationships(
    replayability_state: Dict[str, Any],
    merged_rolling: Dict[str, Any],
    turn_number: int,
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Apply frozen Living Cast relationship effects once after legacy calculus.

    Authoritative order tail:
      4. apply frozen LC relationship deltas exactly once
      5-6. clamp + derive state (inside relationships module)
      7. LC threshold effect receipts from LC before/after only
    """
    state = copy.deepcopy(replayability_state)
    frozen = state.get("frozen_npc_move")
    if not isinstance(frozen, dict):
        return state, []

    receipt_id = str(frozen.get("receipt_id") or "")
    if receipt_id and state.get("lc_relationship_applied_receipt_id") == receipt_id:
        return state, []

    effects = frozen.get("effects") or (frozen.get("receipt") or {}).get("effects") or []
    rel_effects = [
        e for e in effects
        if isinstance(e, dict) and e.get("defer_finalize")
    ]
    if not rel_effects:
        if receipt_id:
            state["lc_relationship_applied_receipt_id"] = receipt_id
        return state, []

    adjustments, threshold_receipts = relationships.apply_living_cast_relationship_effects(
        merged_rolling,
        rel_effects,
        turn_number=turn_number,
    )
    for receipt in threshold_receipts:
        _append_relationship_effect_receipt(state, receipt)
    if receipt_id:
        state["lc_relationship_applied_receipt_id"] = receipt_id
    state["frozen_npc_move"] = None
    return state, adjustments


def serialize_state_json(value: Any) -> bytes:
    """Production JSON serialization policy for replayability_state sizing."""
    import json

    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def replayability_state_byte_size(replayability_state: Optional[Mapping[str, Any]]) -> int:
    if not isinstance(replayability_state, dict):
        return 0
    return len(serialize_state_json(replayability_state))


def living_cast_state_metrics(
    replayability_state: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """
    Serialized UTF-8 byte sizes with fixture counts.

    Uses compact JSON (``,`` separators, sorted keys) matching session persistence.
    """
    if not isinstance(replayability_state, dict):
        return {}
    agendas_state = replayability_state.get("npc_agendas") or {}
    active = agendas_state.get("active") or []
    archived = agendas_state.get("archived") or []
    move_receipts = replayability_state.get("npc_move_receipts") or []
    npc_actions = replayability_state.get("npc_actions") or []
    npc_action_receipts = replayability_state.get("npc_action_receipts") or []
    rel_receipts = replayability_state.get("relationship_effect_receipts") or []
    situations = replayability_state.get("situations") or []
    situation_receipts = replayability_state.get("situation_receipts") or []
    goals = replayability_state.get("goals") or []
    goal_receipts = replayability_state.get("goal_receipts") or []
    world_events = replayability_state.get("world_events") or []
    world_event_receipts = replayability_state.get("world_event_receipts") or []
    evidence = replayability_state.get("evidence") or []
    investigations = replayability_state.get("investigations") or []
    investigation_receipts = replayability_state.get("investigation_receipts") or []
    information_items = replayability_state.get("information_items") or []
    information_receipts = replayability_state.get("information_receipts") or []
    reputation_signals = replayability_state.get("reputation_signals") or []
    arc_state = replayability_state.get("arc_diversity") or {}
    arc_beats = arc_state.get("recent_beats") or []
    echo_state = replayability_state.get("consequence_echoes") or {}
    pressure = replayability_state.get("pressure_graph") or {}

    slices = {
        "active_agendas": (active, len(active)),
        "archived_agendas": (archived, len(archived)),
        "npc_move_receipts": (move_receipts, len(move_receipts)),
        "npc_actions": (npc_actions, len(npc_actions)),
        "npc_action_receipts": (npc_action_receipts, len(npc_action_receipts)),
        "relationship_effect_receipts": (rel_receipts, len(rel_receipts)),
        "situations": (situations, len(situations)),
        "situation_receipts": (situation_receipts, len(situation_receipts)),
        "goals": (goals, len(goals)),
        "goal_receipts": (goal_receipts, len(goal_receipts)),
        "world_events": (world_events, len(world_events)),
        "world_event_receipts": (world_event_receipts, len(world_event_receipts)),
        "evidence": (evidence, len(evidence)),
        "investigations": (investigations, len(investigations)),
        "investigation_receipts": (investigation_receipts, len(investigation_receipts)),
        "information_items": (information_items, len(information_items)),
        "information_receipts": (information_receipts, len(information_receipts)),
        "reputation_signals": (reputation_signals, len(reputation_signals)),
        "arc_diversity_beats": (arc_beats, len(arc_beats)),
        "pressure_graph": (pressure, len(pressure.get("nodes") or [])),
        "consequence_echoes": (
            echo_state,
            len(echo_state.get("scheduled") or [])
            + len(echo_state.get("pending") or [])
            + len(echo_state.get("fired") or []),
        ),
        "full_replayability_state": (replayability_state, 1),
    }
    metrics: Dict[str, Any] = {}
    for key, (val, count) in slices.items():
        metrics[key] = {
            "count": count,
            "bytes": len(serialize_state_json(val)),
        }
    metrics["budget_bytes"] = REPLAYABILITY_STATE_BUDGET_BYTES
    metrics["within_budget"] = metrics["full_replayability_state"]["bytes"] <= REPLAYABILITY_STATE_BUDGET_BYTES
    return metrics


def finalize_action_turn(
    replayability_state: Dict[str, Any],
    qualifying_sources: List[Mapping[str, Any]],
    turn_number: int,
) -> Dict[str, Any]:
    """Schedule echoes from post-guard structured sources; idempotent receipts only."""
    state = copy.deepcopy(replayability_state)
    echo_state = state.setdefault("consequence_echoes", echoes.init_consequence_echoes())
    validated = provenance.filter_provenance_sources(qualifying_sources, turn_number)
    processed = echoes.processed_source_event_ids(echo_state)
    added = echoes.schedule_from_structured_events(
        echo_state,
        validated,
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
    evolve_agendas_from_sources(state, qualifying_sources, turn_number)
    information_result = information_engine.evolve_information(
        state,
        {},
        turn_number,
        run_seed=str(state.get("run_seed") or ""),
        structured_sources=validated,
    )
    for receipt in information_result.get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        receipt_id = str(receipt.get("receipt_id") or "")
        if receipt_id:
            _append_transition_receipt(
                state,
                source_event_id=receipt_id,
                receipt_type=str(receipt.get("receipt_type") or "information_evolved"),
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
    Ensure rolling_state contains only engine-owned replayability projections.

    Replayability truth lives on the session document; rolling_state gets a
    capped pressure_graph projection so retrieval/prompt-state consumers can
    read pressure without trusting model output.
    """
    adjustments = strip_replayability_from_rolling(merged_rolling)
    if authoritative_replayability:
        auth_pg = (authoritative_replayability or {}).get("pressure_graph")
        if isinstance(auth_pg, dict):
            merged_rolling["pressure_graph"] = pressure_graph.project_pressure_graph_for_rolling(auth_pg)
            adjustments.append("rolling_pressure_graph_engine_derived")
            # ADR-023: active_pressures is a read-only projection of the canonical
            # pressure_graph; overwrite any model-emitted value so pressure has a
            # single authoritative source (no narrative/LLM pressure authority).
            merged_rolling["active_pressures"] = pressure_graph.project_active_pressures(auth_pg)
            adjustments.append("rolling_active_pressures_engine_derived")
        active_situations = situation_engine.project_active_situations_for_rolling(
            authoritative_replayability
        )
        if active_situations:
            merged_rolling["active_situations"] = active_situations
            adjustments.append("rolling_active_situations_engine_derived")
        elif "active_situations" in merged_rolling:
            merged_rolling.pop("active_situations", None)
            adjustments.append("rolling_active_situations_engine_cleared")
        active_goals = goal_engine.project_active_goals_for_rolling(authoritative_replayability)
        if active_goals:
            merged_rolling["active_goals"] = active_goals
            adjustments.append("rolling_active_goals_engine_derived")
        elif "active_goals" in merged_rolling:
            merged_rolling.pop("active_goals", None)
            adjustments.append("rolling_active_goals_engine_cleared")
        active_npc_actions = npc_action_engine.project_active_npc_actions_for_rolling(
            authoritative_replayability
        )
        if active_npc_actions:
            merged_rolling["active_npc_actions"] = active_npc_actions
            adjustments.append("rolling_active_npc_actions_engine_derived")
        elif "active_npc_actions" in merged_rolling:
            merged_rolling.pop("active_npc_actions", None)
            adjustments.append("rolling_active_npc_actions_engine_cleared")
        active_world_events = world_event_engine.project_active_world_events_for_rolling(
            authoritative_replayability
        )
        if active_world_events:
            merged_rolling["active_world_events"] = active_world_events
            adjustments.append("rolling_active_world_events_engine_derived")
        elif "active_world_events" in merged_rolling:
            merged_rolling.pop("active_world_events", None)
            adjustments.append("rolling_active_world_events_engine_cleared")
        active_investigations = investigation_engine.project_active_investigations_for_rolling(
            authoritative_replayability
        )
        if active_investigations:
            merged_rolling["active_investigations"] = active_investigations
            adjustments.append("rolling_active_investigations_engine_derived")
        elif "active_investigations" in merged_rolling:
            merged_rolling.pop("active_investigations", None)
            adjustments.append("rolling_active_investigations_engine_cleared")
        active_information = information_engine.project_active_information_for_rolling(
            authoritative_replayability,
            rolling_state=merged_rolling,
        )
        if active_information:
            merged_rolling["active_information"] = active_information
            adjustments.append("rolling_active_information_engine_derived")
        elif "active_information" in merged_rolling:
            merged_rolling.pop("active_information", None)
            adjustments.append("rolling_active_information_engine_cleared")
        active_reputation = information_engine.project_reputation_for_rolling(
            authoritative_replayability,
            rolling_state=merged_rolling,
        )
        if active_reputation:
            merged_rolling["active_reputation"] = active_reputation
            adjustments.append("rolling_active_reputation_engine_derived")
        elif "active_reputation" in merged_rolling:
            merged_rolling.pop("active_reputation", None)
            adjustments.append("rolling_active_reputation_engine_cleared")
        adjustments.extend(agendas.strip_model_agenda_mutations(merged_rolling, authoritative_replayability))
        if not is_closed_enum_identity((authoritative_replayability or {}).get("identity")):
            adjustments.append("replayability_identity_invalid_ignored")
    return adjustments


def replayability_active(session: Mapping[str, Any]) -> bool:
    """Policy A — only sessions with persisted replayability_state participate."""
    rb = session.get("replayability_state")
    return isinstance(rb, dict) and bool(rb.get("run_seed"))


def combine_directive_messages(directives: Mapping[str, str], *, include_opening: bool) -> List[str]:
    """Ordered directive bodies for _build_messages after secret reveal."""
    parts: List[str] = []
    if include_opening:
        opening = (directives.get("opening") or "").strip()
        if opening:
            parts.append(opening)
    world = (directives.get("world") or "").strip()
    if world:
        parts.append(world)
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
