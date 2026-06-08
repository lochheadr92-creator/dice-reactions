"""
Relationship Calculus — Chapter 29 conformance.

Doctrine (Ch 29.1): "A relationship is not a number. A relationship is four numbers."
Each NPC holds a vector toward the PLAYER:

    trust       -100..+100   (will they act predictably / not harm me)
    loyalty        0..100    (will they sacrifice / stay committed)
    fear           0..100    (do they yield to avoid harm)
    resentment     0..100    (do they want to hurt me)

The ENGINE owns these numbers (Ch 31 doctrine). Each turn the engine:
  1. decays neglected relationships toward neutral (Ch 29.10),
  2. detects relationship EVENTS in the player action + narrative and applies the
     canonical deltas from Ch 29.8,
  3. recomputes a derived behavioural state (Ch 29.9) and a coarse stance,
  4. exposes a compact summary to the prompt so the LLM RENDERS behaviour
     consistent with the vector (it never writes the numbers).

The relationship of every NPC toward the player is stored in
``rolling_state['relationship_vectors']`` (a PROTECTED_LIST_KEY).

This module never calls the LLM and never imports ``server``.
"""

from __future__ import annotations

import re as _re
from typing import Any, Dict, List, Optional

from memory import _normalize_object_name  # reused only for stable hyphen/token cleanup

DIMENSIONS = ("trust", "loyalty", "fear", "resentment")
_RANGES = {"trust": (-100, 100), "loyalty": (0, 100), "fear": (0, 100), "resentment": (0, 100)}

# Per-turn neglect decay toward neutral (Ch 29.10 — a turn stands in for "a span
# of time"). Identity bonds decay 10x slower.
_DECAY = {"trust": 0.04, "loyalty": 0.01, "fear": 0.08, "resentment": 0.04}

# Canonical event deltas. The Ch 29.8 table plus lighter interaction-derived
# events. Sign convention matches the dimension valence.
EVENT_DELTAS: Dict[str, Dict[str, int]] = {
    # --- Ch 29.8 table ---
    "betrayal":     {"trust": -60, "loyalty": -50, "fear": +20, "resentment": +70},
    "save_life":    {"trust": +30, "loyalty": +20, "fear": -10, "resentment": -20},
    "humiliate":    {"trust": -15, "loyalty": -10, "fear": +10, "resentment": +30},
    "break_promise":{"trust": -20, "loyalty": -10, "fear": 0,   "resentment": +15},
    "keep_promise": {"trust": +10, "loyalty": +5,  "fear": 0,   "resentment": -5},
    "apology":      {"trust": +10, "loyalty": 0,   "fear": -5,  "resentment": -25},
    "reward":       {"trust": +15, "loyalty": +20, "fear": -5,  "resentment": -10},
    # --- interaction-derived (lighter) ---
    "attack":       {"trust": -25, "loyalty": -15, "fear": +30, "resentment": +30},
    "threaten":     {"trust": -10, "loyalty": -5,  "fear": +25, "resentment": +15},
    "lie":          {"trust": -15, "loyalty": -5,  "fear": 0,   "resentment": +12},
    "help":         {"trust": +12, "loyalty": +8,  "fear": -4,  "resentment": -8},
    "gift":         {"trust": +8,  "loyalty": +10, "fear": -2,  "resentment": -6},
}

