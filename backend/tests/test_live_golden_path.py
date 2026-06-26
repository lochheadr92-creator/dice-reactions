"""
Manual live smoke for the real story/new -> story/action path.

Usage from ``backend/`` with a running server:
    python -m pytest tests/test_live_golden_path.py -m live -q -s
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, Mapping, Optional, Tuple

import pytest
import requests
from requests import RequestException

from security import ADMIN_API_KEY_HEADER, DEVICE_ID_HEADER


pytestmark = pytest.mark.live

CONTROL_TIMEOUT = 30
NEW_TIMEOUT = 210
ACTION_TIMEOUT = 210
BODY_SNIPPET_CHARS = 800


def _configured_base_url() -> str:
    base_url = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
    if not base_url:
        pytest.fail(
            "Live golden path requires EXPO_PUBLIC_BACKEND_URL pointing at "
            "the running backend, for example http://localhost:8000."
        )
    return base_url


def _configured_admin_key() -> str:
    admin_key = os.environ.get("ADMIN_API_KEY", "")
    if not admin_key:
        pytest.fail(
            "Live golden path requires ADMIN_API_KEY in the pytest environment "
            "and the running backend environment so raw diagnostics can be read."
        )
    return admin_key


def _api_url(base_url: str, path: str) -> str:
    if base_url.endswith("/api"):
        return f"{base_url}{path}"
    return f"{base_url}/api{path}"


def _admin_headers(admin_key: str) -> Dict[str, str]:
    return {ADMIN_API_KEY_HEADER: admin_key}


def _request_json(
    client: requests.Session,
    method: str,
    url: str,
    *,
    name: str,
    expected_status: int = 200,
    headers: Optional[Mapping[str, str]] = None,
    payload: Optional[Mapping[str, Any]] = None,
    timeout: int = CONTROL_TIMEOUT,
) -> Tuple[int, Dict[str, Any], int]:
    started = time.perf_counter()
    try:
        response = client.request(
            method,
            url,
            headers=dict(headers or {}),
            json=dict(payload or {}) if payload is not None else None,
            timeout=timeout,
        )
    except RequestException as exc:
        pytest.fail(f"{name} could not reach live backend at {url}: {exc}")
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if response.status_code != expected_status:
        pytest.fail(
            f"{name} returned HTTP {response.status_code}, expected "
            f"{expected_status}. Body: {response.text[:BODY_SNIPPET_CHARS]}"
        )
    try:
        data = response.json()
    except ValueError:
        pytest.fail(
            f"{name} returned non-JSON body: "
            f"{response.text[:BODY_SNIPPET_CHARS]}"
        )
    if not isinstance(data, dict):
        pytest.fail(f"{name} returned JSON {type(data).__name__}, expected object.")
    return response.status_code, data, elapsed_ms


def _optional_admin_json(
    client: requests.Session,
    url: str,
    *,
    admin_key: str,
    name: str,
) -> Dict[str, Any]:
    try:
        response = client.get(
            url,
            headers=_admin_headers(admin_key),
            timeout=CONTROL_TIMEOUT,
        )
    except RequestException as exc:
        return {"available": False, "error": str(exc)}
    if response.status_code != 200:
        return {
            "available": False,
            "status": response.status_code,
            "body": response.text[:BODY_SNIPPET_CHARS],
        }
    try:
        body = response.json()
    except ValueError:
        return {
            "available": False,
            "status": response.status_code,
            "body": response.text[:BODY_SNIPPET_CHARS],
        }
    return {"available": True, "name": name, "body": body}


def _preflight(
    client: requests.Session,
    *,
    base_url: str,
    admin_key: str,
) -> Dict[str, Any]:
    _status, health, health_ms = _request_json(
        client,
        "GET",
        _api_url(base_url, "/health"),
        name="GET /api/health",
        timeout=CONTROL_TIMEOUT,
    )
    if health.get("status") != "ok":
        pytest.fail(f"Backend health is not ok: {health}")
    if health.get("llm_configured") is not True:
        pytest.fail(
            "Backend reports llm_configured=false. Set OPENROUTER_API_KEY "
            "on the running backend before running this live harness."
        )

    _settings_status, settings_body, settings_ms = _request_json(
        client,
        "GET",
        _api_url(base_url, "/admin/settings"),
        name="GET /api/admin/settings",
        headers=_admin_headers(admin_key),
        timeout=CONTROL_TIMEOUT,
    )
    if settings_body.get("provider_configured") is not True:
        pytest.fail(
            "Admin settings report provider_configured=false. Set "
            "OPENROUTER_API_KEY on the running backend."
        )

    settings = settings_body.get("settings") or {}
    defaults = settings_body.get("defaults") or {}
    runtime = _optional_admin_json(
        client,
        _api_url(base_url, "/admin/runtime"),
        admin_key=admin_key,
        name="GET /api/admin/runtime",
    )
    return {
        "health_ms": health_ms,
        "settings_ms": settings_ms,
        "settings_model": settings.get("model"),
        "settings_fallback_models": settings.get("fallback_models"),
        "default_model": defaults.get("default_model"),
        "default_fallback_models": defaults.get("fallback_models"),
        "runtime": runtime,
    }


def _first_choice_text(turn: Mapping[str, Any]) -> str:
    choices = turn.get("choices") or []
    for choice in choices:
        if isinstance(choice, Mapping):
            text = str(choice.get("text") or "").strip()
            if text:
                return text
    pytest.fail(f"story/new returned no usable choice text: {choices!r}")


def _find_turn(turns: Any, turn_number: Any) -> Dict[str, Any]:
    for turn in turns or []:
        if isinstance(turn, dict) and turn.get("turn_number") == turn_number:
            return turn
    pytest.fail(f"Raw export missing turn_number={turn_number}; turns={turns!r}")


def _debug(turn: Mapping[str, Any]) -> Dict[str, Any]:
    debug = turn.get("debug") or {}
    return debug if isinstance(debug, dict) else {}


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _utility_summary(debug: Mapping[str, Any]) -> Dict[str, Any]:
    prefix = "replayability_utility_ai_"
    fields = {
        key.removeprefix(prefix): value
        for key, value in debug.items()
        if key.startswith(prefix)
    }
    return {"present": bool(fields), "fields": fields}


def _turn_evidence(
    *,
    status: int,
    http_latency_ms: int,
    turn: Mapping[str, Any],
) -> Dict[str, Any]:
    debug = _debug(turn)
    rolling_state = turn.get("rolling_state")
    return {
        "status": status,
        "turn_number": turn.get("turn_number"),
        "model_used": debug.get("model_used"),
        "model_requested": debug.get("model_requested"),
        "validation_retried": debug.get("validation_retried") == "yes",
        "validation_retry_kind": debug.get("validation_retry_kind"),
        "validation_first_fail": debug.get("validation_first_fail"),
        "validation_second_fail": debug.get("validation_second_fail"),
        "rolling_state_valid": isinstance(rolling_state, dict)
        and bool(rolling_state),
        "http_latency_ms": http_latency_ms,
        "provider_latency_ms": _as_int(debug.get("latency_ms")),
        "tokens_total": _as_int(debug.get("tokens_total")),
        "tokens_prompt": _as_int(debug.get("tokens_prompt")),
        "tokens_completion": _as_int(debug.get("tokens_completion")),
        "provider": debug.get("provider"),
        "provider_status": debug.get("provider_status"),
    }


def _cleanup_session(
    client: requests.Session,
    *,
    base_url: str,
    session_id: str,
    device_id: str,
) -> None:
    try:
        client.delete(
            _api_url(base_url, f"/story/session/{session_id}"),
            headers={DEVICE_ID_HEADER: device_id},
            timeout=CONTROL_TIMEOUT,
        )
    except RequestException as exc:
        print(f"LIVE_GOLDEN_PATH_CLEANUP_FAILED={exc}")


def test_live_golden_path_story_new_then_action(api_client):
    base_url = _configured_base_url()
    admin_key = _configured_admin_key()
    preflight = _preflight(api_client, base_url=base_url, admin_key=admin_key)

    device_id = f"qa-golden-{uuid.uuid4().hex[:10]}"
    session_id: Optional[str] = None

    try:
        new_payload = {
            "device_id": device_id,
            "genre": "post-apocalyptic",
            "role": "scavenger courier",
            "tone": "grounded",
            "difficulty": "standard",
            "debug_mode": True,
            "mode": "advanced",
            "custom_premise": (
                "A short survival opening with one nearby NPC, one concrete "
                "resource pressure, and an immediate physical decision."
            ),
        }
        new_status, new_body, new_http_ms = _request_json(
            api_client,
            "POST",
            _api_url(base_url, "/story/new"),
            name="POST /api/story/new",
            payload=new_payload,
            timeout=NEW_TIMEOUT,
        )
        session_id = str(new_body.get("session_id") or "")
        if not session_id:
            pytest.fail(f"story/new response missing session_id: {new_body}")

        new_turn = new_body.get("turn") or {}
        first_turn_number = new_turn.get("turn_number")
        if first_turn_number != 1:
            pytest.fail(f"story/new returned unexpected first turn: {new_turn}")

        action_status, action_body, action_http_ms = _request_json(
            api_client,
            "POST",
            _api_url(base_url, "/story/action"),
            name="POST /api/story/action",
            headers={DEVICE_ID_HEADER: device_id},
            payload={
                "session_id": session_id,
                "action_text": _first_choice_text(new_turn),
                "debug_mode": True,
            },
            timeout=ACTION_TIMEOUT,
        )
        action_turn = action_body.get("turn") or {}
        action_turn_number = action_turn.get("turn_number")
        if action_turn_number != 2:
            pytest.fail(f"story/action returned unexpected turn: {action_turn}")

        _raw_status, raw_export, _raw_ms = _request_json(
            api_client,
            "GET",
            _api_url(base_url, f"/story/session/{session_id}/export/raw"),
            name=f"GET /api/story/session/{session_id}/export/raw",
            headers=_admin_headers(admin_key),
            timeout=CONTROL_TIMEOUT,
        )
        raw_session = raw_export.get("session") or {}
        raw_turns = raw_export.get("turns") or []
        raw_first = _find_turn(raw_turns, first_turn_number)
        raw_action = _find_turn(raw_turns, action_turn_number)
        first_evidence = _turn_evidence(
            status=new_status,
            http_latency_ms=new_http_ms,
            turn=raw_first,
        )
        action_evidence = _turn_evidence(
            status=action_status,
            http_latency_ms=action_http_ms,
            turn=raw_action,
        )

        replayability_state = raw_session.get("replayability_state")
        latest_debug = _debug(raw_action)
        validation_retry_count = int(first_evidence["validation_retried"]) + int(
            action_evidence["validation_retried"]
        )
        session_diag = _optional_admin_json(
            api_client,
            _api_url(base_url, f"/admin/session/{session_id}/diagnostics"),
            admin_key=admin_key,
            name=f"GET /api/admin/session/{session_id}/diagnostics",
        )
        evidence = {
            "session_id": session_id,
            "story_new": first_evidence,
            "story_action": action_evidence,
            "validation_retry_count": validation_retry_count,
            "model_used": action_evidence.get("model_used")
            or first_evidence.get("model_used"),
            "model_config": preflight,
            "replayability_active": isinstance(replayability_state, dict)
            and bool(replayability_state.get("run_seed")),
            "utility_ai": _utility_summary(latest_debug),
            "admin_session_diagnostics": session_diag,
            "raw_turn_count": len(raw_turns),
        }

        print(
            "LIVE_GOLDEN_PATH_EVIDENCE="
            + json.dumps(evidence, sort_keys=True, default=str)
        )

        assert first_evidence["status"] == 200
        assert action_evidence["status"] == 200
        assert first_evidence["rolling_state_valid"] is True
        assert action_evidence["rolling_state_valid"] is True
        assert evidence["replayability_active"] is True
        assert evidence["model_used"], evidence
    finally:
        if session_id:
            _cleanup_session(
                api_client,
                base_url=base_url,
                session_id=session_id,
                device_id=device_id,
            )
