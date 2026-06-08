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
import gateway  # noqa: E402

import os  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


def _run(scenario):
    """Run an async scenario with a fresh Mongo client bound to THIS event loop.

    asyncio.run creates+closes a loop per test; motor caches its loop on first
    use, so each e2e test needs its own client to avoid 'Event loop is closed'.
    """
    async def wrapper():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        orig = server.db
        server.db = client[os.environ["DB_NAME"]]
        try:
            return await scenario()
        finally:
            server.db = orig
            client.close()
    return asyncio.run(wrapper())


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

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat

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
        sess, t2 = _run(scenario)
    finally:
        gateway.invoke_llm = original

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


# ---------------------------------------------------------------------------
# Destruction registry e2e — the exact live-model gap (rename instead of status)
# ---------------------------------------------------------------------------
_TD1 = _raw(
    "You stand in the dead furnace chamber, an iron lantern gripped in one hand.",
    {"scene": "furnace chamber",
     "object_locations": [{"object": "iron lantern", "status": "carried", "where": "hand"}]},
    {"Carried": "iron lantern"},
)
# Turn 2: model RENAMES the destroyed lantern to 'lantern fragments' (no status).
_TD2 = _raw(
    "You hurl the iron lantern against the stone; it bursts into useless fragments.",
    {"object_locations": [],
     "inventory_objects": [{"object": "lantern fragments", "location_state": "dropped", "condition": "broken"}]},
    {"Carried": "—"},
)
# Turn 3: model tries to bring the lantern back intact.
_TD3 = _raw(
    "The chamber is silent. Dust drifts through a shaft of broken light.",
    {"object_locations": [{"object": "iron lantern", "status": "carried", "where": "hand"}]},
    {"Carried": "iron lantern"},
)


def test_destruction_registry_end_to_end():
    scripts = [_TD1, _TD2, _TD3]
    call = {"n": 0}

    async def fake_chat(**kwargs):
        content = scripts[min(call["n"], len(scripts) - 1)]
        call["n"] += 1
        return {
            "content": content, "model_used": "test", "model_requested": "test",
            "telemetry": {"provider": "test"}, "fallback_events": [], "attempts_per_model": {},
        }

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat
    device_id = f"e2e-destroy-{uuid.uuid4()}"

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
            await server.story_action(server.ActionRequest(
                session_id=session_id, action_text="smash the lantern against the wall", debug_mode=True))
            sess_after_t2 = await server.db.sessions.find_one({"id": session_id}, {"_id": 0})
            await server.story_action(server.ActionRequest(
                session_id=session_id, action_text="pick up the iron lantern and light it", debug_mode=True))
            t3 = await server.db.turns.find_one(
                {"session_id": session_id, "turn_number": 3}, {"_id": 0})
            return sess_after_t2, t3
        finally:
            if session_id:
                await server.db.turns.delete_many({"session_id": session_id})
                await server.db.sessions.delete_one({"id": session_id})

    try:
        sess_t2, t3 = _run(scenario)
    finally:
        gateway.invoke_llm = original

    # Turn 2: destruction recorded under the ORIGINAL identity, husk gone.
    t2_locs = sess_t2["rolling_state"].get("object_locations", [])
    lantern = [r for r in t2_locs if "lantern" in str(r.get("object", "")).lower()]
    assert lantern and lantern[0]["status"] == "destroyed", f"not recorded destroyed: {t2_locs}"
    assert not any("fragment" in str(r.get("object", "")).lower()
                   for r in sess_t2["rolling_state"].get("inventory_objects", [])), "husk survived"

    # Turn 3: revival attempt stripped — lantern stays destroyed.
    t3_locs = t3["rolling_state"].get("object_locations", [])
    lantern3 = [r for r in t3_locs if "lantern" in str(r.get("object", "")).lower()]
    assert lantern3 and lantern3[0]["status"] == "destroyed", f"lantern revived: {t3_locs}"
    assert "iron lantern" not in str(t3["ledger"].get("Carried", "")).lower()


# ---------------------------------------------------------------------------
# Relationship Calculus e2e (Ch 29) — helping an NPC raises trust in state
# ---------------------------------------------------------------------------
_RC1 = _raw(
    "In the ash-choked plaza you meet Mira, a wary scavenger eyeing your pack.",
    {"scene": "plaza", "npcs": [{"name": "Mira", "stance": "neutral"}]},
    {"Carried": "knife"},
)
_RC2 = _raw(
    "You help Mira to her feet and shield her from the falling debris.",
    {"npcs": [{"name": "Mira", "stance": "neutral"}]},
    {"Carried": "knife"},
)


def test_relationship_calculus_end_to_end():
    scripts = [_RC1, _RC2]
    call = {"n": 0}

    async def fake_chat(**kwargs):
        content = scripts[min(call["n"], len(scripts) - 1)]
        call["n"] += 1
        return {"content": content, "model_used": "test", "model_requested": "test",
                "telemetry": {"provider": "test"}, "fallback_events": [], "attempts_per_model": {}}

    original = gateway.invoke_llm
    gateway.invoke_llm = fake_chat
    device_id = f"e2e-rel-{uuid.uuid4()}"

    async def scenario():
        session_id = None
        try:
            new_res = await server.new_story(server.NewStoryRequest(
                device_id=device_id, genre="post-apocalyptic", role="scavenger",
                difficulty="standard", debug_mode=True, mode="advanced"))
            session_id = new_res["session_id"]
            await server.story_action(server.ActionRequest(
                session_id=session_id, action_text="help Mira to her feet and shield her", debug_mode=True))
            t2 = await server.db.turns.find_one(
                {"session_id": session_id, "turn_number": 2}, {"_id": 0})
            return t2
        finally:
            if session_id:
                await server.db.turns.delete_many({"session_id": session_id})
                await server.db.sessions.delete_one({"id": session_id})

    try:
        t2 = _run(scenario)
    finally:
        gateway.invoke_llm = original

    vectors = t2["rolling_state"].get("relationship_vectors", [])
    mira = [v for v in vectors if v.get("name") == "Mira"]
    assert mira, f"no relationship vector for Mira: {vectors}"
    assert mira[0]["trust"] > 0, f"helping did not raise trust: {mira[0]}"
    assert "rel:" in t2["debug"].get("state_guard_adjustments", "")
