"""
Deterministic checks applied to every turn after validation and before it is
shown or stored. Model turns and engine fallbacks both pass through here.

Each guard only removes or rearranges text that is already there. None of them
writes new story content, calls a model, or changes state, the ledger or facts.

Added after the second independent review of 2026-11-23:
  - finding 1: a player premise asked for a footer word and the model obeyed;
  - finding 3: turns fell outside the paragraph range shown in Settings;
  - finding 7: a choice claimed "the three names they still agree on" when the
    narrative had just said the witnesses disagreed.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import prose_modes

# --- finding 1: a footer the player's setup text asked the narrator to add ----

# A setup sentence is treated as an output request only when it both tells
# someone to do something to the text (a cue) and names a part of the output.
_OUTPUT_CUE_RE = re.compile(
    r"\b(end|ends|ending|finish|close|begin|start|open|sign|append|add|include|"
    r"write|say|print|repeat|output|prefix|suffix)\b",
    re.IGNORECASE,
)
_OUTPUT_PART_RE = re.compile(
    r"\b(turn|turns|reply|replies|response|responses|message|messages|line|lines|"
    r"paragraph|paragraphs|sentence|sentences|word|words|output|narration|answer|answers|text)\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")
_WORD_RE = re.compile(r"[A-Za-z0-9']+")

FOOTER_MAX_WORDS = 4
FOOTER_MAX_CHARS = 40


def output_request_words(player_texts: Iterable[str]) -> set:
    """Words from setup sentences that ask the narrator to change its output."""
    words: set = set()
    for text in player_texts or []:
        for sentence in _SENTENCE_SPLIT_RE.split(str(text or "")):
            if _OUTPUT_CUE_RE.search(sentence) and _OUTPUT_PART_RE.search(sentence):
                words.update(w.lower() for w in _WORD_RE.findall(sentence))
    return words


def _is_requested_fragment(line: str, request_words: set) -> bool:
    text = line.strip()
    if not text or len(text) > FOOTER_MAX_CHARS:
        return False
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words or len(words) > FOOTER_MAX_WORDS:
        return False
    # A fragment, not prose: no punctuation inside it (one closing mark is allowed).
    if re.search(r"[.!?…,;:]", text[:-1]):
        return False
    return all(word in request_words for word in words)


def strip_requested_footer(
    paragraphs: Sequence[str], player_texts: Iterable[str]
) -> Tuple[List[str], str]:
    """Remove a trailing stand-alone fragment that the player's setup text requested.

    Only the last line of the last paragraph is considered, and only when every
    word of it comes from a setup sentence that asked for an output change. The
    same word inside a normal sentence is story content and is never touched, so
    this is a check on position and origin, not a list of banned words.
    """
    out = [str(p) for p in (paragraphs or [])]
    request_words = output_request_words(player_texts)
    if not out or not request_words:
        return out, ""
    lines = out[-1].split("\n")
    last_line = lines[-1]
    if not _is_requested_fragment(last_line, request_words):
        return out, ""
    remaining = "\n".join(lines[:-1]).rstrip()
    if remaining:
        out[-1] = remaining
    elif len(out) > 1:
        out.pop()
    else:
        # The whole turn was the fragment. Leave it for normal validation.
        return [str(p) for p in paragraphs], ""
    return out, last_line.strip()


# --- finding 3: the paragraph count shown to the player -----------------------


def _sentences(paragraph: str) -> List[str]:
    parts: List[str] = []
    start = 0
    for match in prose_modes._SENTENCE_BOUNDARY_RE.finditer(paragraph):
        piece = paragraph[start : match.end()].strip()
        if piece:
            parts.append(piece)
        start = match.end()
    tail = paragraph[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def fit_paragraph_range(
    paragraphs: Sequence[str], min_paragraphs: int, max_paragraphs: int
) -> Tuple[List[str], bool, bool]:
    """Bring a turn inside its paragraph range by moving paragraph breaks only.

    Too many paragraphs: the two neighbours with the least text are joined, and
    again, until the count fits. Too few: the paragraph with the most sentences
    is split at its middle sentence boundary, and again. Every sentence is kept
    in order; nothing is written or deleted.

    Returns ``(paragraphs, changed, satisfied)``. ``satisfied`` is False only
    when the turn has fewer sentences than the minimum, which no rearrangement
    can fix without inventing text.
    """
    out = [p.strip() for p in (paragraphs or []) if str(p).strip()]
    original = list(out)
    if not out:
        return out, False, False

    while len(out) > max_paragraphs:
        index = min(range(len(out) - 1), key=lambda i: len(out[i]) + len(out[i + 1]))
        out[index : index + 2] = [out[index] + " " + out[index + 1]]

    while len(out) < min_paragraphs:
        counts = [len(_sentences(p)) for p in out]
        index = max(range(len(out)), key=lambda i: (counts[i], len(out[i])))
        if counts[index] < 2:
            break
        sentences = _sentences(out[index])
        cut = len(sentences) // 2
        out[index : index + 1] = [" ".join(sentences[:cut]), " ".join(sentences[cut:])]

    satisfied = min_paragraphs <= len(out) <= max_paragraphs
    return out, out != original, satisfied


# --- finding 7: a choice that states a count the story has not established ----

_NUMBER_WORDS = (
    "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
)
# Only a definite count is checked ("the three names", "those two guards"): it
# claims a set the story has already fixed. "Take two steps back" claims nothing.
# The counted word must be a plain plural, so "the three last saw" is left alone.
_COUNT_RE = re.compile(
    r"\b(?P<det>the|these|those|all|all the|your|their|his|her)\s+"
    r"(?P<number>" + "|".join(_NUMBER_WORDS) + r"|[2-9]|[1-9][0-9]+)\s+(?P<noun>[A-Za-z][A-Za-z'-]+s)\b",
    re.IGNORECASE,
)


def _stem(word: str) -> str:
    w = word.lower().strip("'")
    for suffix in ("ies", "es", "s"):
        if len(w) > len(suffix) + 2 and w.endswith(suffix):
            return w[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return w


def _count_is_established(number: str, noun: str, grounding_sentences: Sequence[str]) -> bool:
    """True when some sentence counts that noun: the number, at most one word, then the noun.

    "three witnesses comparing names" counts witnesses, so it does not establish
    "three names". "the same three shared names" does.
    """
    target = number.lower()
    stem = _stem(noun)
    for sentence in grounding_sentences:
        words = [w.lower() for w in _WORD_RE.findall(sentence)]
        for index, word in enumerate(words):
            if word != target:
                continue
            if any(_stem(following) == stem for following in words[index + 1:index + 3]):
                return True
    return False


def repair_unsupported_counts(
    choices: Sequence[Mapping[str, Any]], grounding_texts: Iterable[str]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Drop a number from a choice when the story has not stated that count.

    "Write the three names they still agree on" becomes "Write the names they
    still agree on" unless some sentence the player has seen (or the accepted
    state) puts that number with that noun. The action itself is kept; only the
    unsupported count goes. A count the story did establish is left alone.
    """
    sentences: List[str] = []
    for text in grounding_texts or []:
        sentences.extend(s for s in _SENTENCE_SPLIT_RE.split(str(text or "")) if s.strip())

    repaired: List[str] = []
    out: List[Dict[str, Any]] = []
    for choice in choices or []:
        row = dict(choice)
        text = str(row.get("text") or "")

        def replace(match: "re.Match[str]") -> str:
            if _count_is_established(match.group("number"), match.group("noun"), sentences):
                return match.group(0)
            return f"{match.group('det')} {match.group('noun')}"

        fixed = _COUNT_RE.sub(replace, text)
        if fixed != text:
            repaired.append(f"{row.get('label', '?')}: {text} -> {fixed}")
            row["text"] = fixed
        out.append(row)
    return out, repaired
