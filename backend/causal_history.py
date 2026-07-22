"""
Player-safe causal history projection — the "Why this happened" view.

Builds a human-readable causal chain from persisted engine state ONLY:
guard receipts (`debug.state_guard_adjustments` rel tokens), transition
receipts, the consequence-echo scheduled/fired logs, committed NPC-move
evidence, and per-turn relationship vectors. Narrative prose and provider
output are never consulted, so every line in this view is provable from
engine state.

Output rules (contest/player safety):
- plain sentences only — no internal identifiers (npc-*, evt-*, receipt ids),
  no engine field names, no replayability/clock/lifecycle terminology,
  no dice values, no probabilities, no secret content.
- event kinds are neutral display words: opening / action / change / cast /
  seed / return.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional

# Player-facing labels for the structured relationship events the engine
# resolves from the player's DECLARED action (relationships._EVENT_VERBS).
_REL_EVENT_PHRASES: Dict[str, str] = {
    "gift": "Your generosity was recorded — trust grew.",
    "help": "Your help was recorded — trust and loyalty grew.",
    "save_life": "You saved their life — a deep debt of trust was recorded.",
    "reward": "The reward was recorded — loyalty grew.",
    "keep_promise": "You kept your word — trust grew.",
    "apology": "Your apology eased old resentment.",
    "threaten": "The threat left a mark — fear and resentment rose.",
    "attack": "The attack was recorded — fear and resentment surged.",
    "humiliate": "The humiliation festered — resentment rose.",
    "break_promise": "The broken promise was recorded — trust fell.",
    "lie": "The deception was recorded — trust fell.",
    "betrayal": "The betrayal was recorded — trust collapsed, resentment surged.",
}

# Friendly phrasing for engine relationship threshold/state words.
_REL_STATE_PHRASES: Dict[str, str] = {
    "trusting": "{name} now trusts you.",
    "devoted": "{name} is now devoted to you.",
    "wary": "{name} is now wary of you.",
    "resentful": "{name} now resents you.",
    "cowed": "{name} is now cowed by you.",
    "betrayal_risk": "{name} may now turn on you.",
    "collapsed": "{name} will no longer stand with you.",
}

# Committed autonomous move kinds -> plain verb phrases.
_MOVE_PHRASES: Dict[str, str] = {
    "gather": "moved to secure scarce supplies",
    "protect": "moved to shield someone",
    "investigate": "started digging for the truth",
    "negotiate": "opened a negotiation",
    "pressure": "applied pressure on a rival",
    "conceal": "hid something away",
    "fortify": "fortified their position",
    "withdraw": "pulled back to safety",
    "defect": "turned against their own side",
}

# Fired consequence kinds -> sentence templates ({label} is a cleaned label).
_CONSEQUENCE_PHRASES: Dict[str, str] = {
    "relationship_fracture": "A bond you broke earlier came due: {label}.",
    "alliance_shift": "Word set moving earlier has spread: {label}.",
    "pressure_escalation": "Pressure that had been building finally broke: {label}.",
    "delayed_consequence": "An earlier deed caught up with you: {label}.",
    "resource_loss": "Something spent or destroyed earlier is now missed: {label}.",
    "retaliation": "Earlier pressure is being repaid: {label}.",
    "obligation_returns": "An old obligation resurfaced: {label}.",
    "faction_shift_echo": "Loyalties shifted after an earlier turn of coat: {label}.",
    "defence_cost": "Earlier fortifying now demands its price: {label}.",
    "absence_consequence": "A withdrawal earlier left a gap that mattered: {label}.",
    "hidden_cost": "Something hidden earlier has a cost: {label}.",
    "debt_or_loyalty_echo": "Protection given earlier is remembered: {label}.",
}
_CONSEQUENCE_DEFAULT = "An earlier event returned: {label}."

_REL_TOKEN_RE = re.compile(r"^rel:(?P<name>[^:]+):(?P<kinds>[a-z_+]+)$")

_OUTCOME_STATE_KEYS = (
    "Health",
    "Stress",
    "Fatigue",
    "Position",
    "Inventory Summary",
    "Conditions",
    "Notable Conditions",
    "Danger",
    "Momentum",
    "Pressure",
)
_OUTCOME_LABELS = {"Inventory Summary": "Supplies", "Notable Conditions": "Conditions"}
_OUTCOME_BLOCKED_TERMS = (
    "rolling_state",
    "debug",
    "secret",
    "latent",
    "delayed trigger",
    "active systems",
    "engine",
)


def _clean(text: Any) -> str:
    """Humanize an engine label: no underscores, collapsed whitespace."""
    return re.sub(r"\s+", " ", str(text or "").replace("_", " ")).strip()


def _agenda_names(session: Mapping[str, Any]) -> Dict[str, str]:
    rb = session.get("replayability_state") or {}
    agendas = (rb.get("npc_agendas") or {}) if isinstance(rb, Mapping) else {}
    names: Dict[str, str] = {}
    for row in agendas.get("active") or []:
        if isinstance(row, Mapping) and row.get("npc_id") and row.get("display_name"):
            names[str(row["npc_id"])] = str(row["display_name"])
    return names


def _receipts_by_turn(session: Mapping[str, Any]) -> Dict[int, List[Dict[str, Any]]]:
    rb = session.get("replayability_state") or {}
    out: Dict[int, List[Dict[str, Any]]] = {}
    for r in (rb.get("transition_receipts") or []) if isinstance(rb, Mapping) else []:
        if isinstance(r, Mapping) and isinstance(r.get("turn"), int):
            out.setdefault(int(r["turn"]), []).append(dict(r))
    return out


def _fired_echoes_by_turn(session: Mapping[str, Any]) -> Dict[int, List[Dict[str, Any]]]:
    rb = session.get("replayability_state") or {}
    echoes = (rb.get("consequence_echoes") or {}) if isinstance(rb, Mapping) else {}
    out: Dict[int, List[Dict[str, Any]]] = {}
    for e in echoes.get("fired") or []:
        if isinstance(e, Mapping) and isinstance(e.get("fired_turn"), int):
            out.setdefault(int(e["fired_turn"]), []).append(dict(e))
    return out


def _scheduled_turn_index(session: Mapping[str, Any]) -> Dict[str, int]:
    """source id -> turn the consequence was set in motion (from receipts)."""
    index: Dict[str, int] = {}
    for turn, receipts in _receipts_by_turn(session).items():
        for r in receipts:
            if r.get("receipt_type") == "echo_scheduled" and r.get("source_event_id"):
                index.setdefault(str(r["source_event_id"]), turn)
    return index


def _relationship_states(turn_doc: Mapping[str, Any]) -> Dict[str, str]:
    rolling = turn_doc.get("rolling_state") or {}
    states: Dict[str, str] = {}
    for vec in rolling.get("relationship_vectors") or []:
        if isinstance(vec, Mapping) and vec.get("name"):
            states[str(vec["name"])] = str(vec.get("state") or "neutral")
    return states


def _rel_events_from_guards(turn_doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Parse engine guard receipts like ``rel:Greg Stahl:threaten``/``help+gift``."""
    raw = str((turn_doc.get("debug") or {}).get("state_guard_adjustments") or "")
    events: List[Dict[str, Any]] = []
    for token in (t.strip() for t in raw.split(";")):
        m = _REL_TOKEN_RE.match(token)
        if not m:
            continue
        for kind in m.group("kinds").split("+"):
            if kind in _REL_EVENT_PHRASES:
                events.append({"name": m.group("name").strip(), "kind": kind})
    return events


