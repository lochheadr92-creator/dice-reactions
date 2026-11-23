"""
Mature renderer switched ON: full story-creation + action path.

The renderer's provider call must run inside the request's provider budget,
the faithful rewrite is served, and the canonical narrative is still stored.
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
import provider_budget  # noqa: E402
from security import DEVICE_ID_HEADER  # noqa: E402
from reliability_support import (  # noqa: E402
    FakeGateway,
    MongoEnv,
    make_client,
    relax_rate_limits,
)

# One paragraph, so these stories use the short turn length (1 to 2 paragraphs). At the default
# length a one-paragraph reply is re-broken at delivery (review 2, finding 3).
CANONICAL_OPENING = "Mara waits outside the locked gate. The key remains in your pocket."
CANONICAL_ACTION = "Mara still waits outside the locked gate. The key stays in your pocket."
RENDERED = {
    CANONICAL_OPENING: "Mara waits, rigid and silent, outside the locked gate. The key remains heavy in your pocket.",
    CANONICAL_ACTION: "Mara still waits, jaw tight, outside the locked gate. The key stays cold in your pocket.",
}


def _turn(narrative: str, choices: str) -> str:
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
    monkeypatch.setattr(mature_rendering, "MATURE_RENDERER_ENABLED", True)
    monkeypatch.setattr(mature_rendering, "get_mature_model_id", lambda: "x-ai/grok-pinned-2026-01")
    monkeypatch.setattr(mature_rendering, "model_is_configured", lambda _m: True)
    yield mongo
    mongo.close()


@pytest.fixture()
def renderer(monkeypatch):
    calls = {"n": 0, "budget_active": []}

    async def rewrite(**kwargs):
        calls["n"] += 1
        calls["budget_active"].append(provider_budget._ACTIVE.get() is not None)
        source = kwargs["messages"][-1]["content"].split("<narrative>\n", 1)[1].split("\n</narrative>")[0]
        return {"content": f"<narrative>{RENDERED[source]}</narrative>"}

    monkeypatch.setattr(mature_rendering, "chat_completion_strict_with_meta", rewrite)
    return calls


def test_enabled_renderer_runs_inside_budget_and_serves_rewrite(env, renderer):
    device = f"dev_{uuid.uuid4()}"

    def by_request(_n, kwargs):
        texts = " ".join(str(m.get("content", "")) for m in kwargs.get("messages", []))
        if "Player action:" in texts:
            return _turn(CANONICAL_ACTION, "A. Try the key\nB. Knock twice\nC. Ask Mara to step back\nD. Circle the wall")
        return _turn(CANONICAL_OPENING, "A. Wait\nB. Listen\nC. Speak to Mara\nD. Leave")

    fake = FakeGateway(on_request=by_request).install()
    try:
        with make_client() as client:
            caps = client.get("/api/setup/capabilities").json()["distribution_capabilities"]
            assert caps["mature_renderer_configured"] is True
            created = client.post(
                "/api/story/new",
                json={
                    "device_id": device,
                    "genre": "fantasy",
                    "prose_mode": "brief",
                    "mature_content": {
                        **mature_content.default_mature_content(),
                        "adult_mode_enabled": True,
                        "adult_age_confirmed": True,
                        "violence_level": "graphic",
                    },
                    "creation_request_id": f"create-{uuid.uuid4()}",
                },
            )
            assert created.status_code == 200, created.text
            sid = created.json()["session_id"]
            assert created.json()["turn"]["narrative"] == RENDERED[CANONICAL_OPENING]
            assert created.json()["session"]["rendering_policy"]["last_status"] == "rendered_mature"

            acted = client.post(
                "/api/story/action",
                json={"session_id": sid, "action_text": "Wait", "action_request_id": f"act-{uuid.uuid4()}"},
                headers={DEVICE_ID_HEADER: device},
            )
            assert acted.status_code == 200, acted.text
            assert acted.json()["turn"]["narrative"] == RENDERED[CANONICAL_ACTION]
    finally:
        fake.restore()

    assert renderer["n"] == 2
    assert renderer["budget_active"] == [True, True]
    turns = list(env.sync_db.turns.find({"session_id": sid}).sort("turn_number", 1))
    assert [t["canonical_narrative"] for t in turns] == [CANONICAL_OPENING, CANONICAL_ACTION]
    assert [t["narrative"] for t in turns] == [RENDERED[CANONICAL_OPENING], RENDERED[CANONICAL_ACTION]]
