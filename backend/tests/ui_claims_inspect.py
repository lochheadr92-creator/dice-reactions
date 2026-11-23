"""Read-only view of what the engine recorded for the planted-secret scenario (guarded to *_test)."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_guard import apply_test_environment
apply_test_environment(os.environ)
from pymongo import MongoClient

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
assert os.environ["DB_NAME"].endswith("_test")
for s in db.sessions.find({}):
    st = s.get("claim_state") or {}
    claims = {c["id"]: c for c in st.get("claims", [])}
    print("turn_count:", s.get("turn_count"), "| real location:", (s.get("rolling_state") or {}).get("missing_passenger"))
    for c in claims.values():
        print(" claim:", c["text"], "| speaker:", c["speaker"], "| to:", c.get("recipient"), "| witnesses:", c["witnesses"])
    for b in st.get("beliefs", []):
        print(" belief:", b["actor"]["name"], "->", claims[b["claim_id"]]["text"], "|", b["source"], "| turn", b.get("turn"))
    for r in st.get("relays", []):
        print(" relay:", json.dumps(r, default=str)[:160])
    for a in st.get("actions", []):
        print(" action:", json.dumps(a, default=str)[:200])
