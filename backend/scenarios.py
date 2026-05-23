"""
Curated story scenario presets for the Dice Reaction Story Engine.

Each scenario provides a fully-seeded opening: genre, role, tone, difficulty,
recommended mode, starting location, opening pressure, key NPCs, starting
inventory, hidden threat, and a verbatim opening seed paragraph passed to the
engine. The engine then opens the scene grounded in these constraints.
"""

from __future__ import annotations

from typing import Any, Dict, List

SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "suburban-collapse",
        "title": "Suburban Collapse",
        "pitch": (
            "Power, water, and emergency services fail in a quiet neighbourhood. "
            "What breaks first — the grid, the food, or the people next door?"
        ),
        "genre": "post-apocalyptic",
        "role": "ordinary resident",
        "tone": "grounded, slow-burning",
        "difficulty": "hard",
        "mode": "advanced",
        "starting_location": (
            "Your two-storey house on Elm Crescent, mid-suburb. Day 4 since the "
            "grid went dark. Pantry thinning. Tap water cloudy. Neighbours' lawns "
            "now scattered with bagged trash because the trucks stopped."
        ),
        "starting_pressure": (
            "The Hendersons two doors down had a generator. Last night it stopped. "
            "Today their door is open and the dog is loose. Nobody has gone over."
        ),
        "key_npcs": [
            {"name": "Marlene Cho", "role": "next-door neighbour, retired nurse, calm but tired", "stance": "ally"},
            {"name": "Greg Stahl", "role": "across-the-street, ex-military, watchful and territorial", "stance": "neutral, suspicious"},
            {"name": "The Hendersons", "role": "two doors down, status unknown since last night", "stance": "unknown"},
        ],
        "starting_inventory": (
            "Carried: house keys, wallet (cash $80, dead cards), phone (12% battery, no signal). "
            "Stored kitchen: 4 days of pantry food, ~6L bottled water, can opener, decent knives. "
            "Stored garage: hammer, claw bar, half tank in the car, no spare fuel. "
            "Worn: clothes for the weather. Load: light."
        ),
        "hidden_threat": (
            "A small group from the next neighbourhood has been quietly cataloguing which houses still have lights, "
            "smoke, or movement. They are NOT desperate yet. They are organising. When desperation lands in 3-5 days, "
            "they will arrive door-to-door, polite first, then not."
        ),
        "seed": (
            "The story opens on the fourth dim morning. The fridge has stopped humming days ago and the kitchen smells "
            "faintly wrong despite everything thrown out. Outside the air is too still — no traffic, no leaf blowers, "
            "no plane trails. Down the street, the Hendersons' generator has been silent since 2 a.m. "
            "Their dog Tucker is loose on the lawn, barking at nothing. The player is in their own kitchen, looking "
            "at a glass of cloudy water and a phone that hasn't found signal in 19 hours. The first choice should "
            "include checking on the Hendersons, fortifying inventory, talking to Marlene, watching Greg, and staying inside."
        ),
    },
    {
        "id": "dinosaur-containment-breach",
        "title": "Dinosaur Containment Breach",
        "pitch": (
            "A remote research facility loses containment. You have a rifle with three rounds, a flashlight that "
            "matters more than the rifle, and tracks already cutting across the access road."
        ),
        "genre": "prehistoric survival",
        "role": "junior containment technician",
        "tone": "tense, sweat-and-rain procedural",
        "difficulty": "brutal",
        "mode": "advanced",
        "starting_location": (
            "Substation 4 of the Mainland Site B compound — a humid riverside concrete bunker. Power flickering. "
            "The eastern paddock fence is down across two sections. Visibility 40m through wet ferns."
        ),
        "starting_pressure": (
            "Dr. Aris Kemal is bleeding from a thigh wound in the substation and cannot run. "
            "The radio's last broadcast 14 minutes ago said the medical team's jeep has not arrived."
        ),
        "key_npcs": [
            {"name": "Dr. Aris Kemal", "role": "senior ranger, leg torn open, lucid but fading", "stance": "ally, helpless"},
            {"name": "Site B radio (Maren)", "role": "voice-only from main hub, panicking, status unclear", "stance": "ally"},
            {"name": "The breach", "role": "at least one large theropod, possibly two; tracks suggest hunting pair", "stance": "hostile"},
        ],
        "starting_inventory": (
            "Carried: bolt-action rifle (3 rounds, ok condition), heavy torch (8 hours of light, harsh beam), "
            "radio handset (working, intermittent), tranquiliser pistol (1 dart, slow onset), pocket knife. "
            "Worn: wet jacket, hiking boots. Stored substation: med kit (basic), water (2L), first-aid stretcher, "
            "emergency flare (1). Load: manageable."
        ),
        "hidden_threat": (
            "There are TWO theropods, not one. The second is downwind and silent. It is using the rain to mask its "
            "approach and is currently between the substation and the medical team's stalled jeep. "
            "Any loud action (rifle shot, flare) will pull both onto the player within 1-2 turns."
        ),
        "seed": (
            "The story opens in the substation. Rain hammers the metal roof. Dr. Kemal is propped against the "
            "generator housing, his thigh wrapped in a torn shirt that is already dark. The flashlight beam falls on "
            "three-toed tracks crossing the concrete floor, water still pooling in them. The radio whispers static "
            "and then Maren's voice for one fractured sentence before it cuts out. The first choice should include "
            "staying with Kemal, going for the medical jeep, climbing to the substation roof for visibility, "
            "trying to repair the fence (impossible alone but tempting), or using the tranquiliser dart."
        ),
    },
    {
        "id": "cosmic-horror-road-town",
        "title": "Cosmic Horror Road Town",
        "pitch": (
            "Your car broke down outside Pilcrow Hollow. The motel clerk remembers you. You have never been here. "
            "The map says the highway goes east. The road goes north."
        ),
        "genre": "cosmic horror",
        "role": "passing traveller",
        "tone": "dread, slow unravelling, restrained",
        "difficulty": "standard",
        "mode": "advanced",
        "starting_location": (
            "Pilcrow Hollow, population sign blistered. Single main street, one motel ('Hollow Rest'), one diner "
            "('Mercer's'), a gas station with a closed sign that was open ten minutes ago. The sky is the colour of "
            "wet aluminium and has been since the player arrived."
        ),
        "starting_pressure": (
            "The motel clerk, Edith, greets the player by their first name and asks 'how was the drive back?'. "
            "She gives them room 7 without taking ID. Room 7 has the player's open suitcase on the bed, half-unpacked."
        ),
        "key_npcs": [
            {"name": "Edith (motel clerk)", "role": "knows the player, mid-60s, calm, smells faintly of wet stone", "stance": "unknown — too friendly"},
            {"name": "Sheriff Voss", "role": "tall, polite, asks about the player's 'cousin'", "stance": "unknown — watching"},
            {"name": "The diner regulars", "role": "five locals who all stand up and leave when the player enters", "stance": "afraid"},
        ],
        "starting_inventory": (
            "Carried: car keys (car won't start), wallet, phone (no signal, photos seem to have one extra picture "
            "of a place the player has never been), road atlas (the route through Pilcrow Hollow is not printed). "
            "Worn: travel clothes. Stored car: overnight bag, water bottle (half), snack food, jumper cables. "
            "Load: light."
        ),
        "hidden_threat": (
            "The town remembers visitors who have not yet arrived and forgets the ones who leave. Under the "
            "Methodist church, beneath the boiler room floor, is a soft place in the world. Every guest who stays "
            "three nights becomes a local. Every local who leaves the town limits forgets the town in 40 minutes. "
            "The thing under the church is patient and is not the player's enemy — it is hungry, and the town feeds it."
        ),
        "seed": (
            "The story opens at dusk on the gravel apron of the gas station. The player's car ticks as it cools, "
            "hood up. The clerk inside the booth has not moved in two minutes. Across the street, the Hollow Rest "
            "neon flickers. A woman in the doorway raises one hand to wave, and the player's stomach turns because "
            "she is waving like she has been waiting. The first choice should include trying the gas station clerk, "
            "walking to the motel, checking the diner, attempting the car again, and walking the road out on foot."
        ),
    },
]


def get_scenarios() -> List[Dict[str, Any]]:
    """Public list (without the heavy seed paragraph) for the picker UI."""
    return [
        {k: v for k, v in s.items() if k != "seed"}
        for s in SCENARIOS
    ]


def get_scenario(scenario_id: str) -> Dict[str, Any] | None:
    return next((s for s in SCENARIOS if s["id"] == scenario_id), None)
