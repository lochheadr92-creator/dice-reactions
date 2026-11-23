"""Two friends, opposite sides of one event: the engine half.

The engine owns what happened and who could observe it. The narrator describes one player's
private view and never sees what the other player said, planned or was shown.

Isolation is structural, not cosmetic. A narrator request for seat S is built from:
  * S's own character, inventory and recent history,
  * what S knows about the shared world,
  * observations the engine decided S could witness (engine-written sentences),
  * S's own action.
Nothing the other seat typed, was narrated or reasoned about is ever an input to that request.
The other seat learns an event only as a short engine sentence, and only if there is a line of
sight (the setting's only channel of in-world communication is the lamp the keeper holds).

This module is pure: no database, no network. ``duet_api`` stores and serves it.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

SEATS = ("ferryman", "keeper")
MAX_ACTION_CHARS = 600
MAX_FLASHES = 9
HISTORY_FOR_NARRATOR = 6

SETTING: Dict[str, Any] = {
    "id": "two-lights",
    "title": "Two Lights",
    "first_seat": "ferryman",
    "seats": {
        "ferryman": {
            "label": "Ferryman",
            "character": {"name": "Corin Hale", "role": "ferryman", "inventory": ["ferry pole", "tide table"]},
            "location": "the harbour",
            "opening": (
                "Dusk settles on the harbour. You are Corin Hale, ferryman, and the ferry skiff, the only boat "
                "on this stretch of coast, strains at its mooring. Far up the headland the lighthouse is dark "
                "except for one window."
            ),
            "choices": [
                "Check the tide table",
                "Watch the lighthouse",
                "Launch the skiff into the channel",
                "Wait on the quay",
            ],
        },
        "keeper": {
            "label": "Signal keeper",
            "character": {"name": "Ines Rook", "role": "signal keeper", "inventory": ["signal lamp", "logbook"]},
            "location": "the lighthouse",
            "opening": (
                "The lamp room is cold. You are Ines Rook, signal keeper, and from the gallery you can see the "
                "whole harbour and the channel beyond it, with the ferry skiff small and dark below."
            ),
            "choices": [
                "Write in the logbook",
                "Send three flashes with the signal lamp",
                "Watch the channel",
                "Trim the lamp",
            ],
        },
    },
    # Pairs that can see each other. The lamp is the only in-world channel between the two seats.
    "sight": [["the lighthouse", "the harbour"], ["the lighthouse", "the channel"]],
    "boat": {"name": "the ferry skiff", "location": "the harbour", "state": "moored"},
    # Signals can be agreed only while both are still within hailing distance of each other: until the
    # first action is taken. After that the lamp is the only channel, and it cannot carry a new meaning.
    "signal_window_turns": 0,
}

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_FLASH = re.compile(
    r"\b(?:(one|two|three|four|five|six|seven|eight|nine|\d+)\s+(?:(?:long|short|quick|slow)\s+)?)?(?:flash(?:es)?|blink(?:s)?)\b",
    re.I,
)
_SEND = re.compile(r"\b(?:send|give|flash|blink|signal|make|show|flicker)\w*\b", re.I)
_LAUNCH = re.compile(r"\b(?:launch(?:es)?|push(?:es)? off|cast(?:s)? off|shove(?:s)? off|row(?:s)? out|set(?:s)? out)\b", re.I)


def other(seat: str) -> str:
    return SEATS[1] if seat == SEATS[0] else SEATS[0]


def other_setting_view(setting: Dict[str, Any], seat: str) -> Dict[str, Any]:
    """What a seat may know about the other seat: who they are, nothing they carry or think."""
    c = setting["seats"][other(seat)]["character"]
    return {"seat": other(seat), "name": c["name"], "role": c["role"]}


def can_see(world: Dict[str, Any], a: str, b: str) -> bool:
    return a == b or [a, b] in world["sight"] or [b, a] in world["sight"]


def boat_fact(boat: Dict[str, Any]) -> Dict[str, str]:
    where = boat["location"]
    return {"state": boat["state"], "where": where, "text": f"{boat['name']} is {'out in' if boat['state'] == 'underway' else 'moored at'} {where}"}


def new_duet_state(setting: Dict[str, Any]) -> Dict[str, Any]:
    world = {"boat": copy.deepcopy(setting["boat"]), "sight": copy.deepcopy(setting["sight"]), "flashes": 0, "signals": []}
    known: Dict[str, Any] = {}
    for seat in SEATS:
        # Both start knowing where the one boat is. After that it is only what each can see.
        known[seat] = {"boat": boat_fact(world["boat"])}
    return {"world": world, "known": known}


def opening_choices(setting: Dict[str, Any], seat: str) -> List[Dict[str, str]]:
    return [{"label": "ABCD"[i], "text": t} for i, t in enumerate(setting["seats"][seat]["choices"])]


def _count_word(n: int) -> str:
    return {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine"}.get(n, str(n))


def agreed_signals(world: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [s for s in world.get("signals", []) if s.get("status") == "agreed"]


def propose_signal(world: Dict[str, Any], seat: str, count: int, meaning: str, sid: str, turn_count: int, window: int) -> Dict[str, Any]:
    """One seat offers: this many flashes will mean this. Not a turn; the other seat must agree."""
    world = copy.deepcopy(world)
    world.setdefault("signals", [])  # a story begun before signals existed has none yet
    if turn_count > window:
        raise ValueError("That can only be settled before the first lamp is lit.")
    if not 1 <= count <= MAX_FLASHES:
        raise ValueError(f"Choose between 1 and {MAX_FLASHES} flashes.")
    meaning = " ".join(str(meaning or "").split())[:120]
    if not meaning:
        raise ValueError("Say what it means.")
    if any(s["id"] == sid for s in world["signals"]):
        return world
    if any(s["count"] == count and s["status"] in ("proposed", "agreed") for s in world["signals"]):
        raise ValueError("That number of flashes already means something.")
    world["signals"].append({"id": sid, "count": count, "meaning": meaning, "by": seat, "status": "proposed"})
    return world


def respond_signal(world: Dict[str, Any], seat: str, sid: str, accept: bool) -> Dict[str, Any]:
    world = copy.deepcopy(world)
    for s in world.get("signals", []):
        if s["id"] == sid:
            if s["by"] == seat:
                raise ValueError("The other keeper of the signal has to answer it.")
            if s["status"] == "proposed":
                s["status"] = "agreed" if accept else "declined"
            return world
    raise LookupError("No such signal")


def resolve(setting: Dict[str, Any], world: Dict[str, Any], known: Dict[str, Any], seat: str, action_text: str,
            clarity: str = "clear") -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Apply one action. Returns (world, known, result).

    result = {"note": engine sentence for the actor's narrator or None,
              "observations": {seat: [sentence]},   # only seats that could witness it
              "event": kind or None}
    """
    world = copy.deepcopy(world)
    known = copy.deepcopy(known)
    me = setting["seats"][seat]
    here = me["location"]
    result: Dict[str, Any] = {"note": None, "observations": {}, "event": None}
    text = action_text or ""

    flash = _FLASH.search(text) if _SEND.search(text) else None
    if flash and "signal lamp" in me["character"]["inventory"]:
        raw = flash.group(1)
        count = _NUMBER_WORDS.get((raw or "").lower(), int(raw) if raw and raw.isdigit() else 1)
        count = max(1, min(MAX_FLASHES, count))
        world["flashes"] = int(world.get("flashes", 0)) + count
        result["event"] = "flashes"
        faint = clarity == "faint"
        meant = next((s["meaning"] for s in agreed_signals(world) if s["count"] == count), None)
        result["note"] = f"The lamp flashes {count} time{'s' if count != 1 else ''}{', faint and half-shuttered' if faint else ''}. Only that is certain; who sees it, and what they make of it, is not for you to say."
        if meant:
            result["note"] += f" It is the signal you agreed: {meant}."
        sentence = f"{_count_word(count)} flash{'es' if count != 1 else ''} from the {here.replace('the ', '')} lamp."
        if faint:
            sentence = f"A faint, uncertain flicker from the {here.replace('the ', '')} lamp. You cannot tell how many, or whether it was meant for you."
        elif meant:
            sentence += f" That is the signal you agreed: {meant}."
        for o in SEATS:
            if o != seat and can_see(world, setting["seats"][o]["location"], here):
                result["observations"].setdefault(o, []).append(sentence)
    elif flash and not _LAUNCH.search(text):
        result["note"] = "You have no lamp to signal with, so nothing flashes."
    elif _LAUNCH.search(text):
        boat = world["boat"]
        if "ferry pole" not in me["character"]["inventory"] or here != setting["boat"]["location"]:
            result["note"] = "You are not where the skiff is moored, so you cannot launch it."
        elif boat["state"] == "underway":
            result["note"] = "The skiff is already out in the channel. There is only the one boat, and it cannot be launched twice."
        else:
            origin = boat["location"]
            boat["location"], boat["state"] = "the channel", "underway"
            result["event"] = "launch"
            result["note"] = "The skiff slides off the quay and is now out in the channel."
            sentence = f"{boat['name'].capitalize()} slips away from {origin} into the channel."
            for o in SEATS:
                if o != seat and (can_see(world, setting["seats"][o]["location"], origin)
                                  or can_see(world, setting["seats"][o]["location"], "the channel")):
                    result["observations"].setdefault(o, []).append(sentence)

    # Anyone who can see where the boat is now knows where it is; the actor always does.
    for s in SEATS:
        if (s == seat and result["event"] == "launch") or can_see(world, setting["seats"][s]["location"], world["boat"]["location"]):
            known[s]["boat"] = boat_fact(world["boat"])
    return world, known, result


