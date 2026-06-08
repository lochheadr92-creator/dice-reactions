"""
Anti-Hallucination Gateway — Chapter 31 conformance (incremental).

Doctrine (Source of Truth, Ch 31.1):
    "The LLM writes prose. The engine writes truth."

In this engine the LLM still proposes narrative + state each turn, so full
conformance is not yet possible. This gateway is the first step toward it: it
makes the *engine* the authority over a growing set of immutable facts and
refuses to let the LLM silently rewrite them.

It performs three jobs, mirroring Ch 31.5 / 31.11:

  1. PREVENT  — `build_immutable_truth_block` injects the established facts the
     model must not contradict directly into the next prompt.
  2. STRIP    — `strip_illegal_state_changes` silently reverts illegal state
     mutations the model attempted (reviving a destroyed/consumed object,
     resolving a serious wound with no in-world cause, reviving a dead NPC).
  3. DETECT   — `detect_prose_contradictions` flags prose that contradicts the
     established truth so the caller can issue a correction re-prompt.

Authoritative truth = the PRIOR consolidated rolling_state
(`session.rolling_state`) plus the prior turn state-chips
(`session.last_state`). This module never calls the LLM and never imports
`server` (it is imported BY server).
"""

from __future__ import annotations

import re as _re
from typing import Any, Dict, List, Optional

from memory import _normalize_object_name

# Object statuses that are irreversible. dropped / hidden / stored / lost are
# recoverable (the player can pick the item back up), so they are NOT terminal.
TERMINAL_OBJECT_STATUSES = {"destroyed", "consumed"}

# Injury statuses that count as "resolved" (the wound is gone). Reaching one of
# these from a serious prior state without an in-world cause is illegal.
RESOLVED_INJURY_STATUSES = {"resolved", "healed", "cleared", "gone", "fine", "cured"}

# Prior injury states that may not silently improve.
SERIOUS_INJURY_STATUSES = {"active", "worsening"}
_INJURY_SEVERITY_RANK = {"minor": 1, "moderate": 2, "severe": 3, "critical": 4}

# Recovery cue — a recovery/resolution is only legal when one of these appears
# in the player action or the narrative this turn. Kept in sync with
# server._RECOVERY_CUE_RE.
_RECOVERY_CUE_RE = _re.compile(
    r"\b(rest|sleep|treat|treated|bandage|splint|medicine|medic|heal|healing|"
    r"stabilize|stabilise|calm|breathe|recover|recovered|sit\s+down|drink|eat|"
    r"safe\s+place|first\s+aid|patch(?:ed)?\s+up|tend(?:ed)?)\b",
    _re.IGNORECASE,
)

# Death detection. Two shapes: "<name> ... died" and "killed ... <name>".
_DEATH_AFTER_RE = (
    r"(?:is\s+|lies\s+|lay\s+|now\s+|falls?\s+|fell\s+)?"
    r"(?:dead|died|dies|slain|killed|murdered|executed|"
    r"bled\s+out|did\s+not\s+survive|lifeless|a\s+corpse|breathes?\s+no\s+more)"
)
_DEATH_BEFORE_RE = (
    r"(?:kill(?:ed|s)?|slew|slay|slays|murder(?:ed|s)?|execute[ds]?|cut\s+down)"
)
# Words that make a death statement conditional / hypothetical → NOT a death.
_DEATH_NEGATION_RE = _re.compile(
    r"\b(would|could|might|may|if|when|unless|threaten(?:s|ed)?|warn(?:s|ed)?|"
    r"don'?t|do\s+not|won'?t|will\s+not|never|avoid|nearly|almost|risk|fear|"
    r"afraid|swore\s+to|vow(?:s|ed)?\s+to|plan(?:s|ned)?\s+to|tries?\s+to|"
    r"about\s+to|going\s+to|nearly\s+)\b",
    _re.IGNORECASE,
)

