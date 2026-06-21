"""NPC Agendas v1 — deterministic identity and evolution tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import npc_agendas as agendas  # noqa: E402
import replayability  # noqa: E402

SEED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SEED_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CORPUS = (
    SEED,
    SEED_B,
    "cccccccc-cccc-cccc-cccc-cccccccccccc",
    "11111111-1111-1111-1111-111111111111",
    "22222222-2222-2222-2222-222222222222",
    "33333333-3333-3333-3333-333333333333",
    "44444444-4444-4444-4444-444444444444",
    "55555555-5555-5555-5555-555555555555",
)


def _record(name: str, slot: int = 0, **extra):
    return {"name": name, "source_type": "seed_record", "source_slot": slot, **extra}


def test_same_canonical_npc_id_across_run_seeds():
    npc = _record("Marlene Cho", role="nurse")
    id_a = agendas.derive_canonical_npc_id(npc, source_slot=0)
    id_b = agendas.derive_canonical_npc_id(npc, source_slot=0)
    assert id_a == id_b
    a = agendas.seed_agendas_from_npcs(SEED, [npc])["active"][0]
    b = agendas.seed_agendas_from_npcs(SEED_B, [npc])["active"][0]
    assert a["npc_id"] == b["npc_id"]
    assert a["goal_kind"] != b["goal_kind"] or a["fear_kind"] != b["fear_kind"]


def test_same_seed_and_npc_produces_identical_agenda():
    npcs = [_record("Marlene Cho", role="nurse")]
    a = agendas.seed_agendas_from_npcs(SEED, npcs)
    b = agendas.seed_agendas_from_npcs(SEED, npcs)
    assert a["active"][0] == b["active"][0]


def test_different_seeds_vary_agenda():
    npcs = [_record("Marlene Cho")]
    a = agendas.seed_agendas_from_npcs(CORPUS[0], npcs)["active"][0]
    b = agendas.seed_agendas_from_npcs(CORPUS[1], npcs)["active"][0]
    assert a["npc_id"] == b["npc_id"]
    assert a["goal_kind"] != b["goal_kind"] or a["fear_kind"] != b["fear_kind"]


def test_bounded_schema_and_version():
    state = agendas.seed_agendas_from_npcs(SEED, [_record("Greg")])
    agenda = state["active"][0]
    assert agenda["version"] == 1
    assert agenda["agenda_id"] == agendas.agenda_id(agenda["npc_id"])
    for field in agendas.CLOSED_AGENDA_ENUMS:
        assert agenda[field] in agendas.CLOSED_AGENDA_ENUMS[field]


def test_no_secret_text_in_agenda():
    state, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None,
        custom_world_setup={"secret": "I stole the crown."}, run_seed=SEED,
        npc_seed_records=[_record("Mira")],
    )
    assert "stole" not in str(state["npc_agendas"])


def test_only_grounded_npcs_receive_agendas():
    state = agendas.seed_agendas_from_npcs(SEED, [{"name": ""}, _record("Mira")])
    assert len(state["active"]) == 1


def test_ungrounded_name_only_record_skipped():
    state = agendas.seed_agendas_from_npcs(SEED, [{"name": "Ghost Mention"}])
    assert state["active"] == []


def test_duplicate_npc_id_impossible():
    nid = agendas.canonical_npc_id(
        source_type="seed_record", source_slot=0, name="Mira", role=""
    )
    state = agendas.seed_agendas_from_npcs(
        SEED,
        [
            {"name": "Mira", "npc_id": nid, "source_type": "seed_record", "source_slot": 0},
            {"name": "mira", "npc_id": nid, "source_type": "seed_record", "source_slot": 1},
        ],
    )
    assert len(state["active"]) == 1


def test_different_slots_produce_distinct_ids():
    a = agendas.canonical_npc_id(source_type="scenario", source_slot=0, name="Alex", scenario_id="s1")
    b = agendas.canonical_npc_id(source_type="scenario", source_slot=1, name="Alex", scenario_id="s1")
    assert a != b


def test_case_normalization_does_not_split_identity():
    a = agendas.canonical_npc_id(source_type="seed_record", source_slot=0, name="Mira Cho")
    b = agendas.canonical_npc_id(source_type="seed_record", source_slot=0, name="  mira   cho  ")
    assert a == b


def test_agenda_cap_enforced():
    rows = [_record(f"NPC-{i}", slot=i) for i in range(20)]
    state = agendas.seed_agendas_from_npcs(SEED, rows)
    assert len(state["active"]) <= agendas.MAX_ACTIVE_AGENDAS


def test_structured_event_evolves_progress():
    state = agendas.seed_agendas_from_npcs(SEED, [_record("Mira")])
    agenda = state["active"][0]
    before = agenda["progress"]
    agendas.evolve_agenda_from_structured_event(
        agenda, {"source_kind": "relationship_threshold_crossed"}, 2
    )
    assert agenda["progress"] > before


def test_breaking_point_fires_once():
    state = agendas.seed_agendas_from_npcs(SEED, [_record("Mira")])
    agenda = state["active"][0]
    agenda["progress"] = 84
    agendas.evolve_agenda_from_structured_event(agenda, {"source_kind": "pressure_threshold_crossed"}, 2)
    assert agenda["breaking_fired"]
    agenda["progress"] = 90
    agendas.evolve_agenda_from_structured_event(agenda, {"source_kind": "pressure_threshold_crossed"}, 3)
    assert agenda["status"] == "breaking"


def test_progress_clamps():
    state = agendas.seed_agendas_from_npcs(SEED, [_record("Mira")])
    agenda = state["active"][0]
    agenda["progress"] = 500
    agendas.evolve_agenda_from_structured_event(agenda, {"source_kind": "npc_world_move"}, 2)
    assert agenda["progress"] <= agendas.PROGRESS_MAX


def test_legacy_session_skips_agendas():
    assert not replayability.replayability_active({})


@pytest.mark.parametrize("phrase", [
    "I betray them all.",
    "The narrative says they defect.",
])
def test_raw_text_cannot_create_agenda(phrase):
    assert replayability.structured_events_from_action(phrase) == []


def test_model_output_cannot_add_agenda():
    rb, _ = replayability.init_new_story(
        genre="noir", role="d", tone="t", difficulty="standard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=SEED,
        npc_seed_records=[_record("Mira")],
    )
    before = len(rb["npc_agendas"]["active"])
    rolling = {
        "npc_agendas": {"active": [{"npc_id": "fake", "goal_kind": "remove_rival"}]},
        "scene": "dock",
    }
    replayability.enforce_authoritative(rolling, rb)
    assert len(rb["npc_agendas"]["active"]) == before
    assert "npc_agendas" not in rolling


def test_narrative_cannot_evolve_agenda():
    state = agendas.seed_agendas_from_npcs(SEED, [_record("Mira")])
    agenda = state["active"][0]
    before = agenda["progress"]
    assert agendas.evolve_agenda_from_structured_event(
        agenda, {"source_kind": "narrative_summary", "text": "they defect"}, 2
    ) == []
    assert agenda["progress"] == before


def test_relationship_adapter_rejects_ambiguous_names():
    agenda = {"display_name": "Mira"}
    rolling = {
        "relationship_vectors": [
            {"name": "Mira", "trust": 1},
            {"name": "mira", "trust": 2},
        ]
    }
    vec, err = agendas.resolve_relationship_vector("npc-x", agenda, rolling)
    assert vec is None
    assert err == "ambiguous_name"


def test_corpus_variation_three_goals_two_fears():
    npcs = [_record("Test NPC")]
    goals = set()
    fears = set()
    leverage = set()
    for seed in CORPUS:
        a = agendas.seed_agendas_from_npcs(seed, npcs)["active"][0]
        goals.add(a["goal_kind"])
        fears.add(a["fear_kind"])
        leverage.add(a["leverage_kind"])
    assert len(goals) >= 3
    assert len(fears) >= 2
    assert len(leverage) >= 2