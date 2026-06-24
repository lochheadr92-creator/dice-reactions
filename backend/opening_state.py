"""
Opening State v1 — archetype selection, structured truth, scenario preservation.

Engine-owned opening facts are generated before the first provider call.
The opening directive renders compact guidance from those facts only.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Mapping, Optional

from run_identity import select_from_namespace

OPENING_DIRECTIVE_MARKER = "[REPLAYABILITY_OPENING_V1]"
MAX_FACT_LEN = 120
MAX_ORIGINS = 4

OPENING_ARCHETYPES: Dict[str, Dict[str, str]] = {
    "interrupted_departure": {
        "label": "Interrupted Departure",
        "hook": "The player was about to leave when something stops them cold.",
        "immediate_problem": "departure blocked by urgent interruption",
        "threatened_resource": "time and mobility",
        "relationship_tension": "someone needs an answer before you go",
        "time_pressure": "the window to leave is closing now",
        "opportunity": "a last exchange could change what you carry out",
    },
    "wrong_number": {
        "label": "Wrong Number",
        "hook": "A message, call, or arrival was meant for someone else — but names the player.",
        "immediate_problem": "misaddressed message implicates the player",
        "threatened_resource": "privacy and cover",
        "relationship_tension": "sender expects a reply the player cannot safely give",
        "time_pressure": "the sender is waiting for acknowledgment",
        "opportunity": "the mistake may reveal leverage or a lead",
    },
    "last_chance_window": {
        "label": "Last Chance Window",
        "hook": "A narrow opportunity is expiring within the scene's immediate horizon.",
        "immediate_problem": "a fleeting chance will vanish if ignored",
        "threatened_resource": "timing and access",
        "relationship_tension": "others may seize the chance first",
        "time_pressure": "minutes or hours remain, not days",
        "opportunity": "acting now could secure a decisive advantage",
    },
    "unexpected_visitor": {
        "label": "Unexpected Visitor",
        "hook": "Someone arrives unannounced with stakes already attached.",
        "immediate_problem": "an unscheduled arrival forces confrontation",
        "threatened_resource": "safety and secrecy",
        "relationship_tension": "visitor arrives with demands or accusations",
        "time_pressure": "the visitor will not wait politely",
        "opportunity": "their arrival may open a trade or confession",
    },
    "deadline_arrived": {
        "label": "Deadline Arrived",
        "hook": "A clock the player ignored is now ringing in the present moment.",
        "immediate_problem": "an overdue obligation is now due",
        "threatened_resource": "credibility and schedule",
        "relationship_tension": "creditors or authorities expect compliance",
        "time_pressure": "the deadline is active this scene",
        "opportunity": "meeting it partially may buy breathing room",
    },
    "betrayal_suspected": {
        "label": "Betrayal Suspected",
        "hook": "Evidence suggests trust was misplaced — not proven, but urgent.",
        "immediate_problem": "trust fracture needs immediate response",
        "threatened_resource": "allies and information",
        "relationship_tension": "an ally may have acted against the player",
        "time_pressure": "confrontation or silence both carry cost",
        "opportunity": "careful probing could confirm or clear suspicion",
    },
    "resource_runs_out": {
        "label": "Resource Runs Out",
        "hook": "A necessary resource fails, empties, or is denied at the worst moment.",
        "immediate_problem": "critical supply unavailable when needed",
        "threatened_resource": "fuel, medicine, food, or shelter",
        "relationship_tension": "someone controls what the player lacks",
        "time_pressure": "needs are immediate, not theoretical",
        "opportunity": "scarcity may force a trade or risky salvage",
    },
    "witness_present": {
        "label": "Witness Present",
        "hook": "Someone is watching who should not be, or who changes the stakes by seeing.",
        "immediate_problem": "observed actions carry higher stakes",
        "threatened_resource": "secrecy and freedom of action",
        "relationship_tension": "witness may report or leverage what they see",
        "time_pressure": "the witness is present now",
        "opportunity": "winning the witness could neutralize the threat",
    },
    "locked_in": {
        "label": "Locked In",
        "hook": "An exit, route, or option is suddenly closed — movement is constrained.",
        "immediate_problem": "movement or escape route blocked",
        "threatened_resource": "mobility and options",
        "relationship_tension": "someone may hold the key or blame",
        "time_pressure": "confinement worsens if ignored",
        "opportunity": "negotiation may reopen a path",
    },
    "message_arrives": {
        "label": "Message Arrives",
        "hook": "News, a summons, or a warning lands before the player can settle.",
        "immediate_problem": "incoming news demands response",
        "threatened_resource": "attention and cover story",
        "relationship_tension": "sender's intent may be hostile or needy",
        "time_pressure": "reply or action expected soon",
        "opportunity": "the message may contain leverage or a lead",
    },
    "injury_complicates": {
        "label": "Injury Complicates",
        "hook": "Pain, impairment, or someone else's wound forces an immediate decision.",
        "immediate_problem": "injury impairs immediate capability",
        "threatened_resource": "health and stamina",
        "relationship_tension": "care or blame attaches to the wounded party",
        "time_pressure": "worsening injury if untreated",
        "opportunity": "aid now may earn loyalty or reveal skill",
    },
    "authority_demands": {
        "label": "Authority Demands",
        "hook": "Power — formal or informal — is already exerting pressure on the player.",
        "immediate_problem": "authority is exerting immediate demand",
        "threatened_resource": "autonomy and legal standing",
        "relationship_tension": "power holder expects compliance",
        "time_pressure": "defiance or delay will be punished",
        "opportunity": "partial compliance may buy negotiation room",
    },
    "storm_approaches": {
        "label": "Storm Approaches",
        "hook": "Environmental pressure is closing in: weather, noise, heat, darkness, or contagion.",
        "immediate_problem": "environmental hazard closing in",
        "threatened_resource": "shelter and safe passage",
        "relationship_tension": "others compete for the same refuge",
        "time_pressure": "conditions worsen within the scene",
        "opportunity": "preparation now may prevent catastrophe",
    },
    "debt_called": {
        "label": "Debt Called",
        "hook": "An old favour, promise, or obligation is collected now — politely or not.",
        "immediate_problem": "an old obligation is collected now",
        "threatened_resource": "favours and future goodwill",
        "relationship_tension": "creditor expects payment or service",
        "time_pressure": "refusal escalates immediately",
        "opportunity": "renegotiation may restructure the debt",
    },
}

DEFAULT_GENRE = "general"

GENRE_ARCHETYPE_CATALOG: Dict[str, List[str]] = {
    "general": list(OPENING_ARCHETYPES.keys()),
    "post-apocalyptic": [
        "resource_runs_out",
        "unexpected_visitor",
        "witness_present",
        "locked_in",
        "storm_approaches",
        "deadline_arrived",
        "authority_demands",
        "last_chance_window",
    ],
    "prehistoric survival": [
        "injury_complicates",
        "storm_approaches",
        "resource_runs_out",
        "witness_present",
        "locked_in",
        "deadline_arrived",
        "unexpected_visitor",
    ],
    "noir": [
        "wrong_number",
        "betrayal_suspected",
        "witness_present",
        "message_arrives",
        "debt_called",
        "authority_demands",
        "last_chance_window",
    ],
    "fantasy": [
        "unexpected_visitor",
        "message_arrives",
        "debt_called",
        "authority_demands",
        "last_chance_window",
        "storm_approaches",
        "witness_present",
    ],
    "horror": [
        "witness_present",
        "locked_in",
        "wrong_number",
        "storm_approaches",
        "injury_complicates",
        "unexpected_visitor",
        "message_arrives",
    ],
    "romance": [
        "interrupted_departure",
        "unexpected_visitor",
        "message_arrives",
        "last_chance_window",
        "witness_present",
        "debt_called",
    ],
    "mystery": [
        "wrong_number",
        "witness_present",
        "message_arrives",
        "betrayal_suspected",
        "authority_demands",
        "deadline_arrived",
    ],
}

SCENARIO_ARCHETYPE_HINTS: Dict[str, str] = {
    "suburban-collapse": "unexpected_visitor",
    "dinosaur-containment-breach": "injury_complicates",
    "cosmic-horror-road-town": "witness_present",
}


def _stable_fact_id(run_seed: str, slot: str) -> str:
    digest = hashlib.sha256(f"{run_seed}:opening:fact:{slot}".encode("utf-8")).hexdigest()
    return f"fact-{digest[:12]}"


def _bound_text(value: str) -> str:
    text = (value or "").strip()
    return text[:MAX_FACT_LEN]


def normalize_genre(genre: Optional[str]) -> str:
    g = (genre or DEFAULT_GENRE).strip().lower()
    return g if g in GENRE_ARCHETYPE_CATALOG else DEFAULT_GENRE


def catalog_for_genre(genre: Optional[str]) -> List[str]:
    return list(GENRE_ARCHETYPE_CATALOG.get(normalize_genre(genre), GENRE_ARCHETYPE_CATALOG[DEFAULT_GENRE]))


def _pressure_origins(
    run_seed: str,
    identity: Mapping[str, Any],
    archetype_id: str,
) -> List[Dict[str, str]]:
    origins: List[Dict[str, str]] = []
    slots = (
        ("primary", identity.get("primary_pressure_kind", "resource")),
        ("secondary", identity.get("secondary_pressure_kind", "social")),
        ("scarcity", identity.get("scarcity_axis", "time")),
        ("fault", identity.get("relationship_fault_line", "loyalty")),
    )
    for slot, kind in slots[:MAX_ORIGINS]:
        origin_id = _stable_fact_id(run_seed, f"pressure-origin-{slot}")
        origins.append(
            {
                "origin_id": origin_id,
                "kind": str(kind),
                "slot": slot,
                "source_archetype": archetype_id,
            }
        )
    return origins


def select_opening_archetype(
    run_seed: str,
    setup: Mapping[str, Any],
    *,
    identity: Optional[Mapping[str, Any]] = None,
    scenario: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Pick an opening archetype and emit structured engine-owned opening truth.

    Scenario preservation: curated scenarios keep canon location/NPCs; variation
    applies only to dimensions the scenario leaves open.
    """
    genre = setup.get("genre")
    scenario_id = setup.get("scenario_id")
    preserved = bool(scenario_id and scenario)
    id_seed = identity or {}

    if preserved and scenario_id in SCENARIO_ARCHETYPE_HINTS:
        archetype_id = SCENARIO_ARCHETYPE_HINTS[scenario_id]
    else:
        pool = catalog_for_genre(genre)
        archetype_id = select_from_namespace(run_seed, "opening_archetype", tuple(pool))

    if archetype_id not in OPENING_ARCHETYPES:
        archetype_id = catalog_for_genre(genre)[0]

    meta = OPENING_ARCHETYPES[archetype_id]
    scarcity = str(id_seed.get("scarcity_axis") or "time")
    fault = str(id_seed.get("relationship_fault_line") or "loyalty")
    opportunity = str(id_seed.get("opportunity_style") or meta["opportunity"]).replace("_", " ")

    opening: Dict[str, Any] = {
        "archetype_id": archetype_id,
        "label": meta["label"],
        "hook": meta["hook"],
        "genre": normalize_genre(genre),
        "preserved_scenario": preserved,
        "scenario_id": scenario_id,
        "immediate_problem": _bound_text(meta["immediate_problem"]),
        "threatened_resource": _bound_text(f"{scarcity} — {meta['threatened_resource']}"),
        "relationship_tension": _bound_text(f"{fault} — {meta['relationship_tension']}"),
        "time_pressure": _bound_text(meta["time_pressure"]),
        "opportunity": _bound_text(opportunity),
        "fact_ids": {
            "problem": _stable_fact_id(run_seed, "problem"),
            "resource": _stable_fact_id(run_seed, "resource"),
            "tension": _stable_fact_id(run_seed, "tension"),
            "time": _stable_fact_id(run_seed, "time"),
            "opportunity": _stable_fact_id(run_seed, "opportunity"),
        },
        "pressure_origins": _pressure_origins(run_seed, id_seed, archetype_id),
    }

    if preserved and scenario:
        opening["starting_location_ref"] = str(scenario.get("starting_location") or scenario.get("location") or "")[:80]
        opening["scenario_title"] = str(scenario.get("title") or scenario_id or "")[:80]
        if scenario.get("starting_pressure"):
            opening["scenario_starting_pressure"] = _bound_text(str(scenario.get("starting_pressure")))

    return opening


