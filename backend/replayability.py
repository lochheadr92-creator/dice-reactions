"""
Replayability Engine v1 — orchestration, state container, directives, enforcement.

Session document field ``replayability_state`` (NOT rolling_state).
Legacy sessions without the field skip replayability processing (Policy A).

Canonical transitions live in rolling_state structures (relationship vectors,
faction ticks, delayed consequences) and pressure ``threshold_crossings``.
NPC move transition receipts live in ``replayability_state`` only — not
rolling_state and not a canonical event-sourcing log.
"""

from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

import arc_diversity as arc
import consequence_echoes as echoes
import foundation_integration
import living_cast_provenance as provenance
import npc_agendas as agendas
import npc_world_moves as world_moves
import opening_state
import pressure_graph
import relationships
import stress
from run_identity import derive_run_identity, is_closed_enum_identity

REPLAYABILITY_VERSION = 1
TRANSITION_RECEIPTS_MAX = 32
RELATIONSHIP_EFFECT_RECEIPTS_MAX = 32
# Documented hard budget for full replayability_state at simultaneous caps.
# Measured capped fixture ~53 KiB; 64 KiB leaves ~21% headroom without truncation.
REPLAYABILITY_STATE_BUDGET_BYTES = 65_536

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
    "npc_agendas",
    "arc_diversity",
    "pending_npc_move",
    "engine_world_events",
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
    move, _candidates = world_moves.select_npc_move(
        run_seed, agendas_state, working_rolling, state, identity, turn_number
    )
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
    rel_receipts = replayability_state.get("relationship_effect_receipts") or []
    arc_state = replayability_state.get("arc_diversity") or {}
    arc_beats = arc_state.get("recent_beats") or []
    echo_state = replayability_state.get("consequence_echoes") or {}
    pressure = replayability_state.get("pressure_graph") or {}

    slices = {
        "active_agendas": (active, len(active)),
        "archived_agendas": (archived, len(archived)),
        "npc_move_receipts": (move_receipts, len(move_receipts)),
        "relationship_effect_receipts": (rel_receipts, len(rel_receipts)),
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