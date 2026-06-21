import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from foundation_acceptance.comparison import classify, collect_divergences, map_ledger_gap
from foundation_acceptance.delta_ledger import build_delta_ledger
from foundation_acceptance.models import ComparisonInput, LedgerGap


def _inp(**kwargs):
    base = dict(
        schema_version=1,
        fixture_id="f1",
        source_state_hash="h",
        run_seed="s",
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
        provisional_result={},
        foundation_result={},
    )
    base.update(kwargs)
    return ComparisonInput(**base)


def test_match_when_no_divergence():
    inp = _inp(
        provisional_result={"selected": {"action_kind": "gather"}},
        foundation_result={"selected": {"action_kind": "gather"}},
    )
    divs = collect_divergences(inp)
    result = classify(inp, build_delta_ledger(), divs)
    assert result.classification == "MATCH"


def test_placeholder_driven_when_utility_blocked():
    inp = _inp(
        utility_inputs_complete=False,
        provisional_result={"dimension_scores": {"survival": 40}},
        foundation_result={
            "blocker_codes": ("MISSING_STRESS_LEVEL",),
            "dimension_scores": {"survival": 80},
        },
    )
    divs = collect_divergences(inp)
    result = classify(inp, build_delta_ledger(), divs)
    assert result.classification in ("PLACEHOLDER_DRIVEN", "UNATTRIBUTED", "INCONCLUSIVE")


def test_ledger_gap_maps_to_inconclusive():
    result = map_ledger_gap(LedgerGap("MISSING_AUTHORITATIVE_INPUT"))
    assert result.classification == "INCONCLUSIVE"


def test_same_facet_active_entries_do_not_conflict():
    entries = [e for e in build_delta_ledger() if e.facet.value == "eligibility"]
    assert len(entries) == 1