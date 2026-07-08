"""
Foundation systems v0.1 cross-system integration on a frozen turn snapshot.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Mapping, Optional, Tuple

import actor_resolution
import foundation_promotion
import gravity_governance
import memory_retrieval
import utility_ai
from engine_determinism import canonical_json
from engine_projection import project_foundation_prepared
from foundation_snapshot import FoundationTurnSnapshot

FOUNDATION_INTEGRATION_VERSION = 1


def evaluate_foundation_turn(
    *,
    run_seed: str,
    turn_sequence: int,
    rolling_state: Mapping[str, Any],
    replayability_state: Mapping[str, Any],
    prior_foundation_state: Optional[Mapping[str, Any]] = None,
    developer_mode: bool = False,
    context_budget_items: int = 0,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Run Actor → Gravity → Utility → Retrieval on one immutable snapshot.

    Returns (prepared_bundle, bounded_diag). Does not mutate rolling_state.
    """
    snapshot = FoundationTurnSnapshot.build(
        run_seed=run_seed,
        turn_sequence=turn_sequence,
        rolling_state=rolling_state,
        replayability_state=replayability_state,
    )
    prior = copy.deepcopy(prior_foundation_state) if isinstance(prior_foundation_state, dict) else {}

    gravity_prepared = gravity_governance.evaluate_gravity_governance(
        snapshot,
        prior_state=(prior.get("gravity") or {}).get("prepared_state"),
        context_budget_items=context_budget_items,
        trait_significance_enabled=foundation_promotion.gravity_enabled(),
    )
    retention_by_actor = gravity_governance.retention_scores_by_actor(gravity_prepared)

    actor_prepared = actor_resolution.evaluate_actor_resolution(
        snapshot,
        prior_state=(prior.get("actor_resolution") or {}).get("prepared_state"),
        retention_scores=retention_by_actor,
    )

    candidates = utility_ai.candidates_from_agendas(
        snapshot,
        rolling_state=rolling_state,
        replayability_state=replayability_state,
        run_seed=run_seed,
    )
    utility_prepared = utility_ai.select_action(
        candidates,
        snapshot=snapshot,
        actor_resolution=actor_prepared,
    )

    # Stage 4 promotion: canonical Memory Retrieval. Prompt injection stays
    # BLOCKED pending SEPARATE_SHADOW_ACCEPTANCE (D_MEMORY_RETRIEVAL_SHADOW), so
    # shadow_mode stays True and the prompt is unaffected; the canonical set is
    # surfaced in diagnostics only. See docs/foundation-promotion.md.
    memory_injection_allowed = foundation_promotion.memory_retrieval_prompt_injection_allowed()
    retrieval_prepared = memory_retrieval.evaluate_memory_retrieval(
        snapshot,
        actor_resolution=actor_prepared,
        gravity=gravity_prepared,
        rolling_state=rolling_state,
        shadow_mode=not memory_injection_allowed,
        developer_mode=developer_mode,
    )

    bundle = {
        "schema_version": FOUNDATION_INTEGRATION_VERSION,
        "snapshot_schema_version": snapshot.schema_version,
        "source_state_hash": snapshot.source_state_hash,
        "snapshot": {
            "turn_sequence": snapshot.turn_sequence,
            "run_seed": snapshot.run_seed,
            "source_state_hash": snapshot.source_state_hash,
        },
        "actor_resolution": actor_prepared,
        "gravity": gravity_prepared,
        "utility": utility_prepared,
        "retrieval": retrieval_prepared,
        "prepared_bytes": canonical_json(
            {
                "actor_resolution": actor_prepared.get("state_hash"),
                "gravity": gravity_prepared.get("state_hash"),
                "utility": utility_prepared.get("state_hash"),
                "retrieval": retrieval_prepared.get("state_hash"),
            }
        ),
    }
    diag = {
        "foundation_evaluated": True,
        "foundation_shadow_mode": retrieval_prepared.get("shadow_mode"),
        "foundation_prepared_projection": project_foundation_prepared(bundle),
        "foundation_promotion_flags": foundation_promotion.promotion_flags(),
        "foundation_authority": foundation_promotion.foundation_authority(),
        "memory_retrieval_promotion": foundation_promotion.memory_retrieval_diagnostics(
            retrieval_prepared
        ),
    }
    return bundle, diag


def apply_prepared_to_replayability_state(
    replayability_state: Dict[str, Any],
    prepared_bundle: Mapping[str, Any],
) -> Dict[str, Any]:
    """Stage approved prepared outputs on the action working copy."""
    state = copy.deepcopy(replayability_state)
    state["foundation_prepared_v1"] = {
        "schema_version": FOUNDATION_INTEGRATION_VERSION,
        "snapshot_schema_version": prepared_bundle.get("snapshot_schema_version"),
        "source_state_hash": prepared_bundle.get("source_state_hash"),
        "actor_resolution_state": (prepared_bundle.get("actor_resolution") or {}).get("prepared_state"),
        "gravity_state": (prepared_bundle.get("gravity") or {}).get("prepared_state"),
        "utility_selection": (prepared_bundle.get("utility") or {}).get("selected"),
        "retrieval_memory_ids": (prepared_bundle.get("retrieval") or {}).get("selected_memory_ids"),
    }
    return state


def clear_prepared(state: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(state)
    out.pop("foundation_prepared_v1", None)
    return out
