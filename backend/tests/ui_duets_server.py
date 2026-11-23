"""Deterministic backend for playing Feature 3 (two friends, opposite sides) through the real screens.

    python tests/ui_duets_server.py --port 8010

``_test`` database only, no provider calls. The scripted narrator is the same fixture the tests use:
it writes only from the one seat's request, so what each browser shows is what that seat was sent.
It also records every narrator request to a JSONL file for leak inspection.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from db_guard import apply_test_environment  # noqa: E402

apply_test_environment(os.environ)
os.environ["DEFAULT_PROSE_MODE"] = "standard"

import gateway  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from reliability_support import fake_llm_result  # noqa: E402
from test_duets import Narrator  # noqa: E402

LOG = Path(os.environ.get("DUET_NARRATOR_LOG", "duet_narrator_requests.jsonl"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    assert os.environ["DB_NAME"].endswith("_test"), "refusing to touch a non-test database"
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    for name in ("duets", "duet_turns", "rate_limits", "provider_usage"):
        sync[name].delete_many({})
    LOG.write_text("")
    narrator = Narrator()
    counter = {"n": 0}

    async def scripted(**kwargs):
        counter["n"] += 1
        content = await narrator(counter["n"], kwargs)
        req = narrator.requests[-1]
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(req) + "\n")
        return fake_llm_result(content)

    gateway.invoke_llm = scripted
    print(f"duet UI server on {args.port}, db {os.environ['DB_NAME']}", flush=True)
    import uvicorn
    import server

    uvicorn.run(server.app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
