"""Agree on a signal with someone, and use it.

A signal is a perceivable sign (a phrase, a visible mark, a sound) with a meaning two people agreed on.
Three things are decided separately when it is sent: what was sent, who in the scene perceived it, and
whose knowledge lets them interpret it. Anyone present can notice the sign. Only the two who agreed
know what it means. A faint signal is perceived by the partner as something, not as the signal.

State (``play_state["signal"]``): ``signals`` (agreement, parties) and ``sends`` (what happened).
"""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional, Tuple

import play_facts as pf
from play_facts import Context, MoveError

KIND = "signal"
RESULT_MARKER = "[SIGNAL_RESULT_V1]"
STANDING_MARKER = "[SIGNAL_STANDING_V1]"
_NS = uuid.UUID("a7d20c5b-3e18-4d96-82f4-5b0c6e19d3a8")
CHANNELS = {"phrase": "a spoken phrase", "sight": "a visible sign", "sound": "a sound"}
MIN_TRUST = 20
MAX_SIGNALS = 12
MAX_SENDS = 40


def new_state() -> Dict[str, Any]:
    return {"signals": [], "sends": []}


def _part(state: Dict[str, Any]) -> Dict[str, Any]:
    part = state.setdefault(KIND, new_state())
    part.setdefault("signals", [])
    part.setdefault("sends", [])
    return part


def _sig(part: Dict[str, Any], sid: Any) -> Dict[str, Any]:
    for s in part["signals"]:
        if s["id"] == str(sid):
            return s
    raise MoveError(404, "You have not agreed that signal.")


