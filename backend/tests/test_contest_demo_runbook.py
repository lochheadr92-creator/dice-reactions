"""
Contest demo runbook pinning tests — docs/contest-demo-runbook.md.

Deterministic, provider-free proof that the exact demo script in the runbook
produces the intended ENGINE-owned events, independent of LLM narration:

  1. The `suburban-collapse` scenario exists with the named demo NPCs.
  2. Each scripted player action resolves to the intended structured
     relationship events (relationship calculus reads ONLY the player's
     declared action — never prose).
  3. The three-beat arc (kindness -> threaten -> betrayal) drives Greg Stahl
     across an engine threshold state that qualifies as an echo source.
  4. The scheduled relationship_fracture echo matures and fires inside the
     six-turn demo window (schedule T4 -> fire T6).
  5. Neutral/fallback actions and hypothetical phrasing produce zero events,
     so improvised filler turns cannot corrupt the demo state.

No production code is exercised through the provider; nothing here touches
lifecycle, action-duration, feature flags, or API contracts.
"""
from __future__ import annotations

import copy

import consequence_echoes as echoes
import relationship_provenance as rp
import relationships
import replayability
from scenarios import get_scenario, get_scenarios

MARLENE = "Marlene Cho"
GREG = "Greg Stahl"

# Exact strings published in docs/contest-demo-runbook.md — keep in sync.
T2_KINDNESS = "I share my bottled water with Marlene Cho and help her carry supplies inside."
T3_THREATEN = "I threaten Greg Stahl with the claw bar and tell him to stay off my property."
T4_BETRAYAL = (
    "I betray Greg Stahl to the scavengers at the fence, telling them exactly "
    "where his supplies are hidden."
)
T5_NEUTRAL = "I wait by the front window and watch the street."
T6_NEUTRAL = "I look out at the street once more and listen."
FALLBACK_HYPOTHETICAL = "I think about threatening Greg Stahl but stay where I am."


def _demo_rolling() -> dict:
    """Minimal authoritative rolling_state carrying both demo NPCs."""
    return {
        "scene": "Elm Crescent",
        "npcs": [
            {"name": MARLENE, "stance": "ally", "last_seen": "next door"},
            {"name": GREG, "stance": "neutral, suspicious", "last_seen": "across the street"},
        ],
    }


def _names() -> list:
    return [MARLENE, GREG]


# ---------------------------------------------------------------------------
# 1. Scenario shape
# ---------------------------------------------------------------------------
def test_suburban_collapse_scenario_exists_with_demo_npcs():
    scenario = get_scenario("suburban-collapse")
    assert scenario is not None
    assert scenario["title"] == "Suburban Collapse"
    assert scenario["mode"] == "advanced"
    names = [n["name"] for n in scenario["key_npcs"]]
    assert MARLENE in names
    assert GREG in names
    # Seeded pressure + hidden threat exist for the pressure-graph story.
    assert scenario["starting_pressure"]
    assert scenario["hidden_threat"]


def test_scenario_listed_for_picker_without_seed():
    listed = {s["id"]: s for s in get_scenarios()}
    assert "suburban-collapse" in listed
    assert "seed" not in listed["suburban-collapse"]


# ---------------------------------------------------------------------------
# 2. Scripted actions -> intended structured events (engine-owned resolution)
# ---------------------------------------------------------------------------
def test_t2_kindness_resolves_gift_and_help_for_marlene_only():
    events = rp.resolve_player_action_events(T2_KINDNESS, _names(), 2)
    by_target = {}
    for ev in events:
        by_target.setdefault(ev["target_name"], set()).add(ev["kind"])
    assert by_target.get(MARLENE) == {"gift", "help"}
    assert GREG not in by_target


def test_t3_threaten_resolves_threaten_for_greg_only():
    events = rp.resolve_player_action_events(T3_THREATEN, _names(), 3)
    by_target = {}
    for ev in events:
        by_target.setdefault(ev["target_name"], set()).add(ev["kind"])
    assert by_target.get(GREG) == {"threaten"}
    assert MARLENE not in by_target


