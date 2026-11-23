"""Routes and persistence for the two-player story. The rules live in ``duet``.

Collections
  * ``duets``       one document per story: seats (device ids), turn order, the shared world,
                    what each seat knows, each seat's current choices, opt-in flags, an action lease.
  * ``duet_turns``  one document per committed turn. It holds the actor's private action and
                    narration plus the engine sentences the other seat may witness.

Every response is built from an explicit whitelist for ONE seat. A device that holds no seat gets
404 for every route, so a third device cannot tell the story exists.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import hmac
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import action_requests
import ai_config
import duet
import turn_commit
from security import require_device_id

# A lease must outlast the longest narration call (the provider timeout), and a heartbeat keeps it alive
# for as long as the call runs, so a second request can never take over a turn still being written.
SIGNAL_RACE = "The story changed while you were answering. Reload and try again."
LEASE_SECONDS = int(ai_config.PROVIDER_TIMEOUT) + 60
NOT_FOUND = "Story not found"
BUSY = "An action is being resolved. Try again in a moment."
DUETS_ENV_VAR = "DUETS_ENABLED"


def duets_enabled() -> bool:
    """Two-player stories are off unless the operator switches them on. Read on every request."""
    return str(os.environ.get(DUETS_ENV_VAR, "")).strip().lower() in ("1", "true", "yes", "on")


def require_duets() -> None:
    """Every duet route depends on this. Switched off, the routes answer 404 as if they did not exist."""
    if not duets_enabled():
        raise HTTPException(status_code=404, detail="Not Found")


def _lease_live(doc: Dict[str, Any]) -> bool:
    lease = doc.get("lease")
    return bool(lease) and float(lease.get("expires_at") or 0) >= time.time()


def _no_live_lease() -> Dict[str, Any]:
    return {"$or": [{"lease": None}, {"lease.expires_at": {"$lt": time.time()}}]}

Narrate = Callable[..., Awaitable[str]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _seat_of(doc: Dict[str, Any], device_id: str) -> Optional[str]:
    for seat in duet.SEATS:
        held = (doc.get("seats") or {}).get(seat)
        if held and hmac.compare_digest(str(held.get("device_id") or ""), str(device_id)):
            return seat
    return None


async def ensure_indexes(db) -> None:
    await db.duet_turns.create_index([("duet_id", 1), ("turn_number", 1)], unique=True, name="duet_turn_number_unique")
    await db.duet_turns.create_index([("duet_id", 1), ("request_id", 1)], unique=True, name="duet_turn_request_unique",
                                     partialFilterExpression={"request_id": {"$type": "string"}})
    await db.duets.create_index([("id", 1)], unique=True, name="duet_id_unique")
    await db.duets.create_index([("invite_hash", 1)], unique=True, name="duet_invite_unique")


def _entries(setting: Dict[str, Any], seat: str, turns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Everything ONE seat has been shown. The other seat's actions and narration never enter."""
    out: List[Dict[str, Any]] = [{"turn": 0, "kind": "opening", "text": setting["seats"][seat]["opening"]}]
    for t in turns:
        if t["seat"] == seat:
            out.append({"turn": t["turn_number"], "kind": "you", "action": t["action_text"], "text": t["narrative"]})
        for sentence in (t.get("observations") or {}).get(seat, []):
            out.append({"turn": t["turn_number"], "kind": "observed", "text": sentence})
    return out


def _view(setting: Dict[str, Any], doc: Dict[str, Any], seat: str, turns: List[Dict[str, Any]]) -> Dict[str, Any]:
    me = setting["seats"][seat]
    status = doc["status"]
    your_turn = status == "active" and doc["current_seat"] == seat
    them = duet.other_setting_view(setting, seat)
    return {
        "id": doc["id"],
        "title": doc["title"],
        "status": status,
        "you": {"seat": seat, "label": me["label"], "character": copy.deepcopy(me["character"])},
        "other": {**them, "joined": bool((doc["seats"] or {}).get(duet.other(seat)))},
        "turn_count": doc["turn_count"],
        "your_turn": your_turn,
        "waiting_for": them["name"] if status == "active" and not your_turn else None,
        "history": _entries(setting, seat, turns),
        "choices": copy.deepcopy((doc.get("choices") or {}).get(seat) or []) if your_turn else [],
        "known": {"boat": doc["known"][seat]["boat"]["text"]},
        "signals": [
            {"id": s["id"], "count": s["count"], "meaning": s["meaning"], "status": s["status"], "mine": s["by"] == seat}
            for s in (doc.get("world") or {}).get("signals", []) if s["status"] != "declined"
        ],
        "signal_window_open": status == "active" and doc["turn_count"] <= setting.get("signal_window_turns", 0),
        "chapter_ended": status == "chapter_ended",
    }


