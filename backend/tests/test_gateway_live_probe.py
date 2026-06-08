"""
LIVE adversarial probe of the Anti-Hallucination Gateway (Ch 31).

Hits the public preview backend with the REAL active model (dolphin-mistral:free
with auto-fallback to anthropic/claude-3-5-haiku). Each test:
    * creates a session,
    * drives gameplay to force a terminal/dead/wounded fact,
    * tries to undo it,
    * asserts rolling_state never reverses a terminal fact and prose stays
      consistent.

Because the LLM is non-deterministic and rate-limited, each call uses a 120s
timeout, and the tests retry blunt actions a few times when the world doesn't
move into the target state. Each test cleans up its own session at the end.
"""

import os
import time
import uuid
from typing import Any, Dict, List, Optional

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
ACTION_TIMEOUT = 150  # seconds — rate-limited free model can fall back slowly
NEW_TIMEOUT = 150
EXPORT_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _new_session(client: requests.Session) -> Dict[str, Any]:
    payload = {
        "device_id": f"probe-{uuid.uuid4()}",
        "genre": "post-apocalyptic",
        "role": "scavenger",
        "difficulty": "standard",
        "debug_mode": True,
        "mode": "advanced",
    }
    r = client.post(f"{BASE_URL}/api/story/new", json=payload, timeout=NEW_TIMEOUT)
    assert r.status_code == 200, f"new_story failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert "session_id" in data, f"new_story missing session_id: {data}"
    return data


def _act(client: requests.Session, sid: str, text: str) -> Dict[str, Any]:
    payload = {"session_id": sid, "action_text": text, "debug_mode": True}
    r = client.post(f"{BASE_URL}/api/story/action", json=payload, timeout=ACTION_TIMEOUT)
    assert r.status_code == 200, f"action failed: {r.status_code} {r.text[:400]}"
    return r.json()


def _export(client: requests.Session, sid: str) -> Dict[str, Any]:
    r = client.get(f"{BASE_URL}/api/story/session/{sid}/export", timeout=EXPORT_TIMEOUT)
    assert r.status_code == 200, f"export failed: {r.status_code} {r.text[:300]}"
    return r.json()


def _delete(client: requests.Session, sid: str) -> None:
    try:
        client.delete(f"{BASE_URL}/api/story/session/{sid}", timeout=30)
    except Exception:
        pass


def _rolling(exp: Dict[str, Any]) -> Dict[str, Any]:
    return (exp.get("summary") or {}).get("rolling_state") or {}


def _turns(exp: Dict[str, Any]) -> List[Dict[str, Any]]:
    return exp.get("turns") or []


def _last_turn(exp: Dict[str, Any]) -> Dict[str, Any]:
    t = _turns(exp)
    return t[-1] if t else {}


def _terminal_object(rolling: Dict[str, Any], needle: str, statuses=("destroyed",)) -> Optional[Dict[str, Any]]:
    needle = needle.lower()
    for row in rolling.get("object_locations") or []:
        if not isinstance(row, dict):
            continue
        if needle in str(row.get("object", "")).lower() and str(row.get("status", "")).lower() in statuses:
            return row
    return None


def _ledger_carried(turn: Dict[str, Any]) -> str:
    ledger = turn.get("ledger") or {}
    return str(ledger.get("Carried", "")).lower()


def _narrative(turn: Dict[str, Any]) -> str:
    return str(turn.get("narrative") or "").lower()


def _debug_field(turn: Dict[str, Any], key: str) -> str:
    return str((turn.get("debug") or {}).get(key, ""))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def session(api_client):
    assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL not set"
    info = _new_session(api_client)
    sid = info["session_id"]
    yield sid, info
    _delete(api_client, sid)


