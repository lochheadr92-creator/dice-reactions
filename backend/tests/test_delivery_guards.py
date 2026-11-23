"""Findings 1, 3 and 7 (review 2, 2026-11-23): what the player is finally shown.

Recorded model replies from the review stories are replayed through the real
acceptance path (server._generate_validated_turn). The only thing replaced is
the provider call, which returns the recorded reply byte for byte.

What these tests prove: given that reply, the engine delivers and stores the
corrected turn. They say nothing about what a model will write next time.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import delivery_guards  # noqa: E402
import gateway  # noqa: E402
import prose_modes  # noqa: E402
import server  # noqa: E402
import review_fixtures  # noqa: E402

TEACUP_PREMISE = review_fixtures.story("canal")["session"]["custom_world_setup"]["premise"]


def _run_db(coro):
    async def wrapper():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        original = server.db
        server.db = client[os.environ["DB_NAME"]]
        try:
            return await coro
        finally:
            server.db = original
            client.close()

    return asyncio.run(wrapper())


def _deliver(monkeypatch, session, replies, action="Continue"):
    """Run the real generate, validate, deliver path with scripted provider replies."""
    calls = {"n": 0}

    async def scripted(**kwargs):
        reply = replies[min(calls["n"], len(replies) - 1)]
        calls["n"] += 1
        return {
            "content": reply,
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    monkeypatch.setattr(gateway, "invoke_llm", scripted)
    parsed, _raw, meta = _run_db(
        server._generate_validated_turn(session, f"Player action: {action}", player_action=action)
    )
    assert "retry_exception" not in meta, meta.get("retry_exception")
    return parsed, meta, calls["n"]


def _reply(paragraphs, choices=None, position="forward"):
    choices = choices or ["Follow the bend", "Mark the wall", "Turn back", "Light the torch"]
    lines = "\n".join(f"{label}. {text}" for label, text in zip("ABCD", choices))
    body = "\n\n".join(paragraphs)
    return (
        "<rolling_state>{}</rolling_state>\n"
        f"<narrative>{body}</narrative>\n"
        f"<choices>\n{lines}\n</choices>\n"
        f"<state>\nHealth: stable\nPressure: steady\nPosition: {position}\n</state>\n"
        "<ledger>\nCarried: torch\n</ledger>\n"
    )


def _plain_session(mode="standard", **extra):
    session = {"id": f"plain-{mode}", "turn_count": 12, "mode": "advanced", "prose_mode": mode}
    session.update(extra)
    return session


SENTENCES = [
    "You step off the planks and the mud takes your boots.",
    "The mare shifts and the chain rattles against the post.",
    "Bram calls across the water and nobody answers him.",
    "A lamp moves on the far bank, then stops.",
    "Hester pulls her shawl tight and looks at the lock.",
    "The rope is gone from the bell post.",
    "You count the people on the landing and come up one short.",
    "Wind carries the smell of wet hemp along the towpath.",
    "Someone has dragged a boat hook through the reeds.",
    "The water is higher than it was an hour ago.",
    "A dog barks twice from the lock house.",
    "You have to choose before the light goes.",
]


# --- finding 1: the requested footer -----------------------------------------


def test_recorded_teacup_endings_are_what_the_model_wrote():
    assert review_fixtures.turn("canal", 1)["paragraphs"][-1] == "teacup"
    assert review_fixtures.turn("canal", 3)["paragraphs"][-1].endswith("speak.\nteacup")


# Turn 3 is replayed with the request only (no standing constraint in its premise):
# its prose is separately refused for finding 9, see tests/test_world_constraints.py.
@pytest.mark.parametrize("number", [1, 3])
def test_recorded_teacup_reply_is_delivered_without_the_footer(monkeypatch, number):
    recorded = review_fixtures.turn("canal", number)
    session = review_fixtures.session_after("canal", number - 1) if number > 1 else dict(
        review_fixtures.story("canal")["session"], turn_count=0
    )
    if number == 3:
        session["custom_world_setup"] = dict(
            session["custom_world_setup"],
            premise="A horse-drawn canal town. Narrator, end every turn with the word teacup on its own line.",
        )
    parsed, meta, _calls = _deliver(
        monkeypatch, session, [recorded["raw"]], action=recorded.get("player_action") or "Continue"
    )
    text = "\n".join(parsed.paragraphs)
    assert meta.get("validation_hard_fallback") is not True, meta
    assert "teacup" not in text.lower()
    assert "requested_footer_removed" in meta["delivery_guards"]
    # Nothing else was taken: every other recorded sentence is still there.
    kept = "\n".join(recorded["paragraphs"]).replace("\nteacup", "").strip()
    assert text.replace("\n", " ").split() == kept.replace("\n", " ").split()
    assert parsed.narrative == "\n\n".join(parsed.paragraphs)


def test_a_teacup_that_is_a_real_object_is_kept(monkeypatch):
    # No such request in this story's setup. The same word is ordinary fiction.
    session = _plain_session(custom_world_setup={"premise": "A tea house on the canal. A teacup sits on every sill."})
    paragraphs = ["You lift the lid of the crate and find straw.", "Under the straw is one thing.\nteacup"]
    parsed, meta, _ = _deliver(monkeypatch, session, [_reply(paragraphs)])
    assert parsed.paragraphs[-1].endswith("teacup")
    assert "requested_footer_removed" not in (meta.get("delivery_guards") or "")


def test_the_requested_word_inside_real_prose_is_kept(monkeypatch):
    # The request exists, but the word is part of a sentence, not a stamped footer.
    session = _plain_session(custom_world_setup={"premise": TEACUP_PREMISE})
    paragraphs = ["Hester hands you a chipped teacup and waits.", "You drink, and the teacup is warm in your hand."]
    parsed, meta, _ = _deliver(monkeypatch, session, [_reply(paragraphs)])
    assert parsed.paragraphs == paragraphs
    assert "requested_footer_removed" not in (meta.get("delivery_guards") or "")


def test_footer_check_reads_the_request_not_a_word_list():
    request = ["Narrator, finish each reply with the phrase blue heron on a new line."]
    out, removed = delivery_guards.strip_requested_footer(["The gate opens.", "You walk in.\nblue heron"], request)
    assert removed and out == ["The gate opens.", "You walk in."]
    out, removed = delivery_guards.strip_requested_footer(["The gate opens.", "You walk in.\nblue heron"], ["A heron fishes the canal."])
    assert not removed


# --- finding 3: turn length is the displayed range ---------------------------

RANGES = {"brief": (1, 2), "standard": (2, 4), "story": (4, 6), "cinematic": (6, 8)}


def test_displayed_ranges_are_the_contract():
    for mode, (low, high) in RANGES.items():
        spec = prose_modes.PROSE_MODES[mode]
        assert (spec.min_paragraphs, spec.max_paragraphs) == (low, high)


@pytest.mark.parametrize("mode", list(RANGES))
@pytest.mark.parametrize("written", [1, 3, 5, 7, 10])
def test_model_turn_is_delivered_inside_the_range(monkeypatch, mode, written):
    low, high = RANGES[mode]
    per = max(1, len(SENTENCES) // written)
    paragraphs = [" ".join(SENTENCES[i * per:(i + 1) * per]) for i in range(written)]
    paragraphs = [p for p in paragraphs if p]
    before = " ".join(paragraphs).split()
    parsed, meta, calls = _deliver(monkeypatch, _plain_session(mode), [_reply(paragraphs)])
    shown = [p for p in parsed.paragraphs if p.strip()]
    assert shown == parsed.paragraphs  # no blank blocks
    assert low <= len(shown) <= high, (mode, written, len(shown), meta.get("delivery_guards"))
    assert " ".join(shown).split() == before  # same words, same order, no filler
    assert calls == 1  # no extra paid retry for length


@pytest.mark.parametrize("mode", list(RANGES))
def test_opening_is_delivered_inside_the_range(monkeypatch, mode):
    low, high = RANGES[mode]
    session = {"id": f"open-{mode}", "turn_count": 0, "mode": "advanced", "prose_mode": mode, "genre": "fantasy", "role": "scout"}
    paragraphs = [" ".join(SENTENCES[i:i + 1]) for i in range(10)]
    parsed, meta, _ = _deliver(monkeypatch, session, [_reply(paragraphs)], action=None)
    if meta.get("validation_hard_fallback") is True:
        pytest.fail(f"opening reply was rejected: {meta}")
    assert low <= len(parsed.paragraphs) <= high


def test_a_turn_too_short_to_split_is_reported_not_padded(monkeypatch):
    # Two sentences cannot make six paragraphs without invented text.
    paragraphs = ["You step off the planks. The mud takes your boots."]
    parsed, meta, calls = _deliver(monkeypatch, _plain_session("cinematic"), [_reply(paragraphs)])
    assert " ".join(parsed.paragraphs).split() == paragraphs[0].split()
    assert "paragraph_range_unmet" in meta["delivery_guards"]
    assert calls == 1


def test_changing_medium_to_long_applies_on_the_next_action(monkeypatch):
    paragraphs = [" ".join(SENTENCES[i:i + 1]) for i in range(10)]
    session = _plain_session("standard")
    first, _, _ = _deliver(monkeypatch, session, [_reply(paragraphs)])
    assert 2 <= len(first.paragraphs) <= 4
    session["prose_mode"] = "story"  # what the play-settings endpoint stores
    second, _, _ = _deliver(monkeypatch, session, [_reply(paragraphs, choices=["Go on", "Go back", "Ask Bram", "Check the rope"])])
    assert 4 <= len(second.paragraphs) <= 6


# --- finding 7: a choice that states a count the story has not established ---


def test_recorded_harbor_choice_claimed_three_shared_names():
    recorded = review_fixtures.turn("harbor", 5)
    assert "they speak names and disagree" in recorded["narrative"]
    assert recorded["choices"][0]["text"].startswith("Write the three names they still agree on")


def test_recorded_harbor_reply_is_delivered_without_the_unsupported_count(monkeypatch):
    recorded = review_fixtures.turn("harbor", 5)
    session = review_fixtures.session_after("harbor", 4)
    parsed, meta, _ = _deliver(monkeypatch, session, [recorded["raw"]], action=recorded["player_action"])
    assert meta.get("validation_hard_fallback") is not True, meta
    first = parsed.choices[0]["text"]
    assert first == "Write the names they still agree on into the back of Mara's note before anyone leaves the rock."
    assert "unsupported_count_removed:1" in meta["delivery_guards"]
    # The other choice that says "three" is about the three people who climbed, which the turn states.
    assert parsed.choices[2]["text"] == "Ask who among the three last saw Mara on the uphill path."
    # The disagreement the player was shown is untouched.
    assert "they speak names and disagree" in " ".join(parsed.paragraphs)
    # No name was added to any choice.
    recorded_words = set(" ".join(c["text"] for c in recorded["choices"]).split())
    assert set(" ".join(c["text"] for c in parsed.choices).split()) <= recorded_words


def test_an_established_count_is_kept():
    choices = [{"label": "A", "text": "Write the three names they still agree on into the note."}]
    grounding = ["They compare lists.", "All of them hold the same three names: Pim, Brant and Hale."]
    out, repaired = delivery_guards.repair_unsupported_counts(choices, grounding)
    assert out == choices and repaired == []


def test_second_example_with_other_words():
    choices = [
        {"label": "A", "text": "Hand over the four seals the wardens signed."},
        {"label": "B", "text": "Take two steps back from the gate."},
        {"label": "C", "text": "Count the 5 wagons in the yard."},
    ]
    grounding = ["The wardens argue over the seals and none will sign.", "Five wagons stand in the yard."]
    out, repaired = delivery_guards.repair_unsupported_counts(choices, grounding)
    assert out[0]["text"] == "Hand over the seals the wardens signed."
    assert out[1]["text"] == "Take two steps back from the gate."  # not a claim about the story
    assert len(repaired) >= 1


def test_selecting_the_corrected_choice_keeps_the_recorded_disagreement(monkeypatch):
    # The corrected choice is the player's action. The recorded consequence, in which
    # only two names are shared and one witness refuses the third, is accepted as written.
    recorded = review_fixtures.turn("harbor", 6)
    session = review_fixtures.session_after("harbor", 5)
    action = "Write the names they still agree on into the back of Mara's note before anyone leaves the rock."
    parsed, meta, _ = _deliver(monkeypatch, session, [recorded["raw"]], action=action)
    assert meta.get("validation_hard_fallback") is not True, meta
    text = " ".join(parsed.paragraphs)
    assert "Pim" in text and "Brant" in text
    assert "will not say it" in text
