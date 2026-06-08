"""
Live E2E verification of Ch 29 Relationship Calculus against the real public API
and a live LLM. Covers Tests A–F from the iteration_5 review request.

Design choices:
  - One driver session walks the full positive→hostile→betrayal→decay arc so we
    pay the LLM cost once. Each turn ~14-27s under claude-3-5-haiku.
  - A second tiny session exercises the regression path (Test F) so the long arc
    cannot mask a smoke regression.
  - All assertions are made against /export -> summary.rolling_state and against
    per-turn debug.state_guard_adjustments ('rel:' markers).
"""

from __future__ import annotations

import os
import re
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
TIMEOUT = 120  # per-turn LLM budget
DIMENSIONS = ("trust", "loyalty", "fear", "resentment")
EXPECTED_STATES = {
    "neutral", "wary", "trusting", "resentful", "devoted",
    "cowed", "collapsed", "betrayal_risk",
}


def _ensure_url():
    assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL is not configured"


def _post(client, path, payload, timeout=TIMEOUT):
    r = client.post(f"{BASE_URL}{path}", json=payload, timeout=timeout)
    assert r.status_code == 200, f"POST {path} -> {r.status_code}: {r.text[:400]}"
    return r.json()


def _export(client, sid):
    r = client.get(f"{BASE_URL}/api/story/session/{sid}/export", timeout=30)
    assert r.status_code == 200, f"export -> {r.status_code}: {r.text[:400]}"
    return r.json()


def _vec(rolling, name):
    for v in (rolling or {}).get("relationship_vectors") or []:
        if str(v.get("name", "")).lower() == name.lower():
            return v
    return None


def _last_turn_debug(export_json):
    turns = export_json.get("turns") or []
    if not turns:
        return {}
    return (turns[-1].get("debug") or {})


def _pick_named_npc(rolling):
    """Pick the first usable NPC name from rolling_state.npcs.

    Accept any non-trivial name. We deliberately allow generic placeholders
    (e.g. "Unknown Survivor", "The Stranger") because the engine matches by
    literal name — what matters is that we address THAT exact label in the
    action text, which preserves verb-near-name proximity for event detection.
    """
    for row in (rolling or {}).get("npcs") or []:
        name = str((row or {}).get("name", "")).strip()
        if not name or len(name) < 2:
            continue
        if name.lower() in {"the player", "player", "you"}:
            continue
        if len(name.split()) > 5:
            continue
        return name
    return None


@pytest.fixture(scope="module")
def client():
    _ensure_url()
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------------------------------------------------------------------
# Test F (regression): /story/new and one /story/action stay well-formed.
# Runs FIRST so a broken backend fails fast.
# ---------------------------------------------------------------------------
def test_F_regression_new_and_action_well_formed(client):
    device = f"TEST_rel_reg_{uuid.uuid4().hex[:8]}"
    new = _post(client, "/api/story/new", {
        "device_id": device, "genre": "post-apocalyptic", "role": "scavenger",
        "difficulty": "standard", "debug_mode": True, "mode": "advanced",
    })
    sid = new["session_id"]
    try:
        t0 = new["turn"]
        assert isinstance(t0.get("narrative"), str) and t0["narrative"].strip()
        assert isinstance(t0.get("choices"), list) and 4 <= len(t0["choices"]) <= 6
        assert isinstance(t0.get("state"), dict)
        assert isinstance(t0.get("ledger"), (dict, list))

        action = _post(client, "/api/story/action", {
            "session_id": sid, "action_text": "look around carefully",
            "debug_mode": True,
        })
        t = action["turn"]
        assert isinstance(t.get("narrative"), str) and t["narrative"].strip()
        assert isinstance(t.get("choices"), list) and 4 <= len(t["choices"]) <= 6
    finally:
        client.delete(f"{BASE_URL}/api/story/session/{sid}", timeout=15)


