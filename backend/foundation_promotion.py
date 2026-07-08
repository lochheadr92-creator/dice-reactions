"""
Foundation Completion Phase 2 — promotion routing.

Promotes the canonical foundation subsystems (Actor Resolution, Gravity
Governance, Utility AI, Memory Retrieval) from shadow evaluation into the
authoritative decision path, one explicit feature flag at a time.

Design contract:
  • Every routing helper is PURE and FAIL-CLOSED. On a disabled flag, missing
    canonical data, an unmapped actor, or ANY exception it returns the LEGACY
    result unchanged, together with a comparison diagnostic. It never raises out
    of the routing layer and never mutates its inputs.
  • No helper performs I/O, touches persisted rolling_state, or calls the LLM.
  • With every flag OFF the returned value is identical to the legacy input, so
    the surrounding turn path stays byte-identical to pre-promotion behaviour.

Flag defaults (all OFF) live in ai_config; this module only reads them.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import ai_config

PROMOTION_SCHEMA_VERSION = 1

# Canonical Actor Resolution tiers that are permitted to act this turn.
_ACTING_TIERS = ("hero", "active", "relevant")

# Stage 2 designed-extension inputs: map an npc_memory prompt-registry row onto a
# gravity retention input. Canon Ch 14/26 is non-numerical, so these are DESIGNED
# extensions (like stress.py constants), not canon transcriptions. They only order
# the prompt projection; persisted state and the item count are never affected.
_GRAVITY_MAJOR = 0.8
_GRAVITY_BASE = 0.4
_GRAVITY_CONNECTIVITY_SATURATION = 5.0


# ---------------------------------------------------------------------------
# Flag readers
# ---------------------------------------------------------------------------
def actor_resolution_enabled() -> bool:
    return bool(ai_config.ENABLE_CANONICAL_ACTOR_RESOLUTION)


def gravity_enabled() -> bool:
    return bool(ai_config.ENABLE_CANONICAL_GRAVITY)


def utility_live_enabled() -> bool:
    """Canonical Utility AI live handoff — canonical flag OR legacy alias."""
    return bool(
        ai_config.ENABLE_CANONICAL_UTILITY
        or ai_config.ENABLE_UTILITY_AI_LIVE_SELECTION
    )


def memory_retrieval_enabled() -> bool:
    return bool(ai_config.ENABLE_CANONICAL_MEMORY_RETRIEVAL)


def memory_retrieval_prompt_injection_allowed() -> bool:
    """
    True only when the canonical flag is on AND the separate shadow-acceptance
    constant has been granted. The acceptance constant is currently False, so
    canonical retrieval never feeds the prompt — see docs/foundation-promotion.md
    and foundation-canon-deltas D_MEMORY_RETRIEVAL_SHADOW.
    """
    return bool(
        ai_config.ENABLE_CANONICAL_MEMORY_RETRIEVAL
        and ai_config.CANONICAL_MEMORY_RETRIEVAL_PROMPT_INJECTION_ACCEPTED
    )


def promotion_flags() -> Dict[str, bool]:
    """Snapshot of promotion state for diagnostics / debug panel."""
    return {
        "actor_resolution": actor_resolution_enabled(),
        "gravity": gravity_enabled(),
        "utility": utility_live_enabled(),
        "memory_retrieval": memory_retrieval_enabled(),
        "memory_retrieval_prompt_injection_allowed": (
            memory_retrieval_prompt_injection_allowed()
        ),
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _norm_name(name: Any) -> str:
    return " ".join(str(name or "").strip().lower().split())


def _canonical_tier_by_name(actor_prepared: Mapping[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    registry = (actor_prepared or {}).get("referenceable_registry") or []
    for row in registry:
        if not isinstance(row, Mapping):
            continue
        key = _norm_name(row.get("display_name"))
        if key:
            out[key] = str(row.get("tier") or "unknown")
    return out


# ---------------------------------------------------------------------------
# Stage 1 — Actor Resolution (authoritative eligibility gate over NPC moves)
# ---------------------------------------------------------------------------
def compute_actor_resolution_prepared(snapshot: Any) -> Dict[str, Any]:
    """
    Run canonical Gravity -> Actor Resolution over a selection-time snapshot.

    Mirrors the dependency order used by foundation_integration (gravity retention
    feeds actor tiers). Used only when the actor-resolution promotion flag is on.
    """
    import gravity_governance
    import actor_resolution

    gravity_prepared = gravity_governance.evaluate_gravity_governance(
        snapshot,
        trait_significance_enabled=gravity_enabled(),
    )
    retention = gravity_governance.retention_scores_by_actor(gravity_prepared)
    return actor_resolution.evaluate_actor_resolution(
        snapshot, retention_scores=retention
    )


def route_actor_move(
    legacy_move: Optional[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    actor_prepared: Optional[Mapping[str, Any]],
    *,
    enabled: Optional[bool] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Apply canonical Actor Resolution as the authority over WHO acts this turn.

    Fail-closed semantics:
      • flag off / any error / legacy actor unmapped in the canonical registry
        -> return the legacy move unchanged (never suppress on a mapping gap).
      • canonical explicitly classifies the legacy actor as non-acting
        (dormant/archived/unknown) -> re-pick the first canonically-acting
        candidate (candidates are pre-sorted by score); if none, suppress (None).

    Only ever selects an actor already present in the legacy candidate set; never
    invents one. Returns (authoritative_move_or_none, diagnostic).
    """
    on = actor_resolution_enabled() if enabled is None else bool(enabled)
    legacy = dict(legacy_move) if isinstance(legacy_move, Mapping) else None
    diag: Dict[str, Any] = {
        "actor_resolution_enabled": on,
        "actor_resolution_applied": False,
        "actor_resolution_changed": False,
    }
    if legacy is not None:
        diag["actor_resolution_legacy_actor"] = str(legacy.get("npc_id") or "")
        diag["actor_resolution_legacy_actor_name"] = str(legacy.get("display_name") or "")

    if not on:
        return legacy, diag

    try:
        tier_by_name = _canonical_tier_by_name(actor_prepared or {})
        diag["actor_resolution_registry_size"] = len(tier_by_name)

        def _acting(row: Mapping[str, Any]) -> Optional[bool]:
            key = _norm_name(row.get("display_name"))
            if key not in tier_by_name:
                return None  # mapping gap -> unknown; do not veto
            return tier_by_name[key] in _ACTING_TIERS

        if legacy is None:
            diag["actor_resolution_applied"] = True
            return None, diag

        legacy_key = _norm_name(legacy.get("display_name"))
        diag["actor_resolution_legacy_canonical_tier"] = tier_by_name.get(
            legacy_key, "unmapped"
        )
        legacy_acting = _acting(legacy)
        if legacy_acting is not False:
            # Acting, or unmapped (fail-open): canonical confirms the legacy actor.
            diag["actor_resolution_applied"] = True
            return legacy, diag

        # Canonical vetoes the legacy actor. Re-pick the top canonically-acting
        # candidate, preserving the existing deterministic score order.
        for cand in candidates or []:
            if _acting(cand) is True:
                chosen = dict(cand)
                diag.update(
                    {
                        "actor_resolution_applied": True,
                        "actor_resolution_changed": True,
                        "actor_resolution_reason": "legacy_actor_non_acting",
                        "actor_resolution_authoritative_actor": str(chosen.get("npc_id") or ""),
                        "actor_resolution_authoritative_actor_name": str(chosen.get("display_name") or ""),
                    }
                )
                return chosen, diag

        diag.update(
            {
                "actor_resolution_applied": True,
                "actor_resolution_changed": True,
                "actor_resolution_reason": "no_acting_candidate",
                "actor_resolution_authoritative_actor": "",
            }
        )
        return None, diag
    except Exception as exc:  # fail-closed to legacy
        diag["actor_resolution_error"] = str(exc)[:200]
        diag["actor_resolution_applied"] = False
        return legacy, diag


