"""The scarcity roll must fit the world the story is set in.

Regression: a typed "regular world except I can read minds" story rolled
scarcity "ammo" and opened on a debt paid in bullets.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run_identity  # noqa: E402

TYPED_WORLD = "regular world except i can read peoples minds"
SEEDS = [f"seed-{n}" for n in range(300)]


def _rolled_axes(genre) -> set:
    return {
        run_identity.derive_run_identity(seed, {"genre": genre, "role": "local resident"})["scarcity_axis"]
        for seed in SEEDS
    }


@pytest.mark.parametrize("genre", [TYPED_WORLD, "Dinosaur Island Survival", "", None])
def test_typed_or_missing_world_rolls_only_universal_axes(genre):
    rolled = _rolled_axes(genre)
    assert rolled <= set(run_identity.UNIVERSAL_SCARCITY_AXES)
    assert len(rolled) >= 2
    assert not rolled & {"ammo", "fuel", "medicine"}


@pytest.mark.parametrize("genre", ["modern", "fantasy", "prehistoric survival", "detective", "horror"])
def test_catalog_worlds_without_guns_never_roll_ammo(genre):
    rolled = _rolled_axes(genre)
    assert "ammo" not in rolled
    assert rolled <= set(run_identity.SCARCITY_AXES)


@pytest.mark.parametrize("genre", ["post-apocalyptic", "war survival", "urban crime", "Post-Apocalyptic"])
def test_worlds_where_guns_belong_can_still_roll_ammo(genre):
    assert "ammo" in _rolled_axes(genre)


def test_every_rolled_identity_is_still_a_valid_closed_enum_identity():
    for genre in (TYPED_WORLD, "modern", "post-apocalyptic"):
        identity = run_identity.derive_run_identity("seed-1", {"genre": genre})
        assert run_identity.is_closed_enum_identity(identity)


def test_same_seed_and_setup_gives_the_same_axis():
    setup = {"genre": TYPED_WORLD, "role": "local resident"}
    first = run_identity.derive_run_identity("seed-7", setup)
    again = run_identity.derive_run_identity("seed-7", dict(setup))
    assert first["scarcity_axis"] == again["scarcity_axis"]


def test_catalog_and_gun_genres_are_known_genres():
    assert run_identity.AMMO_SCARCITY_GENRES <= run_identity.CATALOG_GENRES