def apply(state: Dict[str, Any], ctx: Context, args: Dict[str, Any], *, turn: int, request_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    st = copy.deepcopy(state)
    part = _part(st)
    rid = str(uuid.uuid5(_NS, f"signal:{request_id}"))
    for s in part["signals"]:
        if rid in s["request_ids"]:
            return st, _result(s, "replay", None, replay=True)
    me = ctx.me
    op = str(args.get("op") or "agree")
    if op == "agree":
        person = pf.find_person(ctx.rolling, str(args.get("with") or ""), ctx.scene_text())
        if person is None or not person["present"]:
            raise MoveError(422, "That person is not here to agree anything with.")
        if pf.hostile(person["row"]) or pf.trust_of(ctx.rolling, person["row"]) < MIN_TRUST:
            raise MoveError(422, f"{person['name']} does not trust you enough to settle a signal.")
        channel = str(args.get("channel") or "")
        if channel not in CHANNELS:
            raise MoveError(422, "Choose how it will be sent: " + ", ".join(CHANNELS) + ".")
        sign = pf.clean(args.get("sign"), 80)
        meaning = pf.clean(args.get("meaning"), 120)
        if not sign or not meaning:
            raise MoveError(422, "Say what the sign is and what it means.")
        for s in part["signals"]:
            if pf.norm(s["sign"]) == pf.norm(sign) and any(p["id"] == person["key"] for p in s["parties"]):
                raise MoveError(409, "You already agreed that one.")
        sig = {"id": rid, "request_ids": [rid], "channel": channel, "sign": sign, "meaning": meaning, "turn": turn,
               "parties": [{"id": me, "name": ctx.my_name}, pf.ref(person)]}
        part["signals"].append(sig)
        part["signals"] = part["signals"][-MAX_SIGNALS:]
        return st, _result(sig, "agree", None, replay=False)
    if op != "send":
        raise MoveError(422, "Agree a signal or send one.")
    sig = _sig(part, args.get("signal_id"))
    if not any(p["id"] == me for p in sig["parties"]):
        raise MoveError(422, "That is not your signal.")
    clarity = str(args.get("clarity") or "clear")
    if clarity not in ("clear", "faint"):
        raise MoveError(422, "Send it clearly or faintly.")
    partner = next(p for p in sig["parties"] if p["id"] != me)
    here = [p for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"]]
    perceivers = [pf.ref(p) for p in here]
    partner_here = any(p["key"] == partner["id"] for p in here)
    interpreters = [p for p in perceivers if p["id"] == partner["id"]] if clarity == "clear" else []
    unsure = [p for p in perceivers if p["id"] == partner["id"]] if clarity == "faint" else []
    send = {"turn": turn, "clarity": clarity, "perceived_by": perceivers, "understood_by": interpreters, "unsure": unsure,
            "partner_here": partner_here, "by": me}
    sig.setdefault("sends", []).append(send)
    sig["request_ids"].append(rid)
    part["sends"].append({"signal": sig["id"], **send})
    part["sends"] = part["sends"][-MAX_SENDS:]
    return st, _result(sig, "send", send, replay=False)


def _result(sig: Dict[str, Any], op: str, send: Optional[Dict[str, Any]], *, replay: bool) -> Dict[str, Any]:
    partner = sig["parties"][1]["name"]
    chan = CHANNELS[sig["channel"]]
    if op == "agree":
        line = [f"The player and {partner} settle on {chan}: \"{sig['sign']}\". Between them it means: {sig['meaning']}. Nobody else heard the agreement."]
    elif op == "send":
        line = [f"The player sends {chan}: \"{sig['sign']}\", {'clearly' if send['clarity'] == 'clear' else 'faintly, half hidden'}."]
        names = [p["name"] for p in send["perceived_by"] if p["id"] != sig["parties"][0]["id"]]
        if names:
            line.append(f"Everyone here can notice the sign: {', '.join(names)}. Only {partner} knows what it means; no one else may be told or guess its meaning.")
        if send["understood_by"]:
            line.append(f"{partner} recognises it: {sig['meaning']}. {partner} may act on it on their own from here.")
        elif send["unsure"]:
            line.append(f"{partner} notices something but cannot be sure it was the signal. {partner} may guess, hold back, or act on incomplete information. Do not confirm what it meant.")
        else:
            line.append(f"{partner} is not here to perceive it, so it reaches no one who knows its meaning.")
    else:
        line = ["Already done."]
    return {"kind": KIND, "op": op, "replayed": replay, "directive": f"{RESULT_MARKER}\n" + "\n".join(f"- {l}" for l in line),
            "terms": line, "id": sig["id"], "action_text": f"You settle a signal with {partner}." if op == "agree" else f"You give {partner} the signal."}


def narrator_context(state: Dict[str, Any], ctx: Context, result: Optional[Dict[str, Any]]) -> str:
    part = (state or {}).get(KIND) or {}
    parts: List[str] = []
    if result and result.get("kind") == KIND:
        parts.append(result["directive"])
    here = {p["key"] for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"]}
    lines: List[str] = []
    for s in part.get("signals") or []:
        if not any(p["id"] == ctx.me for p in s["parties"]):
            continue
        partner = next(p for p in s["parties"] if p["id"] != ctx.me)
        if partner["id"] in here:
            lines.append(f"{partner['name']} and the player have a sign: {CHANNELS[s['channel']]} \"{s['sign']}\" means {s['meaning']}. No one else knows it.")
    if lines:
        parts.append(f"{STANDING_MARKER}\n" + "\n".join(f"- {l}" for l in lines))
    return "\n\n".join(parts)


def player_view(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for s in ((state or {}).get(KIND) or {}).get("signals") or []:
        sends = [{"turn": x["turn"], "clarity": x["clarity"], "partner_understood": bool(x["understood_by"]),
                  "others_noticed": max(0, len(x["perceived_by"]) - (1 if x["partner_here"] else 0))} for x in s.get("sends", [])]
        out.append({"id": s["id"], "channel": s["channel"], "sign": s["sign"], "meaning": s["meaning"], "with": s["parties"][1]["name"], "sends": sends})
    return out


def options(ctx: Context) -> Dict[str, Any]:
    part = (ctx.play or {}).get(KIND) or {}
    here = [p for p in pf.people(ctx.rolling, ctx.scene_text()) if p["present"]]
    willing = [{"name": p["name"]} for p in here if not pf.hostile(p["row"]) and pf.trust_of(ctx.rolling, p["row"]) >= MIN_TRUST]
    mine = []
    for s in part.get("signals") or []:
        if any(p["id"] == ctx.me for p in s["parties"]):
            partner = next(p for p in s["parties"] if p["id"] != ctx.me)
            mine.append({"id": s["id"], "sign": s["sign"], "meaning": s["meaning"], "channel": s["channel"], "with": partner["name"],
                         "partner_here": any(p["key"] == partner["id"] for p in here)})
    reason = None if (willing or mine) else "Nobody here trusts you enough to settle a signal with."
    return {"kind": KIND, "available": reason is None, "reason": reason, "partners": willing, "signals": mine, "channels": CHANNELS}
