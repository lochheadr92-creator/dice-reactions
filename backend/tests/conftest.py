import os
import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Safe defaults so server.py imports succeed in hermetic CI without a .env file.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "dice_reactions_test")

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