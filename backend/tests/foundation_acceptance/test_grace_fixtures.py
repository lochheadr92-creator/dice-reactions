import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import actor_resolution


def test_grace_inside_boundary_blocks_demotion():
    result = actor_resolution._apply_demotion_grace(
        current_tier="hero",
        proposed_tier="active",
        last_interaction_minutes=0,
        now_minutes=3,
    )
    assert result == "hero"


def test_grace_outside_boundary_allows_demotion():
    result = actor_resolution._apply_demotion_grace(
        current_tier="active",
        proposed_tier="relevant",
        last_interaction_minutes=0,
        now_minutes=actor_resolution.DEMOTION_GRACE_MINUTES[("active", "relevant")] + 1,
    )
    assert result == "relevant"


def test_retry_does_not_advance_fixture_time():
    t1 = actor_resolution._apply_demotion_grace(
        current_tier="relevant",
        proposed_tier="dormant",
        last_interaction_minutes=100,
        now_minutes=200,
    )
    t2 = actor_resolution._apply_demotion_grace(
        current_tier="relevant",
        proposed_tier="dormant",
        last_interaction_minutes=100,
        now_minutes=200,
    )
    assert t1 == t2