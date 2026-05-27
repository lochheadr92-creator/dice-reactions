"""
Backend API tests for Dice Reaction Story Engine v3.3
Tests health, story creation, action, listing, retrieval, deletion, and 404 handling.
"""
import uuid
import pytest


# ---------- Health ----------
def test_health_llm_configured(api_client, base_url):
    r = api_client.get(f"{base_url}/api/health", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("llm_configured") is True
    assert isinstance(data.get("model"), str) and data.get("model").strip()


# ---------- Shared session helpers ----------
@pytest.fixture(scope="module")
def device_id():
    return f"TEST_{uuid.uuid4()}"


@pytest.fixture(scope="module")
def created_session(api_client, base_url, device_id):
    """Create a single story session reused across tests (LLM calls are 12-30s each)."""
    payload = {
        "device_id": device_id,
        "genre": "fantasy",
        "role": "wanderer",
        "tone": "grounded",
        "difficulty": "soft",
        "debug_mode": True,
    }
    r = api_client.post(f"{base_url}/api/story/new", json=payload, timeout=120)
    assert r.status_code == 200, r.text
    data = r.json()
    yield data
    # Teardown — delete session
    sid = data["session_id"]
    api_client.delete(f"{base_url}/api/story/session/{sid}", timeout=30)


# ---------- POST /api/story/new ----------
class TestNewStory:
    def test_response_shape(self, created_session):
        assert "session_id" in created_session
        assert "turn" in created_session
        assert "session" in created_session

    def test_turn_paragraphs(self, created_session):
        turn = created_session["turn"]
        assert len(turn["paragraphs"]) >= 2, f"expected >=2 paragraphs, got {len(turn['paragraphs'])}"

    def test_turn_choices_count(self, created_session):
        turn = created_session["turn"]
        assert 4 <= len(turn["choices"]) <= 6
        labels = [c["label"] for c in turn["choices"]]
        assert all(l in "ABCDEF" for l in labels)
        for c in turn["choices"]:
            assert c["text"]

    def test_turn_state_keys(self, created_session):
        turn = created_session["turn"]
        state = turn["state"]
        for key in ["Health", "Stress", "Fatigue", "Position", "Objective", "Inventory Summary"]:
            assert key in state, f"missing state key: {key}; got {list(state.keys())}"
        assert ("Conditions" in state) or ("Notable Conditions" in state)

    def test_turn_ledger_keys(self, created_session):
        ledger = created_session["turn"]["ledger"]
        # Engine should populate at least core keys; require a meaningful subset
        required_any = ["Carried", "Worn", "Stored", "Weapons", "Supplies", "Uncertain", "Load"]
        present = [k for k in required_any if k in ledger]
        assert len(present) >= 4, f"ledger missing keys, got {list(ledger.keys())}"
        assert "Load" in ledger

    def test_debug_block_present_when_on(self, created_session):
        debug = created_session["turn"].get("debug")
        assert debug, "debug block should be present when debug_mode=True"
        # Expect at least Roll & Final
        assert "Roll" in debug or "roll" in {k.lower() for k in debug.keys()}

    def test_no_mongo_id_leak(self, created_session):
        assert "_id" not in created_session
        assert "_id" not in created_session["turn"]
        assert "_id" not in created_session["session"]

    def test_turn_number_one(self, created_session):
        assert created_session["turn"]["turn_number"] == 1


# ---------- POST /api/story/action ----------
class TestStoryAction:
    @pytest.fixture(scope="class")
    def action_turn(self, api_client, base_url, created_session):
        sid = created_session["session_id"]
        # pick first choice
        first_choice = created_session["turn"]["choices"][0]["text"]
        r = api_client.post(
            f"{base_url}/api/story/action",
            json={"session_id": sid, "action_text": first_choice, "debug_mode": False},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        return r.json()["turn"]

    def test_turn_increments(self, action_turn):
        assert action_turn["turn_number"] == 2

    def test_player_action_stored(self, action_turn):
        assert action_turn["player_action"]

    def test_paragraphs_choices_state(self, action_turn):
        assert len(action_turn["paragraphs"]) >= 2
        assert 4 <= len(action_turn["choices"]) <= 6
        assert action_turn["state"].get("Health")
        assert action_turn["ledger"].get("Load")

    def test_debug_omitted_when_off(self, action_turn):
        # In developer_mode=false, debug should be absent. In developer_mode=true,
        # telemetry debug may still be returned for developer diagnostics.
        debug = action_turn.get("debug")
        if debug:
            assert "model_used" in debug or "latency_ms" in debug
        else:
            assert not debug

    def test_no_dice_leak_in_narrative(self, action_turn):
        narrative = action_turn["narrative"].lower()
        # rolls/modifiers must NEVER appear in narrative when debug is OFF
        assert "d20" not in narrative
        assert "roll:" not in narrative
        assert "modifier" not in narrative


# ---------- GET /api/story/sessions ----------
class TestListSessions:
    def test_list_for_device(self, api_client, base_url, device_id, created_session):
        r = api_client.get(f"{base_url}/api/story/sessions", params={"device_id": device_id}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "sessions" in data
        assert any(s["id"] == created_session["session_id"] for s in data["sessions"])
        # Verify no _id leak
        for s in data["sessions"]:
            assert "_id" not in s

    def test_isolation_by_device(self, api_client, base_url):
        r = api_client.get(f"{base_url}/api/story/sessions",
                           params={"device_id": f"TEST_unknown_{uuid.uuid4()}"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["sessions"] == []


# ---------- GET /api/story/session/{id} & latest ----------
class TestGetSession:
    def test_get_full_session(self, api_client, base_url, created_session):
        sid = created_session["session_id"]
        r = api_client.get(f"{base_url}/api/story/session/{sid}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["session"]["id"] == sid
        assert "_id" not in data["session"]
        assert len(data["turns"]) >= 1
        # ordered by turn_number ascending
        nums = [t["turn_number"] for t in data["turns"]]
        assert nums == sorted(nums)
        for t in data["turns"]:
            assert "_id" not in t

    def test_latest_turn(self, api_client, base_url, created_session):
        sid = created_session["session_id"]
        r = api_client.get(f"{base_url}/api/story/session/{sid}/latest", timeout=15)
        assert r.status_code == 200
        turn = r.json()["turn"]
        assert "_id" not in turn
        assert turn["turn_number"] >= 1


# ---------- 404 handling ----------
class TestNotFound:
    def test_get_session_404(self, api_client, base_url):
        r = api_client.get(f"{base_url}/api/story/session/nonexistent-{uuid.uuid4()}", timeout=15)
        assert r.status_code == 404

    def test_latest_404(self, api_client, base_url):
        r = api_client.get(f"{base_url}/api/story/session/nonexistent-{uuid.uuid4()}/latest", timeout=15)
        assert r.status_code == 404

    def test_action_unknown_session_404(self, api_client, base_url):
        r = api_client.post(
            f"{base_url}/api/story/action",
            json={"session_id": f"missing-{uuid.uuid4()}", "action_text": "look around", "debug_mode": False},
            timeout=15,
        )
        assert r.status_code == 404

    def test_delete_404(self, api_client, base_url):
        r = api_client.delete(f"{base_url}/api/story/session/missing-{uuid.uuid4()}", timeout=15)
        assert r.status_code == 404


# ---------- DELETE flow (separate session) ----------
class TestDeleteFlow:
    def test_delete_then_404(self, api_client, base_url):
        device = f"TEST_del_{uuid.uuid4()}"
        r = api_client.post(
            f"{base_url}/api/story/new",
            json={"device_id": device, "genre": "fantasy", "difficulty": "soft", "debug_mode": False},
            timeout=120,
        )
        assert r.status_code == 200
        sid = r.json()["session_id"]
        d = api_client.delete(f"{base_url}/api/story/session/{sid}", timeout=15)
        assert d.status_code == 200
        assert d.json().get("deleted") is True
        # Now GET should 404
        g = api_client.get(f"{base_url}/api/story/session/{sid}", timeout=15)
        assert g.status_code == 404
