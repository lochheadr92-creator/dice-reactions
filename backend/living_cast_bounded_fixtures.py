"""
Deterministic maximum-cap fixtures for Living Cast bounded-state audit.

All values use production schemas with documented caps — no inflated strings.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Mapping, Optional

import arc_diversity as arc
import consequence_echoes as echoes
import npc_agendas as agendas
import npc_world_moves as world_moves
import pressure_graph
import replayability

SEED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

CAP_ACTIVE_AGENDAS = agendas.MAX_ACTIVE_AGENDAS
CAP_ARCHIVED_AGENDAS = agendas.MAX_ARCHIVED_SUMMARIES
CAP_MOVE_RECEIPTS = world_moves.MAX_NPC_MOVE_RECEIPTS
CAP_REL_EFFECT_RECEIPTS = replayability.RELATIONSHIP_EFFECT_RECEIPTS_MAX
CAP_ARC_BEATS = arc.MAX_RECENT_BEATS
CAP_ECHO_SCHEDULED = echoes.MAX_SCHEDULED
CAP_ECHO_FIRED = echoes.MAX_FIRED_LOG
CAP_PRESSURE_NODES = pressure_graph.MAX_ACTIVE_NODES
CAP_THRESHOLD_RECEIPTS = pressure_graph.MAX_THRESHOLD_RECEIPTS


def _npc_id(slot: int) -> str:
    digest = hashlib.sha256(f"scenario:seed_record:{slot}:npc-{slot}".encode()).hexdigest()
    return f"npc-{digest[:12]}"


def _agenda_record(slot: int) -> Dict[str, Any]:
    npc_id = _npc_id(slot)
    return agendas._new_agenda(
        SEED,
        npc_id,
        display_name=f"NPC-{slot}",
        role_hint=f"role-{slot % 5}",
        relationship_state="neutral",
    )


def build_active_agendas_at_cap() -> List[Dict[str, Any]]:
    return [_agenda_record(i) for i in range(CAP_ACTIVE_AGENDAS)]


def build_archived_agendas_at_cap() -> List[Dict[str, Any]]:
    return [
        {
            "npc_id": _npc_id(100 + i),
            "goal_kind": agendas.GOAL_KINDS[i % len(agendas.GOAL_KINDS)],
            "final_progress": 70 + (i % 20),
        }
        for i in range(CAP_ARCHIVED_AGENDAS)
    ]


def build_move_receipt_at_index(i: int, *, compressed: bool = False) -> Dict[str, Any]:
    npc_id = _npc_id(i % CAP_ACTIVE_AGENDAS)
    agenda_id = agendas.agenda_id(npc_id)
    move_kind = world_moves.MOVE_KINDS[i % len(world_moves.MOVE_KINDS)]
    target_type = "player" if move_kind in ("protect", "pressure", "conceal") else "faction"
    target_id = "player" if target_type == "player" else world_moves._faction_id("Syndicate")
    receipt_id = f"npc-move-{i:04d}"
    effect_ids = [f"fx:{move_kind}:{target_type}:{target_id}"]
    stub = {
        "version": world_moves.NPC_MOVE_RECEIPT_VERSION,
        "receipt_id": receipt_id,
        "receipt_type": "npc_move_committed",
        "turn": 2 + (i % 40),
        "npc_id": npc_id,
        "agenda_id": agenda_id,
        "move_kind": move_kind,
        "target_type": target_type,
        "target_id": target_id,
        "effect_ids": effect_ids,
        "observable_template_id": world_moves.observable_template_id(move_kind, target_type, target_id),
    }
    if compressed:
        stub["compressed"] = True
        return stub
    stub["effects"] = [
        {
            "effect_id": effect_ids[0],
            "effect_type": "agenda_progress",
            "target_id": agenda_id,
            "delta": 8,
            "before": 20,
            "after": 28,
        },
        {
            "effect_id": f"fx:{move_kind}:relationship_delta:{target_id}:trust",
            "effect_type": "relationship_delta",
            "target_name": f"NPC-{i % CAP_ACTIVE_AGENDAS}",
            "dimension": "trust",
            "delta": -3,
            "before": 10,
            "after": 7,
            "defer_finalize": True,
        },
    ]
    return stub


def build_move_receipts_at_cap(*, compressed_count: int = 0) -> List[Dict[str, Any]]:
    full_count = CAP_MOVE_RECEIPTS - compressed_count
    receipts = [build_move_receipt_at_index(i) for i in range(full_count)]
    receipts.extend(
        build_move_receipt_at_index(full_count + i, compressed=True)
        for i in range(compressed_count)
    )
    return receipts[-CAP_MOVE_RECEIPTS:]


def build_relationship_effect_receipt_at_index(i: int) -> Dict[str, Any]:
    """Minimal threshold transition only — not a duplicate of move effect bundle."""
    return {
        "receipt_id": f"rel-fx-{i:04d}",
        "receipt_type": "living_cast_relationship_threshold",
        "turn": 3 + (i % 30),
        "npc_name": f"NPC-{i % CAP_ACTIVE_AGENDAS}",
        "before_state": "resentful",
        "after_state": "betrayal_risk",
        "source_effect_id": f"fx:pressure:relationship_delta:player:resentment",
    }


def build_relationship_effect_receipts_at_cap() -> List[Dict[str, Any]]:
    return [build_relationship_effect_receipt_at_index(i) for i in range(CAP_REL_EFFECT_RECEIPTS)]


def build_arc_beats_at_cap() -> List[Dict[str, Any]]:
    beats = []
    for i in range(CAP_ARC_BEATS):
        beats.append(
            {
                "turn": i + 1,
                "kind": arc.BEAT_KINDS[i % len(arc.BEAT_KINDS)],
                "subkind": world_moves.MOVE_KINDS[i % len(world_moves.MOVE_KINDS)],
                "urgency": 40 + (i % 40),
            }
        )
    return beats


def build_echo_entry(
    i: int,
    *,
    bucket: str,
    receipt_id: Optional[str] = None,
) -> Dict[str, Any]:
    rid = receipt_id or f"npc-move-{i:04d}"
    echo_kind = echoes.ECHO_KINDS[i % len(echoes.ECHO_KINDS)]
    entry = {
        "id": echoes.echo_id_for_source(rid, echo_kind),
        "kind": echo_kind,
        "label": echo_kind.replace("_", " ")[:40],
        "source_event_id": rid,
        "source_kind": "npc_world_move",
        "scheduled_turn": 2 + i,
        "mature_turn": 4 + i,
        "source_provenance": {
            "npc_id": _npc_id(i % CAP_ACTIVE_AGENDAS),
            "agenda_id": agendas.agenda_id(_npc_id(i % CAP_ACTIVE_AGENDAS)),
            "move_kind": world_moves.MOVE_KINDS[i % len(world_moves.MOVE_KINDS)],
            "target_type": "player",
            "target_id": "player",
        },
    }
    if bucket == "fired":
        entry["fired_turn"] = 5 + i
    return entry


def build_echoes_at_cap() -> Dict[str, Any]:
    state = echoes.init_consequence_echoes()
    state["scheduled"] = [
        build_echo_entry(i, bucket="scheduled") for i in range(CAP_ECHO_SCHEDULED)
    ]
    state["pending"] = [
        build_echo_entry(i + CAP_ECHO_SCHEDULED, bucket="pending")
        for i in range(min(4, CAP_ECHO_SCHEDULED))
    ]
    state["fired"] = [
        build_echo_entry(i, bucket="fired") for i in range(CAP_ECHO_FIRED)
    ]
    state["last_fired_turn"] = 40
    return state


def build_pressure_graph_at_cap() -> Dict[str, Any]:
    state, _ = replayability.init_new_story(
        genre="noir",
        role="detective",
        tone="grim",
        difficulty="standard",
        scenario_id=None,
        custom_premise=None,
        custom_world_setup=None,
        run_seed=SEED,
    )
    graph = state["pressure_graph"]
    nodes = graph.get("nodes") or []
    pressure_kinds = ("resource", "social", "environmental", "bodily")
    while len([n for n in nodes if n.get("status") == "active"]) < CAP_PRESSURE_NODES:
        idx = len(nodes)
        kind = pressure_kinds[idx % len(pressure_kinds)]
        node_id = pressure_graph.stable_pressure_id(SEED, kind, "fixture", f"origin-{idx}", str(idx))
        nodes.append(
            pressure_graph._new_node(
                node_id,
                kind=kind,
                origin_type="fixture",
                origin_id=f"origin-{idx}",
                scope="local",
                magnitude=30 + idx * 3,
                trend=idx % 3 - 1,
                created_turn=1,
                label=f"{kind} pressure {idx}",
            )
        )
    graph["nodes"] = nodes[:CAP_PRESSURE_NODES]
    crossings = []
    for i in range(CAP_THRESHOLD_RECEIPTS):
        crossings.append(
            {
                "event_id": f"evt-threshold-fix-{i:03d}",
                "kind": "pressure_threshold_crossed",
                "pressure_kind": pressure_kinds[i % len(pressure_kinds)],
                "node_id": graph["nodes"][i % len(graph["nodes"])]["id"],
                "turn": 2 + i,
            }
        )
    graph["threshold_crossings"] = crossings
    graph["tick"] = 50
    return graph


def build_replayability_state_at_all_caps(
    *,
    move_compressed_count: int = 8,
) -> Dict[str, Any]:
    """Fully populated replayability_state at simultaneous documented caps."""
    base, _ = replayability.init_new_story(
        genre="noir",
        role="detective",
        tone="grim",
        difficulty="standard",
        scenario_id=None,
        custom_premise=None,
        custom_world_setup=None,
        run_seed=SEED,
    )
    base["npc_agendas"] = {
        "version": agendas.AGENDA_VERSION,
        "active": build_active_agendas_at_cap(),
        "archived": build_archived_agendas_at_cap(),
    }
    base["npc_move_receipts"] = build_move_receipts_at_cap(compressed_count=move_compressed_count)
    base["relationship_effect_receipts"] = build_relationship_effect_receipts_at_cap()
    base["arc_diversity"] = {
        "version": arc.ARC_VERSION,
        "recent_beats": build_arc_beats_at_cap(),
        "last_primary_kind": "npc_move",
        "repeat_count": 2,
    }
    base["consequence_echoes"] = build_echoes_at_cap()
    base["pressure_graph"] = build_pressure_graph_at_cap()
    base["transition_receipts"] = [
        {
            "source_event_id": f"evt-transition-{i:03d}",
            "receipt_type": "echo_scheduled",
            "turn": 2 + i,
        }
        for i in range(replayability.TRANSITION_RECEIPTS_MAX)
    ]
    return base


def build_max_living_cast_directive() -> str:
    move = {
        "display_name": "Marlene Cho",
        "observable_template_id": "defect_faction",
        "move_kind": "defect",
    }
    return world_moves.build_move_directive(move)


def build_max_opening_plus_living_cast_directive() -> str:
    _, directives = replayability.init_new_story(
        genre="noir",
        role="detective",
        tone="grim",
        difficulty="standard",
        scenario_id=None,
        custom_premise="A long-running syndicate war tests every alliance.",
        custom_world_setup=None,
        run_seed=SEED,
        npc_seed_records=[
            {"name": f"NPC-{i}", "source_type": "seed_record", "source_slot": i}
            for i in range(CAP_ACTIVE_AGENDAS)
        ],
    )
    opening = directives.get("opening") or ""
    world = build_max_living_cast_directive()
    pressure = directives.get("pressure") or ""
    return "\n\n".join(p for p in (opening, world, pressure) if p)