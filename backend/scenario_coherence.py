"""
Scenario + creation coherence guards — model-independent.

Stage 1/2A: selected-scenario openings and early-turn choices.
Stage 2B: Guided/Advanced creation-contract enforcement across openings,
choices, and later turns.

Narrative remains non-authority; structured session state + creation/scenario
contract + pressure graph are authority. Recent prose cannot replace hard setup.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import creation_contract

# Capitalized tokens that look like proper names (not start-of-sentence noise).
_PROPER_RE = re.compile(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)\b")
_STOP_NAMES = frozenset(
    {
        "The",
        "This",
        "That",
        "Then",
        "When",
        "Where",
        "What",
        "With",
        "From",
        "Into",
        "Your",
        "You",
        "And",
        "But",
        "For",
        "Not",
        "Are",
        "Was",
        "Were",
        "Have",
        "Has",
        "Had",
        "Will",
        "Would",
        "Could",
        "Should",
        "May",
        "Might",
        "Can",
        "Sit",
        "Stay",
        "Leave",
        "Search",
        "Wait",
        "Look",
        "Take",
        "Keep",
        "Use",
        "Ask",
        "Tell",
        "Show",
        "Hide",
        "Open",
        "Close",
        "Climb",
        "Track",
        "Salvage",
        "Abandon",
        "Signal",
        "Bind",
        "Stand",
        "Step",
        "Point",
        "Admit",
        "Fold",
        "Shout",
        "Rain",
        "Storm",
        "Night",
        "Morning",
        "Door",
        "Roof",
        "Beam",
        "Mud",
        "Water",
        "Wood",
        "Metal",
        "Site",
        "Mainland",
        "Substation",
        "Radio",
        "Jeep",
        "Fence",
        "Tracks",
        "Ridge",
        "Uphill",
        "Downhill",
        "North",
        "South",
        "East",
        "West",
    }
)

# Phrases that signal off-frame debt/property plots for prehistoric-survival
# openings when the scenario forbids them.
_PROPERTY_DEBT_RE = re.compile(
    r"\b(debt|creditor|foreclosure|lease\s+agreement|building\s+inspection|"
    r"inspector|foreman|mortgage|title\s+deed|property\s+claim|"
    r"fraudulent\s+(?:debt|contract)|renegotiate\s+terms)\b",
    re.IGNORECASE,
)

# Stage 2B — exclusion / groundedness pattern packs (structured contract driven).
_FIREARM_RE = re.compile(
    r"\b(firearm|firearms|handgun|pistol|rifle|shotgun|revolver|machine\s*gun|"
    r"assault\s*rifle|bullets?|gunfire|gunshot)\b",
    re.IGNORECASE,
)
_MAGIC_RE = re.compile(
    r"\b(spellcraft|spellcasting|wizardry|sorcery|enchantment|mana\b|arcane\s+blast|"
    r"cast\s+a\s+spell|magic\s+missile|fireball\s+spell)\b",
    re.IGNORECASE,
)
# Broader magic when exclusion text says "magic"
_MAGIC_BROAD_RE = re.compile(
    r"\b(magic|magical|wizard|witch|sorcerer|enchanted|spell)\b",
    re.IGNORECASE,
)
_SUPERNATURAL_RE = re.compile(
    r"\b(ghost|spectre|specter|demon|vampire|werewolf|undead|haunting|"
    r"poltergeist|necromancy|possession\s+by|summoned\s+spirit)\b",
    re.IGNORECASE,
)
_OMNISCIENT_CHOICE_RE = re.compile(
    r"\b(secretly\s+knows?|hidden\s+motive|you\s+know\s+that\s+.+\s+is\s+lying|"
    r"telepathically|omniscient|read\s+their\s+mind|knows?\s+the\s+truth\s+about)\b",
    re.IGNORECASE,
)
_ROLE_SWAP_PAIRS = (
    (("scholar", "academic", "researcher", "archivist"), ("soldier", "guard", "trooper", "marine")),
    (("survivor",), ("official", "inspector", "bureaucrat", "mayor", "governor")),
    (("investigator", "detective"), ("owner", "landlord", "property owner", "creditor")),
)
_UNSUPPORTED_TECH_BY_TOKEN = {
    "firearm": _FIREARM_RE,
    "firearms": _FIREARM_RE,
    "gun": _FIREARM_RE,
    "guns": _FIREARM_RE,
    "magic": _MAGIC_BROAD_RE,
    "magical": _MAGIC_BROAD_RE,
    "supernatural": _SUPERNATURAL_RE,
    "ghost": _SUPERNATURAL_RE,
    "vampire": _SUPERNATURAL_RE,
}


def _names_in_text(text: str) -> Set[str]:
    found: Set[str] = set()
    for match in _PROPER_RE.finditer(text or ""):
        name = match.group(1).strip()
        if name in _STOP_NAMES:
            continue
        # Single common adjectives / roles
        if name.lower() in {
            "inside",
            "outside",
            "interior",
            "exterior",
            "something",
            "someone",
            "nothing",
            "everything",
        }:
            continue
        found.add(name)
    return found


def _npc_names_from_state(rolling: Optional[Mapping[str, Any]]) -> Set[str]:
    names: Set[str] = set()
    if not isinstance(rolling, Mapping):
        return names
    for row in rolling.get("npcs") or []:
        if isinstance(row, Mapping) and row.get("name"):
            names.add(str(row["name"]).strip())
    for row in rolling.get("npc_memory") or []:
        if isinstance(row, Mapping) and row.get("name"):
            names.add(str(row["name"]).strip())
    return {n for n in names if n}


def _scenario_npc_names(scenario: Optional[Mapping[str, Any]]) -> Set[str]:
    names: Set[str] = set()
    if not isinstance(scenario, Mapping):
        return names
    for row in scenario.get("key_npcs") or []:
        if isinstance(row, Mapping) and row.get("name"):
            # Only the personal name token (before parenthetical / em-dash role)
            raw = str(row["name"]).split("—")[0].split("(")[0].strip()
            if raw:
                names.add(raw)
                # Also first token for "Dr. Aris Kemal"
                parts = raw.replace(".", " ").split()
                if parts:
                    names.add(parts[-1])  # surname
                    if len(parts) >= 2:
                        names.add(" ".join(parts[-2:]))
    return names


def known_person_names(
    *,
    narrative: str,
    prior_rolling: Optional[Mapping[str, Any]],
    scenario: Optional[Mapping[str, Any]],
) -> Set[str]:
    """Names the player may legitimately act on this turn."""
    known = _names_in_text(narrative)
    known |= _npc_names_from_state(prior_rolling)
    known |= _scenario_npc_names(scenario)
    # Expand first/last parts of multi-word names
    expanded = set(known)
    for name in list(known):
        for part in name.split():
            if len(part) > 2 and part[0].isupper():
                expanded.add(part)
    return expanded


def _names_in_choice_text(text: str) -> Set[str]:
    """Proper names inside a choice, ignoring the leading imperative verb."""
    words = (text or "").strip().split()
    if not words:
        return set()
    # "Leave the shelter and intercept Harwood" — skip "Leave"
    rest = " ".join(words[1:])
    return _names_in_text(rest)


def validate_choices_named_entities(
    choices: Sequence[Mapping[str, Any]],
    *,
    narrative: str,
    prior_rolling: Optional[Mapping[str, Any]] = None,
    scenario: Optional[Mapping[str, Any]] = None,
) -> Tuple[bool, str]:
    """Choices may not introduce proper names absent from narrative / known state."""
    known = known_person_names(
        narrative=narrative,
        prior_rolling=prior_rolling,
        scenario=scenario,
    )
    for choice in choices or []:
        text = str(choice.get("text") or "")
        for name in _names_in_choice_text(text):
            if name in known:
                continue
            # Allow if any known name contains this token or vice versa
            if any(name in k or k in name for k in known):
                continue
            return (
                False,
                f"choice introduces unknown person '{name}' before narrative/state introduction",
            )
    return True, ""


def validate_choice_length_and_intent(
    choices: Sequence[Mapping[str, Any]],
    *,
    max_words: int = 28,
) -> Tuple[bool, str]:
    """Soft structural guard: choices should stay scannable and single-intent."""
    for choice in choices or []:
        text = str(choice.get("text") or "").strip()
        words = text.split()
        if len(words) > max_words:
            return False, f"choice too long ({len(words)} words; max {max_words})"
        # Compound multi-strategy markers
        if text.count(" — ") + text.count(" - ") >= 2 and len(words) > 18:
            return False, "choice packs multiple strategies; use one intention"
    return True, ""


def validate_opening_named_before_choices(
    narrative: str,
    choices: Sequence[Mapping[str, Any]],
) -> Tuple[bool, str]:
    """On openings, every choice proper name must appear in this turn's narrative."""
    narr_names = _names_in_text(narrative)
    for choice in choices or []:
        for name in _names_in_choice_text(str(choice.get("text") or "")):
            if name not in narr_names and not any(name in n or n in name for n in narr_names):
                return (
                    False,
                    f"opening choice references '{name}' before narrative introduction",
                )
    return True, ""


