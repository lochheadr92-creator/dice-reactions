"""Facts the player moves stand on, read from what an ordinary save already holds.

A normal or custom story never has engine-only fixtures. What it has is:

* ``rolling_state.npcs`` rows the narrator writes (a name, and whatever else it chose to say),
* ``rolling_state`` places (``scene``, ``known_rooms``, ``locations``, ``route_continuity``),
* the published prose of every turn (what the player was actually shown),
* the last turn's inventory ledger (what the current character carries),
* the controlled-character record a handover writes.

So nothing here asks for a genre, a scenario name or a hand-written field. A person is *present*
when the scene says so or when the latest published prose names them. A statement is *evidence*
when it sits in prose the current character was shown. An item is *presentable* when the ledger
lists it as carried. A move whose prerequisite is missing is reported as unavailable, with the
reason, rather than faked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import chapter_handover as ch
import claim_engine as ce
from player_api import build_player_paragraphs

class MoveError(Exception):
    """A move the engine refuses. ``status`` maps to the HTTP answer; ``detail`` is shown to the player."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


# Ledger sections that list what the character has on them. "Stored" and "Uncertain" do not count.
ON_PERSON_SECTIONS = ("Carried", "Worn", "Weapons", "Tools", "Supplies", "Currency", "Ammo")
_NONE = re.compile(r"^(none|nothing|empty|n/?a|-|—|no\s+\w+)$", re.I)
_GONE_FLAGS = ("removed", "absent", "departed", "left", "gone")


def norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def has_phrase(text: Any, phrase: Any) -> bool:
    """Whole-word phrase match on normalised text."""
    want = norm(phrase)
    if not want:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(want).replace(r"\ ", r"\s+") + r"(?![a-z0-9])", norm(text)) is not None


def split_items(value: Any) -> List[str]:
    """Item names from a ledger line. Mirrors the play screen's splitting."""
    text = str(value or "")
    parts: List[str] = []
    depth, cur = 0, ""
    for ch_ in text:
        if ch_ in "([":
            depth += 1
        if ch_ in ")]":
            depth = max(0, depth - 1)
        if depth == 0 and ch_ in ",;\n":
            parts.append(cur)
            cur = ""
            continue
        cur += ch_
    parts.append(cur)
    out: List[str] = []
    for raw in parts:
        for piece in re.split(r"\s+and\s+(?![^()]*\))", raw, flags=re.I):
            s = re.sub(r"^[-*\s]+", "", piece)
            s = re.sub(r"[.\s]+$", "", s).strip()
            if s and not _NONE.match(s):
                out.append(s)
    return out


def ledger_items(ledger: Any) -> List[str]:
    """What the current character has on them, from the last turn's ledger."""
    if not isinstance(ledger, Mapping):
        return []
    seen: List[str] = []
    for section in ON_PERSON_SECTIONS:
        for key, value in ledger.items():
            if str(key).strip().lower() == section.lower():
                for item in split_items(value):
                    if norm(item) not in {norm(s) for s in seen}:
                        seen.append(item)
    return seen


def item_matches(item: str, wanted: str) -> bool:
    """A named item matches a ledger entry by whole phrase, ignoring a leading quantity."""
    a = re.sub(r"^\d+\s*x?\s*", "", norm(item))
    b = re.sub(r"^\d+\s*x?\s*", "", norm(wanted))
    return bool(a) and bool(b) and (a == b or has_phrase(a, b) or has_phrase(b, a))


# ---------------------------------------------------------------------------
# Who the player is, and who is here
# ---------------------------------------------------------------------------
def character_key(session: Mapping[str, Any]) -> str:
    """Who holds knowledge, items and skills on the player's side. Stable across a handover."""
    who = ch.current_character(session)
    return str(who.get("actor_id") or "player")


def character_name(session: Mapping[str, Any]) -> str:
    return str(ch.current_character(session).get("name") or "the player")


