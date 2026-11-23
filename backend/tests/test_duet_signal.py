"""Two humans agree a lamp signal in Two Lights, from two independent clients.

The narrator fixture records every request it receives, so premature disclosure is inspected on the
actual provider payloads and on both clients' responses, not assumed.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
import duet  # noqa: E402
from test_duets import act, call, client, env, narrator, start  # noqa: F401,E402

MEANING = "SIGNAL-MEANING-quartz bring the skiff round to the north slip"


def _propose(client, did, dev, count=3, meaning=MEANING, rid=None):
    return call(client, "POST", f"/duets/{did}/signals", dev, {"request_id": rid or f"p-{uuid.uuid4()}", "count": count, "meaning": meaning})


def _agree(client):
    ferry, keeper, did, _ = start(client)
    p = _propose(client, did, keeper)
    assert p.status_code == 200, p.text
    sid = p.json()["duet"]["signals"][0]["id"]
    r = call(client, "POST", f"/duets/{did}/signals/{sid}/respond", ferry, {"accept": True})
    assert r.status_code == 200, r.text
    return ferry, keeper, did, sid


def test_agreement_needs_both_and_is_seen_by_both(client, env, narrator):
    ferry, keeper, did, _ = start(client)
    p = _propose(client, did, keeper)
    mine = p.json()["duet"]["signals"][0]
    assert mine["mine"] is True and mine["status"] == "proposed"
    theirs = call(client, "GET", f"/duets/{did}", ferry).json()["duet"]["signals"][0]
    assert theirs["mine"] is False and theirs["status"] == "proposed" and theirs["meaning"] == MEANING
    # The proposer cannot agree to their own offer.
    assert call(client, "POST", f"/duets/{did}/signals/{theirs['id']}/respond", keeper, {"accept": True}).status_code == 409
    ok = call(client, "POST", f"/duets/{did}/signals/{theirs['id']}/respond", ferry, {"accept": True})
    assert ok.status_code == 200 and ok.json()["duet"]["signals"][0]["status"] == "agreed"
    assert call(client, "GET", f"/duets/{did}", keeper).json()["duet"]["signals"][0]["status"] == "agreed"


def test_a_clear_signal_is_understood_by_the_other_client_only_after_it_is_sent(client, env, narrator):
    ferry, keeper, did, _ = _agree(client)
    # Before anything is sent the ferryman's narrator has never been told how the keeper will use it.
    act(client, did, ferry, "Watch the lighthouse")
    assert narrator.for_seat("keeper") == []
    r = act(client, did, keeper, "Send three flashes with the signal lamp")
    assert r.status_code == 200, r.text
    ferry_view = call(client, "GET", f"/duets/{did}", ferry).json()["duet"]
    seen = [e["text"] for e in ferry_view["history"] if e["kind"] == "observed"]
    assert seen and "Three flashes" in seen[-1] and MEANING in seen[-1]
    # The ferryman's own narrator request carries the observation; the keeper's private action text never leaves her request.
    act(client, did, ferry, "Launch the skiff into the channel")
    fr = narrator.for_seat("ferryman")[-1]
    assert "Three flashes" in fr and "Send three flashes with the signal lamp" not in fr


def test_a_faint_signal_is_perceived_but_not_understood(client, env, narrator):
    ferry, keeper, did, _ = _agree(client)
    act(client, did, ferry, "Wait on the quay")
    r = call(client, "POST", f"/duets/{did}/action", keeper, {"action_text": "Send three flashes with the signal lamp", "action_request_id": f"f-{uuid.uuid4()}", "clarity": "faint"})
    assert r.status_code == 200, r.text
    ferry_view = call(client, "GET", f"/duets/{did}", ferry).json()["duet"]
    seen = " ".join(e["text"] for e in ferry_view["history"] if e["kind"] == "observed")
    assert "uncertain flicker" in seen and "Three flashes" not in seen and MEANING not in seen
    # What the ferryman's narrator may say about it is limited to that; the meaning is not in the observation.
    act(client, did, ferry, "Launch the skiff into the channel")
    assert "uncertain flicker" in narrator.for_seat("ferryman")[-1]
    obs_block = narrator.for_seat("ferryman")[-1].split("OBSERVATIONS")[1].split("\n\n")[0]
    assert MEANING not in obs_block


def test_agreement_closes_after_the_first_action_and_unknown_flashes_mean_nothing(client, env, narrator):
    ferry, keeper, did, _ = start(client)
    act(client, did, ferry, "Wait on the quay")
    late = _propose(client, did, keeper)
    assert late.status_code == 409
    # Three flashes with no agreement: the other seat sees three flashes and nothing more.
    act(client, did, keeper, "Send three flashes with the signal lamp")
    seen = " ".join(e["text"] for e in call(client, "GET", f"/duets/{did}", ferry).json()["duet"]["history"] if e["kind"] == "observed")
    assert "Three flashes" in seen and "agreed" not in seen


def test_a_retried_proposal_is_one_proposal_and_a_third_device_sees_nothing(client, env, narrator):
    from player_features_support import device

    ferry, keeper, did, _ = start(client)
    a = _propose(client, did, keeper, rid="same-request-1")
    b = _propose(client, did, keeper, rid="same-request-1")
    assert a.status_code == b.status_code == 200
    assert len(call(client, "GET", f"/duets/{did}", keeper).json()["duet"]["signals"]) == 1
    outsider = device()
    assert call(client, "POST", f"/duets/{did}/signals", outsider, {"request_id": "xx-12345678", "count": 2, "meaning": "x"}).status_code == 404
    assert call(client, "POST", f"/duets/{did}/signals/{a.json()['duet']['signals'][0]['id']}/respond", outsider, {"accept": True}).status_code == 404



def test_a_signal_change_that_loses_a_race_is_refused_not_silently_dropped(client, env, narrator, monkeypatch):
    a, b, did, _ = start(client)
    real = duet.propose_signal

    def raced(*args, **kwargs):
        env.sync_db.duets.update_one({"id": did}, {"$inc": {"revision": 1}})  # another write lands first
        return real(*args, **kwargs)

    monkeypatch.setattr(duet, "propose_signal", raced)
    r = _propose(client, did, a)
    assert r.status_code == 409 and "Reload" in r.json()["detail"]
    assert (env.sync_db.duets.find_one({"id": did})["world"].get("signals") or []) == []
    monkeypatch.setattr(duet, "propose_signal", real)
    assert _propose(client, did, a).status_code == 200