def validate_scenario_frame_coherence(
    *,
    scenario: Optional[Mapping[str, Any]],
    narrative: str,
    choices: Sequence[Mapping[str, Any]],
    is_opening: bool,
) -> Tuple[bool, str]:
    """Reject openings dominated by forbidden frames for the selected scenario."""
    if not scenario or not is_opening:
        return True, ""
    frame = scenario.get("world_frame") if isinstance(scenario.get("world_frame"), dict) else {}
    forbidden = [str(x).lower() for x in (frame.get("forbidden_opening_frames") or [])]
    if not forbidden:
        return True, ""
    blob = (narrative or "") + "\n" + "\n".join(
        str(c.get("text") or "") for c in (choices or [])
    )
    # Property/debt frame check when forbidden
    if any("debt" in f or "property" in f or "paperwork" in f or "foreman" in f for f in forbidden):
        if _PROPERTY_DEBT_RE.search(blob):
            # Allow if scenario itself seeds debt (none of ours do for dino)
            seed = str(scenario.get("seed") or "") + str(scenario.get("starting_pressure") or "")
            if not _PROPERTY_DEBT_RE.search(seed):
                return (
                    False,
                    "opening invents debt/property/inspection frame incompatible with scenario world_frame",
                )
    return True, ""


def validate_scenario_opening_context(
    *,
    scenario: Optional[Mapping[str, Any]],
    narrative: str,
    paragraphs: Sequence[str],
) -> Tuple[bool, str]:
    """Opening must establish location + pressure-ish context when scenario is set."""
    if not scenario:
        return True, ""
    text = (narrative or "").strip()
    if len(text) < 80:
        return False, "opening narrative too thin to establish scenario context"
    # Location: mention a content word from starting_location
    loc = str(scenario.get("starting_location") or "")
    loc_tokens = [
        t.lower()
        for t in re.findall(r"[A-Za-z]{4,}", loc)
        if t.lower()
        not in {"with", "from", "that", "this", "your", "have", "been", "into", "across"}
    ][:12]
    lowered = text.lower()
    if loc_tokens and not any(tok in lowered for tok in loc_tokens[:8]):
        # Also accept title words (Substation, Site, etc.)
        title_tokens = re.findall(r"[A-Za-z]{4,}", str(scenario.get("title") or ""))
        if not any(t.lower() in lowered for t in title_tokens):
            return False, "opening does not establish scenario location"
    # Scenario pressure tokens
    pressure = str(scenario.get("starting_pressure") or "")
    press_tokens = [
        t.lower()
        for t in re.findall(r"[A-Za-z]{5,}", pressure)
        if t.lower() not in {"cannot", "their", "about", "minutes", "since"}
    ][:10]
    # At least one scenario key NPC first name or pressure/survival token
    npc_hit = False
    for row in scenario.get("key_npcs") or []:
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or "")
        for part in re.findall(r"[A-Za-z]{3,}", name):
            if part.lower() in {"the", "site", "radio"}:
                continue
            if part.lower() in lowered or part in text:
                npc_hit = True
                break
    survival_tokens = (
        "track",
        "predator",
        "theropod",
        "fence",
        "breach",
        "rifle",
        "containment",
        "rain",
        "wound",
        "bleeding",
        "radio",
        "jeep",
        "substation",
        "paddock",
        "dinosaur",
    )
    survival_hit = any(tok in lowered for tok in survival_tokens)
    pressure_hit = any(tok in lowered for tok in press_tokens[:6]) if press_tokens else False
    if not (npc_hit or survival_hit or pressure_hit):
        return False, "opening lacks scenario pressure/NPC/survival anchors"
    if len(paragraphs or []) < 1:
        return False, "opening missing paragraphs"
    return True, ""


