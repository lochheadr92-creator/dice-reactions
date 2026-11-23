"""Finding 9 (review 2, 2026-11-23): a limit the player wrote must hold until the player ends it.

Canal story premise: "two banks cannot signal each other". Recorded turns 3, 5,
6 and 7 let a recognised lamp sign and a shouted exchange cross the canal with
no player action that built a signal.

The recorded replies are replayed through the real acceptance path. These tests
prove what the engine accepts, stores and sends. They do not prove what a model
will write when it is given the new instruction.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import creation_contract  # noqa: E402
import gateway  # noqa: E402
import server  # noqa: E402
import world_constraints as wc  # noqa: E402
import review_fixtures  # noqa: E402
from test_security import _device_headers, client, mongo_env  # noqa: E402,F401

CANAL_PREMISE = review_fixtures.story("canal")["session"]["custom_world_setup"]["premise"]
TOWER_PREMISE = (
    "A border war in the hills. The two watchtowers can no longer send word to each other "
    "since the beacon oil ran out."
)
LIFT = '<rolling_state>{"constraint_lifted":[{"id":"c1","how":"%s"}],'


def _run_db(coro):
    async def wrapper():
        db_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        original = server.db
        server.db = db_client[os.environ["DB_NAME"]]
        try:
            return await coro
        finally:
            server.db = original
            db_client.close()

    return asyncio.run(wrapper())


def _deliver(monkeypatch, session, replies, action):
    calls = {"n": 0, "messages": []}

    async def scripted(**kwargs):
        calls["messages"].append(kwargs["messages"])
        reply = replies[min(calls["n"], len(replies) - 1)]
        calls["n"] += 1
        return {"content": reply, "model_used": "test", "model_requested": "test",
                "telemetry": {}, "fallback_events": [], "attempts_per_model": {}}

    monkeypatch.setattr(gateway, "invoke_llm", scripted)
    user_text = f"Player action: {action}" if action else "Begin."
    parsed, _raw, meta = _run_db(server._generate_validated_turn(session, user_text, player_action=action))
    assert "retry_exception" not in meta, meta.get("retry_exception")
    return parsed, meta, calls


def _with_lift(raw: str, how: str) -> str:
    head, rest = raw.split("<rolling_state>", 1)
    body = rest.lstrip()
    assert body.startswith("{")
    return head + (LIFT % how) + body[1:]


def _tower_session(turn_count=3, rolling=None):
    return {
        "id": f"tower-{turn_count}", "turn_count": turn_count, "mode": "advanced", "prose_mode": "standard",
        "genre": "hill war", "role": "signaller", "custom_world_setup": {"creationFlow": "advanced", "premise": TOWER_PREMISE},
        "rolling_state": rolling or {"scene": "south watchtower"},
    }


def _tower_reply(paragraphs, lift=None):
    rolling = '{"constraint_lifted":[{"id":"c1","how":"%s"}]}' % lift if lift else "{}"
    return (
        f"<rolling_state>{rolling}</rolling_state>\n"
        f"<narrative>{chr(10).join(paragraphs)}</narrative>\n"
        "<choices>\nA. Climb to the roof\nB. Check the oil store\nC. Wake the captain\nD. Count the arrows\n</choices>\n"
        "<state>\nHealth: stable\nPressure: steady\nPosition: south watchtower\n</state>\n"
        "<ledger>\nCarried: flint\n</ledger>\n"
    )


# --- what counts as a constraint ---------------------------------------------


def test_the_premise_limit_is_read_as_a_standing_constraint():
    rows = wc.extract([CANAL_PREMISE])
    assert [(r["id"], r["kind"]) for r in rows] == [("c1", "communication")]
    assert "two banks cannot signal each other" in rows[0]["text"]
    # The request to the narrator in the same premise is not a fact of the world.
    assert "teacup" not in rows[0]["text"]
    assert wc.extract(["A quiet harbour town. Each tide erases one name."]) == []
    tower = wc.extract([TOWER_PREMISE])
    assert tower[0]["kind"] == "communication" and wc.parties(tower[0]["text"]) == ["watchtower"]


# --- carried forward, as engine state ----------------------------------------


@pytest.mark.parametrize("number", [1, 2, 4])
def test_constraint_is_restated_every_turn_without_player_text_in_the_instruction(monkeypatch, number):
    recorded = review_fixtures.turn("canal", number)
    session = review_fixtures.session_after("canal", number - 1) if number > 1 else dict(
        review_fixtures.story("canal")["session"], turn_count=0
    )
    _parsed, _meta, calls = _deliver(monkeypatch, session, [recorded["raw"]], recorded.get("player_action"))
    messages = calls["messages"][0]
    directive = next(m for m in messages if "[STANDING CONSTRAINTS" in str(m["content"]))
    assert directive["role"] == "system"
    assert "c1 (player_story_data.standing_constraints.c1): ACTIVE" in directive["content"]
    assert "canal" not in directive["content"] and "banks" not in directive["content"]
    assert "No meaning passes" in directive["content"]
    data_message = messages[-1]
    assert data_message["role"] == "user"
    block = data_message["content"].split(creation_contract.PLAYER_DATA_OPEN)[1]
    assert "two banks cannot signal each other" in block
    if number == 1:
        assert "It cannot end in the opening" in directive["content"]
    else:
        assert "Only this turn's player action can" in directive["content"]


# --- recorded turns ----------------------------------------------------------


@pytest.mark.parametrize("number", [1, 2, 4])
def test_a_light_seen_across_the_water_with_no_meaning_is_allowed(monkeypatch, number):
    recorded = review_fixtures.turn("canal", number)
    session = review_fixtures.session_after("canal", number - 1) if number > 1 else dict(
        review_fixtures.story("canal")["session"], turn_count=0
    )
    parsed, meta, calls = _deliver(monkeypatch, session, [recorded["raw"]], recorded.get("player_action"))
    assert meta.get("validation_hard_fallback") is not True, meta
    assert calls["n"] == 1
    assert "lantern" in " ".join(parsed.paragraphs)
    assert parsed.rolling_state["world_constraints"] == [{"id": "c1", "status": "active"}]


@pytest.mark.parametrize("number,phrase", [(3, "old wait-sign"), (5, "a woman shouts so the landing can hear"), (6, "a woman calls so the landing can hear")])
def test_recorded_sign_or_shouted_exchange_is_not_delivered(monkeypatch, number, phrase):
    recorded = review_fixtures.turn("canal", number)
    assert phrase in recorded["narrative"]  # what the player was shown on 23 November
    session = review_fixtures.session_after("canal", number - 1)
    parsed, meta, calls = _deliver(monkeypatch, session, [recorded["raw"]], recorded["player_action"])
    assert "standing constraint c1 is still active" in str(meta.get("validation_first_fail"))
    assert calls["n"] == 2  # the one existing retry, nothing more
    assert meta.get("validation_hard_fallback") is True
    assert phrase not in " ".join(parsed.paragraphs)
    assert parsed.rolling_state["world_constraints"] == [{"id": "c1", "status": "active"}]


def test_incidental_prose_cannot_lift_the_constraint_even_when_the_model_claims_a_lift(monkeypatch):
    # Opening: there is no player action, so a claimed lift does not count.
    recorded = review_fixtures.turn("canal", 1)
    session = dict(review_fixtures.story("canal")["session"], turn_count=0)
    raw = _with_lift(recorded["raw"], "the east bank understood the lantern")
    parsed, meta, _calls = _deliver(monkeypatch, session, [raw], None)
    assert parsed.rolling_state["world_constraints"] == [{"id": "c1", "status": "active"}]
    assert "constraint_lifted" not in parsed.rolling_state
    assert "constraint_lift_refused:c1" in meta["delivery_guards"]


def test_a_player_action_that_builds_a_signal_lifts_it_and_later_turns_remember_how(monkeypatch):
    recorded = review_fixtures.turn("canal", 7)
    action = recorded["player_action"]
    assert action.startswith("Lash your short spare line to the cut end and raise the joined rope")
    session = review_fixtures.session_after("canal", 6)

    # Without a recorded lift, the same reply is refused: "Both banks heard her."
    _parsed, meta, _ = _deliver(monkeypatch, dict(session), [recorded["raw"]], action)
    assert meta.get("validation_hard_fallback") is True

    how = "joined rope raised on the bell post where the east lamp reads it"
    parsed, meta, _ = _deliver(monkeypatch, dict(session), [_with_lift(recorded["raw"], how)], action)
    assert meta.get("validation_hard_fallback") is not True, meta
    assert "Both banks heard her" in " ".join(parsed.paragraphs)
    row = parsed.rolling_state["world_constraints"][0]
    assert row["status"] == "lifted" and row["lifted_turn"] == 7
    assert row["how"] == how and row["player_action"].startswith("Lash your short spare line")
    assert "constraint_lifted:c1" in meta["delivery_guards"]

    # Next turn: the engine says it is lifted and how. An exchange across the water is now accepted.
    after = dict(session, turn_count=7, rolling_state=parsed.rolling_state)
    reply = (
        "<rolling_state>{}</rolling_state>\n"
        "<narrative>You dip the joined rope twice. Across the canal the east lamp answers, and both banks heard the count.</narrative>\n"
        "<choices>\nA. Send for the grain boat\nB. Tie the rope off\nC. Face the searcher\nD. Thank Ned\n</choices>\n"
        "<state>\nHealth: stable\nPressure: steady\nPosition: west landing\n</state>\n"
        "<ledger>\nCarried: fog whistle\n</ledger>\n"
    )
    later, later_meta, calls = _deliver(monkeypatch, after, [reply], "Dip the rope twice to ask for the grain boat.")
    assert later_meta.get("validation_hard_fallback") is not True, later_meta
    text = "\n".join(str(m["content"]) for m in calls["messages"][0])
    assert "c1 (player_story_data.standing_constraints.c1): LIFTED by the player on turn 7" in text
    assert how.replace(" ", "") in text.replace(" ", "").replace("\n", "")
    assert later.rolling_state["world_constraints"][0]["status"] == "lifted"


# --- a second setting, other words -------------------------------------------


def test_second_setting_unintelligible_light_is_allowed(monkeypatch):
    reply = _tower_reply(["A fire shows on the north watchtower.", "Nobody here can tell what it means."])
    parsed, meta, calls = _deliver(monkeypatch, _tower_session(), [reply], "Watch the north ridge.")
    assert meta.get("validation_hard_fallback") is not True, meta
    assert calls["n"] == 1


def test_second_setting_recognised_pattern_is_refused(monkeypatch):
    reply = _tower_reply(["The north watchtower flashes the agreed pattern.", "The captain reads it and nods."])
    parsed, meta, calls = _deliver(monkeypatch, _tower_session(), [reply], "Watch the north ridge.")
    assert meta.get("validation_hard_fallback") is True
    assert "agreed pattern" not in " ".join(parsed.paragraphs)
    assert calls["n"] == 2


def test_second_setting_player_built_means_is_accepted_and_remembered(monkeypatch):
    reply = _tower_reply(
        ["You angle the polished shield at the sun.", "The north watchtower answers with three flashes, and its captain understood the count."],
        lift="polished shield flashed in the sun, three flashes for danger",
    )
    parsed, meta, _ = _deliver(monkeypatch, _tower_session(), [reply], "Polish the shield and flash the sun at the north tower.")
    assert meta.get("validation_hard_fallback") is not True, meta
    row = parsed.rolling_state["world_constraints"][0]
    assert row["status"] == "lifted" and "polished shield" in row["how"]


def test_a_story_without_such_a_premise_is_untouched(monkeypatch):
    session = {"id": "plain", "turn_count": 12, "mode": "advanced", "prose_mode": "standard"}
    reply = _tower_reply(["Across the yard a guard calls the old signal.", "The gate answers."])
    parsed, meta, calls = _deliver(monkeypatch, session, [reply], "Walk on.")
    assert meta.get("validation_hard_fallback") is not True
    assert calls["n"] == 1 and "world_constraints" not in (parsed.rolling_state or {})
