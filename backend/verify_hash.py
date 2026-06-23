"""Step 7 — confirm the snapshot-hash change is inert for stress-absent state.

Run from backend/ on the clean checkout:  python verify_hash.py
Compares the current stress-absent snapshot hash to the pre-P1 value.
"""

import json

from foundation_snapshot import FoundationTurnSnapshot

_PRE_P1_FALLBACK = "7d2825b108b1da752b9fcfbdd10b9916295179d85eb3e9a0b047dfa7c4535134"

rolling = {"npcs": [{"npc_id": "npc-a", "name": "Mara"}]}
replay = {
    "run_seed": "s",
    "pressure_graph": {"nodes": [{"id": "p1", "status": "active", "magnitude": 50}]},
    "npc_agendas": {"agendas": [{"npc_id": "npc-a", "goal_kind": "escape_danger"}]},
}

snap = FoundationTurnSnapshot.build(
    run_seed="s", turn_sequence=1, rolling_state=rolling, replayability_state=replay
)
current = snap.source_state_hash

try:
    pre = json.load(open("hashes_pre.json"))["0"]
except (FileNotFoundError, KeyError, ValueError):
    pre = _PRE_P1_FALLBACK

print("pre-P1 :", pre)
print("current:", current)
print("RESULT :", "MATCH" if current == pre else "DRIFT")
