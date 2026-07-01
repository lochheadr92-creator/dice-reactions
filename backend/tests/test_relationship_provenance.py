"""
Relationship provenance remediation (Phase 1) — deterministic unit tests.

Covers: structured-event updates, rejection of narrative/prose-driven updates,
replay determinism, legacy compatibility, malformed-event rejection, no duplicate
application, event ordering stability, provenance traceability, and dev-only
leakage containment.

Pure-Python (imports ``relationships`` + ``relationship_provenance``); no server,
no MongoDB, no LLM.
"""

import copy
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import relationships as rc  # noqa: E402
import relationship_provenance as rp  # noqa: E402

_VECTOR_KEYS = {"name", "trust", "loyalty", "fear", "resentment", "last_turn", "bond", "state"}


class _P:
    """Minimal parsed-turn stand-in carrying generated prose."""

    def __init__(self, narrative=""):
        self.narrative = narrative
        self.paragraphs = [narrative] if narrative else []


def _vec(merged, name):
    for v in merged.get("relationship_vectors", []):
        if v["name"].lower() == name.lower():
            return v
    return None


def _prior(name="Garrett", **vals):
    base = {"name": name, "trust": 0, "loyalty": 0, "fear": 0, "resentment": 0,
            "last_turn": 1, "bond": "neutral"}
    base.update(vals)
    return {"relationship_vectors": [base]}


def _event(target="Garrett", kind="help", deltas=None, event_id="e1", source_kind="engine_event"):
    return {
        "event_id": event_id,
        "kind": kind,
        "target_name": target,
        "source_kind": source_kind,
        "deltas": deltas if deltas is not None else {"trust": 10, "loyalty": 5},
        "reason": f"test {kind}",
    }


# --------------------------------------------------------------------------- #
# 1. Structured-event updates
# --------------------------------------------------------------------------- #
def test_structured_event_mutates_vector_and_records_provenance():
    prior = _prior(trust=40, loyalty=80)
    merged = {"npcs": [{"name": "Garrett"}]}
    ev = _event(kind="betrayal",
                deltas={"trust": -60, "loyalty": -50, "fear": 20, "resentment": 70})
    sink = []
    rp.apply_relationship_events(prior, merged, [ev], current_turn=3, provenance_sink=sink)
    v = _vec(merged, "Garrett")
    assert v["trust"] == -20 and v["loyalty"] == 30 and v["fear"] == 20 and v["resentment"] == 70
    assert v["state"] == "betrayal_risk"
    assert len(sink) == 1
    rec = sink[0]
    assert rec["applied_deltas"]["trust"] == -60 and rec["applied_deltas"]["resentment"] == 70


def test_new_npc_created_from_structured_event():
    merged = {"npcs": []}
    rp.apply_relationship_events(None, merged, [_event(target="Mira", kind="help")], current_turn=1)
    assert _vec(merged, "Mira") is not None


def test_deceased_excluded_even_with_event():
    merged = {"npcs": [{"name": "Garrett"}], "deceased": ["Garrett"]}
    rp.apply_relationship_events(None, merged, [_event(kind="help")], current_turn=2)
    assert _vec(merged, "Garrett") is None


# --------------------------------------------------------------------------- #
# 2. Generated prose can NEVER mutate relationship state
# --------------------------------------------------------------------------- #
def test_narrative_prose_cannot_mutate_vectors():
    prior = _prior(trust=30, loyalty=40)
    merged = {"npcs": [{"name": "Garrett"}]}
    # Prose narrates a betrayal + attack; the player merely "wait"s.
    rc.update_relationship_calculus(
        _P("You betray Garrett and attack him without mercy."),
        prior, merged, "wait", 2,
    )
    v = _vec(merged, "Garrett")
    # No betrayal/attack applied — resentment stays 0; trust only decays (still > 0).
    assert v["resentment"] == 0 and v["fear"] == 0
    assert 0 < v["trust"] <= 30


def test_player_action_still_resolves_events():
    merged = {"npcs": [{"name": "Garrett"}]}
    rc.update_relationship_calculus(_P("irrelevant prose"), None, merged, "help Garrett", 2)
    v = _vec(merged, "Garrett")
    assert v["trust"] == rc.EVENT_DELTAS["help"]["trust"]
    assert v["loyalty"] == rc.EVENT_DELTAS["help"]["loyalty"]


# --------------------------------------------------------------------------- #
# 3 & 4. Replay determinism
# --------------------------------------------------------------------------- #
def test_replay_is_byte_identical():
    prior = _prior(trust=10, loyalty=20, fear=15, resentment=5)
    events = [
        _event(kind="threaten", deltas={"fear": 25, "trust": -10}, event_id="a"),
        _event(kind="help", deltas={"trust": 12, "loyalty": 8}, event_id="b"),
    ]
    results, sinks = [], []
    for _ in range(3):
        m = {"npcs": [{"name": "Garrett"}]}
        s = []
        rp.apply_relationship_events(copy.deepcopy(prior), m, copy.deepcopy(events),
                                     current_turn=4, provenance_sink=s)
        results.append(m["relationship_vectors"])
        sinks.append(s)
    assert results[0] == results[1] == results[2]
    assert sinks[0] == sinks[1] == sinks[2]


def test_repeated_player_action_replay_identical():
    outs = []
    for _ in range(3):
        merged = {"npcs": [{"name": "Garrett"}]}
        rc.update_relationship_calculus(_P(""), _prior(trust=5), merged, "betray Garrett", 7)
        outs.append(merged["relationship_vectors"])
    assert outs[0] == outs[1] == outs[2]