def _combined_text(narrative: str, choices: Sequence[Mapping[str, Any]], rolling: Optional[Mapping[str, Any]] = None) -> str:
    parts = [narrative or ""]
    for c in choices or []:
        parts.append(str(c.get("text") or ""))
    if isinstance(rolling, Mapping):
        parts.append(str(rolling.get("scene") or ""))
        parts.append(str(rolling.get("character") or ""))
        for key in ("objectives", "unresolved", "active_pressures"):
            val = rolling.get(key)
            if isinstance(val, list):
                parts.extend(str(x) for x in val[:12])
            elif val:
                parts.append(str(val))
    return "\n".join(parts)


def _exclusion_tokens(contract: Mapping[str, Any]) -> List[str]:
    raw = " ".join(
        [
            str(contract.get("excluded_elements") or ""),
            str((contract.get("world_frame") or {}).get("excluded_elements") or "")
            if isinstance(contract.get("world_frame"), dict)
            else "",
        ]
    ).lower()
    tokens = re.findall(r"[a-z][a-z\-]{2,}", raw)
    return tokens[:24]


def validate_creation_exclusions_and_groundedness(
    *,
    contract: Mapping[str, Any],
    narrative: str,
    choices: Sequence[Mapping[str, Any]],
    rolling: Optional[Mapping[str, Any]] = None,
) -> Tuple[bool, str]:
    """Block firearms/magic/supernatural/bureaucracy when contract forbids them."""
    blob = _combined_text(narrative, choices, rolling)
    tokens = set(_exclusion_tokens(contract))
    grounded = str(contract.get("groundedness") or "").lower()
    frame = contract.get("world_frame") if isinstance(contract.get("world_frame"), dict) else {}
    tech = str(frame.get("technology") or "").lower()
    genre = str(contract.get("genre") or "").lower()

    # Explicit exclusion text.
    if tokens & {"firearm", "firearms", "gun", "guns", "rifle", "pistol"} or "firearm" in " ".join(tokens):
        if _FIREARM_RE.search(blob):
            return False, "output introduces firearms excluded by creation contract"
    if tokens & {"magic", "magical", "wizardry", "sorcery"} or "magic" in " ".join(tokens):
        if _MAGIC_BROAD_RE.search(blob):
            return False, "output introduces magic excluded by creation contract"
    if tokens & {"supernatural", "ghost", "undead", "vampire", "demon"}:
        if _SUPERNATURAL_RE.search(blob):
            return False, "output introduces supernatural elements excluded by creation contract"

    # Realistic groundedness: no supernatural causes.
    if grounded in ("realistic",):
        if _SUPERNATURAL_RE.search(blob) and "supernatural" not in str(contract.get("required_elements") or "").lower():
            return False, "realistic groundedness forbids supernatural causes"

    # Prehistoric / lithic tech: no firearms or modern bureaucracy.
    if "lithic" in tech or genre in ("prehistoric survival", "prehistoric"):
        if _FIREARM_RE.search(blob):
            return False, "prehistoric world frame forbids firearms"
        if _PROPERTY_DEBT_RE.search(blob):
            return False, "prehistoric world frame forbids modern debt/property bureaucracy"

    # General science fiction must not silently become cyberpunk debt/property opening.
    if genre in ("science fiction", "science-fiction", "sci-fi") and "cyberpunk" not in genre:
        pressures = " ".join(str(p) for p in (contract.get("active_pressures") or [])).lower()
        if _PROPERTY_DEBT_RE.search(blob) and "debt" not in pressures and "authority" not in pressures:
            # Allow mild "contract" only if not property repossession frame
            if re.search(r"\b(foreclosure|mortgage|creditor|building\s+inspection|title\s+deed)\b", blob, re.I):
                return False, "science-fiction opening invents debt/property frame outside world frame"

    return True, ""


