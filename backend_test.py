"""
Backend test for Dice Reaction Story Engine — OpenRouter migration.

Covers:
  - GET /api/health
  - GET /api/admin/settings
  - GET /api/admin/models
  - POST /api/admin/settings (valid patches + validation rejections)
  - POST /api/story/new + /api/story/action (using free-tier model)
  - GET /api/story/sessions, /api/story/session/{id}, .../latest
  - DELETE /api/story/session/{id}

Always restores the active model back to gryphe/mythomax-l2-13b at the end.
"""

import json
import os
import sys
import time
import uuid
from typing import Any, Dict, Optional

import requests

# Load backend public URL from frontend env (per testing rules)
FRONTEND_ENV = "/app/frontend/.env"
BACKEND_URL = None
with open(FRONTEND_ENV, "r", encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BACKEND_URL = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

assert BACKEND_URL, "EXPO_PUBLIC_BACKEND_URL missing from /app/frontend/.env"
API = f"{BACKEND_URL}/api"

FREE_MODEL = "openai/gpt-oss-120b:free"
DEFAULT_MODEL = "gryphe/mythomax-l2-13b"

results: Dict[str, Dict[str, Any]] = {}
device_id = f"tester-{uuid.uuid4().hex[:10]}"


def record(name: str, ok: bool, detail: str = "", payload: Optional[Any] = None):
    results[name] = {"ok": ok, "detail": detail, "payload_keys": list(payload.keys()) if isinstance(payload, dict) else None}
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name} :: {detail}")


def get(path: str, **kw):
    return requests.get(f"{API}{path}", timeout=60, **kw)


def post(path: str, body: Optional[Dict] = None, **kw):
    return requests.post(f"{API}{path}", json=body or {}, timeout=180, **kw)


def delete(path: str, **kw):
    return requests.delete(f"{API}{path}", timeout=60, **kw)


def _restore_default_model():
    try:
        r = post("/admin/settings", {"model": DEFAULT_MODEL})
        print(f"[cleanup] restore default model status={r.status_code} body={r.text[:200]}")
    except Exception as e:
        print(f"[cleanup] FAILED to restore model: {e}")


# =====================================================================
# 1. GET /api/health
# =====================================================================
def test_health():
    r = get("/health")
    if r.status_code != 200:
        record("GET /api/health", False, f"status={r.status_code} body={r.text[:200]}")
        return
    d = r.json()
    checks = [
        d.get("provider") == "openrouter",
        d.get("llm_configured") is True,
        d.get("model") is not None,
        d.get("temperature") is not None,
        d.get("max_tokens") is not None,
        d.get("history_window") is not None,
    ]
    ok = all(checks)
    record(
        "GET /api/health",
        ok,
        f"provider={d.get('provider')} llm_configured={d.get('llm_configured')} model={d.get('model')} "
        f"temp={d.get('temperature')} max_tokens={d.get('max_tokens')} history_window={d.get('history_window')}",
        d,
    )


# =====================================================================
# 2. GET /api/admin/settings
# =====================================================================
def test_admin_settings_get():
    r = get("/admin/settings")
    if r.status_code != 200:
        record("GET /api/admin/settings", False, f"status={r.status_code} body={r.text[:200]}")
        return
    d = r.json()
    expected_keys = {"settings", "models", "limits", "defaults", "provider_configured"}
    missing = expected_keys - set(d.keys())
    ok = (
        not missing
        and isinstance(d["settings"], dict)
        and isinstance(d["models"], list)
        and isinstance(d["limits"], dict)
        and isinstance(d["defaults"], dict)
        and isinstance(d["provider_configured"], bool)
    )
    record(
        "GET /api/admin/settings",
        ok,
        f"missing={missing} provider_configured={d.get('provider_configured')} "
        f"models_count={len(d.get('models', []))} settings={d.get('settings')}",
        d,
    )


# =====================================================================
# 3. GET /api/admin/models
# =====================================================================
def test_admin_models():
    r = get("/admin/models")
    if r.status_code != 200:
        record("GET /api/admin/models", False, f"status={r.status_code} body={r.text[:200]}")
        return
    d = r.json()
    models = d.get("models") or []
    ids = {m.get("id") for m in models}
    ok = len(models) >= 8 and DEFAULT_MODEL in ids
    record(
        "GET /api/admin/models",
        ok,
        f"count={len(models)} default_in_list={DEFAULT_MODEL in ids}",
        d,
    )


