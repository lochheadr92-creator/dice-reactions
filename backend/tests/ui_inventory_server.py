"""Deterministic backend for looking at the inventory screen on the real play screen.

    python tests/ui_inventory_server.py --port 8010 --device ui-test-device

``_test`` database only, no provider calls. Seeds one save whose latest turn has a full ledger. The
scripted narrator echoes the action it was sent so the item buttons can be seen reaching the story.
"""

from __future__ import annotations

import argparse
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
from pymongo import MongoClient  # noqa: E402
from reliability_support import fake_llm_result  # noqa: E402
from test_orders import seed, world  # noqa: E402

LEDGER = {
    "Worn": "wool coat, leather boots, flat cap",
    "Weapons": "hatchet, flare pistol",
    "Tools": "flashlight, lockpicks",
    "Carried": "canvas satchel, ferry keys, folded letter",
    "Supplies": "3 bandages, water flask",
    "Currency": "12 coins",
    "Uncertain": "radio?",
    "Load": "light",
}


async def scripted_narrator(**kwargs):
    text = str(kwargs["messages"][-1].get("content") or "")
    match = re.search(r"Player action:\s*(.+)", text)
    action = (match.group(1) if match else "").strip()
    content = (
        f"<rolling_state>{{}}</rolling_state>\n<narrative>You act: {action}</narrative>\n"
        "<choices>\nA. Wait\nB. Look around\nC. Check the rope\nD. Walk the bank\n</choices>\n"
        "<state>\nHealth: stable\nPressure: steady\nPosition: here\n</state>\n"
        "<ledger>\nCarried: canvas satchel, ferry keys, folded letter\nWorn: wool coat, leather boots, flat cap\n"
        "Weapons: hatchet, flare pistol\nTools: flashlight, lockpicks\nSupplies: 3 bandages, water flask\nLoad: light\n</ledger>\n"
    )
    return fake_llm_result(content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--device", default="ui-test-device")
    args = parser.parse_args()
    assert os.environ["DB_NAME"].endswith("_test"), "refusing to seed a non-test database"
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    for name in ("sessions", "turns", "rate_limits", "action_requests", "provider_usage"):
        sync[name].delete_many({})
    sid = seed(sync, args.device, world())
    sync.turns.update_many({"session_id": sid}, {"$set": {"ledger": LEDGER}})
    print(f"seeded session {sid} for device {args.device}", flush=True)
    gateway.invoke_llm = scripted_narrator
    import uvicorn
    import server

    uvicorn.run(server.app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