# --------------------------------------------------------------------------- #
# 5. Legacy compatibility
# --------------------------------------------------------------------------- #
def test_legacy_calculus_signature_and_behaviour():
    # Old positional call still works and still decays engine-owned vectors,
    # ignoring an LLM-injected bogus vector.
    prior = _prior(trust=20)
    merged = {"npcs": [{"name": "Garrett"}],
              "relationship_vectors": [{"name": "Garrett", "trust": 999}]}
    adj = rc.update_relationship_calculus(_P("Silence."), prior, merged, "wait", 2)
    assert _vec(merged, "Garrett")["trust"] <= 20
    assert isinstance(adj, list)


def test_living_cast_effect_provenance_normalises():
    merged = {"npcs": [{"name": "Mira"}], "relationship_vectors": []}
    effects = [{
        "effect_type": "relationship_delta",
        "effect_id": "lc-1",
        "target_name": "Mira",
        "delta": {"trust": 15, "loyalty": 10},
    }]
    rc.apply_living_cast_relationship_effects(merged, effects, turn_number=3)
    records = rp.living_cast_effect_provenance(effects, 3)
    assert len(records) == 1
    r = records[0]
    assert r["source_kind"] == "living_cast_effect" and r["event_id"] == "lc-1"
    assert r["applied_deltas"]["trust"] == 15


# --------------------------------------------------------------------------- #
# 6. Malformed event rejection
# --------------------------------------------------------------------------- #
def test_malformed_events_rejected_valid_still_applies():
    merged = {"npcs": [{"name": "Garrett"}]}
    events = [
        "not-a-dict",
        {"kind": "help", "deltas": {"trust": 5}},                       # missing target
        {"target_name": "Garrett", "deltas": {"trust": 5}},             # missing kind
        {"target_name": "Garrett", "kind": "x"},                        # missing deltas
        {"target_name": "Garrett", "kind": "x", "deltas": {"trust": "NaN"}},  # bad delta
        {"target_name": "Garrett", "kind": "x", "deltas": {"mood": 5}},       # no valid dims
        _event(kind="help", deltas={"trust": 5}, event_id="ok"),        # valid
    ]
    sink = []
    rp.apply_relationship_events(None, merged, events, current_turn=1, provenance_sink=sink)
    v = _vec(merged, "Garrett")
    assert v["trust"] == 5  # only the one valid event applied
    applied = [r for r in sink if not r.get("rejected")]
    rejected = [r for r in sink if r.get("rejected")]
    assert len(applied) == 1 and len(rejected) == 6


# --------------------------------------------------------------------------- #
# 7. No duplicate application
# --------------------------------------------------------------------------- #
def test_duplicate_event_id_applied_once():
    merged = {"npcs": [{"name": "Garrett"}]}
    ev = _event(kind="help", deltas={"trust": 10}, event_id="dup")
    sink = []
    rp.apply_relationship_events(None, merged, [ev, dict(ev)], current_turn=1, provenance_sink=sink)
    assert _vec(merged, "Garrett")["trust"] == 10
    assert len([r for r in sink if not r.get("rejected")]) == 1


# --------------------------------------------------------------------------- #
# 8. Event ordering stability
# --------------------------------------------------------------------------- #
def test_input_order_does_not_change_result():
    e1 = _event(kind="help", deltas={"trust": 12, "loyalty": 8}, event_id="a")
    e2 = _event(kind="threaten", deltas={"fear": 25, "trust": -10}, event_id="b")

    m1 = {"npcs": [{"name": "Garrett"}]}
    rp.apply_relationship_events(None, m1, [e1, e2], current_turn=1)
    m2 = {"npcs": [{"name": "Garrett"}]}
    rp.apply_relationship_events(None, m2, [e2, e1], current_turn=1)
    assert m1["relationship_vectors"] == m2["relationship_vectors"]


# --------------------------------------------------------------------------- #
# Traceability + leakage containment
# --------------------------------------------------------------------------- #
def test_provenance_exposes_full_traceability():
    merged = {"npcs": [{"name": "Garrett"}]}
    sink = []
    rp.apply_relationship_events(None, merged, [_event(kind="help", deltas={"trust": 12})],
                                 current_turn=9, provenance_sink=sink)
    rec = next(r for r in sink if not r.get("rejected"))
    for field in rp.PROVENANCE_FIELDS:
        assert field in rec, f"missing provenance field: {field}"
    assert rec["turn"] == 9 and rec["target_name"] == "Garrett" and rec["kind"] == "help"


def test_provenance_never_enters_vectors_or_prompt_block():
    merged = {"npcs": [{"name": "Garrett"}]}
    sink = []
    rp.apply_relationship_events(_prior(trust=40, loyalty=80), merged,
                                 [_event(kind="betrayal",
                                         deltas={"trust": -60, "loyalty": -50, "resentment": 70})],
                                 current_turn=3, provenance_sink=sink)
    # Vectors carry no provenance keys.
    for v in merged["relationship_vectors"]:
        assert set(v.keys()) <= _VECTOR_KEYS
    # The prompt block leaks no provenance vocabulary.
    block = rc.build_relationship_block(merged)
    for token in ("event_id", "provenance", "reason", "applied_deltas", "source_kind"):
        assert token not in block


def test_provenance_sink_optional_no_crash_without_it():
    merged = {"npcs": [{"name": "Garrett"}]}
    # No provenance_sink passed — must still mutate and not raise.
    rc.update_relationship_calculus(_P(""), None, merged, "help Garrett", 1)
    assert _vec(merged, "Garrett")["trust"] == rc.EVENT_DELTAS["help"]["trust"]
