"""Deterministic backend for driving the real play screen by hand or by a browser agent.

    python tests/ui_scenario_server.py --port 8010 --device ui-test-device

Safety: runs under the same guard as the test suite. The database name must end in ``_test``
(db_guard forces it), provider keys are blanked, and ``gateway.invoke_llm`` is replaced by a
scripted narrator, so no model is ever called. The seeded save holds two characters who own
different items and know different facts (see player_features_support).
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
from player_features_support import seed_story  # noqa: E402

_calls = {"n": 0}
_ITEMS = {"locket": "silver locket", "knife": "rusty knife", "lantern": "storm lantern", "key": "brass key"}


async def scripted_narrator(**kwargs):
    _calls["n"] += 1
    n = _calls["n"]
    text = str(kwargs["messages"][-1].get("content") or "")
    match = re.search(r"Player action:\s*(.+)", text)
    action = (match.group(1) if match else "").lower()
    rolling = "{}"
    for word, item in _ITEMS.items():
        if word in action:
            rolling = '{"inventory_objects":[{"object":"%s","location_state":"carried"}]}' % item
            break
    content = (
        f"<rolling_state>{rolling}</rolling_state>\n"
        f"<narrative>The dock settles into a new hush (scripted reply {n}).</narrative>\n"
        f"<choices>\nA. Study the water, round {n}\nB. Check the ropes, round {n}\n"
        f"C. Wait for the tide, round {n}\nD. Call across the river, round {n}\n</choices>\n"
        "<state>\nHealth: stable\nPressure: steady\nPosition: the ferry dock\n</state>\n"
        "<ledger>\nCarried: see story\n</ledger>\n"
    )
    return fake_llm_result(content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--device", default="ui-test-device")
    args = parser.parse_args()

    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    assert os.environ["DB_NAME"].endswith("_test"), "refusing to seed a non-test database"
    for name in ("sessions", "turns", "rate_limits", "action_requests", "provider_usage", "notebook_items"):
        sync[name].delete_many({})
    sid = seed_story(sync, args.device, turns=3, title="Dock Mystery")
    print(f"seeded session {sid} for device {args.device} in {os.environ['DB_NAME']}", flush=True)

    gateway.invoke_llm = scripted_narrator
    import uvicorn
    import server

    uvicorn.run(server.app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
