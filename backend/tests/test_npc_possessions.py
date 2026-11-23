"""NPC inventory is remembered by the engine, not by whatever the narrator re-emits.

Real action handler, real persistence, real player responses. The narrator fixture controls only
what it writes back for the cast; the restored values come from the saved ledger.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import npc_possessions as np  # noqa: E402
from test_orders import DOCK, Narrator, _act, _doc, _shown, client, env, fake, narrator, seed, world  # noqa: E402,F401
from player_features_support import device, headers  # noqa: E402


def _mara(doc):
    return next(n for n in doc["rolling_state"]["npcs"] if n["name"] == "Mara Voss")


def test_first_turn_records_what_she_carries(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world())
    assert _act(client, sid, dev, 1).status_code == 200
    ledger = _doc(env, sid)["npc_ledger"]["rows"]
    assert ledger["npc-mara0000000"]["inventory"] == ["fishing knife", "sealed parcel"]


def test_narrator_dropping_the_inventory_field_does_not_lose_it(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world())
    assert _act(client, sid, dev, 1).status_code == 200
    # Next narrator reply rewrites the whole cast and leaves out inventory.
    narrator.rolling_for_call[2] = {"npcs": [{"name": "Mara Voss", "npc_id": "npc-mara0000000", "role": "ferry hand", "last_seen": DOCK},
                                              {"name": "Dov Marsh", "npc_id": "npc-dov00000000", "role": "harbourmaster"}]}
    assert _act(client, sid, dev, 2).status_code == 200
    assert _mara(_doc(env, sid))["inventory"] == ["fishing knife", "sealed parcel"]
    shown = json.dumps(_shown(client, sid, dev))
    assert "npc_ledger" not in shown   # the raw ledger is never in a player response


MARA_ROW = {"name": "Mara Voss", "npc_id": "npc-mara0000000", "role": "ferry hand", "last_seen": DOCK}
ASK_ALL = "Ask Mara what she is carrying"


def _entry(env, sid):
    return _doc(env, sid)["npc_ledger"]["rows"]["npc-mara0000000"]


def test_narrator_can_drop_what_the_player_knows_but_not_what_is_hidden(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world())
    assert _act(client, sid, dev, 1, text=ASK_ALL).status_code == 200
    assert sorted(_entry(env, sid)["known"]) == ["fishing knife", "sealed parcel"]
    narrator.rolling_for_call[2] = {"npcs": [{**MARA_ROW, "inventory": ["fishing knife"]}]}
    assert _act(client, sid, dev, 2).status_code == 200
    assert _entry(env, sid)["inventory"] == ["fishing knife"]          # known item she used up
    narrator.rolling_for_call[3] = {"npcs": [{**MARA_ROW, "inventory": ["fishing knife", "rope"]}]}
    assert _act(client, sid, dev, 3).status_code == 200
    assert "rope" in _entry(env, sid)["known"]                         # the narrator put it on stage


def test_narrator_cannot_erase_an_item_the_player_never_learned_of(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world())
    assert _act(client, sid, dev, 1).status_code == 200
    narrator.rolling_for_call[2] = {"npcs": [{**MARA_ROW, "inventory": []}]}
    assert _act(client, sid, dev, 2).status_code == 200
    assert _entry(env, sid)["inventory"] == ["fishing knife", "sealed parcel"]


def test_the_narrator_is_never_sent_what_the_player_has_not_learned(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world())
    for n in (1, 2):
        assert _act(client, sid, dev, n).status_code == 200
    for blob in narrator.seen:
        assert "sealed parcel" not in blob and "fishing knife" not in blob
        assert "[NPC_POSSESSIONS_V1]" in blob and "inventory_known" in blob
    assert _entry(env, sid)["known"] == []


def test_a_direct_question_is_answered_when_trust_is_high_enough(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(trust=60))
    assert _act(client, sid, dev, 1, text=ASK_ALL).status_code == 200
    first = narrator.seen[-1]
    assert "tells the player what they are carrying: fishing knife, sealed parcel" in first
    assert _act(client, sid, dev, 2).status_code == 200
    later = narrator.seen[-1]
    assert "inventory_known" in later and "sealed parcel" in later and "fishing knife" in later   # now it is known


def test_a_direct_question_is_refused_when_the_relationship_is_too_thin(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(trust=np.DISCLOSE_MIN_TRUST - 1))
    assert _act(client, sid, dev, 1, text=ASK_ALL).status_code == 200
    blob = narrator.seen[-1]
    assert "does not want to say what they carry" in blob
    assert "sealed parcel" not in blob and "fishing knife" not in blob
    assert _entry(env, sid)["known"] == []
    assert _act(client, sid, dev, 2).status_code == 200
    assert "sealed parcel" not in narrator.seen[-1]


def test_the_trust_line_is_exact(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(trust=np.DISCLOSE_MIN_TRUST))
    assert _act(client, sid, dev, 1, text=ASK_ALL).status_code == 200
    assert sorted(_entry(env, sid)["known"]) == ["fishing knife", "sealed parcel"]


def test_a_stranger_with_no_relationship_does_not_volunteer_anything(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(dov_at=DOCK))
    assert _act(client, sid, dev, 1, text="Ask Dov what he is carrying").status_code == 200
    assert "does not want to say what they carry" in narrator.seen[-1]


def test_asking_for_one_item_reveals_only_that_item(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(trust=60))
    assert _act(client, sid, dev, 1, text="Ask Mara if she has a knife").status_code == 200
    assert "confirms they have: fishing knife" in narrator.seen[-1]
    assert "sealed parcel" not in narrator.seen[-1]
    assert _entry(env, sid)["known"] == ["fishing knife"]


def test_asking_about_something_she_does_not_have_gets_an_honest_no(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(trust=60))
    assert _act(client, sid, dev, 1, text="Ask Mara if she has a lantern").status_code == 200
    blob = narrator.seen[-1]
    assert "does not have what the player asked about" in blob and "sealed parcel" not in blob
    assert _entry(env, sid)["known"] == []


def test_a_gift_moves_the_item_and_the_player_now_knows_it(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(trust=60))
    assert _act(client, sid, dev, 1, text="Ask Mara to give me the knife").status_code == 200
    assert "hands the player their fishing knife" in narrator.seen[-1]
    assert _entry(env, sid)["inventory"] == ["sealed parcel"] and _entry(env, sid)["known"] == []
    assert "fishing knife" not in _mara(_doc(env, sid))["inventory"]


def test_a_request_for_an_item_is_refused_without_the_relationship(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(trust=10))
    assert _act(client, sid, dev, 1, text="Ask Mara to give me the knife").status_code == 200
    assert "does not trust the player enough" in narrator.seen[-1]
    assert _entry(env, sid)["inventory"] == ["fishing knife", "sealed parcel"]


def test_someone_who_is_not_here_cannot_be_asked(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world(trust=60))
    assert _act(client, sid, dev, 1, text="Ask Dov what he is carrying").status_code == 200
    assert "tells the player" not in narrator.seen[-1] and "does not want to say" not in narrator.seen[-1]


def test_an_npc_who_leaves_and_returns_gets_her_things_back(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world())
    assert _act(client, sid, dev, 1).status_code == 200
    assert _act(client, sid, dev, 2).status_code == 200
    narrator.rolling_for_call[3] = {"npcs": [{"name": "Dov Marsh", "npc_id": "npc-dov00000000", "role": "harbourmaster"},
                                              {"name": "Mara Voss", "npc_id": "npc-mara0000000"}]}
    assert _act(client, sid, dev, 3).status_code == 200
    assert _mara(_doc(env, sid))["inventory"] == ["fishing knife", "sealed parcel"]


def test_unrecorded_possessions_stay_unknown_not_empty():
    ledger, _ = np.apply(None, {"npcs": [{"name": "Stranger"}]}, turn=1)
    assert np.inventory_of(ledger, {"name": "Stranger"}) is None
    rolling = {"npcs": [{"name": "Stranger"}]}
    np.apply(ledger, rolling, turn=2)
    assert "inventory" not in rolling["npcs"][0]


def test_engine_handover_changes_ledger_and_row_together():
    rolling = {"npcs": [{"name": "Mara Voss", "npc_id": "n1", "inventory": ["knife", "parcel"]}]}
    ledger, _ = np.apply(None, rolling, turn=1)
    np.set_inventory(ledger, rolling, rolling["npcs"][0], ["knife"], turn=2)
    assert rolling["npcs"][0]["inventory"] == ["knife"]
    later = {"npcs": [{"name": "Mara Voss", "npc_id": "n1"}]}
    np.apply(ledger, later, turn=3)
    assert later["npcs"][0]["inventory"] == ["knife"]


def test_ledger_is_bounded_and_cleans_items():
    rows = {"npcs": [{"name": f"N{i}", "inventory": ["x" * 500, "x" * 500, " ", "a"] * 10} for i in range(80)]}
    ledger, _ = np.apply(None, rows, turn=5)
    assert len(ledger["rows"]) <= np.MAX_LEDGER_ROWS
    inv = rows["npcs"][0]["inventory"]
    assert len(inv) <= np.MAX_ITEMS and all(len(x) <= np.MAX_TEXT for x in inv)


def test_branch_copies_the_ledger(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, world())
    assert _act(client, sid, dev, 1).status_code == 200
    assert "npc_ledger" in _doc(env, sid)
    r = client.post(f"/api/story/session/{sid}/branch", json={"request_id": "br-npc-ledger-1"}, headers=headers(dev))
    assert r.status_code == 200, r.text
    new_id = r.json()["session"]["id"]
    assert new_id != sid
    assert _doc(env, new_id)["npc_ledger"]["rows"]["npc-mara0000000"]["inventory"] == ["fishing knife", "sealed parcel"]


def test_solo_save_without_a_ledger_still_plays(client, env, narrator):
    dev = device()
    sid = seed(env.sync_db, dev, {"scene": DOCK, "location": DOCK, "npcs": []})
    assert "npc_ledger" not in _doc(env, sid)
    assert _act(client, sid, dev, 1).status_code == 200
    assert "npc_ledger" not in _doc(env, sid)
