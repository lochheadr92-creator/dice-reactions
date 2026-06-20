"""
Arc Diversity Governor v1 — engine beat history and primary emphasis selection.

Tracks engine-selected beat categories only. Never parses model prose.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Optional, Tuple

ARC_VERSION = 1
MAX_RECENT_BEATS = 12
RECENCY_PENALTY = 14
REPEAT_PENALTY = 10
CRITICAL_URGENCY = 80

BEAT_KINDS = (
    "opening",
    "pressure",
    "echo",
    "npc_move",
    "relationship",
    "faction",
    "resource_loss",
    "location",
)


def init_arc_diversity() -> Dict[str, Any]:
    return {
        "version": ARC_VERSION,
        "recent_beats": [],
        "last_primary_kind": None,
        "repeat_count": 0,
    }


def record_beat(
    state: Dict[str, Any],
    *,
    turn_number: int,
    kind: str,
    subkind: str,
    urgency: int = 50,
) -> None:
    beats = state.setdefault("recent_beats", [])
    beats.append(
        {
            "turn": turn_number,
            "kind": kind,
            "subkind": (subkind or kind)[:40],
            "urgency": max(0, min(100, int(urgency))),
        }
    )
    if len(beats) > MAX_RECENT_BEATS:
        state["recent_beats"] = beats[-MAX_RECENT_BEATS:]
    if state.get("last_primary_kind") == kind:
        state["repeat_count"] = int(state.get("repeat_count") or 0) + 1
    else:
        state["last_primary_kind"] = kind
        state["repeat_count"] = 1


def _repeat_penalty(state: Mapping[str, Any], kind: str, subkind: str, urgency: int) -> int:
    if urgency >= CRITICAL_URGENCY:
        return 0
    penalty = 0
    if state.get("last_primary_kind") == kind:
        penalty += REPEAT_PENALTY * int(state.get("repeat_count") or 0)
    recent = state.get("recent_beats") or []
    for beat in recent[-4:]:
        if isinstance(beat, dict) and beat.get("kind") == kind and beat.get("subkind") == subkind:
            penalty += RECENCY_PENALTY
    return penalty


def select_primary_beat(
    candidates: List[Mapping[str, Any]],
    arc_state: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Choose which engine development receives primary narrative emphasis.

    All candidates remain committed in state — this only affects directive emphasis.
    """
    if not candidates:
        return None
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        urgency = int(cand.get("urgency") or 50)
        score = urgency
        kind = str(cand.get("kind") or "")
        subkind = str(cand.get("subkind") or kind)
        score -= _repeat_penalty(arc_state, kind, subkind, urgency)
        if identity.get("echo_bias") == "betrayals" and kind == "npc_move" and subkind == "defect":
            score += 6
        if identity.get("primary_pressure_kind") == "social" and kind == "npc_move":
            score += 4
        scored.append((score, dict(cand)))
    scored.sort(key=lambda row: (-row[0], row[1].get("kind", ""), row[1].get("subkind", "")))
    return scored[0][1] if scored else None


def build_world_development_directive(
    primary: Optional[Mapping[str, Any]],
    supporting: Optional[Mapping[str, str]] = None,
) -> str:
    """One compact directive for primary + essential supporting beats."""
    if not primary:
        parts = []
        if supporting:
            for body in supporting.values():
                if body:
                    parts.append(body.strip())
        return "\n\n".join(parts)

    lines = [
        "INTERNAL — primary world development (engine emphasis; state is authoritative):",
        f"- Primary beat: {primary.get('kind')} / {primary.get('subkind')}",
    ]
    directive = str(primary.get("directive") or "").strip()
    if directive:
        lines.append(directive)
    if supporting:
        for key, body in supporting.items():
            if key != primary.get("kind") and body and str(body).strip():
                lines.append(f"- Supporting ({key}): surface briefly if natural.")
    return "\n".join(lines)


def copy_arc_state(state: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    return copy.deepcopy(state) if isinstance(state, dict) else init_arc_diversity()