# =====================================================================
# 4. POST /api/admin/settings — valid + validation
# =====================================================================
def test_admin_settings_post():
    # 4a. valid patch (temperature + max_tokens)
    r = post("/admin/settings", {"temperature": 0.7, "max_tokens": 1024})
    ok = r.status_code == 200
    body = {}
    if ok:
        body = r.json()
        s = body.get("settings", {})
        ok = abs(float(s.get("temperature", -1)) - 0.7) < 1e-6 and int(s.get("max_tokens", -1)) == 1024
    record("POST /api/admin/settings (valid patch)", ok, f"status={r.status_code} body={r.text[:200]}", body)

    # Confirm persistence
    r2 = get("/admin/settings")
    persisted = False
    if r2.status_code == 200:
        s = r2.json().get("settings", {})
        persisted = abs(float(s.get("temperature", -1)) - 0.7) < 1e-6 and int(s.get("max_tokens", -1)) == 1024
    record("POST /api/admin/settings persistence", persisted, f"after GET settings={r2.json().get('settings') if r2.status_code==200 else r2.text[:200]}")

    # 4b. reject unsupported model -> 400
    r = post("/admin/settings", {"model": "fake/model"})
    record(
        "POST /api/admin/settings reject bogus model (400)",
        r.status_code == 400,
        f"status={r.status_code} body={r.text[:200]}",
    )

    # 4c. reject temperature 3.0 -> 422
    r = post("/admin/settings", {"temperature": 3.0})
    record(
        "POST /api/admin/settings reject temperature 3.0 (422)",
        r.status_code == 422,
        f"status={r.status_code} body={r.text[:200]}",
    )

    # 4d. reject max_tokens 50 -> 422
    r = post("/admin/settings", {"max_tokens": 50})
    record(
        "POST /api/admin/settings reject max_tokens 50 (422)",
        r.status_code == 422,
        f"status={r.status_code} body={r.text[:200]}",
    )

    # 4e. reject history_window 1 -> 422
    r = post("/admin/settings", {"history_window": 1})
    record(
        "POST /api/admin/settings reject history_window 1 (422)",
        r.status_code == 422,
        f"status={r.status_code} body={r.text[:200]}",
    )