def alive(rolling: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    if any(row.get(flag) for flag in _GONE_FLAGS):
        return False
    return ce._alive(dict(rolling), dict(row))


def _named_rows(rolling: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [r for r in rolling.get("npcs") or [] if isinstance(r, dict) and ce.npc_name(r)]


def _distinct_tokens(rolling: Mapping[str, Any]) -> Dict[str, List[str]]:
    """Per person: the name words only they use ("Brother" is no use when two people share it)."""
    rows = _named_rows(rolling)
    counts: Dict[str, int] = {}
    for r in rows:
        for tok in set(norm(ce.npc_name(r)).split()):
            counts[tok] = counts.get(tok, 0) + 1
    out: Dict[str, List[str]] = {}
    for r in rows:
        out[ce.npc_key(r)] = [t for t in norm(ce.npc_name(r)).split() if len(t) >= 3 and counts.get(t) == 1]
    return out


def named_in(text: Any, row: Mapping[str, Any], rolling: Mapping[str, Any]) -> bool:
    """Is this person named in the text: the full name, or a name word no one else here shares."""
    name = ce.npc_name(dict(row))
    if has_phrase(text, name):
        return True
    return any(has_phrase(text, tok) for tok in _distinct_tokens(rolling).get(ce.npc_key(dict(row)), []))


def _at_scene(rolling: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    scene = norm(rolling.get("scene") or rolling.get("location") or "")
    where = norm(row.get("location") or row.get("last_seen") or "")
    return bool(scene) and bool(where) and (scene == where or has_phrase(scene, where) or has_phrase(where, scene))


def people(rolling: Mapping[str, Any], latest_text: str = "") -> List[Dict[str, Any]]:
    """Everyone the cast lists, with whether they are here now. ``row`` is the narrator's own row."""
    out = []
    for row in _named_rows(rolling):
        if not alive(rolling, row):
            continue
        here = _at_scene(rolling, row) or (bool(latest_text) and named_in(latest_text, row, rolling) and not _elsewhere(rolling, row))
        out.append({"name": ce.npc_name(row), "key": ce.npc_key(row), "present": here, "row": row})
    return out


def _elsewhere(rolling: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    """The row puts them somewhere other than the scene, so being named in prose does not make them present."""
    where = norm(row.get("location") or row.get("last_seen") or "")
    scene = norm(rolling.get("scene") or rolling.get("location") or "")
    return bool(where) and bool(scene) and not (where == scene or has_phrase(scene, where) or has_phrase(where, scene))


def find_person(rolling: Mapping[str, Any], ref: str, latest_text: str = "") -> Optional[Dict[str, Any]]:
    want = norm(ref)
    for p in people(rolling, latest_text):
        if want and want in {norm(p["name"]), p["key"]}:
            return p
    return None


# ---------------------------------------------------------------------------
# Published prose, as one character was shown it
# ---------------------------------------------------------------------------
def paragraphs_of(row: Mapping[str, Any]) -> List[str]:
    return build_player_paragraphs(row.get("paragraphs"))


def latest_text(rows: Sequence[Mapping[str, Any]]) -> str:
    """The prose of the newest published turn: the scene the player is looking at."""
    if not rows:
        return ""
    newest = max(rows, key=lambda r: int(r.get("turn_number") or 0))
    return " ".join(paragraphs_of(newest))


def was_shown(session: Mapping[str, Any], turn_number: int, paragraph: str) -> bool:
    """Could the current character have seen this passage?

    Before a handover every published passage is theirs. After one, prose from before the
    boundary belongs to the former protagonist unless the passage names the current character,
    which is the only evidence the engine has that they were there.
    """
    floor = ch.replay_floor(session)
    if floor == 0 or int(turn_number) >= floor:
        return True
    name = ch.current_character(session).get("name")
    return bool(name) and has_phrase(paragraph, name)


@dataclass
class Context:
    """Everything a move may read. Built once per request; nothing here is written back."""

    session: Dict[str, Any]
    rolling: Dict[str, Any]
    rows: List[Dict[str, Any]] = field(default_factory=list)  # published turns: turn_number, paragraphs
    ledger: Dict[str, Any] = field(default_factory=dict)
    pins: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # notebook pins the move named
    turn: int = 0
    npc_ledger: Dict[str, Any] = field(default_factory=dict)
    play: Dict[str, Any] = field(default_factory=dict)  # play_state as the request found it

    @property
    def me(self) -> str:
        return character_key(self.session)

    @property
    def my_name(self) -> str:
        return character_name(self.session)

    def scene_text(self) -> str:
        return latest_text(self.rows)

    def row_for(self, turn_number: int) -> Optional[Dict[str, Any]]:
        for r in self.rows:
            if int(r.get("turn_number") or 0) == int(turn_number):
                return r
        return None

    def held(self) -> List[str]:
        return ledger_items(self.ledger)


_HOSTILE = {"hostile", "enemy", "antagonist", "adversary"}
_FRIENDLY = {"ally", "friendly", "friend", "loyal", "devoted"}


def hostile(row: Mapping[str, Any]) -> bool:
    return bool(row.get("refuses_orders")) or norm(row.get("stance")) in _HOSTILE


def trust_of(rolling: Mapping[str, Any], row: Mapping[str, Any]) -> int:
    """How far this person trusts the player, 0 to 100 in practice.

    The engine's own relationship vector wins. A row that carries a number uses it. With no
    number, the narrator's stance decides: an ally is trusting, a hostile person is not, anyone
    else is wary but not closed.
    """
    name = norm(ce.npc_name(dict(row)))
    for vec in rolling.get("relationship_vectors") or []:
        if isinstance(vec, dict) and norm(vec.get("name")) == name and isinstance(vec.get("trust"), (int, float)):
            return int(vec["trust"])
    if isinstance(row.get("trust"), (int, float)):
        return int(row["trust"])
    stance = norm(row.get("stance"))
    if stance in _FRIENDLY:
        return 60
    if stance in _HOSTILE:
        return 0
    return 30


def ref(person: Mapping[str, Any]) -> Dict[str, str]:
    return {"id": person["key"], "name": person["name"]}


def clean(text: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


# ---------------------------------------------------------------------------
# Engine-side changes to what a person carries
# ---------------------------------------------------------------------------
def ledger_remove(ledger: Mapping[str, Any], item: str) -> Dict[str, Any]:
    """The player's ledger without ``item``, in every on-person section."""
    out: Dict[str, Any] = dict(ledger)
    sections = {s.lower() for s in ON_PERSON_SECTIONS}

    def bare(text: Any) -> str:
        return re.sub(r"^\d+\s*x?\s*", "", norm(text))

    # The exact item goes when the ledger has it, so losing "knife" leaves "knife sheath" alone.
    # Only when nothing matches exactly does the looser phrase match decide.
    want = bare(item)
    exact = any(
        bare(i) == want
        for key, value in out.items() if str(key).strip().lower() in sections
        for i in split_items(value)
    )
    for key, value in list(out.items()):
        if str(key).strip().lower() not in sections:
            continue
        kept = [i for i in split_items(value) if not ((bare(i) == want) if exact else item_matches(i, item))]
        out[key] = "; ".join(kept) if kept else "-"
    return out


def ledger_add(ledger: Mapping[str, Any], item: str) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(ledger)
    if any(item_matches(i, item) for i in ledger_items(out)):
        return out
    key = next((k for k in out if str(k).strip().lower() == "carried"), "Carried")
    current = [i for i in split_items(out.get(key))]
    out[key] = "; ".join(current + [item])
    return out


def npc_inventory(ctx_ledger: Mapping[str, Any], row: Mapping[str, Any]) -> List[str]:
    """What this person truly carries. Engine use only: the player sees only what they have learned."""
    import npc_possessions as np

    got = np.inventory_of(dict(ctx_ledger), row)
    if got is not None:
        return got
    raw = row.get("inventory")
    return [str(i) for i in raw] if isinstance(raw, list) else []


def npc_known_items(ctx_ledger: Mapping[str, Any], row: Mapping[str, Any]) -> List[str]:
    import npc_possessions as np

    return np.known_inventory_of(dict(ctx_ledger), row)


def npc_take(npc_ledger: Dict[str, Any], rolling: Dict[str, Any], row: Mapping[str, Any], item: str, turn: int, *, reveal: bool = False) -> None:
    import npc_possessions as np

    items = [i for i in npc_inventory(npc_ledger, row) if not item_matches(i, item)]
    items.append(item)
    np.set_inventory(npc_ledger, rolling, dict(row), items, turn=turn)
    if reveal:
        entry = np._rows(npc_ledger).get(np.key_for(row))
        if entry is not None and not any(item_matches(k, item) for k in entry.get("known", [])):
            entry.setdefault("known", []).append(item)


def npc_lose(npc_ledger: Dict[str, Any], rolling: Dict[str, Any], row: Mapping[str, Any], item: str, turn: int) -> None:
    import npc_possessions as np

    items = [i for i in npc_inventory(npc_ledger, row) if not item_matches(i, item)]
    np.set_inventory(npc_ledger, rolling, dict(row), items, turn=turn)
