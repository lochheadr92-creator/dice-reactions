import os
import sys
import pytest
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db_guard import apply_test_environment  # noqa: E402

# Test safety (review 2026-11-20, finding 1). Several fixtures delete every
# session and turn in the configured database. backend/.env names the real
# local game database, and server.py loads that file on import, so this runs
# BEFORE anything imports server: it forces a database whose name ends in
# "_test", blanks provider keys unless the shell sets them, and refuses to
# continue otherwise. backend/.env is deliberately not loaded here.
apply_test_environment(os.environ)

# Pin the new-story narration default so a local backend/.env setting
# (DEFAULT_PROSE_MODE) cannot change test expectations.
os.environ["DEFAULT_PROSE_MODE"] = "standard"

# Explicit admin key for security/raw-export tests — do not rely on import order.
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-for-live-suite")

# Frontend env has the public URL
ROOT = Path(__file__).resolve().parents[2]
fe_env = ROOT / "frontend" / ".env"
if fe_env.exists():
    for line in fe_env.read_text().splitlines():
        if line.startswith("EXPO_PUBLIC_BACKEND_URL"):
            os.environ["EXPO_PUBLIC_BACKEND_URL"] = line.split("=", 1)[1].strip().strip('"')

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="session")
def base_url():
    assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL is not configured"
    return BASE_URL


@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(autouse=True)
def block_live_llm_in_deterministic_suite(request, monkeypatch):
    """Fail closed if gateway.invoke_llm is reached during non-live tests."""
    if request.node.get_closest_marker("live"):
        return

    import gateway

    def _blocked(*_args, **_kwargs):
        raise RuntimeError(
            "Live LLM provider call blocked in deterministic test suite"
        )

    monkeypatch.setattr(gateway, "invoke_llm", _blocked)