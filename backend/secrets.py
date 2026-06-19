"""
Secret Reveal Trigger v1 — deterministic engine-state transitions.

Secrets live in rolling_state.secret_registry. Only explicit player confession
may reveal an unrevealed entry. The LLM never authors or mutates registry truth.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_REVEAL_POLICY = "explicit_player_confession"
DIRECTIVE_MARKER = "[SECRET_REVEAL_DIRECTIVE_V1]"
DIRECTIVE_PROSE_PATTERNS = (
    r"INTERNAL\s+—\s+revealed\s+secret\s+continuity",
    r"NEW\s+CONFESSION\s+THIS\s+TURN",
    r"ESTABLISHED\s+REVEALED\s+TRUTH\s+\(continuity\s+only\)",
)


def build_stable_secret_id(registry_index: int) -> str:
    """Deterministic ID from stable zero-based registry position."""
    return f"secret-{registry_index + 1}"

# ---------------------------------------------------------------------------
# Explicit confession detection (narrow, deterministic)
# ---------------------------------------------------------------------------
_WEAK_ADMIT_RE = re.compile(
    r"\badmit\s+(?:that\s+)?i\s+(?:do\s+not|don'?t)\s+know\b",
    re.IGNORECASE,
)

_NEGATION_RES = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(?:will|won't|wont|would|refuse|refusing|never)\s+(?:not\s+)?(?:reveal|confess|admit)\b",
        r"\b(?:don't|do not|not)\s+(?:reveal|confess|tell|share)(?:\s+\w+){0,3}\s+(?:my|the)\s+secret\b",
        r"\bkeep\s+(?:my\s+)?(?:past|secret)\s+hidden\b",
        r"\bpretend\s+to\s+confess\b",
        r"\b(?:someone|somebody)\s+else'?s?\s+secret\b",
        r"\bthreaten(?:ing)?\s+to\s+reveal\b",
        r"\bask\s+(?:whether|if)\b.*\bsecret\b",
        r"\bwhether\s+.*\s+has\s+a\s+secret\b",
        r"\breveal\s+(?:someone|somebody|his|her|their|your)\b",
        r"\bconfess\s+(?:his|her|their|your)\b",
        r"\btell\s+(?:them|him|her)\s+(?:his|her|their|your)\s+secret\b",
    )
]

_POSITIVE_RES = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(?:reveal|confess)\s+(?:my\s+)?secret\b",
        r"\btell\s+(?:them|him|her|everyone|the\s+group)\s+(?:my\s+)?secret\b",
        r"\bcome\s+clean\b",
        r"\badmit\s+what\s+i\s+(?:did|have\s+done)\b",
        r"\btell\s+(?:her|him|them)\s+the\s+truth\s+about\s+what\s+i\s+did\b",
        r"\bi\s+confess(?:\s+my\s+secret)?\b",
        r"\bi\s+come\s+clean\s+about\s+my\s+(?:past|secret)\b",
    )
]


def normalize_action_text(action_text: str) -> str:
    return re.sub(r"\s+", " ", (action_text or "").strip().lower())


def detects_explicit_confession(action_text: str) -> bool:
    """True when the player deliberately confesses their own hidden secret."""
    text = normalize_action_text(action_text)
    if not text:
        return False
    if _WEAK_ADMIT_RE.search(text):
        return False
    for pat in _NEGATION_RES:
        if pat.search(text):
            return False
    for pat in _POSITIVE_RES:
        if pat.search(text):
            return True
    return False


def _eligible_unrevealed(registry: List[Any]) -> List[Tuple[int, Dict[str, Any]]]:
    eligible: List[Tuple[int, Dict[str, Any]]] = []
    for idx, entry in enumerate(registry):
        if not isinstance(entry, dict):
            continue
        if entry.get("revealed"):
            continue
        policy = entry.get("reveal_policy") or DEFAULT_REVEAL_POLICY
        if policy != DEFAULT_REVEAL_POLICY:
            continue
        eligible.append((idx, entry))
    eligible.sort(key=lambda pair: (pair[1].get("turn_added", 0), pair[0]))
    return eligible


def build_revealed_secret_directive(
    rolling_state: Optional[Dict[str, Any]],
    current_turn: int,
) -> str:
    """Internal system directive for revealed secrets only. Empty if none revealed."""
    if not isinstance(rolling_state, dict):
        return ""
    registry = rolling_state.get("secret_registry") or []
    if not isinstance(registry, list):
        return ""

    revealed_entries = [e for e in registry if isinstance(e, dict) and e.get("revealed")]
    if not revealed_entries:
        return ""

    lines = [
        DIRECTIVE_MARKER,
        "INTERNAL — revealed secret continuity (engine truth). React naturally; "
        "do not exposition-dump. Do not alter, delete, or rewrite these canonical secrets.",
    ]
    for entry in revealed_entries:
        secret_text = str(entry.get("secret") or "").strip()
        if not secret_text:
            continue
        revealed_turn = entry.get("revealed_turn")
        if revealed_turn == current_turn:
            lines.append(
                "NEW CONFESSION THIS TURN: The player has just deliberately revealed "
                f"this truth: {secret_text}"
            )
        else:
            lines.append(
                f"ESTABLISHED REVEALED TRUTH (continuity only): {secret_text}"
            )
    if len(lines) <= 2:
        return ""
    return "\n".join(lines)


def prepare_turn_reveal(
    rolling_state: Optional[Dict[str, Any]],
    player_action: str,
    next_turn_number: int,
) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
    """
    Copy-on-write reveal transition before generation.

    Returns:
        working_rolling — deep-copied rolling state (reveal applied if eligible)
        directive — internal LLM directive from working state
        diagnostics — non-sensitive reveal metadata (no secret text)
    """
    working = copy.deepcopy(rolling_state) if rolling_state else {}
    diagnostics: Dict[str, Any] = {}

    registry = working.get("secret_registry")
    if not isinstance(registry, list):
        registry = []
        working["secret_registry"] = registry

    if detects_explicit_confession(player_action):
        eligible = _eligible_unrevealed(registry)
        if eligible:
            idx, _entry = eligible[0]
            new_registry = copy.deepcopy(registry)
            updated = dict(new_registry[idx])
            updated["revealed"] = True
            updated["revealed_turn"] = next_turn_number
            updated["reveal_mode"] = "player_confession"
            new_registry[idx] = updated
            working["secret_registry"] = new_registry
            diagnostics["secret_reveal_occurred"] = True
            diagnostics["secret_reveal_mode"] = "player_confession"
            diagnostics["secret_reveal_index"] = idx
            if updated.get("secret_id"):
                diagnostics["secret_reveal_id"] = updated["secret_id"]

    directive = build_revealed_secret_directive(working, next_turn_number)
    return working, directive, diagnostics


def enforce_authoritative_registry(
    merged_rolling: Dict[str, Any],
    authoritative_registry: Optional[List[Any]],
) -> List[str]:
    """Restore engine-owned secret_registry after consolidation."""
    auth = copy.deepcopy(authoritative_registry) if authoritative_registry else []
    model_registry = merged_rolling.get("secret_registry")
    if model_registry != auth:
        merged_rolling["secret_registry"] = auth
        return ["secret_registry_model_mutation_stripped"]
    return []


def merge_reveal_diagnostics(meta: Dict[str, Any], diagnostics: Dict[str, Any]) -> None:
    """Attach non-sensitive reveal diagnostics to generation meta in-place."""
    for key, value in diagnostics.items():
        meta[key] = value