# Detection verbs (player acting toward the NPC). Checked in this order so the
# stronger event in a conflicting group wins; conflicts are pruned below.
_EVENT_VERBS = {
    "betrayal": _re.compile(
        r"\b(betray(?:s|ed)?|double[\s-]?cross(?:ed)?|sell\s+\w+\s+out|sold\s+\w+\s+out|"
        r"turn(?:ed)?\s+\w+\s+in|hand(?:ed)?\s+\w+\s+over\s+to|rat(?:ted|ed)?\s+\w+\s+out)\b",
        _re.IGNORECASE),
    "attack": _re.compile(
        r"\b(attack(?:s|ed)?|strike|struck|stab(?:bed)?|shoot|shot|punch(?:ed)?|"
        r"slash(?:ed)?|wound(?:ed)?|beat|assault(?:ed)?|fire[sd]?\s+at|swing\s+at|"
        r"hit|club(?:bed)?|choke[sd]?|grab(?:bed)?\s+\w+\s+by\s+the\s+throat)\b",
        _re.IGNORECASE),
    "threaten": _re.compile(
        r"\b(threaten(?:s|ed)?|intimidate[sd]?|menace[sd]?|coerce[sd]?|"
        r"aim(?:ed)?\s+at|point(?:ed)?\s+\w*\s*\w*\s*at|at\s+gunpoint|at\s+knifepoint)\b",
        _re.IGNORECASE),
    "save_life": _re.compile(
        r"\b(save[sd]?|saved|rescue[sd]?|rescued|pull(?:ed)?\s+\w+\s+to\s+safety|"
        r"drag(?:ged)?\s+\w+\s+clear|shield(?:ed)?\s+\w+|haul(?:ed)?\s+\w+\s+out|"
        r"kept?\s+\w+\s+alive)\b",
        _re.IGNORECASE),
    "humiliate": _re.compile(
        r"\b(humiliate[sd]?|mock(?:ed)?|insult(?:ed)?|ridicule[sd]?|shame[sd]?|"
        r"belittle[sd]?|demean(?:ed)?|spit\s+on|laugh(?:ed)?\s+at|sneer(?:ed)?\s+at)\b",
        _re.IGNORECASE),
    "break_promise": _re.compile(
        r"\b(break\s+\w*\s*promise|broke\s+\w*\s*promise|go\s+back\s+on|went\s+back\s+on|"
        r"renege[d]?|abandon(?:ed)?|leave\s+\w+\s+behind|left\s+\w+\s+behind)\b",
        _re.IGNORECASE),
    "keep_promise": _re.compile(
        r"\b(keep\s+\w*\s*promise|kept\s+\w*\s*promise|fulfil+(?:ed)?\s+\w*\s*(?:promise|oath|word)|"
        r"honou?r(?:ed)?\s+\w*\s*(?:promise|word|deal|oath))\b",
        _re.IGNORECASE),
    "apology": _re.compile(
        r"\b(apologi[sz]e[sd]?|apolog(?:y|ies)|say\s+sorry|said\s+sorry|"
        r"beg\s+\w*\s*forgiveness|make\s+amends|made\s+amends|atone[sd]?)\b",
        _re.IGNORECASE),
    "reward": _re.compile(
        r"\b(reward(?:ed)?|pay|paid|bribe[sd]?|tip(?:ped)?|compensate[sd]?|"
        r"promote[sd]?|repay|repaid)\b",
        _re.IGNORECASE),
    "lie": _re.compile(
        r"\b(lie\s+to|lied\s+to|deceive[sd]?|deceived|trick(?:ed)?|mislead|misled|"
        r"con(?:ned)?|dupe[sd]?|bluff(?:ed)?|cheat(?:ed)?)\b",
        _re.IGNORECASE),
    "help": _re.compile(
        r"\b(help(?:s|ed)?|aid(?:ed)?|assist(?:ed)?|support(?:ed)?|defend(?:ed)?|"
        r"protect(?:ed)?|heal(?:ed)?|treat(?:ed)?|bandage[sd]?|free[sd]?|untie[sd]?|"
        r"cover(?:ed)?\s+for|stand\s+up\s+for|stood\s+up\s+for)\b",
        _re.IGNORECASE),
    "gift": _re.compile(
        r"\b(give[sd]?|gave|gift(?:ed)?|offer(?:ed)?|share[sd]?|hand(?:ed)?\s+\w+\s+to)\b",
        _re.IGNORECASE),
}

# Events that subsume weaker overlapping ones in the same turn.
_SUBSUMES = {
    "betrayal": {"lie", "break_promise", "threaten", "attack"},
    "attack": {"threaten"},
    "save_life": {"help"},
    "reward": {"gift"},
}

# Hypothetical / intent guard — a threatened or considered action is not an event.
_HYPOTHETICAL_RE = _re.compile(
    r"\b(would|could|might|may|if|unless|consider(?:s|ing)?|think(?:s|ing)?\s+about|"
    r"plan(?:s|ned)?\s+to|want(?:s|ed)?\s+to|tr(?:y|ies|ying)\s+to|about\s+to|"
    r"going\s+to|almost|nearly|threaten(?:s|ed)?\s+to|refuse[sd]?\s+to|decline[sd]?\s+to)\b",
    _re.IGNORECASE,
)