# =====================================================================
# 5-9. Story flow (uses free model)
# =====================================================================
def test_story_flow():
    # Switch to free model
    r = post("/admin/settings", {"model": FREE_MODEL})
    if r.status_code != 200:
        record("Switch to FREE model", False, f"status={r.status_code} body={r.text[:200]}")
        return
    record("Switch to FREE model", True, f"model={r.json().get('settings', {}).get('model')}")

    # 5. POST /api/story/new
    new_body = {
        "device_id": device_id,
        "genre": "post-apocalyptic survival",
        "role": "drifter scavenger",
        "tone": "grim, cinematic",
        "difficulty": "standard",
        "debug_mode": True,
        "custom_premise": "Dust storm closing in on an abandoned highway.",
    }
    r = post("/story/new", new_body)
    if r.status_code != 200:
        record("POST /api/story/new", False, f"status={r.status_code} body={r.text[:300]}")
        return
    d = r.json()
    session_id = d.get("session_id")
    turn = d.get("turn") or {}
    ok = (
        bool(session_id)
        and turn.get("turn_number") == 1
        and turn.get("player_action") in (None, "")
        and isinstance(turn.get("paragraphs"), list) and len(turn["paragraphs"]) >= 1
        and isinstance(turn.get("choices"), list) and len(turn["choices"]) >= 2
        and isinstance(turn.get("state"), dict)
        and isinstance(turn.get("ledger"), dict)
    )
    record(
        "POST /api/story/new",
        ok,
        f"session_id={session_id} turn_number={turn.get('turn_number')} paragraphs={len(turn.get('paragraphs') or [])} "
        f"choices={len(turn.get('choices') or [])} debug_present={turn.get('debug') is not None}",
        turn,
    )
    if not session_id:
        return

    # 5b. session persisted in /api/story/sessions
    r = get("/story/sessions", params={"device_id": device_id})
    sessions = (r.json() or {}).get("sessions", []) if r.status_code == 200 else []
    found = any(s.get("id") == session_id for s in sessions)
    record(
        "GET /api/story/sessions (session persisted)",
        r.status_code == 200 and found,
        f"status={r.status_code} count={len(sessions)} found={found}",
    )

    # Grab first choice text to drive turn 2
    first_choice = ""
    try:
        first_choice = turn["choices"][0]["text"]
    except Exception:
        first_choice = "Move cautiously toward the nearest source of cover."

    # 6. POST /api/story/action
    action_body = {
        "session_id": session_id,
        "action_text": first_choice,
        "debug_mode": True,
    }
    r = post("/story/action", action_body)
    if r.status_code != 200:
        record("POST /api/story/action", False, f"status={r.status_code} body={r.text[:300]}")
        return
    turn2 = (r.json() or {}).get("turn") or {}
    cont_ok = (
        turn2.get("turn_number") == 2
        and turn2.get("player_action") == first_choice
        and isinstance(turn2.get("paragraphs"), list) and len(turn2["paragraphs"]) >= 1
        and isinstance(turn2.get("choices"), list) and len(turn2["choices"]) >= 2
    )
    record(
        "POST /api/story/action (turn 2)",
        cont_ok,
        f"turn_number={turn2.get('turn_number')} player_action_match={turn2.get('player_action') == first_choice} "
        f"paragraphs={len(turn2.get('paragraphs') or [])} choices={len(turn2.get('choices') or [])}",
        turn2,
    )

    # 7. GET /api/story/session/{id}
    r = get(f"/story/session/{session_id}")
    if r.status_code != 200:
        record("GET /api/story/session/{id}", False, f"status={r.status_code} body={r.text[:200]}")
    else:
        d = r.json()
        sess = d.get("session") or {}
        turns = d.get("turns") or []
        ok = sess.get("id") == session_id and len(turns) == 2 and turns[0]["turn_number"] == 1 and turns[1]["turn_number"] == 2
        record(
            "GET /api/story/session/{id}",
            ok,
            f"session_id_match={sess.get('id') == session_id} turn_count={len(turns)}",
        )

    # 8. GET /api/story/session/{id}/latest
    r = get(f"/story/session/{session_id}/latest")
    if r.status_code != 200:
        record("GET /api/story/session/{id}/latest", False, f"status={r.status_code} body={r.text[:200]}")
    else:
        lt = (r.json() or {}).get("turn") or {}
        ok = lt.get("turn_number") == 2
        record("GET /api/story/session/{id}/latest", ok, f"turn_number={lt.get('turn_number')}")

    # 9. DELETE /api/story/session/{id}
    r = delete(f"/story/session/{session_id}")
    if r.status_code != 200:
        record("DELETE /api/story/session/{id}", False, f"status={r.status_code} body={r.text[:200]}")
    else:
        ok = (r.json() or {}).get("deleted") is True
        record("DELETE /api/story/session/{id}", ok, f"body={r.text[:200]}")

    # Subsequent GET should be 404
    r = get(f"/story/session/{session_id}")
    record("GET deleted session returns 404", r.status_code == 404, f"status={r.status_code}")


def main():
    print(f"BACKEND_URL={BACKEND_URL}")
    print(f"API base={API}")
    print(f"device_id={device_id}")
    print()
    try:
        test_health()
        test_admin_settings_get()
        test_admin_models()
        test_admin_settings_post()
        test_story_flow()
    finally:
        _restore_default_model()

    print("\n========= SUMMARY =========")
    failed = [k for k, v in results.items() if not v["ok"]]
    for k, v in results.items():
        marker = "PASS" if v["ok"] else "FAIL"
        print(f"  [{marker}] {k}")
    print(f"\nTotal: {len(results)} | Passed: {len(results)-len(failed)} | Failed: {len(failed)}")
    if failed:
        print("\nFailed details:")
        for k in failed:
            print(f"  - {k}: {results[k]['detail']}")
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