def validate_creation_opening_location_and_role(
    *,
    contract: Mapping[str, Any],
    narrative: str,
    rolling: Optional[Mapping[str, Any]],
    is_opening: bool,
) -> Tuple[bool, str]:
    """Opening must respect authoritative starting location and role."""
    if not is_opening:
        return True, ""
    text = (narrative or "").lower()
    scene = str((rolling or {}).get("scene") or "").lower() if rolling else ""
    character = str((rolling or {}).get("character") or "").lower() if rolling else ""
    blob = f"{text}\n{scene}\n{character}"

    location = str(contract.get("starting_location") or "").strip()
    if location:
        loc_tokens = [
            t
            for t in re.findall(r"[a-z]{4,}", location.lower())
            if t not in {"with", "from", "that", "this", "your", "have", "been", "into", "group"}
        ][:8]
        # Reject clear replacement with a wildly different stock location class.
        alien_locations = (
            "orbital salvage",
            "space station",
            "corporate tower",
            "stock exchange",
            "suburban mortgage",
        )
        if loc_tokens and not any(tok in blob for tok in loc_tokens):
            if any(a in blob for a in alien_locations):
                return False, "opening replaces authoritative starting location"

    role = str(contract.get("role") or "").lower()
    if role:
        # Casual role swap pairs — only on opening when role tokens are clear.
        for keepers, invaders in _ROLE_SWAP_PAIRS:
            if any(k in role for k in keepers):
                if any(inv in blob for inv in invaders) and not any(k in blob for k in keepers):
                    return False, f"opening replaces authoritative role ({role}) without cause"
    return True, ""


