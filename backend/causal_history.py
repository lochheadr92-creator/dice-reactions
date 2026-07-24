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

# Why-history return phrases — richer, but player-safe (no schedule turns,
# no raw pressure-graph labels, no speculative blame).
_HISTORY_RETURN_PHRASES: Dict[str, str] = {
    "relationship_fracture": "A bond you broke earlier came due.",
    "alliance_shift": "Word set moving earlier has spread.",
    "pressure_escalation": "Pressure that had been building has broken into the present.",
    "delayed_consequence": "An earlier deed caught up with you.",
    "resource_loss": "Something spent or destroyed earlier is now missed.",
    "retaliation": "Earlier pressure is being repaid.",
    "obligation_returns": "An old obligation resurfaced.",
    "faction_shift_echo": "Loyalties shifted after an earlier turn of coat.",
    "defence_cost": "Earlier fortifying now demands its price.",
    "absence_consequence": "A withdrawal earlier left a gap that mattered.",
    "hidden_cost": "Something hidden earlier has a cost.",
    "debt_or_loyalty_echo": "Protection given earlier is remembered.",
}
_HISTORY_RETURN_NAMED: Dict[str, str] = {
    "relationship_fracture": "A bond with {name} came due.",
    "alliance_shift": "Word involving {name} has spread.",
    "retaliation": "Pressure from {name} is being repaid.",
    "debt_or_loyalty_echo": "{name} remembers protection given earlier.",
    "obligation_returns": "An old obligation involving {name} resurfaced.",
}
_HISTORY_RETURN_DEFAULT = "An earlier consequence returned."

# Compact latest-outcome RETURN only — immediate, short, no engine scheduling.
_COMPACT_RETURN_PHRASES: Dict[str, str] = {
    "pressure_escalation": "The situation has escalated.",
    "relationship_fracture": "An earlier action has changed the immediate situation.",
    "alliance_shift": "An earlier action has changed the immediate situation.",
    "delayed_consequence": "A delayed consequence has arrived.",
    "resource_loss": "An earlier action has changed the immediate situation.",
    "retaliation": "Someone nearby reacted.",
    "obligation_returns": "An earlier action has changed the immediate situation.",
    "faction_shift_echo": "An earlier action has changed the immediate situation.",
    "defence_cost": "An earlier action has changed the immediate situation.",
    "absence_consequence": "An earlier action has changed the immediate situation.",
    "hidden_cost": "An earlier action has changed the immediate situation.",
    "debt_or_loyalty_echo": "Someone nearby reacted.",
}
_COMPACT_RETURN_DEFAULT = "An earlier action has changed the immediate situation."

_REL_TOKEN_RE = re.compile(r"^rel:(?P<name>[^:]+):(?P<kinds>[a-z_+]+)$")
_SPECULATIVE_LABEL_RE = re.compile(
    r"\b(may|might|could|someone|blame|holds? the key|pressure graph|"
    r"delayed trigger|latent|set in motion|scheduled|utility|goal)\b",
    re.IGNORECASE,
)

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
# Priority for the compact STATE SHIFT card (most critical first).
_OUTCOME_CHANGE_PRIORITY = (
    "Health",
    "Conditions",
    "Notable Conditions",
    "Danger",
    "Inventory Summary",
    "Position",
    "Pressure",
    "Stress",
    "Fatigue",
    "Momentum",
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
_MAX_OUTCOME_CHANGES = 4
_SHORT_STATE_LEN = 48
_COMPACT_AFTER_LEN = 72


def _clean(text: Any) -> str:
    """Humanize an engine label: no underscores, collapsed whitespace."""
    return re.sub(r"\s+", " ", str(text or "").replace("_", " ")).strip()


def _display_name_from_label(label: str) -> Optional[str]:
    """Extract a short proper-name fragment; reject speculative engine labels."""
    cleaned = _clean(label)
    if not cleaned or _SPECULATIVE_LABEL_RE.search(cleaned):
        return None
    # Prefer the left side of an em/en dash or colon when the left is a name.
    head = re.split(r"\s*[—–\-|:]\s*", cleaned, maxsplit=1)[0].strip()
    if not head or len(head) > 40:
        return None
    # Reject sentence-like or abstract labels (lowercase starts, multi-clause).
    if head[:1].islower() or " " in head and not head[0].isupper():
        # Allow multi-word proper names: "Greg Stahl", "Marlene Cho"
        parts = head.split()
        if not parts or not all(p[:1].isupper() for p in parts if p):
            return None
    if not re.match(r"^[A-Za-z][A-Za-z0-9' .\-]*$", head):
        return None
    # Abstract single words that are not people/places
    if head.lower() in {
        "authority", "pressure", "scarcity", "danger", "threat", "unknown",
        "resources", "alliance", "faction", "defence", "defense", "absence",
    }:
        return None
    return head


def _history_return_text(kind: str, label: str) -> str:
    """Richer Why-history return line — still player-safe, no turn scheduling."""
    name = _display_name_from_label(label)
    if name and kind in _HISTORY_RETURN_NAMED:
        return _HISTORY_RETURN_NAMED[kind].format(name=name)
    return _HISTORY_RETURN_PHRASES.get(kind, _HISTORY_RETURN_DEFAULT)


def _compact_return_text(kind: str) -> str:
    """Short latest-outcome RETURN only — no labels, turns, or speculation."""
    return _COMPACT_RETURN_PHRASES.get(kind, _COMPACT_RETURN_DEFAULT)


def _split_state_clauses(text: str) -> List[str]:
    cleaned = _clean(text)
    if not cleaned:
        return []
    if ";" in cleaned or "|" in cleaned:
        parts = re.split(r"\s*[;|]\s*", cleaned)
    elif cleaned.count(",") >= 1 and len(cleaned) > _SHORT_STATE_LEN:
        parts = re.split(r"\s*,\s*", cleaned)
    else:
        parts = [cleaned]
    out: List[str] = []
    for part in parts:
        chunk = part.strip().rstrip(".")
        if chunk:
            out.append(chunk)
    return out


def _kv_pairs(clauses: List[str]) -> Dict[str, str]:
    pairs: Dict[str, str] = {}
    for clause in clauses:
        if ":" not in clause:
            continue
        key, value = clause.split(":", 1)
        k = key.strip()
        v = value.strip()
        if k and v:
            pairs[k] = v
    return pairs


_TOPIC_RE = re.compile(
    r"\b(bleeding|gauze|bandage|wound|rifle|canteen|tin|first[- ]?aid|"
    r"cover|hands?|ankle|pressure|supplies?|water|ammo|keys?|radio)\b",
    re.IGNORECASE,
)


def _clause_topic(clause: str) -> Optional[str]:
    match = _TOPIC_RE.search(clause)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1).lower().replace("-", " "))


