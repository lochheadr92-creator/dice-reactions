"""Echo checks (2026-11-23): a standing limit retold in sentence after sentence, and copied passages.

Live playtest, canal story, premise "two banks cannot signal each other". Turns 1 to 4
restated the limit in 3 to 5 sentences each ("none of it became a word, a recognised
sign, or an answer either bank could trust"), and turn 6 repeated a 19 word passage
from turn 5. The engine's own instruction listed those words every turn.

These tests prove what the engine detects, asks for and accepts. They do not prove
what a model writes when it is given the new instruction.
"""

from __future__ import annotations

import json
import sys
import os
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import repetition_guard  # noqa: E402
import review_fixtures  # noqa: E402
import server  # noqa: E402
import world_constraints as wc  # noqa: E402
from test_security import mongo_env  # noqa: E402,F401
from test_world_constraints import (  # noqa: E402
    CANAL_PREMISE,
    TOWER_PREMISE,
    _deliver,
    _run_db,
    _tower_reply,
    _tower_session,
)

_FIXTURE = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "echo_playtest_2026_11_23.json").read_text(encoding="utf-8")
)
CANAL = wc.extract([CANAL_PREMISE])[0]
TOWER = wc.extract([TOWER_PREMISE])[0]
ACTIVE = [{"id": "c1", "status": "active"}]
ACTION = "Watch the north ridge."

ECHO = [
    "The north tower stood dark across the valley and no word came from it.",
    "Nothing you did would make a signal they could understand.",
    "You still could not make an answer out of the dark, and the captain waited.",
]
CLEAN = [
    "The oil store was nearly dry, and the south wall held the night's cold.",
    "The captain's door stayed shut while the arrows were counted below.",
]
COPIED = (
    "A lantern swung in a slow arc three times and then once more while pale dust lifted off the open sack."
)


def _turns(story):
    return _FIXTURE["stories"][story]


def _text(paragraphs):
    return "\n".join(paragraphs)


# --- the engine instruction no longer supplies the words ----------------------


def test_directive_states_the_rule_once_and_hands_over_no_phrase_list():
    text = wc.build_directive([CANAL], wc.status_rows([CANAL], None), None, has_player_action=True)
    assert "No meaning passes" in text
    for phrase in ("recognised sign", "words made out", "no answer, no agreement"):
        assert phrase not in text
    assert "at most one sentence a turn" in text
    assert "do not list what fails to arrive" in text


def test_directive_still_treats_other_limits_as_before():
    bridge = wc.extract(["The old bridge can no longer carry carts."])[0]
    text = wc.build_directive([bridge], wc.status_rows([bridge], None), None, has_player_action=True)
    assert "Nothing in this turn shows it undone or worked around." in text
    assert "No meaning passes" not in text


# --- restating the limit, on the recorded turns --------------------------------


@pytest.mark.parametrize("number", [1, 2, 3, 4])
def test_recorded_canal_turns_that_restate_the_limit_are_reported(number):
    reason = wc.restatement_reason(_turns("canal")[number - 1], [CANAL], ACTIVE, is_opening=number == 1)
    assert "restates a standing limit" in reason
    assert len(reason) <= 200  # the "fresh" retry style cuts the reason at 200 characters


@pytest.mark.parametrize("number", [5, 6])
def test_recorded_canal_turns_that_mention_it_once_or_not_at_all_pass(number):
    assert wc.restatement_reason(_turns("canal")[number - 1], [CANAL], ACTIVE, is_opening=False) == ""


@pytest.mark.parametrize("story", ["harbor", "guided"])
def test_stories_without_a_limit_are_never_reported(story):
    for number, paragraphs in enumerate(_turns(story), start=1):
        assert wc.restating_sentences(paragraphs, CANAL) == [], (story, number)
        assert wc.restatement_reason(paragraphs, [CANAL], ACTIVE, is_opening=number == 1) == ""


def test_the_opening_may_establish_the_limit_in_two_sentences():
    opening = review_fixtures.turn("canal", 1)["paragraphs"]
    assert len(wc.restating_sentences(opening, CANAL)) == 2
    assert wc.restatement_reason(opening, [CANAL], ACTIVE, is_opening=True) == ""
    assert wc.restatement_reason(opening, [CANAL], ACTIVE, is_opening=False) != ""