def validate_creation_role_continuity(
    *,
    contract: Mapping[str, Any],
    narrative: str,
    rolling: Optional[Mapping[str, Any]],
    prior_rolling: Optional[Mapping[str, Any]],
    is_opening: bool,
) -> Tuple[bool, str]:
    """Later turns: block casual role replacement without authoritative transition."""
    if is_opening:
        return True, ""
    role = str(contract.get("role") or "").lower()
    if not role:
        return True, ""
    character = str((rolling or {}).get("character") or "").lower() if rolling else ""
    prior_char = str((prior_rolling or {}).get("character") or "").lower() if prior_rolling else ""
    text = f"{narrative or ''}\n{character}".lower()

    for keepers, invaders in _ROLE_SWAP_PAIRS:
        if not any(k in role for k in keepers):
            continue
        # Invader appears and keeper vanished from character line after having been present.
        if any(inv in text for inv in invaders):
            if prior_char and any(k in prior_char for k in keepers) and not any(k in character for k in keepers):
                # Allow if objectives/unresolved mention promotion/commission/oath event
                evolution = " ".join(
                    str(x)
                    for x in (
                        list((rolling or {}).get("objectives") or [])
                        + list((rolling or {}).get("unresolved") or [])
                        + list((rolling or {}).get("recent_beats") or [])
                    )
                ).lower()
                if not re.search(r"\b(commission|promoted|enlisted|sworn|appointed|forced\s+into)\b", evolution):
                    return False, "role changed without authoritative event"
    return True, ""


