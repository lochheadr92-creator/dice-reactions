"""Retry only the story flow tests with smaller max_tokens to fit within preview ingress timeout."""
import sys, uuid, requests, time

BACKEND_URL = "https://dice-story-engine.preview.emergentagent.com"
API = f"{BACKEND_URL}/api"
FREE_MODEL = "openai/gpt-oss-120b:free"
DEFAULT_MODEL = "gryphe/mythomax-l2-13b"

device_id = f"tester-{uuid.uuid4().hex[:10]}"
session_id = None

def post(p, b=None): return requests.post(f"{API}{p}", json=b or {}, timeout=240)
def get(p, **kw):    return requests.get(f"{API}{p}", timeout=60, **kw)
def delete(p):       return requests.delete(f"{API}{p}", timeout=60)

print("Switching to FREE model + small max_tokens for speed…")
r = post("/admin/settings", {"model": FREE_MODEL, "max_tokens": 768, "temperature": 0.8})
print("settings:", r.status_code, r.json())

# Retry up to 2x for transient 502s from preview ingress
def try_story_new():
    body = {
        "device_id": device_id,
        "genre": "post-apocalyptic survival",
        "role": "drifter scavenger",
        "tone": "grim, cinematic",
        "difficulty": "standard",
        "debug_mode": True,
        "custom_premise": "Dust storm closing in on an abandoned highway.",
    }
    for attempt in range(1, 4):
        t0 = time.time()
        r = post("/story/new", body)
        dt = time.time() - t0
        print(f"attempt {attempt} status={r.status_code} time={dt:.1f}s")
        if r.status_code == 200:
            return r.json()
        print("body:", r.text[:300])
        time.sleep(2)
    return None

d = try_story_new()
if not d:
    print("FAIL story/new")
    # restore
    post("/admin/settings", {"model": DEFAULT_MODEL, "max_tokens": 2048})
    sys.exit(1)

session_id = d["session_id"]
turn = d["turn"]
print(f"PASS story/new session_id={session_id} turn_number={turn['turn_number']} "
      f"player_action={turn['player_action']} paragraphs={len(turn['paragraphs'])} "
      f"choices={len(turn['choices'])} state_keys={list(turn['state'].keys())[:3]} "
      f"ledger_keys={list(turn['ledger'].keys())[:3]} debug_present={turn['debug'] is not None}")

# session persistence
r = get("/story/sessions", params={"device_id": device_id})
print(f"sessions list status={r.status_code} found={any(s['id']==session_id for s in r.json().get('sessions',[]))}")

# action
first_choice_text = turn["choices"][0]["text"] if turn.get("choices") else "Move toward cover."
print(f"\nAction (choice): {first_choice_text[:90]}...")
for attempt in range(1, 4):
    t0 = time.time()
    r = post("/story/action", {"session_id": session_id, "action_text": first_choice_text, "debug_mode": True})
    dt = time.time() - t0
    print(f"action attempt {attempt} status={r.status_code} time={dt:.1f}s")
    if r.status_code == 200:
        break
    print("body:", r.text[:300])
    time.sleep(2)

if r.status_code != 200:
    print("FAIL story/action")
    post("/admin/settings", {"model": DEFAULT_MODEL, "max_tokens": 2048})
    sys.exit(1)

turn2 = r.json()["turn"]
print(f"PASS story/action turn_number={turn2['turn_number']} player_action_match={turn2['player_action']==first_choice_text} "
      f"paragraphs={len(turn2['paragraphs'])} choices={len(turn2['choices'])}")
# Continuity check: did the narrative reference prior scene elements?
n1 = turn["narrative"].lower()
n2 = turn2["narrative"].lower()
# Look for shared distinctive nouns
def keywords(txt):
    import re
    words = re.findall(r"[a-z]{5,}", txt)
    common = {"the","that","with","there","where","which","could","would","while","their","other","again","into","this","then","when"}
    return set(w for w in words if w not in common)
overlap = keywords(n1) & keywords(n2)
print(f"continuity overlap keywords ({len(overlap)}): {sorted(list(overlap))[:15]}")

# GET session
r = get(f"/story/session/{session_id}")
d = r.json()
print(f"GET session status={r.status_code} turns_count={len(d.get('turns', []))} session_id_match={d['session']['id']==session_id}")

# latest
r = get(f"/story/session/{session_id}/latest")
print(f"GET latest status={r.status_code} latest_turn_number={r.json()['turn']['turn_number']}")

# DELETE
r = delete(f"/story/session/{session_id}")
print(f"DELETE status={r.status_code} body={r.text}")

# GET 404
r = get(f"/story/session/{session_id}")
print(f"GET deleted status={r.status_code}")

# restore default
r = post("/admin/settings", {"model": DEFAULT_MODEL, "max_tokens": 2048})
print(f"Restored default model: {r.json()}")
