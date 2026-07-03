"""
Prose Length System v2 — deterministic prose modes + local length enforcement.

Doctrine:
    Simulation determines truth. Narration determines presentation.
    Renderer/enforcement determines length. Prose mode affects narration ONLY.

This module is pure and deterministic: no I/O, no LLM calls, no engine state.
It owns:
  • the four prose modes (brief / standard / story / cinematic)
  • legacy S/M/L alias resolution (S/short → brief, M/medium/default → standard,
    L/long → story; cinematic is the explicit fourth mode)
  • the structural prompt directive for each mode
  • narration measurement (paragraph / sentence / character counts)
  • local sentence-boundary trimming for over-budget narration

Over-budget narration is ALWAYS handled here, locally. It must never trigger a
new simulation, regenerate canonical events, or cause another provider request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ProseMode:
    """One presentation-only narration budget. Never touches simulation truth."""

    name: str
    min_paragraphs: int
    max_paragraphs: int
    min_sentences: Optional[int]
    max_sentences: Optional[int]
    min_chars: int
    max_chars: int
    # Raise the completion-token budget so larger modes are not cut mid-output.
    # Floors always LOSE to explicit caps (basic-profile cap, low-cost cap).
    max_tokens_floor: int
    directive: str


PROSE_MODES: Dict[str, ProseMode] = {
    "brief": ProseMode(
        name="brief",
        min_paragraphs=1,
        max_paragraphs=1,
        min_sentences=2,
        max_sentences=4,
        min_chars=300,
        max_chars=600,
        max_tokens_floor=0,
        directive=(
            "[PROSE MODE: BRIEF] Write exactly 1 paragraph of 2-4 sentences "
            "(approx 300-600 characters). Deliver the immediate outcome and "
            "essential dialogue only; minimal description. Do not pad."
        ),
    ),
    "standard": ProseMode(
        name="standard",
        min_paragraphs=2,
        max_paragraphs=3,
        min_sentences=5,
        max_sentences=9,
        min_chars=700,
        max_chars=1200,
        max_tokens_floor=0,
        directive=(
            "[PROSE MODE: STANDARD] Write 2-3 paragraphs, 5-9 sentences total "
            "(approx 700-1200 characters). Cover action, environment, character "
            "reactions, and consequences."
        ),
    ),
    "story": ProseMode(
        name="story",
        min_paragraphs=4,
        max_paragraphs=6,
        min_sentences=10,
        max_sentences=18,
        min_chars=1800,
        max_chars=2400,
        max_tokens_floor=3072,
        directive=(
            "[PROSE MODE: STORY] Write 4-6 paragraphs, 10-18 sentences total "
            "(approx 1800-2400 characters). Build a continuous scene. Include "
            "atmosphere, character thoughts where appropriate, multiple "
            "interactions, dialogue, environment, action, reaction, and "
            "consequence. End naturally. Do not summarise."
        ),
    ),
    "cinematic": ProseMode(
        name="cinematic",
        min_paragraphs=6,
        max_paragraphs=10,
        min_sentences=None,
        max_sentences=None,
        min_chars=3000,
        max_chars=4000,
        max_tokens_floor=4096,
        directive=(
            "[PROSE MODE: CINEMATIC] Write 6-10 paragraphs (approx 3000-4000 "
            "characters). Compose a full scene: detailed description, multiple "
            "actors, dialogue, emotional pacing, environment, action, reaction, "
            "and consequence. End naturally. Do not summarise."
        ),
    ),
}

DEFAULT_PROSE_MODE = "standard"

# Legacy S/M/L compatibility. Unknown / missing values resolve to standard so
# existing sessions and callers keep today's behaviour (700-1200 chars).
_ALIASES: Dict[str, str] = {
    "s": "brief",
    "short": "brief",
    "brief": "brief",
    "m": "standard",
    "medium": "standard",
    "default": "standard",
    "standard": "standard",
    "l": "story",
    "long": "story",
    "story": "story",
    "xl": "cinematic",
    "cinematic": "cinematic",
}


def resolve_prose_mode_name(value: Optional[str]) -> str:
    """Map any legacy or new value onto a canonical mode name (deterministic)."""
    key = str(value or "").strip().lower()
    return _ALIASES.get(key, DEFAULT_PROSE_MODE)


def resolve_prose_mode(value: Optional[str]) -> ProseMode:
    """Resolve a requested value (S/M/L, short/medium/long, mode name, None)."""
    return PROSE_MODES[resolve_prose_mode_name(value)]


def build_prose_directive(mode: ProseMode) -> str:
    """Structural prompt guidance for the mode (engine-only user-message hint)."""
    return mode.directive


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------
# Sentence boundary: terminal punctuation, optional closing quotes/brackets,
# then whitespace or end-of-text. Deliberately simple and deterministic.
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?…]+[\"'”’)\]]*(?:\s+|$)")


def split_sentences(text: str) -> List[str]:
    """Split one paragraph into sentences at safe terminal-punctuation boundaries."""
    sentences: List[str] = []
    start = 0
    for match in _SENTENCE_BOUNDARY_RE.finditer(text):
        chunk = text[start:match.end()].strip()
        if chunk:
            sentences.append(chunk)
        start = match.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def measure_narration(paragraphs: Sequence[str]) -> Dict[str, int]:
    """Measure narration presentation only. Reads nothing but the given text."""
    paragraphs = [p for p in (paragraphs or []) if p]
    return {
        "paragraph_count": len(paragraphs),
        "sentence_count": sum(len(split_sentences(p)) for p in paragraphs),
        # Matches the engine's historical measure: sum of paragraph lengths
        # (paragraph separators are not counted).
        "character_count": sum(len(p) for p in paragraphs),
    }


# ---------------------------------------------------------------------------
# Local trimming — the ONLY over-budget remedy. Never re-calls the model.
# ---------------------------------------------------------------------------
def trim_narration(
    paragraphs: Sequence[str], max_chars: int
) -> Tuple[List[str], bool]:
    """Trim narration to ``max_chars`` at the nearest safe sentence boundary.

    Returns ``(trimmed_paragraphs, trimming_occurred)``. Whole paragraphs are
    kept while they fit; the first overflowing paragraph is cut back to the
    last complete sentence that fits; later paragraphs are dropped. If not even
    one sentence fits (pathological budget), fall back to a word-boundary hard
    cut with an ellipsis so the player never receives empty narration.

    Pure presentation. Input text is never reordered or rewritten, only
    truncated, so trimmed output is always a prefix of the model's narration.
    """
    source = [p for p in (paragraphs or []) if p]
    total = sum(len(p) for p in source)
    if total <= max_chars:
        return list(source), False

    kept_paragraphs: List[str] = []
    used = 0
    for paragraph in source:
        if used + len(paragraph) <= max_chars:
            kept_paragraphs.append(paragraph)
            used += len(paragraph)
            continue

        remaining = max_chars - used
        partial = ""
        for sentence in split_sentences(paragraph):
            candidate = f"{partial} {sentence}".strip() if partial else sentence
            if len(candidate) <= remaining:
                partial = candidate
            else:
                break
        if partial:
            kept_paragraphs.append(partial)
        elif not kept_paragraphs and remaining > 1:
            # Nothing fits at a sentence boundary anywhere — hard cut on a word
            # boundary rather than returning empty narration.
            cut = paragraph[: remaining - 1]
            if " " in cut:
                cut = cut.rsplit(" ", 1)[0]
            cut = cut.rstrip(" ,;:—-")
            if cut:
                kept_paragraphs.append(cut + "…")
        break

    return kept_paragraphs, True
