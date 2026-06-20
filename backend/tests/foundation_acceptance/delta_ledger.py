"""Executable canon-delta ledger — test-owned, versioned, hash-stable."""

from __future__ import annotations

from typing import List, Sequence, Tuple

from engine_determinism import stable_hash

from . import HARNESS_SCHEMA_VERSION
from .models import (
    ComparisonInput,
    CoveragePolicy,
    DeltaEntry,
    DeltaStatus,
    DivergenceFacet,
    DivergenceRecord,
    PredicateResult,
    PredictionResult,
)

LEDGER_SCHEMA_VERSION = 1
LEDGER_VERSION = "1.0.0"
CANON_SOURCE_VERSION = "1.2"
SOURCE_COMMIT_SHA = "9da1ae2ed7c12dc8b5984a343eee8adf3ff1cf67"


def _d_sel_applies(inp: ComparisonInput) -> PredicateResult:
    prov = inp.provisional_result.get("selected") or {}
    found = inp.foundation_result.get("selected") or {}
    differs = (
        prov.get("actor_id") != found.get("actor_id")
        or prov.get("action_kind") != found.get("action_kind")
        or prov.get("target_kind") != found.get("target_kind")
        or prov.get("target_id") != found.get("target_id")
    )
    codes = ("D_SEL_APPLIES",) if differs else ()
    return PredicateResult(
        applies=differs,
        evidence_codes=codes,
        observed_values={
            "provisional_action": str(prov.get("action_kind")),
            "foundation_action": str(found.get("action_kind")),
        },
    )


def _d_sel_predicts(inp: ComparisonInput, _rec: DivergenceRecord) -> PredictionResult:
    if not inp.utility_inputs_complete:
        return PredictionResult(
            verdict="INDETERMINATE",
            evidence_codes=("MISSING_AUTHORITATIVE_INPUT",),
        )
    return PredictionResult(
        verdict="PREDICTED",
        predicted_changed_fields=frozenset(
            {"selected_actor", "action_kind", "target_kind", "target_id"}
        ),
        evidence_codes=("CANON_ORACLE_MATCH",),
    )


def _tier_assignment_applies(inp: ComparisonInput) -> PredicateResult:
    prov_tiers = inp.provisional_result.get("tiers_by_actor_id") or {}
    found_tiers = inp.foundation_result.get("tiers_by_actor_id") or {}
    differs = prov_tiers != found_tiers
    return PredicateResult(
        applies=differs,
        evidence_codes=("TIER_DIFF",) if differs else (),
        observed_values={"count": len(set(prov_tiers) | set(found_tiers))},
    )


def _tier_assignment_predicts(_inp: ComparisonInput, _rec: DivergenceRecord) -> PredictionResult:
    return PredictionResult(
        verdict="INDETERMINATE",
        evidence_codes=("MISSING_CONTEXT_GRAVITY",),
    )


def _acting_eligibility_applies(inp: ComparisonInput) -> PredicateResult:
    prov = set(inp.provisional_result.get("acting_actor_ids") or [])
    found = set(inp.foundation_result.get("acting_actor_ids") or [])
    differs = prov != found
    return PredicateResult(applies=differs, evidence_codes=("ACTING_SET_DIFF",) if differs else ())


def _acting_eligibility_predicts(inp: ComparisonInput, rec: DivergenceRecord) -> PredictionResult:
    if rec.field_name != "acting_eligibility":
        return PredictionResult(verdict="NOT_APPLICABLE_TO_FACET")
    return PredictionResult(
        verdict="PREDICTED",
        predicted_changed_fields=frozenset({"eligibility"}),
        evidence_codes=("CANON_ELIGIBILITY",),
    )


def _cadence_applies(inp: ComparisonInput) -> PredicateResult:
    prov = inp.provisional_result.get("processing_eligible") or {}
    found = inp.foundation_result.get("processing_eligible") or {}
    differs = prov != found
    return PredicateResult(applies=differs, evidence_codes=("CADENCE_DIFF",) if differs else ())


def _cadence_predicts(_inp: ComparisonInput, _rec: DivergenceRecord) -> PredictionResult:
    return PredictionResult(
        verdict="PREDICTED",
        predicted_changed_fields=frozenset({"processing_eligibility"}),
        evidence_codes=("CANON_CADENCE",),
    )


