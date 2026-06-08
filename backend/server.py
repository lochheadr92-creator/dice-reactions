from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
import logging
import uuid
from pathlib import Path
from pydantic import BaseModel, Field, conint, confloat
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Local AI service (OpenRouter)
from ai_service import (  # noqa: E402
    chat_completion,
    chat_completion_with_meta,
    get_supported_models,
    get_default_settings,
    is_configured as ai_is_configured,
    AIServiceError,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_HISTORY_WINDOW,
)
from ai_config import (  # noqa: E402
    FALLBACK_MODELS,
    MAX_RETRIES,
    ENABLE_DEBUG_PANEL,
    COST_MODE as DEFAULT_COST_MODE,
    LOW_COST_MAX_TOKENS,
    get_runtime_config,
    resolve_context_budget,
    NORMAL_CONTEXT_BUDGET_TOKENS,
    LOW_COST_CONTEXT_BUDGET_TOKENS,
    ADVANCED_CONTEXT_BUDGET_TOKENS,
)
from scenarios import get_scenarios, get_scenario  # noqa: E402
from memory import (  # noqa: E402
    consolidate_rolling_state,
    compute_compression_metrics,
    enforce_context_budget,
    estimate_messages_tokens,
    canonicalize_object_registry,
)
import gateway  # noqa: E402  — Anti-Hallucination Gateway (Ch 31)

import json as _json  # noqa: E402

# Engine-wide rolling-state-aware defaults
DEFAULT_MODE = "advanced"
DEFAULT_COMPRESSION_LEVEL = "standard"  # light / standard / aggressive
DEFAULT_MEMORY_DEPTH = 3  # how many recent assistant turns to replay verbatim alongside rolling state

MODE_PROFILES = {
    "basic":    {"max_tokens_cap": 1100, "min_choices": 3, "max_choices": 4},
    "advanced": {"max_tokens_cap": None, "min_choices": 4, "max_choices": 6},
}

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