# ---------------------------------------------------------------------------
# Test 1 — destroyed item revival blocked
# ---------------------------------------------------------------------------
def test_destroyed_item_cannot_be_revived(api_client, session):
    sid, _ = session

    destroy_actions = [
        "I take the iron lantern in both hands and smash it against the stone wall repeatedly until the glass and metal shatter into pieces.",
        "I stomp on the broken lantern with my boot, grinding the shards into the floor until nothing usable remains.",
        "I kick the remaining pieces of the lantern into the fire pit so they melt and burn away forever.",
    ]
    destroyed_row = None
    target_token = "lantern"
    for action in destroy_actions:
        try:
            _act(api_client, sid, action)
        except AssertionError as e:
            pytest.skip(f"action failed (live model): {e}")
        rolling = _rolling(_export(api_client, sid))
        destroyed_row = _terminal_object(rolling, target_token, ("destroyed",))
        if destroyed_row:
            break
        time.sleep(1)

    if not destroyed_row:
        # try generic "torch" as fallback target if lantern never appeared
        for action in [
            "I throw my torch into the open furnace and watch it burn down to ash, completely consumed and destroyed.",
        ]:
            try:
                _act(api_client, sid, action)
            except AssertionError as e:
                pytest.skip(f"action failed (live model): {e}")
            rolling = _rolling(_export(api_client, sid))
            destroyed_row = _terminal_object(rolling, "torch", ("destroyed",))
            if destroyed_row:
                target_token = "torch"
                break

    if not destroyed_row:
        pytest.skip("Could not drive any object to status='destroyed' via live model in 3-4 turns.")

    # Now attempt revival
    revive_actions = [
        f"I pick up the {target_token} from the ground and hold it up to light my way.",
        f"I grab the {target_token} and use it again as if it were intact.",
    ]
    for action in revive_actions:
        try:
            _act(api_client, sid, action)
        except AssertionError as e:
            pytest.fail(f"revive action failed: {e}")

    exp = _export(api_client, sid)
    rolling = _rolling(exp)
    last = _last_turn(exp)

    # Assertion 1: object still destroyed in rolling_state
    still_destroyed = _terminal_object(rolling, target_token, ("destroyed", "consumed"))
    assert still_destroyed is not None, (
        f"Terminal object '{target_token}' was revived in rolling_state: "
        f"{rolling.get('object_locations')}"
    )

    # Assertion 2: ledger Carried does not list it
    carried = _ledger_carried(last)
    assert target_token not in carried, (
        f"Destroyed '{target_token}' still in player ledger Carried: {carried!r}"
    )

    # Assertion 3: prose did not describe holding/using the intact item
    # (soft check — narrative may reference it as a memory; we only fail if
    # there's a clear possession phrase next to the token)
    narrative = _narrative(last)
    possession_hits = [
        f"pick up the {target_token}",
        f"grab the {target_token}",
        f"hold the {target_token}",
        f"using the {target_token}",
        f"raise the {target_token}",
    ]
    # Allow if narrative qualifies it as broken/destroyed/another
    for phrase in possession_hits:
        if phrase in narrative:
            window = narrative.split(phrase)[0][-80:] + phrase + narrative.split(phrase, 1)[1][:80]
            if not any(q in window for q in ("broken", "shattered", "ash", "remains", "another", "spare", "destroyed", "ruined", "memory")):
                pytest.fail(f"Prose describes using intact '{target_token}': ...{window}...")


# ---------------------------------------------------------------------------
# Test 2 — consumed item reuse blocked
# ---------------------------------------------------------------------------
def test_consumed_item_cannot_be_reused(api_client, session):
    sid, _ = session

    consume_actions = [
        "I unwrap my last ration and eat every bite of it, finishing it completely so nothing remains.",
        "I scrape out the last crumbs of my ration from the wrapper, chew them, then crumple the empty wrapper and toss it aside.",
        "I drink the last of the water from my canteen in one long swallow, draining it completely.",
    ]
    target_token = None
    for action in consume_actions:
        try:
            _act(api_client, sid, action)
        except AssertionError as e:
            pytest.skip(f"action failed (live model): {e}")
        rolling = _rolling(_export(api_client, sid))
        for token in ("ration", "water", "canteen"):
            row = _terminal_object(rolling, token, ("consumed",))
            if row:
                target_token = token
                break
        if target_token:
            break
        time.sleep(1)

    if not target_token:
        pytest.skip("Could not drive any object to status='consumed' via live model.")

    # Attempt to reuse
    try:
        _act(api_client, sid, f"I open my pack and eat the {target_token} again, savouring every bite.")
        _act(api_client, sid, f"I take another long drink from the {target_token}.")
    except AssertionError as e:
        pytest.fail(f"reuse action failed: {e}")

    exp = _export(api_client, sid)
    rolling = _rolling(exp)
    last = _last_turn(exp)

    row = _terminal_object(rolling, target_token, ("consumed",))
    assert row is not None, (
        f"'{target_token}' status changed away from consumed: {rolling.get('object_locations')}"
    )
    carried = _ledger_carried(last)
    assert target_token not in carried, (
        f"Consumed '{target_token}' re-added to Carried: {carried!r}"
    )


