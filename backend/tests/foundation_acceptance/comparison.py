"""Comparison classifier — deterministic, pure, no side effects."""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from .models import (
    Classification,
    ClassificationResult,
    ComparisonInput,
    DeltaEntry,
    DeltaStatus,
    DivergenceFacet,
    DivergenceRecord,
    LedgerGap,
    PredictionResult,
)


def global_decision_tuple(result: Dict) -> Tuple:
    sel = result.get("selected") or {}
    return (
        sel.get("actor_id"),
        sel.get("action_kind"),
        sel.get("target_kind"),
        sel.get("target_id"),
    )


def collect_divergences(inp: ComparisonInput) -> Tuple[DivergenceRecord, ...]:
    records: List[DivergenceRecord] = []
    if global_decision_tuple(inp.provisional_result) != global_decision_tuple(inp.foundation_result):
        prov = inp.provisional_result.get("selected") or {}
        found = inp.foundation_result.get("selected") or {}
        for field, facet in (
            ("actor_id", DivergenceFacet.SELECTED_ACTOR),
            ("action_kind", DivergenceFacet.ACTION_KIND),
            ("target_kind", DivergenceFacet.TARGET_KIND),
            ("target_id", DivergenceFacet.TARGET_ID),
        ):
            if prov.get(field) != found.get(field):
                records.append(
                    DivergenceRecord(
                        facet=facet,
                        field_name=field,
                        provisional_value=prov.get(field),
                        foundation_value=found.get(field),
                    )
                )
    prov_tiers = inp.provisional_result.get("tiers_by_actor_id") or {}
    found_tiers = inp.foundation_result.get("tiers_by_actor_id") or {}
    for actor_id in sorted(set(prov_tiers) | set(found_tiers)):
        if prov_tiers.get(actor_id) != found_tiers.get(actor_id):
            records.append(
                DivergenceRecord(
                    facet=DivergenceFacet.TIER,
                    field_name="tier",
                    provisional_value=prov_tiers.get(actor_id),
                    foundation_value=found_tiers.get(actor_id),
                )
            )
    prov_acting = set(inp.provisional_result.get("acting_actor_ids") or [])
    found_acting = set(inp.foundation_result.get("acting_actor_ids") or [])
    if prov_acting != found_acting:
        records.append(
            DivergenceRecord(
                facet=DivergenceFacet.ELIGIBILITY,
                field_name="acting_eligibility",
                provisional_value=str(sorted(prov_acting)),
                foundation_value=str(sorted(found_acting)),
            )
        )
    prov_scores = inp.provisional_result.get("dimension_scores") or {}
    found_scores = inp.foundation_result.get("dimension_scores") or {}
    for dim in sorted(set(prov_scores) | set(found_scores)):
        if prov_scores.get(dim) != found_scores.get(dim):
            records.append(
                DivergenceRecord(
                    facet=DivergenceFacet.DIMENSION_SCORE,
                    field_name=dim,
                    provisional_value=prov_scores.get(dim),
                    foundation_value=found_scores.get(dim),
                )
            )
    return tuple(records)


def map_ledger_gap(exc: LedgerGap) -> ClassificationResult:
    mapping = {
        "MISSING_AUTHORITATIVE_INPUT": "INCONCLUSIVE",
        "PLACEHOLDER_IMPLEMENTATION": "PLACEHOLDER_DRIVEN",
        "MALFORMED_FIXTURE": "INCONCLUSIVE",
        "SELECTOR_ERROR": "INCONCLUSIVE",
        "UNSUPPORTED_SCHEMA": "INCONCLUSIVE",
        "MISSING_BASELINE": "INCONCLUSIVE",
        "LEDGER_CONFLICT": "INCONCLUSIVE",
        "PREDICTION_INDETERMINATE": "INCONCLUSIVE",
    }
    classification: Classification = mapping.get(exc.reason_code, "INCONCLUSIVE")
    return ClassificationResult(classification=classification, reason_code=exc.reason_code)


def classify(
    inp: ComparisonInput,
    entries: Sequence[DeltaEntry],
    divergences: Sequence[DivergenceRecord],
) -> ClassificationResult:
    if inp.baseline_source == "NO_BASELINE_AVAILABLE":
        return ClassificationResult(classification="INCONCLUSIVE", reason_code="MISSING_BASELINE")

    if not divergences:
        return ClassificationResult(classification="MATCH", reason_code="NO_DIVERGENCE")

    attributed: List[str] = []
    evidence: List[str] = []
    placeholder_hit = False
    contradiction = False
    indeterminate = False

    for rec in divergences:
        applicable = [e for e in entries if e.facet == rec.facet and e.status != DeltaStatus.RETIRED]
        if not applicable:
            return ClassificationResult(
                classification="UNATTRIBUTED",
                reason_code="NO_DELTA_FOR_FACET",
            )
        predictions: List[PredictionResult] = []
        for entry in applicable:
            pred = entry.applies_when(inp)
            if not pred.applies:
                continue
            if entry.status == DeltaStatus.NOT_MACHINE_CHECKABLE:
                indeterminate = True
                evidence.append("NOT_MACHINE_CHECKABLE")
                continue
            if entry.status == DeltaStatus.PLACEHOLDER_BLOCKED:
                placeholder_hit = True
                evidence.append(entry.id)
                continue
            if rec.field_name in entry.forbidden_changed_fields:
                return ClassificationResult(
                    classification="CONTRADICTION",
                    reason_code="FORBIDDEN_FIELD_CHANGED",
                    matched_delta_ids=tuple(e.id for e in applicable),
                )
            pr = entry.predicts(inp, rec)
            predictions.append(pr)
            if pr.verdict == "CONTRADICTED":
                contradiction = True
            elif pr.verdict == "INDETERMINATE":
                indeterminate = True
            elif pr.verdict == "PREDICTED" and entry.status == DeltaStatus.ACTIVE:
                attributed.append(entry.id)

        same_facet_verdicts = {p.verdict for p in predictions if p.verdict != "NOT_APPLICABLE_TO_FACET"}
        if len(same_facet_verdicts) > 1 and "CONTRADICTED" in same_facet_verdicts:
            return ClassificationResult(classification="INCONCLUSIVE", reason_code="LEDGER_CONFLICT")

    if contradiction:
        return ClassificationResult(
            classification="CONTRADICTION",
            reason_code="DELTA_CONTRADICTION",
            matched_delta_ids=tuple(attributed),
            evidence_codes=tuple(evidence),
        )
    if indeterminate:
        return ClassificationResult(classification="INCONCLUSIVE", reason_code="PREDICTION_INDETERMINATE")
    if placeholder_hit and not attributed:
        return ClassificationResult(
            classification="PLACEHOLDER_DRIVEN",
            reason_code="PLACEHOLDER_BLOCKED",
            evidence_codes=tuple(evidence),
        )
    if attributed:
        return ClassificationResult(
            classification="ATTRIBUTED",
            reason_code="DELTA_ATTRIBUTED",
            matched_delta_ids=tuple(sorted(set(attributed))),
            evidence_codes=tuple(evidence),
        )
    return ClassificationResult(classification="UNATTRIBUTED", reason_code="UNEXPLAINED_DIVERGENCE")