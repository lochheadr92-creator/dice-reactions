"""Immutable typed records for Foundation acceptance harness."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable, FrozenSet, Literal, Mapping, Optional, Tuple

CanonicalScalar = str | int | float | bool | None

Classification = Literal[
    "MATCH",
    "ATTRIBUTED",
    "PLACEHOLDER_DRIVEN",
    "CONTRADICTION",
    "UNATTRIBUTED",
    "INCONCLUSIVE",
]

PredictionVerdict = Literal[
    "PREDICTED",
    "CONTRADICTED",
    "NOT_APPLICABLE_TO_FACET",
    "INDETERMINATE",
]

BaselineSource = Literal[
    "RECORDED_PERSISTED_DECISION",
    "FROZEN_PROVISIONAL_OUTPUT",
    "SYNTHETIC_EXPECTED_DECISION",
    "NO_BASELINE_AVAILABLE",
]


class DivergenceFacet(str, enum.Enum):
    ACTOR_SET = "actor_set"
    ELIGIBILITY = "eligibility"
    PROCESSING_ELIGIBILITY = "processing_eligibility"
    TIER = "tier"
    SELECTED_ACTOR = "selected_actor"
    ACTION_KIND = "action_kind"
    TARGET_KIND = "target_kind"
    TARGET_ID = "target_id"
    PREPARED_EFFECT_KIND = "prepared_effect_kind"
    PREPARED_EFFECT_DIRECTION = "prepared_effect_direction"
    DIMENSION_SCORE = "dimension_score"
    SCORE_ORDER = "score_order"
    TIE_MEMBERSHIP = "tie_membership"
    RETRIEVAL_MEMBERSHIP = "retrieval_membership"
    RETRIEVAL_ORDER = "retrieval_order"
    GRAVITY_DISPOSITION = "gravity_disposition"


class DeltaStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PLACEHOLDER_BLOCKED = "PLACEHOLDER_BLOCKED"
    NOT_MACHINE_CHECKABLE = "NOT_MACHINE_CHECKABLE"
    RETIRED = "RETIRED"


@dataclass(frozen=True)
class PredicateResult:
    applies: bool
    evidence_codes: Tuple[str, ...] = ()
    observed_values: Mapping[str, CanonicalScalar] = field(default_factory=dict)


@dataclass(frozen=True)
class PredictionResult:
    verdict: PredictionVerdict
    predicted_changed_fields: FrozenSet[str] = frozenset()
    evidence_codes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CoveragePolicy:
    decision_affecting: bool
    witness_fixture_id: str
    requires_attributed_witness: bool = False


@dataclass(frozen=True)
class DeltaEntry:
    id: str
    system: str
    canon_ref: str
    description: str
    facet: DivergenceFacet
    applies_when: Callable[[ComparisonInput], PredicateResult]
    predicts: Callable[[ComparisonInput, DivergenceRecord], PredictionResult]
    allowed_changed_fields: FrozenSet[str]
    forbidden_changed_fields: FrozenSet[str]
    coverage_policy: CoveragePolicy
    status: DeltaStatus


@dataclass(frozen=True)
class ComparisonInput:
    schema_version: int
    fixture_id: str
    source_state_hash: str
    run_seed: str
    turn_sequence: int
    canonical_actor_registry: Tuple[Mapping[str, Any], ...]
    provisional_state: Mapping[str, Any]
    foundation_snapshot: Mapping[str, Any]
    pressure_refs: Tuple[str, ...]
    consequence_refs: Tuple[str, ...]
    relationship_refs: Tuple[str, ...]
    agenda_refs: Tuple[Mapping[str, Any], ...]
    location_ref: str
    secret_access_flags: Tuple[str, ...]
    schema_versions: Mapping[str, int]
    baseline_source: BaselineSource
    baseline_selector_commit: str
    baseline_result_hash: str
    provisional_result: Mapping[str, Any]
    foundation_result: Mapping[str, Any]
    utility_inputs_complete: bool = False


@dataclass(frozen=True)
class DivergenceRecord:
    facet: DivergenceFacet
    field_name: str
    provisional_value: CanonicalScalar
    foundation_value: CanonicalScalar


@dataclass(frozen=True)
class ClassificationResult:
    classification: Classification
    reason_code: str
    matched_delta_ids: Tuple[str, ...] = ()
    evidence_codes: Tuple[str, ...] = ()


class LedgerGap(Exception):
    reason_code: str

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code