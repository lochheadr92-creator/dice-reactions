"""
Seeded Living Cast scenario — deterministic early-move proof (turn 2).

Guarantees a single dominant `gather` move against a resource pressure node.
No relationship-dependent scoring; no player-keyword dependency.
"""

from __future__ import annotations

import copy
import hashlib
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple

import npc_agendas as agendas
import npc_world_moves as world_moves
import pressure_graph
import replayability

# Fixed run seed for reproducible preflight and live manifest pinning.
PROOF_RUN_SEED = "lc-proof-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PROOF_SCENARIO_ID = "living-cast-proof"
PROOF_NPC_NAME = "Marlene Cho"
PROOF_NPC_ROLE = "neighbour engineer"
PROOF_SCENE = "dock warehouse"
PROOF_RESOURCE_PRESSURE_ID = "pressure-resource-lcproof01"
PROOF_EARLIEST_TURN = 2
INTENDED_MOVE_KIND = "gather"
INTENDED_EFFECT_TYPE = "pressure_magnitude"
INTENDED_EFFECT_DIRECTION = "decrease"

# Neutral turn-1 player actions — must not manipulate LC selection inputs.
RECOMMENDED_NEUTRAL_ACTIONS = (
    "I wait and listen.",
    "I look around the room.",
    "I stay where I am and observe.",
)


class MoveSelectionDeviation(str, Enum):
    PREFLIGHT_ERROR = "PREFLIGHT_ERROR"
    EXPECTED_ENGINE_DRIFT = "EXPECTED_ENGINE_DRIFT"
    UNEXPECTED_ENGINE_DRIFT = "UNEXPECTED_ENGINE_DRIFT"
    PROSE_DERIVED_STATE_PERTURBATION = "PROSE_DERIVED_STATE_PERTURBATION"
    SELECTION_IMPLEMENTATION_DEFECT = "SELECTION_IMPLEMENTATION_DEFECT"
    UNVERIFIED = "UNVERIFIED"


class NarrativeSurfacing(str, Enum):
    CORRECTLY_NARRATED = "CORRECTLY_NARRATED"
    WEAKLY_NARRATED = "WEAKLY_NARRATED"
    OMITTED = "OMITTED"
    CONTRADICTED = "CONTRADICTED"


LIVING_CAST_PROOF_SCENARIO: Dict[str, Any] = {
    "id": PROOF_SCENARIO_ID,
    "title": "Living Cast Proof Scenario",
    "pitch": "Deterministic harness scenario for early NPC world-move verification.",
    "genre": "noir",
    "role": "investigator",
    "tone": "grounded",
    "difficulty": "standard",
    "mode": "advanced",
    "starting_location": PROOF_SCENE,
    "starting_pressure": "A resource shortage tightens supply lines near the dock.",
    "key_npcs": [
        {
            "name": PROOF_NPC_NAME,
            "role": PROOF_NPC_ROLE,
            "stance": "ally",
        }
    ],
    "starting_inventory": "Carried: flashlight. Stored: none. Worn: coat. Load: light.",
    "hidden_threat": "A syndicate quietly monitors dock traffic.",
    "seed": (
        "The story opens in the dock warehouse. Marlene Cho is present and alert. "
        "Supply pressure is visible but no confrontation occurs yet."
    ),
}


def proof_canonical_npc_id() -> str:
    return agendas.canonical_npc_id(
        source_type="scenario",
        source_slot=0,
        name=PROOF_NPC_NAME,
        role=PROOF_NPC_ROLE,
        scenario_id=PROOF_SCENARIO_ID,
    )


def proof_agenda_id() -> str:
    return agendas.agenda_id(proof_canonical_npc_id())


def build_proof_rolling_state() -> Dict[str, Any]:
    """Authoritative rolling_state immediately before turn-2 prepare_action_turn."""
    return {
        "scene": PROOF_SCENE,
        "location": PROOF_SCENE,
        "npcs": [
            {
                "name": PROOF_NPC_NAME,
                "stance": "ally",
                "last_seen": PROOF_SCENE,
            }
        ],
        "relationship_vectors": [
            {
                "name": PROOF_NPC_NAME,
                "trust": 0,
                "loyalty": 30,
                "fear": 0,
                "resentment": 12,
                "state": "neutral",
                "bond": "neutral",
            }
        ],
        "faction_pressure": [
            {"name": "Syndicate", "ticks": {"suspicion": 0, "goodwill": 0}}
        ],
    }


