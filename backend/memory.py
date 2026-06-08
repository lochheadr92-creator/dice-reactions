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

import json as _json
import re as _re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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
    "active_threats",
    "unresolved",
    "injuries",
    "inventory_objects",
    "object_locations",
    "route_continuity",
    "npc_memory",
    "relationship_threads",
    "faction_pressure",
    "world_instability",
    "simulation_hooks",
    "promises",
    "clues",
    "known_rooms",  # P1-C — persistent room state for revisit reconciliation
    "deceased",     # Ch 31 — engine-owned death registry (never resurrect)
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
        # Object-identity fields are checked FIRST so that the same physical
        # object emitted on different turns (with different status / location)
        # collapses to a single canonical row rather than accumulating
        # contradictory historical states.
        for k in ("object", "item"):
            if k in item and item[k]:
                return f"object:{_normalize_object_name(item[k])}"
        for k in ("id", "key", "name", "trigger", "description", "text", "label"):
            if k in item and item[k]:
                return f"{k}:{str(item[k]).strip().lower()}"
        return str(sorted(item.items()))[:300]
    return str(item).strip().lower()


# ---------------------------------------------------------------------------
# Object-permanence canonicalization (P0 — anti-bloat)
# ---------------------------------------------------------------------------
# Reasons for this layer:
#   • The LLM may emit the same physical object on multiple turns with
#     slightly different label spellings ("the iron key" vs "iron key").
#   • Union-merging protected lists without identity-collapse causes
#     contradictory historical entries to accumulate (e.g. one row says
#     "carried at start", another says "stored under shelf") for the SAME
#     object. This is the rolling-memory bloat documented in QA #2.
#   • We resolve it by collapsing each identity to a single row and keeping
#     the most recent (fresh-wins) state.

_OBJECT_STOP_WORDS = {
    "the", "a", "an", "and", "with", "of", "on", "in", "at", "to",
    "this", "that", "your", "my", "some",
    "small", "large", "tiny", "big", "old", "new", "broken", "damaged",
    "torn", "rusted", "worn", "metal", "wooden", "iron", "steel",
    "good", "bad", "half", "full", "empty", "near", "under", "over",
}


def _normalize_object_name(name: Any) -> str:
    """Reduce an object label to a stable identity token set string.

    "The Iron Key (rusted)" → "key"
    "old leather satchel"   → "leather satchel" (descriptors stripped)
    "bone-handled knife"    → "bone handled knife" (hyphens broken to tokens)
    """
    if not name:
        return ""
    raw = str(name).lower()
    # Strip parenthetical descriptors, including unclosed fragments (e.g.
    # ledger row "iron key (1" left over after a sloppy split).
    raw = _re.sub(r"\(.*?(?:\)|$)", " ", raw)
    # Normalise hyphens / underscores to spaces so "bone-handled" and
    # "bone handled" collapse to the same identity.
    raw = _re.sub(r"[-_/]", " ", raw)
    words = _re.findall(r"[a-z][a-z0-9]+", raw)
    tokens = [w.rstrip("s") for w in words if w not in _OBJECT_STOP_WORDS]
    if not tokens:
        return str(name).strip().lower()[:40]
    return " ".join(sorted(set(tokens)))


# Status priority — when the same identity arrives with multiple statuses
# in a single emission, prefer the most resolved/terminal state so the
# ledger never carries a stale "carried" row alongside a "destroyed" row.
_STATUS_PRIORITY = {
    "destroyed": 90,
    "consumed": 80,
    "dropped": 70,
    "hidden": 60,
    "stored": 50,
    "worn": 40,
    "carried": 30,
    "uncertain": 10,
    "": 0,
}


def _status_rank(status: Any) -> int:
    return _STATUS_PRIORITY.get(str(status or "").strip().lower(), 20)


