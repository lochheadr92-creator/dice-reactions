"""
Immutable foundation turn input snapshot shared by Actor, Gravity, Utility, Retrieval.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from engine_determinism import SERIALIZATION_SCHEMA_VERSION, stable_hash

FOUNDATION_SNAPSHOT_SCHEMA_VERSION = 2


@dataclasses.dataclass(frozen=True)
class FoundationTurnSnapshot:
    schema_version: int
    run_id: str
    run_seed: str
    turn_sequence: int
    actor_registry: Tuple[Dict[str, Any], ...]
    actor_resolution_inputs: Dict[str, Any]
    pressure_state_ref: Dict[str, Any]
    confirmed_consequence_refs: Tuple[str, ...]
    relationship_vector_ref: Dict[str, Any]
    agenda_refs: Tuple[Dict[str, Any], ...]
    location_ref: str
    secret_access_facts: Tuple[str, ...]
    gravity_metadata: Dict[str, Any]
    utility_input_refs: Tuple[Dict[str, Any], ...]
    source_state_hash: str

    @staticmethod
    def build(
        *,
        run_seed: str,
        turn_sequence: int,
        rolling_state: Mapping[str, Any],
        replayability_state: Mapping[str, Any],
        run_id: str = "",
    ) -> "FoundationTurnSnapshot":
        rolling = dict(rolling_state) if isinstance(rolling_state, dict) else {}
        replay = dict(replayability_state) if isinstance(replayability_state, dict) else {}
        registry = _build_actor_registry(rolling)
        hash_material = {
            "run_seed": run_seed,
            "turn_sequence": turn_sequence,
            "registry_ids": sorted(row.get("actor_id", "") for row in registry),
            "pressure_graph": replay.get("pressure_graph") or {},
            "rolling_keys": sorted(rolling.keys()),
        }
        stress_commit = _actor_stress_commitment(rolling)
        if stress_commit is not None:
            # Commit authoritative stress values into snapshot identity so the
            # hash proves WHICH stress produced the output (provenance, not just
            # determinism): catches corrupted persistence / changed derivation.
            hash_material["actor_stress"] = stress_commit
        source_hash = stable_hash("foundation_snapshot", hash_material)
        return FoundationTurnSnapshot(
            schema_version=FOUNDATION_SNAPSHOT_SCHEMA_VERSION,
            run_id=run_id or str(replay.get("run_seed") or run_seed),
            run_seed=run_seed,
            turn_sequence=turn_sequence,
            actor_registry=tuple(registry),
            actor_resolution_inputs=_actor_resolution_inputs(rolling, replay, turn_sequence),
            pressure_state_ref=dict(replay.get("pressure_graph") or {}),
            confirmed_consequence_refs=_consequence_refs(rolling),
            relationship_vector_ref={
                "vectors": list(rolling.get("relationship_vectors") or []),
            },
            agenda_refs=tuple(
                dict(row)
                for row in (replay.get("npc_agendas") or {}).get("agendas") or []
                if isinstance(row, dict)
            ),
            location_ref=str(rolling.get("scene") or rolling.get("location") or ""),
            secret_access_facts=tuple(_secret_access_facts(rolling, replay)),
            gravity_metadata=dict(replay.get("gravity_metadata") or {}),
            utility_input_refs=tuple(_utility_input_refs(rolling, replay, registry)),
            source_state_hash=source_hash,
        )


def _build_actor_registry(rolling: Mapping[str, Any]) -> list:
    registry: Dict[str, Dict[str, Any]] = {}
    deceased = {str(name).strip().lower() for name in (rolling.get("deceased") or [])}
    for row in rolling.get("npcs") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        actor_id = str(row.get("npc_id") or _actor_id_from_name(name))
        registry[actor_id] = {
            "actor_id": actor_id,
            "display_name": name,
            "referenceable": True,
            "life_status": "deceased" if name.lower() in deceased else "alive",
            "stance": str(row.get("stance") or ""),
            "last_seen": str(row.get("last_seen") or ""),
        }
    for row in rolling.get("npc_memory") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        actor_id = _actor_id_from_name(name)
        entry = registry.setdefault(
            actor_id,
            {
                "actor_id": actor_id,
                "display_name": name,
                "referenceable": True,
                "life_status": "deceased" if name.lower() in deceased else "alive",
            },
        )
        entry["has_memory"] = True
    for vec in rolling.get("relationship_vectors") or []:
        if not isinstance(vec, dict):
            continue
        name = str(vec.get("name") or "").strip()
        if not name:
            continue
        actor_id = _actor_id_from_name(name)
        entry = registry.setdefault(
            actor_id,
            {
                "actor_id": actor_id,
                "display_name": name,
                "referenceable": True,
                "life_status": "deceased" if name.lower() in deceased else "alive",
            },
        )
        entry["has_relationship"] = True
    for name in deceased:
        actor_id = _actor_id_from_name(name)
        registry.setdefault(
            actor_id,
            {
                "actor_id": actor_id,
                "display_name": name,
                "referenceable": True,
                "life_status": "deceased",
            },
        )
    return sorted(registry.values(), key=lambda row: row["actor_id"])


def _actor_stress_commitment(rolling: Mapping[str, Any]) -> Optional[Dict[str, Dict[str, Any]]]:
    """Canonical authoritative stress values for snapshot hash commitment.

    Returns None when there are no authoritative stress values (key absent, empty
    dict, or only None-valued entries), so the digest contributes nothing in those
    cases. NOTE: legacy hash identity holds only when ``actor_stress`` is absent
    ENTIRELY — an empty/inert ``actor_stress`` key still changes ``rolling_keys``
    (pre-existing behaviour), which is independent of this digest.
    """
    raw = rolling.get("actor_stress")
    if not isinstance(raw, dict) or not raw:
        return None
    commit: Dict[str, Dict[str, Any]] = {}
    for sid, row in raw.items():
        if isinstance(row, dict) and row.get("stress_level") is not None:
            commit[str(sid)] = {
                "stress_level": float(row.get("stress_level")),
                "capacity": float(row["capacity"]) if row.get("capacity") is not None else None,
            }
    return commit or None


def build_actor_registry(rolling: Mapping[str, Any]) -> list:
    """Public alias for the authoritative actor registry build.

    Used by the stress subsystem (stress.update_actor_stress) so it keys
    per-actor stress by the exact same actor_id this snapshot uses.
    """
    return _build_actor_registry(rolling)


def highest_pressure_intensity(pressure_graph: Mapping[str, Any]) -> Optional[float]:
    """Public alias for the canonical highest active pressure intensity (0-1)."""
    return _highest_pressure_intensity(pressure_graph)


def _actor_id_from_name(name: str) -> str:
    from engine_determinism import stable_hash

    digest = stable_hash("actor_id", {"name": name.strip().lower()})
    return f"actor-{digest[:12]}"


def _actor_resolution_inputs(
    rolling: Mapping[str, Any],
    replay: Mapping[str, Any],
    turn_sequence: int,
) -> Dict[str, Any]:
    return {
        "turn_sequence": turn_sequence,
        "player_location": str(rolling.get("scene") or rolling.get("location") or ""),
        "active_pressure_node_ids": [
            str(node.get("id"))
            for node in (replay.get("pressure_graph") or {}).get("nodes") or []
            if isinstance(node, dict) and node.get("status") == "active"
        ],
        "investigation_active": bool(rolling.get("clues") or rolling.get("topic_ledger")),
    }


def _consequence_refs(rolling: Mapping[str, Any]) -> Tuple[str, ...]:
    refs = []
    for key in ("active_consequences", "delayed_consequences"):
        for row in rolling.get(key) or []:
            if isinstance(row, dict):
                ref = str(row.get("id") or row.get("description") or "")
                if ref:
                    refs.append(ref)
    return tuple(sorted(refs))


def _utility_input_refs(
    rolling: Mapping[str, Any],
    replay: Mapping[str, Any],
    registry: Sequence[Mapping[str, Any]],
) -> list:
    """Bounded authoritative utility inputs per actor - no narrative prose."""
    refs: list = []
    agendas = {
        str(row.get("npc_id") or ""): row
        for row in (replay.get("npc_agendas") or {}).get("agendas") or []
        if isinstance(row, dict)
    }
    if not agendas:
        for row in (replay.get("npc_agendas") or {}).get("active") or []:
            if isinstance(row, dict):
                agendas[str(row.get("npc_id") or "")] = row
    rel_by_actor: Dict[str, Dict[str, Any]] = {}
    for vec in rolling.get("relationship_vectors") or []:
        if not isinstance(vec, dict):
            continue
        actor_id = str(vec.get("npc_id") or _actor_id_from_name(str(vec.get("name") or "")))
        rel_by_actor[actor_id] = vec
    highest_pressure = _highest_pressure_intensity(replay.get("pressure_graph") or {})
    resource_scarcity = _resource_scarcity(replay.get("pressure_graph") or {})
    stress_by_actor: Dict[str, Any] = {}
    raw_stress = rolling.get("actor_stress")
    if isinstance(raw_stress, dict):
        for sid, srow in raw_stress.items():
            if isinstance(srow, dict) and srow.get("stress_level") is not None:
                stress_by_actor[str(sid)] = float(srow.get("stress_level"))
    memory_by_name = {
        str(row.get("name") or "").strip().lower(): _memory_signatures(row)
        for row in rolling.get("npc_memory") or []
        if isinstance(row, dict)
    }
    for actor in registry:
        actor_id = str(actor.get("actor_id") or "")
        if not actor_id:
            continue
        agenda = agendas.get(actor_id) or {}
        name_key = str(actor.get("display_name") or "").strip().lower()
        rel = rel_by_actor.get(actor_id) or {}
        importance = None
        if rel:
            importance = min(10.0, max(1.0, (int(rel.get("loyalty", 0)) + int(rel.get("trust", 0))) / 20.0 + 5.0))
        refs.append(
            {
                "actor_id": actor_id,
                "goal_kind": str(agenda.get("goal_kind") or ""),
                "fear_kind": str(agenda.get("fear_kind") or ""),
                "starving": str(agenda.get("fear_kind") or "") == "starvation",
                "highest_pressure_intensity": highest_pressure,
                "resource_scarcity": resource_scarcity,
                "relationship_importance": importance,
                "stress_level": stress_by_actor.get(actor_id),
                "memory_signatures": memory_by_name.get(name_key, ()),
            }
        )
    return sorted(refs, key=lambda row: row["actor_id"])


def _highest_pressure_intensity(pressure_graph: Mapping[str, Any]) -> Optional[float]:
    peak = 0.0
    found = False
    for node in pressure_graph.get("nodes") or []:
        if not isinstance(node, dict) or node.get("status") != "active":
            continue
        found = True
        peak = max(peak, float(node.get("magnitude", 0)) / 100.0)
    return peak if found else None


def _resource_scarcity(pressure_graph: Mapping[str, Any]) -> Optional[float]:
    for node in pressure_graph.get("nodes") or []:
        if not isinstance(node, dict) or node.get("status") != "active":
            continue
        if node.get("kind") == "resource":
            return min(1.0, float(node.get("magnitude", 0)) / 100.0)
    return None


def _memory_signatures(npc_memory_row: Mapping[str, Any]) -> Tuple[Dict[str, Any], ...]:
    sigs = []
    for mem in npc_memory_row.get("remembers") or []:
        if not isinstance(mem, dict):
            continue
        weight = str(mem.get("weight") or mem.get("severity") or "minor").lower()
        ctx = mem.get("context") if isinstance(mem.get("context"), dict) else {}
        sigs.append(
            {
                "location": str(ctx.get("location") or ""),
                "activity": str(ctx.get("activity") or ""),
                "actor_type": str(ctx.get("actor_type") or ""),
                "negative": weight in ("defining", "major", "high", "severe"),
                "trauma_intensity": 2.0 if weight == "defining" else 1.5 if weight == "major" else 1.0,
            }
        )
    return tuple(sigs[:8])


def _secret_access_facts(rolling: Mapping[str, Any], replay: Mapping[str, Any]) -> Tuple[str, ...]:
    facts = []
    identity = replay.get("identity") or {}
    if identity.get("has_secret"):
        facts.append("player_has_secret")
    registry = rolling.get("secret_registry") or {}
    if isinstance(registry, dict):
        for key in sorted(registry.keys()):
            facts.append(f"secret_registry:{key}")
    return tuple(facts)
