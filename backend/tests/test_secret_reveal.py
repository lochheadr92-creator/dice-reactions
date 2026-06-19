"""
Secret Reveal Trigger v1 — deterministic tests.

No live LLM calls. Covers confession detection, registry transitions,
directive plumbing, retry invariants, export safety, and persistence.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from starlette.testclient import TestClient

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import gateway  # noqa: E402
import player_api  # noqa: E402
import secrets  # noqa: E402
import server  # noqa: E402
from ai_service import AIServiceError  # noqa: E402
from memory import enforce_context_budget  # noqa: E402
from security import ADMIN_API_KEY_HEADER, DEVICE_ID_HEADER  # noqa: E402

SECRET_A = "I set the fire that killed the convoy."
SECRET_B = "I sold the patrol route to the raiders."
SECRET_C = "I forged the governor's seal."

TEST_ADMIN_KEY = os.environ.get("ADMIN_API_KEY") or "test-admin-key-for-secret-reveal"
os.environ["ADMIN_API_KEY"] = TEST_ADMIN_KEY


def _registry(*entries) -> Dict[str, Any]:
    return {"secret_registry": list(entries)}


def _entry(secret: str, revealed: bool = False, turn_added: int = 1, **extra) -> Dict[str, Any]:
    row = {
        "secret": secret,
        "revealed": revealed,
        "turn_added": turn_added,
        "reveal_policy": secrets.DEFAULT_REVEAL_POLICY,
    }
    row.update(extra)
    return row


def _run_db(coro):
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


def _action_turn_response(*, leak: str = "") -> str:
    narrative = f"You steady your breath. {leak}".strip()
    return (
        f"<narrative>{narrative}</narrative>"
        f"<paragraphs><p>{narrative}</p></paragraphs>"
        "<choices>A. Continue\nB. Wait\nC. Listen\nD. Move</choices>"
        "<state><Health>stable</Health><Pressure>steady</Pressure></state>"
        "<ledger><Carried>torch</Carried></ledger>"
        "<rolling_state>{}</rolling_state>"
    )


def _valid_parsed(**overrides) -> server.ParsedTurn:
    base = {
        "narrative": "You steady your breath.",
        "paragraphs": ["You steady your breath."],
        "choices": [
            {"label": "A", "text": "Continue"},
            {"label": "B", "text": "Wait"},
            {"label": "C", "text": "Listen"},
            {"label": "D", "text": "Move"},
        ],
        "state": {"Health": "stable", "Pressure": "steady"},
        "ledger": {"Carried": "torch"},
        "rolling_state": {},
        "raw": _action_turn_response(),
    }
    base.update(overrides)
    return server.ParsedTurn(**base)


# ---------------------------------------------------------------------------
# Confession detection (tests 1–7, 11–12)
# ---------------------------------------------------------------------------
def test_ordinary_action_does_not_reveal():
    working, directive, diag = secrets.prepare_turn_reveal(
        _registry(_entry(SECRET_A)), "look around the room", 2
    )
    assert working["secret_registry"][0]["revealed"] is False
    assert diag == {}
    assert directive == ""


@pytest.mark.parametrize(
    "action",
    [
        "Reveal my secret.",
        "I confess my secret.",
        "Tell them my secret.",
        "I come clean about my past.",
        "I admit what I did.",
        "I tell her the truth about what I did.",
    ],
)
def test_explicit_confession_phrases_reveal(action):
    assert secrets.detects_explicit_confession(action)


@pytest.mark.parametrize(
    "action",
    [
        "I will not reveal my secret.",
        "I refuse to confess.",
        "Don't tell them my secret.",
        "Keep my past hidden.",
        "Pretend to confess.",
        "Threaten to reveal someone else's secret.",
    ],
)
def test_negated_or_refused_confession_does_not_reveal(action):
    assert not secrets.detects_explicit_confession(action)


def test_someone_elses_secret_does_not_reveal():
    assert not secrets.detects_explicit_confession("Ask whether he has a secret.")


def test_weak_admit_i_dont_know_does_not_reveal():
    assert not secrets.detects_explicit_confession("I admit I don't know.")


def test_only_one_secret_reveals_per_turn():
    rolling = _registry(
        _entry(SECRET_A, turn_added=1),
        _entry(SECRET_B, turn_added=3),
    )
    working, _, diag = secrets.prepare_turn_reveal(rolling, "Reveal my secret.", 5)
    revealed = [e for e in working["secret_registry"] if e.get("revealed")]
    assert len(revealed) == 1
    assert revealed[0]["secret"] == SECRET_A
    assert diag["secret_reveal_occurred"] is True


def test_oldest_eligible_secret_selected_deterministically():
    rolling = _registry(
        _entry(SECRET_B, turn_added=5),
        _entry(SECRET_A, turn_added=2),
    )
    working, _, _ = secrets.prepare_turn_reveal(rolling, "I confess my secret.", 6)
    assert working["secret_registry"][1]["revealed"] is True
    assert working["secret_registry"][0]["revealed"] is False


def test_already_revealed_secret_unchanged():
    rolling = _registry(_entry(SECRET_A, revealed=True, turn_added=1, revealed_turn=2))
    working, _, diag = secrets.prepare_turn_reveal(rolling, "Reveal my secret.", 3)
    assert working["secret_registry"][0]["revealed"] is True
    assert working["secret_registry"][0]["revealed_turn"] == 2
    assert "secret_reveal_occurred" not in diag


def test_repeated_confession_is_idempotent():
    rolling = _registry(
        _entry(SECRET_A, revealed=True, turn_added=1, revealed_turn=2, reveal_mode="player_confession")
    )
    working, _, diag = secrets.prepare_turn_reveal(rolling, "Reveal my secret.", 3)
    assert working["secret_registry"][0]["revealed_turn"] == 2
    assert "secret_reveal_occurred" not in diag


def test_legacy_registry_without_reveal_policy_is_compatible():
    rolling = {"secret_registry": [{"secret": SECRET_A, "revealed": False, "turn_added": 1}]}
    working, _, diag = secrets.prepare_turn_reveal(rolling, "Reveal my secret.", 2)
    assert working["secret_registry"][0]["revealed"] is True
    assert diag["secret_reveal_occurred"] is True


def test_prepare_turn_reveal_does_not_mutate_input():
    rolling = _registry(_entry(SECRET_A))
    snapshot = json.dumps(rolling, sort_keys=True)
    secrets.prepare_turn_reveal(rolling, "Reveal my secret.", 2)
    assert json.dumps(rolling, sort_keys=True) == snapshot


# ---------------------------------------------------------------------------
# Directive + message plumbing (tests 14–19)
# ---------------------------------------------------------------------------
def test_unrevealed_secret_absent_from_build_messages():
    session = {
        "id": str(uuid.uuid4()),
        "turn_count": 1,
        "rolling_state": _registry(_entry(SECRET_A)),
    }

    async def run():
        msgs = await server._build_messages(session, "Player action: wait", 3, 40, None, "")
        blob = json.dumps(msgs)
        assert SECRET_A not in blob
        assert "secret_registry" not in blob

    _run_db(run())


def test_newly_revealed_secret_in_internal_directive():
    rolling = _registry(
        _entry(SECRET_A, revealed=True, revealed_turn=3, reveal_mode="player_confession")
    )
    directive = secrets.build_revealed_secret_directive(rolling, 3)
    assert secrets.DIRECTIVE_MARKER in directive
    assert SECRET_A in directive
    assert "NEW CONFESSION THIS TURN" in directive


def test_older_revealed_secret_gets_continuity_not_new_confession():
    rolling = _registry(
        _entry(SECRET_A, revealed=True, revealed_turn=2, reveal_mode="player_confession")
    )
    directive = secrets.build_revealed_secret_directive(rolling, 5)
    assert "ESTABLISHED REVEALED TRUTH" in directive
    assert "NEW CONFESSION THIS TURN" not in directive


def test_unrevealed_entries_never_in_directive_when_another_revealed():
    rolling = _registry(
        _entry(SECRET_A, revealed=True, revealed_turn=2, reveal_mode="player_confession"),
        _entry(SECRET_B, revealed=False, turn_added=1),
    )
    directive = secrets.build_revealed_secret_directive(rolling, 3)
    assert SECRET_A in directive
    assert SECRET_B not in directive


def test_directive_survives_context_budget_trim():
    rolling = _registry(
        _entry(SECRET_A, revealed=True, revealed_turn=2, reveal_mode="player_confession")
    )
    directive = secrets.build_revealed_secret_directive(rolling, 2)
    msgs = [
        {"role": "system", "content": server.STORY_ENGINE_SYSTEM_PROMPT},
        {"role": "system", "content": directive},
        *[{"role": "user", "content": f"old turn {i}"} for i in range(20)],
        *[{"role": "assistant", "content": f"reply {i}"} for i in range(20)],
        {"role": "user", "content": "Player action: wait"},
    ]
    trimmed, _ = enforce_context_budget(msgs, budget_tokens=200, protected_recent_msgs=2)
    system_contents = [m["content"] for m in trimmed if m.get("role") == "system"]
    assert any(secrets.DIRECTIVE_MARKER in c for c in system_contents)


def test_directive_identical_on_retry_message_construction():
    rolling = _registry(_entry(SECRET_A, revealed=True, revealed_turn=2, reveal_mode="player_confession"))
    directive = secrets.build_revealed_secret_directive(rolling, 2)
    session = {"id": str(uuid.uuid4()), "turn_count": 1, "rolling_state": rolling}
    captured: List[str] = []

    original_build = server._build_messages

    async def track_build(
        session,
        user_text,
        memory_depth,
        history_window_fallback,
        early_game_stage=None,
        secret_reveal_directive="",
        replayability_directives=None,
    ):
        captured.append(secret_reveal_directive)
        return await original_build(
            session,
            user_text,
            memory_depth,
            history_window_fallback,
            early_game_stage=early_game_stage,
            secret_reveal_directive=secret_reveal_directive,
            replayability_directives=replayability_directives,
        )

    server._build_messages = track_build
    calls = {"n": 0}

    async def fake_chat(**kwargs):
        calls["n"] += 1
        return {
            "content": _action_turn_response(),
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat

    def fail_once(parsed, sess, player_action, early_game_stage=None):
        if calls["n"] <= 1:
            return False, "bad format", "format"
        return True, "", "ok"

    original_validate = server._full_validate
    server._full_validate = fail_once
    try:
        _run_db(
            server._generate_validated_turn(
                session,
                "[DEV_MODE: OFF]\n\nPlayer action: Reveal my secret.",
                player_action="Reveal my secret.",
                secret_reveal_directive=directive,
            )
        )
        assert captured[0] == directive
        assert captured[1] == directive
        assert calls["n"] == 2
    finally:
        server._build_messages = original_build
        server._full_validate = original_validate
        gateway.invoke_llm = original


def test_retry_does_not_reveal_additional_secret():
    rolling = _registry(
        _entry(SECRET_A, turn_added=1),
        _entry(SECRET_B, turn_added=2),
    )
    working, directive, _ = secrets.prepare_turn_reveal(rolling, "Reveal my secret.", 3)
    revealed = [e for e in working["secret_registry"] if e.get("revealed")]
    assert len(revealed) == 1
    session = {"id": str(uuid.uuid4()), "turn_count": 2, "rolling_state": working}
    calls = {"n": 0}

    async def fake_chat(**kwargs):
        calls["n"] += 1
        return {
            "content": _action_turn_response(),
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat

    def fail_once(parsed, sess, player_action, early_game_stage=None):
        if calls["n"] <= 1:
            return False, "bad format", "format"
        return True, "", "ok"

    original_validate = server._full_validate
    server._full_validate = fail_once
    try:
        _run_db(
            server._generate_validated_turn(
                session,
                "[DEV_MODE: OFF]\n\nPlayer action: Reveal my secret.",
                player_action="Reveal my secret.",
                secret_reveal_directive=directive,
            )
        )
        assert calls["n"] == 2
        assert sum(1 for e in working["secret_registry"] if e.get("revealed")) == 1
    finally:
        server._full_validate = original_validate
        gateway.invoke_llm = original


def test_gateway_invoke_llm_calls_at_most_two():
    rolling = _registry(_entry(SECRET_A))
    working, directive, _ = secrets.prepare_turn_reveal(rolling, "Reveal my secret.", 2)
    session = {"id": str(uuid.uuid4()), "turn_count": 1, "rolling_state": working}
    calls = {"n": 0}

    async def fake_chat(**kwargs):
        calls["n"] += 1
        return {
            "content": _action_turn_response(),
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat

    def always_fail(parsed, sess, player_action, early_game_stage=None):
        return False, "bad format", "format"

    original_validate = server._full_validate
    server._full_validate = always_fail
    try:
        _run_db(
            server._generate_validated_turn(
                session,
                "[DEV_MODE: OFF]\n\nPlayer action: Reveal my secret.",
                player_action="Reveal my secret.",
                secret_reveal_directive=directive,
            )
        )
        assert calls["n"] == 2
    finally:
        server._full_validate = original_validate
        gateway.invoke_llm = original


def test_model_emitted_secret_registry_mutation_is_stripped():
    merged = {"scene": "hall", "secret_registry": [{"secret": "forged", "revealed": True}]}
    auth = [_entry(SECRET_A, revealed=True, revealed_turn=2, reveal_mode="player_confession")]
    adj = secrets.enforce_authoritative_registry(merged, auth)
    assert "secret_registry_model_mutation_stripped" in adj
    assert merged["secret_registry"] == auth


# ---------------------------------------------------------------------------
# HTTP integration — persistence + export safety (tests 23–29)
# ---------------------------------------------------------------------------
@pytest.fixture()
def mongo_env(monkeypatch):
    motor_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    sync_client = MongoClient(os.environ["MONGO_URL"])
    db_name = os.environ["DB_NAME"]
    original_db = server.db
    server.db = motor_client[db_name]
    sync_db = sync_client[db_name]
    sync_db.sessions.delete_many({})
    sync_db.turns.delete_many({})
    yield sync_db
    server.db = original_db
    motor_client.close()
    sync_client.close()


@pytest.fixture()
def client(mongo_env):
    original = gateway.invoke_llm

    async def fake_chat(**kwargs):
        return {
            "content": _action_turn_response(),
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    gateway.invoke_llm = fake_chat
    with TestClient(server.app) as tc:
        yield tc
    gateway.invoke_llm = original


def _insert_session(sync_db, device_id: str, rolling: Dict[str, Any], turn_count: int = 1):
    sid = str(uuid.uuid4())
    sync_db.sessions.insert_one(
        {
            "id": sid,
            "device_id": device_id,
            "genre": "horror",
            "role": "scout",
            "tone": "grim",
            "difficulty": "standard",
            "mode": "advanced",
            "turn_count": turn_count,
            "rolling_state": copy.deepcopy(rolling),
            "last_state": {"Health": "stable"},
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    )
    return sid


def _attach_action_lease(sync_db, sid: str) -> str:
    token = str(uuid.uuid4())
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    sync_db.sessions.update_one(
        {"id": sid},
        {
            "$set": {
                "action_lock_token": token,
                "action_lock_acquired_at": now,
                "action_lock_expires_at": now + timedelta(seconds=600),
            }
        },
    )
    return token


def test_generation_failure_leaves_persisted_registry_unchanged(client, mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    rolling = _registry(_entry(SECRET_A))
    sid = _insert_session(mongo_env, device_id, rolling)

    async def boom(**kwargs):
        raise AIServiceError("provider down")

    original = gateway.invoke_llm
    gateway.invoke_llm = boom
    try:
        r = client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "Reveal my secret.", "debug_mode": True},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert r.status_code == 502
    finally:
        gateway.invoke_llm = original

    stored = mongo_env.sessions.find_one({"id": sid})
    assert stored["rolling_state"]["secret_registry"][0]["revealed"] is False


def test_successful_generation_persists_reveal_once(client, mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    rolling = _registry(_entry(SECRET_A))
    sid = _insert_session(mongo_env, device_id, rolling)

    r = client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "Reveal my secret.", "debug_mode": True},
        headers={DEVICE_ID_HEADER: device_id},
    )
    assert r.status_code == 200
    stored = mongo_env.sessions.find_one({"id": sid})
    reg = stored["rolling_state"]["secret_registry"][0]
    assert reg["revealed"] is True
    assert reg["revealed_turn"] == 2
    assert reg["reveal_mode"] == "player_confession"


def test_secret_registry_absent_from_player_session_payload(client, mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    sid = _insert_session(mongo_env, device_id, _registry(_entry(SECRET_A, revealed=True, revealed_turn=1)))
    r = client.get(
        f"/api/story/session/{sid}",
        headers={DEVICE_ID_HEADER: device_id},
    )
    assert r.status_code == 200
    assert "secret_registry" not in json.dumps(r.json())


def test_secret_registry_absent_from_player_turn_response(client, mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    rolling = _registry(_entry(SECRET_A))
    sid = _insert_session(mongo_env, device_id, rolling)
    r = client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "Reveal my secret.", "debug_mode": True},
        headers={DEVICE_ID_HEADER: device_id},
    )
    assert r.status_code == 200
    assert "secret_registry" not in json.dumps(r.json())


def test_secret_registry_absent_from_player_safe_export(client, mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    sid = _insert_session(mongo_env, device_id, _registry(_entry(SECRET_A)))
    client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "Reveal my secret.", "debug_mode": True},
        headers={DEVICE_ID_HEADER: device_id},
    )
    r = client.get(
        f"/api/story/session/{sid}/export",
        headers={DEVICE_ID_HEADER: device_id},
    )
    assert r.status_code == 200
    dumped = json.dumps(r.json())
    assert "secret_registry" not in dumped
    assert secrets.DIRECTIVE_MARKER not in dumped
    assert "NEW CONFESSION THIS TURN" not in dumped


def test_raw_admin_export_retains_registry(client, mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    sid = _insert_session(mongo_env, device_id, _registry(_entry(SECRET_A)))
    client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "Reveal my secret.", "debug_mode": True},
        headers={DEVICE_ID_HEADER: device_id},
    )
    r = client.get(
        f"/api/story/session/{sid}/export/raw",
        headers={ADMIN_API_KEY_HEADER: TEST_ADMIN_KEY},
    )
    assert r.status_code == 200
    reg = r.json()["summary"]["rolling_state"]["secret_registry"][0]
    assert reg["revealed"] is True
    assert SECRET_A in reg["secret"]


# ---------------------------------------------------------------------------
# Secret ID determinism
# ---------------------------------------------------------------------------
def test_build_stable_secret_id_is_position_based():
    assert secrets.build_stable_secret_id(0) == "secret-1"
    assert secrets.build_stable_secret_id(1) == "secret-2"
    assert secrets.build_stable_secret_id(0) == secrets.build_stable_secret_id(0)


def test_identical_seeded_inputs_produce_identical_secret_ids():
    setup = {"secret": SECRET_A}
    first = server._seed_custom_setup_into_rolling({}, setup)
    second = server._seed_custom_setup_into_rolling({}, setup)
    assert first["secret_registry"][0]["secret_id"] == second["secret_registry"][0]["secret_id"]


def test_different_registry_positions_do_not_collide():
    rolling = {
        "secret_registry": [
            _entry(SECRET_A, secret_id=secrets.build_stable_secret_id(0)),
            _entry(SECRET_B, turn_added=2, secret_id=secrets.build_stable_secret_id(1)),
        ]
    }
    ids = [e["secret_id"] for e in rolling["secret_registry"]]
    assert len(set(ids)) == 2


def test_secret_id_path_has_no_random_or_time_dependent_generation():
    source = Path(__file__).resolve().parents[1] / "secrets.py"
    text = source.read_text(encoding="utf-8")
    forbidden = ("uuid4", "uuid.uuid4", "time.time", "datetime.now", "random.", "hash(")
    for token in forbidden:
        assert token not in text


# ---------------------------------------------------------------------------
# Internal directive leakage
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "field,leak,reason",
    [
        ("paragraphs", secrets.DIRECTIVE_MARKER, "internal system directive leaked into narrative"),
        ("choices", secrets.DIRECTIVE_MARKER, "internal system directive leaked into choices"),
        ("state", secrets.DIRECTIVE_MARKER, "internal system directive leaked into state"),
        ("ledger", secrets.DIRECTIVE_MARKER, "internal system directive leaked into ledger"),
        ("rolling_state", secrets.DIRECTIVE_MARKER, "internal system directive leaked into rolling_state"),
    ],
)
def test_internal_marker_rejected_in_player_fields(field, leak, reason):
    kwargs = {}
    if field == "paragraphs":
        kwargs["paragraphs"] = [f"The room is quiet. {leak}"]
    elif field == "choices":
        kwargs["choices"] = [
            {"label": "A", "text": f"Continue {leak}"},
            {"label": "B", "text": "Wait"},
            {"label": "C", "text": "Listen"},
            {"label": "D", "text": "Move"},
        ]
    elif field == "state":
        kwargs["state"] = {"Health": "stable", "Pressure": leak}
    elif field == "ledger":
        kwargs["ledger"] = {"Carried": leak}
    else:
        kwargs["rolling_state"] = {"scene": leak}
    ok, got = server._validate_parsed(_valid_parsed(**kwargs))
    assert not ok
    assert got == reason


def test_directive_prose_rejected_in_narrative():
    ok, reason = server._validate_parsed(
        _valid_parsed(paragraphs=["A hush falls. NEW CONFESSION THIS TURN: truth"])
    )
    assert not ok
    assert "internal system directive" in reason


def test_marker_never_appears_in_build_player_turn():
    raw_turn = {
        "session_id": "s1",
        "turn_number": 2,
        "player_action": "wait",
        "narrative": f"Quiet. {secrets.DIRECTIVE_MARKER}",
        "paragraphs": [f"Quiet. {secrets.DIRECTIVE_MARKER}"],
        "choices": [{"label": "A", "text": "Continue"}],
        "state": {"Health": "stable"},
        "ledger": {"Carried": "torch"},
    }
    safe = player_api.build_player_turn(raw_turn)
    blob = json.dumps(safe)
    assert secrets.DIRECTIVE_MARKER not in blob
    assert "NEW CONFESSION THIS TURN" not in blob


def test_marker_absent_from_player_action_response(client, mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    sid = _insert_session(mongo_env, device_id, _registry(_entry(SECRET_A)))
    r = client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "Reveal my secret.", "debug_mode": True},
        headers={DEVICE_ID_HEADER: device_id},
    )
    assert r.status_code == 200
    blob = json.dumps(r.json())
    assert secrets.DIRECTIVE_MARKER not in blob
    assert "NEW CONFESSION THIS TURN" not in blob


def test_retry_uses_same_directive_without_exposing_marker(client, mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    sid = _insert_session(mongo_env, device_id, _registry(_entry(SECRET_A)))
    calls = {"n": 0}
    captured_directives: List[str] = []
    original_build = server._build_messages

    async def track_build(
        session,
        user_text,
        memory_depth,
        history_window_fallback,
        early_game_stage=None,
        secret_reveal_directive="",
        replayability_directives=None,
    ):
        captured_directives.append(secret_reveal_directive)
        return await original_build(
            session,
            user_text,
            memory_depth,
            history_window_fallback,
            early_game_stage=early_game_stage,
            secret_reveal_directive=secret_reveal_directive,
            replayability_directives=replayability_directives,
        )

    async def leaky_then_clean(**kwargs):
        calls["n"] += 1
        leak = secrets.DIRECTIVE_MARKER if calls["n"] == 1 else ""
        return {
            "content": _action_turn_response(leak=leak),
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    server._build_messages = track_build
    original = gateway.invoke_llm
    gateway.invoke_llm = leaky_then_clean
    try:
        r = client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "Reveal my secret.", "debug_mode": True},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert r.status_code == 200
        assert calls["n"] == 2
        assert captured_directives[0] == captured_directives[1]
        assert secrets.DIRECTIVE_MARKER in captured_directives[0]
        assert secrets.DIRECTIVE_MARKER not in json.dumps(r.json())
    finally:
        server._build_messages = original_build
        gateway.invoke_llm = original


# ---------------------------------------------------------------------------
# Authoritative registry mutation classes
# ---------------------------------------------------------------------------
def test_model_registry_omit_is_restored():
    auth = [_entry(SECRET_A, revealed=True, revealed_turn=2, reveal_mode="player_confession")]
    merged = {"scene": "hall"}
    adj = secrets.enforce_authoritative_registry(merged, auth)
    assert "secret_registry_model_mutation_stripped" in adj
    assert merged["secret_registry"] == auth


def test_model_registry_secret_text_change_is_stripped():
    auth = [_entry(SECRET_A, revealed=False, turn_added=1)]
    merged = {"secret_registry": [{"secret": "forged truth", "revealed": False, "turn_added": 1}]}
    adj = secrets.enforce_authoritative_registry(merged, auth)
    assert adj
    assert merged["secret_registry"][0]["secret"] == SECRET_A


def test_model_registry_reveal_metadata_change_is_stripped():
    auth = [_entry(SECRET_A, revealed=True, revealed_turn=2, reveal_mode="player_confession")]
    forged = dict(auth[0])
    forged["revealed_turn"] = 99
    forged["reveal_mode"] = "model_invented"
    merged = {"secret_registry": [forged]}
    adj = secrets.enforce_authoritative_registry(merged, auth)
    assert adj
    assert merged["secret_registry"][0]["revealed_turn"] == 2
    assert merged["secret_registry"][0]["reveal_mode"] == "player_confession"


def test_model_registry_extra_entries_are_stripped():
    auth = [_entry(SECRET_A, revealed=False, turn_added=1)]
    merged = {
        "secret_registry": [
            auth[0],
            _entry(SECRET_B, turn_added=2),
        ]
    }
    adj = secrets.enforce_authoritative_registry(merged, auth)
    assert adj
    assert len(merged["secret_registry"]) == 1


# ---------------------------------------------------------------------------
# Best-available fallback scrubbing + registry preservation
# ---------------------------------------------------------------------------
def test_best_available_fallback_scrubs_marker_from_persisted_fields(client, mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    sid = _insert_session(mongo_env, device_id, _registry(_entry(SECRET_A)))
    calls = {"n": 0}
    marker = secrets.DIRECTIVE_MARKER

    async def leaky_chat(**kwargs):
        calls["n"] += 1
        return {
            "content": _action_turn_response(leak=marker),
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    original_validate = server._full_validate
    gateway.invoke_llm = leaky_chat

    def always_fail(*_args, **_kwargs):
        return False, "forced validation failure", "format"

    server._full_validate = always_fail
    try:
        r = client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "Reveal my secret.", "debug_mode": True},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert r.status_code == 200
        assert calls["n"] == 2
        blob = json.dumps(r.json())
        assert marker not in blob
        assert "NEW CONFESSION THIS TURN" not in blob

        turn = mongo_env.turns.find_one({"session_id": sid, "turn_number": 2})
        assert marker not in (turn.get("narrative") or "")
        assert marker not in json.dumps(turn.get("paragraphs") or [])
        assert marker not in json.dumps(turn.get("choices") or [])
        assert marker not in json.dumps(turn.get("state") or {})
        assert marker not in json.dumps(turn.get("ledger") or {})
        assert marker not in json.dumps(turn.get("rolling_state") or {})

        replay = server._summarise_turn_for_assistant(turn)
        assert marker not in replay
        assert "NEW CONFESSION THIS TURN" not in replay

        exported = client.get(
            f"/api/story/session/{sid}/export",
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert marker not in json.dumps(exported.json())
    finally:
        gateway.invoke_llm = original
        server._full_validate = original_validate


def test_scrub_preserves_authoritative_secret_registry_text(client, mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    sid = _insert_session(mongo_env, device_id, _registry(_entry(SECRET_A)))
    marker = secrets.DIRECTIVE_MARKER

    async def leaky_chat(**kwargs):
        leaked_registry = {
            "secret_registry": [
                {
                    "secret": f"{marker} forged secret text",
                    "revealed": True,
                    "turn_added": 1,
                }
            ],
            "scene": f"scene with {marker}",
        }
        return {
            "content": (
                _action_turn_response(leak=marker).replace(
                    "<rolling_state>{}</rolling_state>",
                    f"<rolling_state>{json.dumps(leaked_registry)}</rolling_state>",
                )
            ),
            "model_used": "test",
            "model_requested": "test",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    original_validate = server._full_validate
    gateway.invoke_llm = leaky_chat

    def always_fail(*_args, **_kwargs):
        return False, "forced validation failure", "format"

    server._full_validate = always_fail
    try:
        r = client.post(
            "/api/story/action",
            json={"session_id": sid, "action_text": "Reveal my secret.", "debug_mode": True},
            headers={DEVICE_ID_HEADER: device_id},
        )
        assert r.status_code == 200
        stored = mongo_env.sessions.find_one({"id": sid})
        reg = stored["rolling_state"]["secret_registry"][0]
        assert reg["secret"] == SECRET_A
        assert reg["revealed"] is True
        assert marker not in reg["secret"]
        turn = mongo_env.turns.find_one({"session_id": sid, "turn_number": 2})
        assert turn["rolling_state"]["secret_registry"][0]["secret"] == SECRET_A
    finally:
        gateway.invoke_llm = original
        server._full_validate = original_validate


def test_finalize_validated_turn_scrubs_without_touching_registry():
    marker = secrets.DIRECTIVE_MARKER
    parsed = _valid_parsed(
        paragraphs=[f"Quiet. {marker}"],
        rolling_state={
            "scene": f"hall {marker}",
            "secret_registry": [_entry(SECRET_A, revealed=True, revealed_turn=2)],
        },
    )
    scrubbed, _raw, _meta = server._finalize_validated_turn(parsed, parsed.raw, {})
    assert marker not in scrubbed.paragraphs[0]
    assert marker not in scrubbed.rolling_state["scene"]
    assert scrubbed.rolling_state["secret_registry"][0]["secret"] == SECRET_A


# ---------------------------------------------------------------------------
# Persistence atomicity / rollback
# ---------------------------------------------------------------------------
def test_rollback_removes_inserted_turn_when_session_not_updated(mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    rolling = _registry(_entry(SECRET_A))
    sid = _insert_session(mongo_env, device_id, rolling)
    turn_id = str(uuid.uuid4())
    snapshot = {
        "turn_count": 1,
        "rolling_state": copy.deepcopy(rolling),
        "last_state": {"Health": "stable"},
    }
    mongo_env.turns.insert_one(
        {
            "id": turn_id,
            "session_id": sid,
            "turn_number": 2,
            "player_action": "Reveal my secret.",
            "narrative": "confession",
            "paragraphs": ["confession"],
            "choices": [],
            "state": {"Health": "stable"},
            "ledger": {},
            "rolling_state": _registry(_entry(SECRET_A, revealed=True, revealed_turn=2)),
        }
    )

    async def run():
        await server._rollback_story_action_persist(
            sid,
            turn_id,
            snapshot,
            None,
            turn_inserted=True,
            session_updated=False,
        )

    _run_db(run())
    assert mongo_env.turns.count_documents({"session_id": sid, "id": turn_id}) == 0
    stored = mongo_env.sessions.find_one({"id": sid})
    assert stored["turn_count"] == 1
    assert stored["rolling_state"]["secret_registry"][0]["revealed"] is False


def test_rollback_restores_session_and_removes_turn(mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    rolling = _registry(_entry(SECRET_A))
    sid = _insert_session(mongo_env, device_id, rolling)
    turn_id = str(uuid.uuid4())
    snapshot = {
        "turn_count": 1,
        "rolling_state": copy.deepcopy(rolling),
        "last_state": {"Health": "stable"},
        "debug_mode": True,
    }
    revealed = _registry(_entry(SECRET_A, revealed=True, revealed_turn=2, reveal_mode="player_confession"))
    attempted_update = {"turn_count": 2, "rolling_state": revealed}
    mongo_env.sessions.update_one({"id": sid}, {"$set": attempted_update})
    mongo_env.turns.insert_one(
        {
            "id": turn_id,
            "session_id": sid,
            "turn_number": 2,
            "player_action": "Reveal my secret.",
            "narrative": "confession",
            "paragraphs": ["confession"],
            "choices": [],
            "state": {"Health": "stable"},
            "ledger": {},
            "rolling_state": revealed,
        }
    )

    async def run():
        await server._rollback_story_action_persist(
            sid,
            turn_id,
            snapshot,
            attempted_update,
            turn_inserted=True,
            session_updated=True,
        )

    _run_db(run())
    assert mongo_env.turns.count_documents({"session_id": sid, "id": turn_id}) == 0
    stored = mongo_env.sessions.find_one({"id": sid})
    assert stored["turn_count"] == 1
    assert stored["rolling_state"]["secret_registry"][0]["revealed"] is False


def test_persist_story_action_turn_rolls_back_when_cas_update_fails(mongo_env, monkeypatch):
    device_id = f"dev_{uuid.uuid4()}"
    rolling = _registry(_entry(SECRET_A))
    sid = _insert_session(mongo_env, device_id, rolling)
    lease_token = _attach_action_lease(mongo_env, sid)
    revealed = _registry(_entry(SECRET_A, revealed=True, revealed_turn=2, reveal_mode="player_confession"))
    snapshot = {
        "turn_count": 1,
        "rolling_state": copy.deepcopy(rolling),
        "last_state": {"Health": "stable"},
        "debug_mode": True,
        "model_switches": [],
    }
    turn_doc = {
        "id": str(uuid.uuid4()),
        "session_id": sid,
        "turn_number": 2,
        "player_action": "Reveal my secret.",
        "narrative": "confession",
        "paragraphs": ["confession"],
        "choices": [],
        "state": {"Health": "stable"},
        "ledger": {},
        "rolling_state": revealed,
    }
    update_set = {
        "turn_count": 2,
        "last_state": {"Health": "stable"},
        "rolling_state": revealed,
        "debug_mode": True,
        "updated_at": "2026-01-01T00:00:00Z",
    }

    async def boom_cas(*_args, **_kwargs):
        raise RuntimeError("session CAS failed")

    monkeypatch.setattr(server, "_cas_update_story_action_session", boom_cas)

    async def run():
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await server._persist_story_action_turn(
                sid,
                2,
                turn_doc,
                update_set,
                snapshot,
                {"model_used": "test"},
                lease_token=lease_token,
                expected_turn_count=1,
            )
        assert exc.value.status_code == 502

    _run_db(run())
    assert mongo_env.turns.count_documents({"session_id": sid, "turn_number": 2}) == 0
    stored = mongo_env.sessions.find_one({"id": sid})
    assert stored["turn_count"] == 1
    assert stored["rolling_state"]["secret_registry"][0]["revealed"] is False


def test_turn_insert_failure_leaves_session_registry_unchanged(mongo_env, monkeypatch):
    device_id = f"dev_{uuid.uuid4()}"
    rolling = _registry(_entry(SECRET_A))
    sid = _insert_session(mongo_env, device_id, rolling)
    lease_token = _attach_action_lease(mongo_env, sid)
    revealed = _registry(_entry(SECRET_A, revealed=True, revealed_turn=2, reveal_mode="player_confession"))
    snapshot = {
        "turn_count": 1,
        "rolling_state": copy.deepcopy(rolling),
        "last_state": {"Health": "stable"},
        "debug_mode": True,
        "model_switches": [],
    }
    turn_doc = {
        "id": str(uuid.uuid4()),
        "session_id": sid,
        "turn_number": 2,
        "player_action": "Reveal my secret.",
        "narrative": "confession",
        "paragraphs": ["confession"],
        "choices": [],
        "state": {"Health": "stable"},
        "ledger": {},
        "rolling_state": revealed,
    }
    update_set = {"turn_count": 2, "rolling_state": revealed, "last_state": {"Health": "stable"}}

    async def fail_insert(_doc):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(server, "_insert_story_action_turn", fail_insert)

    async def run():
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await server._persist_story_action_turn(
                sid,
                2,
                turn_doc,
                update_set,
                snapshot,
                {"model_used": "test"},
                lease_token=lease_token,
                expected_turn_count=1,
            )
        assert exc.value.status_code == 502

    _run_db(run())
    stored = mongo_env.sessions.find_one({"id": sid})
    assert stored["turn_count"] == 1
    assert stored["rolling_state"]["secret_registry"][0]["revealed"] is False
    assert mongo_env.turns.count_documents({"session_id": sid}) == 0


def test_session_update_failure_rolls_back_inserted_turn(mongo_env, monkeypatch):
    device_id = f"dev_{uuid.uuid4()}"
    rolling = _registry(_entry(SECRET_A))
    sid = _insert_session(mongo_env, device_id, rolling)
    lease_token = _attach_action_lease(mongo_env, sid)
    revealed = _registry(_entry(SECRET_A, revealed=True, revealed_turn=2, reveal_mode="player_confession"))
    snapshot = {
        "turn_count": 1,
        "rolling_state": copy.deepcopy(rolling),
        "last_state": {"Health": "stable"},
        "debug_mode": True,
        "model_switches": [],
    }
    turn_doc = {
        "id": str(uuid.uuid4()),
        "session_id": sid,
        "turn_number": 2,
        "player_action": "Reveal my secret.",
        "narrative": "confession",
        "paragraphs": ["confession"],
        "choices": [],
        "state": {"Health": "stable"},
        "ledger": {},
        "rolling_state": revealed,
    }
    update_set = {"turn_count": 2, "rolling_state": revealed, "last_state": {"Health": "stable"}}

    async def fail_update(*_args, **_kwargs):
        raise RuntimeError("session update failed")

    monkeypatch.setattr(server, "_cas_update_story_action_session", fail_update)

    async def run():
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await server._persist_story_action_turn(
                sid,
                2,
                turn_doc,
                update_set,
                snapshot,
                {"model_used": "test"},
                lease_token=lease_token,
                expected_turn_count=1,
            )
        assert exc.value.status_code == 502

    _run_db(run())
    assert mongo_env.turns.count_documents({"session_id": sid, "turn_number": 2}) == 0
    stored = mongo_env.sessions.find_one({"id": sid})
    assert stored["turn_count"] == 1
    assert stored["rolling_state"]["secret_registry"][0]["revealed"] is False


def test_successful_persistence_writes_one_turn_and_one_reveal_transition(client, mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    rolling = _registry(_entry(SECRET_A))
    sid = _insert_session(mongo_env, device_id, rolling)
    r = client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "Reveal my secret.", "debug_mode": True},
        headers={DEVICE_ID_HEADER: device_id},
    )
    assert r.status_code == 200
    stored = mongo_env.sessions.find_one({"id": sid})
    turns = list(mongo_env.turns.find({"session_id": sid}))
    assert stored["turn_count"] == 2
    assert len(turns) == 1
    assert turns[0]["turn_number"] == 2
    assert stored["rolling_state"]["secret_registry"][0]["revealed"] is True
    assert turns[0]["rolling_state"]["secret_registry"][0]["revealed"] is True


def test_retry_after_persistence_failure_reveals_exactly_once(client, mongo_env, monkeypatch):
    device_id = f"dev_{uuid.uuid4()}"
    rolling = _registry(_entry(SECRET_A))
    sid = _insert_session(mongo_env, device_id, rolling)
    real_persist = server._persist_story_action_turn
    attempts = {"n": 0}

    async def fail_once_persist(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            from fastapi import HTTPException

            raise HTTPException(status_code=502, detail=server._STORY_ENGINE_UNAVAILABLE)
        return await real_persist(*args, **kwargs)

    monkeypatch.setattr(server, "_persist_story_action_turn", fail_once_persist)
    first = client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "Reveal my secret.", "debug_mode": True},
        headers={DEVICE_ID_HEADER: device_id},
    )
    assert first.status_code == 502
    second = client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "Reveal my secret.", "debug_mode": True},
        headers={DEVICE_ID_HEADER: device_id},
    )
    assert second.status_code == 200

    stored = mongo_env.sessions.find_one({"id": sid})
    reveal_turns = list(mongo_env.turns.find({"session_id": sid, "turn_number": 2}))
    assert stored["turn_count"] == 2
    assert len(reveal_turns) == 1
    assert stored["rolling_state"]["secret_registry"][0]["revealed"] is True
    assert sum(1 for t in reveal_turns if t["rolling_state"]["secret_registry"][0]["revealed"]) == 1


def test_rollback_does_not_delete_earlier_turn(mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    rolling = _registry(_entry(SECRET_A))
    sid = _insert_session(mongo_env, device_id, rolling, turn_count=2)
    earlier_id = str(uuid.uuid4())
    failed_id = str(uuid.uuid4())
    mongo_env.turns.insert_one(
        {
            "id": earlier_id,
            "session_id": sid,
            "turn_number": 2,
            "player_action": "wait",
            "narrative": "Earlier turn.",
            "paragraphs": ["Earlier turn."],
            "choices": [],
            "state": {"Health": "stable"},
            "ledger": {},
            "rolling_state": copy.deepcopy(rolling),
        }
    )
    snapshot = {
        "turn_count": 2,
        "rolling_state": copy.deepcopy(rolling),
        "last_state": {"Health": "stable"},
    }
    mongo_env.turns.insert_one(
        {
            "id": failed_id,
            "session_id": sid,
            "turn_number": 3,
            "player_action": "Reveal my secret.",
            "narrative": "failed turn",
            "paragraphs": ["failed turn"],
            "choices": [],
            "state": {"Health": "stable"},
            "ledger": {},
            "rolling_state": _registry(_entry(SECRET_A, revealed=True, revealed_turn=3)),
        }
    )

    async def run():
        await server._rollback_story_action_persist(
            sid,
            failed_id,
            snapshot,
            None,
            turn_inserted=True,
            session_updated=False,
        )

    _run_db(run())
    assert mongo_env.turns.count_documents({"session_id": sid, "id": earlier_id}) == 1
    assert mongo_env.turns.count_documents({"session_id": sid, "id": failed_id}) == 0
    stored = mongo_env.sessions.find_one({"id": sid})
    assert stored["turn_count"] == 2


def test_rollback_deletes_only_exact_turn_id_when_turn_numbers_collide(mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    rolling = _registry(_entry(SECRET_A))
    sid = _insert_session(mongo_env, device_id, rolling)
    try:
        mongo_env.turns.drop_index("turns_session_turn_unique")
    except Exception:
        pass
    winner_id = str(uuid.uuid4())
    loser_id = str(uuid.uuid4())
    winner_doc = {
        "id": winner_id,
        "session_id": sid,
        "turn_number": 2,
        "player_action": "winner",
        "narrative": "Winner turn.",
        "paragraphs": ["Winner turn."],
        "choices": [],
        "state": {"Health": "stable"},
        "ledger": {},
        "rolling_state": copy.deepcopy(rolling),
    }
    loser_doc = {
        "id": loser_id,
        "session_id": sid,
        "turn_number": 2,
        "player_action": "loser",
        "narrative": "Loser turn.",
        "paragraphs": ["Loser turn."],
        "choices": [],
        "state": {"Health": "stable"},
        "ledger": {},
        "rolling_state": copy.deepcopy(rolling),
    }
    mongo_env.turns.insert_one(winner_doc)
    mongo_env.turns.insert_one(loser_doc)

    async def run():
        await server._rollback_story_action_persist(
            sid,
            loser_id,
            {"turn_count": 1, "rolling_state": copy.deepcopy(rolling)},
            None,
            turn_inserted=True,
            session_updated=False,
        )

    _run_db(run())
    assert mongo_env.turns.count_documents({"session_id": sid, "id": winner_id}) == 1
    assert mongo_env.turns.count_documents({"session_id": sid, "id": loser_id}) == 0


def test_rollback_idempotent_when_exact_turn_already_absent(mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    sid = _insert_session(mongo_env, device_id, _registry(_entry(SECRET_A)))
    missing_id = str(uuid.uuid4())

    async def run():
        await server._rollback_story_action_persist(
            sid,
            missing_id,
            {"turn_count": 1, "rolling_state": _registry(_entry(SECRET_A))},
            None,
            turn_inserted=True,
            session_updated=False,
        )
        await server._rollback_story_action_persist(
            sid,
            missing_id,
            {"turn_count": 1, "rolling_state": _registry(_entry(SECRET_A))},
            None,
            turn_inserted=True,
            session_updated=False,
        )

    _run_db(run())


def test_session_rollback_skipped_when_compare_and_set_misses(mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    rolling = _registry(_entry(SECRET_A))
    sid = _insert_session(mongo_env, device_id, rolling)
    turn_id = str(uuid.uuid4())
    winner_revealed = _registry(
        _entry(SECRET_A, revealed=True, revealed_turn=2, reveal_mode="player_confession")
    )
    loser_revealed = _registry(
        _entry("forged secret text", revealed=True, revealed_turn=2, reveal_mode="player_confession")
    )
    mongo_env.sessions.update_one(
        {"id": sid},
        {"$set": {"turn_count": 2, "rolling_state": winner_revealed}},
    )
    snapshot = {
        "turn_count": 1,
        "rolling_state": copy.deepcopy(rolling),
        "last_state": {"Health": "stable"},
    }
    attempted_update = {"turn_count": 2, "rolling_state": loser_revealed}

    async def run():
        await server._rollback_story_action_persist(
            sid,
            turn_id,
            snapshot,
            attempted_update,
            turn_inserted=False,
            session_updated=True,
        )

    _run_db(run())
    stored = mongo_env.sessions.find_one({"id": sid})
    assert stored["turn_count"] == 2
    assert stored["rolling_state"]["secret_registry"][0]["secret"] == SECRET_A
    assert stored["rolling_state"]["secret_registry"][0]["revealed"] is True


def test_debug_telemetry_contains_no_secret_text(client, mongo_env):
    device_id = f"dev_{uuid.uuid4()}"
    sid = _insert_session(mongo_env, device_id, _registry(_entry(SECRET_A)))
    r = client.post(
        "/api/story/action",
        json={"session_id": sid, "action_text": "Reveal my secret.", "debug_mode": True},
        headers={DEVICE_ID_HEADER: device_id},
    )
    assert r.status_code == 200
    turn = mongo_env.turns.find_one({"session_id": sid, "turn_number": 2})
    debug_blob = json.dumps(turn.get("debug") or {})
    assert SECRET_A not in debug_blob
    assert turn["debug"].get("secret_reveal_occurred") == "true"