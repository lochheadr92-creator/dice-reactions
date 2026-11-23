"""Read-only inspector for the UI scenario database (guarded to *_test)."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_guard import apply_test_environment
apply_test_environment(os.environ)
from pymongo import MongoClient

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
assert os.environ["DB_NAME"].endswith("_test")
for s in db.sessions.find({}):
    r = s.get("rolling_state") or s.get("rolling") or {}
    print(s["_id"] if "session_id" not in s else s["session_id"], s.get("title"), "| turns", db.turns.count_documents({"session_id": s.get("session_id", s["_id"])}))
    print("  controlled:", (s.get("controlled_character") or {}).get("name"), "| handover:", bool(s.get("handover")))
    print("  inventory_objects:", [o.get("object") for o in (r.get("inventory_objects") or [])])
    print("  npcs:", [(n.get("name"), n.get("controller"), n.get("former_protagonist")) for n in (r.get("npcs") or [])])
print("notebook_items:", db.notebook_items.count_documents({}))
