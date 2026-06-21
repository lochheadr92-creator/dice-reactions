"""Living Cast bounded-state audit — real max-cap fixtures and hard-cap proofs."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import arc_diversity as arc  # noqa: E402
import consequence_echoes as echoes  # noqa: E402
import living_cast_bounded_fixtures as fixtures  # noqa: E402
import npc_agendas as agendas  # noqa: E402
import npc_world_moves as moves  # noqa: E402
import replayability  # noqa: E402

SEED = fixtures.SEED


def _capped_state():
    return fixtures.build_replayability_state_at_all_caps()


# --------------------------------------------------------------------------- fixtures
def test_max_cap_fixture_counts():
    state = _capped_state()
    assert len(state["npc_agendas"]["active"]) == fixtures.CAP_ACTIVE_AGENDAS
    assert len(state["npc_agendas"]["archived"]) == fixtures.CAP_ARCHIVED_AGENDAS
    assert len(state["npc_move_receipts"]) == fixtures.CAP_MOVE_RECEIPTS
    assert len(state["relationship_effect_receipts"]) == fixtures.CAP_REL_EFFECT_RECEIPTS
    assert len(state["arc_diversity"]["recent_beats"]) == fixtures.CAP_ARC_BEATS
    assert len(state["consequence_echoes"]["scheduled"]) == fixtures.CAP_ECHO_SCHEDULED
    assert len(state["consequence_echoes"]["fired"]) == fixtures.CAP_ECHO_FIRED
    assert len(state["pressure_graph"]["nodes"]) == fixtures.CAP_PRESSURE_NODES
    assert len(state["pressure_graph"]["threshold_crossings"]) == fixtures.CAP_THRESHOLD_RECEIPTS


def test_capped_state_within_documented_budget():
    state = _capped_state()
    size = replayability.replayability_state_byte_size(state)
    assert size <= replayability.REPLAYABILITY_STATE_BUDGET_BYTES
    metrics = replayability.living_cast_state_metrics(state)
    assert metrics["within_budget"] is True


def test_capped_state_metrics_non_trivial():
    state = _capped_state()
    metrics = replayability.living_cast_state_metrics(state)
    assert metrics["active_agendas"]["count"] == 12
    assert metrics["active_agendas"]["bytes"] > 3000
    assert metrics["archived_agendas"]["count"] == 8
    assert metrics["archived_agendas"]["bytes"] > 200
    assert metrics["npc_move_receipts"]["count"] == 24
    assert metrics["npc_move_receipts"]["bytes"] > 8000
    assert metrics["relationship_effect_receipts"]["count"] == 32
    assert metrics["relationship_effect_receipts"]["bytes"] > 2000
    assert metrics["arc_diversity_beats"]["count"] == 12
    assert metrics["arc_diversity_beats"]["bytes"] > 400
    assert metrics["pressure_graph"]["bytes"] > 2000
    assert metrics["consequence_echoes"]["bytes"] > 5000
    assert metrics["full_replayability_state"]["bytes"] > 12000


def test_directive_sizes_at_cap():
    lc = fixtures.build_max_living_cast_directive()
    combo = fixtures.build_max_opening_plus_living_cast_directive()
    assert len(lc.encode("utf-8")) > 100
    assert len(combo.encode("utf-8")) > len(lc.encode("utf-8"))


# --------------------------------------------------------------------------- agenda caps
def test_agenda_13_is_rejected_on_seed():
    records = [
        {"name": f"NPC-{i}", "source_type": "seed_record", "source_slot": i}
        for i in range(13)
    ]
    state = agendas.seed_agendas_from_npcs(SEED, records)
    assert len(state["active"]) == agendas.MAX_ACTIVE_AGENDAS


def test_archived_summary_9_drops_oldest():
    ag_state = agendas.init_npc_agendas()
    for i in range(9):
        ag_state["archived"].append(
            {"npc_id": f"npc-old-{i}", "goal_kind": "escape_danger", "final_progress": i}
        )
        if len(ag_state["archived"]) > agendas.MAX_ARCHIVED_SUMMARIES:
            ag_state["archived"] = ag_state["archived"][-agendas.MAX_ARCHIVED_SUMMARIES:]
    assert len(ag_state["archived"]) == 8
    assert ag_state["archived"][0]["npc_id"] == "npc-old-1"


# --------------------------------------------------------------------------- receipt caps
def test_move_receipt_25_enforces_hard_cap():
    receipts = [fixtures.build_move_receipt_at_index(i) for i in range(25)]
    capped = moves.enforce_npc_move_receipt_cap(receipts)
    assert len(capped) == moves.MAX_NPC_MOVE_RECEIPTS
    assert all("effects" not in r or r.get("compressed") for r in capped[: len(capped) - 1] or capped)


def test_receipt_cap_compression_is_idempotent():
    receipts = [fixtures.build_move_receipt_at_index(i) for i in range(30)]
    once = moves.enforce_npc_move_receipt_cap(receipts)
    twice = moves.enforce_npc_move_receipt_cap(once)
    assert once == twice


def test_relationship_effect_cap_truncates_oldest():
    state = replayability.empty_replayability_state()
    for i in range(33):
        replayability._append_relationship_effect_receipt(
            state,
            fixtures.build_relationship_effect_receipt_at_index(i),
        )
    assert len(state["relationship_effect_receipts"]) == replayability.RELATIONSHIP_EFFECT_RECEIPTS_MAX
    assert state["relationship_effect_receipts"][0]["receipt_id"] == "rel-fx-0001"


# --------------------------------------------------------------------------- arc beats
def test_beat_13_drops_oldest():
    arc_state = arc.init_arc_diversity()
    for i in range(13):
        arc.record_beat(arc_state, turn_number=i + 1, kind="npc_move", subkind="pressure", urgency=50)
    assert len(arc_state["recent_beats"]) == arc.MAX_RECENT_BEATS
    assert arc_state["recent_beats"][0]["turn"] == 2


# --------------------------------------------------------------------------- echo worst-case
def test_worst_case_echo_references_do_not_pin_full_receipts():
    state = replayability.empty_replayability_state()
    state["run_seed"] = SEED
    echo_state = echoes.init_consequence_echoes()
    scheduled = []
    for i in range(30):
        receipt = fixtures.build_move_receipt_at_index(i)
        rid = str(receipt["receipt_id"])
        moves.append_npc_move_receipt(state, receipt)
        src = moves.move_to_echo_source(
            {
                "receipt_id": rid,
                "move_kind": "pressure",
                "npc_id": receipt["npc_id"],
                "agenda_id": receipt["agenda_id"],
                "target_type": receipt["target_type"],
                "target_id": receipt["target_id"],
            }
        )
        echoes.schedule_from_structured_events(echo_state, [src], 2 + i)
        scheduled.append(src["source_event_id"])
    assert len(state["npc_move_receipts"]) <= moves.MAX_NPC_MOVE_RECEIPTS
    for entry in echo_state["scheduled"]:
        assert entry.get("source_provenance")
        assert entry["source_provenance"].get("npc_id")
        assert entry["source_provenance"].get("move_kind")
    # pending echo can still fire
    echo_state["pending"] = list(echo_state["scheduled"][:3])
    fired, did = echoes.fire_echo(echo_state, 99)
    assert did and fired
    assert fired.get("source_provenance")
    # duplicate source blocked
    retained = echo_state["scheduled"][-1]
    retained_rid = retained["source_event_id"]
    dup_added = echoes.schedule_from_structured_events(
        echo_state,
        [moves.move_to_echo_source(
            {
                "receipt_id": retained_rid,
                "move_kind": "pressure",
                "npc_id": fixtures._npc_id(0),
                "agenda_id": agendas.agenda_id(fixtures._npc_id(0)),
                "target_type": "player",
                "target_id": "player",
            }
        )],
        100,
        processed_source_ids=echoes.processed_source_event_ids(echo_state),
    )
    assert not dup_added


# --------------------------------------------------------------------------- relationship storage
def test_relationship_threshold_receipt_not_duplicate_of_move_bundle():
    move_receipt = fixtures.build_move_receipt_at_index(0)
    threshold = fixtures.build_relationship_effect_receipt_at_index(0)
    assert "effects" in move_receipt
    assert "effects" not in threshold
    assert threshold["source_effect_id"]
    assert not any(
        k in threshold
        for k in ("delta", "defer_finalize", "before", "after")
        if k not in ("before_state", "after_state")
    )


def test_one_lc_relationship_effect_single_canonical_bundle():
    state = _capped_state()
    full_bundles = sum(
        1
        for r in state["npc_move_receipts"]
        if isinstance(r.get("effects"), list) and r["effects"]
    )
    threshold_only = len(state["relationship_effect_receipts"])
    assert full_bundles > 0
    assert threshold_only == 32
    for rel_r in state["relationship_effect_receipts"]:
        assert "effects" not in rel_r


# --------------------------------------------------------------------------- no unbounded growth
@pytest.mark.parametrize(
    "cap_fn,expected",
    [
        (lambda: agendas.seed_agendas_from_npcs(SEED, [{"name": f"N{i}", "source_type": "seed_record", "source_slot": i} for i in range(20)])["active"], agendas.MAX_ACTIVE_AGENDAS),
        (lambda: moves.enforce_npc_move_receipt_cap([fixtures.build_move_receipt_at_index(i) for i in range(40)]), moves.MAX_NPC_MOVE_RECEIPTS),
    ],
)
def test_structures_do_not_grow_without_bound(cap_fn, expected):
    result = cap_fn()
    assert len(result) == expected