# ---------------------------------------------------------------------------
# Test 3 — dead NPC cannot be revived
# ---------------------------------------------------------------------------
def test_dead_npc_cannot_be_revived(api_client, session):
    sid, _ = session

    # Force at least one named NPC into the scene then kill them.
    setup_actions = [
        "A lone guard named Garrett blocks the doorway ahead of me. I draw my knife and lock eyes with him.",
        "I lunge forward and stab Garrett in the throat, twisting the blade until he chokes, collapses, and dies on the spot.",
        "I stand over Garrett's lifeless body, confirming he is dead. He does not move. He does not breathe.",
    ]
    for action in setup_actions:
        try:
            _act(api_client, sid, action)
        except AssertionError as e:
            pytest.skip(f"setup action failed: {e}")
        time.sleep(0.5)

    exp = _export(api_client, sid)
    rolling = _rolling(exp)
    deceased = [str(n).lower() for n in (rolling.get("deceased") or [])]

    if "garrett" not in deceased:
        # try one more push
        try:
            _act(api_client, sid, "I check Garrett's pulse — there is none. Garrett is dead. Garrett has died from his wounds.")
        except AssertionError as e:
            pytest.skip(f"death push failed: {e}")
        exp = _export(api_client, sid)
        rolling = _rolling(exp)
        deceased = [str(n).lower() for n in (rolling.get("deceased") or [])]

    if "garrett" not in deceased:
        pytest.skip(f"Could not drive NPC 'Garrett' into deceased registry. deceased={deceased}")

    # Now try to interact with the dead NPC
    try:
        _act(api_client, sid, "I shake Garrett by the shoulders and ask him for help finding the exit.")
        _act(api_client, sid, "Garrett, please answer me — which way is out of here?")
    except AssertionError as e:
        pytest.fail(f"revive interaction failed: {e}")

    exp = _export(api_client, sid)
    rolling = _rolling(exp)
    last = _last_turn(exp)

    deceased = [str(n).lower() for n in (rolling.get("deceased") or [])]
    assert "garrett" in deceased, (
        f"Dead NPC Garrett removed from deceased registry: {rolling.get('deceased')}"
    )
    # If any npcs entry for Garrett, stance must be 'dead'
    for npc in rolling.get("npcs") or []:
        if str(npc.get("name", "")).lower() == "garrett":
            assert str(npc.get("stance", "")).lower() == "dead", (
                f"Dead NPC Garrett has live stance: {npc}"
            )

    # Prose check: dead NPC should not be speaking/acting alive
    narrative = _narrative(last)
    bad_phrases = [
        "garrett says", "garrett asks", "garrett replies", "garrett whispers",
        "garrett shouts", "garrett laughs", "garrett nods", "garrett smiles",
        "garrett stands", "garrett walks", "garrett steps",
    ]
    for phrase in bad_phrases:
        if phrase in narrative:
            # Allow if framed as memory/ghost/dream
            window_idx = narrative.find(phrase)
            window = narrative[max(0, window_idx - 60): window_idx + 60]
            if not any(q in window for q in ("dream", "remember", "ghost", "spirit", "memory", "vision", "imagin")):
                pytest.fail(f"Dead Garrett speaks/acts alive in prose: ...{window}...")


# ---------------------------------------------------------------------------
# Test 4 — silent injury healing blocked
# ---------------------------------------------------------------------------
def test_silent_injury_healing_blocked(api_client, session):
    sid, _ = session

    wound_actions = [
        "I throw my full weight against the rusted iron door, smashing through it. A jagged shard of metal rips deep into my leg, gashing it badly. Blood pours from the wound.",
        "I look down at the deep, bleeding gash on my leg. It is a serious wound — the bone may be exposed.",
    ]
    prior_injury = None
    for action in wound_actions:
        try:
            _act(api_client, sid, action)
        except AssertionError as e:
            pytest.skip(f"wound action failed: {e}")
        exp = _export(api_client, sid)
        rolling = _rolling(exp)
        for row in rolling.get("injuries") or []:
            sev = str(row.get("severity", "")).lower()
            status = str(row.get("status", "")).lower()
            if sev in ("severe", "critical") or status in ("active", "worsening"):
                prior_injury = row
                break
        if prior_injury:
            break
        time.sleep(0.5)

    if not prior_injury:
        pytest.skip("Could not drive a serious/active injury via live model.")

    prior_sev = str(prior_injury.get("severity", "")).lower()
    prior_name = str(prior_injury.get("name", "")).lower()

    # No-recovery-cue action
    try:
        _act(api_client, sid, "I grit my teeth and sprint full speed down the dark corridor without stopping.")
        _act(api_client, sid, "I keep running, ignoring everything around me, focused only on the path ahead.")
    except AssertionError as e:
        pytest.fail(f"no-recovery action failed: {e}")

    exp = _export(api_client, sid)
    rolling = _rolling(exp)

    severity_rank = {"minor": 1, "moderate": 2, "severe": 3, "critical": 4}
    resolved = {"resolved", "healed", "cleared", "gone", "fine", "cured"}

    # Find the matching injury
    matched = None
    for row in rolling.get("injuries") or []:
        nm = str(row.get("name", "")).lower()
        if prior_name and (nm == prior_name or prior_name in nm or nm in prior_name):
            matched = row
            break
    if not matched and rolling.get("injuries"):
        # Use first injury if names diverge
        matched = rolling["injuries"][0]

    if not matched:
        pytest.fail(
            f"Serious injury silently disappeared from rolling_state. "
            f"prior={prior_injury}, current_injuries={rolling.get('injuries')}"
        )

    new_status = str(matched.get("status", "")).lower()
    new_sev = str(matched.get("severity", "")).lower()
    assert new_status not in resolved, (
        f"Injury silently resolved without recovery cue: prior={prior_injury}, now={matched}"
    )
    if prior_sev in severity_rank and new_sev in severity_rank:
        assert severity_rank[new_sev] >= severity_rank[prior_sev], (
            f"Injury severity silently downgraded {prior_sev} -> {new_sev}: prior={prior_injury}, now={matched}"
        )


