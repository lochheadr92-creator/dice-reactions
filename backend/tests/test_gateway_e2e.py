"""
End-to-end Anti-Hallucination Gateway test (Ch 31) through the real routes.

Drives `new_story` + `story_action` with a SCRIPTED LLM (chat_completion_with_meta
is monkeypatched) so the test is fully deterministic. Verifies:
  • death registry records a clear NPC death on turn 1,
  • immutable-truth block is injected into the turn-2 prompt,
  • a contradictory turn-2 draft (revived object + dead NPC speaking) triggers the
    hallucination correction re-prompt,
  • the route STRIPS the revived terminal object and the deceased NPC from state,
  • the player ledger no longer carries the destroyed object.

Runs against the local Mongo configured in backend/.env. Cleans up after itself.
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402


def _raw(narrative, rolling_state, ledger, choices="A. Go left\nB. Go right\nC. Wait\nD. Listen"):
    return (
        f"<narrative>\n{narrative}\n</narrative>\n"
        f"<choices>\n{choices}\n</choices>\n"
        f"<state>\nHealth: wounded\n</state>\n"
        f"<ledger>\n" + "\n".join(f"{k}: {v}" for k, v in ledger.items()) + "\n</ledger>\n"
        f"<rolling_state>\n{json.dumps(rolling_state)}\n</rolling_state>\n"
    )


TURN1 = _raw(
    "The furnace roars white-hot. The iron key melts to slag in your fist, destroyed. "
    "Across the chamber Garrett lies dead, crushed by the fallen beam. Only Mira still "
    "breathes, pressed flat against the wall.",
    {
        "scene": "a collapsing furnace chamber",
        "object_locations": [{"object": "iron key", "status": "destroyed", "where": "furnace"}],
        "npcs": [{"name": "Garrett", "stance": "unknown"}, {"name": "Mira", "stance": "neutral"}],
        "npc_memory": [
            {"name": "Garrett", "remembers": [{"event": "crushed in the collapse", "severity": "major", "since_turn": 1}]},
            {"name": "Mira", "remembers": [{"event": "survived beside the player", "severity": "major", "since_turn": 1}], "goal": "escape", "next_move": "follow the player"},
        ],
    },
    {"Carried": "torch"},
)

# Turn-2 draft 1: blatantly contradicts truth (revives the key, dead Garrett talks).
TURN2_BAD = _raw(
    "You grab the iron key from the rubble and slip it into your pocket. "
    "Garrett says you should hurry before the roof falls.",
    {
        "object_locations": [{"object": "iron key", "status": "carried", "where": "pocket"}],
        "npcs": [{"name": "Garrett", "stance": "ally", "last_seen": "chamber"}],
        "npc_memory": [{"name": "Garrett", "next_move": "help you escape"}],
    },
    {"Carried": "torch; iron key"},
)

# Turn-2 draft 2 (retry): prose is now clean, but state STILL tries to revive both.
TURN2_RETRY = _raw(
    "The chamber is silent. Dust drifts through a shaft of broken light. "
    "Nothing stirs in the rubble around you.",
    {
        "object_locations": [{"object": "iron key", "status": "carried", "where": "pocket"}],
        "npcs": [{"name": "Garrett", "stance": "ally", "last_seen": "chamber"}],
        "npc_memory": [{"name": "Garrett", "next_move": "help you escape"}],
    },
    {"Carried": "torch; iron key"},
)


def test_gateway_end_to_end():
    captured = {"messages": []}
    scripts = [TURN1, TURN2_BAD, TURN2_RETRY]
    call = {"n": 0}

    async def fake_chat(**kwargs):
        captured["messages"].append(kwargs.get("messages"))
        idx = min(call["n"], len(scripts) - 1)
        content = scripts[idx]
        call["n"] += 1
        return {
            "content": content,
            "model_used": "test-model",
            "model_requested": "test-model",
            "telemetry": {"provider": "test", "status": "ok"},
            "fallback_events": [],
            "attempts_per_model": {},
        }

    original = server.chat_completion_with_meta
    server.chat_completion_with_meta = fake_chat

    device_id = f"e2e-{uuid.uuid4()}"

    async def scenario():
        session_id = None
        try:
            new_res = await server.new_story(
                server.NewStoryRequest(
                    device_id=device_id, genre="post-apocalyptic", role="scavenger",
                    difficulty="standard", debug_mode=True, mode="advanced",
                )
            )
            session_id = new_res["session_id"]

            # Turn 1 persisted: Garrett recorded deceased, key destroyed.
            sess = await server.db.sessions.find_one({"id": session_id}, {"_id": 0})

            # Turn 2 action.
            await server.story_action(
                server.ActionRequest(
                    session_id=session_id, action_text="search the room for tools", debug_mode=True
                )
            )
            t2 = await server.db.turns.find_one(
                {"session_id": session_id, "turn_number": 2}, {"_id": 0}
            )
            return sess, t2
        finally:
            if session_id:
                await server.db.turns.delete_many({"session_id": session_id})
                await server.db.sessions.delete_one({"id": session_id})

    try:
        sess, t2 = asyncio.run(scenario())
    finally:
        server.chat_completion_with_meta = original

    # --- Turn 1: death recorded, no false positives. ---
    assert "Garrett" in (sess["rolling_state"].get("deceased") or []), "death not recorded"
    assert "Mira" not in (sess["rolling_state"].get("deceased") or []), "false death"

    # --- Truth injection: turn-2 prompt must carry the established_truth block. ---
    turn2_prompt = "\n".join(
        m.get("content", "") for m in (captured["messages"][1] or [])
    )
    assert "established_truth" in turn2_prompt, "truth block not injected"
    assert "iron key" in turn2_prompt.lower()

    # --- Correction re-prompt fired (3 LLM calls: t1, t2-bad, t2-retry). ---
    assert call["n"] == 3, f"expected 3 LLM calls, got {call['n']}"
    assert t2["debug"].get("validation_retry_kind") == "hallucination"

    rolling = t2["rolling_state"]
    # --- Terminal object stays destroyed despite the model reviving it. ---
    key_rows = [r for r in rolling.get("object_locations", []) if "key" in str(r.get("object", "")).lower()]
    assert key_rows and key_rows[0]["status"] == "destroyed", f"key revived: {key_rows}"

    # --- Deceased NPC stays dead. ---
    assert "Garrett" in (rolling.get("deceased") or [])
    garrett = [n for n in rolling.get("npcs", []) if n.get("name") == "Garrett"]
    assert garrett and garrett[0].get("stance") == "dead", f"Garrett revived: {garrett}"

    # --- Player ledger no longer carries the destroyed key. ---
    assert "iron key" not in str(t2["ledger"].get("Carried", "")).lower()

    # --- Gateway adjustments are recorded for diagnostics. ---
    adj = t2["debug"].get("state_guard_adjustments", "")
    assert "gateway:" in adj, f"no gateway adjustments logged: {adj}"
