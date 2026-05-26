"""
Rolling Memory Compression v3.8 — surgical layer.

The story engine already emits a fresh `rolling_state` JSON each turn. This
module sits between the parsed LLM output and the persisted state to make
two guarantees the LLM alone cannot:

  1. Unresolved consequence / threat / promise / clue / delayed-trigger fields
     are NEVER lost just because the model omitted them on a given turn.
  2. Deterministic compression diagnostics are produced for the Developer
     panel (raw_turns_kept, compressed_turns_count, rolling_state_updated_at,
     estimated_context_savings) — invisible to standard players.

State remains the source of truth; this layer protects it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Field policy
# ---------------------------------------------------------------------------
# Keys whose contents represent UNRESOLVED forward-looking state. If the LLM
# drops items from these, we restore them from the previous turn's snapshot
# so causal continuity cannot be silently lost.
PROTECTED_LIST_KEYS = (
    "active_consequences",
    "delayed_consequences",
    "latent_triggers",
    "unresolved_threats",
    "promises",
    "clues",
)

# Keys where the model is authoritative each turn (it actively prunes them).
AUTHORITATIVE_LIST_KEYS = (
    "topic_ledger",
    "recent_choice_signatures",
    "active_pressures",
    "recent_beats",
    "archived",
)


def _key_for(item: Any) -> str:
    """Stable string fingerprint for de-duplicating consequence-style entries."""
    if isinstance(item, dict):
        for k in ("id", "key", "name", "trigger", "description", "text", "label"):
            if k in item and item[k]:
                return f"{k}:{str(item[k]).strip().lower()}"
        return str(sorted(item.items()))[:300]
    return str(item).strip().lower()


def _is_unresolved(item: Any) -> bool:
    """Heuristic: dict with status/resolved markers, or any plain string item."""
    if isinstance(item, dict):
        status = str(item.get("status", "")).lower()
        if status in {"resolved", "done", "complete", "cleared", "closed", "expired"}:
            return False
        if item.get("resolved") is True:
            return False
        return True
    return bool(item)


def consolidate_rolling_state(
    prior: Optional[Dict[str, Any]], fresh: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Deterministic merge of LLM-emitted rolling_state with the prior snapshot.

    Rules:
      • fresh fields overwrite prior fields for everything not in
        PROTECTED_LIST_KEYS.
      • AUTHORITATIVE_LIST_KEYS are taken from fresh as-is (the model prunes
        these intentionally — exhausted topics, recent fingerprints, etc.).
      • PROTECTED_LIST_KEYS are union-merged: any unresolved entry that
        existed in prior but is missing from fresh is restored. This is the
        contract guaranteeing consequence chains survive model omissions.
    """
    if not prior and not fresh:
        return {}
    if not prior:
        return dict(fresh or {})
    if not fresh:
        return dict(prior)

    merged: Dict[str, Any] = dict(prior)
    for k, v in fresh.items():
        merged[k] = v

    # Authoritative keys → take fresh verbatim (already done by the loop above).

    # Protected keys → union, restoring unresolved prior items.
    for key in PROTECTED_LIST_KEYS:
        prior_val = prior.get(key)
        fresh_val = fresh.get(key)
        if not prior_val:
            continue
        if not fresh_val:
            # Model dropped the whole field — restore protected continuity.
            merged[key] = prior_val
            continue
        if isinstance(prior_val, list) and isinstance(fresh_val, list):
            seen_keys = {_key_for(x) for x in fresh_val}
            survivors = [
                x
                for x in prior_val
                if _key_for(x) not in seen_keys and _is_unresolved(x)
            ]
            if survivors:
                merged[key] = list(fresh_val) + survivors
        # If prior is a dict (e.g. {id: detail}) and fresh is also a dict,
        # do a shallow union preferring fresh entries.
        elif isinstance(prior_val, dict) and isinstance(fresh_val, dict):
            union: Dict[str, Any] = dict(prior_val)
            for k2, v2 in fresh_val.items():
                if not (
                    isinstance(v2, dict)
                    and (str(v2.get("status", "")).lower() == "resolved")
                ):
                    union[k2] = v2
            merged[key] = union

    return merged


# ---------------------------------------------------------------------------
# Compression diagnostics
# ---------------------------------------------------------------------------
# Rough heuristic: 4 chars per token. Used only for the debug panel — not
# used for any cost or routing decision.
CHARS_PER_TOKEN = 4


def compute_compression_metrics(
    *,
    turn_number: int,
    memory_depth: int,
    prior_turns_payloads: List[str],
) -> Dict[str, Any]:
    """Return diagnostics describing the compression at THIS turn.

    Args:
        turn_number: 1-based number of the turn just produced.
        memory_depth: number of full-detail recent turns the prompt actually keeps.
        prior_turns_payloads: raw / narrative payloads of older (compressed-out)
            turns — used purely to estimate the bytes that no longer travel to
            the LLM versus a "send everything" baseline.
    """
    raw_kept = min(max(memory_depth, 1), turn_number)
    compressed = max(0, turn_number - raw_kept)
    saved_chars = sum(len(p or "") for p in prior_turns_payloads[: compressed])
    return {
        "raw_turns_kept": raw_kept,
        "compressed_turns_count": compressed,
        "rolling_state_updated_at": datetime.now(timezone.utc).isoformat(),
        "estimated_context_savings_chars": saved_chars,
        "estimated_context_savings_tokens": saved_chars // CHARS_PER_TOKEN,
    }
