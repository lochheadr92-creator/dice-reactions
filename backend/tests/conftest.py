import os
import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

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
