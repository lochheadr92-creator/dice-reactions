"""
Curated story scenario presets for the Dice Reaction Story Engine.

Each scenario provides a fully-seeded opening: genre, role, tone, difficulty,
recommended mode, starting location, opening pressure, key NPCs, starting
inventory, hidden threat, world_frame (coherence), and a verbatim opening seed.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Sequence

from living_cast_live_gate import is_live_gate_enabled


def _frame(
    *,
    era: str,
    technology: str,
    setting: str,
    primary_pressures: Sequence[str],
    required_anchors: Sequence[str],
    forbidden_opening_frames: Sequence[str],
) -> Dict[str, Any]:
    return {
        "era": era,
        "technology": technology,
        "setting": setting,
        "primary_pressures": list(primary_pressures),
        "required_anchors": list(required_anchors),
        "forbidden_opening_frames": list(forbidden_opening_frames),
    }


_FORBID_MODERN_DEBT = (
    "property_debt_collection",
    "urban_real_estate_dispute",
    "paperwork_and_inspections_as_primary_conflict",
    "civil_foreman_creditor_negotiation",
)

_FORBID_ANACHRONISM = (
    "modern_vehicles_or_firearms",
    "electronic_communications",
    "industrial_research_facility",
    "corporate_or_legal_debt",
)


def _sc(
    *,
    id: str,
    title: str,
    quick_description: str,
    icon: str,
    pitch: str,
    genre: str,
    role: str,
    tone: str,
    difficulty: str,
    world_frame: Dict[str, Any],
    starting_location: str,
    starting_pressure: str,
    key_npcs: List[Dict[str, str]],
    starting_inventory: str,
    hidden_threat: str,
    seed: str,
    mode: str = "advanced",
) -> Dict[str, Any]:
    return {
        "id": id,
        "title": title,
        "quick_description": quick_description,
        "icon": icon,
        "pitch": pitch,
        "genre": genre,
        "role": role,
        "tone": tone,
        "difficulty": difficulty,
        "mode": mode,
        "world_frame": world_frame,
        "starting_location": starting_location,
        "starting_pressure": starting_pressure,
        "key_npcs": key_npcs,
        "starting_inventory": starting_inventory,
        "hidden_threat": hidden_threat,
        "seed": seed,
    }


SCENARIOS: List[Dict[str, Any]] = [
    # ------------------------------------------------------------------ #
    # Fantasy (3)
    # ------------------------------------------------------------------ #
    _sc(
        id="oath-broken-keep",
        title="Oath-Broken Keep",
        quick_description="Hold a frontier keep after its lord vanishes with the treasury.",
        icon="shield-outline",
        pitch=(
            "The banner still flies, but the lord is gone and the storehouses are empty. "
            "Oaths hold only as long as the grain does."
        ),
        genre="fantasy",
        role="oathbound steward",
        tone="mythic",
        difficulty="standard",
        world_frame=_frame(
            era="low_fantasy_medieval",
            technology="preindustrial_steel",
            setting="frontier_keep",
            primary_pressures=["oath_and_loyalty", "supply_shortage", "border_raid_risk"],
            required_anchors=["keep_or_hall", "oath_obligation", "named_retainers"],
            forbidden_opening_frames=list(_FORBID_MODERN_DEBT)
            + ["modern_city_crime", "firearm_combat"],
        ),
        starting_location=(
            "Greywatch Keep's great hall — cold hearths, wet cloaks steaming by the door. "
            "Rain on slate. The lord's chair empty since dawn."
        ),
        starting_pressure=(
            "Captain Rhea Vale reports the east granary lock was forced overnight. "
            "A third of the winter grain is missing. The levy is due at noon."
        ),
        key_npcs=[
            {"name": "Captain Rhea Vale", "role": "garrison captain, loyal, furious", "stance": "ally"},
            {"name": "Brother Calen", "role": "chaplain who blessed the missing lord's oath", "stance": "neutral"},
            {"name": "Torren Ash", "role": "stablehand who saw riders leave before dawn", "stance": "afraid"},
        ],
        starting_inventory=(
            "Carried: steward's seal ring, short sword (serviceable), keep keys, wax tablet. "
            "Worn: wool cloak, boots. Stored hall: ledger book, three days' personal rations. Load: light."
        ),
        hidden_threat=(
            "The lord did not flee alone — a rival house paid him to abandon the keep so their "
            "raiders can claim it as 'abandoned land' within two nights. Torren was paid to stay quiet."
        ),
        seed=(
            "Open in the hall as Rhea finishes her report. Rain hammers the shutters. "
            "Introduce Rhea, Calen, and Torren in prose before any choice names them. "
            "First choices: audit the granary, question Torren, send riders, seal the gates, or convene the levy."
        ),
    ),
    _sc(
        id="relic-road-toll",
        title="Relic Road Toll",
        quick_description="Escort a sealed reliquary through a mountain pass that taxes more than coin.",
        icon="trail-sign-outline",
        pitch=(
            "The road is old, the toll is older, and the reliquary must not be opened. "
            "Something in the pass already knows you are coming."
        ),
        genre="fantasy",
        role="sworn courier",
        tone="mythic",
        difficulty="standard",
        world_frame=_frame(
            era="low_fantasy_medieval",
            technology="preindustrial_steel",
            setting="mountain_pass_road",
            primary_pressures=["escort_duty", "toll_and_ambush", "relic_taboo"],
            required_anchors=["mountain_road", "reliquary", "toll_or_gate"],
            forbidden_opening_frames=list(_FORBID_MODERN_DEBT) + ["modern_city_crime"],
        ),
        starting_location=(
            "Stone switchback above the treeline. A rope bridge spans a wind-cut gorge. "
            "The reliquary crate is lashed to a mule that will not cross."
        ),
        starting_pressure=(
            "The bridge planks ahead are missing three boards. Wind is rising. "
            "Behind you, dust on the trail means riders — or worse — are closing."
        ),
        key_npcs=[
            {"name": "Sister Miren", "role": "temple guardian of the seal, unbending", "stance": "ally"},
            {"name": "Jor the muleteer", "role": "hired hand, wants to turn back", "stance": "neutral, fearful"},
            {"name": "Pass toll-warden", "role": "unseen yet; horn already answered from the far cliff", "stance": "unknown"},
        ],
        starting_inventory=(
            "Carried: sealed letter of passage, short spear, knife, waterskin (half). "
            "Protected: iron-bound reliquary (must not open). Worn: travel cloak. Load: moderate."
        ),
        hidden_threat=(
            "The toll-warden is dead; the horn was answered by scavengers who open sealed temple cargo "
            "and sell the contents. They will demand the crate as 'toll' if you cross."
        ),
        seed=(
            "Open on the switchback with the mule refusing the bridge. Name Sister Miren and Jor in prose. "
            "Choices: repair the bridge, force the mule, scout the far side, hide the crate, or signal the horn."
        ),
    ),
    _sc(
        id="kingdom-border-curse",
        title="Kingdom Border Curse",
        quick_description="A village on the border wakes under a geas that forbids anyone from speaking the king's name.",
        icon="book-outline",
        pitch=(
            "Words fail at the border stones. Trade has stopped. Something old is rewriting the village's tongue."
        ),
        genre="fantasy",
        role="itinerant hedge-mage",
        tone="mythic",
        difficulty="hard",
        world_frame=_frame(
            era="low_fantasy_medieval",
            technology="preindustrial_with_minor_magic",
            setting="border_village",
            primary_pressures=["magical_geas", "border_politics", "village_panic"],
            required_anchors=["border_stones", "cursed_speech", "village_square"],
            forbidden_opening_frames=list(_FORBID_MODERN_DEBT) + ["modern_technology"],
        ),
        starting_location=(
            "Ashenford square at dusk. Market stalls half-packed. Villagers mouth words that will not form "
            "when they try to name the crown."
        ),
        starting_pressure=(
            "A child collapsed after saying half a royal name. Foam at the mouth. "
            "The reeve demands you fix it before the border riders arrive at first light."
        ),
        key_npcs=[
            {"name": "Reeve Halda", "role": "village head, practical, terrified", "stance": "demanding ally"},
            {"name": "Old Pem", "role": "midwife who remembers the last curse", "stance": "wary ally"},
            {"name": "Border rider scout", "role": "will arrive soon; expects taxes in the king's name", "stance": "unknown"},
        ],
        starting_inventory=(
            "Carried: charm chalk, dried herbs, iron nail, small knife, one healing draught. "
            "Worn: travel robes. Load: light."
        ),
        hidden_threat=(
            "The geas is bait — a rival mage wants the border riders to interpret silence as rebellion "
            "and burn the village as traitors."
        ),
        seed=(
            "Open in the square with the collapsed child and Halda's demand. Introduce Halda and Pem in prose. "
            "Choices: tend the child, inspect border stones, question Pem, prepare wards, or flee before riders."
        ),
    ),
    # ------------------------------------------------------------------ #
    # Post-Apocalyptic (3)
    # ------------------------------------------------------------------ #
    _sc(
        id="suburban-collapse",
        title="Suburban Collapse",
        quick_description="Keep a neighbourhood alive after the power, water, and services fail.",
        icon="home-outline",
        pitch=(
            "Power, water, and emergency services fail in a quiet neighbourhood. "
            "What breaks first — the grid, the food, or the people next door?"
        ),
        genre="post-apocalyptic",
        role="ordinary resident",
        tone="grounded, slow-burning",
        difficulty="hard",
        world_frame=_frame(
            era="near_future_collapse",
            technology="failing_modern_civilian",
            setting="suburban_street",
            primary_pressures=["resource_scarcity", "neighbour_trust", "unknown_absence"],
            required_anchors=["player_home", "neighbouring_houses", "failing_utilities"],
            forbidden_opening_frames=[
                "fantasy_magic_as_primary",
                "prehistoric_wilderness",
                "corporate_office_drama",
            ],
        ),
        starting_location=(
            "Your two-storey house on Elm Crescent, mid-suburb. Day 4 since the "
            "grid went dark. Pantry thinning. Tap water cloudy. Neighbours' lawns "
            "now scattered with bagged trash because the trucks stopped."
        ),
        starting_pressure=(
            "The Hendersons two doors down had a generator. Last night it stopped. "
            "Today their door is open and the dog is loose. Nobody has gone over."
        ),
        key_npcs=[
            {
                "name": "Marlene Cho",
                "role": "next-door neighbour, retired nurse, calm but tired",
                "stance": "ally",
            },
            {
                "name": "Greg Stahl",
                "role": "across-the-street, ex-military, watchful and territorial",
                "stance": "neutral, suspicious",
            },
            {
                "name": "The Hendersons",
                "role": "two doors down, status unknown since last night",
                "stance": "unknown",
            },
        ],
        starting_inventory=(
            "Carried: house keys, wallet (cash $80, dead cards), phone (12% battery, no signal). "
            "Stored kitchen: 4 days of pantry food, ~6L bottled water, can opener, decent knives. "
            "Stored garage: hammer, claw bar, half tank in the car, no spare fuel. "
            "Worn: clothes for the weather. Load: light."
        ),
        hidden_threat=(
            "A small group from the next neighbourhood has been quietly cataloguing which houses still have lights, "
            "smoke, or movement. They are NOT desperate yet. They are organising. When desperation lands in 3-5 days, "
            "they will arrive door-to-door, polite first, then not."
        ),
        seed=(
            "The story opens on the fourth dim morning. Outside the air is too still. "
            "Down the street, the Hendersons' generator has been silent since 2 a.m. "
            "Their dog Tucker is loose on the lawn. Introduce Marlene and Greg before choices name them. "
            "First choices: check Hendersons, fortify inventory, talk to Marlene, watch Greg, stay inside."
        ),
    ),
    _sc(
        id="ash-caravan-ambush",
        title="Ash Caravan Ambush",
        quick_description="A trade caravan stalls in grey ash while shooters wait on the ridgeline.",
        icon="bus-outline",
        pitch=(
            "Ashfall choked the road. The lead truck is dead. Something on the ridge is counting your heads."
        ),
        genre="post-apocalyptic",
        role="caravan scout",
        tone="grim",
        difficulty="hard",
        world_frame=_frame(
            era="post_collapse",
            technology="scavenged_modern",
            setting="ash_road_caravan",
            primary_pressures=["ambush_threat", "vehicle_failure", "cargo_protection"],
            required_anchors=["caravan_vehicles", "ash_terrain", "ridge_threat"],
            forbidden_opening_frames=list(_FORBID_MODERN_DEBT)[:2]
            + ["fantasy_magic_as_primary", "prehistoric_wilderness"],
        ),
        starting_location=(
            "Two cargo trucks and a pickup on a grey two-lane. Lead engine seized. "
            "Ash drifts like snow. Visibility to the ridge: maybe 200m."
        ),
        starting_pressure=(
            "A scoped glint flashed once on the ridge and did not flash again. "
            "Driver Len is under the lead truck and cannot hear you over the wind."
        ),
        key_npcs=[
            {"name": "Len Okoye", "role": "lead driver, under the chassis", "stance": "ally"},
            {"name": "Sera Quinn", "role": "cargo boss, prioritises the manifest", "stance": "ally, tense"},
            {"name": "Ridge shooters", "role": "unknown number, elevated position", "stance": "hostile"},
        ],
        starting_inventory=(
            "Carried: binoculars, bolt rifle (5 rounds), radio (weak), knife, dust mask. "
            "Worn: goggles, coat. Stored pickup: water (8L), spare belt, med kit. Load: moderate."
        ),
        hidden_threat=(
            "The ambushers want the refrigerated trailer specifically — it holds antibiotics. "
            "They will trade safe passage for it if forced; otherwise they take it by force at dusk."
        ),
        seed=(
            "Open beside the seized truck with ash in your teeth. Introduce Len and Sera in prose. "
            "Choices: free Len, glass the ridge, move cargo, reverse off the road, or signal surrender trade."
        ),
    ),
    _sc(
        id="dry-reservoir-claim",
        title="Dry Reservoir Claim",
        quick_description="A cracked reservoir still holds a last pool — and three factions know it.",
        icon="water-outline",
        pitch=(
            "Water is law. The reservoir fence is cut. Whoever fills containers first writes the rules."
        ),
        genre="post-apocalyptic",
        role="settlement runner",
        tone="grim",
        difficulty="hard",
        world_frame=_frame(
            era="post_collapse",
            technology="scavenged_modern",
            setting="drained_reservoir",
            primary_pressures=["water_scarcity", "faction_contest", "fence_breach"],
            required_anchors=["reservoir_basin", "water_containers", "competing_groups"],
            forbidden_opening_frames=["fantasy_magic_as_primary", "office_politics"],
        ),
        starting_location=(
            "Concrete basin under a white sun. A shallow pool at the deep end, green at the edges. "
            "Your handcart and jerrycans are at the access road."
        ),
        starting_pressure=(
            "A second group is already at the far stair with pumps. "
            "Your settlement's kids drink from rain barrels that run out tonight."
        ),
        key_npcs=[
            {"name": "Nia Brooks", "role": "your settlement's water lead", "stance": "ally"},
            {"name": "Cutters crew", "role": "pump team on the far stair", "stance": "rival"},
            {"name": "Fence watch kid", "role": "saw who cut the wire, too scared to speak", "stance": "afraid"},
        ],
        starting_inventory=(
            "Carried: empty jerrycans (4), hand pump, wrench, sidearm (2 rounds), cloth filters. "
            "Worn: sun hat, boots. Load: light until filled."
        ),
        hidden_threat=(
            "The pool is contaminated with agricultural runoff; untreated water will sicken a settlement "
            "in 48 hours. The Cutters know and plan to trade 'clean' water after your people get sick."
        ),
        seed=(
            "Open at the basin rim with Nia counting cans. Introduce Nia in prose; show the far-stair crew. "
            "Choices: fill fast, negotiate, test water, cut their hose, or withdraw and fortify barrels."
        ),
    ),
    # ------------------------------------------------------------------ #
    # Cosmic Horror (3)
    # ------------------------------------------------------------------ #
    _sc(
        id="cosmic-horror-road-town",
        title="Cosmic Horror Road Town",
        quick_description="Find a way out of a roadside town that remembers you before you arrived.",
        icon="eye-outline",
        pitch=(
            "Your car broke down outside Pilcrow Hollow. The motel clerk remembers you. You have never been here. "
            "The map says the highway goes east. The road goes north."
        ),
        genre="cosmic horror",
        role="passing traveller",
        tone="dread, slow unravelling, restrained",
        difficulty="standard",
        world_frame=_frame(
            era="contemporary",
            technology="modern_civilian",
            setting="roadside_town",
            primary_pressures=["identity_unravelling", "spatial_wrongness", "town_complicity"],
            required_anchors=["broken_car_or_road", "motel_or_main_street", "false_familiarity"],
            forbidden_opening_frames=list(_FORBID_MODERN_DEBT)
            + ["dinosaur_predators", "military_campaign"],
        ),
        starting_location=(
            "Pilcrow Hollow, population sign blistered. Single main street, one motel ('Hollow Rest'), one diner "
            "('Mercer's'), a gas station with a closed sign that was open ten minutes ago."
        ),
        starting_pressure=(
            "The motel clerk, Edith, greets the player by their first name and asks 'how was the drive back?'. "
            "She gives them room 7 without taking ID. Room 7 has the player's open suitcase on the bed, half-unpacked."
        ),
        key_npcs=[
            {
                "name": "Edith (motel clerk)",
                "role": "knows the player, mid-60s, calm, smells faintly of wet stone",
                "stance": "unknown — too friendly",
            },
            {
                "name": "Sheriff Voss",
                "role": "tall, polite, asks about the player's 'cousin'",
                "stance": "unknown — watching",
            },
            {
                "name": "The diner regulars",
                "role": "five locals who all stand up and leave when the player enters",
                "stance": "afraid",
            },
        ],
        starting_inventory=(
            "Carried: car keys (car won't start), wallet, phone (no signal, one extra photo of an unknown place), "
            "road atlas (route through Pilcrow Hollow not printed). Worn: travel clothes. Load: light."
        ),
        hidden_threat=(
            "The town remembers visitors who have not yet arrived and forgets the ones who leave. Under the "
            "Methodist church is a soft place in the world. Guests who stay three nights become locals."
        ),
        seed=(
            "Open at dusk on the gas station apron. Car ticking as it cools. A woman at Hollow Rest waves like "
            "she has been waiting. Introduce Edith before choices name her. "
            "Choices: gas station, motel, diner, try the car, walk the road out."
        ),
    ),
    _sc(
        id="lighthouse-signal-loop",
        title="Lighthouse Signal Loop",
        quick_description="A coastal light flashes a pattern that matches your childhood nickname.",
        icon="flashlight-outline",
        pitch=(
            "The mainland ferry cancelled. The lighthouse keeps a schedule no chart lists. "
            "Tonight it is calling you by a name you buried."
        ),
        genre="cosmic horror",
        role="relief keeper",
        tone="bleak",
        difficulty="hard",
        world_frame=_frame(
            era="contemporary",
            technology="modern_with_failing_radio",
            setting="offshore_lighthouse",
            primary_pressures=["isolation", "signal_anomaly", "identity_erosion"],
            required_anchors=["lighthouse", "sea_isolation", "anomalous_signal"],
            forbidden_opening_frames=list(_FORBID_MODERN_DEBT) + ["urban_gang_war"],
        ),
        starting_location=(
            "Spiral stair and lamp room of Blackreed Light. Salt on every surface. "
            "Radio desk shows the ferry is 'indefinitely delayed'."
        ),
        starting_pressure=(
            "The lamp just completed a flash sequence that spells a private nickname only one living person knew. "
            "That person drowned twelve years ago."
        ),
        key_npcs=[
            {"name": "Harbour radio (Cole)", "role": "mainland voice, insists you stay on rotation", "stance": "ally?"},
            {"name": "Previous keeper's log", "role": "handwriting that begins to match yours", "stance": "unknown"},
            {"name": "Something on the rocks", "role": "moves only when the lamp is dark", "stance": "hostile/unknown"},
        ],
        starting_inventory=(
            "Carried: key ring, flashlight, thermos, pocket knife. "
            "Station: spare lamp mantle, flare gun (1), logbooks, three days of tinned food. Load: light."
        ),
        hidden_threat=(
            "Each correct reply to the pattern overwrites a personal memory. After seven exchanges the keeper "
            "becomes the light's next permanent occupant — Cole already knows and is delaying the ferry."
        ),
        seed=(
            "Open in the lamp room as the pattern finishes. Salt air, radio hiss. "
            "Do not invent mainland visitors. Choices: log the pattern, radio Cole, douse the lamp, "
            "search the rocks with a light, reread the previous keeper's log."
        ),
    ),
    _sc(
        id="library-that-rewrites",
        title="Library That Rewrites",
        quick_description="A closed special collection edits the books while you read them — and then edits you.",
        icon="library-outline",
        pitch=(
            "After hours, the reading room still has one light on. The catalogue lists a book with your name as author."
        ),
        genre="cosmic horror",
        role="night archivist",
        tone="bleak",
        difficulty="standard",
        world_frame=_frame(
            era="contemporary",
            technology="modern_civilian",
            setting="closed_library",
            primary_pressures=["textual_reality_shift", "isolation", "identity_rewrite"],
            required_anchors=["library_interior", "catalog_or_book", "after_hours"],
            forbidden_opening_frames=list(_FORBID_MODERN_DEBT) + ["open_warfare"],
        ),
        starting_location=(
            "Special Collections reading room, third floor. One desk lamp. Stacks in shadow. "
            "Street noise from below sounds a half-second late."
        ),
        starting_pressure=(
            "The call slip in your pocket now requests a volume titled with your full legal name. "
            "You did not fill that slip out."
        ),
        key_npcs=[
            {"name": "Ms. Orth", "role": "head librarian, left 'for an hour' three hours ago", "stance": "unknown"},
            {"name": "Night security (Ray)", "role": "camera loop shows him still in the lobby", "stance": "ally?"},
            {"name": "The catalogue terminal", "role": "updates entries without keystrokes", "stance": "hostile/unknown"},
        ],
        starting_inventory=(
            "Carried: staff badge, keys to stacks, phone (no signal indoors), pencil, notebook. "
            "Desk: desk lamp, gloves, acid-free paper. Load: light."
        ),
        hidden_threat=(
            "Reading any sentence that contains your name transfers a memory into the collection. "
            "The library is completing an author-entry and will lock the building when the entry is whole."
        ),
        seed=(
            "Open at the lit desk with the altered call slip. Footsteps in a stack that should be locked. "
            "Introduce Orth only if she appears; otherwise keep her absent. "
            "Choices: find the volume, call Ray, leave via fire stair, photograph the slip, shut the lamp."
        ),
    ),
    # ------------------------------------------------------------------ #
    # Detective / Noir (3)
    # ------------------------------------------------------------------ #
    _sc(
        id="rain-district-alibi",
        title="Rain District Alibi",
        quick_description="A client paid cash for an alibi that is already falling apart in the rain.",
        icon="umbrella-outline",
        pitch=(
            "Someone is dead in the canal district. Your client swears they were with you. "
            "Your own notes disagree."
        ),
        genre="detective",
        role="private investigator",
        tone="grounded",
        difficulty="standard",
        world_frame=_frame(
            era="contemporary_noir",
            technology="modern_civilian",
            setting="rainy_city_district",
            primary_pressures=["murder_clock", "false_alibi", "client_pressure"],
            required_anchors=["detective_office_or_street", "client", "crime_timeline"],
            forbidden_opening_frames=["fantasy_magic_as_primary", "prehistoric_wilderness"],
        ),
        starting_location=(
            "Your walk-up office above a shuttered pawn shop. Rain on the fire escape. "
            "A manila envelope of cash on the desk, still damp."
        ),
        starting_pressure=(
            "Detective Serra called: a body matching your client's description of 'the problem' "
            "was pulled from Canal Street twenty minutes ago. She wants you downtown now."
        ),
        key_npcs=[
            {"name": "Client Rourke", "role": "paid for silence, missing since noon", "stance": "unknown"},
            {"name": "Detective Serra", "role": "homicide, not your friend, not yet enemy", "stance": "authority"},
            {"name": "Lila the bartender", "role": "saw Rourke at 9pm — or swears she did", "stance": "witness"},
        ],
        starting_inventory=(
            "Carried: notebook, pen, phone, pocket .38 (unloaded in desk unless you take it), office keys. "
            "Envelope: $2,000 cash. Worn: coat, hat. Load: light."
        ),
        hidden_threat=(
            "Rourke is framing you as the shooter; the cash envelope has your prints and his blood on an inner bill."
        ),
        seed=(
            "Open in the office with Serra's call still buzzing. Rain, damp cash, empty client chair. "
            "Introduce Serra by voice first. Choices: go downtown, find Lila, hunt Rourke, hide the cash, arm yourself."
        ),
    ),
    _sc(
        id="warehouse-shift-murder",
        title="Warehouse Shift Murder",
        quick_description="Third shift found a body between the pallets. Everyone still clocked in.",
        icon="cube-outline",
        pitch=(
            "The loading bay cameras glitched for four minutes. When they returned, a supervisor was dead "
            "and the manifest no longer matched the crates."
        ),
        genre="detective",
        role="insurance investigator",
        tone="grounded",
        difficulty="standard",
        world_frame=_frame(
            era="contemporary_noir",
            technology="modern_industrial",
            setting="night_warehouse",
            primary_pressures=["locked_scene", "crew_lies", "cargo_discrepancy"],
            required_anchors=["warehouse_floor", "body_or_crime_scene", "shift_crew"],
            forbidden_opening_frames=["fantasy_magic_as_primary", "open_military_battle"],
        ),
        starting_location=(
            "Bay 6, refrigerated warehouse. Condensation fog. Yellow tape nobody respects. "
            "Forklift still idling."
        ),
        starting_pressure=(
            "Shift lead Dana wants the floor cleared for the 4 a.m. truck. "
            "The dead supervisor's tablet is missing. Your firm loses the policy if the truck leaves sealed."
        ),
        key_npcs=[
            {"name": "Dana Ruiz", "role": "shift lead, pushing schedule", "stance": "obstructive"},
            {"name": "Marco Pell", "role": "forklift driver, first to 'find' the body", "stance": "suspect"},
            {"name": "Patrol officer Keene", "role": "first responder, bored and cold", "stance": "authority"},
        ],
        starting_inventory=(
            "Carried: company badge, camera phone, evidence gloves, notepad, flashlight. "
            "Car outside: thermos, spare batteries. Load: light."
        ),
        hidden_threat=(
            "Crates marked produce hold diverted pharma. The supervisor was going to report it; "
            "Dana needs the truck gone before counts finish."
        ),
        seed=(
            "Open on Bay 6 with the body covered and Dana talking over you. Introduce Dana and Marco in prose. "
            "Choices: delay the truck, interview Marco, pull camera logs, search crates, call your firm."
        ),
    ),
    _sc(
        id="jazz-club-blackmail",
        title="Jazz Club Blackmail",
        quick_description="A singer's dressing room holds photos that could burn three powerful names.",
        icon="musical-notes-outline",
        pitch=(
            "The set is starting. The envelope arrived at intermission. "
            "If the photos go public at midnight, the city changes hands."
        ),
        genre="detective",
        role="fixer",
        tone="grounded",
        difficulty="hard",
        world_frame=_frame(
            era="contemporary_noir",
            technology="modern_civilian",
            setting="nightclub_backstage",
            primary_pressures=["blackmail_deadline", "reputation_leverage", "club_politics"],
            required_anchors=["jazz_club", "blackmail_material", "midnight_clock"],
            forbidden_opening_frames=["fantasy_magic_as_primary", "wilderness_survival"],
        ),
        starting_location=(
            "Back corridor of the Velvet Frequency. Brass and smoke. Dressing room 2 door cracked. "
            "Bass line throbbing through the wall."
        ),
        starting_pressure=(
            "Singer Ivy Quinn is due on stage in twelve minutes and will not go on until the envelope is 'handled'. "
            "A second copy may already be with a gossip columnist."
        ),
        key_npcs=[
            {"name": "Ivy Quinn", "role": "headliner, terrified and sharp", "stance": "client"},
            {"name": "Club owner Drex", "role": "wants the show to run, hates cops", "stance": "neutral pressure"},
            {"name": "Columnist Vane", "role": "may have the second copy", "stance": "threat"},
        ],
        starting_inventory=(
            "Carried: phone, cash roll, lockpick set, club guest pass. "
            "Envelope: polaroids and a typed midnight deadline. Load: light."
        ),
        hidden_threat=(
            "Ivy took the photos herself as insurance; the blackmailer is her estranged partner using her as bait "
            "to pull you into a frame for the mayor's aide."
        ),
        seed=(
            "Open in the corridor with music and the cracked dressing-room door. Introduce Ivy in prose. "
            "Choices: calm Ivy, find Drex, chase Vane, destroy photos, search for the second copy."
        ),
    ),
    # ------------------------------------------------------------------ #
    # Prehistoric Survival — literal prehistoric (3). NOT modern containment.
    # ------------------------------------------------------------------ #
    _sc(
        id="flint-band-stalked",
        title="Flint Band Stalked",
        quick_description="Your hunting band is being followed by something that hunts like a person and eats like a beast.",
        icon="leaf-outline",
        pitch=(
            "The mammoth trail turned wrong. Prints that were not yours appeared beside the river. "
            "The children are already tired."
        ),
        genre="prehistoric survival",
        role="hunt leader",
        tone="tense, sweat-and-rain procedural",
        difficulty="brutal",
        world_frame=_frame(
            era="upper_paleolithic",
            technology="lithic_and_bone",
            setting="river_valley_wilderness",
            primary_pressures=["predator_stalking", "band_survival", "terrain_and_weather"],
            required_anchors=["band_or_camp", "stone_tools", "wilderness_threat"],
            forbidden_opening_frames=list(_FORBID_MODERN_DEBT)
            + list(_FORBID_ANACHRONISM)
            + ["research_facility", "firearms", "radio_communications"],
        ),
        starting_location=(
            "Willow-choked bend of a cold river at dusk. Smoke from a low fire. "
            "Hide lean-tos half-built. Wet flint chips on a hide mat."
        ),
        starting_pressure=(
            "Scout Tova found prints with claw marks too wide for wolf, too careful for bear — "
            "and they circle the camp twice. The meat rack is empty though nobody admits taking from it."
        ),
        key_npcs=[
            {"name": "Tova", "role": "scout, best tracker, shaken", "stance": "ally"},
            {"name": "Old Sarn", "role": "elder, insists on moving camp now", "stance": "ally, urgent"},
            {"name": "The stalker", "role": "unseen predator with patient circuits", "stance": "hostile"},
        ],
        starting_inventory=(
            "Carried: thrusting spear, flint knife, fire-kit (ember in horn), gut cord. "
            "Camp: two hide shelters, dried fish (1 day for the band), water skins. Load: light."
        ),
        hidden_threat=(
            "The stalker is a wounded cave lion pushed from its range by a larger pride; "
            "fire will delay it once. After that it targets the slowest child unless given a carcass."
        ),
        seed=(
            "Open at the river camp with wet prints in the mud and Tova speaking low. "
            "No metal, no radios, no buildings of stone industry. Introduce Tova and Sarn in prose. "
            "Choices: move camp, set spear pits, tend the fire, search the meat rack, send scouts."
        ),
    ),
    _sc(
        id="river-ice-calving",
        title="River Ice Calving",
        quick_description="Spring ice breaks under the migration path while a rival band holds the only ford.",
        icon="snow-outline",
        pitch=(
            "The ice talks and splits. Behind you, empty bellies. Ahead, another band's spears at the ford."
        ),
        genre="prehistoric survival",
        role="migration guide",
        tone="tense, sweat-and-rain procedural",
        difficulty="brutal",
        world_frame=_frame(
            era="late_glacial",
            technology="lithic_and_bone",
            setting="breaking_river_ice",
            primary_pressures=["ice_collapse", "rival_band", "starvation_clock"],
            required_anchors=["ice_or_river", "migration_band", "ford_or_crossing"],
            forbidden_opening_frames=list(_FORBID_MODERN_DEBT)
            + list(_FORBID_ANACHRONISM)
            + ["research_facility", "firearms"],
        ),
        starting_location=(
            "Wide frozen river under a white sky. Dark seams where water shows. "
            "Your band's travois and hide bundles wait on the near bank."
        ),
        starting_pressure=(
            "A sheet calved ten paces ahead of the lead walker. "
            "Across the river, rival spears are planted — they will allow crossing for half your dried meat."
        ),
        key_npcs=[
            {"name": "Kesh", "role": "your sibling, injured ankle, cannot run", "stance": "ally, dependent"},
            {"name": "Vara of the far bank", "role": "rival band speaker", "stance": "rival"},
            {"name": "Child Ren", "role": "carries the fire-horn, terrified of the ice", "stance": "ally"},
        ],
        starting_inventory=(
            "Carried: spear, antler pick, hide rope, fire-horn ember. "
            "Band stores: dried meat (2 days if shared thrifty), furs, one spare spear. Load: moderate."
        ),
        hidden_threat=(
            "Vara's band already weakened the ice near the 'safe' path; they want your people forced into "
            "the toll or into the water."
        ),
        seed=(
            "Open on the near bank with the ice cracking and rival spears visible. "
            "Introduce Kesh and name Vara only when seen/heard. No modern gear. "
            "Choices: test ice, negotiate meat, find another crossing, threaten, tend Kesh."
        ),
    ),
    _sc(
        id="tar-pit-foraging",
        title="Tar Pit Foraging",
        quick_description="A tar seep traps game — and people — while poison fumes thicken at noon.",
        icon="flame-outline",
        pitch=(
            "Meat stands in the black seep screaming. Rescue means rope and courage. Waiting means free food and a curse."
        ),
        genre="prehistoric survival",
        role="forager",
        tone="tense, sweat-and-rain procedural",
        difficulty="hard",
        world_frame=_frame(
            era="pleistocene_forager",
            technology="lithic_and_bone",
            setting="tar_seep_basin",
            primary_pressures=["toxic_fumes", "trapped_game_or_person", "heat_and_time"],
            required_anchors=["tar_seep", "foraging_party", "rope_or_poles"],
            forbidden_opening_frames=list(_FORBID_MODERN_DEBT)
            + list(_FORBID_ANACHRONISM)
            + ["research_facility", "firearms", "vehicles"],
        ),
        starting_location=(
            "Sun-baked basin where black tar seeps through cracked earth. "
            "Heat shimmer. Bones of old kills ring the edge like a warning."
        ),
        starting_pressure=(
            "A juvenile ground sloth is stuck to mid-flank and still thrashing. "
            "Your cousin Bram went out with a pole and is now also stuck to the knee. Fumes make eyes water."
        ),
        key_npcs=[
            {"name": "Bram", "role": "cousin, stuck in tar to the knee", "stance": "ally, helpless"},
            {"name": "Ylla", "role": "forager who wants the meat not the risk", "stance": "ally, conflicting"},
            {"name": "The seep", "role": "heat and fumes worsen toward midday", "stance": "environment hostile"},
        ],
        starting_inventory=(
            "Carried: flint knife, digging stick, gut rope (short), water skin (low). "
            "Party: two longer poles, empty meat sling. Load: light."
        ),
        hidden_threat=(
            "Predators have learned the seep is a free kill site; a pack will arrive when the thrashing stops. "
            "Staying to butcher guarantees a fight."
        ),
        seed=(
            "Open at the seep edge with Bram shouting and the sloth thrashing. "
            "Introduce Bram and Ylla in prose. Strictly prehistoric tools only. "
            "Choices: pull Bram, kill the sloth, leave both, build a pole bridge, retreat for more rope."
        ),
    ),
    # ------------------------------------------------------------------ #
    # Modern containment — available, NOT in Prehistoric Survival Quick pool
    # ------------------------------------------------------------------ #
    _sc(
        id="dinosaur-containment-breach",
        title="Dinosaur Containment Breach",
        quick_description="Escape a flooded research site while two predators hunt through the breach.",
        icon="paw-outline",
        pitch=(
            "A remote research facility loses containment. You have a rifle with three rounds, a flashlight that "
            "matters more than the rifle, and tracks already cutting across the access road."
        ),
        genre="modern containment",
        role="junior containment technician",
        tone="tense, sweat-and-rain procedural",
        difficulty="brutal",
        world_frame=_frame(
            era="modern_research_containment",
            technology="modern_industrial",
            setting="remote_research_compound",
            primary_pressures=[
                "escaped_predators",
                "injury_and_evacuation",
                "containment_failure",
                "terrain_and_weather",
            ],
            required_anchors=[
                "research_site_or_containment_structure",
                "predator_threat",
                "survival_tools",
            ],
            forbidden_opening_frames=list(_FORBID_MODERN_DEBT),
        ),
        starting_location=(
            "Substation 4 of the Mainland Site B compound — a humid riverside concrete bunker. Power flickering. "
            "The eastern paddock fence is down across two sections. Visibility 40m through wet ferns."
        ),
        starting_pressure=(
            "Dr. Aris Kemal is bleeding from a thigh wound in the substation and cannot run. "
            "The radio's last broadcast 14 minutes ago said the medical team's jeep has not arrived."
        ),
        key_npcs=[
            {
                "name": "Dr. Aris Kemal",
                "role": "senior ranger, leg torn open, lucid but fading",
                "stance": "ally, helpless",
            },
            {
                "name": "Site B radio (Maren)",
                "role": "voice-only from main hub, panicking, status unclear",
                "stance": "ally",
            },
            {
                "name": "The breach",
                "role": "at least one large theropod, possibly two; tracks suggest hunting pair",
                "stance": "hostile",
            },
        ],
        starting_inventory=(
            "Carried: bolt-action rifle (3 rounds, ok condition), heavy torch (8 hours of light, harsh beam), "
            "radio handset (working, intermittent), tranquiliser pistol (1 dart, slow onset), pocket knife. "
            "Worn: wet jacket, hiking boots. Stored substation: med kit (basic), water (2L), first-aid stretcher, "
            "emergency flare (1). Load: manageable."
        ),
        hidden_threat=(
            "There are TWO theropods, not one. The second is downwind and silent. It is using the rain to mask its "
            "approach and is currently between the substation and the medical team's stalled jeep. "
            "Any loud action (rifle shot, flare) will pull both onto the player within 1-2 turns."
        ),
        seed=(
            "The story opens in the substation. Rain hammers the metal roof. Dr. Kemal is propped against the "
            "generator housing, his thigh wrapped in a torn shirt that is already dark. The flashlight beam falls on "
            "three-toed tracks crossing the concrete floor, water still pooling in them. The radio whispers static "
            "and then Maren's voice for one fractured sentence before it cuts out. The first choice should include "
            "staying with Kemal, going for the medical jeep, climbing to the substation roof for visibility, "
            "trying to repair the fence (impossible alone but tempting), or using the tranquiliser dart."
        ),
    ),
    # ------------------------------------------------------------------ #
    # Horror (3)
    # ------------------------------------------------------------------ #
    _sc(
        id="farmhouse-false-safety",
        title="Farmhouse False Safety",
        quick_description="A dark-road farmhouse offers shelter that feels rehearsed.",
        icon="moon-outline",
        pitch=(
            "The storm forced you off the road. The family inside already set a fourth place at the table."
        ),
        genre="horror",
        role="stranded traveller",
        tone="grim",
        difficulty="hard",
        world_frame=_frame(
            era="contemporary_rural",
            technology="modern_civilian",
            setting="isolated_farmhouse",
            primary_pressures=["isolation", "false_hospitality", "storm_trap"],
            required_anchors=["farmhouse", "host_family", "storm_or_night"],
            forbidden_opening_frames=["office_comedy", "open_battlefield"],
        ),
        starting_location=(
            "Mudroom of a two-storey farmhouse. Generator hum. Oil lamps. "
            "Rain hammering tin roof. Your car is stuck at the end of the drive."
        ),
        starting_pressure=(
            "Host Ruth pours coffee and asks how long you have been 'coming back here'. "
            "You have never been here. A fourth plate steams on the table."
        ),
        key_npcs=[
            {"name": "Ruth", "role": "host, warm voice, wrong questions", "stance": "unknown"},
            {"name": "Cal", "role": "adult son, watches exits", "stance": "threatening"},
            {"name": "The cellar door", "role": "padlocked from this side, scratches on the other", "stance": "unknown"},
        ],
        starting_inventory=(
            "Carried: car keys, phone (1 bar then none), pocket knife, wet wallet. "
            "Car (unreachable in storm): overnight bag. Load: light."
        ),
        hidden_threat=(
            "The family collects travellers to replace a dead sibling; the cellar holds the last guest. "
            "They act before dawn when the generator is refuelled outside."
        ),
        seed=(
            "Open in the mudroom with Ruth's wrong familiarity and the fourth plate. Introduce Ruth and Cal. "
            "Choices: play along, ask about the plate, check the cellar, go back to the car, excuse to the bathroom."
        ),
    ),
    _sc(
        id="mine-elevator-stuck",
        title="Mine Elevator Stuck",
        quick_description="A tourist mine elevator stops between levels. Something knocks from below.",
        icon="alert-circle-outline",
        pitch=(
            "The guide's radio dies. The cage will not rise. Knocking answers from a sealed drift that is not on the map."
        ),
        genre="horror",
        role="tour visitor",
        tone="grim",
        difficulty="hard",
        world_frame=_frame(
            era="contemporary",
            technology="modern_industrial_aging",
            setting="mine_elevator_shaft",
            primary_pressures=["confinement", "unknown_below", "failing_systems"],
            required_anchors=["elevator_cage", "mine_shaft", "group_of_people"],
            forbidden_opening_frames=["sunny_comedy", "space_opera"],
        ),
        starting_location=(
            "Steel cage elevator between Level 2 and 3. Bare bulb flicker. "
            "Rock walls wet. Six strangers and one guide packed close."
        ),
        starting_pressure=(
            "Guide Pat cannot raise surface. From below: three slow knocks, pause, three again — "
            "answering a pattern someone in the cage just hummed without thinking."
        ),
        key_npcs=[
            {"name": "Pat", "role": "mine guide, trying to stay professional", "stance": "ally"},
            {"name": "Nora", "role": "tourist who hummed the knock pattern", "stance": "afraid"},
            {"name": "Something below", "role": "knocks; wants the cage lowered", "stance": "hostile/unknown"},
        ],
        starting_inventory=(
            "Carried: phone flashlight, ticket stub, small water bottle. "
            "Cage: emergency crank (stiff), first-aid pouch, guide's dead radio. Load: light."
        ),
        hidden_threat=(
            "A sealed 1920s collapse trapped miners whose remains were never recovered; "
            "the mine company knows and keeps the lower gate welded. Lowering the cage frees them into Level 2."
        ),
        seed=(
            "Open in the stuck cage with bulb flicker and knocks from below. Introduce Pat and Nora. "
            "Choices: crank up, crank down, keep silent, search the cage, force the side hatch."
        ),
    ),
    _sc(
        id="fog-boarding-house",
        title="Fog Boarding House",
        quick_description="Guests who check out are still heard walking upstairs.",
        icon="bed-outline",
        pitch=(
            "The fog never lifts from this coastal street. Your room key opens two doors. "
            "One of them is already occupied by your handwriting."
        ),
        genre="horror",
        role="new boarder",
        tone="grim",
        difficulty="standard",
        world_frame=_frame(
            era="contemporary_coastal",
            technology="modern_civilian",
            setting="boarding_house",
            primary_pressures=["fog_isolation", "identity_double", "house_rules"],
            required_anchors=["boarding_house", "fog", "room_key"],
            forbidden_opening_frames=["military_campaign", "space_travel"],
        ),
        starting_location=(
            "Narrow lobby of the Harrow Boarding House. Bell on the desk. "
            "Fog pressed against the glass like a face."
        ),
        starting_pressure=(
            "Landlady Mrs. Grell hands you key 3B and says 'you left your notebook last stay'. "
            "Inside 3B the notebook is open to today's date in your handwriting."
        ),
        key_npcs=[
            {"name": "Mrs. Grell", "role": "landlady, insists on house curfew", "stance": "unknown"},
            {"name": "Boarder in 3A", "role": "coughs in a rhythm that matches footsteps above", "stance": "unknown"},
            {"name": "The upstairs walker", "role": "heard after checkout hours", "stance": "hostile/unknown"},
        ],
        starting_inventory=(
            "Carried: suitcase (half-unpacked already?), phone, wallet, room key 3B. "
            "Room: notebook with today's date filled. Load: light."
        ),
        hidden_threat=(
            "The house keeps a copy of each guest; after three nights the copy leaves and the original stays forever. "
            "Mrs. Grell is a copy who believes she is the original."
        ),
        seed=(
            "Open in the lobby with fog on the glass and Mrs. Grell's wrong memory. Introduce her in prose. "
            "Choices: go to 3B, confront Grell, check 3A, leave into fog, read the notebook."
        ),
    ),
    # ------------------------------------------------------------------ #
    # Urban Crime (3)
    # ------------------------------------------------------------------ #
    _sc(
        id="dockside-cut",
        title="Dockside Cut",
        quick_description="A pier meet goes wrong when the package is lighter than promised.",
        icon="boat-outline",
        pitch=(
            "Foghorns and diesel. The buyer is early. The scale is honest. The weight is not."
        ),
        genre="urban crime",
        role="courier",
        tone="grounded",
        difficulty="standard",
        world_frame=_frame(
            era="contemporary_urban",
            technology="modern_civilian",
            setting="industrial_docks",
            primary_pressures=["bad_hand_off", "violence_risk", "loyalty_test"],
            required_anchors=["dock_or_pier", "package", "buyer_or_crew"],
            forbidden_opening_frames=["fantasy_magic_as_primary", "prehistoric_wilderness"],
        ),
        starting_location=(
            "Pier 9, night. Stacked containers. One working floodlight. "
            "Your van idles with the side door cracked."
        ),
        starting_pressure=(
            "Buyer Costa opens the duffel, checks the scale, and says you are twenty percent light. "
            "His two men step wider without raising guns — yet."
        ),
        key_npcs=[
            {"name": "Costa", "role": "buyer, calm, lethal reputation", "stance": "threat"},
            {"name": "Jules", "role": "your lookout on the roof, radio silent", "stance": "ally?"},
            {"name": "Dock watchman", "role": "paid to look away; may have skimmed", "stance": "suspect"},
        ],
        starting_inventory=(
            "Carried: phone, burner radio, pocket knife, van keys, cash envelope for Jules. "
            "Duffel: product short by feel. Load: moderate."
        ),
        hidden_threat=(
            "Jules already sold the missing weight and tipped Costa to test whether you fold. "
            "If you name Jules, Costa kills you as unreliable; if you eat the loss, Jules owns you."
        ),
        seed=(
            "Open on Pier 9 with Costa at the scale. Introduce Costa in prose. Jules is radio-silent. "
            "Choices: bluff, offer make-good, stall, call Jules, run for the van."
        ),
    ),
    _sc(
        id="rooftop-debt-run",
        title="Rooftop Debt Run",
        quick_description="You have until sunrise to move a debt marker across three rooftops without being seen.",
        icon="business-outline",
        pitch=(
            "The marker is a USB and a name. Street-level is owned. The roofs are almost free."
        ),
        genre="urban crime",
        role="runner",
        tone="grounded",
        difficulty="hard",
        world_frame=_frame(
            era="contemporary_urban",
            technology="modern_civilian",
            setting="city_rooftops",
            primary_pressures=["time_deadline", "pursuit", "delivery_obligation"],
            required_anchors=["rooftops", "debt_marker", "sunrise_deadline"],
            forbidden_opening_frames=["fantasy_magic_as_primary", "wilderness_survival"],
        ),
        starting_location=(
            "Tar roof above a closed laundromat. City hum. Neon bleed. "
            "Gap to the next building is jumpable if you do not hesitate."
        ),
        starting_pressure=(
            "Your phone shows 4:12 a.m. Drop is a red door three blocks east at roof level. "
            "Sirens two streets over — maybe unrelated, maybe not."
        ),
        key_npcs=[
            {"name": "Handler Min", "role": "texts only; expects proof photo at drop", "stance": "employer"},
            {"name": "Rival runner Paz", "role": "wants the same marker", "stance": "rival"},
            {"name": "Roof gardener", "role": "old man who saw you land", "stance": "witness"},
        ],
        starting_inventory=(
            "Carried: USB marker, phone, gloves, small pry bar, energy gel. "
            "Worn: dark clothes, soft shoes. Load: light."
        ),
        hidden_threat=(
            "The USB contains evidence against Min; the drop is a setup to photograph you holding it "
            "for blackmail. Paz has been paid to ensure you arrive."
        ),
        seed=(
            "Open on the laundromat roof with the phone clock and the jump gap ahead. "
            "Min exists as texts until seen. Choices: jump, find stairs, hide, message Min, double back."
        ),
    ),
    _sc(
        id="precinct-leak",
        title="Precinct Leak",
        quick_description="Someone inside the precinct is selling case files. You need the name before roll call.",
        icon="document-text-outline",
        pitch=(
            "A reporter has pages that should never leave the building. "
            "Internal Affairs is already in the parking lot."
        ),
        genre="urban crime",
        role="detective",
        tone="grounded",
        difficulty="standard",
        world_frame=_frame(
            era="contemporary_urban",
            technology="modern_civilian",
            setting="police_precinct",
            primary_pressures=["internal_betrayal", "ia_pressure", "case_integrity"],
            required_anchors=["precinct", "leaked_files", "deadline_roll_call"],
            forbidden_opening_frames=["fantasy_magic_as_primary", "prehistoric_wilderness"],
        ),
        starting_location=(
            "Bullpen at 6:40 a.m. Coffee burnt. Printer still warm. "
            "Your desk drawer lock has fresh scratches."
        ),
        starting_pressure=(
            "IA Captain Holt wants a private word before 7:00 roll call. "
            "A reporter's blog draft open on a shared terminal lists your open case number."
        ),
        key_npcs=[
            {"name": "Captain Holt", "role": "Internal Affairs", "stance": "authority pressure"},
            {"name": "Partner Dell", "role": "your partner, too helpful this morning", "stance": "suspect/ally"},
            {"name": "Clerk Rios", "role": "records access after hours", "stance": "suspect"},
        ],
        starting_inventory=(
            "Carried: badge, service weapon (holstered), phone, desk keys, notepad. "
            "Desk: case binder, coffee. Load: light."
        ),
        hidden_threat=(
            "Dell is the leak under blackmail; Holt already knows and is using you to flush Dell's handler."
        ),
        seed=(
            "Open at your desk with scratched lock and the blog draft. Introduce Holt when he approaches. "
            "Choices: meet Holt, confront Dell, pull camera logs, wipe the terminal, tip the reporter."
        ),
    ),
    # ------------------------------------------------------------------ #
    # War & Attrition (3)
    # ------------------------------------------------------------------ #
    _sc(
        id="trench-supply-gap",
        title="Trench Supply Gap",
        quick_description="A trench section is low on shells and high on wounded while the wire still holds.",
        icon="flag-outline",
        pitch=(
            "Mud, wire, and a schedule of bombardments that no longer matches your maps. "
            "The runner is late with the only working radio battery."
        ),
        genre="war survival",
        role="section leader",
        tone="grim",
        difficulty="hard",
        world_frame=_frame(
            era="early_20c_trench_war",
            technology="early_industrial_military",
            setting="forward_trench",
            primary_pressures=["supply_shortage", "bombardment_schedule", "casualty_care"],
            required_anchors=["trench", "unit_orders", "enemy_line"],
            forbidden_opening_frames=["modern_office", "fantasy_magic_as_primary", "peacetime_crime"],
        ),
        starting_location=(
            "Forward trench bay under a grey dawn. Duckboards half-sunk. "
            "Periscope notch muddy. Smell of cordite and wet wool."
        ),
        starting_pressure=(
            "Sergeant Moira reports six shells left for the trench mortar. "
            "Medics need a stretch of quiet to move two stretchers to the aid post — quiet you cannot promise."
        ),
        key_npcs=[
            {"name": "Sergeant Moira", "role": "NCO, blunt, competent", "stance": "ally"},
            {"name": "Private Hens", "role": "wounded, can still carry a message", "stance": "ally, fragile"},
            {"name": "Enemy wire line", "role": "occasional sniper fire", "stance": "hostile"},
        ],
        starting_inventory=(
            "Carried: service rifle, whistle, map case (outdated), field dressing. "
            "Bay stores: six mortar shells, two stretchers, foul water. Load: combat."
        ),
        hidden_threat=(
            "Command already wrote this section as expendable diversion; the 'quiet' you were promised is a feint "
            "and the real barrage lands on your bay in under an hour."
        ),
        seed=(
            "Open in the trench bay with Moira's shell count and stretchers waiting. Introduce Moira and Hens. "
            "Choices: hold fire, send Hens back, re-aim mortar, dig in, request relief you will not get."
        ),
    ),
    _sc(
        id="convoy-bridge-hold",
        title="Convoy Bridge Hold",
        quick_description="A timber bridge must stay up for one more convoy — demolitions are already wired.",
        icon="git-commit-outline",
        pitch=(
            "Engineers say the charges are live. Command says the fuel trucks still have to cross. "
            "Enemy scouts are in the tree line."
        ),
        genre="war survival",
        role="bridge security NCO",
        tone="grim",
        difficulty="hard",
        world_frame=_frame(
            era="mid_20c_war",
            technology="industrial_military",
            setting="river_bridge",
            primary_pressures=["bridge_integrity", "convoy_schedule", "enemy_scouts"],
            required_anchors=["bridge", "demolition_charges", "convoy_or_road"],
            forbidden_opening_frames=["peacetime_suburb", "fantasy_magic_as_primary"],
        ),
        starting_location=(
            "Timber and steel bridge over a fast brown river. Sandbags at both ends. "
            "Wire leads run to a blasting machine under a tarp."
        ),
        starting_pressure=(
            "Engineer Lenz wants authority to blow if scouts reach the near bank. "
            "Convoy ETA is twelve minutes. Smoke already rises from the far tree line."
        ),
        key_npcs=[
            {"name": "Engineer Lenz", "role": "demo specialist, finger near the crank", "stance": "ally, conflicted"},
            {"name": "Driver Colm", "role": "lead fuel truck, radio contact weak", "stance": "ally"},
            {"name": "Enemy scouts", "role": "tree line, unknown strength", "stance": "hostile"},
        ],
        starting_inventory=(
            "Carried: rifle, binoculars, radio handset (weak), whistle. "
            "Position: two LMGs, sandbags, demo crank under tarp. Load: combat."
        ),
        hidden_threat=(
            "Charges were partially cut by a saboteur in your unit; a full crank may fail on one pier "
            "and drop only half the bridge under the convoy."
        ),
        seed=(
            "Open on the bridge with Lenz at the tarp and smoke in the trees. Introduce Lenz. "
            "Choices: hold for convoy, blow now, inspect charges, push a patrol, radio Colm."
        ),
    ),
    _sc(
        id="occupied-quarter-curfew",
        title="Occupied Quarter Curfew",
        quick_description="Under curfew, a neighbour begs you to hide a wanted courier until dawn.",
        icon="lock-closed-outline",
        pitch=(
            "Boots on cobbles. Searchlights on wet brick. A knock that is not the patrol — yet."
        ),
        genre="war survival",
        role="civilian under occupation",
        tone="grim",
        difficulty="hard",
        world_frame=_frame(
            era="mid_20c_occupation",
            technology="industrial_era_civilian",
            setting="occupied_city_quarter",
            primary_pressures=["curfew_enforcement", "moral_refuge_choice", "search_risk"],
            required_anchors=["apartment_or_street", "occupying_patrol", "courier_or_fugitive"],
            forbidden_opening_frames=["peacetime_office", "fantasy_magic_as_primary"],
        ),
        starting_location=(
            "Third-floor flat overlooking a narrow street. Blackout curtains. "
            "Cold stove. Your papers are in order — for now."
        ),
        starting_pressure=(
            "Neighbour Anya pushes a bleeding stranger inside and mouths 'please' as patrol boots "
            "turn onto your street. The stranger carries a sealed dispatch case."
        ),
        key_npcs=[
            {"name": "Anya", "role": "neighbour, resistance-adjacent", "stance": "ally, desperate"},
            {"name": "The courier", "role": "wounded, silent, case chained to wrist", "stance": "dependent"},
            {"name": "Patrol sergeant Krell", "role": "methodical, knows your building", "stance": "hostile authority"},
        ],
        starting_inventory=(
            "Carried: identity papers, ration cards, kitchen knife, candle stub. "
            "Flat: wardrobe, false floorboard (empty), one bottle of spirits. Load: light."
        ),
        hidden_threat=(
            "The dispatch is a plant; Krell is testing the block for collaborators. "
            "The courier will confess any host under pressure."
        ),
        seed=(
            "Open as Anya pushes the wounded courier in and boots sound below. Introduce Anya and the courier. "
            "Choices: hide them, refuse, destroy the case, signal from the window, prepare a cover story."
        ),
    ),
]


# Quick Start category → ordered scenario pool (3+ each; deterministic pick by seed).
QUICK_START_SCENARIO_POOLS: Dict[str, List[str]] = {
    "fantasy": ["oath-broken-keep", "relic-road-toll", "kingdom-border-curse"],
    "post-apocalyptic": ["suburban-collapse", "ash-caravan-ambush", "dry-reservoir-claim"],
    "cosmic-horror": [
        "cosmic-horror-road-town",
        "lighthouse-signal-loop",
        "library-that-rewrites",
    ],
    "detective": ["rain-district-alibi", "warehouse-shift-murder", "jazz-club-blackmail"],
    "dinosaur-survival": ["flint-band-stalked", "river-ice-calving", "tar-pit-foraging"],
    "horror": ["farmhouse-false-safety", "mine-elevator-stuck", "fog-boarding-house"],
    "urban-crime": ["dockside-cut", "rooftop-debt-run", "precinct-leak"],
    "war-survival": ["trench-supply-gap", "convoy-bridge-hold", "occupied-quarter-curfew"],
}


def get_scenarios() -> List[Dict[str, Any]]:
    """Public list (without the heavy seed paragraph) for the picker UI."""
    return [{k: v for k, v in s.items() if k != "seed"} for s in SCENARIOS]


def get_scenario(scenario_id: str) -> Dict[str, Any] | None:
    if scenario_id == "living-cast-proof":
        if not is_live_gate_enabled():
            return None
        from living_cast_seeded_scenario import LIVING_CAST_PROOF_SCENARIO

        return LIVING_CAST_PROOF_SCENARIO
    return next((s for s in SCENARIOS if s["id"] == scenario_id), None)


def select_scenario_id_from_pool(
    pool: Sequence[str],
    seed: str,
) -> Optional[str]:
    """
    Sole deterministic Quick Start scenario pick.

    Algorithm (authoritative — do not reimplement with a different hash):
      digest = SHA256("quick-scenario:" + seed) as hex
      index  = int(digest[:12], 16) % len(pool)

    Same (pool, seed) always yields the same scenario_id. Empty pool → None.
    """
    ids = [str(x).strip() for x in pool if str(x).strip()]
    if not ids:
        return None
    digest = hashlib.sha256(f"quick-scenario:{seed}".encode("utf-8")).hexdigest()
    idx = int(digest[:12], 16) % len(ids)
    return ids[idx]


def select_quick_start_scenario_id(
    card_key: str,
    seed: str,
) -> Optional[str]:
    """Pick from the canonical Quick Start pool for a card key."""
    pool = QUICK_START_SCENARIO_POOLS.get(card_key) or []
    return select_scenario_id_from_pool(pool, seed)


class ScenarioResolutionError(ValueError):
    """Fail-closed Quick Start / scenario membership errors."""


def resolve_new_story_scenario(
    *,
    scenario_id: Optional[str] = None,
    quick_start_key: Optional[str] = None,
    creation_request_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Resolve the scenario for POST /story/new.

    Authority when ``quick_start_key`` is set (Quick Start live path):
      - Backend selects scenario_id from QUICK_START_SCENARIO_POOLS[key]
        using select_scenario_id_from_pool(..., creation_request_id).
      - Client-supplied scenario_id, if present, must match exactly or fail closed.
      - Prehistoric key may never resolve to dinosaur-containment-breach.

    When only scenario_id is set (non-Quick curated start):
      - scenario must exist or fail closed.

    When neither is set: (None, None) — freeform genre start.
    """
    key = (quick_start_key or "").strip() or None
    client_sid = (scenario_id or "").strip() or None
    seed = (creation_request_id or "").strip()

    if key:
        if key not in QUICK_START_SCENARIO_POOLS:
            raise ScenarioResolutionError(f"Unknown quick_start_key: {key}")
        pool = list(QUICK_START_SCENARIO_POOLS[key])
        resolved = select_scenario_id_from_pool(pool, seed)
        if not resolved:
            raise ScenarioResolutionError(f"Empty scenario pool for quick_start_key: {key}")
        if key == "dinosaur-survival" and resolved == "dinosaur-containment-breach":
            raise ScenarioResolutionError(
                "Prehistoric Survival cannot use modern containment scenario"
            )
        if client_sid:
            if client_sid not in pool:
                raise ScenarioResolutionError(
                    f"scenario_id '{client_sid}' is not in the Quick Start pool for '{key}'"
                )
            if client_sid != resolved:
                raise ScenarioResolutionError(
                    "scenario_id does not match backend Quick Start selection for this creation_request_id"
                )
        scenario = get_scenario(resolved)
        if not scenario:
            raise ScenarioResolutionError(f"Unknown scenario: {resolved}")
        return resolved, scenario

    if client_sid:
        scenario = get_scenario(client_sid)
        if not scenario:
            raise ScenarioResolutionError(f"Unknown scenario: {client_sid}")
        return client_sid, scenario

    return None, None