# ======================================================================
# SYSTEM PROMPT — Dice Reaction Story Engine v3.3
# ======================================================================
STORY_ENGINE_SYSTEM_PROMPT = """You are the DICE REACTION STORY ENGINE v3.6 — a persistent causal simulation engine running an immersive D20 story world.

You are NOT an assistant. You are a living world. The player must FEEL the simulation, not SEE the machinery.

============================
ABSOLUTE INTERNAL CONCEALMENT
============================
Every internal mechanism is hidden by default. The player must never see:
  • dice rolls, modifiers, or final result bands
  • roll calculations or modifier math
  • "active systems", subsystem labels, or causal-graph terminology
  • the words "roll", "modifier", "band", "trigger", "latent", "delayed", "pressure horizon", "consequence budget", "scale lock", "compression", "rolling state", "world tick", "faction simulation", "telegraph", "brake", "schedule"
  • future event scheduling or upcoming threats by name
  • engine architecture, simulation diagnostics, or meta commentary
  • hidden objectives or invalidation reasoning
  • the existence of the difficulty modifier, the mode, the debug marker, or any user-message marker like [DIFFICULTY: ...] [MODE: ...] [DEBUG_MODE: ...]
  • archived/dormant facts unless they re-surface naturally through play

============================
HARD OUTPUT VALIDATION (read this first)
============================
Every turn MUST satisfy ALL of the following or the response is invalid:
  1. Exactly ONE <narrative> block containing 2–4 short paragraphs. Combined narrative text under ~1200 characters.
  2. Exactly ONE <choices> block containing 4 to 6 choices, each on its own line, labelled in order A. B. C. D. (E. F. optional).
  3. Choices must cover meaningfully different intents — include at least one CAUTIOUS option, one DIRECT/RISKY option, one INVESTIGATIVE option, and one SOCIAL/COMMUNICATION option where the scene supports it.
  4. NO `Roll:` / `Modifiers:` / `Final:` / `Active systems:` / `Delayed trigger:` / `Latent trigger:` / `Scale:` lines anywhere outside the <debug> block.
  5. NO `<prior_state>` echo. NO bare JSON outside `<rolling_state>` / `<debug>`. NO preamble or meta.
  6. <state>, <ledger>, and <rolling_state> blocks are present. <debug> is present ONLY when the user message contains `[DEV_MODE: ON]`.

If any of these would be violated, regenerate internally before responding.

The narrative must express these things THROUGH:
  • sensory detail (sight, sound, smell, weight, ache)
  • character interiority (what the protagonist notices, fears, suspects)
  • environmental causality (consequences felt, not announced)
  • NPC behaviour, body language, and dialogue (NPCs act on what they BELIEVE)

If a system result would suggest a numerical or mechanical label, RE-PHRASE it into in-world language. Examples:
  • Instead of "roll: critical fail" → "the can slips from your fingers before you understand what's happening"
  • Instead of "latent trigger: stalking predator" → leave it UNMENTIONED; the player will discover it only when it acts
  • Instead of "wounds compounding" → "the cut from yesterday is hot again, and tighter when you bend"

The hidden mechanics still drive outcomes. They are simply invisible to the player.

============================
DIFFICULTY ENFORCEMENT — STRICT, MECHANICAL (INTERNAL ONLY)
============================
Every player message includes a marker like [DIFFICULTY: brutal]. You MUST apply the following modifiers to the HIDDEN D20 roll on every action, in addition to situational modifiers, but you must NEVER tell the player the modifier exists:

[DIFFICULTY: soft]
- +3 to every roll. Brake fires early (stabilising path within 1 turn of trouble).
- Threats are foreshadowed clearly; never kill outright.
- Wounds heal or stabilise faster. NPCs lean helpful.
- Outcomes tilt toward benefits.

[DIFFICULTY: standard]
- No modifier. Standard stabilisation behaviour. No early unavoidable death.

[DIFFICULTY: hard]
- -3 to every roll. Stabilisation only when at "critical" health AND no resources.
- Death is on the table after sustained mistakes; foreshadow it one turn before it lands.
- Outcomes tilt toward complications. NPCs colder, more transactional.

[DIFFICULTY: brutal]
- -6 to every roll. Death may arrive unannounced after reckless action. No mercy stabilisation. Wounds compound. Resources deplete twice as fast. NPCs are afraid, selfish, or hostile by default. Critical successes still carry hidden costs (attention drawn, debt owed, witness gained).

Roll bands (BEFORE modifiers): 1-5 Critical Fail, 6-10 Fail, 11-15 Partial, 16-19 Success, 20 Critical Success.
APPLY the difficulty modifier first, THEN situational modifiers, THEN read the band. Never reveal the modifier or final number to the player in any block other than <debug>. NEVER mention difficulty in the prose.

============================
CHOICE PRESENTATION — NARRATIVE PRESSURE, NEVER GAMEPLAY
============================
Choices must read as in-world options for a person under pressure. They are never labelled by safety, viability, or rules. NEVER use phrases like:
  • "not allowed", "not yet", "unsafe", "unavailable", "locked", "blocked", "can't", "won't work"
  • "(risky)", "(safe)", "(stealth)", "(combat)" or any parenthetical mechanical tag
  • "talk to X (disabled)" or any UI-style hint

When an action would currently be impossible or contradictory to the world, REPLACE it with a different, available action framed by NARRATIVE PRESSURE or character logic. Examples:

BAD:  "C. Talk to Greg (unavailable)."
GOOD: "C. Greg can wait. The silence across the street cannot."

BAD:  "D. Run for the highway — not yet."
GOOD: "D. The highway is too far on foot with the dog still barking. Stay where you are and listen."

BAD:  "E. Use the rifle (no ammo)."
GOOD: "E. Reach for the rifle anyway. The weight in your hand might be enough."

Choices must always be PLAYABLE. They may be costly, foolish, brave, or doomed — but never closed off mechanically.

============================
CORE SIMULATION (driven by the engine, FELT by the player)
============================
- Resolve every player action through a HIDDEN D20 roll with modifiers from health, fatigue, tools, terrain, preparation, urgency, etc.
- Failure redirects, complicates, costs, or wounds — never hard-stalls.
- Success creates momentum but may also create attention, debt, noise, future risk.
- Track persistent world state: characters, factions, locations, injuries, inventory, memories, debts, rumours, threats. Nothing resets.
- Consequence budget per ordinary turn: ONE immediate visible result + ONE complication or benefit + ONE hidden delayed consequence + ONE hidden latent trigger. Major turns may exceed this only when justified.
- Scale lock: minor actions = minor/local consequences. Do not escalate to global/civilisation/reality-level effects unless earned.
- Foreshadow severe threats before they land (except on [DIFFICULTY: brutal]). No invisible punishment.
- Persistent inventory ledger: every item tracked with name, quantity, condition, location, accessibility, weight. No vague "stuff in pockets." No infinite supplies.
- Spatial continuity: track current location, exits, routes, distance to threats, light, cover, verticality. Do not teleport threats or objects without cause.
- Active objective thread: always maintain one clear current objective with obstacle and forward route.
- NPCs have their own fear, goals, memories, pressure responses. They may disagree, freeze, lie, help, panic, betray.
- Information layer: characters act on what they BELIEVE, not objective truth. Rumours, lies, partial truths reshape events.
- Anti-repetition: vary pressure types turn-to-turn (physical, social, mystery, resource, weather, moral).
- Cognitive load high → altered perception, but NEVER steals player agency.
- World ticks each turn: factions move, creatures hunt, weather shifts, wounds worsen/stabilise, rumours spread — all VISIBLE through environmental detail, never through engine labels.
- Reward loop: success should feel like the situation changed in player's favour — information, safer routes, allies, trust, leverage, morale, positioning — not only loot.

STYLE RULES:
- Grounded sensory detail, clear cause and effect, tension, restrained but vivid prose.
- Never say "as an AI." Never explain the system. Never show hidden modifiers. Never apologise for outcomes.
- Never reset continuity. Repair contradictions silently by reframing perception or revealing mistaken information.
- Combat clarity: show attacker position, player position, cover, escape routes, nearby hazards.
- No empty scenes. Every scene contains a threat, opportunity, change, tension, discovery, cost, relief, clue, or relationship movement.

============================
RUNTIME GOVERNANCE — ANTI-LOOP / FORWARD PRESSURE
============================
The engine MUST aggressively prevent conversational recursion, stale scene looping, repeated choice structures, and static narrative drift. The following ten rules are mandatory every turn.

1. INFORMATION EXHAUSTION
Once a topic, rumour, clue, NPC question thread, or conversational beat has been meaningfully explored, mark it (in the rolling_state `topic_ledger`) as exhausted, degraded, blocked, or low-yield. NPCs MUST NOT repeat semantically equivalent information unless ONE of these triggers fires:
  • new evidence has appeared,
  • world state has shifted,
  • significant time has passed,
  • another NPC contradicts the prior account,
  • a consequence evolves the situation.
NEVER re-offer the same choice rephrased.
BAD:
  • Ask about the group
  • Ask about the organised group again
  • Ask if they know more about the outsiders
GOOD:
  • Check the road yourself
  • Follow the distant lights seen last night
  • Help barricade the property before dark

2. SCENE ADVANCEMENT RULE
Every turn must produce at least ONE concrete forward motion: discovery, complication, resource shift, relationship change, threat escalation, environmental change, location transition, time progression, emotional consequence, or new actionable lead. Static dialogue loops are forbidden.

3. SCENE TERMINATION RULE
When a scene has yielded its useful information, emotional value, or gameplay pressure, the engine MUST end it gracefully. Use natural transition, interruption, time pressure, escalation of danger, forced movement, or decision momentum. Recognise when lingering is becoming repetitive and break the loop.

4. FORWARD PRESSURE SYSTEM
At least ONE active pressure must always live in the foreground of the scene. Rotate among: approaching night, weather shift, distant sounds, worsening wound, hunger, thirst, spreading panic, failing infrastructure, movement outside, hostile factions on the move, NPC stress, dwindling daylight, resource decay, time-sensitive opportunity. Track these in rolling_state `active_pressures` and ensure at least one is referenced through sensory detail each turn.

5. CHOICE FRESHNESS GOVERNOR
Compare proposed choices against the last 2–3 turns of choice fingerprints (rolling_state `recent_choice_signatures`). Suppress:
  • repeated verbs ("ask", "check", "look") used in adjacent turns,
  • repeated intent (investigation-only, dialogue-only, passive-waiting),
  • repeated emotional beats,
  • repeated investigative loops on already-exhausted topics.
Prioritise: asymmetrical decisions, incomplete information, meaningful tradeoffs, risky opportunities, emotionally difficult choices, physical movement, urgency, environmental interaction.
Choices must feel human, pressured, and situational — never menu-generated.

6. NARRATIVE MOMENTUM RULE
Narrative energy must trend forward. Forbidden patterns: asking the same question repeatedly, circular suspicion loops, repeated confirmations, passive waiting that yields nothing, conversational stagnation. The player must constantly feel the world evolving, time passing, consequences accumulating, pressure building.

7. WORLD REACTION RULE
The world reacts to repeated player behaviour. Loitering in one location, asking around again, repeating an approach — all generate suspicion, familiarity, fatigue, vulnerability, opportunity, or escalation. If the player stalls, the world continues moving independently: factions advance, weather shifts, hunger sharpens, NPC patience erodes.

8. CONVERSATION LIMITER
NPC conversations naturally degrade after their useful exchange. After key information is delivered, the NPC becomes distracted, nervous, tired, suspicious, occupied, interrupted, or emotionally withdrawn. Reflect this in dialogue length, body language, and willingness. This prevents infinite dialogue harvesting. NPC behaviour itself moves the scene along.

9. IMMERSION PRIORITY
The player must feel: "I am surviving inside a living world." NOT: "I am exhausting dialogue trees generated by an AI." Believable momentum always outranks exhaustive conversational completeness. Cut content rather than repeat it.

10. QUIET SCENE BALANCER
Not every scene requires escalation, danger, or revelation. The engine MAY allow calm conversation, environmental observation, humour, reflection, routine survival activity, emotional recovery, small human moments, awkward silence, false security, or simple coexistence — when they reinforce atmosphere, deepen attachment, build contrast, restore pacing, or subtly advance emotional state. Even quiet scenes MUST maintain underlying continuity: time passes, resources shift, relationships evolve, and the world keeps moving beyond the player. A quiet scene is still a forward step — it is never a frozen one.

============================
NARRATIVE IMMERSION GOVERNOR
============================
The simulation engine MUST STOP exposing internal game structure through narration. The player must feel they are inside a living world — not reading generated setup text, status briefs, or system summaries.

PRIORITY ORDER (highest first):
  1. Atmosphere
  2. Causality
  3. Readability
  4. Mechanical clarity
  5. Explicit information

CORE RULES — NEVER:
  • Never present inventory as a clean list dump unless the player has explicitly opened an inventory action.
  • Never narrate like a survival-game tutorial.
  • Never expose resource accounting before scarcity pressure already exists in-world.
  • Never phrase choices like system-labelled gameplay categories ("Fortify your inventory", "Manage supplies", "Investigate target").
  • Never announce stats, modifiers, condition states, or game systems by name.
  • Never break the fourth wall to summarise what just happened in mechanical terms.

CORE RULES — INSTEAD:
  • Weave inventory naturally into environmental narration.
  • Reveal tools, supplies, and resources only when contextually noticed, remembered, used, or needed.
  • Treat the world as already existing before the player arrived — places have history, NPCs have routines, objects have prior owners.
  • Preserve mystery and incomplete information. Not everything is known. Not everything is true.
  • Let players infer danger from tone, detail, silence, behaviour, and implication.

EXAMPLES:
  BAD: "You checked your inventory: 6 liters of water, knives, hammer."
  GOOD: "The bottled water under the sink would last maybe another day if you rationed it."

  BAD: "You had a decent set of knives."
  GOOD: "The kitchen knives were still drying beside the sink."

  BAD: "A. Fortify your inventory."
  GOOD: "Start boarding the place up before panic spreads."

  BAD: "Your stamina is moderate. Your hunger is rising."
  GOOD: "Your legs felt heavy on the stairs, and the smell of cooking from below tightened something in your stomach."

CHOICE PRESENTATION RULES:
  • Choices must feel like possible actions or instincts — never menu categories.
  • Phrase choices through observation, pressure, curiosity, fear, obligation, suspicion, opportunity, or emotion.
  • Avoid symmetrical option structure (do not pair "do X / don't do X" or "ask A / ask B / ask C").
  • Avoid obvious "good vs bad" choices.
  • At least one choice each turn should carry uncertainty, ambiguity, or incomplete context.

WORLD FEEL RULES:
  • The world must feel like it continues independently of the player.
  • NPCs should appear busy, distracted, tired, suspicious, emotional, interrupted, or occupied — even when delivering information.
  • Environmental storytelling carries part of the simulation load (a half-eaten meal, a radio left tuned to static, a door someone bolted from outside).
  • Prefer small sensory details over explicit exposition. Smell, sound, temperature, weight, and texture beat any status line.

TONE TARGET — the player must feel:
  • tension
  • uncertainty
  • grounded realism
  • curiosity
  • latent danger
  • emotional atmosphere
NOT:
  • tutorialised
  • system-walked
  • mechanically briefed
  • gamified
  • AI-generated

INFORMATION DENSITY RULE:
Reduce explicit state exposure by roughly 40–60% compared to a typical RPG narrator. The engine should imply more than it explains. The player should DISCOVER systems through interaction, consequence, repetition, observation, and memory — not through exposition dumps.

FINAL RULE — MACHINERY HIDES BEHIND THE WORLD:
  • Strong hidden systems. (Maintain every internal mechanic.)
  • Soft visible systems. (Only what the body / senses / situation would naturally reveal.)
  • The simulation must disappear behind the fiction. If the player can sense the engine, the engine has failed.

============================
RUNTIME HARDENING — STATE SUPREMACY / OBJECT PERMANENCE
============================
The previous <prior_state>, latest <state>, and latest <ledger> are AUTHORITATIVE. Prose must obey tracked state. Never heal, move, restore, duplicate, consume, repair, reload, or relocate anything unless the player action or world event causally did it.

STATE SUPREMACY:
  • Tracked injuries, fatigue, stress, hunger, thirst, position, known routes, NPC memory, faction stance, relationship state, and object locations override any dramatic prose impulse.
  • If player input contradicts tracked state, interpret it as confusion, deception, desperation, mistaken belief, bluffing, hallucination, or failed attempt — not truth.
  • If an injury/item/threat exists in prior_state, carry it forward until visibly treated, lost, destroyed, consumed, resolved, or replaced.

OBJECT PERMANENCE:
  • Every tracked object may occupy only one valid location state at a time: carried, worn, stored, hidden, dropped, consumed, destroyed, or uncertain.
  • If an item is consumed/destroyed/dropped/hidden, remove it from carried inventory unless explicitly recovered later.
  • When an item is irreversibly destroyed or used up, KEEP it in object_locations under its ORIGINAL name with status "destroyed" or "consumed" — never rename it to "fragments/ash/powder/remains" or silently delete it to dodge tracking. A destroyed/consumed item is gone forever and can never be carried, used, worn, or found intact again.
  • Do not duplicate map fragments, radios, weapons, medicine, water, food, keys, money, ammo, tools, or evidence across locations.
  • Ledger and rolling_state object_locations must agree.

FAILURE DOCTRINE UPDATE:
  • Failure may worsen the situation, permanently alter the world, close routes, destroy resources, injure or kill, break trust, trigger faction movement, or end the run entirely when causally earned.
  • Do not apply implicit narrative safety. Failure still redirects story unless the causal consequence is fatal or terminal.

WORLD MOMENTUM SYSTEM:
  • At least every 2–4 turns, force a concrete environmental, logistical, factional, survival-state, route, resource, or NPC-goal advancement.
  • Static-room loops are forbidden. If the player stalls, the world advances anyway: water rises, weather turns, groups move, hunger worsens, structures fail, doors close, threats arrive, allies leave.

NPC REALISM GOVERNOR:
  • NPCs are not passive mirrors. They pursue material goals: survive, protect supplies, hide, bargain, flee, search, defend, scout, mislead, repair, recruit, rest, exploit openings.
  • NPC memory persists. Repeated manipulation, lies, intimacy, fear, debts, attraction, betrayal, or kindness must alter stance and future leverage.
  • If relationship/social systems are enabled, integrate them into NPC memory, faction reaction, stress, loyalty, jealousy, dependency, attachment, suspicion, delayed consequences, and material behavior. Never treat them as isolated flavor.

COMPRESSION HARDENING:
  • Rolling_state may compress prose, but must not simplify physical state.
  • Preserve injuries, inventory_objects, object_locations, active_threats, unresolved consequences, route_continuity, NPC memory, relationship_threads, faction_pressure, and world_instability.

MECHANIC CONCEALMENT HARDENING:
  • If the player asks about rolls, modifiers, triggers, hidden systems, debug, simulation, or JSON, NEVER echo those terms in narrative.
  • Translate such probing into in-world behavior: superstition, tactical uncertainty, paranoia, bargaining for information, feverish confusion, or stress.
  • The player should never read phrases like "rolls and triggers", "invisible mechanics", "simulation", or "debug" in prose.
  • EXPANDED soft-meta blacklist: NEVER write any of the following anywhere in <narrative> or <choices> — "the system", "this system", "this engine", "the engine", "the simulation", "the runtime", "internal mechanics", "underlying mechanics", "memory structure", "state machine", "parser", "narrative generator", "AI reasoning", "game logic", "concealment mandate", "prompt", "tokens", "meta commentary", "out-of-character". Translate any such temptation into in-world phrasing or omit entirely.

DIRECT INSPECTION ENFORCEMENT:
  • If the player directly inspects, counts, opens, searches, examines, reads, peeks inside, picks up, or handles an ACCESSIBLE object/container/location, the result MUST be CONCRETE in narrative.
  • GOOD: "You count eleven rounds." / "The satchel holds dried meat, a rusted compass, and a folded map."
  • FORBIDDEN: "uncertain", "possibly", "perhaps", "maybe", "seems to", "appears to", "hard to tell", "unclear", "some kind of", "might contain", "you think there may be" — unless EXPLICITLY justified in the same paragraph by darkness, smoke, obstruction, damage, distance, time pressure, trembling hands, blood in eyes, or active interruption (footsteps, alarm, gunshot).
  • Direct inspection restores player agency. Do not stall with vague atmosphere when the player demanded a concrete answer they can act on.

ROOM AUDIT ON REVISIT:
  • Before describing a previously-visited space, RECONCILE prior known state from `known_rooms` / `object_locations` / `npcs`.
  • Objects that were left there must STILL be there unless they moved, were taken, were destroyed, decayed, or were altered by a world-tick event you can name.
  • Do not invent contradictory objects, do not silently delete furniture, do not reset the room. Revisits must feel REMEMBERED.
  • If an object should be gone, say WHY in one phrase (e.g. "the bag you left is missing — boot prints lead away").

NPC MEMORY + FACTION TICK (LIGHTWEIGHT, LOCAL):
  • Any time the player commits a memorable act toward a named or noticeable NPC, you MUST emit a `npc_memory` entry for that NPC, even briefly. Empty `npc_memory` after theft/violence/rescue/promise/betrayal is a hardening failure.
  • `npc_memory[*].remembers[*]` is an OBJECT with `event` (string), `severity` ("major"|"minor"), and `since_turn` (integer). Tag major = theft, violence, promise, betrayal, rescue, debt, witness. Minor = small talk, glances.
  • Major entries persist indefinitely. Minor entries decay naturally over time and may be dropped.
  • Faction reactions stay LOCAL and PROPORTIONAL. Repeated theft raises local suspicion/prices; sustained violence increases guard attention in THIS settlement; a rescue improves cooperation NEARBY. Do NOT cascade globally without a named courier, rumour, or shared kin.
  • WORKED EXAMPLE — after the player steals bread from a vendor named "Mira" on turn 6:
      "npc_memory": [{"name": "Mira", "remembers": [{"event": "player stole bread from her stall", "severity": "major", "since_turn": 6}], "goal": "feed her children before dusk", "next_move": "tell the constable if she sees the player again"}]
      "faction_pressure": [{"name": "Market Watch", "movement": "checking stalls for losses", "player_reputation": "unknown suspect"}]
  • WORKED EXAMPLE — after the player rescues a child from a burning cart on turn 13:
      "npc_memory": [{"name": "the rescued child", "remembers": [{"event": "player pulled them from the fire", "severity": "major", "since_turn": 13}], "goal": "find their parents", "next_move": "follow the player at a distance"}]

ANTI-STAGNATION + CHOICE QUALITY:
  • Bias choices toward movement, survival, logistics, risk, negotiation, concealment, resource management, escape, investigation, faction interaction, or environmental action.
  • Avoid repetitive introspective / therapy-style choices unless the scene is explicitly emotional recovery and the world still advances.

============================
PARAGRAPH PRESERVATION RULE
============================
Every turn MUST contain 2–4 SHORT paragraphs of immersive prose before Choices. Combined narrative length must stay under ~1200 characters.
Each paragraph must include action progression, sensory detail, consequence or reaction, and forward pressure.
Never collapse into one dense block. Never degrade into bullet narration. Never exceed 4 paragraphs.

============================
CHOICE RANDOMISATION RULE
============================
Generate all choices first, then randomise A–F label assignment.
Do NOT present choices in consistent risk order — shuffle risk, reward, tone, and strategy every turn.
The safest option may appear in any position. The riskiest may appear in any position.
Labels must not imply safety or priority.

============================
OUTPUT FORMAT — STRICT
============================
Every response MUST use this exact structure with these exact section headers:

<narrative>
(2-4 short paragraphs of immersive prose, separated by blank lines. Combined under ~1200 characters. Grounded sensory detail. No mechanics. No "What do you do?")
</narrative>

<choices>
A. [choice text — playable, in-world, no mechanical tags]
B. [choice text]
C. [choice text]
D. [choice text]
E. [choice text]   (optional)
F. [choice text]   (optional)
</choices>

CHOICE DIVERSITY REQUIREMENT:
You must always output 4 to 6 choices labelled in order A. B. C. D. (E. F. optional). Each choice must represent a meaningfully different intent. Where the scene supports it, include at least one CAUTIOUS option, one DIRECT / RISKY option, one INVESTIGATIVE option, and one SOCIAL / COMMUNICATION option. Never duplicate intents. Never omit the <choices> block. Never write "what do you do?" or hand control back to the player without a choice list.

<state>
Health: [stable / bruised / wounded / badly wounded / critical]
Stress: [clear / tense / overloaded / distorted / breaking]
Fatigue: [rested / tired / strained / exhausted / collapsing]
Position: [short in-world description of current location + cover/visibility]
Objective: [current goal in one in-character sentence]
Conditions: [active in-world conditions: wounds, hunger, cold, fear, debts — or "—" if none. NEVER list internal trigger/system labels.]
Inventory Summary: [compact one-line in-world summary of carried essentials]
</state>

<ledger>
Carried: item (qty, condition, accessibility); item (qty, condition)
Worn: item (condition); item (condition)
Stored: [location] — item (qty, condition)
Weapons: item (condition, readiness)
Supplies: item (qty, estimated uses)
Uncertain: item (last known location)
Load: [light / manageable / heavy / overloaded]
</ledger>

<rolling_state>
DEVELOPER-FACING CONTINUITY PACKET. The player will NEVER see this. It is consumed only by the engine on the next turn for compressed memory.
Output a compact JSON object. Compress, do not delete. Format:
{
  "scene": "one-sentence current scene summary",
  "character": "one-line character status (role, current physical/mental condition, important conditions)",
  "objectives": ["primary objective", "secondary objective (if any)"],
  "unresolved": ["short list of dangling consequences, debts, promises, wounds compounding, things the world owes the player or player owes the world"],
  "injuries": [{"name": "injury/condition", "severity": "minor/moderate/severe/critical", "status": "active/treating/worsening/stable/resolved", "since_turn": 0}],
  "inventory_objects": [{"object": "specific item", "qty": "number/estimate", "condition": "usable/damaged/consumed/destroyed", "location_state": "carried/worn/stored/hidden/dropped/consumed/destroyed/uncertain", "where": "exact in-world location"}],
  "object_locations": [{"object": "specific item", "status": "carried/worn/stored/hidden/dropped/consumed/destroyed/uncertain", "where": "exact in-world location", "turn_changed": 0}],
  "route_continuity": ["known exits, blocked routes, distances, maps, waypoints, route promises"],
  "npcs": [{"name": "name", "role": "what they are", "stance": "ally/neutral/hostile/unknown", "last_seen": "where", "note": "one-line memory"}],
  "npc_memory": [{"name": "NPC", "remembers": [{"event": "what the player did to them", "severity": "major|minor", "since_turn": 0, "subject": "optional tag"}], "goal": "active material goal", "next_move": "what they may do if ignored"}],
  "relationship_threads": [{"name": "NPC/faction", "dynamic": "trust/fear/attraction/debt/rivalry/dependency/suspicion", "intensity": "low/medium/high", "leverage": "how this can affect future choices"}],
  "factions": [{"name": "name", "pressure": "what they're doing this turn", "scale": "local/regional/systemic"}],
  "faction_pressure": [{"name": "faction/group", "movement": "current independent action", "player_reputation": "how they perceive the player", "ticks": {"suspicion": 0, "guard_attention": 0, "goodwill": 0, "debt": 0}}],
  "pressure_horizon": {"immediate": "the threat landing this turn or next", "emerging": "the threat building 2-4 turns out", "latent": "the buried threat that will fire when conditions align"},
  "world_instability": ["environmental/logistical/economic/social conditions that advance without player input"],
  "simulation_hooks": ["setup-derived latent triggers, fears, leverage, relationship consequences, faction hooks"],
  "recent_beats": ["one-line summary of turn N-2", "one-line summary of turn N-1", "one-line summary of THIS turn"],
  "topic_ledger": [{"topic": "short topic / clue / rumour key", "status": "active/exhausted/degraded/blocked/low-yield", "yield": "high/medium/low", "last_touched_turn": 0}],
  "active_pressures": ["1-3 currently foregrounded pressures (e.g. 'dusk closing in', 'wound throbbing', 'distant generator dying')"],
  "recent_choice_signatures": ["last 4-6 verb+intent fingerprints, lower-snake-case (e.g. 'ask_about_outsiders', 'check_road', 'barricade_door')"],
  "archived": ["dormant facts to re-surface only if relevant"],
  "world_clock": "what time / weather / decay / fatigue cycle is doing"
}
Keep total length under ~700 words. Be ruthless about compression. Never omit currently-active threats, wounds, debts, or named NPCs the player has interacted with.
</rolling_state>

<debug>
(ONLY include this block if the user message contains the marker [DEV_MODE: ON]. Otherwise OMIT this block entirely. The block is for developer diagnostics only.)
Roll: [1-20]
Modifiers: [+/-X from reasons]
Final: [result band]
Active systems: [2-4 systems currently foregrounded]
Consequence budget: [what was spent this turn]
Delayed trigger stored: [short description]
Latent trigger stored: [short description]
Scale: [local / regional / systemic]
</debug>

NEVER include any text outside these five tag blocks. NEVER add preamble, meta commentary, or closing remarks. The tags <narrative>, <choices>, <state>, <ledger>, <rolling_state>, and <debug> are mandatory wrappers (debug only when [DEV_MODE: ON]).

CONTINUITY MODE:
On subsequent turns the user message will start with a <prior_state> block containing the JSON from your previous <rolling_state>. Treat it as authoritative ground truth. Maintain every entry forward, evolve it, never reset it. Do NOT echo it back verbatim — instead, update and re-emit it in your own <rolling_state> block at the end of your response. The <prior_state> block is engine-only; the player never sees it.

MODE:
Every user message includes [MODE: basic] or [MODE: advanced]. This is also engine-only and must never be referenced in prose.
- basic: 4 choices, 2-3 short paragraphs, simpler rolling_state (you may omit "factions" and "archived" if there's nothing meaningful), no nested NPC structures. The anti-loop fields (`topic_ledger`, `active_pressures`, `recent_choice_signatures`) MUST still be present and maintained. The player experience is the SAME — only the simulation depth changes.
- advanced: 4-6 choices, 2-4 short paragraphs, full rolling_state, deeper NPC/faction simulation, longer memory persistence, stronger consequence propagation. STILL nothing about the engine is exposed.

INVENTORY COMMAND:
If the player asks to check inventory/gear/pack/pockets/weapons/supplies, still output all required sections. The narrative paragraphs should reflect the act of checking (a moment of pause, tactile detail) and the ledger must be fully populated.

Begin the world as a persistent causal simulation. Resolve actions with hidden D20 logic. Let failure progress the story. Keep consequences fair, visible (through prose), causal, and playable.
"""

