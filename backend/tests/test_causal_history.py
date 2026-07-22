"""
Causal-history ("Why this happened") projection tests — contest showcase proof.

Deterministic, provider-free. Proves the player-safe history view:
  1. surfaces an autonomous NPC move (from the commit receipt + evidence keys),
  2. surfaces persistent player-caused relationship changes (from guard receipts),
  3. surfaces a consequence seeded on one turn and returning on a later turn,
     traced back to the turn that caused it,
  4. surfaces a later NPC state consistent with the earlier event,
  5. NEVER exposes internal identifiers, engine field names, replayability /
     clock / lifecycle terminology, dice values, or probabilities.
"""
from __future__ import annotations

import json

from causal_history import build_causal_history, build_latest_outcome

MARLENE_ID = "npc-aaaaaaaaaaaa"
GREG_ID = "npc-bbbbbbbbbbbb"


def _demo_session() -> dict:
    return {
        "id": "sess-1",
        "title": "Suburban Collapse",
        "replayability_state": {
            "npc_agendas": {
                "active": [
                    {"npc_id": MARLENE_ID, "display_name": "Marlene Cho", "goal_kind": "secure_resources"},
                    {"npc_id": GREG_ID, "display_name": "Greg Stahl", "goal_kind": "restore_loss"},
                ]
            },
            "transition_receipts": [
                {"source_event_id": "npc-move-111", "receipt_type": "npc_move_committed", "turn": 2},
                {"source_event_id": "evt-rel-greg stahl-turn-4", "receipt_type": "echo_scheduled", "turn": 4},
                {"source_event_id": "evt-rel-greg stahl-turn-4", "receipt_type": "echo_fired", "turn": 6},
            ],
            "consequence_echoes": {
                "scheduled": [],
                "fired": [
                    {
                        "id": "echo-222",
                        "kind": "relationship_fracture",
                        "label": "Greg Stahl — collapsed",
                        "source_event_id": "evt-rel-greg stahl-turn-4",
                        "fired_turn": 6,
                    }
                ],
            },
        },
    }


def _turn(n: int, action: str = "", guards: str = "", vectors=None, dbg_extra=None, state=None) -> dict:
    debug = {"state_guard_adjustments": guards} if guards else {}
    debug.update(dbg_extra or {})
    return {
        "turn_number": n,
        "player_action": action,
        "debug": debug,
        "rolling_state": {"relationship_vectors": vectors or []},
        "state": state or {},
    }


def _demo_turns() -> list:
    return [
        _turn(1),
        _turn(
            2,
            action="I share my bottled water with Marlene Cho and help her carry supplies inside.",
            guards="rumour_seeded; rel:Marlene Cho:help+gift; rolling_active_pressures_engine_derived",
            vectors=[
                {"name": "Marlene Cho", "state": "neutral"},
                {"name": "Greg Stahl", "state": "neutral"},
            ],
            dbg_extra={
                "replayability_utility_ai_committed_move_receipt_id": "npc-move-111",
                "replayability_utility_ai_heuristic_winner_actor": MARLENE_ID,
                "replayability_utility_ai_heuristic_winner_move": "gather",
                "replayability_utility_ai_selected_live_winner_source": "heuristic",
            },
        ),
        _turn(
            3,
            action="I threaten Greg Stahl with the claw bar and tell him to stay off my property.",
            guards="rel:Greg Stahl:threaten",
            vectors=[
                {"name": "Marlene Cho", "state": "neutral"},
                {"name": "Greg Stahl", "state": "neutral"},
            ],
        ),
        _turn(
            4,
            action="I betray Greg Stahl to the scavengers at the fence.",
            guards="rel:Greg Stahl:betrayal",
            vectors=[
                {"name": "Marlene Cho", "state": "neutral"},
                {"name": "Greg Stahl", "state": "collapsed"},
            ],
        ),
        _turn(5, action="I wait by the front window and watch the street."),
        _turn(6, action="I look out at the street once more and listen."),
    ]


def _flat_texts(history) -> str:
    return "\n".join(ev["text"] for row in history for ev in row["events"])