@pytest.mark.parametrize("number", [2, 3])
def test_one_mention_in_the_earlier_review_story_is_fine(number):
    paragraphs = review_fixtures.turn("canal", number)["paragraphs"]
    assert wc.restatement_reason(paragraphs, [CANAL], ACTIVE, is_opening=False) == ""


def test_a_lifted_or_lifting_constraint_is_not_policed():
    paragraphs = _turns("canal")[1]
    lifted = [{"id": "c1", "status": "lifted"}]
    assert wc.restatement_reason(paragraphs, [CANAL], lifted, is_opening=False) == ""
    assert wc.restatement_reason(paragraphs, [CANAL], ACTIVE, lifting_now=["c1"], is_opening=False) == ""


def test_only_communication_limits_are_checked():
    bridge = wc.extract(["The old bridge can no longer carry carts."])[0]
    assert bridge["kind"] != "communication"
    assert wc.restating_sentences(_turns("canal")[1], bridge) == []


def test_the_tower_fixture_restates_in_other_words():
    assert len(wc.restating_sentences(ECHO, TOWER)) == 3
    assert len(wc.restating_sentences([ECHO[0], CLEAN[1]], TOWER)) == 1
    assert wc.restating_sentences(CLEAN, TOWER) == []


# --- copying a recent turn ------------------------------------------------------


def test_a_passage_copied_from_a_recent_turn_is_reported():
    turns = _turns("canal")
    reason = repetition_guard.copied_passage_reason([_text(turns[4])], turns[5])
    assert "recent turn" in reason and "miller" in reason
    assert len(reason) <= 200


def test_no_other_recorded_turn_copies_a_recent_one():
    flagged = []
    for story, turns in _FIXTURE["stories"].items():
        for index, paragraphs in enumerate(turns):
            recent = [_text(t) for t in turns[max(0, index - 3):index]]
            if repetition_guard.copied_passage_reason(recent, paragraphs):
                flagged.append((story, index + 1))
    assert flagged == [("canal", 6)]


def test_a_stable_description_repeated_across_turns_is_not_a_copy():
    # Turns 3, 4 and 5 all say "the woman at the grey horse's head": 8 words, below the limit.
    turns = _turns("canal")
    assert "woman at the grey horse" in _text(turns[2]) and "woman at the grey horse" in _text(turns[3])
    assert repetition_guard.copied_passage_reason([_text(turns[2])], turns[3]) == ""


def test_the_reason_stays_whole_inside_the_200_characters_the_fresh_retry_style_allows():
    long_words = ["unforgettable", "astonishingly", "incomprehensible", "characteristically", "disproportionately"] * 4
    passage = " ".join(long_words)
    reason = repetition_guard.copied_passage_reason([passage], [passage])
    assert reason.endswith("Write what is new this turn instead.")
    assert len(reason) <= 200, len(reason)


def test_empty_or_short_history_never_reports():
    assert repetition_guard.copied_passage_reason([], ["Anything at all."]) == ""
    assert repetition_guard.copied_passage_reason(["one two three"], ["one two three"]) == ""
    assert repetition_guard.copied_passage_reason([""], [""]) == ""


# --- what the engine does with an echo ------------------------------------------


def test_echo_is_a_soft_failure_so_it_can_never_cause_a_fallback_turn():
    assert server._validation_failure_is_hard("echo", "any reason") is False
    assert server._validation_failure_is_hard("coherence", "standing constraint c1 is still active") is True


@pytest.mark.parametrize("style", ["show_rejected", "fresh"])
def test_a_turn_that_restates_the_limit_is_asked_to_rewrite_once(monkeypatch, style):
    # "fresh" is what backend/.env sets: the model is shown only a 200 character reason.
    monkeypatch.setattr(server, "VALIDATION_RETRY_STYLE", style)
    replies = [_tower_reply(ECHO), _tower_reply(CLEAN)]
    parsed, meta, calls = _deliver(monkeypatch, _tower_session(), replies, ACTION)
    assert calls["n"] == 2
    assert meta["validation_retried"] is True and meta["validation_retry_kind"] == "echo"
    assert "restates a standing limit" in meta["validation_first_fail"]
    assert meta.get("validation_hard_fallback") is not True
    assert "no word came" not in " ".join(parsed.paragraphs)
    retry_text = "\n".join(str(m["content"]) for m in calls["messages"][1])
    assert "restates a standing limit" in retry_text  # the model is told what to change