def _grace_applies(inp: ComparisonInput) -> PredicateResult:
    prov = inp.provisional_result.get("tier_after_grace") or {}
    found = inp.foundation_result.get("tier_after_grace") or {}
    differs = prov != found
    return PredicateResult(applies=differs, evidence_codes=("GRACE_DIFF",) if differs else ())


def _grace_predicts(_inp: ComparisonInput, _rec: DivergenceRecord) -> PredictionResult:
    return PredictionResult(
        verdict="INDETERMINATE",
        evidence_codes=("BLOCKED_BY_MISSING_AUTHORITATIVE_INPUT_SIMULATION_TIME",),
    )


def _utility_placeholder_applies(inp: ComparisonInput) -> PredicateResult:
    blockers = inp.foundation_result.get("blocker_codes") or ()
    applies = bool(blockers) and not inp.utility_inputs_complete
    return PredicateResult(
        applies=applies,
        evidence_codes=tuple(blockers) if applies else (),
    )


def _utility_placeholder_predicts(_inp: ComparisonInput, _rec: DivergenceRecord) -> PredictionResult:
    return PredictionResult(
        verdict="PREDICTED",
        predicted_changed_fields=frozenset({"dimension_score"}),
        evidence_codes=("PLACEHOLDER_HEURISTIC",),
    )


def _memory_shadow_applies(inp: ComparisonInput) -> PredicateResult:
    prov = set(inp.provisional_result.get("retrieved_memory_ids") or [])
    found = set(inp.foundation_result.get("retrieved_memory_ids") or [])
    differs = prov != found
    return PredicateResult(applies=differs, evidence_codes=("RETRIEVAL_DIFF",) if differs else ())


def _memory_shadow_predicts(_inp: ComparisonInput, _rec: DivergenceRecord) -> PredictionResult:
    return PredictionResult(verdict="INDETERMINATE", evidence_codes=("SEPARATE_SHADOW_ACCEPTANCE_REQUIRED",))


