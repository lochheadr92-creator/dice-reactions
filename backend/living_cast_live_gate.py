"""
Living Cast live-gate harness — Haiku-only observation, attempt accounting.

Enabled only when LIVING_CAST_LIVE_GATE is set. Does not alter production
fallback behaviour; classifies live runs against the primary model baseline.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Optional

import ai_config
from living_cast_seeded_scenario import (
    PROOF_RUN_SEED,
    PROOF_SCENARIO_ID,
    build_proof_replayability_state,
    collect_sampling_provenance,
    live_gate_manifest,
    run_move_preflight,
)

LIVE_GATE_ENV_VAR = "LIVING_CAST_LIVE_GATE"
LIVE_GATE_PRIMARY_MODEL = "anthropic/claude-3-5-haiku"
INCONCLUSIVE_FALLBACK = (
    "INCONCLUSIVE — primary model was not observed; "
    "fallback output cannot validate the Haiku baseline"
)

# Worst-case physical outbound attempts for the proof harness:
#   2 story endpoints (opening + 1 neutral action)
#   × up to 2 validation-retried logical generations each
#   × MAX_RETRIES per-model HTTP attempts on Haiku only (fallback aborts)
OUTBOUND_ATTEMPT_BUDGET_ENV = "LIVING_CAST_OUTBOUND_BUDGET"
DEFAULT_OUTBOUND_ATTEMPT_BUDGET = (
    2 * 2 * int(ai_config.MAX_RETRIES)
)


def is_live_gate_enabled() -> bool:
    return os.environ.get(LIVE_GATE_ENV_VAR, "").lower() in ("1", "true", "yes", "on")


def resolve_outbound_attempt_budget() -> int:
    raw = os.environ.get(OUTBOUND_ATTEMPT_BUDGET_ENV)
    if raw is None or str(raw).strip() == "":
        return DEFAULT_OUTBOUND_ATTEMPT_BUDGET
    try:
        return max(1, int(str(raw).strip()))
    except ValueError:
        return DEFAULT_OUTBOUND_ATTEMPT_BUDGET


def load_proof_fixture() -> Dict[str, Any]:
    """Authorised harness path for the deterministic proof fixture."""
    if not is_live_gate_enabled():
        raise PermissionError("LIVING_CAST_LIVE_GATE is not enabled")
    return {
        "scenario_id": PROOF_SCENARIO_ID,
        "run_seed": PROOF_RUN_SEED,
        "replayability_state": build_proof_replayability_state(),
    }


class AttemptLedger:
    """Tracks logical generations vs physical provider HTTP attempts."""

    def __init__(self, *, budget: Optional[int] = None) -> None:
        self.budget = budget if budget is not None else resolve_outbound_attempt_budget()
        self.logical_generations = 0
        self.validation_retries = 0
        self.physical_outbound_attempts = 0
        self.fallback_attempts = 0
        self.models_observed: List[str] = []
        self.fallback_events: List[Dict[str, Any]] = []
        self.aborted = False
        self.abort_reason = ""

    def record_logical_generation(self, meta: Mapping[str, Any], *, validation_retry: bool = False) -> None:
        self.logical_generations += 1
        if validation_retry:
            self.validation_retries += 1
        self._ingest_meta(meta)

    def _ingest_meta(self, meta: Mapping[str, Any]) -> None:
        attempts = meta.get("attempts_per_model") or {}
        for model_id, count in attempts.items():
            self.physical_outbound_attempts += int(count or 0)
            if int(count or 0) > 0 and model_id not in self.models_observed:
                self.models_observed.append(str(model_id))
        for evt in meta.get("fallback_events") or []:
            if isinstance(evt, dict):
                self.fallback_events.append(dict(evt))
                self.fallback_attempts += 1
        if self.physical_outbound_attempts > self.budget:
            self.aborted = True
            self.abort_reason = (
                f"outbound attempt budget exceeded "
                f"({self.physical_outbound_attempts}>{self.budget})"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "logical_generations": self.logical_generations,
            "validation_retries": self.validation_retries,
            "physical_outbound_attempts": self.physical_outbound_attempts,
            "fallback_attempts": self.fallback_attempts,
            "models_observed": list(self.models_observed),
            "fallback_events": list(self.fallback_events),
            "outbound_budget": self.budget,
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
        }


def classify_generation_meta(meta: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Evaluate one logical generation against the Haiku live-gate policy.

    Production fallback is unchanged; this only classifies harness results.
    """
    model_used = str(meta.get("model_used") or "")
    model_requested = str(meta.get("model_requested") or LIVE_GATE_PRIMARY_MODEL)
    fallback_events = list(meta.get("fallback_events") or [])
    attempts = dict(meta.get("attempts_per_model") or {})

    primary_observed = model_used == LIVE_GATE_PRIMARY_MODEL
    fallback_triggered = bool(fallback_events) or any(
        m != LIVE_GATE_PRIMARY_MODEL and int(c or 0) > 0
        for m, c in attempts.items()
    )
    mislabeled = (
        model_used == LIVE_GATE_PRIMARY_MODEL
        and fallback_triggered
        and any(str(e.get("from")) == LIVE_GATE_PRIMARY_MODEL for e in fallback_events)
    )

    if fallback_triggered or not primary_observed:
        verdict = "INCONCLUSIVE"
        detail = INCONCLUSIVE_FALLBACK
    elif mislabeled:
        verdict = "INCONCLUSIVE"
        detail = "model identifier inconsistent with fallback telemetry"
    else:
        verdict = "PRIMARY_OBSERVED"
        detail = ""

    return {
        "verdict": verdict,
        "detail": detail,
        "model_used": model_used,
        "model_requested": model_requested,
        "primary_model": LIVE_GATE_PRIMARY_MODEL,
        "fallback_triggered": fallback_triggered,
        "primary_observed": primary_observed,
        "attempts_per_model": attempts,
        "fallback_events": fallback_events,
    }