def validate_creation_relationship_safety(
    *,
    contract: Mapping[str, Any],
    narrative: str,
    choices: Sequence[Mapping[str, Any]],
    rolling: Optional[Mapping[str, Any]],
) -> Tuple[bool, str]:
    """Nobody invents no person; archetypes stay unnamed; no parent/child promotion."""
    who = str(contract.get("relationship_archetype") or "").lower()
    threads = list((rolling or {}).get("relationship_threads") or []) if rolling else []
    blob = _combined_text(narrative, choices, rolling)

    if who in ("", "nobody"):
        # who_matters_floor must not exist; no invented "your child/partner X" from nothing
        for t in threads:
            if not isinstance(t, dict):
                continue
            if t.get("name") == "who_matters_floor":
                return False, "nobody relationship must not seed a who_matters floor"
            if t.get("named") is True and t.get("archetype"):
                return False, "relationship archetype must not invent a named person"
        # Choice inventing "your child" / "your partner Marlene" when nobody
        if re.search(r"\b(your\s+child|your\s+partner\s+[A-Z]|find\s+Marlene|protect\s+Greg)\b", blob):
            return False, "nobody setup invents a named relationship person"

    # Archetype must not become parent/child cast labels in threads
    for t in threads:
        if not isinstance(t, dict):
            continue
        arch = str(t.get("archetype") or "").lower()
        name = str(t.get("name") or "").lower()
        if arch == "family-member" and ("parent" in name or name == "parent"):
            return False, "family-member must not become parent"
        if arch == "someone-depending" and ("child" in name and "who_matters" not in name):
            return False, "someone-depending must not become child"
        if arch and t.get("named") is True and not t.get("introduced"):
            return False, "named relationship requires authoritative introduction"

    # Parent/child promotion in prose when only family-member archetype
    if who == "family-member" and re.search(r"\b(your\s+father|your\s+mother|your\s+parent)\b", blob, re.I):
        # Allow only if an NPC with that relationship was already introduced in prior state
        npcs = " ".join(
            str(n.get("name") or "") + str(n.get("role") or "")
            for n in ((rolling or {}).get("npcs") or [])
            if isinstance(n, dict)
        ).lower()
        if "father" not in npcs and "mother" not in npcs and "parent" not in npcs:
            return False, "family-member archetype must not invent a parent without introduction"

    return True, ""


def validate_creation_knowledge_bounds(
    *,
    contract: Mapping[str, Any],
    choices: Sequence[Mapping[str, Any]],
    narrative: str,
) -> Tuple[bool, str]:
    """Knowledge scope bounds motive visibility and omniscient choice text."""
    scope = str(contract.get("knowledge_scope") or "").lower()
    blob = "\n".join(str(c.get("text") or "") for c in (choices or []))
    narr = narrative or ""

    if scope in ("very_little", "very little"):
        if _OMNISCIENT_CHOICE_RE.search(blob) or _OMNISCIENT_CHOICE_RE.search(narr):
            return False, "very_little knowledge forbids omniscient player knowledge in choices"
        # Hidden motive / secret faction as familiar
        if re.search(r"\b(confront\s+the\s+hidden\s+faction|expose\s+the\s+conspiracy\s+you\s+already\s+know)\b", blob, re.I):
            return False, "choices assume hidden knowledge outside knowledge scope"

    # Secret registry must never appear in narration/choices (engine-only).
    if "secret_registry" in blob.lower() or "secret_registry" in narr.lower():
        return False, "secret state leaked into player-visible output"

    return True, ""


