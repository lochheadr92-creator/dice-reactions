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
# Claude 3.5 Haiku — strong instruction following, low cost, ~200k context.
DEFAULT_MODEL: str = os.environ.get(
    "DEFAULT_MODEL", "anthropic/claude-3-5-haiku"
)

# Ordered fallback chain. The first entry is the default; subsequent entries
# are tried only after the previous one fails with a fallback-trigger error.
FALLBACK_MODELS: List[str] = _csv_env(
    "FALLBACK_MODELS",
    [
        "anthropic/claude-3-5-haiku",     # primary
        "anthropic/claude-3-5-sonnet",    # higher fidelity safety net
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
    }
