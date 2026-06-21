"""Deterministic acceptance artifact serializer."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from engine_determinism import canonical_json, stable_hash

from . import HARNESS_SCHEMA_VERSION, HARNESS_VERSION
from .delta_ledger import LEDGER_VERSION, ledger_hash
from .models import ClassificationResult, ComparisonInput


def build_artifact(
    *,
    ledger_entries: Sequence,
    ledger_version: str,
    l_hash: str,
    corpus_version: str,
    corpus_hash: str,
    commit_sha: str,
    records: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    bucket_counts: Dict[str, int] = {}
    for rec in records:
        cls = str(rec.get("classification", "UNKNOWN"))
        bucket_counts[cls] = bucket_counts.get(cls, 0) + 1
    return {
        "schema_version": HARNESS_SCHEMA_VERSION,
        "harness_version": HARNESS_VERSION,
        "ledger_version": ledger_version,
        "ledger_hash": l_hash,
        "corpus_version": corpus_version,
        "corpus_hash": corpus_hash,
        "commit_sha": commit_sha,
        "comparison_count": len(records),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "coverage": {},
        "records": list(records),
    }


def artifact_bytes(artifact: Mapping[str, Any]) -> bytes:
    return canonical_json(artifact).encode("utf-8")


def artifact_hash(artifact: Mapping[str, Any]) -> str:
    return stable_hash("acceptance_artifact", artifact)


def comparison_record(
    inp: ComparisonInput,
    result: ClassificationResult,
) -> Dict[str, Any]:
    return {
        "fixture_id": inp.fixture_id,
        "classification": result.classification,
        "reason_code": result.reason_code,
        "matched_delta_ids": list(result.matched_delta_ids),
        "evidence_codes": list(result.evidence_codes),
        "baseline_source": inp.baseline_source,
        "baseline_result_hash": inp.baseline_result_hash,
    }