class CreateDuet(BaseModel):
    seat: str = Field(default="ferryman", max_length=20)


class JoinDuet(BaseModel):
    code: str = Field(min_length=8, max_length=80)


class DuetAction(BaseModel):
    action_text: str = Field(min_length=1, max_length=duet.MAX_ACTION_CHARS)
    action_request_id: str = Field(min_length=8, max_length=128)
    expected_turn_count: Optional[int] = Field(default=None, ge=0)
    # "faint": the lamp is half-shuttered. The other seat perceives something, not the signal.
    clarity: str = Field(default="clear", pattern="^(clear|faint)$")


class ProposeSignal(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    count: int = Field(ge=1, le=duet.MAX_FLASHES)
    meaning: str = Field(min_length=1, max_length=120)


class RespondSignal(BaseModel):
    accept: bool


class Share(BaseModel):
    share: bool


class _LostLease(Exception):
    pass


def register(api_router: APIRouter, *, get_db: Callable[[], Any], narrate: Narrate, require_tx: Callable[[], None]) -> None:
    async def load(duet_id: str, device_id: str):
        db = get_db()
        doc = await db.duets.find_one({"id": duet_id}, {"_id": 0})
        seat = _seat_of(doc, device_id) if doc else None
        if not doc or not seat:
            raise HTTPException(status_code=404, detail=NOT_FOUND)
        return db, doc, seat

    async def turns_of(db, duet_id: str) -> List[Dict[str, Any]]:
        return await db.duet_turns.find({"duet_id": duet_id}, {"_id": 0}).sort("turn_number", 1).to_list(length=1000)

    def new_code() -> str:
        return "DUET-" + secrets.token_urlsafe(18)

    @api_router.post("/duets", dependencies=[Depends(require_duets)])
    async def create_duet(req: CreateDuet, device_id: str = Depends(require_device_id)):
        require_tx()
        if req.seat not in duet.SEATS:
            raise HTTPException(status_code=422, detail="Pick ferryman or keeper")
        setting = duet.SETTING
        db = get_db()
        code = new_code()
        state = duet.new_duet_state(setting)
        now = _now()
        doc = {
            "id": str(uuid.uuid4()), "title": setting["title"], "setting_id": setting["id"], "status": "waiting_for_friend",
            "host_seat": req.seat, "seats": {req.seat: {"device_id": device_id, "joined_at": now}, duet.other(req.seat): None},
            "invite_hash": _hash(code), "invite_used": False, "current_seat": setting["first_seat"], "turn_count": 0,
            "revision": 0, "lease": None, "world": state["world"], "known": state["known"],
            "choices": {s: duet.opening_choices(setting, s) for s in duet.SEATS}, "optin": {},
            "created_at": now, "updated_at": now,
        }
        await db.duets.insert_one(copy.deepcopy(doc))
        return {"duet": _view(setting, doc, req.seat, []), "invite_code": code}

    @api_router.post("/duets/join", dependencies=[Depends(require_duets)])
    async def join_duet(req: JoinDuet, device_id: str = Depends(require_device_id)):
        require_tx()
        db = get_db()
        doc = await db.duets.find_one({"invite_hash": _hash(req.code)}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="That invitation is not valid")
        if _seat_of(doc, device_id):
            raise HTTPException(status_code=409, detail="You are already in this story")
        guest = duet.other(doc["host_seat"])
        if doc["invite_used"] or doc["seats"].get(guest):
            raise HTTPException(status_code=409, detail="That invitation has already been used")
        res = await db.duets.update_one(
            {"id": doc["id"], "invite_used": False, f"seats.{guest}": None, "status": "waiting_for_friend"},
            {"$set": {"invite_used": True, "status": "active", f"seats.{guest}": {"device_id": device_id, "joined_at": _now()},
                      "updated_at": _now()}, "$inc": {"revision": 1}},
        )
        if res.modified_count != 1:
            raise HTTPException(status_code=409, detail="That invitation has already been used")
        fresh = await db.duets.find_one({"id": doc["id"]}, {"_id": 0})
        return {"duet": _view(duet.SETTING, fresh, guest, [])}

    @api_router.post("/duets/{duet_id}/invite", dependencies=[Depends(require_duets)])
    async def new_invite(duet_id: str, device_id: str = Depends(require_device_id)):
        db, doc, seat = await load(duet_id, device_id)
        if seat != doc["host_seat"] or doc["status"] != "waiting_for_friend":
            raise HTTPException(status_code=409, detail="A new invitation is only possible while waiting for your friend")
        code = new_code()
        await db.duets.update_one({"id": duet_id, "status": "waiting_for_friend"},
                                  {"$set": {"invite_hash": _hash(code), "updated_at": _now()}})
        return {"invite_code": code}

    @api_router.get("/duets", dependencies=[Depends(require_duets)])
    async def list_duets(device_id: str = Depends(require_device_id)):
        db = get_db()
        rows = await db.duets.find(
            {"$or": [{f"seats.{s}.device_id": device_id} for s in duet.SEATS]}, {"_id": 0}
        ).sort("updated_at", -1).to_list(length=100)
        setting = duet.SETTING
        out = []
        for doc in rows:
            seat = _seat_of(doc, device_id)
            if not seat:
                continue
            out.append({
                "id": doc["id"], "title": doc["title"], "status": doc["status"], "seat": seat,
                "label": setting["seats"][seat]["label"], "other_name": duet.other_setting_view(setting, seat)["name"],
                "turn_count": doc["turn_count"], "your_turn": doc["status"] == "active" and doc["current_seat"] == seat,
            })
        return {"duets": out}

    @api_router.get("/duets/{duet_id}", dependencies=[Depends(require_duets)])
    async def get_duet(duet_id: str, device_id: str = Depends(require_device_id)):
        db, doc, seat = await load(duet_id, device_id)
        return {"duet": _view(duet.SETTING, doc, seat, await turns_of(db, duet_id))}

    @api_router.post("/duets/{duet_id}/action", dependencies=[Depends(require_duets)])
    async def duet_action(duet_id: str, req: DuetAction, device_id: str = Depends(require_device_id)):
        require_tx()
        db, doc, seat = await load(duet_id, device_id)
        setting = duet.SETTING
        rid = req.action_request_id

        done = await db.duet_turns.find_one({"duet_id": duet_id, "request_id": rid}, {"_id": 0})
        if done:
            if done["seat"] != seat:
                raise HTTPException(status_code=409, detail="That request id belongs to another action")
            if done.get("action_text") != req.action_text.strip() or (done.get("clarity") or "clear") != req.clarity:
                raise HTTPException(status_code=409, detail=action_requests.REQUEST_MISMATCH_DETAIL)
            return {"duet": _view(setting, doc, seat, await turns_of(db, duet_id)), "replayed": True}

        if doc["status"] == "waiting_for_friend":
            raise HTTPException(status_code=409, detail="Your friend has not joined yet")
        if doc["status"] != "active":
            raise HTTPException(status_code=409, detail="This chapter has ended")
        if doc["current_seat"] != seat:
            raise HTTPException(status_code=409, detail=f"Waiting for {duet.other_setting_view(setting, seat)['name']}")
        if req.expected_turn_count is not None and req.expected_turn_count != doc["turn_count"]:
            raise HTTPException(status_code=409, detail="The story has moved on. Reload to see where it stands.")

        now = time.time()
        leased = await db.duets.update_one(
            {"id": duet_id, "status": "active", "current_seat": seat, "turn_count": doc["turn_count"],
             "$or": [{"lease": None}, {"lease.expires_at": {"$lt": now}}]},
            {"$set": {"lease": {"request_id": rid, "seat": seat, "expires_at": now + LEASE_SECONDS}}, "$inc": {"revision": 1}},
        )
        if leased.modified_count != 1:
            raise HTTPException(status_code=409, detail="Another action is already being resolved")

        async def release() -> None:
            await db.duets.update_one({"id": duet_id, "lease.request_id": rid}, {"$set": {"lease": None}})

        try:
            doc = await db.duets.find_one({"id": duet_id}, {"_id": 0})
            turns = await turns_of(db, duet_id)
            n = doc["turn_count"]
            world, known, result = duet.resolve(setting, doc["world"], doc["known"], seat, req.action_text, req.clarity)
            entries = _entries(setting, seat, turns)
            last_own = max([t["turn_number"] for t in turns if t["seat"] == seat] or [0])
            pending_obs = [e["text"] for e in entries if e["kind"] == "observed" and e["turn"] > last_own]
            history = [e for e in entries if e["kind"] in ("you", "observed")]
            messages = duet.build_messages(setting, seat, known, history, pending_obs, req.action_text, result["note"],
                                           duet.location_text(setting, world, seat))
            async def keep_lease() -> None:
                # No revision bump: the commit below matches the revision read after the lease was taken.
                while True:
                    await asyncio.sleep(max(0.2, LEASE_SECONDS / 3))
                    await db.duets.update_one({"id": duet_id, "lease.request_id": rid},
                                              {"$set": {"lease.expires_at": time.time() + LEASE_SECONDS}})

            beat = asyncio.create_task(keep_lease())
            try:
                raw = await narrate(messages, device_id=device_id, duet_id=duet_id, request_key=rid)
            finally:
                beat.cancel()
            narrative, paragraphs, choices = duet.parse_reply(raw, duet.opening_choices(setting, seat))
            if not narrative:
                raise HTTPException(status_code=502, detail="The story engine returned nothing. Try again.")
            turn_doc = {
                "id": str(uuid.uuid4()), "duet_id": duet_id, "turn_number": n + 1, "seat": seat, "request_id": rid,
                "action_text": req.action_text.strip(), "clarity": req.clarity, "narrative": narrative, "paragraphs": paragraphs, "choices": choices,
                "observations": result["observations"], "engine_note": result["note"], "created_at": _now(),
            }
            update = {
                "$set": {"world": world, "known": known, "current_seat": duet.other(seat), "turn_count": n + 1,
                         f"choices.{seat}": choices, "lease": None, "updated_at": _now()},
                "$inc": {"revision": 1},
            }

            async def commit(session) -> None:
                res = await db.duets.update_one(
                    {"id": duet_id, "revision": doc["revision"], "lease.request_id": rid, "turn_count": n}, update, session=session
                )
                if res.modified_count != 1:
                    raise _LostLease()
                await db.duet_turns.insert_one(turn_doc, session=session)

            try:
                await turn_commit._run_transaction(db, commit)
            except _LostLease:
                raise HTTPException(status_code=409, detail="Another action got there first")
        except BaseException:
            await release()
            raise
        fresh = await db.duets.find_one({"id": duet_id}, {"_id": 0})
        return {"duet": _view(setting, fresh, seat, await turns_of(db, duet_id)), "replayed": False}

    @api_router.post("/duets/{duet_id}/signals", dependencies=[Depends(require_duets)])
    async def propose_signal(duet_id: str, req: ProposeSignal, device_id: str = Depends(require_device_id)):
        """Offer a meaning for a number of lamp flashes. Not a turn; the other seat must agree."""
        require_tx()
        db, doc, seat = await load(duet_id, device_id)
        setting = duet.SETTING
        if doc["status"] != "active":
            raise HTTPException(status_code=409, detail="Your friend has not joined yet" if doc["status"] == "waiting_for_friend" else "This chapter has ended")
        sid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{duet_id}:{seat}:{req.request_id}"))
        try:
            world = duet.propose_signal(doc["world"], seat, req.count, req.meaning, sid, doc["turn_count"], setting.get("signal_window_turns", 0))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        if world == doc["world"]:
            # A repeated proposal changes nothing, so nothing is written and the revision stands.
            return {"duet": _view(setting, doc, seat, await turns_of(db, duet_id))}
        if _lease_live(doc):
            # A turn is being written against this revision. A change now would throw that turn away.
            raise HTTPException(status_code=409, detail=BUSY)
        res = await db.duets.update_one({"id": duet_id, "revision": doc["revision"], **_no_live_lease()},
                                        {"$set": {"world": world, "updated_at": _now()}, "$inc": {"revision": 1}})
        if res.modified_count != 1:
            raise HTTPException(status_code=409, detail=SIGNAL_RACE)
        fresh = await db.duets.find_one({"id": duet_id}, {"_id": 0})
        return {"duet": _view(setting, fresh, seat, await turns_of(db, duet_id))}

    @api_router.post("/duets/{duet_id}/signals/{signal_id}/respond", dependencies=[Depends(require_duets)])
    async def respond_signal(duet_id: str, signal_id: str, req: RespondSignal, device_id: str = Depends(require_device_id)):
        require_tx()
        db, doc, seat = await load(duet_id, device_id)
        setting = duet.SETTING
        if doc["status"] != "active":
            raise HTTPException(status_code=409, detail="This chapter has ended")
        try:
            world = duet.respond_signal(doc["world"], seat, signal_id, req.accept,
                                        doc["turn_count"], setting.get("signal_window_turns", 0))
        except LookupError:
            raise HTTPException(status_code=404, detail="No such signal")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        if world == doc["world"]:
            # Already answered: nothing is written and the revision stands.
            return {"duet": _view(setting, doc, seat, await turns_of(db, duet_id))}
        if _lease_live(doc):
            raise HTTPException(status_code=409, detail=BUSY)
        known = copy.deepcopy(doc["known"])
        for s in duet.SEATS:
            known[s]["signals"] = [{"count": x["count"], "meaning": x["meaning"]} for x in duet.agreed_signals(world)]
        res = await db.duets.update_one({"id": duet_id, "revision": doc["revision"], **_no_live_lease()},
                                        {"$set": {"world": world, "known": known, "updated_at": _now()}, "$inc": {"revision": 1}})
        if res.modified_count != 1:
            raise HTTPException(status_code=409, detail=SIGNAL_RACE)
        fresh = await db.duets.find_one({"id": duet_id}, {"_id": 0})
        return {"duet": _view(setting, fresh, seat, await turns_of(db, duet_id))}

    @api_router.post("/duets/{duet_id}/end-chapter", dependencies=[Depends(require_duets)])
    async def end_chapter(duet_id: str, device_id: str = Depends(require_device_id)):
        db, doc, seat = await load(duet_id, device_id)
        if doc["status"] == "waiting_for_friend":
            raise HTTPException(status_code=409, detail="Your friend has not joined yet")
        if doc["status"] == "active":
            res = await db.duets.update_one(
                {"id": duet_id, "status": "active", "$or": [{"lease": None}, {"lease.expires_at": {"$lt": time.time()}}]},
                {"$set": {"status": "chapter_ended", "updated_at": _now()}, "$inc": {"revision": 1}},
            )
            if res.modified_count != 1:
                raise HTTPException(status_code=409, detail="An action is being resolved. Try again in a moment.")
            doc = await db.duets.find_one({"id": duet_id}, {"_id": 0})
        return {"duet": _view(duet.SETTING, doc, seat, await turns_of(db, duet_id))}

    def comparison_state(setting: Dict[str, Any], doc: Dict[str, Any], seat: str, turns: List[Dict[str, Any]]) -> Dict[str, Any]:
        optin = doc.get("optin") or {}
        both = all(optin.get(s) is True for s in duet.SEATS)
        accounts = []
        for s in ([seat, duet.other(seat)] if both else [seat]):
            c = setting["seats"][s]["character"]
            accounts.append({"seat": s, "mine": s == seat, "character": {"name": c["name"], "role": c["role"]},
                             "entries": _entries(setting, s, turns)})
        return {
            "ended": doc["status"] == "chapter_ended",
            "you_shared": optin.get(seat),
            # Never says whether the other seat declined: only that nothing is shared yet.
            "both_shared": both,
            "accounts": accounts if doc["status"] == "chapter_ended" else [],
        }

    @api_router.post("/duets/{duet_id}/comparison", dependencies=[Depends(require_duets)])
    async def share_comparison(duet_id: str, req: Share, device_id: str = Depends(require_device_id)):
        db, doc, seat = await load(duet_id, device_id)
        if doc["status"] != "chapter_ended":
            raise HTTPException(status_code=409, detail="The chapter has not ended yet")
        await db.duets.update_one({"id": duet_id}, {"$set": {f"optin.{seat}": bool(req.share), "updated_at": _now()}})
        doc = await db.duets.find_one({"id": duet_id}, {"_id": 0})
        return comparison_state(duet.SETTING, doc, seat, await turns_of(db, duet_id))

    @api_router.get("/duets/{duet_id}/comparison", dependencies=[Depends(require_duets)])
    async def get_comparison(duet_id: str, device_id: str = Depends(require_device_id)):
        db, doc, seat = await load(duet_id, device_id)
        return comparison_state(duet.SETTING, doc, seat, await turns_of(db, duet_id))

    @api_router.get("/duets/{duet_id}/export", dependencies=[Depends(require_duets)])
    async def export_duet(duet_id: str, device_id: str = Depends(require_device_id)):
        db, doc, seat = await load(duet_id, device_id)
        v = _view(duet.SETTING, doc, seat, await turns_of(db, duet_id))
        return {"format": "duet-account-v1", "title": v["title"], "you": v["you"], "history": v["history"]}
