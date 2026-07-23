"""Creation contract projection — Stage 2A.

Derives a compact, typed creation contract from existing session fields
(genre/role/tone/difficulty/scenario_id/custom_world_setup/mature_content)
without inventing a second Mongo schema.

Field classes:
  hard_state            — authoritative session identity (genre, role, scenario_id)
  persistent_sim_input  — seeds simulation (pressures, location, stability, hooks)
  presentation_policy   — tone, difficulty, mature rendering
  unsupported           — worldPace, storyFocus, secret (excluded until full support)

State is truth: later turns re-project from session fields; setup must not
exist only as opening-prompt prose.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Closed catalogs / constants
# ---------------------------------------------------------------------------

DEAD_SETUP_KEYS = frozenset({"worldPace", "storyFocus"})
# Secret is engine-only when present; never projected into the contract surface.
ENGINE_ONLY_SETUP_KEYS = frozenset({"secret"})

# Top-level keys that map out of the custom bag (not duplicated in contract bag).
TOP_LEVEL_MAPPED_KEYS = frozenset({"worldGenre", "customGenre", "storyFeel"})

WHO_ARCHETYPES = frozenset(
    {
        "family-member",
        "friend",
        "partner",
        "mentor",
        "someone-depending",
        "someone-failed",
        "nobody",
    }
)

# Legacy catalog → current archetype. Never invent parent/child from family/dependant.
WHO_ALIASES = {
    "child": "someone-depending",
    "parent": "family-member",
    "family": "family-member",
    "dependant": "someone-depending",
    "dependent": "someone-depending",
    "no one yet": "nobody",
    "no-one": "nobody",
    "none": "nobody",
}

# Guided pressure closed values → pressure_graph kinds (existing kind groups).
PRESSURE_KIND_MAP = {
    "scarcity": "scarcity",
    "violence": "danger",
    "isolation": "social",
    "betrayal": "social",
    "illness": "injury_or_fatigue",
    "authority": "social",
    "unknown": "unresolved_thread",
}

LOCATION_LABELS = {
    "small_settlement": "small settlement",
    "crowded_city": "crowded city",
    "remote_wilderness": "remote wilderness",
    "isolated_location": "isolated location",
    "travelling_group": "travelling group",
}

CONDITION_STABILITY = {
    "stable": "high",
    "uneasy": "medium",
    "divided": "low",
    "collapsing": "low",
}

MAX_HOOK_LEN = 120
MAX_ELEMENTS_LEN = 320
MAX_PRESSURES = 3
MAX_LATER_TURN_LINES = 14

# Genre → minimal world_frame (non-scenario Guided/Advanced paths).
# Science fiction stays general — never forced to cyberpunk.
_GENRE_WORLD_FRAMES: Dict[str, Dict[str, Any]] = {
    "fantasy": {
        "era": "secondary_world",
        "setting": "fantasy_realm",
        "technology": "preindustrial_magic",
        "primary_pressures": ["oaths", "scarcity", "faction"],
    },
    "horror": {
        "era": "ambiguous_modern_or_timeless",
        "setting": "isolated_threat",
        "technology": "setting_native",
        "primary_pressures": ["isolation", "dread", "unknown"],
    },
    "science fiction": {
        "era": "near_or_far_future",
        "setting": "general_science_fiction",
        "technology": "advanced_but_not_prescribed",
        "primary_pressures": ["systems", "scarcity", "authority"],
        "forbidden_opening_frames": ["default_cyberpunk_neon_only"],
    },
    "post-apocalyptic": {
        "era": "after_collapse",
        "setting": "scarce_settlements",
        "technology": "salvage",
        "primary_pressures": ["scarcity", "violence", "trust"],
    },
    "detective": {
        "era": "modern_or_period_noir",
        "setting": "investigation_locale",
        "technology": "era_appropriate",
        "primary_pressures": ["secrecy", "violence", "authority"],
    },
    "mystery": {
        "era": "modern_or_period",
        "setting": "investigation_locale",
        "technology": "era_appropriate",
        "primary_pressures": ["secrecy", "social", "unknown"],
    },
    "modern": {
        "era": "contemporary",
        "setting": "grounded_present",
        "technology": "contemporary",
        "primary_pressures": ["social", "scarcity", "authority"],
    },
    "cyberpunk": {
        "era": "near_future",
        "setting": "corporate_urban",
        "technology": "cybernetic",
        "primary_pressures": ["debt", "surveillance", "corp"],
    },
    "prehistoric survival": {
        "era": "deep_prehistory",
        "setting": "lithic_band",
        "technology": "lithic_and_bone",
        "primary_pressures": ["predators", "weather", "scarcity"],
        "forbidden_opening_frames": [
            "research_facility",
            "firearms",
            "radio",
            "modern_debt",
        ],
    },
}


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------


def _short(value: Any, limit: int = MAX_HOOK_LEN) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _humanize(value: Any) -> str:
    text = _short(value, MAX_HOOK_LEN)
    if not text:
        return ""
    return text.replace("-", " ").replace("_", " ").strip()


def normalize_who_matters(value: Any) -> str:
    """Return a closed archetype slug. Unnamed; never parent/child promotion."""
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if raw in WHO_ARCHETYPES:
        return raw
    aliased = WHO_ALIASES.get(raw)
    if aliased:
        return aliased
    # Unknown free-text is not an archetype — refuse cast invention.
    return raw.replace(" ", "-")[:60]


def map_pressure_kind(pressure: str) -> str:
    key = str(pressure or "").strip().lower()
    return PRESSURE_KIND_MAP.get(key, "unresolved_thread")


def resolve_starting_location(setup: Mapping[str, Any]) -> str:
    if not isinstance(setup, dict):
        return ""
    if setup.get("startingLocation") == "custom_location":
        return _short(setup.get("customLocation"), 160)
    loc = setup.get("startingLocation") or setup.get("starting_location") or setup.get("location")
    if not loc:
        return ""
    key = str(loc).strip()
    return LOCATION_LABELS.get(key, _humanize(key) or key)


def resolve_starting_role(setup: Mapping[str, Any], session_role: Optional[str] = None) -> str:
    if session_role and str(session_role).strip():
        return _short(session_role, 160)
    if not isinstance(setup, dict):
        return ""
    if setup.get("startingRole") == "custom_role":
        return _short(setup.get("customRole"), 160)
    role = setup.get("startingRole") or ""
    return _humanize(role) if role else ""


def resolve_recent_disruption(setup: Mapping[str, Any]) -> str:
    if not isinstance(setup, dict):
        return ""
    raw = setup.get("recentChange")
    if not raw or raw == "nothing_major":
        return ""
    if raw == "custom_event":
        return _short(setup.get("customRecentChange"), 200)
    return _humanize(raw)


def derive_world_frame(
    genre: Optional[str],
    *,
    groundedness: Optional[str] = None,
    setup: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Minimal world_frame for non-scenario creation. SF ≠ cyberpunk."""
    g = str(genre or "modern").strip().lower()
    base = dict(_GENRE_WORLD_FRAMES.get(g) or _GENRE_WORLD_FRAMES["modern"])
    if groundedness:
        base["groundedness"] = str(groundedness).strip().lower()[:40]
    if isinstance(setup, dict):
        req = _short(setup.get("worldElements"), MAX_ELEMENTS_LEN)
        exc = _short(setup.get("worldExclusions"), MAX_ELEMENTS_LEN)
        if req:
            base["required_elements"] = req
        if exc:
            base["excluded_elements"] = exc
    return base


