"""Engine-owned memory of what each NPC carries, and what the player is allowed to know about it.

``rolling_state["npcs"]`` is replaced wholesale by whatever the narrator re-emits each turn, so
an NPC's items and condition were lost whenever a row was rewritten or an NPC left the scene
and came back. The ledger lives on the save (``session["npc_ledger"]``), is never shown raw to
the player, and is restored into the cast after every merge.

Knowledge rules (the player is not omniscient about what someone else has):
* An item is KNOWN to the player when the NPC handed it over, when the NPC answered a direct
  question about it, or when the narrator itself put it on stage (it emitted the item).
* Everything else is hidden. The narrator is never sent hidden items: ``narrator_view`` replaces
  ``inventory`` with ``inventory_known``.
* A direct question or a request for an item is decided by the engine, not the narrator. The NPC
  answers only when trust is high enough (``DISCLOSE_MIN_TRUST``) and they are not hostile.
  Otherwise the narrator is told to show the refusal in character and reveal nothing.
* The narrator can add items and remove items the player already knows about. It cannot remove
  hidden ones, so a rewritten cast never erases what the engine holds.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

import claim_engine as ce
import order_engine as oe

LEDGER_VERSION = 1
PERSISTED_FIELDS = ("inventory", "condition", "contacts")
MAX_LEDGER_ROWS = 64
MAX_ITEMS = 12
MAX_TEXT = 80
DISCLOSE_MIN_TRUST = 40
DIRECTIVE_MARKER = "[NPC_POSSESSIONS_V1]"
_FRIENDLY = {"ally", "friendly", "loyal", "devoted"}


def _name(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    return str(row.get("name") or row.get("npc") or "").strip()


def key_for(row: Any) -> str:
    """Stable identity: npc_id when present, otherwise the lower-cased name."""
    if not isinstance(row, dict):
        return ""
    ident = str(row.get("npc_id") or row.get("id") or "").strip().lower()
    return ident or _name(row).lower()


def _clean_items(value: Any) -> List[str]:
    out: List[str] = []
    if isinstance(value, str):
        value = [value]
    for item in value or []:
        text = str(item.get("object") if isinstance(item, dict) else item or "").strip()[:MAX_TEXT]
        if text and text.lower() not in {x.lower() for x in out}:
            out.append(text)
        if len(out) >= MAX_ITEMS:
            break
    return out


def _clean(field: str, value: Any) -> Any:
    if field in ("inventory", "contacts"):
        return _clean_items(value)
    return str(value or "").strip()[:MAX_TEXT]


def _has(items: List[str], item: str) -> bool:
    return item.lower() in {i.lower() for i in items}


def new_ledger() -> Dict[str, Any]:
    return {"version": LEDGER_VERSION, "rows": {}}


def _rows(ledger: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = ledger.get("rows")
    if not isinstance(rows, dict):
        rows = {}
        ledger["rows"] = rows
    return rows


def _known(entry: Dict[str, Any]) -> List[str]:
    inv = entry.get("inventory") or []
    return [i for i in _clean_items(entry.get("known")) if _has(inv, i)]


def ensure(prior_ledger: Optional[Dict[str, Any]], rolling: Optional[Dict[str, Any]],
           *, turn: int = 0) -> Dict[str, Any]:
    """Make sure every cast row that carries an inventory has a ledger row. New rows start hidden."""
    ledger = copy.deepcopy(prior_ledger) if isinstance(prior_ledger, dict) else new_ledger()
    rows = _rows(ledger)
    for npc in (rolling or {}).get("npcs") or []:
        key = key_for(npc)
        if not key or key in rows or "inventory" not in npc:
            continue
        rows[key] = {"name": _name(npc), "inventory": _clean_items(npc["inventory"]), "known": [], "last_turn": turn}
        if npc.get("npc_id"):
            rows[key]["npc_id"] = str(npc["npc_id"])
    return ledger


def apply(prior_ledger: Optional[Dict[str, Any]], rolling: Optional[Dict[str, Any]],
          *, turn: int = 0, narrator_npcs: Optional[List[Any]] = None) -> Tuple[Dict[str, Any], List[str]]:
    """Reconcile the ledger with the merged cast. Mutates ``rolling`` rows, returns (ledger, notes).

    ``narrator_npcs`` are the rows the narrator itself emitted this turn. Without it every row in
    ``rolling`` counts as narrator output.
    """
    ledger = ensure(prior_ledger, rolling, turn=turn)
    rows = _rows(ledger)
    notes: List[str] = []
    if not isinstance(rolling, dict):
        return ledger, notes
    emitted_by_key = {
        key_for(n): n for n in (narrator_npcs if narrator_npcs is not None else rolling.get("npcs") or [])
        if isinstance(n, dict) and key_for(n)
    }
    for npc in rolling.get("npcs") or []:
        key = key_for(npc)
        if not key:
            continue
        entry = rows.setdefault(key, {"name": _name(npc), "known": []})
        entry["name"] = _name(npc) or entry.get("name", "")
        if npc.get("npc_id"):
            entry["npc_id"] = str(npc["npc_id"])
        emitted = emitted_by_key.get(key) or {}
        for field in PERSISTED_FIELDS:
            if field == "inventory":
                _reconcile_inventory(entry, npc, emitted, turn)
                if "inventory" in entry:
                    if "inventory" not in npc:
                        notes.append(f"npc_ledger:restored_inventory:{entry.get('name')}")
                    npc["inventory"] = list(entry["inventory"])
                continue
            if field in npc:
                cleaned = _clean(field, npc[field])
                if entry.get(field) != cleaned:
                    entry[field] = cleaned
                    entry["last_turn"] = turn
                npc[field] = copy.deepcopy(cleaned)
            elif field in entry:
                npc[field] = copy.deepcopy(entry[field])
                notes.append(f"npc_ledger:restored_{field}:{entry.get('name')}")
    if len(rows) > MAX_LEDGER_ROWS:
        keep = sorted(rows.items(), key=lambda kv: int(kv[1].get("last_turn") or 0), reverse=True)
        ledger["rows"] = dict(keep[:MAX_LEDGER_ROWS])
    return ledger, notes


def _reconcile_inventory(entry: Dict[str, Any], npc: Dict[str, Any], emitted: Dict[str, Any], turn: int) -> None:
    held = _clean_items(entry.get("inventory")) if "inventory" in entry else None
    known = _known(entry) if held is not None else []
    if "inventory" in emitted:
        said = _clean_items(emitted["inventory"])
        if held is None:
            held, known = list(said), list(said)          # on stage, so the player saw it
        else:
            for item in said:                                # the narrator put it on stage
                if not _has(held, item):
                    held.append(item)
                if not _has(known, item):
                    known.append(item)
            for item in list(known):                         # the narrator may drop what the player already knows
                if not _has(said, item):
                    held = [h for h in held if h.lower() != item.lower()]
                    known = [k for k in known if k.lower() != item.lower()]
        entry["last_turn"] = turn
    elif "inventory" in npc:
        engine = _clean_items(npc["inventory"])              # an engine change (order handover) or a carried value
        if held is None:
            held, known = engine, []
        elif engine != held:
            held = engine
            known = [k for k in known if _has(held, k)]
            entry["last_turn"] = turn
    if held is not None:
        entry["inventory"] = held[:MAX_ITEMS]
        entry["known"] = [k for k in known if _has(entry["inventory"], k)]


def inventory_of(ledger: Optional[Dict[str, Any]], row: Any) -> Optional[List[str]]:
    """What the NPC truly carries, or None when it was never recorded. Engine use only."""
    entry = _rows(ledger or {}).get(key_for(row)) if isinstance(ledger, dict) else None
    if entry is None or "inventory" not in entry:
        return None
    return list(entry["inventory"])


def known_inventory_of(ledger: Optional[Dict[str, Any]], row: Any) -> List[str]:
    """What the player is allowed to know this NPC carries."""
    entry = _rows(ledger or {}).get(key_for(row)) if isinstance(ledger, dict) else None
    return _known(entry) if entry else []


def set_inventory(ledger: Dict[str, Any], rolling: Optional[Dict[str, Any]], row: Any,
                  items: List[str], *, turn: int) -> None:
    """Engine-side change: update the ledger and the visible cast row together."""
    key = key_for(row)
    entry = _rows(ledger).setdefault(key, {"name": _name(row), "known": []})
    entry["inventory"] = _clean_items(items)
    entry["known"] = [k for k in _clean_items(entry.get("known")) if _has(entry["inventory"], k)]
    entry["last_turn"] = turn
    for npc in (rolling or {}).get("npcs") or []:
        if key_for(npc) == key:
            npc["inventory"] = list(entry["inventory"])


def _reveal(ledger: Dict[str, Any], row: Any, items: List[str], turn: int) -> None:
    entry = _rows(ledger).setdefault(key_for(row), {"name": _name(row)})
    known = _clean_items(entry.get("known"))
    for item in items:
        if not _has(known, item):
            known.append(item)
    entry["known"] = known
    entry["last_turn"] = turn


# ---- what the narrator is shown --------------------------------------------------------------


def narrator_view(rolling: Optional[Dict[str, Any]], ledger: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """A copy of the cast for the narrator: real inventories replaced by what the player knows."""
    if not isinstance(rolling, dict):
        return rolling
    view = copy.deepcopy(rolling)
    for npc in view.get("npcs") or []:
        if not isinstance(npc, dict):
            continue
        known = known_inventory_of(ledger, npc)
        npc.pop("inventory", None)
        if known:
            npc["inventory_known"] = known
    return view


_ASK = re.compile(r"\b(ask|asks|asking|enquire|inquire|question)\b|\?", re.I)
_GENERAL = re.compile(
    r"\bwhat\b[^.?!]*\b(carry|carrying|carries|have|has|got|holding|bag|pockets?|pack|satchel|belongings|supplies)\b"
    r"|\b(carrying|have|has|got) anything\b|\bwhat'?s in (her|his|their)\b",
    re.I,
)
_SPECIFIC = re.compile(r"\b(have|has|got|carry|carrying|spare)\b", re.I)
_GIVE = re.compile(
    r"\b(give|hand|lend|pass|spare)\b[^.]*\bme\b|\blet me (have|borrow|use|take)\b|\bcan i (have|borrow|take)\b", re.I
)


def _named(rolling: Dict[str, Any], text: str) -> List[Dict[str, Any]]:
    low = text.lower()
    hits = []
    for row in ce.present_npcs(rolling):
        name = (ce.npc_name(row) or "").lower()
        parts = [name] + [p for p in name.split() if len(p) > 2]
        if name and any(re.search(r"\b" + re.escape(p) + r"\b", low) for p in parts):
            hits.append(row)
    return hits


def _mentioned(items: List[str], text: str) -> List[str]:
    words = set(re.findall(r"[a-z]+", text.lower()))
    out = []
    for item in items:
        tokens = re.findall(r"[a-z]+", item.lower())
        if item.lower() in text.lower() or (tokens and len(tokens[-1]) > 2 and tokens[-1] in words):
            out.append(item)
    return out


def _discloses(rolling: Dict[str, Any], row: Dict[str, Any]) -> bool:
    if row.get("refuses_orders") or oe._n(row.get("stance")) in oe._HOSTILE:
        return False
    trust = oe._trust(rolling, row)
    if trust is None:
        return oe._n(row.get("stance")) in _FRIENDLY
    return trust >= DISCLOSE_MIN_TRUST


_REFUSE_TELL = ("{who} does not want to say what they carry and gives the player nothing about it. "
                "Show this in character. Do not name or hint at any item.")


def inquire(ledger: Dict[str, Any], rolling: Dict[str, Any], action_text: str, *, turn: int) -> Tuple[Dict[str, Any], str]:
    """Decide a direct question or a request for an item. Returns (ledger, directive line or '')."""
    text = action_text or ""
    hits = _named(rolling, text)
    if len(hits) != 1:
        return ledger, ""
    row = hits[0]
    who = ce.npc_name(row)
    held = inventory_of(ledger, row)
    if held is None:
        return ledger, ""
    willing = _discloses(rolling, row)
    asked = bool(_ASK.search(text))

    if _GIVE.search(text):
        wanted = _mentioned(held, text)
        if not wanted:
            return ledger, ""
        if not willing:
            return ledger, (f"{who} does not trust the player enough to hand over what they carry. "
                            "Show the refusal in character. Nothing changes hands and no item is named.")
        item = wanted[0]
        set_inventory(ledger, rolling, row, [h for h in held if h != item], turn=turn)
        return ledger, f"{who} hands the player their {item}. The player now carries it: narrate the handover and list it under Carried."

    if asked and _GENERAL.search(text):
        if not willing:
            return ledger, _REFUSE_TELL.format(who=who)
        _reveal(ledger, row, held, turn)
        listing = ", ".join(held) if held else "nothing"
        return ledger, f"{who} tells the player what they are carrying: {listing}. Narrate them saying so. The player now knows this."

    if asked and _SPECIFIC.search(text):
        if not willing:
            return ledger, _REFUSE_TELL.format(who=who)
        found = _mentioned(held, text)
        if found:
            _reveal(ledger, row, found, turn)
            return ledger, f"{who} confirms they have: {', '.join(found)}. Narrate it. The player now knows this."
        return ledger, f"{who} does not have what the player asked about. Narrate an honest no. Do not invent that they carry anything else."
    return ledger, ""


def standing_rule(rolling: Optional[Dict[str, Any]]) -> str:
    """One line for the narrator whenever people are present."""
    if not ce.present_npcs(rolling or {}):
        return ""
    return (
        f"{DIRECTIVE_MARKER}\nCast rows list only `inventory_known`: items the player has seen or been given. "
        "What anyone else carries beyond that is not yours to state or hint at, and nobody volunteers it. "
        "If the player asks a person directly, the engine decides the answer and tells you below."
    )


def narrator_context(rolling: Optional[Dict[str, Any]], directive: str) -> str:
    parts = [standing_rule(rolling)]
    if directive:
        parts.append(f"{DIRECTIVE_MARKER} RESULT\n- {directive}")
    return "\n\n".join(p for p in parts if p)