def build_messages(setting: Dict[str, Any], seat: str, known: Dict[str, Any], own_history: List[Dict[str, Any]],
                   observations: List[str], action_text: str, note: Optional[str]) -> List[Dict[str, str]]:
    me = setting["seats"][seat]
    c = me["character"]
    system = (
        "You narrate ONE player's private view of a two-player story on opposite sides of one event. "
        f"The player is {c['name']}, {c['role']}. You do not know what the other player thinks, plans or does. "
        "Never state or invent the other player's reasons, actions or whereabouts unless an OBSERVATION below says so. "
        "Write 2 short paragraphs in second person, then four choices.\n"
        "Reply exactly as <narrative>...</narrative><choices>\nA. ...\nB. ...\nC. ...\nD. ...\n</choices>"
    )
    lines = [
        f"CHARACTER: {c['name']}, {c['role']}. Carrying: {', '.join(c['inventory'])}. Standing at {me['location']}.",
        f"WHAT YOU KNOW OF THE WORLD: {known[seat]['boat']['text']}.",
    ]
    agreed = known[seat].get("signals") or []
    if agreed:
        lines.append("SIGNALS YOU AGREED WITH THE OTHER PLAYER:\n" + "\n".join(f"- {s['count']} flashes means: {s['meaning']}" for s in agreed))
    if observations:
        lines.append("OBSERVATIONS since your last turn (engine facts, state them plainly):\n" + "\n".join(f"- {o}" for o in observations))
    if own_history:
        lines.append("YOUR RECENT STORY:\n" + "\n".join(f"- {h}" for h in own_history[-HISTORY_FOR_NARRATOR:]))
    if note:
        lines.append(f"[ENGINE_RESULT] {note}")
    lines.append(f"Player action: {action_text}")
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(lines)}]


def parse_reply(raw: str, fallback_choices: List[Dict[str, str]]) -> Tuple[str, List[str], List[Dict[str, str]]]:
    text = str(raw or "")
    m = re.search(r"<narrative>(.*?)</narrative>", text, re.S | re.I)
    narrative = (m.group(1) if m else re.sub(r"<[^>]+>", " ", text.split("<choices>")[0])).strip()
    narrative = re.sub(r"\n{3,}", "\n\n", narrative)[:2400]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", narrative) if p.strip()]
    choices: List[Dict[str, str]] = []
    cm = re.search(r"<choices>(.*?)</choices>", text, re.S | re.I)
    if cm:
        for line in cm.group(1).splitlines():
            lm = re.match(r"\s*([A-D])[.)]\s*(.+)", line)
            if lm:
                choices.append({"label": lm.group(1), "text": lm.group(2).strip()[:160]})
    return narrative, paragraphs, choices if len(choices) == 4 else fallback_choices