def evaluate_haiku_gate(records: List[Mapping[str, Any]]) -> Dict[str, Any]:
    """Aggregate gate result across all logical generations in a live run."""
    classifications = [classify_generation_meta(r) for r in records]
    any_inconclusive = any(c["verdict"] == "INCONCLUSIVE" for c in classifications)
    return {
        "gate_pass": not any_inconclusive and bool(classifications),
        "classifications": classifications,
        "inconclusive_reason": (
            INCONCLUSIVE_FALLBACK if any_inconclusive else ""
        ),
    }


def build_retry_layer_table() -> List[Dict[str, Any]]:
    """Source-derived retry/accounting layers for live-gate documentation."""
    chain_len = len(
        [LIVE_GATE_PRIMARY_MODEL]
        + [m for m in ai_config.FALLBACK_MODELS if m != LIVE_GATE_PRIMARY_MODEL]
    )
    return [
        {
            "layer": "Story turn",
            "trigger": "POST /story/new or POST /story/action",
            "maximum_attempts": 1,
            "counts_as_provider_call": False,
            "can_change_model": False,
        },
        {
            "layer": "Initial generation",
            "trigger": "_generate_validated_turn first _generate_turn",
            "maximum_attempts": 1,
            "counts_as_provider_call": True,
            "can_change_model": True,
        },
        {
            "layer": "Validation retry",
            "trigger": "_generate_validated_turn after _full_validate failure",
            "maximum_attempts": 1,
            "counts_as_provider_call": True,
            "can_change_model": True,
        },
        {
            "layer": "Transport retry",
            "trigger": "chat_completion_with_meta per-model loop on FALLBACK_TRIGGERS",
            "maximum_attempts": int(ai_config.MAX_RETRIES),
            "counts_as_provider_call": True,
            "can_change_model": False,
        },
        {
            "layer": "Rate-limit retry",
            "trigger": "same as transport retry (KIND_RATE_LIMIT in FALLBACK_TRIGGERS)",
            "maximum_attempts": int(ai_config.MAX_RETRIES),
            "counts_as_provider_call": True,
            "can_change_model": False,
        },
        {
            "layer": "Fallback attempt",
            "trigger": "chat_completion_with_meta steps to next model after per-model retries exhausted",
            "maximum_attempts": max(0, chain_len - 1),
            "counts_as_provider_call": True,
            "can_change_model": True,
        },
    ]


def compute_call_ceilings() -> Dict[str, Any]:
    """
    Worst-case ceilings from implementation (not assuming 1:1 logical:physical).
    """
    per_logical = int(ai_config.MAX_RETRIES) * (
        1
        + max(
            0,
            len([m for m in ai_config.FALLBACK_MODELS if m != LIVE_GATE_PRIMARY_MODEL]),
        )
    )
    per_story_turn = 2 * per_logical  # initial + validation retry
    proof_story_turns = 2  # opening + one neutral action
    return {
        "max_retries_per_model": int(ai_config.MAX_RETRIES),
        "fallback_chain_models": len(ai_config.FALLBACK_MODELS),
        "per_logical_generation_worst_physical": per_logical,
        "per_story_turn_worst_physical": per_story_turn,
        "proof_harness_story_turns": proof_story_turns,
        "proof_harness_worst_physical_all_fallbacks": proof_story_turns * per_story_turn,
        "proof_harness_haiku_only_budget": resolve_outbound_attempt_budget(),
        "sdk_transport_retries_instrumented": False,
        "sdk_transport_retries_note": (
            "UNVERIFIED — provider library retry attempts not instrumented"
        ),
    }


def build_diagnostic_manifest(
    ledger: Optional[AttemptLedger] = None,
) -> Dict[str, Any]:
    """Local diagnostic manifest for a live-gate run (no live calls)."""
    manifest = live_gate_manifest()
    manifest["live_gate_enabled"] = is_live_gate_enabled()
    manifest["primary_model_gate"] = LIVE_GATE_PRIMARY_MODEL
    manifest["sampling_provenance"] = collect_sampling_provenance()
    manifest["retry_layers"] = build_retry_layer_table()
    manifest["call_ceilings"] = compute_call_ceilings()
    manifest["preflight"] = run_move_preflight()
    if ledger is not None:
        manifest["attempt_ledger"] = ledger.to_dict()
    return manifest