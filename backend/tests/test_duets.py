"""Feature 3: two friends play opposite sides of one event.

Two independent clients (two device ids), the real route handlers, the real persistence, the real
player responses. The narrator is a deterministic fixture that records every request it receives
and writes only from what that request contains. Nothing here inserts the other player's view.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import duet  # noqa: E402
from ai_service import AIServiceError  # noqa: E402
from reliability_support import FakeGateway, MongoEnv, make_client, relax_rate_limits  # noqa: E402
from player_features_support import device, dump, headers  # noqa: E402

FERRY_PRIVATE = "FERRY-PRIVATE-saffron the toll book is forged"
KEEPER_PRIVATE = "KEEPER-PRIVATE-quince the cargo is due tonight"
THREE_FLASHES = f"Send three flashes with the signal lamp because {KEEPER_PRIVATE}"
LAUNCH = f"Launch the skiff into the channel because {FERRY_PRIVATE}"


class Narrator:
    def __init__(self):
        self.requests = []
        self.fail_next = 0
        self.delay = 0.0

    async def __call__(self, n, kwargs):
        if self.fail_next:
            self.fail_next -= 1
            raise AIServiceError("scripted outage")
        if self.delay:
            import asyncio
            await asyncio.sleep(self.delay)
        text = "\n".join(str(m.get("content") or "") for m in kwargs["messages"])
        seat = "ferryman" if "The player is Corin Hale" in text else "keeper"
        self.requests.append({"seat": seat, "text": text})
        action = re.search(r"Player action: (.*)", text).group(1)
        note = re.search(r"\[ENGINE_RESULT\] (.*)", text)
        seen = re.search(r"OBSERVATIONS[^\n]*\n((?:- .*\n?)+)", text)
        parts = [f"You act: {action}"]
        if note:
            parts.append(note.group(1))
        if seen:
            parts.append("Meanwhile " + " ".join(line[2:] for line in seen.group(1).strip().splitlines()))
        return (
            f"<narrative>{chr(10).join(parts) if False else (chr(10) * 2).join(parts)}</narrative>\n"
            f"<choices>\nA. Look around, call {n}\nB. Wait, call {n}\nC. Think, call {n}\nD. Move, call {n}\n</choices>"
        )

    def for_seat(self, seat):
        return [r["text"] for r in self.requests if r["seat"] == seat]


@pytest.fixture()
def env(monkeypatch):
    mongo = MongoEnv()
    for name in ("duets", "duet_turns"):
        mongo.sync_db[name].delete_many({})
    relax_rate_limits(monkeypatch)
    monkeypatch.setattr(duet, "SETTING", copy.deepcopy(duet.SETTING))
    yield mongo
    for name in ("duets", "duet_turns"):
        mongo.sync_db[name].delete_many({})
    mongo.close()


@pytest.fixture()
def narrator():
    return Narrator()


@pytest.fixture()
def client(env, narrator):
    fake = FakeGateway(on_request=narrator).install()
    with make_client() as tc:
        yield tc
    fake.restore()


def call(client, method, path, dev, body=None):
    return client.request(method, f"/api{path}", json=body, headers=headers(dev))


def start(client, host="host", guest="guest"):
    """Host creates a story and invites a friend; the friend joins from their own device."""
    a, b = device(), device()
    made = call(client, "POST", "/duets", a, {"seat": "ferryman"})
    assert made.status_code == 200, made.text
    code = made.json()["invite_code"]
    joined = call(client, "POST", "/duets/join", b, {"code": code})
    assert joined.status_code == 200, joined.text
    return a, b, made.json()["duet"]["id"], code


def act(client, did, dev, text, rid=None, expected=None):
    body = {"action_text": text, "action_request_id": rid or f"r-{uuid.uuid4()}"}
    if expected is not None:
        body["expected_turn_count"] = expected
    return call(client, "POST", f"/duets/{did}/action", dev, body)


def view(client, did, dev):
    r = call(client, "GET", f"/duets/{did}", dev)
    assert r.status_code == 200, r.text
    return r.json()["duet"]


def test_invite_only_and_each_resumes_from_their_own_device(client, env):
    a, b, did, code = start(client)
    c = device()
    assert call(client, "POST", "/duets/join", c, {"code": code}).status_code == 409            # seat is taken
    assert call(client, "POST", "/duets/join", c, {"code": "DUET-not-a-real-code-at-all"}).status_code == 404
    for method, path in (("GET", f"/duets/{did}"), ("GET", f"/duets/{did}/export"), ("GET", f"/duets/{did}/comparison"),
                         ("POST", f"/duets/{did}/end-chapter")):
        assert call(client, method, path, c).status_code == 404, path
    assert act(client, did, c, "Wait").status_code == 404
    assert call(client, "GET", "/duets", c).json() == {"duets": []}
    solo = call(client, "POST", "/duets", c, {"seat": "keeper"}).json()
    assert call(client, "POST", "/duets/join", c, {"code": solo["invite_code"]}).status_code == 409   # not your own invite
    va, vb = view(client, did, a), view(client, did, b)
    assert (va["you"]["seat"], vb["you"]["seat"]) == ("ferryman", "keeper")
    assert va["your_turn"] is True and va["waiting_for"] is None and va["choices"]
    assert vb["your_turn"] is False and vb["waiting_for"] == "Corin Hale" and vb["choices"] == []
    assert [d["id"] for d in call(client, "GET", "/duets", b).json()["duets"]] == [did]


def test_distinct_characters_and_inventories_with_nothing_of_the_others(client, env):
    a, b, did, _ = start(client)
    va, vb = view(client, did, a), view(client, did, b)
    assert va["you"]["character"]["inventory"] == ["ferry pole", "tide table"]
    assert vb["you"]["character"]["inventory"] == ["signal lamp", "logbook"]
    assert "signal lamp" not in dump(va) and "logbook" not in dump(va)
    assert "ferry pole" not in dump(vb) and "tide table" not in dump(vb)
    assert va["other"] == {"seat": "keeper", "name": "Ines Rook", "role": "signal keeper", "joined": True}


def test_turns_alternate_with_your_turn_and_waiting_state(client, env, narrator):
    a, b, did, _ = start(client)
    early = act(client, did, b, "Watch the channel")
    assert early.status_code == 409 and "Waiting for Corin Hale" in early.text and narrator.requests == []
    assert act(client, did, a, "Check the tide table", expected=0).status_code == 200
    again = act(client, did, a, "Check it again")
    assert again.status_code == 409 and "Waiting for Ines Rook" in again.text
    assert view(client, did, a)["your_turn"] is False and view(client, did, b)["your_turn"] is True
    stale = act(client, did, b, "Watch the channel", expected=0)
    assert stale.status_code == 409 and len(narrator.requests) == 1
    assert act(client, did, b, "Watch the channel", expected=1).status_code == 200
    assert view(client, did, a)["turn_count"] == 2


def test_flashes_and_launch_are_seen_across_the_water_and_nothing_else_leaks(client, env, narrator):
    a, b, did, _ = start(client)
    assert act(client, did, a, f"Check the tide table, quietly. {FERRY_PRIVATE}").status_code == 200
    assert act(client, did, b, THREE_FLASHES).status_code == 200
    va = view(client, did, a)
    assert any(e["kind"] == "observed" and e["text"] == "Three flashes from the lighthouse lamp." for e in va["history"])
    assert act(client, did, a, LAUNCH).status_code == 200
    vb = view(client, did, b)
    assert any(e["kind"] == "observed" and "slips away from the harbour into the channel" in e["text"] for e in vb["history"])
    va = view(client, did, a)
    assert va["known"]["boat"] == vb["known"]["boat"] == "the ferry skiff is out in the channel"
    world = env.sync_db.duets.find_one({"id": did})["world"]["boat"]
    assert (world["location"], world["state"]) == ("the channel", "underway")        # one boat, one place
    # What the ferryman's narrator was sent: his own story plus the engine's sentence about the lamp.
    ferry_requests = narrator.for_seat("ferryman")
    assert len(ferry_requests) == 2 and len(narrator.for_seat("keeper")) == 1
    assert "Three flashes from the lighthouse lamp." in ferry_requests[1]
    assert not any("KEEPER-PRIVATE" in r or "quince" in r or "signal lamp" in r for r in ferry_requests)
    assert not any("FERRY-PRIVATE" in r or "saffron" in r or "ferry pole" in r for r in narrator.for_seat("keeper"))
    # Everything each player can be shown: action responses, resume, list, export.
    shown_a = [dump(view(client, did, a)), dump(call(client, "GET", f"/duets/{did}/export", a).json()), dump(call(client, "GET", "/duets", a).json())]
    shown_b = [dump(view(client, did, b)), dump(call(client, "GET", f"/duets/{did}/export", b).json()), dump(call(client, "GET", "/duets", b).json())]
    assert FERRY_PRIVATE in shown_a[0] and not any("KEEPER-PRIVATE" in s or "quince" in s for s in shown_a)
    assert KEEPER_PRIVATE in shown_b[0] and not any("FERRY-PRIVATE" in s or "saffron" in s for s in shown_b)
    for secret in ("engine_note", "world", "invite", "device_id", "revision", "lease"):
        assert not any(secret in s for s in shown_a + shown_b), secret


def test_second_launch_cannot_create_a_second_boat(client, env, narrator):
    a, b, did, _ = start(client)
    assert act(client, did, a, LAUNCH).status_code == 200
    assert act(client, did, b, "Watch the channel").status_code == 200
    again = act(client, did, a, "Launch the skiff again")
    assert again.status_code == 200
    assert "cannot be launched twice" in again.text
    boat = env.sync_db.duets.find_one({"id": did})["world"]["boat"]
    assert (boat["location"], boat["state"]) == ("the channel", "underway")
    launches = [e for e in view(client, did, b)["history"] if e["kind"] == "observed" and "slips away" in e["text"]]
    assert len(launches) == 1


def test_without_line_of_sight_nobody_learns_what_they_cannot_see(client, env, narrator):
    duet.SETTING["sight"] = []                                   # fixture controls the starting world: fog
    a, b, did, _ = start(client)
    assert act(client, did, a, LAUNCH).status_code == 200
    assert act(client, did, b, THREE_FLASHES).status_code == 200
    vb = view(client, did, b)
    assert not any(e["kind"] == "observed" for e in vb["history"])
    assert vb["known"]["boat"] == "the ferry skiff is moored at the harbour"      # stale: they could not see it go
    va = view(client, did, a)
    assert not any(e["kind"] == "observed" for e in va["history"])
    assert va["known"]["boat"] == "the ferry skiff is out in the channel"
    assert "slips away" not in "".join(narrator.for_seat("keeper"))


def test_reconnect_retry_and_duplicate_actions_advance_once(client, env, narrator):
    a, b, did, _ = start(client)
    rid = f"r-{uuid.uuid4()}"
    first = act(client, did, a, "Check the tide table", rid=rid)
    assert first.status_code == 200 and first.json()["replayed"] is False
    for _ in range(3):                                           # lost responses, reconnects, double taps
        again = act(client, did, a, "Check the tide table", rid=rid)
        assert again.status_code == 200 and again.json()["replayed"] is True
    assert view(client, did, a)["turn_count"] == 1 and len(narrator.requests) == 1
    assert act(client, did, b, "Reuse a request id", rid=rid).status_code == 409           # it is not theirs to replay
    assert env.sync_db.duet_turns.count_documents({"duet_id": did}) == 1
    # A different seat's device cannot act on this seat's turn.
    assert act(client, did, a, "Another action straight away").status_code == 409


def test_overlapping_actions_from_one_seat_resolve_once(client, env, narrator):
    a, b, did, _ = start(client)
    narrator.delay = 0.4
    results = []

    def go(text):
        results.append(act(client, did, a, text).status_code)

    threads = [threading.Thread(target=go, args=(t,)) for t in ("Check the tide table", "Watch the lighthouse")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [200, 409]
    assert len(narrator.requests) == 1 and view(client, did, a)["turn_count"] == 1
    doc = env.sync_db.duets.find_one({"id": did})
    assert doc["lease"] is None and doc["current_seat"] == "keeper"


def test_an_expired_lease_is_reclaimable_and_a_live_one_is_not(client, env, narrator):
    a, b, did, _ = start(client)
    env.sync_db.duets.update_one({"id": did}, {"$set": {"lease": {"request_id": "ghost", "seat": "ferryman", "expires_at": time.time() + 60}}})
    assert act(client, did, a, "Check the tide table").status_code == 409
    env.sync_db.duets.update_one({"id": did}, {"$set": {"lease.expires_at": time.time() - 1}})
    assert act(client, did, a, "Check the tide table").status_code == 200


def test_a_failed_narrator_call_advances_nothing_and_can_be_retried(client, env, narrator):
    a, b, did, _ = start(client)
    narrator.fail_next = 1
    rid = f"r-{uuid.uuid4()}"
    failed = act(client, did, a, "Check the tide table", rid=rid)
    assert failed.status_code == 502
    doc = env.sync_db.duets.find_one({"id": did})
    assert doc["turn_count"] == 0 and doc["lease"] is None and doc["current_seat"] == "ferryman"
    assert env.sync_db.duet_turns.count_documents({"duet_id": did}) == 0
    retry = act(client, did, a, "Check the tide table", rid=rid)
    assert retry.status_code == 200 and retry.json()["replayed"] is False


def test_chapter_end_keeps_both_private_unless_both_opt_in(client, env, narrator):
    a, b, did, _ = start(client)
    assert act(client, did, a, f"Check the tide table. {FERRY_PRIVATE}").status_code == 200
    assert act(client, did, b, THREE_FLASHES).status_code == 200
    assert call(client, "POST", f"/duets/{did}/comparison", a, {"share": True}).status_code == 409      # chapter still running
    ended = call(client, "POST", f"/duets/{did}/end-chapter", b)
    assert ended.status_code == 200 and ended.json()["duet"]["chapter_ended"] is True
    assert call(client, "POST", f"/duets/{did}/end-chapter", a).status_code == 200                       # idempotent
    assert act(client, did, a, "One more thing").status_code == 409
    only_a = call(client, "POST", f"/duets/{did}/comparison", a, {"share": True}).json()
    assert only_a["you_shared"] is True and only_a["both_shared"] is False and [x["seat"] for x in only_a["accounts"]] == ["ferryman"]
    assert "KEEPER-PRIVATE" not in dump(only_a)
    seen_by_b = call(client, "GET", f"/duets/{did}/comparison", b).json()
    assert seen_by_b["you_shared"] is None and seen_by_b["both_shared"] is False and [x["seat"] for x in seen_by_b["accounts"]] == ["keeper"]
    assert "FERRY-PRIVATE" not in dump(seen_by_b)
    declined = call(client, "POST", f"/duets/{did}/comparison", b, {"share": False}).json()
    assert declined["both_shared"] is False and "FERRY-PRIVATE" not in dump(declined)
    assert "KEEPER-PRIVATE" not in dump(call(client, "GET", f"/duets/{did}/comparison", a).json())     # still private for A
    both = call(client, "POST", f"/duets/{did}/comparison", b, {"share": True}).json()
    assert both["both_shared"] is True and [x["seat"] for x in both["accounts"]] == ["keeper", "ferryman"]
    assert KEEPER_PRIVATE in dump(both) and FERRY_PRIVATE in dump(both)
    mirrored = call(client, "GET", f"/duets/{did}/comparison", a).json()
    assert [x["seat"] for x in mirrored["accounts"]] == ["ferryman", "keeper"] and KEEPER_PRIVATE in dump(mirrored)
    assert call(client, "GET", f"/duets/{did}/comparison", device()).status_code == 404
    for hidden in ("engine_note", "world", "known", "invite", "device_id"):
        assert hidden not in dump(both)


def test_solo_saves_are_untouched_by_two_player_stories(client, env):
    from player_features_support import seed_story
    dev = device()
    sid = seed_story(env.sync_db, dev, turns=2)
    r = client.get(f"/api/story/session/{sid}", headers=headers(dev))
    assert r.status_code == 200 and r.json()["session"]["title"] == "Dock Mystery"
    assert "duet" not in dump(r.json())
    assert call(client, "GET", "/duets", dev).json() == {"duets": []}



def test_reusing_a_request_id_for_a_different_action_is_refused_not_replayed(client, env, narrator):
    a, b, did, _ = start(client)
    rid = f"r-{uuid.uuid4()}"
    assert act(client, did, a, "Check the tide table", rid=rid).status_code == 200
    changed = act(client, did, a, "Cut the mooring line", rid=rid)
    assert changed.status_code == 409 and "action_request_id" in changed.json()["detail"]
    assert env.sync_db.duet_turns.count_documents({"duet_id": did}) == 1 and len(narrator.requests) == 1
    assert act(client, did, a, "Check the tide table", rid=rid).json()["replayed"] is True


def test_a_lease_outlasts_the_provider_timeout_and_is_kept_alive_while_narrating(client, env, narrator, monkeypatch):
    import duet_api
    import ai_config
    assert duet_api.LEASE_SECONDS > ai_config.PROVIDER_TIMEOUT
    monkeypatch.setattr(duet_api, "LEASE_SECONDS", 1)  # heartbeat every 0.33s
    a, b, did, _ = start(client)
    narrator.delay = 2.2
    seen = []

    def go():
        seen.append(act(client, did, a, "Check the tide table").status_code)

    t = threading.Thread(target=go)
    t.start()
    time.sleep(0.5)
    first = env.sync_db.duets.find_one({"id": did})["lease"]["expires_at"]
    time.sleep(1.2)  # past the original one second lease
    doc = env.sync_db.duets.find_one({"id": did})
    assert doc["lease"] is not None and doc["lease"]["expires_at"] > first
    assert act(client, did, a, "Watch the lighthouse").status_code == 409  # still held, so nobody takes it over
    t.join()
    assert seen == [200] and view(client, did, a)["turn_count"] == 1