def validate_choice_grounding_objects_and_tech(
    *,
    contract: Mapping[str, Any],
    choices: Sequence[Mapping[str, Any]],
    narrative: str,
    prior_rolling: Optional[Mapping[str, Any]],
    scenario: Optional[Mapping[str, Any]] = None,
) -> Tuple[bool, str]:
    """Choices may not invent absent objects or excluded technology."""
    known_objects: Set[str] = set()
    for source in (prior_rolling,):
        if not isinstance(source, Mapping):
            continue
        for key in ("inventory_objects", "object_locations"):
            for row in source.get(key) or []:
                if isinstance(row, dict):
                    name = str(row.get("object") or row.get("item") or "").strip().lower()
                    if name:
                        known_objects.add(name)
                        for tok in re.findall(r"[a-z]{3,}", name):
                            known_objects.add(tok)
        for row in source.get("npcs") or []:
            if isinstance(row, dict) and row.get("name"):
                known_objects.add(str(row["name"]).lower())

    narr_lower = (narrative or "").lower()
    for tok in re.findall(r"[a-z]{3,}", narr_lower):
        known_objects.add(tok)

    # Absent-object patterns: "take the X" when X never appeared
    for choice in choices or []:
        text = str(choice.get("text") or "")
        m = re.search(
            r"\b(?:take|grab|use|draw|wield|load|fire)\s+(?:the\s+)?([a-z][a-z\- ]{2,30})\b",
            text,
            re.I,
        )
        if m:
            obj = m.group(1).strip().lower()
            obj_core = re.sub(r"\b(the|a|an|my|your)\b", "", obj).strip()
            tokens = [t for t in re.findall(r"[a-z]{3,}", obj_core)]
            # Skip abstract actions
            if tokens and tokens[0] in {"chance", "time", "moment", "lead", "initiative", "cover"}:
                continue
            if tokens and not any(t in known_objects or t in narr_lower for t in tokens[:3]):
                # Strong inventions
                if any(t in {"plasma", "railgun", "excalibur", "nuke", "lightsaber"} for t in tokens):
                    return False, f"choice invents unsupported object '{obj_core}'"

    # Tech exclusions via contract
    excl = " ".join(_exclusion_tokens(contract))
    blob = "\n".join(str(c.get("text") or "") for c in (choices or []))
    for token, pattern in _UNSUPPORTED_TECH_BY_TOKEN.items():
        if token in excl or token in str(contract.get("excluded_elements") or "").lower():
            if pattern.search(blob):
                return False, f"choice uses excluded technology/element ({token})"

    frame = contract.get("world_frame") if isinstance(contract.get("world_frame"), dict) else {}
    tech = str(frame.get("technology") or "").lower()
    if "lithic" in tech and _FIREARM_RE.search(blob):
        return False, "choice uses firearms outside world-permitted technology"

    return True, ""


def validate_seeded_pressure_continuity(
    *,
    session: Mapping[str, Any],
    prior_rolling: Optional[Mapping[str, Any]],
    rolling: Optional[Mapping[str, Any]],
    is_opening: bool,
) -> Tuple[bool, str]:
    """Custom_setup pressures may not vanish without resolution receipt/status."""
    if is_opening:
        return True, ""
    replay = session.get("replayability_state")
    if not isinstance(replay, Mapping):
        # Fall back to contract labels still projected
        labels = creation_contract.active_seeded_pressure_labels(session)
        if not labels:
            return True, ""
        # Without graph, require simulation_hooks / world_instability still mention them
        hooks = " ".join(str(h) for h in ((prior_rolling or {}).get("simulation_hooks") or [])).lower()
        inst = " ".join(str(h) for h in ((prior_rolling or {}).get("world_instability") or [])).lower()
        blob = hooks + " " + inst
        for lab in labels:
            token = str(lab).lower().split(":")[-1].strip()
            if token and token not in blob and token not in " ".join(
                str(h) for h in ((rolling or {}).get("simulation_hooks") or [])
            ).lower():
                # Soft: creation directive still carries them; only fail hard if model
                # actively claims pressure never existed
                pass
        return True, ""

    graph = replay.get("pressure_graph")
    if not isinstance(graph, Mapping):
        return True, ""
    nodes = graph.get("nodes") or []
    if not isinstance(nodes, list):
        return True, ""

    for n in nodes:
        if not isinstance(n, dict):
            continue
        if str(n.get("origin_type") or "") != "custom_setup":
            continue
        status = str(n.get("status") or "active").lower()
        # Active/reduced must remain non-empty id
        if status in ("active", "reduced"):
            if not n.get("id"):
                return False, "seeded pressure lost identity without resolution"
        # "disappeared" = missing from nodes entirely is handled by engine ownership;
        # detect model writing resolved without engine receipt: not applicable here.
    return True, ""


def validate_creation_hidden_obligation(
    *,
    contract: Mapping[str, Any],
    choices: Sequence[Mapping[str, Any]],
    narrative: str,
    is_opening: bool,
) -> Tuple[bool, str]:
    """Block invented hidden obligations (contracts, debts) outside frame."""
    blob = _combined_text(narrative, choices)
    genre = str(contract.get("genre") or "").lower()
    pressures = " ".join(str(p) for p in (contract.get("active_pressures") or [])).lower()
    if genre in ("science fiction", "prehistoric survival", "horror", "fantasy") or (
        str(contract.get("groundedness") or "") == "realistic"
        and "debt" not in pressures
    ):
        if is_opening and _PROPERTY_DEBT_RE.search(blob):
            if "debt" not in pressures and "authority" not in pressures:
                if re.search(
                    r"\b(foreclosure|mortgage|building\s+inspection|title\s+deed|"
                    r"fraudulent\s+debt|creditor)\b",
                    blob,
                    re.I,
                ):
                    return False, "invented hidden obligation/debt outside creation frame"
    return True, ""


