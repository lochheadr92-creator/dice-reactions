import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from foundation_acceptance.delta_ledger import (
    LEDGER_VERSION,
    build_delta_ledger,
    ledger_hash,
    ledger_metadata,
)
from foundation_acceptance.models import DeltaStatus


def test_ledger_hash_stable():
    entries = build_delta_ledger()
    assert ledger_hash(entries) == ledger_hash(entries)


def test_ledger_hash_changes_when_metadata_changes():
    entries = build_delta_ledger()
    h1 = ledger_hash(entries)
    meta = ledger_metadata(entries)
    meta["ledger_version"] = "1.0.1"
    from engine_determinism import stable_hash

    h2 = stable_hash("foundation_delta_ledger", meta)
    assert h1 != h2


def test_d_sel_placeholder_blocked_by_default():
    entries = build_delta_ledger()
    d_sel = next(e for e in entries if e.id == "D_SEL")
    assert d_sel.status == DeltaStatus.PLACEHOLDER_BLOCKED


def test_predicates_pure_and_repeatable():
    from foundation_acceptance.models import ComparisonInput

    entries = build_delta_ledger()
    inp = ComparisonInput(
        schema_version=1,
        fixture_id="f1",
        source_state_hash="abc",
        run_seed="seed",
        turn_sequence=1,
        canonical_actor_registry=(),
        provisional_state={},
        foundation_snapshot={},
        pressure_refs=(),
        consequence_refs=(),
        relationship_refs=(),
        agenda_refs=(),
        location_ref="",
        secret_access_flags=(),
        schema_versions={},
        baseline_source="SYNTHETIC_EXPECTED_DECISION",
        baseline_selector_commit="9da1ae2",
        baseline_result_hash="",
        provisional_result={"selected": {"action_kind": "gather"}},
        foundation_result={"selected": {"action_kind": "protect"}},
    )
    d_sel = next(e for e in entries if e.id == "D_SEL")
    r1 = d_sel.applies_when(inp)
    r2 = d_sel.applies_when(inp)
    assert r1 == r2
    assert r1.applies is True


@pytest.mark.parametrize("entry_id", ["D_TIER_ASSIGNMENT", "D_MEMORY_RETRIEVAL_SHADOW"])
def test_not_machine_checkable_entries(entry_id):
    entries = build_delta_ledger()
    entry = next(e for e in entries if e.id == entry_id)
    assert entry.status == DeltaStatus.NOT_MACHINE_CHECKABLE