# ---------------------------------------------------------------------------
# Stage 2 — Gravity Governance (canonical retention ordering of prompt projection)
# ---------------------------------------------------------------------------
def _npc_memory_row_gravity_inputs(row: Mapping[str, Any]) -> Tuple[float, float]:
    remembers = row.get("remembers") if isinstance(row, Mapping) else None
    events = [m for m in (remembers or []) if isinstance(m, Mapping)]
    has_major = any(str(m.get("severity") or "").lower() == "major" for m in events)
    gravity = _GRAVITY_MAJOR if has_major else _GRAVITY_BASE
    connectivity = min(1.0, len(events) / _GRAVITY_CONNECTIVITY_SATURATION)
    return gravity, connectivity


def gravity_retention_score_for_npc_memory(
    row: Mapping[str, Any],
    *,
    npc_trait_refs: Optional[Mapping[str, Any]] = None,
    settlement_trait_refs: Optional[Mapping[str, Any]] = None,
    location_ref: str = "",
) -> float:
    """Retention score for one npc_memory row via canonical Gravity Governance."""
    import gravity_governance

    gravity, connectivity = _npc_memory_row_gravity_inputs(row)
    modifier = gravity_governance.trait_significance_modifier(
        row,
        npc_trait_refs=npc_trait_refs,
        settlement_trait_refs=settlement_trait_refs,
        location_ref=location_ref,
    )
    return gravity_governance.compute_retention_score(
        gravity=max(0.0, min(1.0, gravity + modifier["gravity"])),
        connectivity=max(0.0, min(1.0, connectivity + modifier["connectivity"])),
        player_relevance=0.0,
        age_years=0.0,
    )