# Possession / use verbs used by the prose contradiction check for objects.
_POSSESSION_VERB_RE = (
    r"(?:grab|grabs|grabbed|grabbing|pick(?:s|ed)?(?:\s+up)?|hold(?:s|ing)?|held|"
    r"use(?:s|d)?|using|wield(?:s|ed|ing)?|draw(?:s|n)?|drew|swing(?:s|ing)?|swung|"
    r"reach(?:es|ed)?\s+for|pull(?:s|ed)?\s+out|equip(?:s|ped)?|raise(?:s|d)?|"
    r"lift(?:s|ed)?|carr(?:y|ies|ied)|clutch(?:es|ed)?|grip(?:s|ped)?|brandish(?:es|ed)?)"
)
# Qualifiers near a terminal-object mention that make the reference legitimate
# (the prose is acknowledging the loss, or referring to a different copy).
_OBJECT_OK_QUALIFIER_RE = _re.compile(
    r"\b(another|second|spare|replacement|new|different|other|remains?|"
    r"wreck(?:age)?|ash(?:es)?|charred|burnt|burned|melted|ruined|shattered|"
    r"broken|destroyed|consumed|gone|empty|husk|fragment|shard|splinter|"
    r"memory|remember|recall|wish|miss(?:ed|ing)?|lost|where|used\s+to)\b",
    _re.IGNORECASE,
)