def _inject_resource_pressure(replayability_state: Dict[str, Any]) -> str:
    pg = replayability_state.setdefault("pressure_graph", pressure_graph.copy_pressure_graph(None))
    nodes = list(pg.get("nodes") or [])
    nodes = [n for n in nodes if isinstance(n, dict) and n.get("kind") != "resource"]
    nodes.insert(
        0,
        pressure_graph._new_node(
            PROOF_RESOURCE_PRESSURE_ID,
            kind="resource",
            origin_type="scenario_pressure",
            origin_id="lc-proof-resource",
            scope="local",
            magnitude=42,
            trend=-1,
            created_turn=1,
            label="dock supply shortage",
        ),
    )
    pg["nodes"] = nodes[: pressure_graph.MAX_ACTIVE_NODES]
    pg["tick"] = 1
    return PROOF_RESOURCE_PRESSURE_ID


def build_proof_replayability_state() -> Dict[str, Any]:
    """Session replayability_state for turn-2 preflight (post opening, pre action-2)."""
    state, _ = replayability.init_new_story(
        genre=LIVING_CAST_PROOF_SCENARIO["genre"],
        role=LIVING_CAST_PROOF_SCENARIO["role"],
        tone=LIVING_CAST_PROOF_SCENARIO["tone"],
        difficulty=LIVING_CAST_PROOF_SCENARIO["difficulty"],
        scenario_id=PROOF_SCENARIO_ID,
        custom_premise=None,
        custom_world_setup=None,
        scenario=LIVING_CAST_PROOF_SCENARIO,
        run_seed=PROOF_RUN_SEED,
    )
    _inject_resource_pressure(state)
    active = state.get("npc_agendas", {}).get("active") or []
    if len(active) != 1:
        raise RuntimeError(f"proof fixture requires exactly one agenda, got {len(active)}")
    agenda = active[0]
    agenda["goal_kind"] = "secure_resources"
    agenda["last_move_turn"] = -10
    agenda["move_count"] = 0
    agenda["progress"] = 20
    agenda["status"] = "active"
    agenda["breaking_fired"] = False
    expected_npc = proof_canonical_npc_id()
    if agenda.get("npc_id") != expected_npc:
        raise RuntimeError(f"npc_id mismatch: {agenda.get('npc_id')} != {expected_npc}")
    return state


