"""
Centralised AI routing & runtime configuration.

Single source of truth for:
  • the default model used for new chronicles
  • the safe fallback chain (Haiku → Sonnet → Mythomax)
  • retry / timeout knobs
  • debug-panel feature flag
  • cost-mode preset

All values are env-overridable so deployments can tune without code changes.
"""

from __future__ import annotations

import os
from typing import List


def _csv_env(name: str, default: List[str]) -> List[str]:
    raw = os.environ.get(name)
    if not raw:
        return default
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts or default


# ---------------------------------------------------------------------------
# Primary routing
# ---------------------------------------------------------------------------
# Claude Haiku 4.5 — strong instruction following, low cost, ~200k context.
DEFAULT_MODEL: str = os.environ.get(
    "DEFAULT_MODEL", "anthropic/claude-haiku-4.5"
)

# Ordered fallback chain. The first entry is the default; subsequent entries
# are tried only after the previous one fails with a fallback-trigger error.
FALLBACK_MODELS: List[str] = _csv_env(
    "FALLBACK_MODELS",
    [
        "anthropic/claude-haiku-4.5",     # primary
        "anthropic/claude-sonnet-4.5",    # higher fidelity safety net
        "gryphe/mythomax-l2-13b",         # ultimate cheap backup
    ],
)

# ---------------------------------------------------------------------------
# Retry / timeout
# ---------------------------------------------------------------------------
# Attempts PER model before declaring it failed and stepping to the next
# fallback model in the chain. Includes the first attempt.
MAX_RETRIES: int = int(os.environ.get("MAX_RETRIES", "2"))

# Per-request HTTP timeout in seconds.
PROVIDER_TIMEOUT: float = float(os.environ.get("PROVIDER_TIMEOUT", "180"))

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------
ENABLE_DEBUG_PANEL: bool = (
    os.environ.get("ENABLE_DEBUG_PANEL", "true").lower() in ("1", "true", "yes", "on")
)

# ADR-024 Phase 2. Default OFF: deployments must opt in to using the canonical
# Utility AI winner for live NPC moves. Shadow comparison continues either way.
ENABLE_UTILITY_AI_LIVE_SELECTION: bool = (
    os.environ.get("ENABLE_UTILITY_AI_LIVE_SELECTION", "false").lower()
    in ("1", "true", "yes", "on")
)

# Dev-only live-turn evidence. Default OFF: emits structured logs proving whether
# Utility AI shadow/live selection was enabled, applied, and what source won.
ENABLE_UTILITY_AI_DIAGNOSTIC_LOGS: bool = (
    os.environ.get("ENABLE_UTILITY_AI_DIAGNOSTIC_LOGS", "false").lower()
    in ("1", "true", "yes", "on")
)