def run_creation_contract_checks(
    *,
    parsed: Any,
    session: Mapping[str, Any],
    prior_rolling: Optional[Mapping[str, Any]],
    is_opening: bool,
) -> Tuple[bool, str]:
    """Stage 2B aggregate for Guided/Advanced custom_world_setup sessions."""
    if not isinstance(session, Mapping):
        return True, ""
    if session.get("scenario_id") and not session.get("custom_world_setup"):
        return True, ""  # Quick Start scenario path — scenario_coherence handles it
    if not session.get("custom_world_setup"):
        return True, ""

    contract = creation_contract.build_creation_contract(session)
    if not contract:
        return True, ""

    narrative = str(getattr(parsed, "narrative", "") or "")
    choices = list(getattr(parsed, "choices", None) or [])
    rolling = getattr(parsed, "rolling_state", None)
    if not isinstance(rolling, Mapping):
        rolling = None

    checks = (
        validate_creation_opening_location_and_role(
            contract=contract, narrative=narrative, rolling=rolling, is_opening=is_opening
        ),
        validate_creation_role_continuity(
            contract=contract,
            narrative=narrative,
            rolling=rolling,
            prior_rolling=prior_rolling,
            is_opening=is_opening,
        ),
        validate_creation_exclusions_and_groundedness(
            contract=contract, narrative=narrative, choices=choices, rolling=rolling
        ),
        validate_creation_relationship_safety(
            contract=contract, narrative=narrative, choices=choices, rolling=rolling
        ),
        validate_creation_knowledge_bounds(
            contract=contract, choices=choices, narrative=narrative
        ),
        validate_choice_grounding_objects_and_tech(
            contract=contract,
            choices=choices,
            narrative=narrative,
            prior_rolling=prior_rolling,
        ),
        validate_seeded_pressure_continuity(
            session=session,
            prior_rolling=prior_rolling,
            rolling=rolling,
            is_opening=is_opening,
        ),
        validate_creation_hidden_obligation(
            contract=contract,
            choices=choices,
            narrative=narrative,
            is_opening=is_opening,
        ),
    )
    for ok, reason in checks:
        if not ok:
            return False, reason
    return True, ""


def run_coherence_checks(
    *,
    parsed: Any,
    session: Mapping[str, Any],
    scenario: Optional[Mapping[str, Any]],
    prior_rolling: Optional[Mapping[str, Any]],
    is_opening: bool,
) -> Tuple[bool, str]:
    """Aggregate checks for format/full validation hooks."""
    narrative = str(getattr(parsed, "narrative", "") or "")
    paragraphs = list(getattr(parsed, "paragraphs", None) or [])
    choices = list(getattr(parsed, "choices", None) or [])

    if is_opening and scenario:
        ok, reason = validate_scenario_opening_context(
            scenario=scenario, narrative=narrative, paragraphs=paragraphs
        )
        if not ok:
            return False, reason
        ok, reason = validate_opening_named_before_choices(narrative, choices)
        if not ok:
            return False, reason
        ok, reason = validate_scenario_frame_coherence(
            scenario=scenario,
            narrative=narrative,
            choices=choices,
            is_opening=True,
        )
        if not ok:
            return False, reason

    ok, reason = validate_choices_named_entities(
        choices,
        narrative=narrative,
        prior_rolling=prior_rolling,
        scenario=scenario if is_opening else None,
    )
    if not ok:
        return False, reason

    ok, reason = validate_choice_length_and_intent(choices)
    if not ok:
        return False, reason

    # Stage 2B — creation contract enforcement (Guided/Advanced).
    ok, reason = run_creation_contract_checks(
        parsed=parsed,
        session=session,
        prior_rolling=prior_rolling,
        is_opening=is_opening,
    )
    if not ok:
        return False, reason

    return True, ""