# Speech / live-action verbs for the deceased-NPC prose check.
_LIVE_ACTION_VERB_RE = (
    r"(?:say|says|said|ask|asks|asked|whisper(?:s|ed)?|shout(?:s|ed)?|reply|"
    r"replies|replied|laugh(?:s|ed)?|nod(?:s|ded)?|smile(?:s|d)?|grin(?:s|ned)?|"
    r"step(?:s|ped)?|walk(?:s|ed)?|run(?:s)?|ran|turn(?:s|ed)?\s+to\s+you|"
    r"approach(?:es|ed)?|draw(?:s)?|attack(?:s|ed)?|grab(?:s|bed)?|stand(?:s)?|"
    r"stood|lean(?:s|ed)?|wave(?:s|d)?|call(?:s|ed)?\s+out|greet(?:s|ed)?|"
    r"hand(?:s|ed)?\s+you|offer(?:s|ed)?|point(?:s|ed)?)"
)
# Words that legitimise a dead name appearing (talking ABOUT them, not TO them).
_DECEASED_OK_QUALIFIER_RE = _re.compile(
    r"\b(memor(?:y|ies)|remember|recall|ghost|spirit|corpse|body|bodies|grave|"
    r"buried|dream|vision|portrait|name|legend|story|tale|mourn|grief|funeral|"
    r"dead|killed|died|murder)\b",
    _re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _split_items(value: Any) -> List[str]:
    return [x.strip() for x in _re.split(r"\s*;\s*", str(value or "")) if x.strip()]


def _injury_name(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("name") or row.get("description") or "").strip().lower()
    return ""


def _npc_name(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("name") or "").strip()
    if isinstance(row, str):
        return row.strip()
    return ""


def _noun_tokens(ident: str) -> List[str]:
    """Distinctive single-word tokens of an object identity (len >= 4)."""
    return [t for t in ident.split() if len(t) >= 4]


# ---------------------------------------------------------------------------
# Truth extraction
# ---------------------------------------------------------------------------
def build_truth(prior_rolling: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract the engine's authoritative immutable facts from prior state."""
    truth: Dict[str, Any] = {
        "terminal_objects": {},   # identity -> terminal status
        "deceased": [],           # list of names
        "serious_injuries": [],   # list of {name, severity, status}
    }
    if not isinstance(prior_rolling, dict):
        return truth

    for row in prior_rolling.get("object_locations") or []:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", "")).strip().lower()
        if status in TERMINAL_OBJECT_STATUSES:
            ident = _normalize_object_name(row.get("object"))
            if ident:
                truth["terminal_objects"][ident] = status

    for name in prior_rolling.get("deceased") or []:
        n = _npc_name(name)
        if n:
            truth["deceased"].append(n)

    for row in prior_rolling.get("injuries") or []:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", "")).strip().lower()
        severity = str(row.get("severity", "")).strip().lower()
        if status in SERIOUS_INJURY_STATUSES or severity in {"severe", "critical"}:
            truth["serious_injuries"].append(
                {"name": _injury_name(row), "severity": severity, "status": status}
            )

    return truth


def build_immutable_truth_block(prior_rolling: Optional[Dict[str, Any]]) -> str:
    """Prompt-injection block (engine-only) listing facts the model must obey.

    Returns "" when there is nothing to assert.
    """
    truth = build_truth(prior_rolling)
    lines: List[str] = []

    terminal = list(truth["terminal_objects"].keys())
    if terminal:
        lines.append(
            "- GONE FOREVER (destroyed/consumed — cannot be carried, used, worn, "
            "drawn, or found intact again): "
            + "; ".join(sorted(terminal)[:12])
        )
    if truth["deceased"]:
        lines.append(
            "- DEAD (cannot speak, act, move, or appear alive; reference only as "
            "a corpse, memory, or absence): "
            + "; ".join(truth["deceased"][:12])
        )
    serious = [i["name"] for i in truth["serious_injuries"] if i["name"]]
    if serious:
        lines.append(
            "- ONGOING WOUNDS (cannot vanish or improve without explicit "
            "treatment/rest in-scene): "
            + "; ".join(sorted(set(serious))[:12])
        )

    if not lines:
        return ""

    return (
        "<established_truth>\n"
        "ENGINE-AUTHORITATIVE FACTS. These are TRUE and FINAL. You MUST NOT "
        "contradict them in narrative, choices, state, ledger, or rolling_state. "
        "Do not echo this block.\n"
        + "\n".join(lines)
        + "\n</established_truth>"
    )


# ---------------------------------------------------------------------------
# STRIP — silently revert illegal state mutations on the FRESH parsed turn
# ---------------------------------------------------------------------------
def strip_illegal_state_changes(
    prior_rolling: Optional[Dict[str, Any]],
    prior_state: Optional[Dict[str, Any]],
    parsed: Any,
    player_action: Optional[str],
) -> List[str]:
    """Mutate the FRESH parsed turn (pre-consolidation) to enforce truth.

    Operates on ``parsed.rolling_state``, ``parsed.ledger``. Returns a list of
    adjustment strings for the developer diagnostics panel.
    """
    truth = build_truth(prior_rolling)
    adjustments: List[str] = []
    fresh = parsed.rolling_state if isinstance(parsed.rolling_state, dict) else None
    text = f"{player_action or ''}\n{getattr(parsed, 'narrative', '') or ''}"
    allows_recovery = bool(_RECOVERY_CUE_RE.search(text))

    # --- 1. Terminal object revival -------------------------------------
    terminal = truth["terminal_objects"]
    if terminal and fresh:
        reverted: List[str] = []
        for row in fresh.get("object_locations") or []:
            if not isinstance(row, dict):
                continue
            ident = _normalize_object_name(row.get("object"))
            if ident in terminal and str(row.get("status", "")).strip().lower() \
                    not in TERMINAL_OBJECT_STATUSES:
                row["status"] = terminal[ident]
                reverted.append(ident)
        for row in fresh.get("inventory_objects") or []:
            if not isinstance(row, dict):
                continue
            ident = _normalize_object_name(row.get("object"))
            if ident in terminal and str(row.get("location_state", "")).strip().lower() \
                    not in TERMINAL_OBJECT_STATUSES:
                row["location_state"] = terminal[ident]
                if ident not in reverted:
                    reverted.append(ident)
        if reverted:
            adjustments.append(
                "gateway:terminal_object_revival_blocked:" + " | ".join(reverted[:6])
            )

    # Remove revived terminal objects from the player-facing ledger Carried/Worn.
    if terminal and getattr(parsed, "ledger", None):
        ledger = parsed.ledger
        ledger_removed: List[str] = []
        for cat in ("Carried", "Worn"):
            items = _split_items(ledger.get(cat))
            if not items:
                continue
            survivors = []
            for raw in items:
                if _normalize_object_name(raw) in terminal:
                    ledger_removed.append(f"{cat}:{raw}")
                else:
                    survivors.append(raw)
            if len(survivors) != len(items):
                ledger[cat] = "; ".join(survivors) if survivors else "—"
        if ledger_removed:
            parsed.ledger = ledger
            adjustments.append(
                "gateway:ledger_terminal_object_removed:" + " | ".join(ledger_removed[:6])
            )

    # --- 2. Silent injury resolution / improvement ----------------------
    if truth["serious_injuries"] and fresh and not allows_recovery:
        prior_by_name = {i["name"]: i for i in truth["serious_injuries"] if i["name"]}
        healed: List[str] = []
        for row in fresh.get("injuries") or []:
            if not isinstance(row, dict):
                continue
            name = _injury_name(row)
            prior = prior_by_name.get(name)
            if not prior:
                continue
            new_status = str(row.get("status", "")).strip().lower()
            if new_status in RESOLVED_INJURY_STATUSES and prior.get("status"):
                row["status"] = prior["status"]
                healed.append(f"{name}(status)")
            new_sev = _INJURY_SEVERITY_RANK.get(
                str(row.get("severity", "")).strip().lower(), 0
            )
            old_sev = _INJURY_SEVERITY_RANK.get(prior.get("severity", ""), 0)
            if new_sev and old_sev and new_sev < old_sev:
                row["severity"] = prior["severity"]
                healed.append(f"{name}(severity)")
        if healed:
            adjustments.append(
                "gateway:silent_injury_recovery_blocked:" + " | ".join(healed[:6])
            )

    # --- 3. Deceased NPC revival ----------------------------------------
    deceased = {d.lower() for d in truth["deceased"]}
    if deceased and fresh:
        neutralised: List[str] = []
        for row in fresh.get("npcs") or []:
            if isinstance(row, dict) and _npc_name(row).lower() in deceased:
                if str(row.get("stance", "")).strip().lower() != "dead":
                    row["stance"] = "dead"
                    neutralised.append(_npc_name(row))
        for row in fresh.get("npc_memory") or []:
            if isinstance(row, dict) and _npc_name(row).lower() in deceased:
                if row.get("next_move"):
                    row["next_move"] = "deceased — cannot act"
                    if _npc_name(row) not in neutralised:
                        neutralised.append(_npc_name(row))
        if neutralised:
            adjustments.append(
                "gateway:deceased_npc_revival_blocked:" + " | ".join(neutralised[:6])
            )

    return adjustments


# ---------------------------------------------------------------------------
# Death registry — record new deaths into engine-owned `deceased`
# ---------------------------------------------------------------------------
def update_death_registry(
    parsed: Any,
    prior_rolling: Optional[Dict[str, Any]],
    merged_rolling: Optional[Dict[str, Any]],
    player_action: Optional[str] = None,
) -> List[str]:
    """Detect NPC deaths this turn and persist them into `merged_rolling.deceased`.

    Conservative: only fires when a KNOWN named NPC is the clear subject/object
    of a death verb, and the statement is not hypothetical/threatening.
    """
    if not isinstance(merged_rolling, dict):
        return []

    # Candidate names = NPCs the engine already knows about.
    names: set = set()
    for src in (prior_rolling, merged_rolling):
        if not isinstance(src, dict):
            continue
        for key in ("npcs", "npc_memory", "relationship_threads"):
            for row in src.get(key) or []:
                n = _npc_name(row)
                if n and len(n) >= 2:
                    names.add(n)

    if not names:
        return []

    text = f"{player_action or ''}\n{getattr(parsed, 'narrative', '') or ''}"
    for beat in (merged_rolling.get("recent_beats") or []):
        if isinstance(beat, str):
            text += "\n" + beat
    if not text.strip():
        return []

    already = {str(d).strip().lower() for d in (merged_rolling.get("deceased") or [])}
    newly_dead: List[str] = []

    for name in names:
        if name.lower() in already:
            continue
        esc = _re.escape(name)
        after = _re.compile(rf"\b{esc}\b[^.!?\n]{{0,50}}?\b{_DEATH_AFTER_RE}", _re.IGNORECASE)
        before = _re.compile(rf"\b{_DEATH_BEFORE_RE}\b[^.!?\n]{{0,30}}?\b{esc}\b", _re.IGNORECASE)
        for rx in (after, before):
            m = rx.search(text)
            if not m:
                continue
            # Reject hypothetical / threat phrasing in the matched window.
            window = text[max(0, m.start() - 40): m.end()]
            if _DEATH_NEGATION_RE.search(window):
                continue
            newly_dead.append(name)
            already.add(name.lower())
            break

    if not newly_dead:
        return []

    registry = list(merged_rolling.get("deceased") or [])
    registry.extend(newly_dead)
    # Dedupe preserving order.
    seen: set = set()
    deduped: List[str] = []
    for n in registry:
        k = str(n).strip().lower()
        if k and k not in seen:
            seen.add(k)
            deduped.append(n)
    merged_rolling["deceased"] = deduped
    return ["gateway:death_recorded:" + " | ".join(newly_dead[:6])]


# ---------------------------------------------------------------------------
# DETECT — prose contradictions that warrant a correction re-prompt
# ---------------------------------------------------------------------------
def detect_prose_contradictions(
    prior_rolling: Optional[Dict[str, Any]],
    parsed: Any,
    player_action: Optional[str] = None,
) -> List[str]:
    """Return human-readable reasons the narrative contradicts established truth.

    Conservative by design — false positives cost a re-prompt, so each rule
    requires tight proximity between the offending verb and the protected fact.
    """
    truth = build_truth(prior_rolling)
    reasons: List[str] = []
    paragraphs = getattr(parsed, "paragraphs", None) or []
    if not paragraphs:
        narrative = getattr(parsed, "narrative", "") or ""
        paragraphs = [narrative] if narrative else []
    if not paragraphs:
        return reasons

    joined = "\n".join(paragraphs)

    # 1. Terminal object used/held as if intact.
    for ident in truth["terminal_objects"]:
        for tok in _noun_tokens(ident):
            esc = _re.escape(tok)
            rx = _re.compile(
                rf"\b{_POSSESSION_VERB_RE}\b[\sa-z,'\"-]{{0,25}}\b{esc}\b",
                _re.IGNORECASE,
            )
            m = rx.search(joined)
            if not m:
                continue
            window = joined[max(0, m.start() - 40): m.end() + 40]
            if _OBJECT_OK_QUALIFIER_RE.search(window):
                continue
            reasons.append(
                f"references destroyed/consumed object '{tok}' as if intact and usable"
            )
            break

    # 2. Dead NPC speaking / acting alive.
    for name in truth["deceased"]:
        esc = _re.escape(name)
        rx = _re.compile(
            rf"\b{esc}\b[\sa-z,'\"-]{{0,30}}\b{_LIVE_ACTION_VERB_RE}\b",
            _re.IGNORECASE,
        )
        m = rx.search(joined)
        if not m:
            continue
        window = joined[max(0, m.start() - 40): m.end() + 20]
        if _DECEASED_OK_QUALIFIER_RE.search(window):
            continue
        reasons.append(f"dead NPC '{name}' speaks or acts alive in the narrative")

    return reasons