def _bool_env(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Foundation promotion flags (Phase 2 — Foundation Completion).
#
# Each flag promotes ONE canonical foundation subsystem from shadow evaluation
# into the authoritative decision path. ALL DEFAULT OFF. With every flag off the
# turn path is byte-identical to the pre-promotion behaviour and the canonical
# systems keep running as shadow diagnostics only. Legacy implementations remain
# available as the fallback whenever a flag is off or a canonical subsystem
# raises (fail-closed). Flipping a flag on is gated by separate acceptance and is
# only intended for comparison/acceptance runs — see docs/foundation-promotion.md.
# ---------------------------------------------------------------------------
ENABLE_CANONICAL_ACTOR_RESOLUTION: bool = _bool_env("ENABLE_CANONICAL_ACTOR_RESOLUTION")
ENABLE_CANONICAL_GRAVITY: bool = _bool_env("ENABLE_CANONICAL_GRAVITY")
# Canonical name for the ADR-024 live Utility AI handoff. Either this OR the
# legacy ENABLE_UTILITY_AI_LIVE_SELECTION engages the authoritative winner; the
# shadow comparison continues to run in every case.
ENABLE_CANONICAL_UTILITY: bool = _bool_env("ENABLE_CANONICAL_UTILITY")
ENABLE_CANONICAL_MEMORY_RETRIEVAL: bool = _bool_env("ENABLE_CANONICAL_MEMORY_RETRIEVAL")

# Memory Retrieval prompt injection is BLOCKED pending SEPARATE_SHADOW_ACCEPTANCE
# (foundation-canon-deltas D_MEMORY_RETRIEVAL_SHADOW). Even with the canonical
# flag on, canonical retrieval is surfaced in diagnostics only and NEVER feeds
# prompt construction until this acceptance constant is granted. Intentionally
# NOT env-overridable: turning it on requires a code change plus acceptance.
CANONICAL_MEMORY_RETRIEVAL_PROMPT_INJECTION_ACCEPTED: bool = False

# Chapter 33 Phase 1 — NPC Lifecycle (aging/mortality/death). Default OFF. With
# the flag OFF no live aging or mortality is applied and gameplay is unchanged;
# the pure lifecycle functions in backend/npc_lifecycle.py remain available for
# tests. Live turn-path wiring is deferred pending an authoritative simulation
# clock (see docs/ch33-lifecycle-phase1.md).
ENABLE_NPC_LIFECYCLE: bool = _bool_env("ENABLE_NPC_LIFECYCLE")

# Cost mode. "normal" (default) or "low". When low, prose is compressed
# and max_tokens is reduced — causality / continuity preserved.
COST_MODE: str = os.environ.get("COST_MODE", "normal").lower()

# Token caps per cost-mode bucket.
LOW_COST_MAX_TOKENS: int = int(os.environ.get("LOW_COST_MAX_TOKENS", "900"))
NORMAL_MAX_TOKENS_DEFAULT: int = int(os.environ.get("NORMAL_MAX_TOKENS_DEFAULT", "2048"))

# ---------------------------------------------------------------------------
# Context Budget Governor v3.9
# ---------------------------------------------------------------------------
# Maximum estimated *prompt* tokens (everything we send to the model, NOT
# counting the upcoming completion). The governor trims oldest / lowest-
# priority context until the prompt fits inside the active budget.
NORMAL_CONTEXT_BUDGET_TOKENS: int = int(
    os.environ.get("NORMAL_CONTEXT_BUDGET_TOKENS", "12000")
)
LOW_COST_CONTEXT_BUDGET_TOKENS: int = int(
    os.environ.get("LOW_COST_CONTEXT_BUDGET_TOKENS", "7000")
)
ADVANCED_CONTEXT_BUDGET_TOKENS: int = int(
    os.environ.get("ADVANCED_CONTEXT_BUDGET_TOKENS", "16000")
)


def resolve_context_budget(*, cost_mode: str, mode: str) -> int:
    """Return the prompt token budget for the active cost_mode + simulation mode."""
    cm = (cost_mode or "normal").lower()
    md = (mode or "advanced").lower()
    if cm == "low":
        return LOW_COST_CONTEXT_BUDGET_TOKENS
    if md == "advanced":
        return ADVANCED_CONTEXT_BUDGET_TOKENS
    return NORMAL_CONTEXT_BUDGET_TOKENS


def get_runtime_config() -> dict:
    """Snapshot the current config — useful for the debug panel and /admin/settings."""
    return {
        "default_model": DEFAULT_MODEL,
        "fallback_models": list(FALLBACK_MODELS),
        "max_retries": MAX_RETRIES,
        "provider_timeout": PROVIDER_TIMEOUT,
        "enable_debug_panel": ENABLE_DEBUG_PANEL,
        "cost_mode": COST_MODE,
        "low_cost_max_tokens": LOW_COST_MAX_TOKENS,
        "normal_max_tokens_default": NORMAL_MAX_TOKENS_DEFAULT,
        "enable_utility_ai_live_selection": ENABLE_UTILITY_AI_LIVE_SELECTION,
        "enable_canonical_actor_resolution": ENABLE_CANONICAL_ACTOR_RESOLUTION,
        "enable_canonical_gravity": ENABLE_CANONICAL_GRAVITY,
        "enable_canonical_utility": ENABLE_CANONICAL_UTILITY,
        "enable_canonical_memory_retrieval": ENABLE_CANONICAL_MEMORY_RETRIEVAL,
        "canonical_memory_retrieval_prompt_injection_accepted": (
            CANONICAL_MEMORY_RETRIEVAL_PROMPT_INJECTION_ACCEPTED
        ),
        "enable_npc_lifecycle": ENABLE_NPC_LIFECYCLE,
    }
