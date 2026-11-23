"""Read-only view of the standing-instruction scenario state (guarded to *_test)."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_guard import apply_test_environment
apply_test_environment(os.environ)
from pymongo import MongoClient

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
assert os.environ["DB_NAME"].endswith("_test")
for s in db.sessions.find({}):
    r = s.get("rolling_state") or {}
    st = s.get("order_state") or {}
    print("turn_count:", s.get("turn_count"), "| scene:", r.get("scene"), "| ferry_state:", r.get("ferry_state"),
          "| water:", (r.get("gauges") or {}).get("river_water", {}).get("level"))
    for o in st.get("orders", []):
        print(" order:", o["status"], "| fired_turn:", o.get("fired_turn"), "| shown:", o.get("shown"), "|", o["text"][:60])
    print(" mara inventory:", [n.get("inventory") for n in r.get("npcs", []) if n["name"] == "Mara Voss"])