def test_t4_betrayal_resolves_betrayal_for_greg_only():
    events = rp.resolve_player_action_events(T4_BETRAYAL, _names(), 4)
    by_target = {}
    for ev in events:
        by_target.setdefault(ev["target_name"], set()).add(ev["kind"])
    assert by_target.get(GREG) == {"betrayal"}
    assert MARLENE not in by_target


def test_neutral_and_hypothetical_actions_resolve_no_events():
    for action in (T5_NEUTRAL, T6_NEUTRAL, FALLBACK_HYPOTHETICAL):
        assert rp.resolve_player_action_events(action, _names(), 5) == [], action


# ---------------------------------------------------------------------------
# 3. Three-beat arc drives the engine threshold + echo source
# ---------------------------------------------------------------------------
def _run_calculus(prior: dict, action: str, turn: int) -> dict:
    merged = copy.deepcopy(prior)
    relationships.update_relationship_calculus(None, prior, merged, action, turn)
    return merged


def _vector(rolling: dict, name: str) -> dict:
    for vec in rolling.get("relationship_vectors") or []:
        if vec.get("name") == name:
            return vec
    raise AssertionError(f"no vector for {name}")


def test_demo_arc_marlene_warms_and_greg_crosses_threshold():
    t1 = _demo_rolling()
    t2 = _run_calculus(t1, T2_KINDNESS, 2)

    marlene = _vector(t2, MARLENE)
    assert marlene["trust"] > 0 and marlene["loyalty"] > 0

    t3 = _run_calculus(t2, T3_THREATEN, 3)
    greg = _vector(t3, GREG)
    assert greg["fear"] > 0 and greg["resentment"] > 0 and greg["trust"] < 0

    t4 = _run_calculus(t3, T4_BETRAYAL, 4)
    greg = _vector(t4, GREG)
    # Betrayal (Ch 29.8 deltas) must push Greg into an engine threshold state.
    assert greg["state"] in relationships.RELATIONSHIP_THRESHOLD_STATES
    # Marlene remains warm — the betrayal names only Greg.
    marlene = _vector(t4, MARLENE)
    assert marlene["trust"] > 0

    # The threshold crossing is a qualifying engine-owned echo source.
    sources = replayability.collect_qualifying_echo_sources(
        prior_rolling=t3, merged_rolling=t4, turn_number=4
    )
    rel_sources = [s for s in sources if s["source_kind"] == "relationship_threshold_crossed"]
    assert len(rel_sources) == 1
    assert GREG.lower() in rel_sources[0]["source_event_id"]
    assert rel_sources[0]["echo_kind"] == "relationship_fracture"


# ---------------------------------------------------------------------------
# 4. Echo timing fits the six-turn demo window (schedule T4 -> fire T6)
# ---------------------------------------------------------------------------
def test_relationship_echo_schedules_t4_and_fires_by_t6():
    echo_state = echoes.init_consequence_echoes()
    source = {
        "source_kind": "relationship_threshold_crossed",
        "source_event_id": "evt-rel-greg stahl-turn-4",
        "echo_kind": "relationship_fracture",
        "label": f"{GREG} — betrayal risk",
    }
    added = echoes.schedule_from_structured_events(
        echo_state, [source], 4, processed_source_ids=set()
    )
    assert len(added) == 1

    # T5: not yet mature — nothing fires.
    echoes.mature_echoes(echo_state, 5)
    fired, did_fire = echoes.fire_echo(echo_state, 5)
    assert not did_fire and fired is None

    # T6: matured and fires exactly once.
    matured = echoes.mature_echoes(echo_state, 6)
    assert matured
    fired, did_fire = echoes.fire_echo(echo_state, 6)
    assert did_fire and fired is not None
    assert fired["source_event_id"] == "evt-rel-greg stahl-turn-4"

    # Duplicate scheduling from the same source event is refused.
    again = echoes.schedule_from_structured_events(
        echo_state, [source], 6,
        processed_source_ids=echoes.processed_source_event_ids(echo_state),
    )
    assert len(again) == 0
