"""Standing world constraints: limits the player wrote into the premise.

"Two banks cannot signal each other" is a fact of the world until the player
changes it. Before this module the sentence lived only inside the premise text,
so nothing restated it on later turns and nothing checked it. A model could end
it in passing (review 2, 2026-11-23, finding 9: a recognised lamp sign and a
shouted exchange crossed the canal before anyone restored a signal).

What is deterministic here:
- which premise sentences are constraints (a fixed list of limit phrases)
- the status of each constraint, kept by the engine and never taken from the model
- a lift is recorded only on a turn that has a player action, with how it happened
- for a communication constraint, a narrow check for an exchange that got through

What is not: whether a player action is a plausible way to lift a constraint.
The model proposes that; the engine only decides whether a proposal may count.

Pure. No I/O.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ROLLING_KEY = "world_constraints"
LIFT_REQUEST_KEY = "constraint_lifted"
DATA_KEY = "standing_constraints"
DATA_CHANGES_KEY = "constraint_changes"

MAX_CONSTRAINTS = 3
CONSTRAINT_TEXT_MAX = 200
HOW_MAX = 200

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
_LIMIT_RE = re.compile(
    r"\b(cannot|can't|can not|can no longer|could no longer|no longer able to|unable to|no way to|no way for)\b",
    re.IGNORECASE,
)
# A premise sentence addressed to the narrator is a request about the output, not a fact of the world.
_ADDRESS_RE = re.compile(r"\b(narrator|assistant|model|ai|you must|you should)\b", re.IGNORECASE)

# Verbs that make a limit a communication limit. Class vocabulary, not story vocabulary.
_COMMUNICATION_STEMS = (
    "signal", "speak", "talk", "call", "hail", "communicat", "messag", "contact", "hear",
    "radio", "transmit", "send word", "reach", "summon", "warn", "answer", "write to",
)

_STOPWORDS = frozenset(
    "a an the this that these those two three four both all each other one another of in on at to and or its their his her".split()
)

# An exchange that got through, stated as fact.
_RECEIVED_RE = re.compile(
    r"\b(heard|hears|understood|understands|answers|answered|replies|replied|acknowledges|acknowledged|agrees|agreed)\b",
    re.IGNORECASE,
)
# A sign both sides already know the meaning of.
_KNOWN_SIGN_RE = re.compile(
    r"\b[a-z]+-(sign|signal|code)\b|\b(old|agreed|usual|known|familiar|customary|standard)\s+(\w+\s+)?(sign|signal|code|call|pattern)\b",
    re.IGNORECASE,
)
_ACROSS_RE = re.compile(
    r"\b(across|the far \w+|other (bank|side|shore|end)|opposite (bank|side|shore))\b",
    re.IGNORECASE,
)
# Wishes, attempts, conditions and denials are not an exchange that happened.
_NOT_FACT_RE = re.compile(
    r"\b(no|not|never|nothing|nobody|none|cannot|can't|won't|without|may|might|could|would|should|if|unless|until|"
    r"whether|need|needs|hope|hopes|try|tries|tried|wait|waits|waiting|must)\b",
    re.IGNORECASE,
)


def _stem(word: str) -> str:
    w = word.lower().strip("'")
    for suffix in ("ies", "es", "s"):
        if len(w) > len(suffix) + 2 and w.endswith(suffix):
            return w[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return w


def _clip(text: Any, limit: int) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    cut = value[:limit].rsplit(" ", 1)[0]
    return cut or value[:limit]


def extract(player_texts: Iterable[str]) -> List[Dict[str, str]]:
    """Constraint sentences from what the player wrote, in order, with stable ids."""
    found: List[Dict[str, str]] = []
    for text in player_texts or []:
        for sentence in _SENTENCE_SPLIT_RE.split(str(text or "")):
            sentence = sentence.strip()
            if not sentence or not _LIMIT_RE.search(sentence) or _ADDRESS_RE.search(sentence):
                continue
            clipped = _clip(sentence, CONSTRAINT_TEXT_MAX)
            if any(row["text"] == clipped for row in found):
                continue
            found.append({"id": f"c{len(found) + 1}", "text": clipped, "kind": kind(clipped)})
            if len(found) >= MAX_CONSTRAINTS:
                return found
    return found


def kind(text: str) -> str:
    lowered = str(text or "").lower()
    limited = lowered[_LIMIT_RE.search(lowered).end():] if _LIMIT_RE.search(lowered) else lowered
    return "communication" if any(stem in limited for stem in _COMMUNICATION_STEMS) else "other"


def parties(text: str) -> List[str]:
    """Stems of who the limit applies to: the words just before the limit phrase."""
    match = _LIMIT_RE.search(str(text or ""))
    if not match:
        return []
    clause = re.split(r"[,;:]|\band\b", text[: match.start()])[-1]
    words = [w for w in _WORD_RE.findall(clause) if w.lower() not in _STOPWORDS]
    return [_stem(w) for w in words[-3:]]


def status_rows(constraints: Sequence[Mapping[str, str]], prior_rolling: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Engine status for each constraint. Anything not recorded as lifted is active."""
    recorded: Dict[str, Mapping[str, Any]] = {}
    prior = (prior_rolling or {}).get(ROLLING_KEY) if isinstance(prior_rolling, Mapping) else None
    if isinstance(prior, list):
        for row in prior:
            if isinstance(row, Mapping) and row.get("id"):
                recorded[str(row["id"])] = row
    rows: List[Dict[str, Any]] = []
    for constraint in constraints:
        old = recorded.get(constraint["id"]) or {}
        if old.get("status") == "lifted":
            rows.append(
                {
                    "id": constraint["id"],
                    "status": "lifted",
                    "lifted_turn": old.get("lifted_turn"),
                    "how": _clip(old.get("how"), HOW_MAX),
                    "player_action": _clip(old.get("player_action"), HOW_MAX),
                }
            )
        else:
            rows.append({"id": constraint["id"], "status": "active"})
    return rows