def _npc_move_entry(
    turn_doc: Mapping[str, Any],
    receipts: List[Dict[str, Any]],
    names: Mapping[str, str],
) -> Optional[str]:
    """Committed autonomous NPC move -> sentence (gated on the commit receipt)."""
    if not any(r.get("receipt_type") == "npc_move_committed" for r in receipts):
        return None
    dbg = turn_doc.get("debug") or {}
    if not dbg.get("replayability_utility_ai_committed_move_receipt_id"):
        # Receipt exists but this turn's evidence keys are absent — stay generic.
        return "One of the cast acted on their own."
    actor_id = str(dbg.get("replayability_utility_ai_heuristic_winner_actor") or "")
    if str(dbg.get("replayability_utility_ai_selected_live_winner_source") or "") == "utility":
        actor_id = str(dbg.get("replayability_utility_ai_utility_winner_actor") or actor_id)
        move = str(dbg.get("replayability_utility_ai_utility_winner_move") or "")
    else:
        move = str(dbg.get("replayability_utility_ai_heuristic_winner_move") or "")
    who = names.get(actor_id) or "One of the cast"
    phrase = _MOVE_PHRASES.get(move, "made a move of their own")
    return f"{who} acted on their own — no prompt, no player input: they {phrase}."


def build_causal_history(
    session: Mapping[str, Any],
    turns: List[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Project engine state into a per-turn, player-safe causal chain.

    Returns [{"turn": n, "events": [{"kind": <display word>, "text": str}]}].
    Kinds: opening | action | change | cast | seed | return.
    """
    names = _agenda_names(session)
    receipts_by_turn = _receipts_by_turn(session)
    fired_by_turn = _fired_echoes_by_turn(session)
    scheduled_index = _scheduled_turn_index(session)

    ordered = sorted(
        (t for t in turns if isinstance(t, Mapping) and isinstance(t.get("turn_number"), int)),
        key=lambda t: int(t["turn_number"]),
    )

    history: List[Dict[str, Any]] = []
    prev_states: Dict[str, str] = {}
    for doc in ordered:
        turn_no = int(doc["turn_number"])
        events: List[Dict[str, Any]] = []
        turn_receipts = receipts_by_turn.get(turn_no, [])

        if turn_no <= 1:
            title = _clean(session.get("title") or "A new world")
            events.append({"kind": "opening", "text": f"The world opened: {title}."})
        else:
            action = str(doc.get("player_action") or "").strip()
            if action:
                events.append({"kind": "action", "text": f"You: {action}"})

        # Persistent relationship changes recorded by the engine from the
        # player's declared action (never from prose).
        current_states = _relationship_states(doc)
        for ev in _rel_events_from_guards(doc):
            events.append(
                {
                    "kind": "change",
                    "text": f"{ev['name']}: {_REL_EVENT_PHRASES[ev['kind']]}",
                }
            )
        for name, state in current_states.items():
            before = prev_states.get(name, "neutral")
            if state != before and state in _REL_STATE_PHRASES:
                events.append(
                    {"kind": "change", "text": _REL_STATE_PHRASES[state].format(name=name)}
                )
        if current_states:
            prev_states.update(current_states)

        # Autonomous NPC move (gated on the committed-move receipt).
        move_text = _npc_move_entry(doc, turn_receipts, names)
        if move_text:
            events.append({"kind": "cast", "text": move_text})

        # Consequences set in motion this turn (no spoiler detail).
        seeded = sum(1 for r in turn_receipts if r.get("receipt_type") == "echo_scheduled")
        for _ in range(seeded):
            events.append(
                {
                    "kind": "seed",
                    "text": "A consequence was quietly set in motion. It will return.",
                }
            )

        # Consequences arriving this turn, traced to the turn that caused them.
        for echo in fired_by_turn.get(turn_no, []):
            kind = str(echo.get("kind") or "")
            label = _clean(echo.get("label") or "an earlier event")
            if kind == "relationship_fracture" and "—" in label:
                label = label.split("—", 1)[0].strip()  # name only; no state word
            template = _CONSEQUENCE_PHRASES.get(kind, _CONSEQUENCE_DEFAULT)
            sentence = template.format(label=label)
            src = str(echo.get("source_event_id") or "")
            origin = scheduled_index.get(src)
            if origin:
                sentence = f"Set in motion on turn {origin}, it arrives now. {sentence}"
            events.append({"kind": "return", "text": sentence})

        if events:
            history.append({"turn": turn_no, "events": events})

    return history


def _safe_outcome_state(turn: Mapping[str, Any]) -> Dict[str, str]:
    """Allowlist small, qualitative state values for the latest-outcome card."""
    raw_state = turn.get("state") or {}
    if not isinstance(raw_state, Mapping):
        return {}
    safe: Dict[str, str] = {}
    for key in _OUTCOME_STATE_KEYS:
        value = raw_state.get(key)
        if value is None or isinstance(value, (Mapping, list, tuple, set)):
            continue
        text = _clean(value)[:120]
        lowered = text.lower()
        if not text or any(term in lowered for term in _OUTCOME_BLOCKED_TERMS):
            continue
        safe[key] = text
    return safe


def build_latest_outcome(
    session: Mapping[str, Any],
    turns: List[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Return a bounded, player-safe projection of the latest committed turn."""
    ordered = sorted(
        (t for t in turns if isinstance(t, Mapping) and isinstance(t.get("turn_number"), int)),
        key=lambda t: int(t["turn_number"]),
    )
    if not ordered:
        return None

    history = build_causal_history(session, ordered)
    latest = ordered[-1]
    turn_number = int(latest["turn_number"])
    history_row = next((row for row in history if row.get("turn") == turn_number), None)
    events: List[Dict[str, str]] = []
    for event in list((history_row or {}).get("events") or [])[:4]:
        if not isinstance(event, Mapping):
            continue
        kind = _clean(event.get("kind"))
        text = _clean(event.get("text"))[:240]
        if kind and text:
            events.append({"kind": kind, "text": text})

    before = _safe_outcome_state(ordered[-2]) if len(ordered) > 1 else {}
    after = _safe_outcome_state(latest)
    changes: List[Dict[str, str]] = []
    for key in _OUTCOME_STATE_KEYS:
        old = before.get(key)
        new = after.get(key)
        if not new or new == old:
            continue
        row: Dict[str, str] = {
            "label": _OUTCOME_LABELS.get(key, key),
            "after": new,
        }
        if old:
            row["before"] = old
        changes.append(row)
        if len(changes) >= 6:
            break

    if not events and not changes:
        return None
    return {"turn": turn_number, "events": events, "changes": changes}