def detect_source_path(
    setup: Optional[Mapping[str, Any]],
    *,
    scenario_id: Optional[str] = None,
    quick_start_key: Optional[str] = None,
) -> str:
    if quick_start_key or scenario_id:
        return "quick"
    if not isinstance(setup, dict) or not setup:
        return "unknown"
    explicit = str(setup.get("creationFlow") or setup.get("source_path") or "").strip().lower()
    if explicit in ("guided", "advanced", "quick"):
        return explicit
    # Heuristic: Advanced sends location/condition; Guided sends pressure list + hooks only.
    advanced_markers = (
        "startingLocation",
        "worldCondition",
        "characterKnowledge",
        "settingGroundedness",
        "consequenceSeverity",
    )
    if any(setup.get(k) for k in advanced_markers):
        return "advanced"
    if setup.get("pressures") or setup.get("want") or setup.get("fear"):
        return "guided"
    return "advanced"


# ---------------------------------------------------------------------------
# Normalize setup for persistence
# ---------------------------------------------------------------------------


def normalize_custom_world_setup(
    setup: Optional[Mapping[str, Any]],
    *,
    source_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Strip dead controls, bound strings, omit empties, normalize archetypes."""
    if not isinstance(setup, dict) or not setup:
        return None

    out: Dict[str, Any] = {}
    for key, value in setup.items():
        if key in DEAD_SETUP_KEYS or key in ENGINE_ONLY_SETUP_KEYS:
            continue
        if key in TOP_LEVEL_MAPPED_KEYS:
            continue
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            limit = MAX_ELEMENTS_LEN if key in ("worldElements", "worldExclusions", "customLocation", "customRecentChange", "customRole") else MAX_HOOK_LEN
            if key in ("desire", "danger", "weakness", "origin", "formerLife", "strengths", "carried", "worldConcept", "worldTone"):
                limit = 220
            out[key] = text[:limit]
        elif isinstance(value, list):
            cleaned = []
            for item in value[:12]:
                if item is None:
                    continue
                if isinstance(item, str):
                    t = item.strip()
                    if t:
                        cleaned.append(t[:MAX_HOOK_LEN])
                elif isinstance(item, (int, float, bool)):
                    cleaned.append(item)
            if cleaned:
                out[key] = cleaned
        elif isinstance(value, dict):
            if value:
                out[key] = value
        elif isinstance(value, (int, float, bool)):
            out[key] = value

    # Secret stays engine-only if caller re-injects later; never persist via this normalizer.
    out.pop("secret", None)

    who = normalize_who_matters(out.get("whoMatters"))
    if who:
        out["whoMatters"] = who

    pressures = out.get("pressures")
    if isinstance(pressures, list):
        out["pressures"] = [str(p).strip().lower()[:40] for p in pressures if str(p).strip()][:MAX_PRESSURES]
        if not out["pressures"]:
            out.pop("pressures", None)

    # Optional character hooks: omit empties (already handled) — leave closed slugs as-is.
    for optional_key in ("ghost", "talent", "flaw", "line"):
        if optional_key in out and not str(out[optional_key]).strip():
            out.pop(optional_key, None)

    path = (source_path or detect_source_path(out)).strip().lower()
    if path in ("guided", "advanced", "quick"):
        out["creationFlow"] = path

    return out or None


# ---------------------------------------------------------------------------
# Compact creation contract
# ---------------------------------------------------------------------------


def build_creation_contract(
    session: Optional[Mapping[str, Any]] = None,
    *,
    genre: Optional[str] = None,
    role: Optional[str] = None,
    tone: Optional[str] = None,
    difficulty: Optional[str] = None,
    scenario_id: Optional[str] = None,
    custom_world_setup: Optional[Mapping[str, Any]] = None,
    mature_content: Optional[Mapping[str, Any]] = None,
    quick_start_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Project a compact contract from session / request fields."""
    session = session if isinstance(session, dict) else {}
    setup_raw = custom_world_setup if custom_world_setup is not None else session.get("custom_world_setup")
    setup = normalize_custom_world_setup(setup_raw) if isinstance(setup_raw, dict) else None
    setup = setup or {}

    g = str(genre if genre is not None else session.get("genre") or "").strip()
    r = str(role if role is not None else session.get("role") or "").strip()
    t = str(tone if tone is not None else session.get("tone") or "").strip()
    d = str(difficulty if difficulty is not None else session.get("difficulty") or "").strip()
    sid = str(scenario_id if scenario_id is not None else session.get("scenario_id") or "").strip()
    mature = mature_content if mature_content is not None else session.get("mature_content")

    source = detect_source_path(
        setup,
        scenario_id=sid or None,
        quick_start_key=quick_start_key or session.get("quick_start_key"),
    )

    pressures: List[str] = []
    raw_pressures = setup.get("pressures")
    if isinstance(raw_pressures, list):
        pressures = [str(p) for p in raw_pressures if str(p).strip()][:MAX_PRESSURES]

    who = normalize_who_matters(setup.get("whoMatters"))
    location = resolve_starting_location(setup)
    groundedness = str(setup.get("settingGroundedness") or "").strip() or None
    stability = str(setup.get("worldCondition") or "").strip() or None
    disruption = resolve_recent_disruption(setup)
    knowledge = str(setup.get("characterKnowledge") or "").strip() or None

    world_frame = derive_world_frame(g, groundedness=groundedness, setup=setup)

    contract: Dict[str, Any] = {
        "source_path": source,
        "genre": g or None,
        "scenario_id": sid or None,
        "role": r or resolve_starting_role(setup) or None,
        "world_frame": world_frame,
        "starting_location": location or None,
        "world_stability": stability,
        "recent_disruption": disruption or None,
        "groundedness": groundedness,
        "active_pressures": pressures,
        "desire": str(setup.get("want") or setup.get("desire") or "").strip() or None,
        "fear": str(setup.get("fear") or "").strip() or None,
        "relationship_archetype": who if who and who != "nobody" else (who or None),
        "knowledge_scope": knowledge,
        "required_elements": _short(setup.get("worldElements"), MAX_ELEMENTS_LEN) or None,
        "excluded_elements": _short(setup.get("worldExclusions"), MAX_ELEMENTS_LEN) or None,
        "ghost": str(setup.get("ghost") or "").strip() or None,
        "talent": str(setup.get("talent") or "").strip() or None,
        "flaw": str(setup.get("flaw") or "").strip() or None,
        "moral_line": str(setup.get("line") or "").strip() or None,
        "tone": t or None,
        "difficulty": d or None,
        "mature_content": mature if isinstance(mature, dict) else None,
        "consequence_severity": str(setup.get("consequenceSeverity") or "").strip() or None,
    }
    # Drop Nones for compactness (keep empty lists only if meaningful).
    return {k: v for k, v in contract.items() if v is not None and v != []}


def classify_field(name: str) -> str:
    hard = {"genre", "role", "scenario_id", "starting_location", "source_path"}
    sim = {
        "world_frame",
        "world_stability",
        "recent_disruption",
        "groundedness",
        "active_pressures",
        "desire",
        "fear",
        "relationship_archetype",
        "knowledge_scope",
        "required_elements",
        "excluded_elements",
        "ghost",
        "talent",
        "flaw",
        "moral_line",
    }
    policy = {"tone", "difficulty", "mature_content", "consequence_severity"}
    excluded = {"worldPace", "storyFocus", "secret"}
    if name in hard:
        return "hard_state"
    if name in sim:
        return "persistent_simulation_input"
    if name in policy:
        return "presentation_policy"
    if name in excluded:
        return "unsupported_excluded"
    return "other"


# ---------------------------------------------------------------------------
# Seeding into rolling state / pressure inputs
# ---------------------------------------------------------------------------


def character_hooks_projection(contract: Mapping[str, Any]) -> Dict[str, str]:
    """Bounded structured character hooks (closed slugs preferred)."""
    hooks: Dict[str, str] = {}
    for key in ("desire", "fear", "ghost", "talent", "flaw", "moral_line"):
        val = contract.get(key)
        if val:
            hooks[key] = _short(val, MAX_HOOK_LEN)
    who = contract.get("relationship_archetype")
    if who and who != "nobody":
        hooks["relationship_archetype"] = str(who)
    return hooks


def seed_creation_into_rolling(
    rolling: Optional[Dict[str, Any]],
    contract: Mapping[str, Any],
    *,
    setup: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Seed durable rolling fields from the creation contract.

    Does not invent named cast. Does not dump full free-text setup repeatedly —
    compact structured hooks only. Secret is never seeded here.
    """
    out = dict(rolling or {})
    setup = setup if isinstance(setup, dict) else {}

    # Authoritative starting place when model left scene empty / generic.
    location = contract.get("starting_location")
    if location:
        scene = str(out.get("scene") or "").strip()
        if not scene or scene.lower() in ("", "unknown", "unspecified"):
            out["scene"] = str(location)[:160]

    # Compact character context — dict, not free-text essay.
    hooks = character_hooks_projection(contract)
    if hooks:
        existing = out.get("character_hooks")
        if isinstance(existing, dict):
            merged = dict(existing)
            for k, v in hooks.items():
                merged.setdefault(k, v)
            out["character_hooks"] = merged
        else:
            out["character_hooks"] = hooks

    # Knowledge scope (player familiarity only — not hidden truth).
    knowledge = contract.get("knowledge_scope")
    if knowledge and not out.get("knowledge_scope"):
        out["knowledge_scope"] = str(knowledge)[:80]

    # World frame constraints (compact).
    frame = contract.get("world_frame")
    if isinstance(frame, dict) and not out.get("world_frame"):
        out["world_frame"] = {
            k: frame[k]
            for k in ("era", "setting", "technology", "groundedness", "required_elements", "excluded_elements")
            if frame.get(k)
        }

    # simulation_hooks: compact coded lines (protected list — survives compaction).
    hooks_list = list(out.get("simulation_hooks") or [])
    for label, key in (
        ("desire", "desire"),
        ("fear", "fear"),
        ("ghost", "ghost"),
        ("talent", "talent"),
        ("flaw", "flaw"),
        ("moral_line", "moral_line"),
    ):
        val = contract.get(key)
        if val:
            hooks_list.append(f"{label}:{_short(val, 80)}")
    who = contract.get("relationship_archetype")
    if who and who != "nobody":
        hooks_list.append(f"relationship_archetype:{who}")
    if knowledge:
        hooks_list.append(f"knowledge_scope:{_short(knowledge, 60)}")
    if contract.get("groundedness"):
        hooks_list.append(f"groundedness:{_short(contract['groundedness'], 40)}")
    if contract.get("required_elements"):
        hooks_list.append(f"required_elements:{_short(contract['required_elements'], 100)}")
    if contract.get("excluded_elements"):
        hooks_list.append(f"excluded_elements:{_short(contract['excluded_elements'], 100)}")
    if location:
        hooks_list.append(f"starting_location:{_short(location, 80)}")
    if contract.get("world_stability"):
        hooks_list.append(f"world_stability:{_short(contract['world_stability'], 40)}")
    if contract.get("recent_disruption"):
        hooks_list.append(f"recent_disruption:{_short(contract['recent_disruption'], 100)}")
    if contract.get("role"):
        hooks_list.append(f"role:{_short(contract['role'], 80)}")

    # Dedupe preserving order (hooks may be str or dict from prior model state).
    seen = set()
    deduped: List[Any] = []
    for h in hooks_list:
        if isinstance(h, str):
            key: Any = ("str", h)
        elif isinstance(h, dict):
            try:
                key = (
                    "dict",
                    json.dumps(h, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str),
                )
            except Exception:
                key = ("dict", str(h)[:200])
        else:
            try:
                key = (type(h).__name__, h)
                hash(key)
            except TypeError:
                key = (type(h).__name__, str(h)[:200])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(h)
    out["simulation_hooks"] = deduped[:16]

    # World instability from stability + disruption + pressures (conditions, not cutscenes).
    instability = list(out.get("world_instability") or []) if isinstance(out.get("world_instability"), list) else []
    if contract.get("world_stability"):
        instability.append(f"world_stability:{contract['world_stability']}")
    if contract.get("recent_disruption"):
        instability.append(f"recent_disruption:{_short(contract['recent_disruption'], 120)}")
    for p in contract.get("active_pressures") or []:
        # Human-readable prefix retained for continuity with pre-Stage-2A seed format.
        instability.append(f"active pressure: {_short(p, 60)}")
    # Dedupe with stable JSON for dict/list rows (order-independent).
    inst_seen = set()
    inst_out: List[str] = []
    for entry in instability:
        if isinstance(entry, str):
            s = entry
        elif isinstance(entry, dict):
            try:
                s = json.dumps(
                    entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
            except Exception:
                s = str(entry)[:200]
        else:
            try:
                s = json.dumps(
                    entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
                )
            except Exception:
                s = str(entry)[:200]
        if s in inst_seen:
            continue
        inst_seen.add(s)
        inst_out.append(s)
    out["world_instability"] = inst_out[:12]

    # Relationship floor: archetype only — no named person, no cast member.
    who = contract.get("relationship_archetype")
    if who and who != "nobody":
        threads = list(out.get("relationship_threads") or [])
        # Social ecosystem marker (unnamed).
        if not any(
            isinstance(t, dict) and t.get("name") == "social ecosystem" for t in threads
        ):
            threads.append(
                {
                    "name": "social ecosystem",
                    "dynamic": "low",
                    "intensity": "medium",
                    "leverage": "relationship systems active; bonds affect trust and leverage",
                    "named": False,
                }
            )
        if not any(
            isinstance(t, dict) and t.get("archetype") == who for t in threads
        ):
            threads.append(
                {
                    "name": "who_matters_floor",
                    "dynamic": "attachment",
                    "archetype": who,
                    "intensity": "medium",
                    "named": False,
                    "leverage": "an unnamed bond of this kind is a stake; do not invent a proper name until play establishes one",
                }
            )
        out["relationship_threads"] = threads[:8]

    # Inventory from carried (Advanced free-text) if present.
    carried = setup.get("carried")
    if carried:
        items = [x.strip() for x in str(carried).replace(";", ",").split(",") if x.strip()]
        if items and not out.get("inventory_objects"):
            out["inventory_objects"] = [
                {
                    "object": item[:80],
                    "qty": "1",
                    "condition": "player-described",
                    "location_state": "carried",
                    "where": "on player at story start",
                }
                for item in items[:10]
            ]

    return out


def pressure_seed_specs(contract: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Return pressure_graph upsert specs from creation contract (max 3)."""
    specs: List[Dict[str, Any]] = []
    for idx, item in enumerate(list(contract.get("active_pressures") or [])[:MAX_PRESSURES]):
        if not item:
            continue
        kind = map_pressure_kind(str(item))
        specs.append(
            {
                "kind": kind,
                "origin_type": "custom_setup",
                "origin_id": f"pressure:{str(item).strip().lower()[:40]}",
                "scope": "local",
                "magnitude": 36 + idx * 3,
                "trend": 0,
                "tags": ["custom_setup", "creation", str(item).strip().lower()[:40]],
                "evidence_refs": [f"custom_setup:pressures:{str(item).strip().lower()[:40]}"],
                "label": _humanize(item)[:80],
            }
        )
    return specs


# ---------------------------------------------------------------------------
# Later-turn bounded directive
# ---------------------------------------------------------------------------


def build_later_turn_creation_directive(contract: Mapping[str, Any]) -> str:
    """Compact later-turn reassertion — not a full onboarding dump."""
    if not contract:
        return ""
    # Quick Start uses scenario frame; skip empty non-setup contracts.
    if contract.get("source_path") == "quick" and not contract.get("active_pressures"):
        if contract.get("scenario_id"):
            return ""

    lines: List[str] = ["[CREATION_CONTEXT]"]
    genre = contract.get("genre")
    role = contract.get("role")
    if genre or role:
        lines.append(f"Identity: genre={genre or '—'}; role={role or '—'}.")

    frame = contract.get("world_frame") if isinstance(contract.get("world_frame"), dict) else {}
    if frame:
        bits = []
        for k in ("era", "setting", "technology", "groundedness"):
            if frame.get(k):
                bits.append(f"{k}={frame[k]}")
        if bits:
            lines.append("World frame: " + "; ".join(bits) + ".")
        if frame.get("required_elements") or contract.get("required_elements"):
            lines.append(
                f"Permitted elements: {_short(frame.get('required_elements') or contract.get('required_elements'), 100)}."
            )
        if frame.get("excluded_elements") or contract.get("excluded_elements"):
            lines.append(
                f"Excluded elements: {_short(frame.get('excluded_elements') or contract.get('excluded_elements'), 100)}."
            )

    if contract.get("starting_location"):
        lines.append(f"Starting place remains relevant: {_short(contract['starting_location'], 80)}.")
    if contract.get("world_stability"):
        lines.append(f"World stability: {contract['world_stability']}.")
    if contract.get("recent_disruption"):
        lines.append(
            f"Established past disruption (not a forced current event): {_short(contract['recent_disruption'], 100)}."
        )
    if contract.get("knowledge_scope"):
        lines.append(
            f"Player knowledge scope: {contract['knowledge_scope']} (not hidden world truth)."
        )

    pressures = contract.get("active_pressures") or []
    if pressures:
        lines.append(
            "Seeded pressures (retain until resolved or transformed): "
            + ", ".join(_short(p, 40) for p in pressures[:3])
            + "."
        )

    hook_bits = []
    for label, key in (
        ("desire", "desire"),
        ("fear", "fear"),
        ("ghost", "ghost"),
        ("talent", "talent"),
        ("flaw", "flaw"),
        ("line", "moral_line"),
    ):
        if contract.get(key):
            hook_bits.append(f"{label}={_short(contract[key], 40)}")
    if hook_bits:
        lines.append("Character hooks: " + "; ".join(hook_bits) + ".")

    who = contract.get("relationship_archetype")
    if who and who != "nobody":
        lines.append(
            f"Relationship archetype (unnamed until established in play): {who}."
        )
    elif who == "nobody":
        lines.append("No relationship floor seeded; do not invent a bond cast member.")

    tone = contract.get("tone")
    difficulty = contract.get("difficulty")
    if tone or difficulty:
        lines.append(
            f"Policy: tone={tone or '—'} (presentation); difficulty={difficulty or '—'} (consequence harshness)."
        )

    lines.append(
        "Do not replace creation identity with an unrelated modern debt/property plot "
        "unless seeded state already established it."
    )
    return "\n".join(lines[: MAX_LATER_TURN_LINES + 2])


def build_opening_setup_lines(contract: Mapping[str, Any]) -> List[str]:
    """Extra opening lines from contract (alongside existing genre/role/tone)."""
    lines: List[str] = []
    if not contract:
        return lines
    if contract.get("starting_location"):
        lines.append(f"Starting place: {contract['starting_location']}")
    if contract.get("world_stability"):
        lines.append(f"World stability: {contract['world_stability']}")
    if contract.get("recent_disruption"):
        lines.append(
            f"Recent disruption (established past, not a forced opening beat): {contract['recent_disruption']}"
        )
    if contract.get("knowledge_scope"):
        lines.append(f"Character knowledge scope: {contract['knowledge_scope']}")
    frame = contract.get("world_frame") if isinstance(contract.get("world_frame"), dict) else {}
    if frame.get("era") or frame.get("setting"):
        lines.append(
            f"World frame: era={frame.get('era', '')}; setting={frame.get('setting', '')}; "
            f"technology={frame.get('technology', '')}."
        )
    return lines


def settlement_stability_from_contract(contract: Mapping[str, Any]) -> Optional[str]:
    cond = str(contract.get("world_stability") or "").strip().lower()
    return CONDITION_STABILITY.get(cond)


# ---------------------------------------------------------------------------
# Stage 2B — compaction survival + hook influence (no mind control)
# ---------------------------------------------------------------------------


def restore_creation_surfaces(
    rolling: Optional[Dict[str, Any]],
    session: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Re-project world_frame + character_hooks from durable session after compaction.

    Session.custom_world_setup + top-level fields are authority. Model omission
    of dict surfaces must not erase creation identity. Does not re-dump full
    onboarding prose; only compact structured fields.
    """
    out = dict(rolling or {})
    if not isinstance(session, Mapping):
        return out
    if session.get("scenario_id") and not session.get("custom_world_setup"):
        # Quick Start path — scenario frame is separate; do not invent Guided bag.
        return out
    if not session.get("custom_world_setup"):
        return out

    contract = build_creation_contract(session)
    if not contract:
        return out

    hooks = character_hooks_projection(contract)
    if hooks:
        existing = out.get("character_hooks") if isinstance(out.get("character_hooks"), dict) else {}
        merged = dict(existing)
        for k, v in hooks.items():
            # Prefer durable contract values; do not let empty model dict wipe them.
            if not merged.get(k):
                merged[k] = v
            else:
                merged.setdefault(k, v)
        # Always re-assert core desire/fear from contract (hard character hooks).
        for core in ("desire", "fear"):
            if hooks.get(core):
                merged[core] = hooks[core]
        out["character_hooks"] = merged

    frame = contract.get("world_frame")
    if isinstance(frame, dict):
        slim = {
            k: frame[k]
            for k in (
                "era",
                "setting",
                "technology",
                "groundedness",
                "required_elements",
                "excluded_elements",
            )
            if frame.get(k)
        }
        existing_f = out.get("world_frame") if isinstance(out.get("world_frame"), dict) else {}
        restored = dict(existing_f)
        for k, v in slim.items():
            if not restored.get(k):
                restored[k] = v
        # Exclusions always re-assert from contract (cannot be prose-overwritten away).
        if slim.get("excluded_elements"):
            restored["excluded_elements"] = slim["excluded_elements"]
        if slim.get("required_elements") and not restored.get("required_elements"):
            restored["required_elements"] = slim["required_elements"]
        if slim.get("era"):
            restored["era"] = slim["era"]
        if slim.get("setting"):
            restored["setting"] = slim["setting"]
        if slim.get("technology"):
            restored["technology"] = slim["technology"]
        if slim.get("groundedness"):
            restored["groundedness"] = slim["groundedness"]
        out["world_frame"] = restored

    knowledge = contract.get("knowledge_scope")
    if knowledge and not out.get("knowledge_scope"):
        out["knowledge_scope"] = str(knowledge)[:80]

    # Opening location: if scene was wiped, restore starting place cue.
    location = contract.get("starting_location")
    if location:
        scene = str(out.get("scene") or "").strip()
        if not scene or scene.lower() in ("", "unknown", "unspecified"):
            out["scene"] = str(location)[:160]

    return out


def build_hook_influence_directive(contract: Mapping[str, Any]) -> str:
    """Bounded influence rules — shape stakes without controlling the player."""
    if not contract:
        return ""
    lines = ["[CHARACTER_HOOKS_INFLUENCE]"]
    if contract.get("desire"):
        lines.append(
            f"Desire ({_short(contract['desire'], 40)}): shapes opportunities and tension; "
            "never force a choice that pursues it."
        )
    if contract.get("fear"):
        lines.append(
            f"Fear ({_short(contract['fear'], 40)}): raises stakes when relevant; "
            "never force fearful behaviour against the player's action."
        )
    if contract.get("ghost"):
        lines.append(
            f"Ghost ({_short(contract['ghost'], 40)}): may colour memory or pressure; "
            "no mandatory flashback loop."
        )
    if contract.get("talent"):
        lines.append(
            f"Talent ({_short(contract['talent'], 40)}): may make capability plausible; "
            "never guarantee success."
        )
    if contract.get("flaw"):
        lines.append(
            f"Flaw ({_short(contract['flaw'], 40)}): may increase risk when relevant; "
            "never override the player's declared action."
        )
    if contract.get("moral_line"):
        lines.append(
            f"Moral line ({_short(contract['moral_line'], 40)}): may shape dilemmas and "
            "consequences; crossing it is allowed with cost — not platform policy."
        )
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def difficulty_reaches_severity(session: Mapping[str, Any]) -> Dict[str, Any]:
    """Prove difficulty is not tone-only: expose existing severity multiplier consumer."""
    from run_identity import difficulty_severity_multiplier

    diff = str(session.get("difficulty") or "standard").strip().lower()
    mult = float(difficulty_severity_multiplier({"difficulty": diff}))
    return {
        "difficulty": diff,
        "severity_multiplier": mult,
        "consumer": "run_identity.difficulty_severity_multiplier → pressure/identity",
        "tone_independent": True,
    }


def active_seeded_pressure_labels(session: Mapping[str, Any]) -> List[str]:
    """Unresolved creation pressures still binding for later-turn context."""
    contract = build_creation_contract(session)
    labels = [str(p) for p in (contract.get("active_pressures") or []) if p]
    # Also surface custom_setup nodes still active in pressure_graph.
    replay = session.get("replayability_state") if isinstance(session, Mapping) else None
    graph = (replay or {}).get("pressure_graph") if isinstance(replay, Mapping) else None
    nodes = (graph or {}).get("nodes") if isinstance(graph, Mapping) else None
    if isinstance(nodes, list):
        for n in nodes:
            if not isinstance(n, dict):
                continue
            if str(n.get("origin_type") or "") != "custom_setup":
                continue
            status = str(n.get("status") or "active").lower()
            if status in ("resolved", "archived"):
                continue
            lab = str(n.get("label") or n.get("origin_id") or "").strip()
            if lab and lab not in labels:
                labels.append(lab[:80])
    return labels[:8]
