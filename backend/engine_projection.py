"""
Engine projection boundary — explicit allowlists for player and prompt surfaces.

Foundation v0.1: internal foundation objects have no player or prompt projection.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def project_actor_resolution_internal(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Bounded internal telemetry only — not for player or model prompts."""
    return {
        "schema_version": result.get("schema_version"),
        "acting_actor_ids": list(result.get("acting_actor_ids") or []),
        "tier_counts": dict(result.get("tier_counts") or {}),
        "source_state_hash": result.get("source_state_hash"),
    }


def project_gravity_internal(result: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": result.get("schema_version"),
        "evaluated_count": result.get("evaluated_count"),
        "overflow": result.get("overflow"),
        "source_state_hash": result.get("source_state_hash"),
    }


def project_utility_internal(result: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": result.get("schema_version"),
        "selected_actor_id": result.get("selected_actor_id"),
        "selected_action_kind": result.get("selected_action_kind"),
        "selected_target_kind": result.get("selected_target_kind"),
        "selected_target_id": result.get("selected_target_id"),
        "candidate_set_hash": result.get("candidate_set_hash"),
        "source_state_hash": result.get("source_state_hash"),
    }


def project_retrieval_internal(result: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": result.get("schema_version"),
        "selected_memory_ids": list(result.get("selected_memory_ids") or []),
        "working_memory_size": result.get("working_memory_size"),
        "shadow_mode": result.get("shadow_mode"),
        "source_state_hash": result.get("source_state_hash"),
    }


def project_foundation_prepared(prepared: Mapping[str, Any]) -> Dict[str, Any]:
    """Aggregate bounded internal view for turn debug — never player/prompt."""
    return {
        "snapshot_schema_version": prepared.get("snapshot_schema_version"),
        "actor_resolution": project_actor_resolution_internal(
            prepared.get("actor_resolution") or {}
        ),
        "gravity": project_gravity_internal(prepared.get("gravity") or {}),
        "utility": project_utility_internal(prepared.get("utility") or {}),
        "retrieval": project_retrieval_internal(prepared.get("retrieval") or {}),
    }


def forbid_player_projection(payload: Mapping[str, Any]) -> Optional[str]:
    """Return error string if payload contains forbidden foundation internals."""
    forbidden_roots = (
        "utility_score_table",
        "retrieval_trace",
        "gravity_dispositions",
        "actor_tier_internals",
        "rng_draw_log",
    )
    for key in forbidden_roots:
        if key in payload:
            return f"forbidden foundation field in player projection: {key}"
    return None