def build_opening_directive(
    opening: Mapping[str, Any],
    identity: Mapping[str, Any],
    *,
    scenario: Optional[Mapping[str, Any]] = None,
) -> str:
    """Non-persisted turn-1 opening guidance from structured facts."""
    if not opening:
        return ""

    lines = [
        OPENING_DIRECTIVE_MARKER,
        "INTERNAL — replayability opening contract (guidance only; do not expose labels):",
        f"- Immediate problem: {opening.get('immediate_problem', '').strip()}",
        f"- Threatened resource: {opening.get('threatened_resource', '').strip()}",
        f"- Relationship tension: {opening.get('relationship_tension', '').strip()}",
        f"- Time pressure: {opening.get('time_pressure', '').strip()}",
        f"- Opportunity: {opening.get('opportunity', '').strip()}",
        f"- Primary pressure kind: {identity.get('primary_pressure_kind', 'resource')}",
        f"- Scarcity axis: {identity.get('scarcity_axis', 'time')}",
        "- Open in medias res; connect first choices to these facts immediately.",
        "- Store visible pressure in state Pressure (the engine maintains rolling_state.active_pressures).",
        "- Preserve any curated scenario seed as canonical; do not replace it.",
    ]

    if opening.get("preserved_scenario") and scenario:
        lines.append(
            f"- Scenario '{scenario.get('title') or opening.get('scenario_id')}' is authoritative "
            "for location, NPCs, inventory, and hidden threat concealment."
        )
        if scenario.get("starting_pressure"):
            lines.append(
                "- Honour scenario starting_pressure as the immediate foreground symptom."
            )

    if identity.get("has_secret"):
        lines.append(
            "- Player carries a hidden secret; do NOT reveal it in the opening — "
            "surface symptoms, pressure, or moral weight only."
        )

    return "\n".join(lines)