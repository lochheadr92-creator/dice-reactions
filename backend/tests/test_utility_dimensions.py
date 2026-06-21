import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utility_dimensions import (
    DimensionSourceStatus,
    score_survival,
    score_stress_reduction,
    score_resource_gain_loss,
    clamp_score,
)


def test_survival_formula_ch_27_4_1():
    row = score_survival("gather")
    assert row.source_status == DimensionSourceStatus.EXACT_CANON_DERIVED
    assert row.value == clamp_score(0.6 * 25 + 0.1 * 25 + 0 + 0.1 * 25)


def test_stress_missing_fails_closed():
    row = score_stress_reduction("withdraw", stress_level=None)
    assert row.source_status == DimensionSourceStatus.MISSING_AUTHORITATIVE_INPUT
    assert row.blocker_code == "MISSING_STRESS_LEVEL"


def test_resource_missing_scarcity_fails_closed():
    row = score_resource_gain_loss("gather", svu_delta=0.5, resource_scarcity=None)
    assert row.source_status == DimensionSourceStatus.MISSING_AUTHORITATIVE_INPUT


def test_stress_not_applicable_for_non_reducing_move():
    row = score_stress_reduction("pressure", stress_level=None)
    assert row.source_status == DimensionSourceStatus.NOT_APPLICABLE