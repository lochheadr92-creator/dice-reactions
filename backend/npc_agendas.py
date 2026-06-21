"""
Persistent NPC Agendas v1 — engine-owned goals stored in replayability_state.

Canonical NPC identity is stable across run seeds. Run seed varies agenda
selection only: run_seed + canonical_npc_id + namespace.
"""

from __future__ import annotations

import copy
import hashlib
import re
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from run_identity import select_from_namespace

AGENDA_VERSION = 1
MAX_ACTIVE_AGENDAS = 12
MAX_ARCHIVED_SUMMARIES = 8
PROGRESS_MAX = 100

GOAL_KINDS = (
    "secure_resources",
    "protect_person",
    "protect_location",
    "gain_influence",
    "uncover_truth",
    "escape_danger",
    "repay_debt",
    "preserve_faction",
    "remove_rival",
    "restore_loss",
)

FEAR_KINDS = (
    "abandonment",
    "starvation",
    "exposure",
    "loss_of_control",
    "betrayal",
    "captivity",
    "disgrace",
    "injury",
    "faction_collapse",
    "hidden_truth_revealed",
)

LEVERAGE_KINDS = (
    "supplies",
    "information",
    "reputation",
    "access",
    "force",
    "technical_skill",
    "social_bond",
    "faction_support",
    "safe_location",
    "transport",
)

BREAKING_POINTS = (
    "trust_collapse",
    "fear_threshold",
    "resource_crisis",
    "ally_harmed",
    "faction_order",
    "repeated_failure",
    "public_humiliation",
    "secret_exposure",
)

PLAN_KINDS = (
    "gather",
    "protect",
    "investigate",
    "negotiate",
    "pressure",
    "conceal",
    "fortify",
    "withdraw",
    "defect",
)

CLOSED_AGENDA_ENUMS = {
    "goal_kind": GOAL_KINDS,
    "fear_kind": FEAR_KINDS,
    "leverage_kind": LEVERAGE_KINDS,
    "breaking_point": BREAKING_POINTS,
    "plan_kind": PLAN_KINDS,
}


def init_npc_agendas() -> Dict[str, Any]:
    return {"version": AGENDA_VERSION, "active": [], "archived": []}


def normalize_npc_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def canonical_npc_id(
    *,
    source_type: str,
    source_slot: int,
    name: str,
    role: str = "",
    scenario_id: str = "",
) -> str:
    """
    Stable NPC identity — never includes run seed, turn, or relationship values.

    Hierarchy when explicit npc_id absent:
    1. scenario: scenario_id + slot + normalized name + role
    2. seed_record: source_type + slot + normalized name + role
    """
    norm_name = normalize_npc_name(name)
    norm_role = re.sub(r"\s+", " ", (role or "").strip().lower())[:80]
    payload = f"{source_type}:{scenario_id}:{int(source_slot)}:{norm_name}:{norm_role}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"npc-{digest[:12]}"


def agenda_id(npc_id: str) -> str:
    digest = hashlib.sha256(f"{npc_id}:agenda:v{AGENDA_VERSION}".encode("utf-8")).hexdigest()
    return f"agenda-{digest[:12]}"


def derive_canonical_npc_id(
    record: Mapping[str, Any],
    *,
    source_slot: int = 0,
    scenario_id: str = "",
) -> Optional[str]:
    """Return canonical npc_id or None when the record is not safely grounded."""
    explicit = str(record.get("npc_id") or record.get("actor_id") or "").strip()
    if explicit.startswith("npc-"):
        return explicit
    name = str(record.get("name") or record.get("display_name") or "").strip()
    if len(name) < 2:
        return None
    source_type = str(record.get("source_type") or ("scenario" if scenario_id else "")).strip()
    if not source_type:
        return None
    slot = record.get("source_slot")
    if slot is None:
        slot = source_slot
    return canonical_npc_id(
        source_type=source_type,
        source_slot=int(slot),
        name=name,
        role=str(record.get("role") or "")[:80],
        scenario_id=scenario_id or str(record.get("scenario_id") or ""),
    )