def build_delta_ledger() -> Tuple[DeltaEntry, ...]:
    return (
        DeltaEntry(
            id="D_SEL",
            system="utility_ai",
            canon_ref="Source_of_Truth_v1.2.md:L18949-L18956",
            description="Foundation utility selection equals independent canon oracle when inputs complete.",
            facet=DivergenceFacet.ACTION_KIND,
            applies_when=_d_sel_applies,
            predicts=_d_sel_predicts,
            allowed_changed_fields=frozenset(
                {"selected_actor", "action_kind", "target_kind", "target_id"}
            ),
            forbidden_changed_fields=frozenset({"eligibility", "tier"}),
            coverage_policy=CoveragePolicy(
                decision_affecting=True,
                witness_fixture_id="utility_oracle_complete_v1",
                requires_attributed_witness=True,
            ),
            status=DeltaStatus.PLACEHOLDER_BLOCKED,
        ),
        DeltaEntry(
            id="D_UTILITY_PLACEHOLDER",
            system="utility_ai",
            canon_ref="Source_of_Truth_v1.2.md:L18910-L18927",
            description="Heuristic or missing-input dimension scoring blocks replacement.",
            facet=DivergenceFacet.DIMENSION_SCORE,
            applies_when=_utility_placeholder_applies,
            predicts=_utility_placeholder_predicts,
            allowed_changed_fields=frozenset({"dimension_score", "score_order"}),
            forbidden_changed_fields=frozenset({"selected_actor", "action_kind"}),
            coverage_policy=CoveragePolicy(
                decision_affecting=False,
                witness_fixture_id="utility_dimension_surface_v1",
            ),
            status=DeltaStatus.PLACEHOLDER_BLOCKED,
        ),
        DeltaEntry(
            id="D_TIER_ASSIGNMENT",
            system="actor_resolution",
            canon_ref="Source_of_Truth_v1.2.md:L18521-L18530",
            description="Tier assignment requires Context Gravity inputs.",
            facet=DivergenceFacet.TIER,
            applies_when=_tier_assignment_applies,
            predicts=_tier_assignment_predicts,
            allowed_changed_fields=frozenset({"tier"}),
            forbidden_changed_fields=frozenset({"selected_actor", "action_kind"}),
            coverage_policy=CoveragePolicy(
                decision_affecting=False,
                witness_fixture_id="tier_assignment_v1",
            ),
            status=DeltaStatus.NOT_MACHINE_CHECKABLE,
        ),
        DeltaEntry(
            id="D_ACTING_ELIGIBILITY",
            system="actor_resolution",
            canon_ref="Source_of_Truth_v1.2.md:L18348-L18412",
            description="Acting set inclusion/exclusion per canon eligibility.",
            facet=DivergenceFacet.ELIGIBILITY,
            applies_when=_acting_eligibility_applies,
            predicts=_acting_eligibility_predicts,
            allowed_changed_fields=frozenset({"eligibility"}),
            forbidden_changed_fields=frozenset({"action_kind", "target_id"}),
            coverage_policy=CoveragePolicy(
                decision_affecting=True,
                witness_fixture_id="acting_eligibility_v1",
            ),
            status=DeltaStatus.ACTIVE,
        ),
        DeltaEntry(
            id="D_TIER_PROCESSING_CADENCE",
            system="actor_resolution",
            canon_ref="Source_of_Truth_v1.2.md:L18966-L18974",
            description="Processing cadence differs while actor remains referenceable.",
            facet=DivergenceFacet.PROCESSING_ELIGIBILITY,
            applies_when=_cadence_applies,
            predicts=_cadence_predicts,
            allowed_changed_fields=frozenset({"processing_eligibility"}),
            forbidden_changed_fields=frozenset({"selected_actor"}),
            coverage_policy=CoveragePolicy(
                decision_affecting=False,
                witness_fixture_id="cadence_v1",
            ),
            status=DeltaStatus.ACTIVE,
        ),
        DeltaEntry(
            id="D_GRACE",
            system="actor_resolution",
            canon_ref="Source_of_Truth_v1.2.md:L18490-L18495",
            description="Demotion grace requires authoritative simulation time.",
            facet=DivergenceFacet.TIER,
            applies_when=_grace_applies,
            predicts=_grace_predicts,
            allowed_changed_fields=frozenset({"tier"}),
            forbidden_changed_fields=frozenset({"action_kind"}),
            coverage_policy=CoveragePolicy(
                decision_affecting=False,
                witness_fixture_id="grace_explicit_time_v1",
            ),
            status=DeltaStatus.PLACEHOLDER_BLOCKED,
        ),
        DeltaEntry(
            id="D_MEMORY_RETRIEVAL_SHADOW",
            system="memory_retrieval",
            canon_ref="Source_of_Truth_v1.2.md:L19118-L19133",
            description="Retrieval shadow compare — separate acceptance track.",
            facet=DivergenceFacet.RETRIEVAL_MEMBERSHIP,
            applies_when=_memory_shadow_applies,
            predicts=_memory_shadow_predicts,
            allowed_changed_fields=frozenset({"retrieval_membership"}),
            forbidden_changed_fields=frozenset({"selected_actor", "action_kind"}),
            coverage_policy=CoveragePolicy(
                decision_affecting=False,
                witness_fixture_id="retrieval_shadow_v1",
            ),
            status=DeltaStatus.NOT_MACHINE_CHECKABLE,
        ),
    )


def ledger_metadata(entries: Sequence[DeltaEntry]) -> dict:
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "ledger_version": LEDGER_VERSION,
        "canon_source_version": CANON_SOURCE_VERSION,
        "source_commit_sha": SOURCE_COMMIT_SHA,
        "entry_ids": sorted(e.id for e in entries),
        "entry_statuses": {e.id: e.status.value for e in entries},
        "entry_facets": {e.id: e.facet.value for e in entries},
    }


def ledger_hash(entries: Sequence[DeltaEntry]) -> str:
    return stable_hash("foundation_delta_ledger", ledger_metadata(entries))


def active_entries(entries: Sequence[DeltaEntry]) -> List[DeltaEntry]:
    return [e for e in entries if e.status == DeltaStatus.ACTIVE]


def get_d_sel_status(utility_contract_complete: bool) -> DeltaStatus:
    return DeltaStatus.ACTIVE if utility_contract_complete else DeltaStatus.PLACEHOLDER_BLOCKED