def explain_score_components(
    move_kind: str,
    agenda: Mapping[str, Any],
    *,
    tier: str,
    target_type: str,
    rolling: Mapping[str, Any],
    identity: Mapping[str, Any],
    turn_number: int,
) -> Dict[str, Any]:
    """Document score components for preflight (mirrors score_move)."""
    components: Dict[str, Any] = {
        "tier": tier,
        "tier_priority": world_moves.TIER_PRIORITY.get(tier, 0),
        "goal_kind": agenda.get("goal_kind"),
        "goal_aligned": agenda.get("goal_kind") in world_moves.MOVE_GOAL_ALIGN.get(move_kind, frozenset()),
        "relationship_contributes": False,
        "relationship_bonus": 0,
        "identity_bonus": 0,
        "fear_bonus": 0,
        "breaking_bonus": 0,
        "recency_penalty": 0,
    }
    if not components["goal_aligned"]:
        return {**components, "total": -1, "ineligible": "goal_misaligned"}

    total = int(components["tier_priority"])
    if components["goal_aligned"]:
        total += 20
    fear = str(agenda.get("fear_kind") or "")
    if move_kind == "withdraw" and fear in ("captivity", "injury", "abandonment"):
        components["fear_bonus"] = 12
        total += 12
    if move_kind == "conceal" and fear in ("exposure", "hidden_truth_revealed"):
        components["fear_bonus"] = 10
        total += 10
    if move_kind == "defect" and agenda.get("breaking_fired"):
        components["breaking_bonus"] = 25
        total += 25

    vec, _ = agendas.resolve_relationship_vector(str(agenda.get("npc_id") or ""), agenda, rolling)
    if vec:
        resentment = int(vec.get("resentment") or 0)
        loyalty = int(vec.get("loyalty") or 0)
        if move_kind == "pressure":
            components["relationship_contributes"] = True
            components["relationship_bonus"] = min(15, resentment // 5)
            total += components["relationship_bonus"]
        if move_kind == "protect" and target_type == "player":
            components["relationship_contributes"] = True
            components["relationship_bonus"] = min(12, loyalty // 8)
            total += components["relationship_bonus"]

    if identity.get("echo_bias") == "betrayals" and move_kind == "defect":
        components["identity_bonus"] += 6
        total += 6
    if identity.get("primary_pressure_kind") == "social" and move_kind in ("negotiate", "pressure"):
        components["identity_bonus"] += 5
        total += 5

    last = int(agenda.get("last_move_turn") or 0)
    if turn_number - last <= 2:
        components["recency_penalty"] = 15
        total -= 15

    components["total"] = total
    return components


def run_move_preflight(*, turn_number: int = PROOF_EARLIEST_TURN) -> Dict[str, Any]:
    """
    Deterministic pre-turn-2 selection proof.

    Returns a complete preflight record for live-gate comparison.
    """
    replayability_state = build_proof_replayability_state()
    rolling = build_proof_rolling_state()
    identity = replayability_state.get("identity") or {}
    agendas_state = replayability_state["npc_agendas"]
    agenda = agendas_state["active"][0]

    tier = world_moves.resolve_actor_tier(
        str(agenda["npc_id"]), PROOF_NPC_NAME, rolling, turn_number
    )
    target = world_moves.resolve_move_target(INTENDED_MOVE_KIND, agenda, rolling, replayability_state)
    if not target:
        raise RuntimeError("intended gather target could not be resolved")

    target_type, target_id = target
    bundle, bundle_err = world_moves.compute_effect_bundle(
        {
            "move_kind": INTENDED_MOVE_KIND,
            "target_type": target_type,
            "target_id": target_id,
            "npc_id": agenda["npc_id"],
            "agenda_id": agenda["agenda_id"],
        },
        agenda,
        rolling,
        replayability_state,
        turn_number,
    )

    all_candidates = world_moves.enumerate_move_candidates(
        PROOF_RUN_SEED,
        agendas_state,
        rolling,
        replayability_state,
        identity,
        turn_number,
    )
    move, truncated_candidates = world_moves.select_npc_move(
        PROOF_RUN_SEED,
        agendas_state,
        rolling,
        replayability_state,
        identity,
        turn_number,
    )
    candidates = all_candidates

    score_table = []
    for cand in candidates:
        score_table.append(
            {
                "move_kind": cand["move_kind"],
                "target_type": cand["target_type"],
                "target_id": cand["target_id"],
                "tier": cand.get("tier"),
                "score": cand.get("score"),
                "tie": cand.get("tie"),
                "components": explain_score_components(
                    cand["move_kind"],
                    agenda,
                    tier=str(cand.get("tier") or ""),
                    target_type=str(cand.get("target_type") or ""),
                    rolling=rolling,
                    identity=identity,
                    turn_number=turn_number,
                ),
            }
        )

    winner_score = int((move or {}).get("score") or -1)
    runner_up_score = int(candidates[1]["score"]) if len(candidates) > 1 else -1
    margin = winner_score - runner_up_score if runner_up_score >= 0 else winner_score

    drift_checks = _simulate_bounded_drift(
        replayability_state,
        rolling,
        identity,
        turn_number,
        expected_winner=move,
    )

    pressure_effect = next(
        (e for e in (bundle or []) if e.get("effect_type") == INTENDED_EFFECT_TYPE),
        None,
    )

    inputs_hash = preflight_selection_inputs_hash(replayability_state, rolling, turn_number)

    return {
        "run_seed": PROOF_RUN_SEED,
        "selection_inputs_hash": inputs_hash,
        "scenario_id": PROOF_SCENARIO_ID,
        "turn_number": turn_number,
        "canonical_npc_id": proof_canonical_npc_id(),
        "agenda_id": proof_agenda_id(),
        "intended_move_kind": INTENDED_MOVE_KIND,
        "intended_target_type": target_type,
        "intended_target_id": target_id,
        "intended_effect_type": INTENDED_EFFECT_TYPE,
        "intended_effect_direction": INTENDED_EFFECT_DIRECTION,
        "earliest_eligible_turn": PROOF_EARLIEST_TURN,
        "actor_tier": tier,
        "candidate_score_table": score_table,
        "winner": move,
        "score_margin_over_runner_up": margin,
        "candidate_count": len(all_candidates),
        "truncated_candidate_count": len(truncated_candidates),
        "relationship_contributes_to_intended_score": False,
        "state_fields_may_change_before_selection": [
            "pressure_graph.nodes[].magnitude (tick_pressure_graph)",
            "pressure_graph.nodes[].trend",
            "npc_agendas.active[].progress (tick_eligible_agendas)",
            "relationship_vectors (legacy calculus on prior turn — does not affect gather score)",
        ],
        "drift_checks": drift_checks,
        "effect_bundle_ok": bundle_err is None and bool(bundle),
        "expected_pressure_delta": int((pressure_effect or {}).get("delta") or 0),
        "recommended_neutral_actions": list(RECOMMENDED_NEUTRAL_ACTIONS),
        "preflight_pass": (
            move is not None
            and move.get("move_kind") == INTENDED_MOVE_KIND
            and move.get("target_type") == "pressure"
            and move.get("target_id") == PROOF_RESOURCE_PRESSURE_ID
            and len(candidates) >= 1
            and (len(candidates) == 1 or margin > 0 or winner_score > runner_up_score)
            and drift_checks.get("winner_unchanged_under_drift") is True
        ),
    }


def _simulate_bounded_drift(
    replayability_state: Dict[str, Any],
    rolling: Dict[str, Any],
    identity: Mapping[str, Any],
    turn_number: int,
    *,
    expected_winner: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Prove plausible pre-selection drift does not change the winner."""
    rb = copy.deepcopy(replayability_state)
    roll = copy.deepcopy(rolling)

    pressure_graph.tick_pressure_graph(rb["pressure_graph"], turn_number, identity=identity)
    agendas.tick_eligible_agendas(rb["npc_agendas"], turn_number)
    move_after_tick, _ = world_moves.select_npc_move(
        PROOF_RUN_SEED, rb["npc_agendas"], roll, rb, identity, turn_number
    )

    roll_rel = copy.deepcopy(rolling)
    vec = roll_rel["relationship_vectors"][0]
    vec["trust"] = 50
    vec["resentment"] = 80
    move_after_rel, _ = world_moves.select_npc_move(
        PROOF_RUN_SEED, rb["npc_agendas"], roll_rel, rb, identity, turn_number
    )

    ag = rb["npc_agendas"]["active"][0]
    ag_progress = copy.deepcopy(rb)
    ag_progress["npc_agendas"]["active"][0]["progress"] = min(99, int(ag.get("progress") or 0) + 5)
    move_after_progress, _ = world_moves.select_npc_move(
        PROOF_RUN_SEED, ag_progress["npc_agendas"], roll, ag_progress, identity, turn_number
    )

    def _same(a: Optional[Mapping[str, Any]], b: Optional[Mapping[str, Any]]) -> bool:
        if not a or not b:
            return a is b
        keys = ("move_kind", "target_type", "target_id", "npc_id")
        return all(a.get(k) == b.get(k) for k in keys)

    return {
        "winner_unchanged_after_pressure_tick": _same(expected_winner, move_after_tick),
        "winner_unchanged_after_relationship_shift": _same(expected_winner, move_after_rel),
        "winner_unchanged_after_agenda_progress": _same(expected_winner, move_after_progress),
        "winner_unchanged_under_drift": (
            _same(expected_winner, move_after_tick)
            and _same(expected_winner, move_after_rel)
            and _same(expected_winner, move_after_progress)
        ),
    }


def diagnose_move_selection_deviation(
    preflight: Mapping[str, Any],
    live: Mapping[str, Any],
) -> Tuple[MoveSelectionDeviation, str]:
    """
    Classify live vs preflight move-selection deviation (exactly one cause).
    """
    if not live.get("state_lineage_captured"):
        return MoveSelectionDeviation.UNVERIFIED, "required state lineage not captured"

    if live.get("selection_inputs_hash") and preflight.get("selection_inputs_hash"):
        if live["selection_inputs_hash"] == preflight["selection_inputs_hash"]:
            if live.get("winner") != preflight.get("winner"):
                return (
                    MoveSelectionDeviation.SELECTION_IMPLEMENTATION_DEFECT,
                    "same deterministic inputs produced different winner",
                )
        else:
            if live.get("documented_drift_reason"):
                return (
                    MoveSelectionDeviation.EXPECTED_ENGINE_DRIFT,
                    str(live["documented_drift_reason"]),
                )
            if live.get("prose_mutated_authoritative_fields"):
                return (
                    MoveSelectionDeviation.PROSE_DERIVED_STATE_PERTURBATION,
                    "player text or narrative altered authoritative selection inputs",
                )
            return (
                MoveSelectionDeviation.UNEXPECTED_ENGINE_DRIFT,
                "authoritative inputs changed without documented cause",
            )

    if not preflight.get("preflight_pass"):
        return MoveSelectionDeviation.PREFLIGHT_ERROR, "preflight fixture failed before live run"

    if live.get("winner") == preflight.get("winner"):
        return MoveSelectionDeviation.PREFLIGHT_ERROR, "no deviation to classify"

    return MoveSelectionDeviation.UNVERIFIED, "insufficient comparison fields"


def preflight_selection_inputs_hash(
    replayability_state: Mapping[str, Any],
    rolling: Mapping[str, Any],
    turn_number: int,
) -> str:
    """Stable hash of inputs that drive select_npc_move."""
    payload = {
        "turn": turn_number,
        "run_seed": PROOF_RUN_SEED,
        "agendas": replayability_state.get("npc_agendas"),
        "pressure_nodes": (replayability_state.get("pressure_graph") or {}).get("nodes"),
        "rolling": {
            "scene": rolling.get("scene"),
            "npcs": rolling.get("npcs"),
            "deceased": rolling.get("deceased"),
            "relationship_vectors": rolling.get("relationship_vectors"),
            "faction_pressure": rolling.get("faction_pressure"),
        },
        "identity": replayability_state.get("identity"),
    }
    digest = hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()
    return digest[:16]


def _env_config_row(
    name: str,
    *,
    env_var: str,
    code_default: Any,
    effective_value: Any,
    source: str,
    tag: str,
) -> Dict[str, Any]:
    return {
        "parameter": name,
        "effective_value": effective_value,
        "env_var": env_var,
        "code_default": code_default,
        "deployment_may_override": True,
        "source": source,
        "pinned": tag,
    }


def collect_sampling_provenance() -> List[Dict[str, Any]]:
    """Audit sampling parameters — no live provider calls."""
    import ai_config
    import ai_service

    return [
        _env_config_row(
            "model",
            env_var="DEFAULT_MODEL",
            code_default="anthropic/claude-3-5-haiku",
            effective_value=ai_config.DEFAULT_MODEL,
            source="ai_config.py",
            tag="PINNED_IN_CONFIG",
        ),
        _env_config_row(
            "temperature",
            env_var="DEFAULT_TEMPERATURE",
            code_default=0.85,
            effective_value=ai_service.DEFAULT_TEMPERATURE,
            source="ai_service.py",
            tag="PINNED_IN_CONFIG",
        ),
        _env_config_row(
            "max_tokens",
            env_var="DEFAULT_MAX_TOKENS",
            code_default=2048,
            effective_value=ai_service.DEFAULT_MAX_TOKENS,
            source="ai_service.py",
            tag="PINNED_IN_CONFIG",
        ),
        _env_config_row(
            "timeout_seconds",
            env_var="PROVIDER_TIMEOUT",
            code_default=180.0,
            effective_value=ai_config.PROVIDER_TIMEOUT,
            source="ai_config.py",
            tag="PINNED_IN_CONFIG",
        ),
        _env_config_row(
            "max_retries_per_model",
            env_var="MAX_RETRIES",
            code_default=2,
            effective_value=ai_config.MAX_RETRIES,
            source="ai_config.py",
            tag="PINNED_IN_CONFIG",
        ),
        _env_config_row(
            "fallback_models",
            env_var="FALLBACK_MODELS",
            code_default=",".join(
                [
                    "anthropic/claude-3-5-haiku",
                    "anthropic/claude-3-5-sonnet",
                    "gryphe/mythomax-l2-13b",
                ]
            ),
            effective_value=",".join(ai_config.FALLBACK_MODELS),
            source="ai_config.py",
            tag="PINNED_IN_CONFIG",
        ),
        {
            "parameter": "top_p",
            "effective_value": None,
            "env_var": None,
            "code_default": None,
            "deployment_may_override": False,
            "source": "ai_service.py _call_model_once",
            "pinned": "INHERITED_PROVIDER_DEFAULT",
        },
        {
            "parameter": "provider_seed",
            "effective_value": None,
            "env_var": None,
            "code_default": None,
            "deployment_may_override": False,
            "source": "ai_service.py _call_model_once payload",
            "pinned": "NOT_SENT",
        },
    ]


def live_gate_manifest() -> Dict[str, Any]:
    """Manifest for live acceptance gate (engine run seed ≠ model sampling seed)."""
    preflight = run_move_preflight()
    return {
        "engine_run_seed": PROOF_RUN_SEED,
        "model_sampling_seed": None,
        "sampling_note": (
            "Engine run seed pins replayability/Living Cast only. "
            "Temperature is PINNED_IN_CONFIG but top_p is INHERITED_PROVIDER_DEFAULT; "
            "model output is not fully reproducible at the sampling layer."
        ),
        "scenario_id": PROOF_SCENARIO_ID,
        "preflight": preflight,
        "sampling_provenance": collect_sampling_provenance(),
        "narrative_surfacing_rules": {k: k for k in NarrativeSurfacing.__members__},
        "deviation_taxonomy": {k: k for k in MoveSelectionDeviation.__members__},
    }