def test_a_turn_that_still_restates_after_the_retry_is_kept_not_replaced(monkeypatch):
    parsed, meta, calls = _deliver(monkeypatch, _tower_session(), [_tower_reply(ECHO)], ACTION)
    assert calls["n"] == 2  # the one existing retry, nothing more
    assert meta.get("validation_hard_fallback") is not True
    assert meta.get("validation_second_fail")
    assert "no word came" in " ".join(parsed.paragraphs)  # the model's own prose, not the engine fallback
    assert parsed.rolling_state["world_constraints"] == [{"id": "c1", "status": "active"}]


def test_one_sentence_about_the_limit_is_fine(monkeypatch):
    parsed, meta, calls = _deliver(monkeypatch, _tower_session(), [_tower_reply([ECHO[0], CLEAN[1]])], ACTION)
    assert calls["n"] == 1 and meta.get("validation_retried") is not True


def test_the_opening_check_allows_two_sentences_and_a_later_turn_does_not():
    parsed = server.parse_turn(_tower_reply([ECHO[0], ECHO[1], CLEAN[1]]))
    opening = _tower_session(turn_count=0)
    ok, reason, kind = server._validate_turn(parsed, opening, None, early_game_stage=None)
    assert (ok, kind) == (True, "ok"), reason
    ok, reason, kind = server._validate_turn(parsed, _tower_session(), ACTION, early_game_stage=None)
    assert (ok, kind) == (False, "echo") and "restates a standing limit" in reason


def test_a_broken_limit_outranks_an_echo():
    reply = _tower_reply(["The north watchtower flashes the agreed pattern.", *ECHO])
    ok, reason, kind = server._validate_turn(server.parse_turn(reply), _tower_session(), ACTION, early_game_stage=None)
    assert (ok, kind) == (False, "coherence") and "standing constraint c1" in reason


# --- copied passages need the stored turns -----------------------------------------


def test_recent_narratives_are_read_from_stored_turns_newest_first_at_most_three():
    sid = str(uuid.uuid4())

    async def go():
        docs = [
            {"id": str(uuid.uuid4()), "session_id": sid, "turn_number": n, "narrative": f"raw {n}"}
            for n in range(1, 6)
        ]
        docs[4]["canonical_narrative"] = "canonical 5"
        await server.db.turns.insert_many(docs)
        try:
            return await server._recent_narratives(sid, 3)
        finally:
            await server.db.turns.delete_many({"session_id": sid})

    assert _run_db(go()) == ["canonical 5", "raw 4", "raw 3"]
    assert _run_db(server._recent_narratives(sid, 3)) == []


def test_a_reply_that_copies_a_recent_turn_is_asked_to_rewrite(monkeypatch):
    sid = str(uuid.uuid4())

    async def seed():
        await server.db.turns.insert_one(
            {
                "id": str(uuid.uuid4()),
                "session_id": sid,
                "turn_number": 3,
                "narrative": f"The wall was cold. {COPIED} Then it was quiet.",
            }
        )

    async def clear():
        await server.db.turns.delete_many({"session_id": sid})

    session = dict(_tower_session(), id=sid)
    _run_db(seed())
    try:
        replies = [_tower_reply([f"The oil store was nearly dry. {COPIED}", CLEAN[1]]), _tower_reply(CLEAN)]
        parsed, meta, calls = _deliver(monkeypatch, session, replies, ACTION)
    finally:
        _run_db(clear())
    assert calls["n"] == 2
    assert meta["validation_retry_kind"] == "echo" and "recent turn" in meta["validation_first_fail"]
    assert COPIED not in " ".join(parsed.paragraphs)
