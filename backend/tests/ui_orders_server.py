"""Deterministic backend for playing Feature 2 (standing instructions) through the real play screen.

    python tests/ui_orders_server.py --port 8010 --device ui-test-device

Same safety as the other scenario servers: ``_test`` database only, no provider calls. The scripted
narrator moves the scene when the player chooses to walk and otherwise only writes what the
engine's result directive tells it. The water rises one step per turn once instructions exist.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from db_guard import apply_test_environment  # noqa: E402

apply_test_environment(os.environ)
os.environ["DEFAULT_PROSE_MODE"] = "standard"

import gateway  # noqa: E402
import order_engine  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from reliability_support import fake_llm_result  # noqa: E402
from test_orders import DOCK, FAR, seed, world  # noqa: E402

_calls = {"n": 0}
_WALKS = {"far bank": FAR, "ferry dock": DOCK}


async def scripted_narrator(**kwargs):
    _calls["n"] += 1
    n = _calls["n"]
    blob = "\n".join(str(m.get("content") or "") for m in kwargs["messages"])
    text = str(kwargs["messages"][-1].get("content") or "")
    match = re.search(r"Player action:\s*(.+)", text)
    action = (match.group(1) if match else "").lower()
    scene = next((place for key, place in _WALKS.items() if "walk to the " + key in action), None)
    rolling = json.dumps({"scene": scene, "location": scene}) if scene else "{}"
    seen = re.search(re.escape(order_engine.DIRECTIVE_MARKER) + r"\n.*?\n((?:- .*\n?)+)", blob)
    prose = (
        "You see it for yourself. " + " ".join(re.findall(r"- \([^)]*\) (.*)", seen.group(1)))
        if seen
        else f"The river murmurs against the pilings (scripted beat {n})."
    )
    content = (
        f"<rolling_state>{rolling}</rolling_state>\n<narrative>{prose}</narrative>\n"
        f"<choices>\nA. Wait and watch, beat {n}\nB. Walk to the far bank, beat {n}\n"
        f"C. Walk to the ferry dock, beat {n}\nD. Check the rope, beat {n}\n</choices>\n"
        "<state>\nHealth: stable\nPressure: steady\nPosition: here\n</state>\n<ledger>\nCarried: nothing\n</ledger>\n"
    )
    return fake_llm_result(content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--device", default="ui-test-device")
    parser.add_argument("--level", type=int, default=0, help="starting water level (the red mark is 3)")
    args = parser.parse_args()

    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    assert os.environ["DB_NAME"].endswith("_test"), "refusing to seed a non-test database"
    for name in ("sessions", "turns", "rate_limits", "action_requests", "provider_usage", "notebook_items"):
        sync[name].delete_many({})
    sid = seed(sync, args.device, world(level=args.level))
    print(f"seeded session {sid} for device {args.device} in {os.environ['DB_NAME']}", flush=True)

    gateway.invoke_llm = scripted_narrator
    import uvicorn
    import server

    uvicorn.run(server.app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