def resolve_relationship_vector(
    npc_id: str,
    agenda: Mapping[str, Any],
    rolling: Mapping[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Adapter: canonical agenda → name-keyed relationship_vectors row.

    Rejects ambiguous duplicate names; never merges same-named NPCs.
    """
    _ = npc_id
    name_key = normalize_npc_name(str(agenda.get("display_name") or ""))
    if not name_key:
        return None, "no_display_name"
    matches = [
        v
        for v in rolling.get("relationship_vectors") or []
        if isinstance(v, dict) and normalize_npc_name(str(v.get("name", ""))) == name_key
    ]
    if len(matches) > 1:
        return None, "ambiguous_name"
    if len(matches) == 1:
        return matches[0], None
    return None, "not_found"


def _clamp_progress(value: int) -> int:
    return max(0, min(PROGRESS_MAX, int(value)))


def _new_agenda(
    run_seed: str,
    npc_id: str,
    *,
    display_name: str = "",
    role_hint: str = "",
    relationship_state: str = "neutral",
) -> Dict[str, Any]:
    mixed = hashlib.sha256(f"{run_seed}:{npc_id}".encode("utf-8")).hexdigest()
    goal = select_from_namespace(mixed, "agenda_goal", GOAL_KINDS)
    fear = select_from_namespace(mixed, "agenda_fear", FEAR_KINDS)
    leverage = select_from_namespace(mixed, "agenda_leverage", LEVERAGE_KINDS)
    breaking = select_from_namespace(mixed, "agenda_breaking", BREAKING_POINTS)
    plan = select_from_namespace(mixed, "agenda_plan", PLAN_KINDS)
    if relationship_state in ("hostile", "betrayal_risk", "collapsed"):
        goal = select_from_namespace(
            mixed, "agenda_goal_hostile", ("remove_rival", "escape_danger", "preserve_faction")
        )
    return {
        "version": AGENDA_VERSION,
        "npc_id": npc_id,
        "agenda_id": agenda_id(npc_id),
        "display_name": (display_name or npc_id)[:80],
        "role_hint": (role_hint or "")[:80],
        "goal_kind": goal,
        "fear_kind": fear,
        "leverage_kind": leverage,
        "loyalty_target_id": "player",
        "breaking_point": breaking,
        "plan_kind": plan,
        "progress": 15,
        "status": "active",
        "last_move_turn": 0,
        "move_count": 0,
        "breaking_fired": False,
    }


def seed_agendas_from_npcs(
    run_seed: str,
    npc_records: List[Mapping[str, Any]],
    *,
    identity: Optional[Mapping[str, Any]] = None,
    relationship_vectors: Optional[List[Mapping[str, Any]]] = None,
    rolling_state: Optional[Mapping[str, Any]] = None,
    scenario_id: str = "",
) -> Dict[str, Any]:
    """Seed at most one agenda per canonical NPC ID. Ungrounded records are skipped."""
    state = init_npc_agendas()
    import npc_liveness
    rel_by_name = {
        normalize_npc_name(str(v.get("name", ""))): v
        for v in relationship_vectors or []
        if isinstance(v, dict) and v.get("name")
    }
    seen: Set[str] = set()
    for idx, raw in enumerate(npc_records or []):
        if not isinstance(raw, dict):
            continue
        npc_id = str(raw.get("npc_id") or "").strip()
        if not npc_id.startswith("npc-"):
            npc_id = derive_canonical_npc_id(raw, source_slot=idx, scenario_id=scenario_id) or ""
        if not npc_id or npc_id in seen:
            continue
        seen.add(npc_id)
        name = str(raw.get("name") or raw.get("display_name") or "").strip()
        if rolling_state is not None and not npc_liveness.is_npc_alive(name, rolling_state):
            continue
        rel = rel_by_name.get(normalize_npc_name(name), {})
        agenda = _new_agenda(
            run_seed,
            npc_id,
            display_name=name,
            role_hint=str(raw.get("role") or "")[:80],
            relationship_state=str(rel.get("state") or "neutral"),
        )
        if identity and identity.get("primary_pressure_kind") == "resource":
            agenda["goal_kind"] = select_from_namespace(
                hashlib.sha256(f"{run_seed}:{npc_id}:bias".encode()).hexdigest(),
                "goal_bias",
                ("secure_resources", "restore_loss", "repay_debt"),
            )
        state["active"].append(agenda)
        if len(state["active"]) >= MAX_ACTIVE_AGENDAS:
            break
    return state


def evolve_agenda_from_structured_event(
    agenda: Dict[str, Any],
    event: Mapping[str, Any],
    turn_number: int,
) -> List[str]:
    """Mutate agenda only from structured engine events. Returns adjustment tags."""
    adjustments: List[str] = []
    kind = str(event.get("source_kind") or event.get("kind") or "")
    if kind == "relationship_threshold_crossed":
        agenda["progress"] = _clamp_progress(int(agenda.get("progress") or 0) + 8)
        adjustments.append(f"agenda_progress:{agenda.get('npc_id')}")
    elif kind == "pressure_threshold_crossed":
        agenda["progress"] = _clamp_progress(int(agenda.get("progress") or 0) + 5)
        adjustments.append(f"agenda_progress:{agenda.get('npc_id')}")
    elif kind == "faction_hostility_shift":
        agenda["progress"] = _clamp_progress(int(agenda.get("progress") or 0) + 6)
        adjustments.append(f"agenda_progress:{agenda.get('npc_id')}")
    elif kind == "npc_world_move":
        agenda["last_move_turn"] = turn_number
        agenda["move_count"] = int(agenda.get("move_count") or 0) + 1
        agenda["progress"] = _clamp_progress(int(agenda.get("progress") or 0) + 10)
        adjustments.append(f"agenda_move:{agenda.get('npc_id')}")

    if not agenda.get("breaking_fired") and int(agenda.get("progress") or 0) >= 85:
        agenda["breaking_fired"] = True
        agenda["status"] = "breaking"
        adjustments.append(f"agenda_breaking:{agenda.get('npc_id')}")
    return adjustments


def tick_eligible_agendas(
    agendas_state: Dict[str, Any],
    turn_number: int,
) -> None:
    """Light per-turn agenda maintenance — internal planning progress only."""
    for agenda in agendas_state.get("active") or []:
        if not isinstance(agenda, dict):
            continue
        if agenda.get("status") != "active":
            continue
        if int(agenda.get("last_move_turn") or 0) < turn_number - 3:
            agenda["progress"] = _clamp_progress(int(agenda.get("progress") or 0) + 1)


def archive_agenda_if_needed(agendas_state: Dict[str, Any], npc_id: str) -> None:
    active = agendas_state.get("active") or []
    remain = []
    for agenda in active:
        if isinstance(agenda, dict) and agenda.get("npc_id") == npc_id and agenda.get("status") == "resolved":
            archived = agendas_state.setdefault("archived", [])
            archived.append(
                {
                    "npc_id": npc_id,
                    "goal_kind": agenda.get("goal_kind"),
                    "final_progress": agenda.get("progress"),
                }
            )
            if len(archived) > MAX_ARCHIVED_SUMMARIES:
                agendas_state["archived"] = archived[-MAX_ARCHIVED_SUMMARIES:]
        else:
            remain.append(agenda)
    agendas_state["active"] = remain[:MAX_ACTIVE_AGENDAS]


def get_agenda_by_npc_id(agendas_state: Mapping[str, Any], npc_id: str) -> Optional[Dict[str, Any]]:
    for agenda in agendas_state.get("active") or []:
        if isinstance(agenda, dict) and agenda.get("npc_id") == npc_id:
            return agenda
    return None


def get_agenda_by_agenda_id(agendas_state: Mapping[str, Any], agenda_id_value: str) -> Optional[Dict[str, Any]]:
    for agenda in agendas_state.get("active") or []:
        if isinstance(agenda, dict) and agenda.get("agenda_id") == agenda_id_value:
            return agenda
    return None


def strip_model_agenda_mutations(
    rolling: Dict[str, Any],
    authoritative: Mapping[str, Any],
) -> List[str]:
    """Remove model-emitted Living Cast fields from rolling_state."""
    adjustments: List[str] = []
    for key in (
        "npc_agendas",
        "arc_diversity",
        "pending_npc_move",
        "engine_world_events",
        "npc_move_receipts",
    ):
        if key in rolling:
            del rolling[key]
            adjustments.append(f"rolling_{key}_stripped")
    return adjustments


def copy_agendas_state(state: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    return copy.deepcopy(state) if isinstance(state, dict) else init_npc_agendas()