def _topic_label(topic: str) -> str:
    return " ".join(part.capitalize() for part in topic.split())


def _value_without_topic(clause: str, topic: str) -> str:
    pattern = re.compile(re.escape(topic).replace(r"\ ", r"[\s\-]+"), re.IGNORECASE)
    value = pattern.sub(" ", clause)
    value = re.sub(r"\s+", " ", value).strip(" ,;:-")
    return value or clause


def _freeform_change_rows(
    field_label: str,
    before: str,
    after: str,
) -> List[Dict[str, str]]:
    """Emit one or more compact rows from freeform multi-clause state strings."""
    before_clauses = _split_state_clauses(before)
    after_clauses = _split_state_clauses(after)
    before_norm = {c.lower() for c in before_clauses}
    after_norm = {c.lower() for c in after_clauses}

    before_by_topic: Dict[str, str] = {}
    for clause in before_clauses:
        topic = _clause_topic(clause)
        if topic and topic not in before_by_topic:
            before_by_topic[topic] = clause
    after_by_topic: Dict[str, str] = {}
    for clause in after_clauses:
        topic = _clause_topic(clause)
        if topic and topic not in after_by_topic:
            after_by_topic[topic] = clause

    rows: List[Dict[str, str]] = []
    seen_after: set[str] = set()

    for topic, after_clause in after_by_topic.items():
        before_clause = before_by_topic.get(topic)
        if before_clause and before_clause.lower() == after_clause.lower():
            continue
        if before_clause:
            old_v = _value_without_topic(before_clause, topic)
            new_v = _value_without_topic(after_clause, topic)
            if old_v and new_v and old_v.lower() != new_v.lower():
                rows.append({
                    "label": _topic_label(topic),
                    "before": old_v,
                    "after": new_v,
                })
            else:
                rows.append({
                    "label": _topic_label(topic),
                    "before": before_clause,
                    "after": after_clause,
                })
        else:
            # Novel topical clause — show the new fact, not the whole field.
            rows.append({"label": field_label, "after": after_clause})
        seen_after.add(after_clause.lower())
        if len(rows) >= 2:
            break

    if len(rows) < 2:
        for clause in after_clauses:
            if clause.lower() in before_norm or clause.lower() in seen_after:
                continue
            rows.append({"label": field_label, "after": clause})
            if len(rows) >= 2:
                break

    if rows:
        return rows

    # Fallback single summary for unstructured rewrite.
    novel = [c for c in after_clauses if c.lower() not in before_norm]
    if novel:
        return [{"label": field_label, "after": novel[0][:_COMPACT_AFTER_LEN]}]
    return [{"label": field_label, "after": after[:_COMPACT_AFTER_LEN].rsplit(" ", 1)[0]
             if len(after) > _COMPACT_AFTER_LEN else after}]


