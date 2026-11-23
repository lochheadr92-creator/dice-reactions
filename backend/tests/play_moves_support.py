"""Shared pieces for the player-move tests: a seeded save, an offline narrator, request helpers.

The narrator only repeats what the engine's result directives say, and it keeps writing the carried
list it was given (stale on purpose), so any item the engine took or gave is the engine's doing.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

from reliability_support import FakeGateway, MongoEnv, insert_session, make_client, relax_rate_limits  # noqa: E402
from player_features_support import FIXED_NOW, device, headers  # noqa: E402

__all__ = ["seed", "Narrator", "env", "narrator", "client", "move", "doc", "session_view", "device", "headers", "moves"]

RESULT = re.compile(r"\[(\w+)_RESULT_V1\]\n((?:- .*\n?)+)")


def seed(sync_db, dev, rolling, turns, *, carried="", npc_ledger=None, extra=None):
    ex = {"title": "Moves", "last_state": {"Health": "ok"}, **(extra or {})}
    if npc_ledger is not None:
        ex["npc_ledger"] = npc_ledger
    sid = insert_session(sync_db, dev, turn_count=len(turns), rolling=rolling, extra=ex)
    for i, paras in enumerate(turns, 1):
        text = " ".join(paras)
        sync_db.turns.insert_one({
            "id": str(uuid.uuid4()), "session_id": sid, "turn_number": i, "player_action": None,
            "narrative": text, "canonical_narrative": text, "paragraphs": paras,
            "choices": [{"label": c, "text": f"Seed {c}"} for c in "ABCD"],
            "state": {"Health": "ok"}, "ledger": {"Carried": carried} if i == len(turns) else {},
            "rolling_state": rolling, "raw": "", "debug": {}, "created_at": FIXED_NOW,
        })
    return sid


class Narrator:
    def __init__(self):
        self.seen = []
        self.carried = "nothing"
        self.rolling = {}

    def __call__(self, n, kwargs):
        text = "\n".join(str(m.get("content") or "") for m in kwargs["messages"])
        self.seen.append(text)
        bits = [f"The moment stretches (beat {n})."]
        for m in RESULT.finditer(text):
            first = m.group(2).splitlines()[0]
            bits.append(first[2:])
        return (
            f"<rolling_state>{json.dumps(self.rolling)}</rolling_state>\n"
            f"<narrative>{' '.join(bits)}</narrative>\n"
            f"<choices>\nA. Wait, beat {n}\nB. Look around, beat {n}\nC. Speak, beat {n}\nD. Leave, beat {n}\n</choices>\n"
            "<state>\nHealth: ok\nPressure: steady\nPosition: here\n</state>\n"
            f"<ledger>\nCarried: {self.carried}\n</ledger>\n"
        )


@pytest.fixture()
def env(monkeypatch):
    mongo = MongoEnv()
    mongo.sync_db.notebook_items.delete_many({})
    relax_rate_limits(monkeypatch)
    yield mongo
    mongo.sync_db.notebook_items.delete_many({})
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


def move(client, sid, dev, expected, kind, args, rid=None, op=None):
    body = {"session_id": sid, "action_text": "", "action_request_id": rid or f"m-{uuid.uuid4()}",
            "expected_turn_count": expected, "move": {"kind": kind, "args": args, **({"op": op} if op else {})}}
    return client.post("/api/story/action", json=body, headers=headers(dev))


def doc(env, sid):
    return env.sync_db.sessions.find_one({"id": sid}, {"_id": 0})


def session_view(client, sid, dev):
    return client.get(f"/api/story/session/{sid}", headers=headers(dev)).json()["session"]


def moves(client, sid, dev):
    return client.get(f"/api/story/session/{sid}/moves", headers=headers(dev)).json()["moves"]
