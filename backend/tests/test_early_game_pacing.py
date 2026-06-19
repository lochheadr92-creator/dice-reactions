"""
Early-Game Pacing Governor v1 — deterministic tests.

Covers stage mapping, directive routing, Stage-1 structural validation,
single-retry budgeting, leak safety, and non-regression of existing guards.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from starlette.testclient import TestClient

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import gateway  # noqa: E402
import hud  # noqa: E402
import pacing  # noqa: E402
import relationships  # noqa: E402
import server  # noqa: E402
from memory import enforce_context_budget  # noqa: E402
from security import ADMIN_API_KEY_HEADER, DEVICE_ID_HEADER  # noqa: E402

TEST_ADMIN_KEY = os.environ.get("ADMIN_API_KEY") or "test-admin-key-for-pacing-suite"
os.environ["ADMIN_API_KEY"] = TEST_ADMIN_KEY


class _Parsed:
    def __init__(
        self,
        narrative="Scene text.",
        paragraphs=None,
        choices=None,
        state=None,
        rolling_state=None,
        ledger=None,
    ):
        self.narrative = narrative
        self.paragraphs = paragraphs if paragraphs is not None else [narrative]
        self.choices = choices or [
            {"label": "A", "text": "Act"},
            {"label": "B", "text": "Wait"},
            {"label": "C", "text": "Look"},
            {"label": "D", "text": "Speak"},
        ]
        self.state = state or {}
        self.rolling_state = rolling_state
        self.ledger = ledger or {"Carried": "torch"}


def _opening_parsed(
    pressure: str = "Someone waits for an answer that will change everything",
    active_pressures=None,
    objectives=None,
    unresolved=None,
) -> _Parsed:
    if active_pressures is None:
        active_pressures = ["a favour is due before dusk"]
    if objectives is None:
        objectives = ["secure passage before the gate closes"]
    if unresolved is None:
        unresolved = []
    return _Parsed(
        state={"Health": "healthy", "Pressure": pressure},
        rolling_state={
            "scene": "a crowded market stall",
            "active_pressures": active_pressures,
            "objectives": objectives,
            "unresolved": unresolved,
        },
    )


def _run_db(coro):
    """Run async server code with a fresh Motor client (avoids closed-loop flakes)."""

    async def wrapper():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        orig = server.db
        server.db = client[os.environ["DB_NAME"]]
        try:
            return await coro
        finally:
            server.db = orig
            client.close()

    return asyncio.run(wrapper())


def _raw_from_parsed(parsed: _Parsed) -> str:
    choices = "\n".join(f"{c['label']}. {c['text']}" for c in parsed.choices)
    state = "\n".join(f"{k}: {v}" for k, v in parsed.state.items())
    return (
        f"<narrative>\n{parsed.narrative}\n</narrative>\n"
        f"<choices>\n{choices}\n</choices>\n"
        f"<state>\n{state}\n</state>\n"
        f"<ledger>\nCarried: torch\n</ledger>\n"
        f"<rolling_state>\n{json.dumps(parsed.rolling_state)}\n</rolling_state>\n"
    )


# ---------------------------------------------------------------------------
# Stage mapping (tests 1–5)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "turn_count,expected",
    [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 4),
        (4, None),
        (10, None),
    ],
)
def test_turn_count_maps_to_early_game_stage(turn_count, expected):
    assert pacing.get_early_game_stage(turn_count) == expected


# ---------------------------------------------------------------------------
# Directive content (tests 8–12, 24)
# ---------------------------------------------------------------------------
def test_stage_one_directive_allows_genesis_authoring():
    text = pacing.build_early_game_directive(1)
    assert "no prior Chronicle truth" in text
    assert "active_pressures" in text
    assert pacing.PACING_DIRECTIVE_MARKER in text


def test_stage_two_directive_forbids_unrelated_truth_invention():
    text = pacing.build_early_game_directive(2)
    assert "do not invent unrelated world truth" in text.lower()
    assert "prior rolling_state" in text.lower()


def test_stage_three_directive_surfaces_existing_engine_state():
    text = pacing.build_early_game_directive(3, {"active_pressures": ["dusk closing"]})
    assert "surface existing state" in text.lower() or "engine-authoritative" in text.lower()
    assert "active_pressures" in text


def test_stage_three_directive_does_not_claim_llm_creates_independent_world_action():
    text = pacing.build_early_game_directive(3)
    assert "do not author autonomous" in text.lower() or "do not invent" in text.lower()
    assert "acts independently" not in text.lower()


def test_stage_four_directive_derives_direction_from_established_state():
    text = pacing.build_early_game_directive(4)
    assert "established state" in text.lower()
    assert "objectives" in text


def test_turn_five_receives_no_pacing_directive():
    assert pacing.build_early_game_directive(None) == ""
    assert pacing.get_early_game_stage(4) is None


# ---------------------------------------------------------------------------
# Stage-1 structural validation (tests 13–23)
# ---------------------------------------------------------------------------
def test_rejects_missing_opening_pressure():
    parsed = _opening_parsed(pressure="")
    parsed.state.pop("Pressure", None)
    assert pacing.validate_opening_structure(parsed) == "missing Pressure in state"


def test_rejects_blank_opening_pressure():
    parsed = _opening_parsed(pressure="   ")
    assert pacing.validate_opening_structure(parsed) == "missing Pressure in state"


@pytest.mark.parametrize("placeholder", ["-", "—", "none", "nothing", "NONE", "Nothing"])
def test_rejects_placeholder_opening_pressure(placeholder):
    parsed = _opening_parsed(pressure=placeholder)
    reason = pacing.validate_opening_structure(parsed)
    assert reason and "placeholder" in reason


def test_rejects_missing_rolling_state_for_opening():
    parsed = _opening_parsed()
    parsed.rolling_state = None
    assert pacing.validate_opening_structure(parsed) == "missing rolling_state"


def test_rejects_missing_active_pressure_state():
    parsed = _opening_parsed(active_pressures=[])
    assert pacing.validate_opening_structure(parsed) == "missing active_pressures"


def test_rejects_missing_objectives_and_unresolved_stake():
    parsed = _opening_parsed(objectives=[], unresolved=[])
    assert pacing.validate_opening_structure(parsed) == "missing objectives and unresolved stake"


def test_accepts_opening_with_required_objective_field():
    parsed = _opening_parsed(objectives=["reach the safehouse"], unresolved=[])
    assert pacing.validate_opening_structure(parsed) is None


def test_accepts_opening_with_required_unresolved_stake():
    parsed = _opening_parsed(objectives=[], unresolved=["a debt comes due at sundown"])
    assert pacing.validate_opening_structure(parsed) is None


def test_accepts_opening_with_required_persistent_fields():
    parsed = _opening_parsed()
    assert pacing.validate_opening_structure(parsed) is None


def test_stage_two_not_rejected_by_stage_one_structural_validator():
    parsed = _Parsed(state={}, rolling_state={})
    assert pacing.validate_opening_structure(parsed) is not None
    _, _, kind = server._full_validate(parsed, {}, None, early_game_stage=2)
    assert kind != "pacing"


def test_stage_three_not_rejected_by_stage_one_structural_validator():
    parsed = _Parsed(state={}, rolling_state={})
    ok, _, kind = server._full_validate(parsed, {}, None, early_game_stage=3)
    assert kind != "pacing"


def test_stage_four_not_rejected_by_stage_one_structural_validator():
    parsed = _Parsed(state={}, rolling_state={})
    ok, _, kind = server._full_validate(parsed, {}, None, early_game_stage=4)
    assert kind != "pacing"


# ---------------------------------------------------------------------------
# Stage immutability + retry budgeting (tests 6–7, 25–27)
# ---------------------------------------------------------------------------
def test_stage_computed_once_and_reused_for_retry():
    captured_stages: List[Optional[int]] = []
    bad = _raw_from_parsed(_opening_parsed(pressure="none"))
    good = _raw_from_parsed(_opening_parsed())
    scripts = [bad, good]
    calls = {"n": 0}

    async def track_build(
        session,
        user_text,
        memory_depth,
        history_window_fallback,
        early_game_stage=None,
        secret_reveal_directive="",
    ):
        captured_stages.append(early_game_stage)
        return await original_build(
            session,
            user_text,
            memory_depth,
            history_window_fallback,
            early_game_stage=early_game_stage,
            secret_reveal_directive=secret_reveal_directive,
        )

    original_build = server._build_messages
    server._build_messages = track_build

    async def fake_chat(**kwargs):
        idx = min(calls["n"], len(scripts) - 1)
        calls["n"] += 1
        return {
            "content": scripts[idx],
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat
    session = {"id": str(uuid.uuid4()), "turn_count": 0, "mode": "advanced"}
    try:
        parsed, raw, meta = _run_db(
            server._generate_validated_turn(session, "[DEV_MODE: OFF]\n\nBegin")
        )
        assert parsed.state.get("Pressure")
        assert captured_stages == [1, 1]
        assert calls["n"] == 2
        assert meta.get("validation_retry_kind") == "pacing"
    finally:
        server._build_messages = original_build
        gateway.invoke_llm = original


def test_mutation_of_session_copy_between_attempts_does_not_change_retry_stage():
    stages_in_validate: List[Optional[int]] = []

    def track_validate(parsed, session, player_action, early_game_stage=None):
        stages_in_validate.append(early_game_stage)
        if len(stages_in_validate) == 1:
            session["turn_count"] = 99
        if early_game_stage == 1 and len(stages_in_validate) == 1:
            return False, "missing Pressure in state", "pacing"
        return True, "", "ok"

    original_validate = server._full_validate
    server._full_validate = track_validate

    calls = {"n": 0}
    content = _raw_from_parsed(_opening_parsed())

    async def fake_chat(**kwargs):
        calls["n"] += 1
        return {
            "content": content,
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat
    session = {"id": str(uuid.uuid4()), "turn_count": 0, "mode": "advanced"}
    try:
        _run_db(server._generate_validated_turn(session, "Begin"))
        assert stages_in_validate == [1, 1]
        assert calls["n"] == 2
    finally:
        server._full_validate = original_validate
        gateway.invoke_llm = original


def test_one_pacing_failure_triggers_at_most_one_retry():
    calls = {"n": 0}

    async def fake_chat(**kwargs):
        calls["n"] += 1
        parsed = _opening_parsed(pressure="none")
        return {
            "content": _raw_from_parsed(parsed),
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat
    session = {"id": str(uuid.uuid4()), "turn_count": 0, "mode": "advanced"}
    try:
        _run_db(server._generate_validated_turn(session, "[DEV_MODE: OFF]\n\nBegin"))
        assert calls["n"] == 2
    finally:
        gateway.invoke_llm = original


def test_pacing_failure_followed_by_contradiction_does_not_trigger_third_provider_call():
    prior = {
        "object_locations": [{"object": "iron key", "status": "destroyed"}],
        "deceased": ["Garrett"],
    }
    bad_opening = _raw_from_parsed(_opening_parsed(pressure="none"))
    contradicting = _raw_from_parsed(
        _Parsed(
            narrative="You pocket the iron key. Garrett waves you onward.",
            state={"Health": "healthy", "Pressure": "roof may fall"},
            rolling_state={
                "scene": "chamber",
                "active_pressures": ["roof stress"],
                "objectives": ["escape"],
                "object_locations": [{"object": "iron key", "status": "carried"}],
            },
        )
    )
    scripts = [bad_opening, contradicting]
    calls = {"n": 0}

    async def fake_chat(**kwargs):
        idx = min(calls["n"], len(scripts) - 1)
        calls["n"] += 1
        return {
            "content": scripts[idx],
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat
    session = {
        "id": str(uuid.uuid4()),
        "turn_count": 0,
        "mode": "advanced",
        "rolling_state": prior,
    }
    try:
        _run_db(server._generate_validated_turn(session, "[DEV_MODE: OFF]\n\nBegin"))
        assert calls["n"] == 2
    finally:
        gateway.invoke_llm = original


def test_same_stage_one_directive_in_initial_and_retry_message_construction():
    captured: List[List[Dict[str, str]]] = []

    async def fake_chat(**kwargs):
        captured.append(kwargs.get("messages") or [])
        parsed = _opening_parsed(pressure="none" if len(captured) == 1 else "roof groans")
        return {
            "content": _raw_from_parsed(parsed),
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat
    session = {"id": str(uuid.uuid4()), "turn_count": 0, "mode": "advanced"}
    try:
        _run_db(server._generate_validated_turn(session, "[DEV_MODE: OFF]\n\nBegin"))
        assert len(captured) == 2
        d1 = pacing.extract_directive_from_messages(captured[0])
        d2 = pacing.extract_directive_from_messages(captured[1])
        assert d1 and d2
        assert d1 == d2
        assert "genesis contract" in d1
    finally:
        gateway.invoke_llm = original


# ---------------------------------------------------------------------------
# Message container (tests 28–29, 41)
# ---------------------------------------------------------------------------
def test_directive_is_separate_internal_system_message():
    async def run():
        session = {"id": str(uuid.uuid4()), "turn_count": 0, "rolling_state": None}
        messages = await server._build_messages(
            session, "Player action: look around", memory_depth=3, history_window_fallback=40, early_game_stage=1
        )
        assert pacing.directive_present_in_messages(messages)
        system_msgs = [m for m in messages if m["role"] == "system"]
        assert len(system_msgs) == 2
        user_msgs = [m for m in messages if m["role"] == "user"]
        for um in user_msgs:
            assert pacing.PACING_DIRECTIVE_MARKER not in um["content"]

    _run_db(run())


def test_directive_not_appended_to_player_user_role_message():
    async def run():
        session = {"id": str(uuid.uuid4()), "turn_count": 1, "rolling_state": {"scene": "ruins"}}
        player_line = "[DEV_MODE: OFF]\n\nPlayer action: step forward"
        messages = await server._build_messages(
            session, player_line, memory_depth=3, history_window_fallback=40, early_game_stage=2
        )
        last_user = messages[-1]["content"]
        assert pacing.PACING_DIRECTIVE_MARKER not in last_user
        assert "Player action: step forward" in last_user

    _run_db(run())


def test_non_pacing_turns_construct_messages_identically_to_current_behaviour():
    async def run():
        session = {"id": str(uuid.uuid4()), "turn_count": 4, "rolling_state": {"scene": "ruins"}}
        user_text = "[DEV_MODE: OFF]\n\nPlayer action: wait"
        with_stage = await server._build_messages(
            session, user_text, memory_depth=3, history_window_fallback=40, early_game_stage=None
        )
        without_param = await server._build_messages(
            session, user_text, memory_depth=3, history_window_fallback=40
        )
        assert with_stage == without_param
        assert not pacing.directive_present_in_messages(with_stage)

    _run_db(run())


# ---------------------------------------------------------------------------
# Context budget — leading system prefix protection
# ---------------------------------------------------------------------------
def test_pacing_directive_survives_context_budget_trim():
    pacing_directive = pacing.build_early_game_directive(1)
    primary = "PRIMARY_STORY_ENGINE_SYSTEM"
    messages = [
        {"role": "system", "content": primary},
        {"role": "system", "content": pacing_directive},
    ]
    for i in range(12):
        messages.append({"role": "user", "content": f"OLD_USER_{i} " + ("x" * 600)})
        messages.append({"role": "assistant", "content": f"OLD_ASST_{i} " + ("y" * 600)})
    messages.append({"role": "user", "content": "RECENT_USER protected"})
    messages.append({"role": "assistant", "content": "RECENT_ASST protected"})
    messages.append({"role": "user", "content": "FINAL current user action"})

    trimmed, diag = enforce_context_budget(
        messages, budget_tokens=120, protected_recent_msgs=2
    )

    assert trimmed[0]["role"] == "system"
    assert trimmed[0]["content"] == primary
    assert trimmed[1]["role"] == "system"
    assert pacing.PACING_DIRECTIVE_MARKER in trimmed[1]["content"]
    assert trimmed[-1]["content"] == "FINAL current user action"
    assert any(m.get("content") == "RECENT_USER protected" for m in trimmed)
    assert any(m.get("content") == "RECENT_ASST protected" for m in trimmed)
    assert not any(f"OLD_USER_{i}" in (m.get("content") or "") for i in range(12) for m in trimmed)
    assert len(trimmed) < len(messages)
    assert diag.get("context_trimmed")
    assert "dropped_" in (diag.get("trim_reason") or "")


def test_single_system_prefix_still_trims_old_history():
    messages = [{"role": "system", "content": "primary system only"}]
    for i in range(8):
        messages.append({"role": "user", "content": f"old user {i} " + ("a" * 500)})
        messages.append({"role": "assistant", "content": f"old asst {i} " + ("b" * 500)})
    messages.append({"role": "user", "content": "recent user"})
    messages.append({"role": "assistant", "content": "recent asst"})
    messages.append({"role": "user", "content": "final user"})

    trimmed, diag = enforce_context_budget(
        messages, budget_tokens=80, protected_recent_msgs=2
    )

    assert trimmed[0]["content"] == "primary system only"
    assert trimmed[-1]["content"] == "final user"
    assert any(m.get("content") == "recent user" for m in trimmed)
    assert any(m.get("content") == "recent asst" for m in trimmed)
    assert len(trimmed) < len(messages)
    assert diag.get("context_trimmed")


def test_context_budget_stops_safely_when_no_removable_middle_messages():
    messages = [
        {"role": "system", "content": "primary"},
        {"role": "system", "content": "secondary internal system"},
        {"role": "user", "content": "recent user"},
        {"role": "assistant", "content": "recent asst"},
        {"role": "user", "content": "final user"},
    ]

    trimmed, _diag = enforce_context_budget(
        messages, budget_tokens=10, protected_recent_msgs=2
    )

    assert len(trimmed) == len(messages)
    assert trimmed[0]["content"] == "primary"
    assert trimmed[1]["content"] == "secondary internal system"
    assert trimmed[-1]["content"] == "final user"


def test_non_leading_system_message_is_not_globally_protected():
    messages = [
        {"role": "system", "content": "primary"},
        {"role": "system", "content": "pacing directive"},
        {"role": "user", "content": "old user one " + ("x" * 700)},
        {"role": "assistant", "content": "old asst one"},
        {"role": "system", "content": "MID_HISTORY_SYSTEM_DROPPABLE"},
        {"role": "user", "content": "old user two " + ("x" * 700)},
        {"role": "assistant", "content": "old asst two"},
        {"role": "user", "content": "recent user"},
        {"role": "assistant", "content": "recent asst"},
        {"role": "user", "content": "final user"},
    ]

    trimmed, diag = enforce_context_budget(
        messages, budget_tokens=100, protected_recent_msgs=2
    )

    assert trimmed[0]["content"] == "primary"
    assert trimmed[1]["content"] == "pacing directive"
    assert trimmed[-1]["content"] == "final user"
    assert diag.get("context_trimmed")
    assert not any(
        m.get("content") == "MID_HISTORY_SYSTEM_DROPPABLE" for m in trimmed
    )


# ---------------------------------------------------------------------------
# Persistence / export leak safety (tests 30–35)
# ---------------------------------------------------------------------------
@pytest.fixture()
def mongo_env():
    motor_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    sync_client = MongoClient(os.environ["MONGO_URL"])
    db_name = os.environ["DB_NAME"]
    original = server.db
    server.db = motor_client[db_name]
    sync_db = sync_client[db_name]
    yield sync_db
    server.db = original
    motor_client.close()
    sync_client.close()


@pytest.fixture()
def client(mongo_env):
    with TestClient(server.app) as c:
        yield c


def _device_headers(device_id: str) -> dict:
    return {DEVICE_ID_HEADER: device_id}


def _install_opening_llm_mock(turn_count: int = 0):
    calls = {"n": 0}

    async def fake_chat(**kwargs):
        calls["n"] += 1
        parsed = _opening_parsed()
        return {
            "content": _raw_from_parsed(parsed),
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat
    return calls, original


def test_directive_is_not_persisted(mongo_env):
    device = f"pacing-{uuid.uuid4()}"
    _, original = _install_opening_llm_mock()
    sid = None
    try:

        async def scenario():
            result = await server._create_new_story(
                server.NewStoryRequest(
                    device_id=device,
                    genre="fantasy",
                    role="scout",
                    difficulty="standard",
                    debug_mode=True,
                    mode="advanced",
                )
            )
            turn = await server.db.turns.find_one(
                {"session_id": result["session_id"], "turn_number": 1}, {"_id": 0}
            )
            session = await server.db.sessions.find_one({"id": result["session_id"]}, {"_id": 0})
            return result["session_id"], turn, session

        sid, turn, session = _run_db(scenario())
        marker = pacing.PACING_DIRECTIVE_MARKER
        assert marker not in (turn.get("player_action") or "")
        assert marker not in json.dumps(turn.get("rolling_state") or {})
        assert marker not in json.dumps(turn.get("state") or {})
        assert marker not in (turn.get("raw") or "")
        session_blob = json.dumps({k: str(v) for k, v in (session or {}).items()})
        assert marker not in session_blob
    finally:
        gateway.invoke_llm = original
        if sid:
            mongo_env.turns.delete_many({"session_id": sid})
            mongo_env.sessions.delete_one({"id": sid})


def test_directive_absent_from_player_export(mongo_env):
    device = f"pacing-export-{uuid.uuid4()}"
    _, original = _install_opening_llm_mock()
    sid = None
    try:

        async def scenario():
            result = await server._create_new_story(
                server.NewStoryRequest(
                    device_id=device,
                    genre="fantasy",
                    role="scout",
                    difficulty="standard",
                    mode="advanced",
                )
            )
            exported = await server.export_session(result["session_id"], device_id=device)
            return result["session_id"], exported

        sid, exported = _run_db(scenario())
        blob = json.dumps(exported)
        assert pacing.PACING_DIRECTIVE_MARKER not in blob
    finally:
        gateway.invoke_llm = original
        if sid:
            mongo_env.turns.delete_many({"session_id": sid})
            mongo_env.sessions.delete_one({"id": sid})


def test_directive_absent_from_raw_admin_export(mongo_env):
    device = f"pacing-raw-{uuid.uuid4()}"
    _, original = _install_opening_llm_mock()
    sid = None
    try:

        async def scenario():
            result = await server._create_new_story(
                server.NewStoryRequest(
                    device_id=device,
                    genre="fantasy",
                    role="scout",
                    difficulty="standard",
                    mode="advanced",
                )
            )
            exported = await server.export_session_raw(result["session_id"], _=None)
            return result["session_id"], exported

        sid, exported = _run_db(scenario())
        blob = json.dumps(exported, default=str)
        assert pacing.PACING_DIRECTIVE_MARKER not in blob
    finally:
        gateway.invoke_llm = original
        if sid:
            mongo_env.turns.delete_many({"session_id": sid})
            mongo_env.sessions.delete_one({"id": sid})


def test_directive_absent_from_player_api_story_action_response(client, mongo_env):
    device = f"pacing-action-{uuid.uuid4()}"
    now = datetime.now(timezone.utc)
    sid = str(uuid.uuid4())
    mongo_env.sessions.insert_one({
        "id": sid,
        "device_id": device,
        "genre": "fantasy",
        "role": "scout",
        "tone": "grim",
        "difficulty": "standard",
        "title": "Test",
        "turn_count": 1,
        "last_state": {},
        "rolling_state": {
            "scene": "market",
            "active_pressures": ["deadline"],
            "objectives": ["decide now"],
        },
        "mode": "advanced",
        "created_at": now,
        "updated_at": now,
    })

    async def fake_chat(**kwargs):
        parsed = _opening_parsed(pressure="clock ticks")
        return {
            "content": _raw_from_parsed(parsed),
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat
    try:
        r = client.post(
            "/api/story/action",
            headers=_device_headers(device),
            json={"session_id": sid, "action_text": "step closer", "debug_mode": False},
        )
        assert r.status_code == 200, r.text
        assert pacing.PACING_DIRECTIVE_MARKER not in json.dumps(r.json())
    finally:
        gateway.invoke_llm = original


# ---------------------------------------------------------------------------
# Non-regression (tests 36–40)
# ---------------------------------------------------------------------------
def test_existing_hallucination_validation_still_runs():
    prior = {"object_locations": [{"object": "brass lantern", "status": "destroyed"}]}
    parsed = _Parsed(
        narrative="You grab the brass lantern and light the way ahead.",
        state={"Health": "healthy", "Pressure": "heat presses in"},
        rolling_state={
            "active_pressures": ["heat"],
            "objectives": ["escape"],
        },
    )
    ok, reason, kind = server._full_validate(
        parsed, {"rolling_state": prior}, "search", early_game_stage=2
    )
    assert not ok
    assert kind == "hallucination"
    assert reason


def test_existing_gateway_contradiction_detection_still_runs():
    prior = {"deceased": ["Mira"]}
    parsed = _Parsed(narrative="Mira whispers a warning.")
    hits = gateway.detect_prose_contradictions(prior, parsed, "listen")
    assert hits


def test_existing_hud_shaping_remains_unchanged():
    state = {"Objective": "Find the key", "Pressure": "You should investigate now"}
    rolling = {"active_pressures": ["wind"]}
    adj = hud.shape_hud(state, rolling)
    assert "Objective" not in state
    assert state.get("Danger") in hud.DANGER_VALUES
    assert state.get("Momentum") in hud.MOMENTUM_VALUES
    assert adj


def test_existing_relationship_calculus_remains_unchanged():
    prior = {"relationship_vectors": [
        {"name": "Garrett", "trust": 20, "loyalty": 0, "fear": 0, "resentment": 0, "last_turn": 1, "bond": "neutral"},
    ]}
    merged = {
        "npcs": [{"name": "Garrett"}],
        "relationship_vectors": [{"name": "Garrett", "trust": 999}],
    }
    relationships.update_relationship_calculus(_Parsed(narrative="Silence."), prior, merged, "wait", 2)
    assert merged["relationship_vectors"][0]["trust"] <= 20


def test_existing_object_permanence_behaviour_remains_unchanged():
    parsed = _Parsed(
        ledger={"Carried": "iron key; torch", "Uncertain": "iron key (destroyed)"},
    )
    adj = server._apply_object_permanence(parsed)
    assert "iron key" not in (parsed.ledger.get("Carried") or "")
    assert adj