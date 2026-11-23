"""
Repetition guard: a turn may not repeat the previous turn's ending or choices, or copy
a long passage from a recent turn.

Pure and deterministic: no I/O, no LLM calls. The engine stores a small
fingerprint of each committed turn on the session and validates the next
model reply against it, so a model that copies its previous reply (seen with
Qwen3.6, 2026-11-21: four turns with the same closing passage and the same six
choices, whatever the player did) is asked to rewrite. The passage check (2026-11-23) catches the
same copying when it sits mid-turn, which the edge fingerprint cannot see.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

EDGE_CHARS = 160
MIN_EDGE_CHARS = 80
CHOICE_OVERLAP_LIMIT = 0.75
# Words in a row shared with a recent turn. Recorded on Grok turns (2026-11-23, 47 turns with
# history): a stable description ("the woman at the grey horse's head") runs 7 to 8 words, an
# established clue restated runs 14, and the two copied passages ran 18. Starting value from a
# small sample, to be revisited with more turns.
SHARED_RUN_LIMIT = 16
MAX_QUOTED_CHARS = 100

_NON_WORD_RE = re.compile(r"[^a-z0-9]+")
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['\u2019][A-Za-z]+)?")


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


def _tokens(text: Any) -> List[Tuple[str, str]]:
    """(form used to compare, as written) for each word. Apostrophes are dropped to compare."""
    out = []
    for match in _TOKEN_RE.finditer(str(text or "")):
        written = match.group(0)
        out.append((written.lower().replace("'", "").replace("\u2019", ""), written))
    return out


def copied_passage_reason(
    previous_texts: Optional[Sequence[str]],
    paragraphs: Optional[Sequence[str]],
) -> str:
    """Why this turn copies a passage from a recent turn, or "" when it does not.

    `previous_texts` are the narratives of the last few committed turns. The reason
    quotes the first copied run so the model can find it.
    """
    size = SHARED_RUN_LIMIT
    current = _tokens(" ".join(paragraphs or []))
    if len(current) < size:
        return ""
    seen = set()
    for text in previous_texts or []:
        words = [form for form, _ in _tokens(text)]
        seen.update(tuple(words[i:i + size]) for i in range(len(words) - size + 1))
    if not seen:
        return ""
    forms = [form for form, _ in current]
    for start in range(len(forms) - size + 1):
        if tuple(forms[start:start + size]) in seen:
            quoted = " ".join(written for _, written in current[start:start + size])
            if len(quoted) > MAX_QUOTED_CHARS:
                # The "fresh" retry style cuts a reason at 200 characters; keep the instruction whole.
                quoted = quoted[:MAX_QUOTED_CHARS].rsplit(" ", 1)[0] + "..."
            return (
                f'the narrative repeats a passage from a recent turn: "{quoted}". '
                "Write what is new this turn instead."
            )
    return ""
