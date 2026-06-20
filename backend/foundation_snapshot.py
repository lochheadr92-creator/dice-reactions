"""
Immutable foundation turn input snapshot shared by Actor, Gravity, Utility, Retrieval.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, Mapping, Optional, Tuple

from engine_determinism import SERIALIZATION_SCHEMA_VERSION, stable_hash

FOUNDATION_SNAPSHOT_SCHEMA_VERSION = 1


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