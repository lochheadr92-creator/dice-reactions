"""
Canonical narration (reliability release): the optional second-pass mature
renderer is disabled. Exercises the complete story-creation + action +
presentation path with an adversarial rewriter that would change an event,
proving the second provider is never called and canonical output is served.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import mature_content  # noqa: E402
import mature_rendering  # noqa: E402
import server  # noqa: E402
from security import DEVICE_ID_HEADER  # noqa: E402
from reliability_support import (  # noqa: E402
    FakeGateway,
    MongoEnv,
    insert_session,
    make_client,
    relax_rate_limits,
)

# One paragraph, so these stories use the short turn length (1 to 2 paragraphs). At the default
# length a one-paragraph reply is re-broken at delivery (review 2, finding 3).
CANONICAL_OPENING = "Mara waits outside the locked gate. The key remains in your pocket."
CANONICAL_ACTION = "Mara still waits outside the locked gate. The key stays in your pocket."
ADVERSARIAL = "Mara opens the gate with your key and escapes into the forest."


_OPENING_CHOICES = "A. Wait\nB. Listen\nC. Speak to Mara\nD. Leave"
# Different from the opening: a reply repeating the previous turn's choices is
# rejected by the repetition guard.
_ACTION_CHOICES = "A. Try the key\nB. Knock twice\nC. Ask Mara to step back\nD. Circle the wall"


def _turn(narrative: str, choices: str = _OPENING_CHOICES) -> str:
    return (
        '<rolling_state>{"npcs": [{"name": "Mara", "age": 30}], "player_age": 30}</rolling_state>\n'
        f"<narrative>{narrative}</narrative>\n"
        f"<choices>\n{choices}\n</choices>\n"
        "<state>\nHealth: stable\nPressure: a locked gate\nPosition: outside the gate\n</state>\n"
        "<ledger>\nCarried: key\n</ledger>\n"
    )


@pytest.fixture()
def env(monkeypatch):
    mongo = MongoEnv()
    relax_rate_limits(monkeypatch)
    monkeypatch.setenv("DISTRIBUTION_CHANNEL", "development")
    monkeypatch.setenv("ENABLE_MATURE_CONTENT", "true")
    # Simulate a fully configured pinned renderer — the release switch must still win.
    monkeypatch.setattr(mature_rendering, "get_mature_model_id", lambda: "x-ai/grok-pinned-2026-01")
    monkeypatch.setattr(mature_rendering, "model_is_configured", lambda _m: True)
    yield mongo
    mongo.close()


@pytest.fixture()
def adversarial_renderer(monkeypatch):
    calls = {"n": 0}

    async def rewrite(**_kwargs):
        calls["n"] += 1
        return {"content": f"<narrative>{ADVERSARIAL}</narrative>"}

    monkeypatch.setattr(mature_rendering, "chat_completion_strict_with_meta", rewrite)
    return calls


def _adult_preferences():
    return {
        **mature_content.default_mature_content(),
        "adult_mode_enabled": True,
        "adult_age_confirmed": True,
        "violence_level": "graphic",
    }


def test_capabilities_report_renderer_unavailable(env):
    with make_client() as client:
        res = client.get("/api/setup/capabilities")
    assert res.status_code == 200
    caps = res.json()["distribution_capabilities"]
    assert caps["mature_renderer_configured"] is False
    # Unrelated content capabilities still reflect deployment configuration.
    assert caps["adult_mode_available"] is True


def test_full_path_serves_canonical_narrative_and_never_calls_second_provider(env, adversarial_renderer):
    device = f"dev_{uuid.uuid4()}"
    def by_request(_n, kwargs):
        texts = " ".join(str(m.get("content", "")) for m in kwargs.get("messages", []))
        if "Player action:" in texts:
            return _turn(CANONICAL_ACTION, _ACTION_CHOICES)
        return _turn(CANONICAL_OPENING)

    fake = FakeGateway(_turn(CANONICAL_OPENING), on_request=by_request).install()
    try:
        with make_client() as client:
            created = client.post(
                "/api/story/new",
                json={
                    "device_id": device,
                    "genre": "fantasy",
                    "prose_mode": "brief",
                    "mature_content": _adult_preferences(),
                    "creation_request_id": f"create-{uuid.uuid4()}",
                },
            )
            assert created.status_code == 200, created.text
            sid = created.json()["session_id"]
            assert created.json()["turn"]["narrative"] == CANONICAL_OPENING
            policy = created.json()["session"]["rendering_policy"]
            assert policy["last_status"] == mature_rendering.RENDERER_DISABLED_STATUS
            assert policy["last_renderer"] == "standard"
            assert created.json()["session"]["mature_content"]["adult_mode_enabled"] is True

            acted = client.post(
                "/api/story/action",
                json={"session_id": sid, "action_text": "Wait", "action_request_id": f"act-{uuid.uuid4()}"},
                headers={DEVICE_ID_HEADER: device},
            )
            assert acted.status_code == 200, acted.text
            assert acted.json()["turn"]["narrative"] == CANONICAL_ACTION
            assert ADVERSARIAL not in acted.text
    finally:
        fake.restore()

    assert adversarial_renderer["n"] == 0
    assert fake.calls >= 2
    turns = list(env.sync_db.turns.find({"session_id": sid}).sort("turn_number", 1))
    assert [t["narrative"] for t in turns] == [CANONICAL_OPENING, CANONICAL_ACTION]
    assert [t["canonical_narrative"] for t in turns] == [CANONICAL_OPENING, CANONICAL_ACTION]
    # Authoritative state is the engine's, untouched by any presentation pass.
    assert turns[-1]["rolling_state"]["npcs"][0]["name"] == "Mara"
    session = env.sync_db.sessions.find_one({"id": sid})
    assert session["mature_content"]["adult_mode_enabled"] is True
    assert session["rendering_policy"]["last_status"] == mature_rendering.RENDERER_DISABLED_STATUS


def test_existing_mature_pinned_session_is_served_canonical_prose(env, adversarial_renderer):
    """A saved session that already requested the renderer keeps its preferences but gets canonical output."""
    device = f"dev_{uuid.uuid4()}"
    historic_passage = "Historic rendered passage that must not be rewritten."
    sid = insert_session(
        env.sync_db,
        device,
        extra={
            "prose_mode": "brief",
            "mature_content": _adult_preferences(),
            "rendering_policy": {
                "route": "mature_pinned",
                "failure_mode": "safe_standard",
                "sexual_age_boundary": "explicit_18_plus_only",
                "last_status": "rendered_mature",
                "last_renderer": "mature_pinned",
            },
        },
    )
    env.sync_db.turns.insert_one(
        {
            "id": str(uuid.uuid4()),
            "session_id": sid,
            "turn_number": 1,
            "player_action": None,
            "narrative": historic_passage,
            "canonical_narrative": "Historic canonical passage.",
            "paragraphs": [historic_passage],
            "choices": [],
            "state": {},
            "ledger": {},
            "rolling_state": {},
        }
    )
    fake = FakeGateway(_turn(CANONICAL_ACTION)).install()
    try:
        with make_client() as client:
            acted = client.post(
                "/api/story/action",
                json={"session_id": sid, "action_text": "Wait", "action_request_id": f"act-{uuid.uuid4()}"},
                headers={DEVICE_ID_HEADER: device},
            )
            assert acted.status_code == 200, acted.text
            assert acted.json()["turn"]["narrative"] == CANONICAL_ACTION
            full = client.get(f"/api/story/session/{sid}", headers={DEVICE_ID_HEADER: device}).json()
    finally:
        fake.restore()
    assert adversarial_renderer["n"] == 0
    # Historical passage untouched; preferences preserved; route preference kept.
    assert full["turns"][0]["narrative"] == historic_passage
    assert full["session"]["mature_content"]["adult_mode_enabled"] is True
    assert full["session"]["rendering_policy"]["route"] == "mature_pinned"
    assert full["session"]["rendering_policy"]["last_status"] == mature_rendering.RENDERER_DISABLED_STATUS
    assert full["session"]["rendering_policy"]["last_renderer"] == "standard"


def test_presentation_wrapper_cannot_be_reached_by_second_provider(env, adversarial_renderer):
    """Direct wrapper call: the server-level presentation step returns canonical prose unchanged."""
    session = {
        "turn_count": 4,
        "mature_content": _adult_preferences(),
        "rendering_policy": {"route": "mature_pinned"},
    }
    rolling = {"player_age": 30, "npcs": [{"name": "Mara", "age": 30}]}
    parsed = server.ParsedTurn(
        narrative=CANONICAL_OPENING,
        paragraphs=[CANONICAL_OPENING],
        choices=[{"label": c, "text": t} for c, t in zip("ABCD", ["Wait", "Listen", "Speak", "Leave"])],
        state={"Health": "stable"},
        ledger={"Carried": "key"},
        rolling_state=dict(rolling),
        raw="",
    )
    import asyncio

    result, policy = asyncio.run(server._apply_presentation_rendering(session, parsed, rolling, "Wait"))
    assert result.narrative == CANONICAL_OPENING
    assert result.rolling_state == rolling
    assert policy["last_status"] == mature_rendering.RENDERER_DISABLED_STATUS
    assert adversarial_renderer["n"] == 0