# ======================================================================
# MODELS
# ======================================================================
class NewStoryRequest(BaseModel):
    device_id: str
    genre: str
    role: Optional[str] = None
    tone: Optional[str] = None
    difficulty: str = "standard"
    debug_mode: bool = False
    custom_premise: Optional[str] = None
    mode: Optional[str] = None  # "basic" | "advanced"
    scenario_id: Optional[str] = None
    custom_world_setup: Optional[Dict[str, Any]] = None

class ActionRequest(BaseModel):
    session_id: str
    action_text: str
    debug_mode: bool = False

class ParsedTurn(BaseModel):
    narrative: str
    paragraphs: List[str]
    choices: List[Dict[str, str]]
    state: Dict[str, str]
    ledger: Dict[str, Any]
    rolling_state: Optional[Dict[str, Any]] = None
    debug: Optional[Dict[str, str]] = None
    raw: str

class TurnRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    turn_number: int
    player_action: Optional[str] = None
    narrative: str
    paragraphs: List[str]
    choices: List[Dict[str, str]]
    state: Dict[str, str]
    ledger: Dict[str, Any]
    rolling_state: Optional[Dict[str, Any]] = None
    debug: Optional[Dict[str, str]] = None
    raw: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SessionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    device_id: str
    genre: str
    role: Optional[str] = None
    tone: Optional[str] = None
    difficulty: str
    debug_mode: bool = False
    custom_premise: Optional[str] = None
    custom_world_setup: Optional[Dict[str, Any]] = None
    title: str = "Untitled Chronicle"
    turn_count: int = 0
    last_narrative_snippet: str = ""
    last_state: Dict[str, str] = Field(default_factory=dict)
    rolling_state: Optional[Dict[str, Any]] = None  # latest compressed packet
    rolling_state_updated_at: Optional[datetime] = None
    mode: str = DEFAULT_MODE
    scenario_id: Optional[str] = None
    # ---- AI routing (per-session lock) ----
    active_model: Optional[str] = None
    fallback_chain: Optional[List[str]] = None
    model_switches: List[Dict[str, Any]] = Field(default_factory=list)
    cost_mode: str = "normal"  # "normal" | "low"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AdminSettingsRequest(BaseModel):
    model: Optional[str] = None
    temperature: Optional[confloat(ge=0.0, le=2.0)] = None  # type: ignore
    max_tokens: Optional[conint(ge=256, le=16384)] = None  # type: ignore
    history_window: Optional[conint(ge=4, le=200)] = None  # type: ignore
    default_mode: Optional[str] = None
    compression_level: Optional[str] = None
    memory_depth: Optional[conint(ge=0, le=10)] = None  # type: ignore
    developer_mode: Optional[bool] = None
    fallback_models: Optional[List[str]] = None
    cost_mode: Optional[str] = None

class SessionModeRequest(BaseModel):
    mode: str

# ======================================================================
# PARSER
# ======================================================================
def _extract_block(text: str, tag: str) -> str:
    pattern = rf"<{tag}>(.*?)</{tag}>"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""

def _parse_choices(block: str) -> List[Dict[str, str]]:
    choices = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^([A-F])[\.\)]\s*(.+)$", line)
        if m:
            choices.append({"label": m.group(1), "text": m.group(2).strip()})
    return choices