def _compact_state_change_rows(
    key: str,
    before: Optional[str],
    after: str,
) -> List[Dict[str, str]]:
    """Build one or more player-facing change rows; never dump full raw walls."""
    label = _OUTCOME_LABELS.get(key, key)
    new = _clean(after)
    old = _clean(before) if before else ""
    if not new or new == old:
        return []

    # Short band-like values: full before → after is readable as one row.
    if (not old or len(old) <= _SHORT_STATE_LEN) and len(new) <= _SHORT_STATE_LEN:
        row: Dict[str, str] = {"label": label, "after": new}
        if old:
            row["before"] = old
        return [row]

    if old:
        # Explicit key: value pairs first.
        before_kv = _kv_pairs(_split_state_clauses(old))
        after_kv = _kv_pairs(_split_state_clauses(new))
        if after_kv or before_kv:
            rows: List[Dict[str, str]] = []
            for item_key, new_v in after_kv.items():
                old_v = before_kv.get(item_key)
                if old_v is None:
                    rows.append({"label": item_key, "after": new_v})
                elif old_v != new_v:
                    rows.append({"label": item_key, "before": old_v, "after": new_v})
                if len(rows) >= 2:
                    break
            if rows:
                return rows
        return _freeform_change_rows(label, old, new)

    short = new
    if len(short) > _COMPACT_AFTER_LEN:
        cut = short[:_COMPACT_AFTER_LEN]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        short = cut.rstrip(" ,;:")
    return [{"label": label, "after": short}]


def _build_outcome_changes(
    before: Mapping[str, str],
    after: Mapping[str, str],
) -> List[Dict[str, str]]:
    changes: List[Dict[str, str]] = []
    seen: set[str] = set()
    for key in _OUTCOME_CHANGE_PRIORITY:
        if key not in _OUTCOME_STATE_KEYS:
            continue
        new = after.get(key)
        if not new:
            continue
        old = before.get(key)
        if new == old:
            continue
        for row in _compact_state_change_rows(key, old, new):
            sig = f"{row.get('label')}|{row.get('before','')}|{row.get('after','')}"
            if sig in seen:
                continue
            seen.add(sig)
            changes.append(row)
            if len(changes) >= _MAX_OUTCOME_CHANGES:
                return changes
    return changes


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

        # Consequences noted this turn (Why view only — no origin-turn spoiler).
        seeded = sum(1 for r in turn_receipts if r.get("receipt_type") == "echo_scheduled")
        for _ in range(seeded):
            events.append(
                {
                    "kind": "seed",
                    "text": "What just happened may still have consequences later.",
                }
            )

        # Consequences arriving this turn — richer Why-history phrasing.
        # Origin turn numbers and speculative engine labels are never included.
        for echo in fired_by_turn.get(turn_no, []):
            kind = str(echo.get("kind") or "")
            label = _clean(echo.get("label") or "")
            events.append({"kind": "return", "text": _history_return_text(kind, label)})

        if events:
            history.append({"turn": turn_no, "events": events})

    return history


def _safe_outcome_state(turn: Mapping[str, Any]) -> Dict[str, str]:
    """Allowlist qualitative state values for compact outcome projection.

    Values may be longer than the final display rows; compaction happens in
    ``_compact_state_change``. Authoritative turn.state is never mutated.
    """
    raw_state = turn.get("state") or {}
    if not isinstance(raw_state, Mapping):
        return {}
    safe: Dict[str, str] = {}
    for key in _OUTCOME_STATE_KEYS:
        value = raw_state.get(key)
        if value is None or isinstance(value, (Mapping, list, tuple, set)):
            continue
        # Keep enough text for clause-level diffs; never dump secrets.
        text = _clean(value)[:280]
        lowered = text.lower()
        if not text or any(term in lowered for term in _OUTCOME_BLOCKED_TERMS):
            continue
        safe[key] = text
    return safe


def build_latest_outcome(
    session: Mapping[str, Any],
    turns: List[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Return a bounded, player-safe projection of the latest committed turn.

    Events and state shifts are presentation-only summaries. Raw turn.state and
    engine receipts remain authoritative and are not modified here.
    """
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

    # Compact card: action / cast / change from history (not seed, not raw return).
    for event in list((history_row or {}).get("events") or []):
        if not isinstance(event, Mapping):
            continue
        kind = _clean(event.get("kind"))
        text = _clean(event.get("text"))[:180]
        if not kind or not text or kind in {"seed", "return"}:
            continue
        events.append({"kind": kind, "text": text})
        if len(events) >= 3:
            break

    # Compact RETURN is projected here from engine echoes — not from history text.
    for echo in _fired_echoes_by_turn(session).get(turn_number, []):
        if not isinstance(echo, Mapping):
            continue
        kind = str(echo.get("kind") or "")
        events.append({"kind": "return", "text": _compact_return_text(kind)})
        if len(events) >= 4:
            break

    before = _safe_outcome_state(ordered[-2]) if len(ordered) > 1 else {}
    after = _safe_outcome_state(latest)
    # Snapshot of raw allowlisted values used only for projection; turn.state unchanged.
    changes = _build_outcome_changes(before, after)

    if not events and not changes:
        return None
    return {"turn": turn_number, "events": events, "changes": changes}
