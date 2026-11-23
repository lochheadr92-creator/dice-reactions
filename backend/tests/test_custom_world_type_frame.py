"""A world type the player typed must shape the world frame and the opening.

Regression: "Dinosaur Island Survival" typed into the Advanced builder fell back
to the Modern frame (era=contemporary; setting=grounded_present), so the opening
had no dinosaurs in it.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import creation_contract  # noqa: E402

CUSTOM_WORLD_TYPE = "Dinosaur Island Survival"
ADVANCED_SETUP = {"creationFlow": "advanced", "startingLocation": "remote_wilderness"}


def _contract(genre: str) -> dict:
    return creation_contract.build_creation_contract(
        genre=genre,
        role="traveller",
        custom_world_setup=dict(ADVANCED_SETUP),
    )


def test_custom_world_type_does_not_fall_back_to_modern_frame():
    frame = creation_contract.derive_world_frame(CUSTOM_WORLD_TYPE)
    assert frame["setting"] == CUSTOM_WORLD_TYPE
    assert frame["era"] != "contemporary"
    assert frame["technology"] != "contemporary"
    assert "grounded_present" not in frame.values()
    assert frame["player_authored"] is True


def test_custom_world_type_is_bounded():
    frame = creation_contract.derive_world_frame("x" * 500)
    assert len(frame["setting"]) <= creation_contract.MAX_ELEMENTS_LEN


def test_catalog_genres_keep_their_frames():
    assert creation_contract.derive_world_frame("modern")["setting"] == "grounded_present"
    assert creation_contract.derive_world_frame("Fantasy")["setting"] == "fantasy_realm"
    assert "player_authored" not in creation_contract.derive_world_frame("horror")


def test_missing_genre_still_uses_modern_frame():
    assert creation_contract.derive_world_frame(None)["setting"] == "grounded_present"
    assert creation_contract.derive_world_frame("  ")["setting"] == "grounded_present"


def test_opening_lines_require_the_custom_world_on_the_page():
    data: dict = {}
    lines = creation_contract.build_opening_setup_lines(_contract(CUSTOM_WORLD_TYPE), data)
    text = "\n".join(lines)
    # The typed world type is data; engine lines refer to it by key.
    ref = creation_contract.player_data_ref("world_type")
    assert data["world_type"] == CUSTOM_WORLD_TYPE
    assert CUSTOM_WORLD_TYPE not in text
    assert "contemporary" not in text
    assert "grounded_present" not in text
    assert any("must appear" in line and ref in line for line in lines)


def test_opening_lines_for_catalog_genre_have_no_custom_world_line():
    lines = creation_contract.build_opening_setup_lines(_contract("fantasy"))
    assert not any("must appear" in line for line in lines)


def test_later_turn_frame_keeps_the_custom_world_type():
    rolling = creation_contract.restore_creation_surfaces(
        {},
        {"genre": CUSTOM_WORLD_TYPE, "role": "traveller", "custom_world_setup": dict(ADVANCED_SETUP)},
    )
    assert rolling["world_frame"]["setting"] == CUSTOM_WORLD_TYPE
    assert rolling["world_frame"].get("era") != "contemporary"