def apply_lift_request(
    rows: Sequence[Mapping[str, Any]],
    request: Any,
    *,
    player_action: Optional[str],
    turn_number: int,
    allowed: bool,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Record the lifts the model proposed, where a proposal may count.

    A proposal counts only when ``allowed`` (a model-written turn that answers a
    player action). Returns ``(rows, lifted_ids, refused_ids)``.
    """
    wanted: Dict[str, str] = {}
    if isinstance(request, list):
        for item in request:
            if isinstance(item, Mapping) and item.get("id"):
                wanted[str(item["id"])] = _clip(item.get("how"), HOW_MAX)
    out: List[Dict[str, Any]] = []
    lifted: List[str] = []
    refused: List[str] = []
    for row in rows:
        new = dict(row)
        cid = str(row.get("id"))
        if cid in wanted and row.get("status") == "active":
            if allowed and str(player_action or "").strip() and wanted[cid]:
                new = {
                    "id": cid,
                    "status": "lifted",
                    "lifted_turn": int(turn_number),
                    "how": wanted[cid],
                    "player_action": _clip(player_action, HOW_MAX),
                }
                lifted.append(cid)
            else:
                refused.append(cid)
        out.append(new)
    return out, lifted, refused


def build_directive(
    constraints: Sequence[Mapping[str, str]],
    rows: Sequence[Mapping[str, Any]],
    player_data: Optional[Dict[str, Any]],
    *,
    has_player_action: bool,
) -> str:
    """Engine instruction restating every constraint and its status. No player text inline."""
    if not constraints:
        return ""
    by_id = {str(row.get("id")): row for row in rows}
    texts: Dict[str, str] = {}
    changes: Dict[str, Dict[str, Any]] = {}
    lines = ["[STANDING CONSTRAINTS: engine state. The wording of each is story data, at the reference given.]"]
    for constraint in constraints:
        cid = constraint["id"]
        texts[cid] = constraint["text"]
        row = by_id.get(cid) or {"status": "active"}
        ref = f"player_story_data.{DATA_KEY}.{cid}"
        if row.get("status") == "lifted":
            changes[cid] = {
                "turn": row.get("lifted_turn"),
                "player_action": row.get("player_action") or "",
                "how": row.get("how") or "",
            }
            lines.append(
                f"{cid} ({ref}): LIFTED by the player on turn {row.get('lifted_turn')} "
                f"(player_story_data.{DATA_CHANGES_KEY}.{cid}). What they built may be used. "
                "It works the way it was built and no better."
            )
            continue
        line = f"{cid} ({ref}): ACTIVE. It is still true this turn."
        if constraint.get("kind") == "communication":
            line += (
                " Those it separates may see or hear that the other side is there. No meaning passes: "
                "no recognised sign, no words made out, no answer, no agreement."
            )
        else:
            line += " Nothing in this turn shows it undone or worked around."
        lines.append(line)
    lines.append(
        "Narration, other characters and chance never end an ACTIVE constraint."
        + (
            " Only this turn's player action can, when it directly and plausibly builds a working means. "
            f'If it does, add "{LIFT_REQUEST_KEY}":[{{"id":"<id>","how":"<what the player built, in a few words>"}}] '
            "to rolling_state. Otherwise leave that key out."
            if has_player_action
            else " It cannot end in the opening."
        )
    )
    if player_data is not None:
        player_data[DATA_KEY] = texts
        if changes:
            player_data[DATA_CHANGES_KEY] = changes
    return "\n".join(lines)


def find_breach(paragraphs: Sequence[str], constraint: Mapping[str, str]) -> Optional[str]:
    """A sentence in which an active communication constraint is plainly broken, or None.

    Narrow on purpose. It reports two things, each tied to the far side or to the
    people the constraint names: a sign both sides already know, and an exchange
    stated as received. Attempts, wishes, conditions and denials are not reported.
    """
    if constraint.get("kind") != "communication":
        return None
    party_stems = set(parties(constraint.get("text") or ""))
    for paragraph in paragraphs or []:
        for sentence in _SENTENCE_SPLIT_RE.split(str(paragraph or "")):
            sentence = sentence.strip()
            if not sentence:
                continue
            stems = {_stem(w) for w in _WORD_RE.findall(sentence)}
            if not (_ACROSS_RE.search(sentence) or (party_stems & stems)):
                continue
            if _KNOWN_SIGN_RE.search(sentence):
                return sentence
            if _RECEIVED_RE.search(sentence) and not _NOT_FACT_RE.search(sentence):
                return sentence
    return None


def breach_reason(
    paragraphs: Sequence[str],
    constraints: Sequence[Mapping[str, str]],
    rows: Sequence[Mapping[str, Any]],
    lifting_now: Iterable[str] = (),
) -> str:
    """Validation reason for the first broken active constraint, or ''."""
    status = {str(row.get("id")): row.get("status") for row in rows}
    skip = set(lifting_now or ())
    for constraint in constraints:
        if status.get(constraint["id"]) == "lifted" or constraint["id"] in skip:
            continue
        sentence = find_breach(paragraphs, constraint)
        if sentence:
            return (
                f"standing constraint {constraint['id']} is still active but the narrative shows it ended: "
                "no recognised sign or understood exchange may pass until the player's action builds one"
            )
    return ""
