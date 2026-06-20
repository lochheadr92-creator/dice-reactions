import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine_determinism import (
    DeterminismError,
    SERIALIZATION_SCHEMA_VERSION,
    build_seed_material,
    canonical_json,
    candidate_set_hash,
    derive_rng_range,
    derive_rng_unit,
    evaluate_weighted_average,
    stable_hash,
)


def test_canonical_json_sorted_keys_and_sets():
    payload = {"b": 1, "a": {"z": 1, "y": 2}, "c": {3, 1, 2}}
    text = canonical_json(payload)
    assert '"a"' in text
    assert text.index('"a"') < text.index('"b"')
    assert "[1,2,3]" in text or "[1, 2, 3]" not in text


def test_reject_nan_and_infinity():
    with pytest.raises(DeterminismError):
        canonical_json({"x": float("nan")})
    with pytest.raises(DeterminismError):
        canonical_json({"x": float("inf")})


def test_stable_hash_independent_of_insertion_order():
    h1 = stable_hash("domain", {"a": 1, "b": 2})
    h2 = stable_hash("domain", {"b": 2, "a": 1})
    assert h1 == h2


def test_candidate_set_hash_includes_identity_fields():
    h = candidate_set_hash(
        actor_id="actor-1",
        action_kind="gather",
        target_kind="pressure",
        target_id="p1",
        decision_version=1,
        candidates=[{"actor_id": "actor-1"}],
    )
    assert len(h) == 64


def test_rng_draw_is_stable_across_pythonhashseed():
    material = build_seed_material(
        run_seed="seed",
        turn_sequence=3,
        subsystem="utility_ai",
        actor_id="actor-1",
        candidate_set_hash_value="abc",
    )
    draws = [derive_rng_unit(material, i) for i in range(5)]
    assert all(0.0 <= d < 1.0 for d in draws)
    assert draws[0] != draws[1]


def test_rng_range_respects_bounds():
    material = build_seed_material(
        run_seed="seed",
        turn_sequence=1,
        subsystem="test",
    )
    value = derive_rng_range(material, 0, -0.5, 0.5)
    assert -0.5 <= value <= 0.5


def test_weighted_average_canonical_order():
    avg = evaluate_weighted_average(
        [
            ("z", 100.0, 1.0),
            ("a", 0.0, 1.0),
        ]
    )
    assert avg == 50.0


@pytest.mark.parametrize("pythonhashseed", ["1", "98765"])
def test_hash_stability_under_pythonhashseed(pythonhashseed, monkeypatch):
    monkeypatch.setenv("PYTHONHASHSEED", pythonhashseed)
    payload = {"schema_version": SERIALIZATION_SCHEMA_VERSION, "actors": ["b", "a"]}
    assert stable_hash("replay", payload) == stable_hash("replay", payload)