# ---------------------------------------------------------------------------
# Test 5 — prose-vs-state contradiction triggers correction/strip
# ---------------------------------------------------------------------------
def test_prose_state_contradiction_correction(api_client, session):
    """
    Drives a terminal item OR dead NPC, then takes contradiction-bait actions
    over a few turns and looks for gateway adjustments OR a hallucination
    re-prompt anywhere in the recent turn debug.
    """
    sid, _ = session

    # Try to lock in a destroyed object (cheapest path).
    try:
        _act(api_client, sid, "I take the iron lantern and smash it on the rocks until the glass shatters and the metal frame is twisted beyond use, destroyed forever.")
        _act(api_client, sid, "I grind the broken lantern pieces underfoot until nothing remains intact.")
    except AssertionError as e:
        pytest.skip(f"destroy action failed: {e}")

    rolling = _rolling(_export(api_client, sid))
    has_terminal = bool(_terminal_object(rolling, "lantern", ("destroyed", "consumed")))

    if not has_terminal:
        # try torch
        try:
            _act(api_client, sid, "I throw my torch into the deep furnace; it is consumed in the flames, gone forever.")
        except AssertionError as e:
            pytest.skip(f"fallback destroy failed: {e}")
        rolling = _rolling(_export(api_client, sid))
        has_terminal = bool(_terminal_object(rolling, "torch", ("destroyed", "consumed")))

    if not has_terminal:
        pytest.skip("Could not establish any terminal object for contradiction probe.")

    # Bait contradictions over a couple of turns
    for action in [
        "I draw the lantern from my belt, raise it high, and let it cast bright light around me.",
        "I use my torch as a club, swinging it intact at the shadow.",
        "I pick up the lantern and walk forward, lighting my way clearly.",
    ]:
        try:
            _act(api_client, sid, action)
        except AssertionError as e:
            pytest.fail(f"contradiction bait failed: {e}")

    exp = _export(api_client, sid)
    rolling = _rolling(exp)
    turns = _turns(exp)
    # Inspect the last 3 turns' debug
    recent = turns[-3:] if len(turns) >= 3 else turns

    gateway_markers = []
    retry_kinds = []
    for t in recent:
        adj = _debug_field(t, "state_guard_adjustments")
        rk = _debug_field(t, "validation_retry_kind")
        if "gateway:" in adj:
            gateway_markers.append(adj)
        if rk:
            retry_kinds.append(rk)

    assert gateway_markers or ("hallucination" in retry_kinds), (
        f"No gateway adjustment or hallucination re-prompt fired across {len(recent)} bait turns. "
        f"adjustments_seen={[_debug_field(t, 'state_guard_adjustments') for t in recent]}; "
        f"retry_kinds_seen={retry_kinds}"
    )

    # Final consistency: terminal object is STILL terminal in final state.
    final_terminal = (
        _terminal_object(rolling, "lantern", ("destroyed", "consumed"))
        or _terminal_object(rolling, "torch", ("destroyed", "consumed"))
    )
    assert final_terminal is not None, (
        f"Final rolling_state lost terminal status: {rolling.get('object_locations')}"
    )