def canonicalize_object_registry(state: Dict[str, Any]) -> Dict[str, Any]:
    """Collapse `object_locations` and `inventory_objects` to a single row
    per normalized object identity. Mutates and returns the input dict.

    Rules:
      • Each identity appears at most once across the registry.
      • If the same identity has multiple rows in a list, keep the row with
        the highest status rank (most final). Ties → the LAST occurrence
        wins (fresh-from-LLM appears after restored survivors in our merge).
      • Cross-list consistency: `object_locations` is the source of truth
        for location_state; `inventory_objects.location_state` is rewritten
        to match.
    """
    if not isinstance(state, dict):
        return state

    # ---- 1. Canonicalize object_locations ----
    raw_locs = state.get("object_locations")
    canonical: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw_locs, list):
        for row in raw_locs:
            if not isinstance(row, dict):
                continue
            ident = _normalize_object_name(row.get("object"))
            if not ident:
                continue
            existing = canonical.get(ident)
            if existing is None:
                canonical[ident] = dict(row)
                continue
            # Prefer the higher-priority status; on tie, the newer row wins.
            if _status_rank(row.get("status")) >= _status_rank(existing.get("status")):
                canonical[ident] = dict(row)
        state["object_locations"] = list(canonical.values())

    # ---- 2. Canonicalize inventory_objects, aligning to object_locations ----
    raw_inv = state.get("inventory_objects")
    if isinstance(raw_inv, list):
        inv_map: Dict[str, Dict[str, Any]] = {}
        for row in raw_inv:
            if not isinstance(row, dict):
                continue
            ident = _normalize_object_name(row.get("object"))
            if not ident:
                continue
            existing = inv_map.get(ident)
            if existing is None:
                inv_map[ident] = dict(row)
                continue
            if _status_rank(row.get("location_state")) >= _status_rank(
                existing.get("location_state")
            ):
                inv_map[ident] = dict(row)
        # Rewrite location_state to match the canonical object_locations entry.
        for ident, row in inv_map.items():
            ref = canonical.get(ident)
            if ref:
                row["location_state"] = ref.get("status", row.get("location_state"))
                if ref.get("where") and not row.get("where"):
                    row["where"] = ref.get("where")
        state["inventory_objects"] = list(inv_map.values())

    return state


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

    # Final pass: collapse object_locations / inventory_objects to one row
    # per canonical identity. This is the P0 anti-bloat guarantee — without
    # it, the additive union above can stack contradictory historical states
    # for the SAME physical object as turns accumulate.
    canonicalize_object_registry(merged)

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


# ===========================================================================
# Context Budget Governor v3.9
# ===========================================================================
# This is a PRE-AI-CALL trim layer. It receives the fully-built `messages`
# array (system + replay history + final user with prior_state) and ensures
# the total estimated tokens stay under the configured budget. Any items
# referenced in PROTECTED_LIST_KEYS, the active scene (latest assistant +
# user messages), and the most recent N turns are NEVER touched.
# ===========================================================================

# Patterns used to strip ENGINE blocks from older assistant messages while
# preserving narrative continuity. We keep <narrative> only.
_ENGINE_BLOCK_STRIP_RE = _re.compile(
    r"<(choices|state|ledger|debug|rolling_state)\b[^>]*>[\s\S]*?</\1\s*>",
    _re.IGNORECASE,
)
_PRIOR_STATE_BLOCK_RE = _re.compile(
    r"<prior_state>\s*([\s\S]*?)\s*</prior_state>", _re.IGNORECASE
)

# rolling_state keys we may safely trim/compress when over budget.
# Authoritative key contents are LOW-PRIORITY context (already summarised
# elsewhere). Protected (consequence-bearing) keys are NEVER touched.
TRIMMABLE_ROLLING_KEYS = (
    "archived",          # explicitly marked as dormant
    "recent_beats",      # last N one-liners
    "recent_choice_signatures",  # last N fingerprints
)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_messages_tokens(messages: List[Dict[str, str]]) -> int:
    # +4 per message: rough overhead for role markers
    return sum(estimate_tokens(m.get("content", "")) + 4 for m in messages)


def _compress_prior_state_json(state: Dict[str, Any]) -> Dict[str, Any]:
    """Drop low-value content from a rolling_state copy without losing causality.

    Removes / shrinks:
      • `archived`
      • `recent_beats` truncated to last 3
      • `recent_choice_signatures` truncated to last 4
      • topic_ledger entries marked `exhausted` keep only {topic, status}
      • resolved items in PROTECTED list keys are dropped (consequence chain stays intact)
    Returns a new dict; never mutates the input.
    """
    if not isinstance(state, dict):
        return state
    out: Dict[str, Any] = {}
    for k, v in state.items():
        if k == "archived":
            continue
        if k == "recent_beats" and isinstance(v, list):
            out[k] = v[-3:]
            continue
        if k == "recent_choice_signatures" and isinstance(v, list):
            out[k] = v[-4:]
            continue
        if k == "topic_ledger" and isinstance(v, list):
            slim = []
            for item in v:
                if isinstance(item, dict) and str(
                    item.get("status", "")
                ).lower() in ("exhausted", "blocked"):
                    slim.append(
                        {
                            "topic": item.get("topic"),
                            "status": item.get("status"),
                        }
                    )
                else:
                    slim.append(item)
            out[k] = slim
            continue
        if k in PROTECTED_LIST_KEYS and isinstance(v, list):
            out[k] = [
                item
                for item in v
                if not (
                    isinstance(item, dict)
                    and str(item.get("status", "")).lower()
                    in {"resolved", "done", "complete", "cleared", "closed", "expired"}
                )
            ]
            continue
        out[k] = v
    return out


