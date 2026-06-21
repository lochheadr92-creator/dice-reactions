"""
Structural determinism primitives for foundation engine systems.

No gameplay constants — serialization, hashing, and seeded draws only.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

SERIALIZATION_SCHEMA_VERSION = 1
RNG_ALGORITHM_VERSION = 1
SEED_MATERIAL_SCHEMA_VERSION = 1
NUMERIC_CONTRACT_VERSION = 1

# v0.1 numeric contract: evaluate float components in canonical key order;
# no rounding at intermediate steps; clamp only at documented boundaries.
# Canon does not define IEEE-754 rounding — intermediate values stay full precision.


class DeterminismError(ValueError):
    """Raised when canonical serialization or RNG material is invalid."""


def reject_non_finite(value: float) -> None:
    if not math.isfinite(value):
        raise DeterminismError(f"non-finite value: {value!r}")


def canonicalize(value: Any) -> Any:
    """Convert value to a JSON-serializable canonical form."""
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        reject_non_finite(value)
        return value
    if isinstance(value, enum.Enum):
        return value.value
    if dataclasses.is_dataclass(value):
        return canonicalize(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): canonicalize(inner)
            for key, inner in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [canonicalize(item) for item in value]
    if isinstance(value, set):
        return sorted(canonicalize(item) for item in value)
    raise DeterminismError(f"unsupported type for canonical serialization: {type(value)!r}")


def canonical_json(value: Any, *, schema_version: int = SERIALIZATION_SCHEMA_VERSION) -> str:
    payload = {"schema_version": schema_version, "value": canonicalize(value)}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(
    domain: str,
    payload: Any,
    *,
    schema_version: int = SERIALIZATION_SCHEMA_VERSION,
) -> str:
    material = f"{domain}|v{schema_version}|{canonical_json(payload, schema_version=schema_version)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def candidate_set_hash(
    *,
    actor_id: str,
    action_kind: str,
    target_kind: str,
    target_id: str,
    decision_version: int,
    candidates: Sequence[Mapping[str, Any]],
) -> str:
    return stable_hash(
        "candidate_set",
        {
            "actor_id": actor_id,
            "action_kind": action_kind,
            "target_kind": target_kind,
            "target_id": target_id,
            "decision_version": decision_version,
            "candidates": list(candidates),
        },
    )


def build_seed_material(
    *,
    run_seed: str,
    turn_sequence: int,
    subsystem: str,
    actor_id: str = "",
    candidate_set_hash_value: str = "",
) -> str:
    """Seed material never includes wall-clock time, PID, or dict insertion order."""
    parts = [
        f"run_seed={run_seed}",
        f"turn={turn_sequence}",
        f"subsystem={subsystem}",
        f"actor_id={actor_id}",
        f"candidate_set={candidate_set_hash_value}",
        f"rng_v={RNG_ALGORITHM_VERSION}",
        f"seed_schema_v={SEED_MATERIAL_SCHEMA_VERSION}",
    ]
    return "|".join(parts)


def derive_rng_unit(seed_material: str, draw_index: int) -> float:
    """
    Counter-based hash-derived draw in [0, 1).

    Algorithm version 1: SHA-256(seed_material|draw=N), first 13 hex chars → 52 bits.
    """
    digest = hashlib.sha256(f"{seed_material}|draw={draw_index}".encode("utf-8")).hexdigest()
    bits = int(digest[:13], 16)
    return bits / float(2**52)


def derive_rng_range(seed_material: str, draw_index: int, low: float, high: float) -> float:
    reject_non_finite(low)
    reject_non_finite(high)
    if high < low:
        raise DeterminismError("high must be >= low")
    unit = derive_rng_unit(seed_material, draw_index)
    return low + unit * (high - low)


def evaluate_weighted_average(
    components: Sequence[tuple[str, float, float]],
) -> float:
    """
    Weighted average in canonical (name-sorted) component order.

    Each tuple is (dimension_name, score, weight). Scores and weights must be finite.
    Returns unrounded average; callers clamp at subsystem boundaries.
    """
    if not components:
        raise DeterminismError("weighted average requires at least one component")
    ordered = sorted(components, key=lambda row: row[0])
    weighted_sum = 0.0
    weight_sum = 0.0
    for _name, score, weight in ordered:
        reject_non_finite(score)
        reject_non_finite(weight)
        if weight < 0:
            raise DeterminismError("weights must be non-negative")
        weighted_sum += score * weight
        weight_sum += weight
    if weight_sum == 0:
        raise DeterminismError("total weight must be positive")
    result = weighted_sum / weight_sum
    reject_non_finite(result)
    return result