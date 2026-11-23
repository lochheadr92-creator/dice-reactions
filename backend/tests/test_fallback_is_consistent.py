"""Finding 2 (review 2, 2026-11-23): the fallback contradicted itself and cut a choice mid-word.

Guided story, turn 4 had established that Pell was on the bank and still around
the bend. The turn 5 fallback then printed "Pell not yet on the bank" and "Pell
is on the bank" together, showed the author-facing sentence "nothing new is
invented to escape it", and offered a choice ending "may take you f".
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gateway  # noqa: E402
import prose_modes  # noqa: E402
import server  # noqa: E402
import review_fixtures  # noqa: E402
from test_security import _device_headers, client, mongo_env  # noqa: E402,F401

ACTION = "Ask Sela, quietly, who put the chain up and whether the stamp is real."


def _run_db(coro):
    """Run against the guarded test database with a client bound to this loop."""

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


def _force_fallback(monkeypatch, session, action=ACTION, prose_mode="story"):
    """Drive the normal entry point with two structurally invalid model replies."""
    calls = {"n": 0}

    async def bad_invoke_llm(**kwargs):
        calls["n"] += 1
        return {
            "content": "no tags at all, so this reply cannot be parsed into a turn",
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    session.setdefault("prose_mode", prose_mode)
    monkeypatch.setattr(gateway, "invoke_llm", bad_invoke_llm)
    parsed, raw, meta = _run_db(
        server._generate_validated_turn(session, "Continue", player_action=action)
    )
    assert "retry_exception" not in meta, meta.get("retry_exception")
    return parsed, meta, calls["n"]


def _pell_session():
    return review_fixtures.session_after("guided", 4)


def test_recorded_turn_five_was_the_broken_fallback():
    recorded = review_fixtures.turn("guided", 5)
    text = " ".join(recorded["paragraphs"])
    assert "Pell not yet on the bank" in text and "Pell is on the bank" in text
    assert "nothing new is invented to escape it" in text
    assert recorded["choices"][-1]["text"].endswith("may take you f")


def test_fallback_agrees_with_the_last_established_position(monkeypatch):
    session = _pell_session()
    parsed, meta, calls = _force_fallback(monkeypatch, session)
    assert meta.get("validation_hard_fallback") is True
    text = " ".join(parsed.paragraphs)

    # One snapshot: the state strip the player was shown on turn 4, restated and stored unchanged.
    assert session["last_state"]["Position"] in text
    assert session["last_state"]["Pressure"] in text
    assert parsed.state["Position"] == session["last_state"]["Position"]
    assert parsed.state["Pressure"] == session["last_state"]["Pressure"]
    # The contradicting private note is gone, and so is the author-facing wording.
    assert "not yet on the bank" not in text
    assert "nothing new is invented" not in text
    assert "invented" not in text and "resolution" not in text
    # Sela was asked a question nobody answered. The fallback must not answer it.
    assert "Sela" not in text and "stamp is real" not in text
    # Retry budget unchanged: the first attempt and one retry, then the fallback.
    assert calls == 2


def test_fallback_choices_are_whole_grounded_and_give_a_way_forward(monkeypatch):
    session = _pell_session()
    parsed, _meta, _calls = _force_fallback(monkeypatch, session)
    texts = [c["text"] for c in parsed.choices]
    assert [c["label"] for c in parsed.choices] == ["A", "B", "C", "D"]
    assert len(set(texts)) == 4
    for text in texts:
        assert not text.endswith(" f")
        assert re.search(r"[a-z]{2,}$", text), text  # ends on a whole word
        assert "Pell is on the bank and the crowd may take you" not in text
    # Mara is with the player in the last shown state, so she may be asked.
    assert "Ask Mara what they make of this" in texts
    # A concrete way forward: retry the same intent another way.
    assert "Try what you just did again, a different way" in texts
    # Nobody the state does not place with the player is offered.
    assert not any("Pell" in t or "Sela" in t for t in texts)


@pytest.mark.parametrize("mode", ["brief", "standard", "story"])
def test_fallback_fits_the_turn_length(monkeypatch, mode):
    session = _pell_session()
    session["prose_mode"] = mode
    parsed, _meta, _calls = _force_fallback(monkeypatch, session, prose_mode=mode)
    expected = prose_modes.PROSE_MODES[mode]
    assert expected.min_paragraphs <= len(parsed.paragraphs) <= expected.max_paragraphs
    assert all(p.strip() for p in parsed.paragraphs)


def test_long_pressure_text_is_never_cut_inside_a_word(monkeypatch):
    session = _pell_session()
    long_pressure = "the grain guild clerk is counting heads at the chain and " * 8
    session["last_state"]["Pressure"] = long_pressure.strip()
    parsed, _meta, _calls = _force_fallback(monkeypatch, session)
    text = " ".join(parsed.paragraphs)
    shown = re.search(r"What presses on you has not changed either: (.*?)\.", text).group(1)
    assert len(shown) <= server.FALLBACK_FACT_MAX_CHARS
    assert long_pressure.startswith(shown)
    assert long_pressure[len(shown)] == " "  # the cut fell between words
    for choice in parsed.choices:
        assert len(choice["text"]) < 90


def test_sparse_state_still_gives_a_coherent_fallback(monkeypatch):
    session = {"id": "sparse", "turn_count": 2, "prose_mode": "standard", "role": "scout", "genre": "fantasy"}
    parsed, meta, _calls = _force_fallback(monkeypatch, session, prose_mode="standard")
    assert meta.get("validation_hard_fallback") is True
    text = " ".join(parsed.paragraphs)
    assert "Nothing is settled yet." in text
    assert "None" not in text and "{}" not in text and "  " not in text
    assert len(parsed.choices) == 4
    assert "Check what you are carrying for something you can use" in [c["text"] for c in parsed.choices]
    assert parsed.state["Position"]


def test_opening_fallback_has_no_retry_wording(monkeypatch):
    session = {"id": "open", "turn_count": 0, "prose_mode": "standard", "role": "scout", "genre": "fantasy"}
    parsed, _meta, _calls = _force_fallback(monkeypatch, session, action=None, prose_mode="standard")
    text = " ".join(parsed.paragraphs)
    assert "What you just tried" not in text
    assert "Wait a moment and watch what changes" in [c["text"] for c in parsed.choices]


def test_failed_generation_and_fallback_commit_exactly_one_turn(client, mongo_env, monkeypatch):
    """Through the real action route: two bad replies, one stored turn, same text delivered and stored."""
    owner = str(uuid.uuid4())
    sid = review_fixtures.seed_story(mongo_env, "guided", 4, owner)
    calls = {"n": 0}

    async def bad_invoke_llm(**kwargs):
        calls["n"] += 1
        return {
            "content": "no tags at all, so this reply cannot be parsed into a turn",
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    monkeypatch.setattr(gateway, "invoke_llm", bad_invoke_llm)
    response = client.post(
        "/api/story/action",
        headers=_device_headers(owner),
        json={"session_id": sid, "action_text": ACTION},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert calls["n"] == 2

    stored = list(mongo_env.turns.find({"session_id": sid, "turn_number": 5}))
    assert len(stored) == 1
    assert mongo_env.turns.count_documents({"session_id": sid}) == 3  # recorded 3 and 4, plus this one
    session = mongo_env.sessions.find_one({"id": sid})
    assert session["turn_count"] == 5

    turn = body.get("turn") or body
    delivered = " ".join(turn["paragraphs"])
    assert delivered == " ".join(stored[0]["paragraphs"])
    assert [c["text"] for c in turn["choices"]] == [c["text"] for c in stored[0]["choices"]]
    assert "still around the bend" in delivered
    assert "not yet on the bank" not in delivered
    assert stored[0]["state"]["Position"] == "on the gravel bar at a chained low ford, crowd in the shallows, Pell still around the bend"
    for choice in turn["choices"]:
        assert re.search(r"[a-z]{2,}$", choice["text"]), choice["text"]
