"""
HUD shaping — player-facing status chips + non-prescriptive PRESSURE line.

Design intent (per product direction): the HUD must NOT behave like a quest /
objective marker. It states the player's current CONDITION and the most immediate
PROBLEM, never the solution or the "correct" next action. Bad choices remain
fully available; consequences come from cause-and-effect elsewhere, not from
steering the player here.

This module:
  * removes any "Objective" guidance from the turn state,
  * guarantees Danger (DNG) and Momentum (MOM) chips with a sane vocabulary,
  * derives a single most-immediate Pressure (PRS) grounded in current state,
    preferring a hard survival flag, then the model's grounded phrasing, then
    a derived fallback — and rejects anything that reads like an instruction.

It never calls the LLM.
"""

from __future__ import annotations

import re as _re
from typing import Any, Dict, List, Optional

DANGER_VALUES = {"none", "low", "elevated", "high", "critical"}
MOMENTUM_VALUES = {"surging", "steady", "stalling", "declining", "lost"}

# Language that turns a PRESSURE into an objective / instruction / solution.
_PRESCRIPTIVE_RE = _re.compile(
    r"\b(find|finds|locate|locates|secure|secures|reach|reaches|get|gets|retrieve|"
    r"obtain|acquire|search|seek|gather|collect|head\s+to|go\s+to|return\s+to|"
    r"escape|flee\s+to|run\s+to|hide|use\s+the|talk\s+to|speak\s+to|kill|defeat|"
    r"craft|build|repair|restore|deliver|bring|reach\s+for|must|need\s+to|"
    r"should|have\s+to|objective|goal|mission|task|quest)\b",
    _re.IGNORECASE,
)


def _inj_name(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("name") or row.get("description") or "").strip()
    if isinstance(row, str):
        return row.strip()
    return ""


def _worst_injury(rolling: Dict[str, Any]) -> Optional[str]:
    best = None
    best_rank = -1
    rank = {"minor": 1, "moderate": 2, "severe": 3, "critical": 4}
    for row in rolling.get("injuries") or []:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", "")).lower()
        if status in ("resolved", "healed", "cleared", "gone"):
            continue
        sev = rank.get(str(row.get("severity", "")).lower(), 1)
        if status == "worsening":
            sev += 1
        if sev > best_rank and _inj_name(row):
            best_rank = sev
            best = _inj_name(row)
    return best


def _clean_phrase(text: str) -> str:
    return _re.sub(r"\s+", " ", str(text or "")).strip().rstrip(".")


def derive_pressure(state: Dict[str, Any], rolling: Dict[str, Any],
                    llm_pressure: Optional[str]) -> str:
    """Return the single most-immediate, non-prescriptive pressure phrase."""
    health = str(state.get("Health", "")).lower()
    worst = _worst_injury(rolling)

    # 1. Survival-critical hard flags always win (guaranteed grounded).
    if health == "critical":
        return f"{worst.capitalize()} worsening" if worst else "Bleeding out"
    if health == "badly wounded" and worst:
        return f"{worst.capitalize()} worsening"

    # 2. Model-authored phrase — only if grounded AND not an instruction.
    phrase = _clean_phrase(llm_pressure)
    if phrase and len(phrase) <= 64 and not _PRESCRIPTIVE_RE.search(phrase):
        return phrase

    # 3. Engine-derived fallbacks, most immediate first.
    threats = rolling.get("active_threats") or rolling.get("unresolved_threats") or []
    if threats:
        return "Unseen threat closing in"
    stress = str(state.get("Stress", "")).lower()
    if stress == "breaking":
        return "Mind beginning to fracture"
    if stress == "distorted":
        return "Grip on reality slipping"
    fatigue = str(state.get("Fatigue", "")).lower()
    if fatigue == "collapsing":
        return "On the verge of collapse"
    instability = str(rolling.get("world_instability", "")).lower()
    if instability in ("high", "critical", "severe", "rising"):
        return "The situation is unravelling"
    if worst:
        return f"{worst.capitalize()} aches"
    if health in ("wounded", "badly wounded"):
        return "Wound throbbing"
    if fatigue == "exhausted":
        return "Exhaustion setting in"
    return ""


def _derive_danger(state: Dict[str, Any], rolling: Dict[str, Any]) -> str:
    health = str(state.get("Health", "")).lower()
    stress = str(state.get("Stress", "")).lower()
    threats = rolling.get("active_threats") or rolling.get("unresolved_threats") or []
    if health == "critical" or stress == "breaking":
        return "critical"
    if threats or health == "badly wounded":
        return "high"
    if health == "wounded" or stress in ("overloaded", "distorted"):
        return "elevated"
    if health in ("bruised",) or stress == "tense":
        return "low"
    return "none"


def shape_hud(state: Optional[Dict[str, Any]], rolling: Optional[Dict[str, Any]]) -> List[str]:
    """Mutate `state` in place: drop Objective, ensure DNG/MOM, set PRS.

    Returns adjustment strings for the developer diagnostics panel.
    """
    if not isinstance(state, dict):
        return []
    rolling = rolling if isinstance(rolling, dict) else {}
    adjustments: List[str] = []

    # 1. No objective / quest guidance in the player-facing HUD.
    for key in ("Objective", "objective", "Goal", "Goals"):
        if key in state:
            state.pop(key, None)
            adjustments.append("hud:objective_removed")

    # 2. Danger chip.
    danger = str(state.get("Danger", "")).strip().lower()
    if danger not in DANGER_VALUES:
        state["Danger"] = _derive_danger(state, rolling)
    else:
        state["Danger"] = danger

    # 3. Momentum chip.
    momentum = str(state.get("Momentum", "")).strip().lower()
    state["Momentum"] = momentum if momentum in MOMENTUM_VALUES else "steady"

    # 4. Pressure line (single most-immediate, non-prescriptive).
    pressure = derive_pressure(state, rolling, state.get("Pressure"))
    if pressure:
        state["Pressure"] = pressure
    else:
        state.pop("Pressure", None)

    return adjustments