def _clamp(dim: str, value: float) -> int:
    lo, hi = _RANGES[dim]
    return int(round(max(lo, min(hi, value))))


def _new_vector(name: str, turn: int, bond: str = "neutral") -> Dict[str, Any]:
    return {"name": name, "trust": 0, "loyalty": 0, "fear": 0, "resentment": 0,
            "last_turn": turn, "bond": bond, "state": "neutral"}


def _candidate_names(*sources) -> List[str]:
    names: List[str] = []
    seen = set()
    for src in sources:
        if not isinstance(src, dict):
            continue
        for key in ("npcs", "npc_memory", "relationship_threads"):
            for row in src.get(key) or []:
                name = ""
                if isinstance(row, dict):
                    name = str(row.get("name") or "").strip()
                elif isinstance(row, str):
                    name = row.strip()
                if name and len(name) >= 2 and name.lower() not in seen:
                    seen.add(name.lower())
                    names.append(name)
    return names


def _verb_hits_name(text: str, verb_re, esc_name: str, window: int = 70) -> bool:
    """True if a verb and the NPC name co-occur within `window`, not hypothetical."""
    name_re = _re.compile(rf"\b{esc_name}\b", _re.IGNORECASE)
    for vm in verb_re.finditer(text):
        seg = text[max(0, vm.start() - window): vm.end() + window]
        if name_re.search(seg):
            guard = text[max(0, vm.start() - 25): vm.end()]
            if not _HYPOTHETICAL_RE.search(guard):
                return True
    return False


def _detect_events(text: str, esc_name: str) -> List[str]:
    matched = [ev for ev, rx in _EVENT_VERBS.items() if _verb_hits_name(text, rx, esc_name)]
    if not matched:
        return []
    matched_set = set(matched)
    for strong, weak in _SUBSUMES.items():
        if strong in matched_set:
            matched_set -= weak
    return [ev for ev in _EVENT_VERBS if ev in matched_set]


def _derive_state(v: Dict[str, Any]) -> str:
    t, lo, f, r = v["trust"], v["loyalty"], v["fear"], v["resentment"]
    if t < -50 and lo < 20:
        return "collapsed"
    if r >= 70 and r > lo:
        return "betrayal_risk"
    if f >= 70:
        return "cowed"
    if lo >= 70:
        return "devoted"
    if t >= 50 and r < 40:
        return "trusting"
    if r >= 40:
        return "resentful"
    if f >= 40:
        return "wary"
    return "neutral"


def _stance_for(state: str) -> Optional[str]:
    """Coarse stance the engine will assert when the signal is strong."""
    if state in ("devoted", "trusting"):
        return "ally"
    if state in ("collapsed", "betrayal_risk"):
        return "hostile"
    return None  # leave the model's stance untouched for ambiguous middles