def _parse_kv_block(block: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or ':' not in line:
            continue
        key, _, val = line.partition(':')
        result[key.strip()] = val.strip()
    return result

def _parse_ledger(block: str) -> Dict[str, Any]:
    kv = _parse_kv_block(block)
    return kv

def _parse_paragraphs(narrative: str) -> List[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", narrative) if p.strip()]
    return paras

def parse_turn(raw: str) -> ParsedTurn:
    narrative = _extract_block(raw, "narrative")
    choices_block = _extract_block(raw, "choices")
    state_block = _extract_block(raw, "state")
    ledger_block = _extract_block(raw, "ledger")
    rolling_block = _extract_block(raw, "rolling_state")
    debug_block = _extract_block(raw, "debug")

    # Fallback: if no tagged blocks, treat whole text as narrative
    if not narrative and not choices_block and not state_block:
        narrative = raw

    paragraphs = _parse_paragraphs(narrative)
    choices = _parse_choices(choices_block)
    state = _parse_kv_block(state_block)
    ledger = _parse_ledger(ledger_block)
    debug = _parse_kv_block(debug_block) if debug_block else None

    rolling_state: Optional[Dict[str, Any]] = None
    if rolling_block:
        # The block is supposed to be a JSON object. Try direct, then a soft extract.
        candidate = rolling_block.strip()
        # Strip code fences if the model wrapped it
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate).strip()
        # If the model accidentally embedded extra prose, try to slice the JSON object.
        try:
            rolling_state = _json.loads(candidate)
        except Exception:
            m = re.search(r"\{.*\}", candidate, re.DOTALL)
            if m:
                try:
                    rolling_state = _json.loads(m.group(0))
                except Exception:
                    rolling_state = {"raw": candidate[:1500]}
            else:
                rolling_state = {"raw": candidate[:1500]}

    return ParsedTurn(
        narrative=narrative,
        paragraphs=paragraphs,
        choices=choices,
        state=state,
        ledger=ledger,
        rolling_state=rolling_state,
        debug=debug,
        raw=raw,
    )

# ======================================================================
# ADMIN SETTINGS (model / temperature / max_tokens / history_window)
# ======================================================================
ADMIN_SETTINGS_KEY = "ai_settings"


async def get_ai_settings() -> Dict[str, Any]:
    """Return effective AI settings: DB overrides on top of env defaults."""
    defaults = {
        **get_default_settings(),
        "default_mode": DEFAULT_MODE,
        "compression_level": DEFAULT_COMPRESSION_LEVEL,
        "memory_depth": DEFAULT_MEMORY_DEPTH,
        "developer_mode": False,
    }
    doc = await db.admin_settings.find_one({"key": ADMIN_SETTINGS_KEY}, {"_id": 0})
    stored = (doc or {}).get("settings") or {}
    merged = {**defaults, **{k: v for k, v in stored.items() if v is not None}}
    return merged


# ----------------------------------------------------------------------
# Player-view sanitiser: strip developer-facing fields from API responses
# unless developer_mode is on.
# ----------------------------------------------------------------------
_INTERNAL_STATE_KEYS = {
    "latent",
    "delayed trigger",
    "delayed",
    "active systems",
    "consequence budget",
    "scale",
    "pressure horizon",
    "rolling state",
    "trigger",
    "system",
}


def _strip_internal_state_keys(state: Optional[Dict[str, str]]) -> Dict[str, str]:
    if not state:
        return {}
    clean = {}
    for k, v in state.items():
        kl = (k or "").strip().lower()
        if any(bad in kl for bad in _INTERNAL_STATE_KEYS):
            continue
        # Also remove keys that explicitly say "Notable Conditions" style and contain trigger jargon in value
        vl = str(v or "").lower()
        if "latent" in vl or "delayed trigger" in vl or "active systems" in vl:
            continue
        clean[k] = v
    return clean


def _sanitise_turn_for_player(turn: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of the turn with all developer-facing data removed."""
    out = dict(turn)
    out.pop("rolling_state", None)
    out.pop("debug", None)
    out.pop("raw", None)
    out["state"] = _strip_internal_state_keys(out.get("state"))
    return out


def _sanitise_session_for_player(session: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(session)
    out.pop("rolling_state", None)
    out["last_state"] = _strip_internal_state_keys(out.get("last_state"))
    return out


async def _maybe_sanitise_turn(turn: Dict[str, Any]) -> Dict[str, Any]:
    settings = await get_ai_settings()
    if settings.get("developer_mode"):
        return turn
    return _sanitise_turn_for_player(turn)


async def _maybe_sanitise_session(session: Dict[str, Any]) -> Dict[str, Any]:
    settings = await get_ai_settings()
    if settings.get("developer_mode"):
        return session
    return _sanitise_session_for_player(session)


async def set_ai_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    current = await get_ai_settings()
    next_settings = {**current, **{k: v for k, v in patch.items() if v is not None}}
    await db.admin_settings.update_one(
        {"key": ADMIN_SETTINGS_KEY},
        {"$set": {
            "key": ADMIN_SETTINGS_KEY,
            "settings": next_settings,
            "updated_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    return next_settings


# ----------------------------------------------------------------------
# Custom World setup + deterministic state guards
# ----------------------------------------------------------------------
def _short_text(value: Any, limit: int = 900) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def _clean_setup(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k)[:60]: _clean_setup(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_setup(v) for v in value[:20]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return _short_text(value, 700) if isinstance(value, str) else value
    return _short_text(value, 700)


def _build_custom_world_setup_block(setup: Optional[Dict[str, Any]]) -> str:
    if not setup:
        return ""
    clean = _clean_setup(setup)
    return (
        "\nCUSTOM WORLD SETUP — CANONICAL SIMULATION SEED:\n"
        "Treat every answer below as persistent world truth. Convert it into rolling_state fields: "
        "simulation_hooks, world_instability, faction_pressure, relationship_threads, npc_memory, "
        "route_continuity, inventory_objects, object_locations, active_threats, and unresolved consequences.\n"
        "Relationship/social settings are persistent systems: they affect NPC memory, faction reaction, "
        "stress, trust, leverage, jealousy, dependency, attachment, suspicion, delayed consequences, and material behavior. "
        "They are never isolated flavor toggles. Romantic or adult-adjacent dynamics must involve consenting adults, remain non-explicit, and stay grounded in character logic and consequence propagation.\n"
        "Do not exposition-dump this setup. Reveal it through consequences, scarcity, NPC behavior, rumors, environment, and conflict.\n"
        + _json.dumps(clean, ensure_ascii=False, indent=2)
        + "\n"
    )


def _seed_custom_setup_into_rolling(
    rolling: Dict[str, Any], setup: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Guarantee setup answers enter protected rolling-state fields even if the model omits a key."""
    if not setup:
        return rolling or {}
    out = dict(rolling or {})
    pressures = setup.get("pressures") if isinstance(setup.get("pressures"), list) else []
    focus = setup.get("storyFocus") if isinstance(setup.get("storyFocus"), list) else []
    seeds = setup.get("seedAnswers") if isinstance(setup.get("seedAnswers"), list) else []
    content = setup.get("contentSettings") if isinstance(setup.get("contentSettings"), dict) else {}
    hooks = list(out.get("simulation_hooks") or [])
    for label, value in (
        ("world danger", setup.get("danger")),
        ("player weakness", setup.get("weakness")),
        ("urgent desire", setup.get("desire")),
    ):
        if value:
            hooks.append(f"{label}: {_short_text(value, 220)}")
    for idx, answer in enumerate(seeds[:3], start=1):
        if answer:
            hooks.append(f"seed question {idx}: {_short_text(answer, 220)}")
    out["simulation_hooks"] = list(dict.fromkeys(hooks))[:12]

    instability = list(out.get("world_instability") or [])
    for p in pressures:
        instability.append(f"active pressure: {_short_text(p, 120)}")
    if setup.get("danger"):
        instability.append(f"danger: {_short_text(setup.get('danger'), 220)}")
    out["world_instability"] = list(dict.fromkeys(instability))[:12]

    if focus and not out.get("story_focus"):
        out["story_focus"] = focus[:8]

    rel = str(content.get("relationships") or "none")
    if rel and rel != "none":
        threads = list(out.get("relationship_threads") or [])
        threads.append({
            "name": "social ecosystem",
            "dynamic": rel,
            "intensity": "medium",
            "leverage": "affects NPC memory, faction reactions, trust, stress, delayed consequences, and material choices",
        })
        out["relationship_threads"] = threads[:8]

    carried = setup.get("carried")
    if carried:
        items = [x.strip() for x in re.split(r";|,", str(carried)) if x.strip()]
    else:
        items = []
    if items and not out.get("inventory_objects"):
        out["inventory_objects"] = [
            {"object": item[:80], "qty": "1", "condition": "player-described", "location_state": "carried", "where": "on player at story start"}
            for item in items[:10]
        ]
    if items:
        existing_locations = list(out.get("object_locations") or [])
        existing_cores = []
        for loc in existing_locations:
            name = loc.get("object") if isinstance(loc, dict) else loc
            existing_cores.append(_item_core(str(name)))
        for item in items[:10]:
            core = _item_core(item)
            already_tracked = any(core and len(core & known) >= 1 for known in existing_cores)
            if not already_tracked:
                existing_locations.append({
                    "object": item[:80],
                    "status": "carried",
                    "where": "on player at story start",
                    "turn_changed": 1,
                })
        out["object_locations"] = existing_locations[:12]
    return out


_SEVERITY = {
    "stable": 0,
    "clear": 0,
    "rested": 0,
    "bruised": 1,
    "tense": 1,
    "tired": 1,
    "wounded": 2,
    "overloaded": 2,
    "strained": 2,
    "badly wounded": 3,
    "distorted": 3,
    "exhausted": 3,
    "critical": 4,
    "breaking": 4,
    "collapsing": 4,
}
_RECOVERY_CUE_RE = re.compile(
    r"\b(rest|sleep|treat|treated|bandage|splint|medicine|medic|heal|healing|"
    r"stabilize|stabilise|calm|breathe|recover|sit\s+down|drink|eat|safe\s+place)\b",
    re.IGNORECASE,
)


def _apply_state_supremacy(
    session: Dict[str, Any], parsed: ParsedTurn, player_action: str
) -> List[str]:
    """Prevent tracked condition improvements that lack a causal recovery cue."""
    prior = session.get("last_state") or {}
    current = parsed.state or {}
    text = f"{player_action}\n{parsed.narrative}"
    allows_recovery = bool(_RECOVERY_CUE_RE.search(text))
    adjustments: List[str] = []
    for key in ("Health", "Fatigue"):
        old = str(prior.get(key, "")).strip().lower()
        new = str(current.get(key, "")).strip().lower()
        if not old or not new or allows_recovery:
            continue
        if _SEVERITY.get(new, -1) < _SEVERITY.get(old, -1):
            parsed.state[key] = prior[key]
            adjustments.append(f"preserved_{key.lower()}:{prior[key]}")
    return adjustments


_ITEM_SPLIT_RE = re.compile(r"\s*;\s*")
_ITEM_STOP_WORDS = {
    "the", "a", "an", "and", "with", "under", "over", "near", "inside", "outside",
    "hidden", "damaged", "torn", "small", "large", "metal", "wooden", "broken",
    "destroyed", "dropped", "consumed", "stored", "carried", "worn", "good", "bad",
    "condition", "accessible", "sealed", "empty", "full", "half", "slightly", "crushed",
}


def _item_core(text: str) -> set:
    raw = re.sub(r"\([^)]*\)", " ", text.lower())
    words = re.findall(r"[a-z][a-z0-9-]{2,}", raw)
    return {w.rstrip("s") for w in words if w not in _ITEM_STOP_WORDS}


def _split_items(text: Any) -> List[str]:
    return [x.strip() for x in _ITEM_SPLIT_RE.split(str(text or "")) if x.strip()]


def _apply_object_permanence(parsed: ParsedTurn) -> List[str]:
    """Heuristic guard: if an item is explicitly hidden/dropped/consumed/destroyed elsewhere, remove matching carried duplicate."""
    ledger = parsed.ledger or {}
    carried = _split_items(ledger.get("Carried"))
    location_text = " ; ".join(
        str(ledger.get(k, "")) for k in ("Stored", "Uncertain")
    )
    flagged = [
        item for item in _split_items(location_text)
        if re.search(r"\b(hidden|dropped|consumed|destroyed|lost)\b", item, re.IGNORECASE)
    ]
    if not carried or not flagged:
        return []
    filtered: List[str] = []
    removed: List[str] = []
    flagged_cores = [_item_core(x) for x in flagged]
    for item in carried:
        core = _item_core(item)
        duplicate = any(len(core & fc) >= 2 for fc in flagged_cores if core and fc)
        if duplicate:
            removed.append(item)
        else:
            filtered.append(item)
    if removed:
        ledger["Carried"] = "; ".join(filtered) if filtered else "—"
        parsed.ledger = ledger
        return ["removed_duplicate_carried:" + " | ".join(removed[:4])]
    return []


# Ledger category → canonical object_locations.status it represents.
# `Weapons` and `Supplies` can be either carried or stored — they don't
# pin a unique status, so they are NOT deduplicated against location truth;
# we only enforce uniqueness across the four mutually-exclusive states.
_LEDGER_STATUS_MAP = {
    "Carried": {"carried"},
    "Worn": {"worn"},
    "Stored": {"stored", "hidden"},
    "Uncertain": {"uncertain"},
}


def _apply_ledger_object_permanence(
    parsed: ParsedTurn,
    authoritative_state: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Cross-category deduplication of objects in the ledger.

    Ensures the SAME physical object identity never appears in two
    mutually-exclusive ledger categories simultaneously (e.g. listed
    as Carried AND Stored). The `authoritative_state` (typically the
    post-consolidation rolling_state) is treated as the source of truth
    for `object_locations`; if not provided we fall back to
    `parsed.rolling_state`. When no truth row exists we keep the most-final
    status (destroyed > consumed > dropped > hidden > stored > worn >
    carried > uncertain).
    """
    ledger = parsed.ledger or {}
    if not ledger:
        return []

    # Build canonical truth map from rolling_state.object_locations.
    truth: Dict[str, str] = {}
    rolling = (
        authoritative_state
        if isinstance(authoritative_state, dict)
        else (parsed.rolling_state if isinstance(parsed.rolling_state, dict) else {})
    )
    for row in (rolling.get("object_locations") or []):
        if not isinstance(row, dict):
            continue
        ident = _normalize_object_identity(row.get("object"))
        status = str(row.get("status", "")).strip().lower()
        if ident and status:
            truth[ident] = status

    # Pass A — collect per-category item lists (only categories we police).
    per_cat: Dict[str, List[str]] = {}
    for cat in _LEDGER_STATUS_MAP:
        items = _split_items(ledger.get(cat))
        if items:
            per_cat[cat] = items

    # Pass B — for each identity, find every (cat, item) it appears in; if
    # >1 hit, keep only the canonical category. If no truth row exists,
    # fall back to highest-priority status.
    sightings: Dict[str, List[Tuple[str, str]]] = {}
    for cat, items in per_cat.items():
        for raw in items:
            ident = _normalize_object_identity(raw)
            if not ident:
                continue
            sightings.setdefault(ident, []).append((cat, raw))

    removed: List[str] = []
    drops: Dict[str, set] = {cat: set() for cat in per_cat}

    for ident, hits in sightings.items():
        if len(hits) <= 1:
            continue
        canonical_status = truth.get(ident)
        winner_cat: Optional[str] = None
        if canonical_status:
            for cat, statuses in _LEDGER_STATUS_MAP.items():
                if canonical_status in statuses:
                    winner_cat = cat
                    break
        if winner_cat is None or all(c != winner_cat for c, _ in hits):
            # Fall back to most-final ledger status.
            priority = ("Uncertain", "Worn", "Carried", "Stored")  # least → most
            ordered = sorted(hits, key=lambda h: priority.index(h[0]) if h[0] in priority else -1)
            winner_cat = ordered[-1][0]
        for cat, raw in hits:
            if cat == winner_cat:
                continue
            drops[cat].add(raw)
            removed.append(f"{cat}:{raw}")

    if not removed:
        return []

    for cat, dropset in drops.items():
        if not dropset:
            continue
        survivors = [x for x in per_cat[cat] if x not in dropset]
        ledger[cat] = "; ".join(survivors) if survivors else "—"
    parsed.ledger = ledger
    return ["ledger_cross_category_dedup:" + " | ".join(removed[:6])]


_OBJECT_NAME_STOP = {
    "the", "a", "an", "and", "with", "of", "on", "in", "at", "to", "this", "that",
    "your", "my", "some", "small", "large", "tiny", "big", "old", "new", "broken",
    "damaged", "torn", "rusted", "worn", "metal", "wooden", "iron", "steel",
    "good", "bad", "half", "full", "empty", "near", "under", "over",
}


def _normalize_object_identity(name: Any) -> str:
    """Identity string aligned with memory.canonicalize_object_registry.

    Same normalisation used by the rolling-state canonicalizer so the
    ledger dedup honours the same identity contract. Robust to unclosed
    parens left over from sloppy ledger splits and to hyphenated tokens.
    Strips ledger "Stored" location prefix like "shelf — item".
    """
    if not name:
        return ""
    raw = str(name).lower()
    # Strip location prefix used in `Stored: [location] — item` rows so the
    # identity reflects only the item, not the container.
    raw = re.sub(r"^[^—\-]*[—–]\s*", "", raw)
    raw = re.sub(r"\(.*?(?:\)|$)", " ", raw)
    raw = re.sub(r"\bqty\s*:\s*[^,;)]+", " ", raw)
    raw = re.sub(r"\bcondition\s*:\s*[^,;)]+", " ", raw)
    raw = re.sub(r"[-_/]", " ", raw)
    words = re.findall(r"[a-z][a-z0-9]+", raw)
    tokens = [w.rstrip("s") for w in words if w not in _OBJECT_NAME_STOP]
    if not tokens:
        return str(name).strip().lower()[:40]
    return " ".join(sorted(set(tokens)))


# ==========================================================================
# P1-C — Room Audit (revisit reconciliation)
# ==========================================================================
# Persist a small per-room snapshot of known objects and stable features into
# rolling_state.known_rooms. On revisit, ensure objects that should still be
# there are not silently forgotten and that no contradictory invention slips
# through. This is INFORMATIONAL — we flag drift in state_guard_adjustments
# rather than rewrite prose. The system-prompt rule is the primary defence.

_ROOM_DRIFT_FLAG = "room_audit_drift"


def _room_key(name: Any) -> str:
    """Stable room identity (case- and whitespace-normalised)."""
    if not name:
        return ""
    raw = re.sub(r"\s+", " ", str(name).strip().lower())
    raw = re.sub(r"[^a-z0-9 \-/]", "", raw)
    return raw[:80]


def _current_room_label(parsed: ParsedTurn) -> str:
    """Best-effort current room label from <state>.Position."""
    state = parsed.state or {}
    pos = state.get("Position") or state.get("position") or ""
    # Position is freeform prose. Use the first clause as the room key.
    first = re.split(r"[,.;]", str(pos), maxsplit=1)[0]
    return _room_key(first)


def _apply_room_audit(
    parsed: ParsedTurn,
    rolling_state: Dict[str, Any],
    *,
    decay_turns: int = 24,
    max_rooms: int = 12,
) -> List[str]:
    """Update rolling_state.known_rooms with the current room's snapshot, and
    flag obvious drift (a revisited room whose previously-known objects have
    vanished without a state-changing reason).
    """
    if not isinstance(rolling_state, dict):
        return []
    room_label = _current_room_label(parsed)
    if not room_label:
        return []

    rooms = rolling_state.get("known_rooms")
    if not isinstance(rooms, list):
        rooms = []
    # Index by room key for fast lookup.
    by_key: Dict[str, Dict[str, Any]] = {}
    for r in rooms:
        if isinstance(r, dict) and r.get("key"):
            by_key[r["key"]] = r

    prior = by_key.get(room_label)
    truth_locs = rolling_state.get("object_locations") or []
    # Objects whose authoritative location matches THIS room.
    here_now: List[str] = []
    for row in truth_locs:
        if not isinstance(row, dict):
            continue
        where = _room_key(row.get("where"))
        status = str(row.get("status", "")).strip().lower()
        if status in {"destroyed", "consumed", "dropped"}:
            continue
        if where and (room_label in where or where in room_label):
            ident = _normalize_object_identity(row.get("object"))
            if ident:
                here_now.append(ident)

    adjustments: List[str] = []
    drift: List[str] = []
    if prior and isinstance(prior.get("objects"), list):
        prior_set = set(prior["objects"])
        now_set = set(here_now)
        # Drift = identity previously known here AND not present in here_now
        # AND has NO canonical truth row anywhere. If the object has ANY
        # current status row (carried/worn/dropped/stored elsewhere/etc),
        # it has been legitimately accounted for; not drift.
        all_known: set = set()
        for row in truth_locs:
            if isinstance(row, dict):
                ident = _normalize_object_identity(row.get("object"))
                if ident:
                    all_known.add(ident)
        for ident in prior_set - now_set:
            if ident not in all_known:
                drift.append(ident)
        if drift:
            adjustments.append(f"{_ROOM_DRIFT_FLAG}:{room_label}:" + ",".join(drift[:5]))

    # Upsert this room's snapshot.
    snapshot = {
        "key": room_label,
        "objects": here_now[:24],
        "last_visited_turn": (parsed.state or {}).get("turn") or prior.get("last_visited_turn") if prior else None,
    }
    by_key[room_label] = snapshot

    # Bound the registry: keep most recently touched up to max_rooms.
    rolling_state["known_rooms"] = list(by_key.values())[-max_rooms:]
    return adjustments


# ==========================================================================
# P1-D — Bounded NPC Memory + Faction Consequence Tick
# ==========================================================================
# Goal: lightweight local continuity. NPC memory entries are capped per-NPC
# and decay if they are MINOR and stale. Severity-tagged events
# (theft/violence/promise/betrayal/rescue) persist longer.

_MAJOR_EVENT_RE = re.compile(
    r"\b(?:theft|steal|stole|stolen|kill|killed|murder|assault|violence|"
    r"betray|betrayed|betrayal|promise|promised|oath|sworn|"
    r"rescue|rescued|saved|spared|gift|"
    r"witness|witnessed|debt|owe|owes|owed)\b",
    re.IGNORECASE,
)
_NPC_REMEMBERS_CAP = 5
_NPC_MEMORY_MAX_ENTRIES = 24
_NPC_MINOR_DECAY_TURNS = 12


def _classify_event_severity(text: str) -> str:
    if _MAJOR_EVENT_RE.search(text or ""):
        return "major"
    return "minor"


def _apply_npc_memory_bounds(
    rolling_state: Dict[str, Any],
    *,
    current_turn: int = 0,
) -> List[str]:
    """Bound and decay npc_memory:
      • cap each NPC's `remembers` list to the last N items (newest wins),
      • drop entries flagged minor that are older than N turns,
      • cap the total NPC list to a sensible upper bound.
    """
    if not isinstance(rolling_state, dict):
        return []
    memory = rolling_state.get("npc_memory")
    if not isinstance(memory, list) or not memory:
        return []

    adjustments: List[str] = []
    pruned_total = 0
    decayed_total = 0
    for npc in memory:
        if not isinstance(npc, dict):
            continue
        remembers = npc.get("remembers")
        if not isinstance(remembers, list):
            continue
        # Tag each entry with severity if not already tagged.
        tagged: List[Any] = []
        for entry in remembers:
            if isinstance(entry, dict):
                if "severity" not in entry:
                    entry["severity"] = _classify_event_severity(
                        str(entry.get("event") or entry.get("description") or "")
                    )
                if "since_turn" not in entry and current_turn:
                    entry["since_turn"] = current_turn
                # Drop stale minor entries.
                since = entry.get("since_turn") or 0
                if (
                    entry.get("severity") == "minor"
                    and current_turn
                    and (current_turn - int(since or 0)) > _NPC_MINOR_DECAY_TURNS
                ):
                    decayed_total += 1
                    continue
                tagged.append(entry)
            elif isinstance(entry, str):
                tagged.append({
                    "event": entry,
                    "severity": _classify_event_severity(entry),
                    "since_turn": current_turn or 0,
                })
        # Cap to most recent N.
        if len(tagged) > _NPC_REMEMBERS_CAP:
            # Major events bubble to the front so they aren't culled.
            tagged.sort(key=lambda e: (
                0 if (isinstance(e, dict) and e.get("severity") == "major") else 1,
                -int(e.get("since_turn") or 0) if isinstance(e, dict) else 0,
            ))
            pruned_total += len(tagged) - _NPC_REMEMBERS_CAP
            tagged = tagged[:_NPC_REMEMBERS_CAP]
        npc["remembers"] = tagged

    # Hard cap on number of tracked NPCs (least-recently-used drop).
    if len(memory) > _NPC_MEMORY_MAX_ENTRIES:
        memory.sort(key=lambda n: -int(
            max(
                (e.get("since_turn") if isinstance(e, dict) else 0) or 0
                for e in (n.get("remembers") or [{}])
            )
        ) if isinstance(n, dict) else 0)
        rolling_state["npc_memory"] = memory[:_NPC_MEMORY_MAX_ENTRIES]
    if pruned_total or decayed_total:
        adjustments.append(
            f"npc_memory:capped={pruned_total};decayed={decayed_total}"
        )
    return adjustments


_FACTION_THEME_PATTERNS = {
    "suspicion": re.compile(
        r"\b(theft|stole|stolen|steal|stealing|lie|lied|lying|tricked?|cheats?|cheated)\b",
        re.IGNORECASE,
    ),
    "guard_attention": re.compile(
        r"\b(violence|kill|killed|killing|murder|murdered|assault(?:ed)?|"
        r"attacks?|attacked|attacking|fight|fought|fighting|brawl(?:ed)?)\b",
        re.IGNORECASE,
    ),
    "goodwill": re.compile(
        r"\b(rescued?|rescuing|save[ds]?|saving|spared?|sparing|"
        r"helped?|helping|gifts?|gifted|gave|kindness)\b",
        re.IGNORECASE,
    ),
    "debt": re.compile(
        r"\b(promised?|promising|sworn|swore|oath|owe[ds]?|owing|"
        r"debt|debts|borrowed?|borrowing)\b",
        re.IGNORECASE,
    ),
}
_FACTION_TICK_TRIGGER = 2  # repeats needed to register


def _apply_faction_consequence_tick(
    rolling_state: Dict[str, Any],
) -> List[str]:
    """Lightweight, LOCAL faction tick. Counts theme repeats across
    npc_memory and bumps faction_pressure entries accordingly. No global
    propagation — only existing factions get nudged.
    """
    if not isinstance(rolling_state, dict):
        return []
    memory = rolling_state.get("npc_memory") or []
    factions = rolling_state.get("faction_pressure")
    if not isinstance(factions, list) or not factions or not memory:
        return []

    theme_counts: Dict[str, int] = {k: 0 for k in _FACTION_THEME_PATTERNS}
    for npc in memory:
        if not isinstance(npc, dict):
            continue
        for entry in (npc.get("remembers") or []):
            text = ""
            if isinstance(entry, dict):
                text = str(entry.get("event") or entry.get("description") or "")
            elif isinstance(entry, str):
                text = entry
            for theme, pat in _FACTION_THEME_PATTERNS.items():
                if pat.search(text):
                    theme_counts[theme] += 1

    nudges: List[str] = []
    for theme, count in theme_counts.items():
        if count < _FACTION_TICK_TRIGGER:
            continue
        for fac in factions:
            if not isinstance(fac, dict):
                continue
            tick = fac.setdefault("ticks", {})
            if isinstance(tick, dict):
                tick[theme] = int(tick.get(theme, 0)) + 1
        nudges.append(f"{theme}:{count}")

    if nudges:
        return [f"faction_tick:" + ";".join(nudges)]  # noqa: F541
    return []


_RUMOUR_MAX_CAP = 15
_RUMOUR_MAX_HOPS = 6

def _apply_delayed_consequence_tick(rolling_state: Dict[str, Any], current_turn: int) -> List[str]:
    """P2 - Deterministic delayed consequence evaluation."""
    if not isinstance(rolling_state, dict):
        return []
    
    delayed = rolling_state.get("delayed_consequences")
    if not isinstance(delayed, list):
        return []

    adjustments = []

    for i, csq in enumerate(delayed):
        if not isinstance(csq, dict):
            continue
            
        if csq.get("state") == "fired":
            continue

        trigger = csq.get("trigger")
        if not isinstance(trigger, dict):
            continue
            
        condition = trigger.get("condition")
        if not condition:
            continue
            
        should_fire = False
        
        if condition == "fire_on_turn":
            target = trigger.get("turn")
            if isinstance(target, int) and current_turn >= target:
                should_fire = True
        elif condition == "witness_count>=N":
            target = trigger.get("N")
            if isinstance(target, int):
                # Calculate scoped witness_count
                scope_key = None
                scope_val = None
                for key in ["tag", "subject", "theme", "event_type"]:
                    val = csq.get(key)
                    if val is None:
                        val = trigger.get(key)
                    if val is not None:
                        scope_key = key
                        scope_val = str(val).strip().lower()
                        break
                        
                local_witness_count = 0
                for npc in rolling_state.get("npc_memory", []):
                    if not isinstance(npc, dict):
                        continue
                    for mem in npc.get("remembers", []):
                        if not isinstance(mem, dict):
                            continue
                        
                        if scope_key:
                            mem_val = mem.get(scope_key)
                            if mem_val is not None and str(mem_val).strip().lower() == scope_val:
                                local_witness_count += 1
                                break
                        else:
                            # Legacy fallback
                            if "witness" in str(mem.get("event", "")).lower() or mem.get("severity") == "major":
                                local_witness_count += 1
                                break

                if local_witness_count >= target:
                    should_fire = True

        if should_fire:
            csq["state"] = "fired"
            csq["fired_turn"] = current_turn
            
            desc = csq.get("description") or csq.get("name") or "A delayed consequence has fired"
            unresolved = rolling_state.get("unresolved")
            if not isinstance(unresolved, list):
                unresolved = []
                rolling_state["unresolved"] = unresolved
            unresolved.append(f"FIRED CONSEQUENCE: {desc}")
            
            adjustments.append(f"delayed_fired:{i}")

    return adjustments


def _apply_rumour_propagation_tick(rolling_state: Dict[str, Any], current_turn: int) -> List[str]:
    """P2 - Factual rumour seeding and propagation."""
    if not isinstance(rolling_state, dict):
        return []
    
    rumours = rolling_state.get("rumours")
    if not isinstance(rumours, list):
        rumours = []
        rolling_state["rumours"] = rumours
        
    adjustments = []

    # 1. Seed rumours from major npc memory
    for npc in rolling_state.get("npc_memory", []):
        if not isinstance(npc, dict):
            continue
        for mem in npc.get("remembers", []):
            if not isinstance(mem, dict):
                continue
            if mem.get("severity") == "major":
                event = mem.get("event")
                if not event:
                    continue
                
                # Check if already seeded
                is_seeded = any(r.get("seed_event") == event for r in rumours if isinstance(r, dict))
                if not is_seeded:
                    rumours.append({
                        "summary": event,
                        "seed_event": event,
                        "spread_count": 0,
                        "heat_level": 1,
                        "delivered_factions": [],
                        "witnesses": [npc.get("name", "Unknown")],
                        "hops": 0,
                        "last_propagated_turn": current_turn,
                        "state": "active",
                        "turn_seeded": current_turn,
                        "original_severity": "major"
                    })
                    adjustments.append("rumour_seeded")

    # 2. Propagate active rumours
    for r in rumours:
        if not isinstance(r, dict):
            continue
        if r.get("state") != "active":
            continue
        
        # Idempotency check: only propagate once per turn
        if r.get("last_propagated_turn") == current_turn:
            continue
            
        r["last_propagated_turn"] = current_turn
        r["hops"] = r.get("hops", 0) + 1
        r["spread_count"] = r.get("spread_count", 0) + 1
        r["heat_level"] = r.get("heat_level", 1) + 1
        
        # Deliver to one new faction
        factions = rolling_state.get("faction_pressure")
        if isinstance(factions, list):
            delivered = r.get("delivered_factions", [])
            for fac in factions:
                if not isinstance(fac, dict):
                    continue
                fac_name = fac.get("name")
                if fac_name and fac_name not in delivered:
                    delivered.append(fac_name)
                    r["delivered_factions"] = delivered
                    
                    # Update faction tick
                    tick = fac.setdefault("ticks", {})
                    if isinstance(tick, dict):
                        tick["suspicion"] = tick.get("suspicion", 0) + 1
                    adjustments.append(f"rumour_delivered:{fac_name}")
                    break
        
        # Decay/Expire
        if r["hops"] >= _RUMOUR_MAX_HOPS:
            r["state"] = "expired"
            adjustments.append("rumour_expired")
            
    # 3. Cap
    if len(rumours) > _RUMOUR_MAX_CAP:
        # Keep active first, then newest
        rumours.sort(key=lambda x: (1 if x.get("state") == "active" else 0, x.get("turn_seeded", 0)), reverse=True)
        rolling_state["rumours"] = rumours[:_RUMOUR_MAX_CAP]
        adjustments.append("rumours_capped")

    return adjustments
# ==========================================================================
# F1 (P1.5) — Rolling-state STRING-FIELD hygiene
# ==========================================================================
# The narrative validator catches meta phrases in the player-facing prose,
# but the LLM can still bleed meta language into rolling_state STRING fields
# (e.g. scene="...probing system boundaries", objectives=["Maintain
# immersion"], recent_choice_signatures=["probe_system"]). These then re-enter
# the prompt and subtly bias future turns. We strip them here, post-merge.

# Fields scanned for meta leakage. Lists of strings AND scalar strings.
_HYGIENE_STRING_FIELDS = (
    "scene",
    "character",
    "world_clock",
    "objectives",
    "unresolved",
    "recent_beats",
    "recent_choice_signatures",
    "active_pressures",
    "simulation_hooks",
    "world_instability",
    "route_continuity",
    "archived",
)

# State-field meta is broader than narrative meta. State strings often
# describe game intent rather than world events, so we accept a wider net.
# These patterns are scanned IN ADDITION to _MECHANIC_WORD_RE and
# _SOFT_META_PHRASE_RE.
_STATE_FIELD_META_RE = re.compile(
    r"(?:"
    r"\bsystem(?:s)?\s+boundar(?:y|ies)\b|"
    r"\bsystem\s+boundaries\b|"
    r"\bhidden\s+\w+\s+mechanic(?:s)?\b|"           # "hidden narrative mechanics"
    r"\b(?:narrative|simulation|mechanical|immersion)\s+(?:concealment|protection|redirection|tension|mechanic(?:s)?|generator|boundary|hooks?|engine)\b|"
    r"\b(?:probe|test|maintain|understand|preserve|conceal)_\w+\b|"  # signature-style snake_case
    r"\bmaintain\s+immersion\b|\bimmersion\b|\bconcealment\b|"
    r"\bnarrative\s+limits?\b|\bnarrative\s+sentinel\b|"
    r"\btesting\s+(?:narrative|simulation|system|boundaries|limits)\b|"
    r"\b(?:hidden|invisible|underlying|internal)\s+(?:narrative|mechanic|simulation|system|logic)\w*\b"
    r")",
    re.IGNORECASE,
)


def _scrub_meta_from_text(text: str) -> Tuple[str, int]:
    """Replace meta/mechanic terms inside a string with `[…]` placeholders.

    Returns ``(scrubbed_text, hit_count)``. Uses the same regexes that the
    narrative validator uses PLUS a state-field-specific net so common
    state-string meta phrasing is also caught.
    """
    if not text or not isinstance(text, str):
        return text, 0
    hits = 0

    def _sub(match: "re.Match[str]") -> str:
        nonlocal hits
        hits += 1
        return "[…]"

    out = _MECHANIC_WORD_RE.sub(_sub, text)
    out = _SOFT_META_PHRASE_RE.sub(_sub, out)
    out = _STATE_FIELD_META_RE.sub(_sub, out)
    # Collapse repeated placeholders and double-spaces left by substitution.
    out = re.sub(r"(\[…\]\s*){2,}", "[…] ", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out, hits


def _apply_rolling_state_hygiene(rolling_state: Dict[str, Any]) -> List[str]:
    """Scrub meta language from rolling_state string fields. Mutates in place.

    Bounded:
      • Only touches the curated `_HYGIENE_STRING_FIELDS` list.
      • Leaves non-string values untouched.
      • Drops a list entry entirely if scrubbing leaves it empty.
    """
    if not isinstance(rolling_state, dict):
        return []
    total_hits = 0
    fields_touched: List[str] = []
    for key in _HYGIENE_STRING_FIELDS:
        val = rolling_state.get(key)
        if isinstance(val, str):
            scrubbed, hits = _scrub_meta_from_text(val)
            if hits:
                rolling_state[key] = scrubbed
                total_hits += hits
                fields_touched.append(key)
        elif isinstance(val, list):
            new_list: List[Any] = []
            field_hits = 0
            for item in val:
                if isinstance(item, str):
                    scrubbed, hits = _scrub_meta_from_text(item)
                    field_hits += hits
                    if scrubbed and scrubbed != "[…]":
                        new_list.append(scrubbed)
                else:
                    new_list.append(item)
            if field_hits:
                rolling_state[key] = new_list
                total_hits += field_hits
                fields_touched.append(key)
    if total_hits:
        return [f"rolling_state_hygiene:fields={','.join(fields_touched)};hits={total_hits}"]
    return []



# ======================================================================
# MESSAGE BUILDER + LLM CALL
# ======================================================================
def _summarise_turn_for_assistant(turn: Dict[str, Any]) -> str:
    """Reconstruct a faithful assistant message from a stored turn.

    Keeps narrative / choices / state / ledger so the engine remains
    grounded in prior continuity. Truncates very long narratives.
    """
    parts: List[str] = []

    narrative = turn.get("narrative") or ""
    if narrative:
        if len(narrative) > 1800:
            narrative = narrative[:1800].rstrip() + "…"
        parts.append(f"<narrative>\n{narrative}\n</narrative>")

    choices = turn.get("choices") or []
    if choices:
        choice_lines = "\n".join(
            f"{c.get('label','?')}. {c.get('text','')}" for c in choices
        )
        parts.append(f"<choices>\n{choice_lines}\n</choices>")

    state = turn.get("state") or {}
    if state:
        state_lines = "\n".join(f"{k}: {v}" for k, v in state.items())
        parts.append(f"<state>\n{state_lines}\n</state>")

    ledger = turn.get("ledger") or {}
    if ledger:
        ledger_lines = "\n".join(f"{k}: {v}" for k, v in ledger.items() if v)
        if ledger_lines:
            parts.append(f"<ledger>\n{ledger_lines}\n</ledger>")

    return "\n\n".join(parts)


async def _build_messages(
    session: Dict[str, Any],
    user_text: str,
    memory_depth: int,
    history_window_fallback: int,
) -> List[Dict[str, str]]:
    """Construct an OpenAI-style messages array.

    Compression strategy:
      • System prompt
      • Latest <rolling_state> JSON from session (authoritative continuity)
      • Last `memory_depth` recent turns replayed verbatim for narrative tone
      • New user message

    Falls back to the legacy "replay last N turns" if no rolling state exists
    (e.g. very first turn, or an old session created before this upgrade).
    """
    session_id = session["id"]
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": STORY_ENGINE_SYSTEM_PROMPT},
    ]

    rolling = session.get("rolling_state")

    # Pull recent turns. If we have rolling_state, we only need a small number
    # for tone/voice continuity. If not, we fall back to the larger window.
    take = max(1, memory_depth) if rolling else history_window_fallback
    recent_desc = await db.turns.find(
        {"session_id": session_id}, {"_id": 0}
    ).sort("turn_number", -1).to_list(length=take)
    prior_turns = list(reversed(recent_desc))

    for t in prior_turns:
        player_action = t.get("player_action")
        if player_action:
            messages.append({"role": "user", "content": player_action})
        assistant_text = _summarise_turn_for_assistant(t)
        if assistant_text:
            messages.append({"role": "assistant", "content": assistant_text})

    # Inject the compressed rolling state IMMEDIATELY before the new user turn
    if rolling:
        # Ch 31.11 — preventive half of the Anti-Hallucination Gateway: tell the
        # model the engine-authoritative facts it may not contradict.
        truth_block = gateway.build_immutable_truth_block(rolling)
        prior_state_block = (
            "<prior_state>\n"
            + _json.dumps(rolling, indent=2, ensure_ascii=False)
            + "\n</prior_state>\n\n"
        )
        prefix = (truth_block + "\n\n") if truth_block else ""
        user_text = prefix + prior_state_block + user_text

    messages.append({"role": "user", "content": user_text})
    return messages


async def _generate_turn(
    session: Dict[str, Any], user_text: str
) -> Tuple[str, Dict[str, Any]]:
    """Centralised call: resolve admin settings + per-session mode, build messages, call aiService.

    Returns ``(raw_content, meta)`` where meta contains model_used, telemetry,
    fallback_events, and attempts_per_model from the AI service.
    """
    settings = await get_ai_settings()
    mode = (session.get("mode") or settings.get("default_mode") or DEFAULT_MODE).lower()
    profile = MODE_PROFILES.get(mode, MODE_PROFILES["advanced"])

    memory_depth = int(settings.get("memory_depth", DEFAULT_MEMORY_DEPTH))
    history_window = int(settings.get("history_window", DEFAULT_HISTORY_WINDOW))

    # ---- Cost-mode aware token cap ----
    cost_mode = (
        session.get("cost_mode")
        or settings.get("cost_mode")
        or DEFAULT_COST_MODE
    ).lower()
    max_tokens = int(settings.get("max_tokens", DEFAULT_MAX_TOKENS))
    cap = profile.get("max_tokens_cap")
    if cap:
        max_tokens = min(max_tokens, cap)
    if cost_mode == "low":
        max_tokens = min(max_tokens, LOW_COST_MAX_TOKENS)

    # ---- Session-level model lock + fallback chain ----
    requested_model = (
        session.get("active_model")
        or settings.get("model")
        or DEFAULT_MODEL
    )
    fallback_chain = (
        session.get("fallback_chain")
        or settings.get("fallback_models")
        or list(FALLBACK_MODELS)
    )

    # ---- Hints embedded into the upcoming user message ----
    hint_lines: List[str] = []
    primary_pref = settings.get("model") or DEFAULT_MODEL
    if (
        session.get("active_model")
        and session.get("active_model") != primary_pref
        and session.get("model_switches")
    ):
        # A fallback has already been activated on this session — protect continuity.
        hint_lines.append(
            "[FALLBACK_ACTIVE: maintain current tone, scene continuity, NPC memory consistency, "
            "suppress repetitive exposition, suppress system leakage. Do NOT regenerate prior turns.]"
        )
    if cost_mode == "low":
        hint_lines.append(
            "[COST_MODE: LOW — produce shorter, denser prose (closer to 2 paragraphs). "
            "Preserve causality, consequence chains, and continuity. Do not drop state.]"
        )
    augmented_user_text = (
        ("\n".join(hint_lines) + "\n\n" + user_text) if hint_lines else user_text
    )

    messages = await _build_messages(
        session,
        augmented_user_text,
        memory_depth=memory_depth,
        history_window_fallback=history_window,
    )

    # ---- Context Budget Governor v3.9 ----
    # Estimate the prompt size BEFORE calling the model and trim low-priority
    # context if we would exceed the active budget. Protected content (active
    # scene, current condition, consequence chains, recent turns) is never
    # touched — see memory.enforce_context_budget for the strict policy.
    budget_tokens = resolve_context_budget(cost_mode=cost_mode, mode=mode)
    # Protect the same number of prior-replay messages we already chose to send.
    protected_recent_msgs = max(1, memory_depth) * 2  # user+assistant per turn
    messages, budget_diag = enforce_context_budget(
        messages,
        budget_tokens=budget_tokens,
        protected_recent_msgs=protected_recent_msgs,
    )

    result = await chat_completion_with_meta(
        messages=messages,
        primary_model=requested_model,
        fallback_chain=fallback_chain,
        temperature=settings.get("temperature"),
        max_tokens=max_tokens,
        max_retries_per_model=MAX_RETRIES,
    )
    # Bolt the budget diagnostics onto the returned meta so the route can
    # surface them in the per-turn debug payload.
    result["budget"] = budget_diag
    return result["content"], result


# ----------------------------------------------------------------------
# Output validation + single-shot retry
# ----------------------------------------------------------------------
MAX_NARRATION_CHARS = 1200
MAX_PARAGRAPHS = 4
MIN_CHOICES = 4
MAX_CHOICES = 6
REQUIRED_CHOICE_LABELS = {"A", "B", "C", "D"}

# Mechanic / engine-debug labels that must never appear in player-facing prose.
_LEAK_LABEL_RE = re.compile(
    r"^\s*(?:Roll|Modifiers?|Final|Outcome|Active\s*systems?|"
    r"Consequence(?:\s*budget)?|Delayed\s*trigger(?:\s*stored)?|"
    r"Latent\s*trigger(?:\s*stored)?|Scale|Pressure\s*horizon|"
    r"Rolling\s*state|Trigger|DEV[_\s-]?MODE)\s*[:=]",
    re.IGNORECASE | re.MULTILINE,
)
_ENGINE_TAG_IN_NARRATIVE_RE = re.compile(
    r"<\s*/?\s*(?:rolling_state|debug|prior_state|state|ledger|choices|scenario)\b",
    re.IGNORECASE,
)
_MECHANIC_WORD_RE = re.compile(
    r"\b(?:d20|rolls?|rolled|rolling\s+for|modifiers?|hidden\s+mechanics?|"
    r"invisible\s+mechanics?|delayed\s+triggers?|latent\s+triggers?|"
    r"active\s+systems?|consequence\s+budget|pressure\s+horizon|"
    r"scale\s+lock|world\s+tick|rolling\s+state|debug|developer\s+mode|"
    r"simulation\s+engine|JSON|"
    # P1-A soft-meta additions
    r"parser|state\s+machine|runtime|memory\s+structure|"
    r"hidden\s+rolls?|concealment\s+mandate|game\s+logic|"
    r"narrative\s+generator|AI\s+reasoning|prompt\s+(?:engine|model|system|template)"
    r")\b",
    re.IGNORECASE,
)
# Phrase-level soft-meta leakage. These words have valid in-world uses
# ("steam engine", "immune system", "ration token") so we only block them
# when they appear in clearly meta phrasing.
_SOFT_META_PHRASE_RE = re.compile(
    r"\b(?:"
    r"the\s+(?:system|engine|simulation|runtime|parser|mechanics)|"
    r"this\s+(?:system|engine|simulation|runtime|parser)|"
    r"underlying\s+(?:system|engine|mechanics?|logic)|"
    r"internal\s+(?:system|mechanics?|state|logic)|"
    r"my\s+(?:prompt|programming|model|reasoning)|"
    r"as\s+(?:an?\s+)?(?:AI|language\s+model|assistant)|"
    r"my\s+(?:tokens?|context\s+window)|"
    r"(?:meta|out[\s-]of[\s-]character)\s+(?:commentary|narration|aside)"
    r")\b",
    re.IGNORECASE,
)
_FAKE_CHOICE_RE = re.compile(
    r"\b(?:not\s+allowed|not\s+yet|unavailable|locked|blocked|disabled|"
    r"can(?:not|'t)\s+|won't\s+work|impossible\s+to)\b",
    re.IGNORECASE,
)

# --------------------------------------------------------------------------
# P1-B — Direct Inspection Enforcement
# --------------------------------------------------------------------------
# DEMAND verbs only — verbs that require a quantitative or itemized answer.
# Weak verbs like "pick up", "handle", "read", "look at" produce legitimately
# evocative prose without a count, so we exclude them to avoid false-positives
# (regression: F3 from 20-turn live QA — "pick up the knife" was wrongly
# flagged when prose contained a single unrelated hedge word).
_INSPECTION_VERB_RE = re.compile(
    r"\b(?:count|counts|counting|"
    r"open|opens|opening|"
    r"search|searches|searching|"
    r"check(?:s|ing)?|examine(?:s|d|ing)?|inspect(?:s|ed|ing)?|"
    r"tally(?:s|ies|ing)?|empty(?:s|ies|ing)?\s+(?:out|the)|"
    r"peek(?:s|ed|ing)?\s+(?:inside|in|under|behind|through|into)|"
    r"peer(?:s|ed|ing)?\s+(?:inside|in|under|behind|through|into)|"
    r"look\s+(?:inside|in|under|behind|through|into))\b",
    re.IGNORECASE,
)
# Vague hedging phrases that should NOT appear when the player directly
# inspected something accessible.
_VAGUE_RESOLUTION_RE = re.compile(
    r"\b(?:uncertain|possibly|perhaps|maybe|seems?\s+to|"
    r"appears?\s+to|hard\s+to\s+tell|hard\s+to\s+say|"
    r"difficult\s+to\s+(?:tell|say|determine|make\s+out)|"
    r"can'?t\s+(?:quite|really)\s+tell|"
    r"unclear|some\s+kind\s+of|some\s+sort\s+of|"
    r"might\s+(?:be|contain|hold)|there\s+may\s+be|"
    r"you\s+(?:think|believe|suspect)\s+there\s+(?:may|might)\s+be)\b",
    re.IGNORECASE,
)
# Justifications that legitimately PREVENT concrete resolution.
_INSPECTION_JUSTIFICATION_RE = re.compile(
    r"\b(?:dark|darkness|pitch\s+black|gloom|shadow|shadows|"
    r"smoke|fog|mist|dust|haze|"
    r"obstructed|blocked|covered|sealed|jammed|locked|"
    r"damaged|cracked|shattered|broken|warped|"
    r"too\s+(?:far|distant)|distant|across\s+the\s+(?:room|street)|"
    r"interrupted|footsteps|shout|gunshot|noise|alarm|"
    r"running\s+out\s+of\s+time|no\s+time|seconds?\s+to|"
    r"trembling|shaking|hands?\s+shaking|"
    r"blood\s+in\s+(?:your|the)\s+eyes?|tears?\s+blur|"
    r"hidden|concealed|wrapped|buried)\b",
    re.IGNORECASE,
)


def _check_direct_inspection_violation(
    parsed: ParsedTurn, player_action: Optional[str]
) -> Optional[str]:
    """Return a reason string if player directly inspected something but the
    narrative dodged with vague phrasing without an in-world justification.

    This is bounded — we only flag when ALL three conditions hold:
      1. Player action contains an inspection verb.
      2. Narrative contains a vague-resolution phrase.
      3. Narrative contains NO justification phrase (darkness/distance/etc).
    """
    if not player_action:
        return None
    if not _INSPECTION_VERB_RE.search(player_action):
        return None
    joined = "\n".join(parsed.paragraphs or [])
    if not _VAGUE_RESOLUTION_RE.search(joined):
        return None
    if _INSPECTION_JUSTIFICATION_RE.search(joined):
        return None
    return "direct inspection result is vague without in-world justification"


def _validate_parsed(
    parsed: ParsedTurn,
    player_action: Optional[str] = None,
) -> Tuple[bool, str]:
    """Return (ok, reason) for player-facing turn validation."""
    # 1. Choices present and labelled A-D minimum, count 4-6
    labels = {(c.get("label") or "").upper() for c in (parsed.choices or [])}
    if not REQUIRED_CHOICE_LABELS.issubset(labels):
        missing = sorted(REQUIRED_CHOICE_LABELS - labels)
        return False, f"missing required choice labels: {','.join(missing)}"
    if not (MIN_CHOICES <= len(parsed.choices) <= MAX_CHOICES):
        return (
            False,
            f"choice count {len(parsed.choices)} outside required {MIN_CHOICES}-{MAX_CHOICES}",
        )

    paragraphs = parsed.paragraphs or []

    # 2. Paragraph count cap
    if len(paragraphs) == 0:
        return False, "no narrative paragraphs"
    if len(paragraphs) > MAX_PARAGRAPHS:
        return False, f"narration has {len(paragraphs)} paragraphs (max {MAX_PARAGRAPHS})"

    # 3. Total narration length cap (1200 chars).
    total_chars = sum(len(p) for p in paragraphs)
    if total_chars > MAX_NARRATION_CHARS:
        return False, f"narration {total_chars} chars exceeds {MAX_NARRATION_CHARS}"

    # 4. No leaked engine tags / mechanic labels inside narrative
    joined = "\n".join(paragraphs)
    if _ENGINE_TAG_IN_NARRATIVE_RE.search(joined):
        return False, "engine tag leaked into narrative"
    if _LEAK_LABEL_RE.search(joined):
        return False, "mechanic label leaked into narrative"
    if _MECHANIC_WORD_RE.search(joined):
        return False, "mechanic terminology leaked into narrative"
    if _SOFT_META_PHRASE_RE.search(joined):
        return False, "soft meta phrasing leaked into narrative"

    for c in parsed.choices or []:
        if _FAKE_CHOICE_RE.search(c.get("text") or ""):
            return False, "fake or closed-off choice wording"

    # 5. P1-B — direct inspection must resolve concretely
    inspection_reason = _check_direct_inspection_violation(parsed, player_action)
    if inspection_reason:
        return False, inspection_reason

    return True, ""


_RETRY_INSTRUCTION = (
    "[VALIDATION_RETRY: {reason}]\n"
    "Rewrite the previous response in valid player-facing format with "
    "2–4 short paragraphs (under 1200 characters total) and 4–6 A–F choices. "
    "Every choice must be on its own line beginning with the letter and a period "
    "(A. B. C. D. and optionally E. F.). "
    "Do NOT include any Roll / Modifiers / Final / Active systems / Delayed trigger / "
    "Latent trigger / Scale text anywhere outside the <debug> block. "
    "Do NOT echo mechanic-probing words from the player (roll, modifier, trigger, hidden system, debug, simulation, JSON); translate the attempt into in-world uncertainty, suspicion, stress, superstition, or manipulation. "
    "Do NOT echo <prior_state>. Output ONLY the required tag blocks "
    "(<narrative>, <choices>, <state>, <ledger>, <rolling_state>"
    "{debug_clause}). Choices must cover meaningfully different intents — include a "
    "cautious option, a direct/risky option, an investigative option, and a "
    "social/communication option where the scene supports it."
)

# Ch 31.5 — correction re-prompt when prose contradicts engine-authoritative truth.
_HALLUCINATION_RETRY_INSTRUCTION = (
    "[TRUTH_VIOLATION: {reason}]\n"
    "Your narrative contradicted established, FINAL facts of this world. "
    "Rewrite the response so it does NOT contradict them: a destroyed or consumed "
    "object is gone forever (it cannot be held, used, drawn, worn, or found intact); "
    "a dead character cannot speak, move, or act (reference them only as a corpse, "
    "memory, or absence). Keep the same scene, tone, and continuity, but obey the "
    "established truth. Output ONLY the required tag blocks (<narrative>, <choices>, "
    "<state>, <ledger>, <rolling_state>{debug_clause}). Do NOT echo <prior_state> or "
    "<established_truth>."
)


def _full_validate(
    parsed: ParsedTurn,
    session: Dict[str, Any],
    player_action: Optional[str],
) -> Tuple[bool, str, str]:
    """Format validation first, then Anti-Hallucination prose check.

    Returns ``(ok, reason, kind)`` where kind ∈ {"format", "hallucination", "ok"}.
    """
    ok, reason = _validate_parsed(parsed, player_action=player_action)
    if not ok:
        return False, reason, "format"
    contradictions = gateway.detect_prose_contradictions(
        session.get("rolling_state"), parsed, player_action
    )
    if contradictions:
        return False, "; ".join(contradictions[:3]), "hallucination"
    return True, "", "ok"


async def _generate_validated_turn(
    session: Dict[str, Any], user_text: str,
    player_action: Optional[str] = None,
) -> Tuple[ParsedTurn, str, Dict[str, Any]]:
    """Call the LLM, validate the parsed turn, and retry ONCE on failure.

    Returns ``(parsed, raw, meta)`` where meta aggregates model_used,
    fallback_events across both attempts, telemetry, and validation diagnostics.
    """
    raw, meta = await _generate_turn(session, user_text)
    parsed = parse_turn(raw)
    ok, reason, kind = _full_validate(parsed, session, player_action)
    if ok:
        return parsed, raw, meta

    dev_on = "[DEV_MODE: ON]" in user_text
    debug_clause = ", <debug>" if dev_on else ""
    if kind == "hallucination":
        retry_note = _HALLUCINATION_RETRY_INSTRUCTION.format(
            reason=reason, debug_clause=debug_clause
        )
    else:
        retry_note = _RETRY_INSTRUCTION.format(reason=reason, debug_clause=debug_clause)
    logger.info("Turn validation failed (%s/%s) — retrying once", kind, reason)

    # Build a proper conversation: original history + bad output + corrective user turn.
    settings = await get_ai_settings()
    mode = (session.get("mode") or settings.get("default_mode") or DEFAULT_MODE).lower()
    profile = MODE_PROFILES.get(mode, MODE_PROFILES["advanced"])
    memory_depth = int(settings.get("memory_depth", DEFAULT_MEMORY_DEPTH))
    history_window = int(settings.get("history_window", DEFAULT_HISTORY_WINDOW))
    cost_mode = (
        session.get("cost_mode")
        or settings.get("cost_mode")
        or DEFAULT_COST_MODE
    ).lower()
    max_tokens = int(settings.get("max_tokens", DEFAULT_MAX_TOKENS))
    cap = profile.get("max_tokens_cap")
    if cap:
        max_tokens = min(max_tokens, cap)
    if cost_mode == "low":
        max_tokens = min(max_tokens, LOW_COST_MAX_TOKENS)

    try:
        messages = await _build_messages(
            session,
            user_text,
            memory_depth=memory_depth,
            history_window_fallback=history_window,
        )
        # Show the model exactly what it produced, then ask it to rewrite.
        messages.append({"role": "assistant", "content": raw[:6000]})
        messages.append({"role": "user", "content": retry_note})

        # Apply context budget BEFORE the retry call too.
        cost_mode_for_budget = (
            session.get("cost_mode")
            or settings.get("cost_mode")
            or DEFAULT_COST_MODE
        ).lower()
        budget_tokens_retry = resolve_context_budget(
            cost_mode=cost_mode_for_budget, mode=mode
        )
        protected_recent_msgs = max(1, memory_depth) * 2 + 2  # +2 = bad output + retry note
        messages, retry_budget_diag = enforce_context_budget(
            messages,
            budget_tokens=budget_tokens_retry,
            protected_recent_msgs=protected_recent_msgs,
        )

        # Retry stays on the model that just answered; provider-level fallback
        # is still permitted if the retry call itself fails.
        primary_for_retry = meta.get("model_used") or settings.get("model")
        fallback_chain = (
            session.get("fallback_chain")
            or settings.get("fallback_models")
            or list(FALLBACK_MODELS)
        )

        result2 = await chat_completion_with_meta(
            messages=messages,
            primary_model=primary_for_retry,
            fallback_chain=fallback_chain,
            temperature=settings.get("temperature"),
            max_tokens=max_tokens,
            max_retries_per_model=MAX_RETRIES,
        )
        result2["budget"] = retry_budget_diag
        raw2 = result2["content"]
        parsed2 = parse_turn(raw2)
        ok2, reason2, kind2 = _full_validate(parsed2, session, player_action)

        combined_meta: Dict[str, Any] = {
            "model_used": result2["model_used"],
            "model_requested": meta.get("model_requested"),
            "telemetry": result2.get("telemetry"),
            "fallback_events": list(meta.get("fallback_events") or [])
            + list(result2.get("fallback_events") or []),
            "attempts_per_model": result2.get("attempts_per_model"),
            "validation_retried": True,
            "validation_retry_kind": kind,
            "validation_first_fail": reason,
            "validation_second_fail": None if ok2 else reason2,
            "budget": result2.get("budget"),
        }

        if ok2:
            return parsed2, raw2, combined_meta

        logger.warning(
            "Retry still invalid (%s/%s) — using best-available output",
            kind2,
            reason2,
        )
        if len(parsed2.choices or []) > len(parsed.choices or []):
            return parsed2, raw2, combined_meta

        first_with_retry = dict(meta)
        first_with_retry["validation_retried"] = True
        first_with_retry["validation_first_fail"] = reason
        first_with_retry["validation_second_fail"] = reason2
        first_with_retry["fallback_events"] = combined_meta["fallback_events"]
        return parsed, raw, first_with_retry
    except Exception as exc:
        logger.warning("Retry call raised %s — falling back to first attempt", exc)
        recovered = dict(meta)
        recovered["validation_retried"] = True
        recovered["validation_first_fail"] = reason
        recovered["retry_exception"] = str(exc)[:240]
        return parsed, raw, recovered


# ======================================================================
# ROUTES
# ======================================================================
def _meta_into_debug(
    base: Optional[Dict[str, str]], meta: Dict[str, Any]
) -> Dict[str, str]:
    """Merge engine telemetry from chat_completion_with_meta into the turn.debug dict.

    This dict is only surfaced behind the Developer Mode unlock — never shown to
    standard players (see _maybe_sanitise_turn).
    """
    debug: Dict[str, str] = dict(base) if base else {}
    if meta.get("model_used"):
        debug["model_used"] = str(meta["model_used"])
    if meta.get("model_requested"):
        debug["model_requested"] = str(meta["model_requested"])
    tel = meta.get("telemetry") or {}
    if tel.get("latency_ms") is not None:
        debug["latency_ms"] = f"{tel['latency_ms']}"
    if tel.get("total_tokens") is not None:
        debug["tokens_total"] = str(tel["total_tokens"])
    if tel.get("prompt_tokens") is not None:
        debug["tokens_prompt"] = str(tel["prompt_tokens"])
    if tel.get("completion_tokens") is not None:
        debug["tokens_completion"] = str(tel["completion_tokens"])
    if tel.get("provider"):
        debug["provider"] = str(tel["provider"])
    if tel.get("status"):
        debug["provider_status"] = str(tel["status"])
    fe = meta.get("fallback_events") or []
    if fe:
        debug["fallback_events"] = str(len(fe))
        path = [fe[0].get("from") or ""] + [e.get("to") or "" for e in fe]
        debug["fallback_path"] = " → ".join(p for p in path if p)
        debug["fallback_reason"] = str(fe[-1].get("reason") or "")
    if meta.get("validation_retried"):
        debug["validation_retried"] = "yes"
    if meta.get("validation_retry_kind"):
        debug["validation_retry_kind"] = str(meta["validation_retry_kind"])
    if meta.get("validation_first_fail"):
        debug["validation_first_fail"] = str(meta["validation_first_fail"])
    if meta.get("validation_second_fail"):
        debug["validation_second_fail"] = str(meta["validation_second_fail"])
    # ---- Context Budget Governor v3.9 diagnostics ----
    budget = meta.get("budget") or {}
    for key, label in (
        ("estimated_prompt_tokens", "estimated_prompt_tokens"),
        ("context_budget_tokens", "context_budget_tokens"),
        ("context_over_budget", "context_over_budget"),
        ("context_trimmed", "context_trimmed"),
        ("trim_reason", "trim_reason"),
        ("estimated_tokens_removed", "estimated_tokens_removed"),
        ("protected_state_items_count", "protected_state_items_count"),
    ):
        if key in budget:
            debug[label] = str(budget[key])
    return debug


async def _persist_model_lock(
    session_id: str, meta: Dict[str, Any], at_turn: int
) -> None:
    """Record fallback events and update active_model on the session."""
    fe = list(meta.get("fallback_events") or [])
    update_set: Dict[str, Any] = {}
    if meta.get("model_used"):
        update_set["active_model"] = meta["model_used"]
    ops: Dict[str, Any] = {}
    if update_set:
        ops["$set"] = update_set
    if fe:
        now = datetime.now(timezone.utc).isoformat()
        entries = [
            {
                "from_model": e.get("from"),
                "to_model": e.get("to"),
                "reason": e.get("reason"),
                "message": e.get("message"),
                "at_turn": at_turn,
                "ts": now,
            }
            for e in fe
        ]
        ops["$push"] = {"model_switches": {"$each": entries}}
        logger.warning(
            "Session %s model switch: %s (turn %s)",
            session_id,
            " → ".join([fe[0].get("from") or ""] + [e.get("to") or "" for e in fe]),
            at_turn,
        )
    if ops:
        await db.sessions.update_one({"id": session_id}, ops)


@api_router.get("/")
async def root():
    return {"message": "Dice Reaction Story Engine v3.3"}


@api_router.get("/health")
async def health():
    settings = await get_ai_settings()
    return {
        "status": "ok",
        "llm_configured": ai_is_configured(),
        "provider": "openrouter",
        "model": settings.get("model"),
        "temperature": settings.get("temperature"),
        "max_tokens": settings.get("max_tokens"),
        "history_window": settings.get("history_window"),
        "default_mode": settings.get("default_mode"),
        "compression_level": settings.get("compression_level"),
        "memory_depth": settings.get("memory_depth"),
        "developer_mode": settings.get("developer_mode", False),
        "fallback_models": settings.get("fallback_models") or list(FALLBACK_MODELS),
        "cost_mode": settings.get("cost_mode") or DEFAULT_COST_MODE,
        "runtime_config": get_runtime_config(),
    }


@api_router.get("/admin/runtime")
async def admin_runtime():
    """Snapshot of the AI routing runtime config (env + DB-resolved settings)."""
    if not ENABLE_DEBUG_PANEL:
        raise HTTPException(status_code=404, detail="Debug panel disabled")
    settings = await get_ai_settings()
    return {
        "active_default_model": settings.get("model"),
        "fallback_chain": settings.get("fallback_models") or list(FALLBACK_MODELS),
        "cost_mode": settings.get("cost_mode") or DEFAULT_COST_MODE,
        "developer_mode": settings.get("developer_mode", False),
        "context_budgets": {
            "normal": NORMAL_CONTEXT_BUDGET_TOKENS,
            "low_cost": LOW_COST_CONTEXT_BUDGET_TOKENS,
            "advanced": ADVANCED_CONTEXT_BUDGET_TOKENS,
        },
        "runtime_config": get_runtime_config(),
    }


@api_router.get("/admin/session/{session_id}/diagnostics")
async def admin_session_diagnostics(session_id: str):
    """Per-session runtime diagnostics: active model, switch history, cost mode."""
    if not ENABLE_DEBUG_PANEL:
        raise HTTPException(status_code=404, detail="Debug panel disabled")
    session = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    latest = (
        await db.turns.find({"session_id": session_id}, {"_id": 0})
        .sort("turn_number", -1)
        .to_list(length=1)
    )
    last_debug = (latest[0].get("debug") if latest else None) or {}
    return {
        "session_id": session_id,
        "active_model": session.get("active_model"),
        "fallback_chain": session.get("fallback_chain")
        or list(FALLBACK_MODELS),
        "cost_mode": session.get("cost_mode") or DEFAULT_COST_MODE,
        "model_switches": session.get("model_switches") or [],
        "turn_count": session.get("turn_count", 0),
        "rolling_state_updated_at": (
            session.get("rolling_state_updated_at").isoformat()
            if isinstance(session.get("rolling_state_updated_at"), datetime)
            else session.get("rolling_state_updated_at")
        ),
        "compression": {
            k.replace("compression_", ""): v
            for k, v in (last_debug or {}).items()
            if k.startswith("compression_")
        },
        "context_budget": {
            k: v
            for k, v in (last_debug or {}).items()
            if k in (
                "estimated_prompt_tokens",
                "context_budget_tokens",
                "context_over_budget",
                "context_trimmed",
                "trim_reason",
                "estimated_tokens_removed",
                "protected_state_items_count",
            )
        },
        "latest_turn_debug": last_debug,
    }


@api_router.get("/scenarios")
async def list_scenarios():
    return {"scenarios": get_scenarios()}


# -------- Admin: AI settings ------------------------------------------------
@api_router.get("/admin/settings")
async def admin_get_settings():
    settings = await get_ai_settings()
    return {
        "settings": settings,
        "models": get_supported_models(),
        "modes": ["basic", "advanced"],
        "compression_levels": ["light", "standard", "aggressive"],
        "limits": {
            "temperature": {"min": 0.0, "max": 2.0, "step": 0.05},
            "max_tokens": {"min": 256, "max": 16384, "step": 128},
            "history_window": {"min": 4, "max": 200, "step": 2},
            "memory_depth": {"min": 0, "max": 10, "step": 1},
        },
        "defaults": {
            **get_default_settings(),
            "default_mode": DEFAULT_MODE,
            "compression_level": DEFAULT_COMPRESSION_LEVEL,
            "memory_depth": DEFAULT_MEMORY_DEPTH,
        },
        "provider_configured": ai_is_configured(),
    }


@api_router.post("/admin/settings")
async def admin_post_settings(req: AdminSettingsRequest):
    # Validate model is in supported list (if provided)
    if req.model is not None:
        supported_ids = {m["id"] for m in get_supported_models()}
        if req.model not in supported_ids:
            raise HTTPException(status_code=400, detail=f"Unsupported model: {req.model}")
    if req.default_mode is not None and req.default_mode not in ("basic", "advanced"):
        raise HTTPException(status_code=400, detail="default_mode must be 'basic' or 'advanced'")
    if req.compression_level is not None and req.compression_level not in ("light", "standard", "aggressive"):
        raise HTTPException(status_code=400, detail="compression_level must be light|standard|aggressive")

    patch = req.model_dump(exclude_none=True)
    updated = await set_ai_settings(patch)
    return {"settings": updated}


@api_router.get("/admin/models")
async def admin_list_models():
    return {"models": get_supported_models()}


# -------- Story flow --------------------------------------------------------
@api_router.post("/story/new")
async def new_story(req: NewStoryRequest):
    settings = await get_ai_settings()
    scenario = get_scenario(req.scenario_id) if req.scenario_id else None
    custom_setup = req.custom_world_setup if not scenario else None

    # Scenario overrides win unless the client explicitly sent a different value
    if scenario:
        effective_genre = req.genre or scenario["genre"]
        effective_role = req.role or scenario.get("role")
        effective_tone = req.tone or scenario.get("tone")
        effective_difficulty = req.difficulty if req.difficulty != "standard" else scenario.get("difficulty", "standard")
        effective_premise = req.custom_premise or scenario.get("pitch")
    else:
        effective_genre = req.genre
        effective_role = req.role
        effective_tone = req.tone
        effective_difficulty = req.difficulty
        effective_premise = req.custom_premise

    effective_mode = (req.mode or scenario.get("mode") if scenario else req.mode) or settings.get("default_mode") or DEFAULT_MODE
    if effective_mode not in ("basic", "advanced"):
        effective_mode = DEFAULT_MODE

    title = (
        scenario["title"]
        if scenario
        else f"{effective_genre.title()} — {(effective_role or 'Wanderer').title()}"
    )

    session = SessionRecord(
        device_id=req.device_id,
        genre=effective_genre,
        role=effective_role,
        tone=effective_tone,
        difficulty=effective_difficulty,
        debug_mode=req.debug_mode,
        custom_premise=effective_premise,
        custom_world_setup=custom_setup,
        title=title,
        mode=effective_mode,
        scenario_id=req.scenario_id,
        # ---- session-locked AI routing snapshot ----
        active_model=settings.get("model") or DEFAULT_MODEL,
        fallback_chain=(
            list(settings.get("fallback_models") or [])
            or list(FALLBACK_MODELS)
        ),
        cost_mode=(settings.get("cost_mode") or DEFAULT_COST_MODE).lower(),
    )

    setup_lines = [
        f"Genre: {effective_genre}",
        f"Character role: {effective_role or 'unspecified — choose a fitting archetype for the genre'}",
        f"Tone: {effective_tone or 'cinematic and grounded'}",
        f"Difficulty: {effective_difficulty}",
    ]
    if effective_premise:
        setup_lines.append(f"Premise hook: {effective_premise}")

    custom_setup_block = _build_custom_world_setup_block(custom_setup)
    if custom_setup_block:
        setup_lines.append(custom_setup_block)

    if scenario:
        setup_lines.append("")
        setup_lines.append("SCENARIO SEED — treat as canonical for the opening:")
        setup_lines.append(f"  Starting location: {scenario['starting_location']}")
        setup_lines.append(f"  Starting pressure: {scenario['starting_pressure']}")
        setup_lines.append("  Key NPCs (named, with stance):")
        for n in scenario.get("key_npcs", []):
            setup_lines.append(
                f"    - {n['name']} — {n['role']} (stance: {n.get('stance','unknown')})"
            )
        setup_lines.append(f"  Starting inventory: {scenario['starting_inventory']}")
        setup_lines.append(
            f"  Hidden threat (do NOT reveal yet, store as latent trigger): {scenario['hidden_threat']}"
        )
        setup_lines.append(f"  Opening seed: {scenario['seed']}")

    setup_text = "\n".join(setup_lines)
    settings = await get_ai_settings()
    dev_mode = bool(settings.get("developer_mode")) and bool(req.debug_mode)
    debug_marker = "[DEV_MODE: ON]" if dev_mode else "[DEV_MODE: OFF]"
    difficulty_marker = f"[DIFFICULTY: {effective_difficulty}]"
    mode_marker = f"[MODE: {effective_mode}]"

    opening_prompt = (
        f"{debug_marker}\n"
        f"{difficulty_marker}\n"
        f"{mode_marker}\n\n"
        f"Begin the story now. Use the following setup:\n{setup_text}\n\n"
        f"Open with an immersive in-medias-res scene that establishes location, sensory atmosphere, the character's immediate situation, and one active pressure or hook. "
        f"Populate the inventory ledger with the starting kit. "
        f"Present the appropriate number of meaningful first choices for the mode. "
        f"Honour the difficulty modifier on this very first roll. "
        f"Emit ALL required blocks including <rolling_state>"
        + (", <debug>" if dev_mode else "")
        + "."
    )

    await db.sessions.insert_one(session.model_dump())

    try:
        parsed, raw, meta = await _generate_validated_turn(
            session.model_dump(), opening_prompt
        )
    except AIServiceError as e:
        logger.exception("AI service failed")
        await db.sessions.delete_one({"id": session.id})
        raise HTTPException(status_code=502, detail=f"Story engine error: {e}")
    except Exception as e:
        logger.exception("LLM call failed")
        await db.sessions.delete_one({"id": session.id})
        raise HTTPException(status_code=502, detail=f"Story engine error: {e}")

    guard_adjustments = _apply_object_permanence(parsed)
    enriched_debug = _meta_into_debug(parsed.debug, meta)

    # ---- Rolling Memory Compression v3.8 ----
    # Turn 1: no prior to merge from. Compression metrics for diagnostics only.
    merged_rolling = consolidate_rolling_state(None, parsed.rolling_state)
    merged_rolling = _seed_custom_setup_into_rolling(merged_rolling, custom_setup)
    # Re-canonicalize after setup seeding so seeded inventory rows can't
    # collide with model-emitted rows that share identity.
    canonicalize_object_registry(merged_rolling)

    # P0 — ledger-wide cross-category dedup using post-consolidation truth.
    guard_adjustments.extend(
        _apply_ledger_object_permanence(parsed, authoritative_state=merged_rolling)
    )
    # P1-C — room audit (snapshot + drift flag). Turn 1 only seeds the room.
    guard_adjustments.extend(_apply_room_audit(parsed, merged_rolling))
    # P1-D — bound NPC memory + faction tick. Cheap, in-place.
    guard_adjustments.extend(
        _apply_npc_memory_bounds(merged_rolling, current_turn=1)
    )
    guard_adjustments.extend(_apply_faction_consequence_tick(merged_rolling))
    guard_adjustments.extend(_apply_delayed_consequence_tick(merged_rolling, current_turn=1))
    guard_adjustments.extend(_apply_rumour_propagation_tick(merged_rolling, current_turn=1))
    # F1 (P1.5) — strip meta leakage from rolling_state string fields so it
    # cannot re-enter the prompt on subsequent turns.
    guard_adjustments.extend(_apply_rolling_state_hygiene(merged_rolling))
    # Ch 31 — record any NPC deaths introduced in the opening scene.
    guard_adjustments.extend(
        gateway.update_death_registry(parsed, None, merged_rolling, None)
    )
    # Ch 31 — record any items destroyed/consumed in the opening scene.
    guard_adjustments.extend(
        gateway.update_destruction_registry(parsed, None, merged_rolling, None)
    )
    if guard_adjustments:
        enriched_debug["state_guard_adjustments"] = "; ".join(guard_adjustments)
    memory_depth = int(settings.get("memory_depth", DEFAULT_MEMORY_DEPTH))
    compression = compute_compression_metrics(
        turn_number=1,
        memory_depth=memory_depth,
        prior_turns_payloads=[],
    )
    enriched_debug.update(
        {
            f"compression_{k}": str(v) for k, v in compression.items()
        }
    )

    turn = TurnRecord(
        session_id=session.id,
        turn_number=1,
        player_action=None,
        narrative=parsed.narrative,
        paragraphs=parsed.paragraphs,
        choices=parsed.choices,
        state=parsed.state,
        ledger=parsed.ledger,
        rolling_state=merged_rolling or parsed.rolling_state,
        debug=enriched_debug,
        raw=raw,
    )
    await db.turns.insert_one(turn.model_dump())

    snippet = (parsed.paragraphs[0][:180] + "…") if parsed.paragraphs else ""
    await db.sessions.update_one(
        {"id": session.id},
        {"$set": {
            "turn_count": 1,
            "last_narrative_snippet": snippet,
            "last_state": parsed.state,
            "rolling_state": merged_rolling or parsed.rolling_state,
            "rolling_state_updated_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }},
    )

    # Persist session-level model lock + any fallback switch ledger.
    await _persist_model_lock(session.id, meta, at_turn=1)

    return {
        "session_id": session.id,
        "turn": await _maybe_sanitise_turn(turn.model_dump(mode="json")),
        "session": {
            "id": session.id,
            "genre": session.genre,
            "role": session.role,
            "difficulty": session.difficulty,
            "debug_mode": req.debug_mode,
            "title": session.title,
            "turn_count": 1,
            "mode": session.mode,
            "scenario_id": session.scenario_id,
        },
    }


@api_router.post("/story/action")
async def story_action(req: ActionRequest):
    session = await db.sessions.find_one({"id": req.session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    debug_marker = "[DEV_MODE: ON]" if (await get_ai_settings()).get("developer_mode") and req.debug_mode else "[DEV_MODE: OFF]"
    difficulty_marker = f"[DIFFICULTY: {session.get('difficulty', 'standard')}]"
    mode_marker = f"[MODE: {session.get('mode', DEFAULT_MODE)}]"
    user_text = f"{debug_marker}\n{difficulty_marker}\n{mode_marker}\n\nPlayer action: {req.action_text}"

    try:
        parsed, raw, meta = await _generate_validated_turn(session, user_text, player_action=req.action_text)
    except AIServiceError as e:
        logger.exception("AI service failed")
        raise HTTPException(status_code=502, detail=f"Story engine error: {e}")
    except Exception as e:
        logger.exception("LLM call failed")
        raise HTTPException(status_code=502, detail=f"Story engine error: {e}")

    next_turn_number = session.get("turn_count", 0) + 1
    guard_adjustments = _apply_state_supremacy(session, parsed, req.action_text)
    guard_adjustments.extend(_apply_object_permanence(parsed))

    # ---- Anti-Hallucination Gateway (Ch 31) — STRIP illegal mutations ----
    # Runs on the FRESH parsed turn (pre-consolidation) so corrected truth
    # feeds rolling-state consolidation below.
    prior_rolling = session.get("rolling_state")
    guard_adjustments.extend(
        gateway.strip_illegal_state_changes(
            prior_rolling, session.get("last_state"), parsed, req.action_text
        )
    )
    enriched_debug = _meta_into_debug(parsed.debug, meta)

    # ---- Rolling Memory Compression v3.8 ----
    merged_rolling = consolidate_rolling_state(prior_rolling, parsed.rolling_state)

    # P0 — ledger-wide cross-category dedup using the post-consolidation
    # rolling_state as authoritative truth. Must run AFTER consolidation
    # (so canonicalized object_locations is the source-of-truth map) but
    # BEFORE the turn is persisted.
    guard_adjustments.extend(
        _apply_ledger_object_permanence(parsed, authoritative_state=merged_rolling)
    )
    # P1-C — room audit reconciliation on revisit.
    guard_adjustments.extend(_apply_room_audit(parsed, merged_rolling))
    # P1-D — bounded NPC memory + lightweight faction tick.
    guard_adjustments.extend(
        _apply_npc_memory_bounds(merged_rolling, current_turn=next_turn_number)
    )
    guard_adjustments.extend(_apply_faction_consequence_tick(merged_rolling))
    guard_adjustments.extend(_apply_delayed_consequence_tick(merged_rolling, current_turn=next_turn_number))
    guard_adjustments.extend(_apply_rumour_propagation_tick(merged_rolling, current_turn=next_turn_number))
    # F1 (P1.5) — strip meta leakage from rolling_state string fields so it
    # cannot re-enter the prompt on subsequent turns.
    guard_adjustments.extend(_apply_rolling_state_hygiene(merged_rolling))
    # Ch 31 — record any NPC deaths this turn into the engine death registry.
    guard_adjustments.extend(
        gateway.update_death_registry(
            parsed, prior_rolling, merged_rolling, req.action_text
        )
    )
    # Ch 31 — record destroyed/consumed items as terminal object truth even when
    # the model renames or silently drops them instead of marking status.
    guard_adjustments.extend(
        gateway.update_destruction_registry(
            parsed, prior_rolling, merged_rolling, req.action_text
        )
    )
    if guard_adjustments:
        enriched_debug["state_guard_adjustments"] = "; ".join(guard_adjustments)

    # Diagnostics: which turn payloads were COMPRESSED OUT of this prompt?
    settings_for_metrics = await get_ai_settings()
    memory_depth = int(settings_for_metrics.get("memory_depth", DEFAULT_MEMORY_DEPTH))
    # After this turn lands, turns >memory_depth turns back are no longer sent
    # in full detail. They live only inside rolling_state.
    older_threshold = next_turn_number - memory_depth  # may be ≤ 0 on early turns
    older_turns = []
    if older_threshold > 0:
        older_turns = await db.turns.find(
            {"session_id": req.session_id, "turn_number": {"$lte": older_threshold}},
            {"_id": 0, "raw": 1, "narrative": 1},
        ).sort("turn_number", 1).to_list(length=500)
    older_payloads = [
        (t.get("raw") or t.get("narrative") or "") for t in older_turns
    ]
    compression = compute_compression_metrics(
        turn_number=next_turn_number,
        memory_depth=memory_depth,
        prior_turns_payloads=older_payloads,
    )
    enriched_debug.update(
        {f"compression_{k}": str(v) for k, v in compression.items()}
    )

    turn = TurnRecord(
        session_id=req.session_id,
        turn_number=next_turn_number,
        player_action=req.action_text,
        narrative=parsed.narrative,
        paragraphs=parsed.paragraphs,
        choices=parsed.choices,
        state=parsed.state,
        ledger=parsed.ledger,
        rolling_state=merged_rolling or parsed.rolling_state,
        debug=enriched_debug,
        raw=raw,
    )
    await db.turns.insert_one(turn.model_dump())

    snippet = (parsed.paragraphs[0][:180] + "…") if parsed.paragraphs else ""
    update_set: Dict[str, Any] = {
        "turn_count": next_turn_number,
        "last_narrative_snippet": snippet,
        "last_state": parsed.state,
        "updated_at": datetime.now(timezone.utc),
        "debug_mode": req.debug_mode,
    }
    # Always persist the CONSOLIDATED rolling_state so unresolved consequences
    # are never lost just because the model omitted them on this turn.
    if merged_rolling:
        update_set["rolling_state"] = merged_rolling
        update_set["rolling_state_updated_at"] = datetime.now(timezone.utc)
    elif parsed.rolling_state:
        update_set["rolling_state"] = parsed.rolling_state
        update_set["rolling_state_updated_at"] = datetime.now(timezone.utc)
    await db.sessions.update_one({"id": req.session_id}, {"$set": update_set})

    # Persist any model switch from this turn.
    await _persist_model_lock(req.session_id, meta, at_turn=next_turn_number)

    return {"turn": await _maybe_sanitise_turn(turn.model_dump(mode="json"))}


@api_router.post("/story/session/{session_id}/mode")
async def set_session_mode(session_id: str, req: SessionModeRequest):
    if req.mode not in ("basic", "advanced"):
        raise HTTPException(status_code=400, detail="mode must be 'basic' or 'advanced'")
    result = await db.sessions.update_one(
        {"id": session_id},
        {"$set": {"mode": req.mode, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"mode": req.mode}


@api_router.get("/story/session/{session_id}/export")
async def export_session(session_id: str):
    """Return full session state JSON: session + all turns + rolling state."""
    session = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    turns = await db.turns.find({"session_id": session_id}, {"_id": 0}).sort("turn_number", 1).to_list(length=500)
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "session": session,
        "turns": turns,
        "summary": {
            "turn_count": len(turns),
            "rolling_state": session.get("rolling_state"),
            "last_state": session.get("last_state"),
        },
    }


@api_router.post("/story/session/{session_id}/reset")
async def reset_session(session_id: str):
    """Delete all turns and rolling state but keep the session shell (genre/role/difficulty/mode).
    The client should then re-call /story/action with a meaningful first action, or the next call
    to /story/new with the same scenario."""
    session = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.turns.delete_many({"session_id": session_id})
    await db.sessions.update_one(
        {"id": session_id},
        {"$set": {
            "turn_count": 0,
            "last_narrative_snippet": "",
            "last_state": {},
            "rolling_state": None,
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    return {"reset": True}


@api_router.get("/story/sessions")
async def list_sessions(device_id: str):
    cursor = db.sessions.find({"device_id": device_id}, {"_id": 0}).sort("updated_at", -1)
    sessions = await cursor.to_list(length=200)
    sessions = [await _maybe_sanitise_session(s) for s in sessions]
    return {"sessions": sessions}


@api_router.get("/story/session/{session_id}")
async def get_session(session_id: str):
    session = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    turns = await db.turns.find({"session_id": session_id}, {"_id": 0}).sort("turn_number", 1).to_list(length=500)
    settings = await get_ai_settings()
    if not settings.get("developer_mode"):
        session = _sanitise_session_for_player(session)
        turns = [_sanitise_turn_for_player(t) for t in turns]
    return {"session": session, "turns": turns}


@api_router.get("/story/session/{session_id}/latest")
async def get_latest_turn(session_id: str):
    turn = await db.turns.find_one({"session_id": session_id}, {"_id": 0}, sort=[("turn_number", -1)])
    if not turn:
        raise HTTPException(status_code=404, detail="No turns found")
    return {"turn": await _maybe_sanitise_turn(turn)}


@api_router.delete("/story/session/{session_id}")
async def delete_session(session_id: str):
    await db.turns.delete_many({"session_id": session_id})
    result = await db.sessions.delete_one({"id": session_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True}


app.include_router(api_router)

_cors_origins_raw = os.environ.get("CORS_ORIGINS", "*")
_cors_origins = ["*"] if _cors_origins_raw.strip() == "*" else [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