def _shrink_user_with_prior_state(user_text: str) -> Tuple[str, bool]:
    """Try compressing the embedded <prior_state> JSON inside the final user
    message. Returns (new_text, did_change)."""
    m = _PRIOR_STATE_BLOCK_RE.search(user_text)
    if not m:
        return user_text, False
    try:
        prior = _json.loads(m.group(1))
    except Exception:
        return user_text, False
    slim = _compress_prior_state_json(prior)
    if slim == prior:
        return user_text, False
    new_block = (
        "<prior_state>\n"
        + _json.dumps(slim, indent=2, ensure_ascii=False)
        + "\n</prior_state>"
    )
    return user_text[: m.start()] + new_block + user_text[m.end():], True


def _strip_assistant_engine_blocks(text: str) -> Tuple[str, bool]:
    """Remove engine tag blocks from an old assistant turn, keeping narrative."""
    if not text:
        return text, False
    new = _ENGINE_BLOCK_STRIP_RE.sub("", text)
    return new, (new != text)


def enforce_context_budget(
    messages: List[Dict[str, str]],
    budget_tokens: int,
    *,
    protected_recent_msgs: int,
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Trim the message list until under budget. Never touches:
      • the system message (index 0)
      • the last `protected_recent_msgs` messages BEFORE the final user msg
      • the final user message (carries active scene + prior_state)

    Order of operations when over budget:
      1. Compress the final user message's <prior_state> JSON (drop archived /
         resolved / shrink lists).
      2. Strip engine blocks from older assistant messages (keep narrative).
      3. Drop the OLDEST trimmable message until budget is met.

    Returns the (possibly mutated copy of) messages and a diagnostics dict.
    """
    if not messages:
        return messages, {
            "estimated_prompt_tokens": 0,
            "context_budget_tokens": budget_tokens,
            "context_over_budget": False,
            "context_trimmed": False,
            "trim_reason": "",
            "estimated_tokens_removed": 0,
            "protected_state_items_count": 0,
        }

    msgs = [dict(m) for m in messages]
    initial_tokens = estimate_messages_tokens(msgs)
    diag_actions: List[str] = []

    # Index regions:
    #   0           → system (NEVER trim)
    #   1 .. -2     → replay history (oldest first) — trimmable but protect tail
    #   -1          → final user with prior_state (compress in-place only)

    def _last_user() -> Dict[str, str]:
        return msgs[-1]

    # Step 1 — try compressing prior_state in the final user message
    if estimate_messages_tokens(msgs) > budget_tokens:
        new_text, changed = _shrink_user_with_prior_state(
            _last_user().get("content", "")
        )
        if changed:
            msgs[-1]["content"] = new_text
            diag_actions.append("compressed_prior_state")

    # Step 2 — strip engine blocks from older assistant messages
    if estimate_messages_tokens(msgs) > budget_tokens:
        protected_start = max(1, len(msgs) - 1 - protected_recent_msgs)
        for i in range(1, protected_start):
            if msgs[i].get("role") != "assistant":
                continue
            new_text, changed = _strip_assistant_engine_blocks(
                msgs[i].get("content", "")
            )
            if changed:
                msgs[i]["content"] = new_text
                diag_actions.append("stripped_engine_blocks")
                if estimate_messages_tokens(msgs) <= budget_tokens:
                    break

    # Step 3 — drop oldest trimmable messages outright
    while (
        estimate_messages_tokens(msgs) > budget_tokens
        and len(msgs) > (1 + protected_recent_msgs + 1)
    ):
        # drop the message right after the system prompt
        dropped = msgs.pop(1)
        diag_actions.append(f"dropped_{dropped.get('role','?')}")

    final_tokens = estimate_messages_tokens(msgs)

    # Count protected state items still present in final user message.
    protected_count = 0
    m = _PRIOR_STATE_BLOCK_RE.search(_last_user().get("content", ""))
    if m:
        try:
            prior = _json.loads(m.group(1))
            for k in PROTECTED_LIST_KEYS:
                v = prior.get(k)
                if isinstance(v, list):
                    protected_count += len(v)
                elif isinstance(v, dict):
                    protected_count += len(v)
        except Exception:
            pass

    diag = {
        "estimated_prompt_tokens": final_tokens,
        "context_budget_tokens": budget_tokens,
        "context_over_budget": initial_tokens > budget_tokens,
        "context_trimmed": bool(diag_actions),
        "trim_reason": ",".join(diag_actions),
        "estimated_tokens_removed": max(0, initial_tokens - final_tokens),
        "protected_state_items_count": protected_count,
    }
    return msgs, diag