def order_npc_memory_by_gravity(
    rows: Sequence[Mapping[str, Any]],
    *,
    enabled: Optional[bool] = None,
    npc_trait_refs: Optional[Mapping[str, Any]] = None,
    settlement_trait_refs: Optional[Mapping[str, Any]] = None,
    location_ref: str = "",
) -> Tuple[Optional[List[int]], Dict[str, Any]]:
    """
    Canonical retention ranking (original indices, best first) for the npc_memory
    prompt registry. Returns None when the flag is off or on any error, so the
    caller falls back to the legacy recency heuristic. Pure; never mutates rows.

    Scope: this governs ONLY which npc_memory rows survive into the budget-limited
    <prior_state> prompt projection. Persisted rolling_state is never touched and
    the retained item count (the caller's cap) is unchanged — State Is Truth and
    the context-budget contract are preserved.
    """
    on = gravity_enabled() if enabled is None else bool(enabled)
    diag: Dict[str, Any] = {"gravity_enabled": on, "gravity_applied": False}
    if not on:
        return None, diag
    try:
        scored: List[Tuple[int, float]] = []
        for idx, row in enumerate(rows or []):
            scored.append(
                (
                    idx,
                    gravity_retention_score_for_npc_memory(
                        row,
                        npc_trait_refs=npc_trait_refs,
                        settlement_trait_refs=settlement_trait_refs,
                        location_ref=location_ref,
                    ),
                )
            )
        # Descending retention score; stable by original index for ties.
        order = [idx for idx, _ in sorted(scored, key=lambda pair: (-pair[1], pair[0]))]
        diag["gravity_applied"] = True
        diag["gravity_ranked_count"] = len(order)
        return order, diag
    except Exception as exc:  # fail-closed to legacy ordering
        diag["gravity_error"] = str(exc)[:200]
        return None, diag


# ---------------------------------------------------------------------------
# Stage 4 — Memory Retrieval (comparison diagnostics; prompt injection blocked)
# ---------------------------------------------------------------------------
def memory_retrieval_diagnostics(
    retrieval_prepared: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """
    Build the Stage 4 comparison diagnostic. Surfaces the canonical retrieval set
    and the explicit blocker keeping it out of the prompt. Diagnostics only — this
    function neither injects into nor reads the prompt.
    """
    injection_allowed = memory_retrieval_prompt_injection_allowed()
    prepared = retrieval_prepared if isinstance(retrieval_prepared, Mapping) else {}
    return {
        "memory_retrieval_enabled": memory_retrieval_enabled(),
        "memory_retrieval_prompt_injection_allowed": injection_allowed,
        "memory_retrieval_blocker_code": (
            None if injection_allowed else "SEPARATE_SHADOW_ACCEPTANCE_REQUIRED"
        ),
        "memory_retrieval_shadow_mode": prepared.get("shadow_mode"),
        "memory_retrieval_canonical_selected_ids": list(
            prepared.get("selected_memory_ids") or []
        ),
    }


# ---------------------------------------------------------------------------
# Compact authority summary (dev-only) — eases replay inspection.
# ---------------------------------------------------------------------------
def foundation_authority() -> Dict[str, str]:
    """
    One-line-per-subsystem summary of WHICH implementation is authoritative this
    turn. Pure; reads flags only. Diagnostics only — never gates gameplay.

    Values:
      • "canonical" — the promotion flag is ON and the canonical path is the
        authority for that subsystem.
      • "legacy"    — the flag is OFF; the legacy implementation is authoritative.
      • memory is special: it can never be "canonical" because prompt injection is
        gated behind CANONICAL_MEMORY_RETRIEVAL_PROMPT_INJECTION_ACCEPTED. With the
        flag ON it is "shadow_diagnostics" (runs, surfaced in diagnostics, does NOT
        feed the prompt); with the flag OFF it is "legacy".
    """
    return {
        "actor": "canonical" if actor_resolution_enabled() else "legacy",
        "gravity": "canonical" if gravity_enabled() else "legacy",
        "utility": "canonical" if utility_live_enabled() else "legacy",
        "memory": (
            "canonical"
            if memory_retrieval_prompt_injection_allowed()
            else ("shadow_diagnostics" if memory_retrieval_enabled() else "legacy")
        ),
    }