# ---------------------------------------------------------------------------
# Test A–E (long arc): build a positive vector, swing hostile + betray,
# then idle to verify decay. Skipped if no named NPC ever appears (LLM choice).
# ---------------------------------------------------------------------------
def test_ABCDE_full_relationship_arc(client):
    device = f"TEST_rel_arc_{uuid.uuid4().hex[:8]}"
    new = _post(client, "/api/story/new", {
        "device_id": device, "genre": "post-apocalyptic", "role": "scavenger",
        "difficulty": "standard", "debug_mode": True, "mode": "advanced",
    })
    sid = new["session_id"]

    try:
        # Step 1: find a named NPC. Try the opening; if none, take a "call out" action.
        export = _export(client, sid)
        rolling = export.get("summary", {}).get("rolling_state") or {}
        npc = _pick_named_npc(rolling)

        if not npc:
            _post(client, "/api/story/action", {
                "session_id": sid,
                "action_text": "call out to anyone nearby and approach the nearest survivor",
                "debug_mode": True,
            })
            export = _export(client, sid)
            rolling = export.get("summary", {}).get("rolling_state") or {}
            npc = _pick_named_npc(rolling)

        if not npc:
            pytest.skip("No named NPC introduced by the LLM in the first 1-2 turns; "
                        "cannot exercise relationship events without a target.")

        print(f"[rel-live] target NPC = {npc!r}")

        # ---------- Test A: positive events ----------
        for action in (
            f"help {npc} to safety and offer water",
            f"protect {npc} from the noise outside, shield {npc} with my body",
        ):
            _post(client, "/api/story/action", {
                "session_id": sid, "action_text": action, "debug_mode": True,
            })
            time.sleep(0.5)

        export = _export(client, sid)
        rolling = export.get("summary", {}).get("rolling_state") or {}
        v = _vec(rolling, npc)
        assert v is not None, f"no relationship_vector row for {npc!r}: {rolling.get('relationship_vectors')}"
        for d in DIMENSIONS + ("name", "state", "last_turn", "bond"):
            assert d in v, f"vector missing key {d!r}: {v}"
        assert v["state"] in EXPECTED_STATES, f"unexpected state {v['state']!r}"
        # canonical shape sanity
        assert -100 <= v["trust"] <= 100
        for d in ("loyalty", "fear", "resentment"):
            assert 0 <= v[d] <= 100, f"{d} out of range: {v[d]}"

        # Test A assertion: trust or loyalty has risen above zero.
        assert v["trust"] > 0 or v["loyalty"] > 0, (
            f"after help+protect, expected trust or loyalty > 0; vec={v}"
        )
        positive_trust = v["trust"]
        positive_loyalty = v["loyalty"]

        # state_guard_adjustments may be a list OR a single concatenated string
        # per turn. Scan all turns and collapse to one big text blob.
        adj_blob = ""
        for t in export.get("turns") or []:
            sga = (t.get("debug") or {}).get("state_guard_adjustments") or []
            if isinstance(sga, str):
                adj_blob += " " + sga
            elif isinstance(sga, list):
                adj_blob += " " + " ".join(str(x) for x in sga)
        rel_markers = re.findall(r"rel:[^;|]+", adj_blob)
        assert rel_markers, (
            f"no 'rel:' state_guard_adjustments fired across turns; blob={adj_blob[:600]!r}"
        )

        # ---------- Test B: hostile events ----------
        for action in (
            f"threaten {npc} at knifepoint to back off",
            f"attack {npc}, strike {npc} hard across the face",
        ):
            _post(client, "/api/story/action", {
                "session_id": sid, "action_text": action, "debug_mode": True,
            })
            time.sleep(0.5)

        export = _export(client, sid)
        rolling = export.get("summary", {}).get("rolling_state") or {}
        v = _vec(rolling, npc)
        assert v is not None
        # fear and/or resentment up, trust dropped from positive peak
        assert v["fear"] > 0 or v["resentment"] > 0, f"hostile events did not raise fear/resentment; vec={v}"
        assert v["trust"] < positive_trust, (
            f"trust did not fall after hostility (was {positive_trust}, now {v['trust']})"
        )
        # negative-leaning state expected
        assert v["state"] in {"wary", "resentful", "cowed", "collapsed", "betrayal_risk", "neutral"}, (
            f"unexpected state after hostility: {v['state']}"
        )

        # ---------- Test C: betrayal -> extreme state + stance flip ----------
        _post(client, "/api/story/action", {
            "session_id": sid,
            "action_text": f"betray {npc} and hand {npc} over to the raiders",
            "debug_mode": True,
        })
        time.sleep(0.5)

        export = _export(client, sid)
        rolling = export.get("summary", {}).get("rolling_state") or {}
        v = _vec(rolling, npc)
        assert v is not None
        # state must be one of the extreme negative states
        assert v["state"] in {"collapsed", "betrayal_risk", "resentful", "cowed"}, (
            f"after betrayal expected extreme negative state; got {v['state']} vec={v}"
        )
        assert v["resentment"] >= 40, f"resentment did not climb after betrayal: {v}"

        # stance flip: NPC row may be removed if killed by the LLM; only assert if present.
        npc_row = next(
            (r for r in (rolling.get("npcs") or []) if str(r.get("name", "")).lower() == npc.lower()),
            None,
        )
        if npc_row is not None and str(npc_row.get("stance", "")).lower() != "dead":
            assert str(npc_row.get("stance", "")).lower() in {"hostile", "neutral", "wary"}, (
                f"expected hostile-leaning stance after betrayal; got {npc_row.get('stance')}"
            )

        # ---------- Test D: decay on neglect ----------
        # Snapshot pre-decay magnitudes (sum of abs values).
        pre = {d: v[d] for d in DIMENSIONS}
        pre_mag = abs(pre["trust"]) + pre["fear"] + pre["resentment"]

        for action in (
            "walk on alone, scan the ruins ahead",
            "search a collapsed building for supplies",
            "check my pack and sip from my canteen",
        ):
            _post(client, "/api/story/action", {
                "session_id": sid, "action_text": action, "debug_mode": True,
            })
            time.sleep(0.5)

        export = _export(client, sid)
        rolling = export.get("summary", {}).get("rolling_state") or {}
        v = _vec(rolling, npc)
        if v is None:
            # The NPC may have exited the scene; that's acceptable since the
            # engine still tracks them via prior_rolling. Skip decay check rather
            # than fail spuriously.
            pytest.skip(f"NPC {npc!r} fell out of rolling_state.npcs after neglect; "
                        "decay vector tracking via prior_rolling cannot be re-asserted here.")

        post_mag = abs(v["trust"]) + v["fear"] + v["resentment"]
        # Magnitude must shrink (decay toward neutral) but not snap to zero.
        assert post_mag < pre_mag, (
            f"vector did not decay across 3 neutral turns: pre={pre}, post={v}"
        )
        assert post_mag > 0, f"vector snapped to all zeros in one stretch (suspicious): {v}"
        # loyalty barely changes (decay 0.01 / turn)
        assert abs(v["loyalty"] - pre["loyalty"]) <= 6, (
            f"loyalty decayed too fast: pre={pre['loyalty']} -> post={v['loyalty']}"
        )

        # ---------- Test E (qualitative): narrative tone vs vector ----------
        # We do NOT fail on tone — just record a soft observation.
        last_narr = (export.get("turns") or [])[-1].get("narrative", "")[:600]
        print(f"[rel-live] final vec for {npc!r} = {v}")
        print(f"[rel-live] last narrative snippet: {last_narr!r}")

    finally:
        client.delete(f"{BASE_URL}/api/story/session/{sid}", timeout=15)
