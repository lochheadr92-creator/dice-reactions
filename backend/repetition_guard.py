"""
Repetition guard: a turn may not repeat the previous turn's ending or choices.

Pure and deterministic: no I/O, no LLM calls. The engine stores a small
fingerprint of each committed turn on the session and validates the next
model reply against it, so a model that copies its previous reply (seen with
Qwen3.6, 2026-11-21: four turns with the same closing passage and the same six
choices, whatever the player did) is asked to rewrite.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

EDGE_CHARS = 160
MIN_EDGE_CHARS = 80
CHOICE_OVERLAP_LIMIT = 0.75

_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


def _norm(text: Any) -> str:
    return _NON_WORD_RE.sub(" ", str(text or "").lower()).strip()


def _choice_texts(choices: Optional[Sequence[Mapping[str, Any]]]) -> List[str]:
    out = []
    for choice in choices or []:
        text = _norm(choice.get("text") if isinstance(choice, Mapping) else "")
        if text:
            out.append(text)
    return out


def turn_fingerprint(
    paragraphs: Optional[Sequence[str]],
    choices: Optional[Sequence[Mapping[str, Any]]],
) -> Dict[str, Any]:
    """Small record of a committed turn, stored on the session."""
    narrative = _norm(" ".join(paragraphs or []))
    return {
        "head": narrative[:EDGE_CHARS],
        "tail": narrative[-EDGE_CHARS:],
        "choices": _choice_texts(choices),
    }


def repetition_reason(
    previous: Optional[Mapping[str, Any]],
    paragraphs: Optional[Sequence[str]],
    choices: Optional[Sequence[Mapping[str, Any]]],
) -> str:
    """Return why this turn repeats the previous one, or "" when it does not."""
    if not isinstance(previous, Mapping):
        return ""
    current = turn_fingerprint(paragraphs, choices)
    prev_tail = str(previous.get("tail") or "")
    if len(prev_tail) >= MIN_EDGE_CHARS and current["tail"] == prev_tail:
        return (
            "narrative ends with the same passage as the previous turn; write a "
            "new ending that follows from the player's action this turn"
        )
    prev_head = str(previous.get("head") or "")
    if len(prev_head) >= MIN_EDGE_CHARS and current["head"] == prev_head:
        return (
            "narrative opens with the same passage as the previous turn; narrate "
            "the outcome of the player's action this turn"
        )
    prev_choices = set(previous.get("choices") or [])
    now_choices = current["choices"]
    if prev_choices and len(now_choices) >= 3:
        repeated = sum(1 for text in now_choices if text in prev_choices)
        if repeated / len(now_choices) >= CHOICE_OVERLAP_LIMIT:
            return (
                "choices repeat the previous turn's choices; write new choices "
                "that follow from what just happened"
            )
    return ""