def update_relationship_calculus(
    parsed: Any,
    prior_rolling: Optional[Dict[str, Any]],
    merged_rolling: Optional[Dict[str, Any]],
    player_action: Optional[str] = None,
    current_turn: int = 0,
) -> List[str]:
    """Recompute every NPC→player relationship vector for this turn.

    Reads the AUTHORITATIVE prior vectors from ``prior_rolling`` (so an LLM that
    invents vectors cannot poison them), applies decay + detected events, and
    writes the result into ``merged_rolling['relationship_vectors']``.
    """
    if not isinstance(merged_rolling, dict):
        return []

    deceased = {str(d).strip().lower() for d in (merged_rolling.get("deceased") or [])}
    text = f"{player_action or ''}\n{getattr(parsed, 'narrative', '') or ''}"

    # Authoritative prior vectors keyed by lowercased name.
    prior_vectors: Dict[str, Dict[str, Any]] = {}
    src = prior_rolling.get("relationship_vectors") if isinstance(prior_rolling, dict) else None
    for row in src or []:
        if isinstance(row, dict) and row.get("name"):
            prior_vectors[str(row["name"]).strip().lower()] = dict(row)

    names = _candidate_names(prior_rolling, merged_rolling)
    # Keep any prior-tracked NPC even if absent this turn (so they keep decaying).
    for key in prior_vectors:
        if key not in {n.lower() for n in names}:
            names.append(prior_vectors[key].get("name", key))

    out: List[Dict[str, Any]] = []
    adjustments: List[str] = []

    for name in names:
        key = name.strip().lower()
        if key in deceased:
            continue
        vec = prior_vectors.get(key) or _new_vector(name, current_turn)
        # normalise shape
        for d in DIMENSIONS:
            vec[d] = _clamp(d, vec.get(d, 0))
        vec.setdefault("bond", "neutral")
        identity = vec.get("bond") == "identity"

        events = _detect_events(text, _re.escape(name))

        if events:
            for ev in events:
                for d, delta in EVENT_DELTAS[ev].items():
                    vec[d] = _clamp(d, vec[d] + delta)
            vec["last_turn"] = current_turn
            adjustments.append(f"{name}:{'+'.join(events)}")
        else:
            # Neglect decay toward neutral.
            factor = 0.1 if identity else 1.0
            for d in DIMENSIONS:
                vec[d] = _clamp(d, vec[d] * (1 - _DECAY[d] * factor))

        vec["state"] = _derive_state(vec)
        out.append(vec)

    merged_rolling["relationship_vectors"] = out

    # Assert coarse stance from strong relationship signals (engine writes truth).
    _sync_stance(merged_rolling, out)

    if adjustments:
        return ["rel:" + " | ".join(adjustments[:8])]
    return []


def _sync_stance(merged_rolling: Dict[str, Any], vectors: List[Dict[str, Any]]) -> None:
    by_name = {v["name"].strip().lower(): v for v in vectors if v.get("name")}
    for row in merged_rolling.get("npcs") or []:
        if not isinstance(row, dict):
            continue
        v = by_name.get(str(row.get("name", "")).strip().lower())
        if not v:
            continue
        stance = _stance_for(v["state"])
        if stance and str(row.get("stance", "")).lower() not in ("dead",):
            row["stance"] = stance


# ---------------------------------------------------------------------------
# Prompt injection — tell the LLM how each NPC currently feels (engine truth).
# ---------------------------------------------------------------------------
_STATE_GUIDANCE = {
    "collapsed": "relationship has collapsed — refuses cooperation, avoids or opposes you",
    "betrayal_risk": "resentment outweighs loyalty — may betray, sabotage, or turn on you",
    "cowed": "ruled by fear — submits, complies, or flees rather than resist",
    "devoted": "deeply loyal — defends you, follows you, will not betray you",
    "trusting": "trusts you — cooperates, shares information, trades openly",
    "resentful": "harbours resentment — uncooperative, cold, looks for payback",
    "wary": "wary and guarded — cautious, slow to cooperate",
    "neutral": "neutral — no strong feeling either way",
}


def build_relationship_block(rolling: Optional[Dict[str, Any]]) -> str:
    """Compact engine-truth summary of NPC feelings for the prompt. '' if none."""
    if not isinstance(rolling, dict):
        return ""
    vectors = rolling.get("relationship_vectors") or []
    lines: List[str] = []
    for v in vectors:
        if not isinstance(v, dict) or not v.get("name"):
            continue
        if all(int(v.get(d, 0)) == 0 for d in DIMENSIONS):
            continue
        state = v.get("state") or "neutral"
        guide = _STATE_GUIDANCE.get(state, "")
        lines.append(
            f"- {v['name']} (toward you): trust {int(v.get('trust', 0))}, "
            f"loyalty {int(v.get('loyalty', 0))}, fear {int(v.get('fear', 0))}, "
            f"resentment {int(v.get('resentment', 0))} → {state}: {guide}"
        )
    if not lines:
        return ""
    return (
        "<relationships>\n"
        "ENGINE-OWNED relationship vectors (NPC feelings toward the player). These "
        "numbers are TRUE and final — render each NPC's tone, dialogue, and choices "
        "to match. Do NOT restate the numbers or change them.\n"
        + "\n".join(lines[:12])
        + "\n</relationships>"
    )
