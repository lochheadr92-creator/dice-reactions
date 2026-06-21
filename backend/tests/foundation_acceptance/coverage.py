"""Coverage policy tracking — applicability and witness coverage."""

from __future__ import annotations

from typing import Dict, Mapping, Sequence

from .models import Classification, DeltaEntry, DeltaStatus


def coverage_report(
    entries: Sequence[DeltaEntry],
    witness_results: Mapping[str, Classification],
) -> Dict[str, object]:
    applicability: Dict[str, bool] = {}
    witnesses: Dict[str, str] = {}
    for entry in entries:
        if entry.status == DeltaStatus.RETIRED:
            continue
        applicability[entry.id] = entry.coverage_policy.witness_fixture_id in witness_results
        if entry.coverage_policy.witness_fixture_id in witness_results:
            witnesses[entry.id] = witness_results[entry.coverage_policy.witness_fixture_id]
    return {
        "applicability": applicability,
        "witnesses": witnesses,
        "placeholder_blocked_ids": [
            e.id for e in entries if e.status == DeltaStatus.PLACEHOLDER_BLOCKED
        ],
        "not_machine_checkable_ids": [
            e.id for e in entries if e.status == DeltaStatus.NOT_MACHINE_CHECKABLE
        ],
    }