def test_autonomous_npc_move_is_surfaced_with_display_name():
    history = build_causal_history(_demo_session(), _demo_turns())
    t2 = next(r for r in history if r["turn"] == 2)
    cast = [e for e in t2["events"] if e["kind"] == "cast"]
    assert len(cast) == 1
    assert "Marlene Cho" in cast[0]["text"]
    assert "acted on their own" in cast[0]["text"]
    assert "supplies" in cast[0]["text"]  # gather -> secure scarce supplies


def test_persistent_player_caused_changes_are_surfaced():
    history = build_causal_history(_demo_session(), _demo_turns())
    t2 = next(r for r in history if r["turn"] == 2)
    changes2 = [e["text"] for e in t2["events"] if e["kind"] == "change"]
    assert any("Marlene Cho" in c and "trust" in c.lower() for c in changes2)
    t3 = next(r for r in history if r["turn"] == 3)
    changes3 = [e["text"] for e in t3["events"] if e["kind"] == "change"]
    assert any("Greg Stahl" in c and "fear" in c.lower() for c in changes3)


def test_later_npc_state_reflects_earlier_event():
    history = build_causal_history(_demo_session(), _demo_turns())
    t4 = next(r for r in history if r["turn"] == 4)
    changes = [e["text"] for e in t4["events"] if e["kind"] == "change"]
    assert any("betrayal" in c.lower() for c in changes)
    # Threshold crossing surfaced as a plain sentence, not an engine state word.
    assert any("Greg Stahl will no longer stand with you." == c for c in changes)


def test_consequence_seeded_then_returns_with_origin_turn():
    history = build_causal_history(_demo_session(), _demo_turns())
    t4 = next(r for r in history if r["turn"] == 4)
    assert any(e["kind"] == "seed" for e in t4["events"])
    t6 = next(r for r in history if r["turn"] == 6)
    returns = [e["text"] for e in t6["events"] if e["kind"] == "return"]
    assert len(returns) == 1
    assert "Set in motion on turn 4" in returns[0]
    assert "Greg Stahl" in returns[0]
    assert "came due" in returns[0]


def test_history_never_exposes_internal_fields_or_identifiers():
    history = build_causal_history(_demo_session(), _demo_turns())
    payload = json.dumps(history).lower()
    forbidden = [
        "replayability", "rolling_state", "pressure_graph", "run_seed",
        "event_id", "source_event", "receipt", "npc-", "evt-", "echo-",
        "agenda", "utility_ai", "heuristic", "lifecycle", "simulation_clock",
        "secret", "debug", "state_guard", "d20", "probability", "betrayal_risk",
        "relationship_fracture", "goal_kind", "npc_id", "display_name",
    ]
    for token in forbidden:
        assert token not in payload, f"internal token leaked: {token}"
    # No snake_case engine words anywhere in player-facing text.
    assert "_" not in _flat_texts(history)


def test_empty_and_degenerate_inputs_are_safe():
    assert build_causal_history({}, []) == []
    # Turn docs with no debug/receipts still yield the action line only.
    history = build_causal_history({}, [_turn(2, action="I wait.")])
    assert history == [
        {"turn": 2, "events": [{"kind": "action", "text": "You: I wait."}]}
    ]


def test_latest_outcome_is_bounded_and_qualitative():
    turns = [
        _turn(1, state={"Pressure": "rising", "Health": "stable"}),
        _turn(2, action="I press on.", state={"Pressure": "elevated", "Health": "bruised"}),
    ]
    outcome = build_latest_outcome({}, turns)
    assert outcome == {
        "turn": 2,
        "events": [{"kind": "action", "text": "You: I press on."}],
        "changes": [
            {"label": "Health", "before": "stable", "after": "bruised"},
            {"label": "Pressure", "before": "rising", "after": "elevated"},
        ],
    }


def test_latest_outcome_drops_internal_state_values():
    turns = [
        _turn(1, state={"Pressure": "stable"}),
        _turn(2, state={"Pressure": "stable", "Danger": "secret_registry=true"}),
    ]
    assert build_latest_outcome({}, turns) is None
