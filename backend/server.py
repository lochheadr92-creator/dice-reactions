from fastapi import Depends, FastAPI, APIRouter, HTTPException, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import copy
import os
import re
import logging
import uuid
from pathlib import Path
from pydantic import BaseModel, Field, conint, confloat
from pymongo.errors import DuplicateKeyError
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Local AI service (OpenRouter)
from ai_service import (  # noqa: E402
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
    AUTOMATIC_FALLBACK_MODELS,
    FALLBACK_MODELS,
    MAX_RETRIES,
    ENABLE_DEBUG_PANEL,
    COST_MODE as DEFAULT_COST_MODE,
    LOW_COST_MAX_TOKENS,
    MODEL_QWEN_UNCENSORED,
    get_runtime_config,
    resolve_context_budget,
    build_automatic_fallback_chain,
    normalize_runtime_model,
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
import relationships  # noqa: E402  — Relationship Calculus (Ch 29)
import hud  # noqa: E402  — player-facing HUD shaping (status chips + Pressure)
import pacing  # noqa: E402  — Early-Game Pacing Governor v1 (deterministic)
import prose_modes  # noqa: E402  — Prose Length System v2 (presentation-only)
import secrets  # noqa: E402  — Secret Reveal Trigger v1 (deterministic)
import replayability  # noqa: E402  — Replayability Engine v1 (deterministic)
import stress  # noqa: E402  — Ch 14 Stress substrate v1 (deterministic)
import causal_history  # noqa: E402  — player-safe "Why this happened" projection
from security import fetch_owned_session, require_admin, require_device_id  # noqa: E402
from rate_limit import (  # noqa: E402
    _rollback_bucket_reservations,
    acquire_story_creation_slot,
    check_story_creation_limits,
    ensure_rate_limit_indexes,
    release_story_creation_slot,
    resolve_client_ip,
)
from action_concurrency import (  # noqa: E402
    ACTION_CONFLICT_DETAIL,
    ActionLeaseConflict,
    ActionLeaseLost,
    acquire_action_lease,
    build_model_lock_patch,
    build_persist_cas_filter,
    ensure_action_concurrency_indexes,
    release_action_lease,
)
from player_api import (  # noqa: E402
    build_new_story_session_payload,
    build_player_session,
    build_player_state,
    build_player_turn,
)

import json as _json  # noqa: E402
import foundation_snapshot  # noqa: E402
import goal_engine  # noqa: E402
import information_engine  # noqa: E402
import investigation_engine  # noqa: E402
import npc_action_engine  # noqa: E402
import pressure_graph  # noqa: E402
import situation_engine  # noqa: E402
import world_event_engine  # noqa: E402
import world_state_consumers as world_consumers  # noqa: E402

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
  1. Exactly ONE <rolling_state> block FIRST. It must contain one complete valid JSON object, then close with </rolling_state> before any prose.
  2. Exactly ONE <narrative> block. Narrative structure and length follow the [PROSE MODE: …] directive in the user message — it defines the paragraph count, sentence count, and character budget for this chronicle. If no directive is present, default to 2-3 paragraphs, 700-1200 characters.
  3. Exactly ONE <choices> block containing 4 to 6 choices, each on its own line, labelled exactly A. B. C. D. in order (E. F. optional).
  4. Choices must cover meaningfully different intents — include at least one CAUTIOUS option, one DIRECT/RISKY option, one INVESTIGATIVE option, and one SOCIAL/COMMUNICATION option where the scene supports it.
  5. NO `Roll:` / `Modifiers:` / `Final:` / `Active systems:` / `Delayed trigger:` / `Latent trigger:` / `Scale:` lines anywhere outside the <debug> block.
  6. NO `<prior_state>` echo. NO bare JSON outside `<rolling_state>` / `<debug>`. NO preamble or meta.
  7. <state>, <ledger>, and <rolling_state> blocks are present. <debug> is present ONLY when the user message contains `[DEV_MODE: ON]`.

If space is limited, preserve a complete closed <rolling_state> block first and shorten narrative, choices, state, and ledger. If choices or state consume space, shorten prose; never omit rolling_state. On retry, stay at the LOW end of the active [PROSE MODE: …] character budget.

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

Choices must always be PLAYABLE. They may be costly, foolish, brave, or doomed — but never closed off mechanically. Do not use parenthetical no-resource labels such as "(no ammo)", "(unavailable)", or "(locked)".

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
At least ONE active pressure must always live in the foreground of the scene. Rotate among: approaching night, weather shift, distant sounds, worsening wound, hunger, thirst, spreading panic, failing infrastructure, movement outside, hostile factions on the move, NPC stress, dwindling daylight, resource decay, time-sensitive opportunity. Ensure at least one is referenced through sensory detail each turn (the engine maintains rolling_state `active_pressures` from the pressure graph).

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

NPC DEATH / EXIT STRUCTURED MARKER RULE:
  • If the narrative states or implies that a named NPC dies, is killed, leaves the scene, exits, disappears, is removed, or is no longer present, the SAME turn's `rolling_state.npcs` row for that NPC MUST carry the matching structured marker: `"alive":false`, or `"stance"`/`"status"` set to `"dead"` for a death; `"stance"`/`"status"` set to `"left"`/`"departed"`/`"exited"`/`"gone"`/`"fled"`, or `"absent":true`, for an exit or departure.
  • Prose is NEVER authoritative on its own. The engine only records a death into the deceased registry, or removes an NPC from the active scene cast, when this structured marker corroborates the narrative. A death or exit narrated without the matching marker is treated by the engine as NOT having happened — the NPC remains alive and present next turn regardless of what the prose said.
  • Do not narrate a death or departure and then omit the NPC from `rolling_state.npcs` with no marker — that reads as a silent, unexplained disappearance and will be reverted. Either keep the NPC in `npcs` with the matching marker, or omit them only after the marker has already been emitted.

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
Every turn MUST contain immersive prose paragraphs before Choices. Paragraph count, sentence count, and total character budget follow the [PROSE MODE: …] directive in the user message (default when absent: 2-3 paragraphs, 700-1200 characters).
Each paragraph must include action progression, sensory detail, consequence or reaction, and forward pressure.
Never collapse into one dense block. Never degrade into bullet narration. A blank line starts a new paragraph. Paragraph count is a style preference, not a limit — favour tight, concentrated prose and stay within the character budget rather than padding, but valid prose is never rejected merely for having more paragraphs.

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

<rolling_state>
DEVELOPER-FACING CONTINUITY PACKET. The player will NEVER see this. It is consumed only by the engine on the next turn for compressed memory.
Output this block FIRST and close it before writing <narrative>. Output one compact valid JSON object and nothing else inside this block.
Do NOT reproduce the full <prior_state>. Emit a bounded continuity UPDATE: changed/new facts, current active facts, and resolved markers only. The engine preserves omitted prior fields and restores protected unresolved state during merge.
Opening turns have no prior state, so seed only compact initial facts. Later turns should usually fit under 1200 characters; hard maximum 1800 characters.
Use minified JSON, no markdown fences, no comments, no trailing commas. Keep arrays short: at most 3 items per list, at most 2 NPCs, at most 2 inventory/object rows unless the player directly changed more this turn.
Required compact shape:
{"scene":"current scene in one clause","character":"one-line condition","objectives":["current objective"],"unresolved":["active unresolved stake"],"injuries":[],"inventory_objects":[],"object_locations":[],"route_continuity":[],"npcs":[],"npc_memory":[],"relationship_threads":[],"faction_pressure":[{"name":"","movement":"","player_reputation":"","ticks":{"suspicion":0,"guard_attention":0,"goodwill":0,"debt":0}}],"pressure_horizon":{"immediate":"immediate pressure","emerging":"","latent":""},"world_instability":[],"simulation_hooks":[],"recent_beats":["this turn in one line"],"topic_ledger":[],"recent_choice_signatures":["verb_intent"],"world_clock":"time/weather/decay"}
If space is tight, keep scene, character, objectives, unresolved, injuries, inventory_objects, object_locations, npcs, npc_memory, recent_beats, recent_choice_signatures, and world_clock; omit low-value empty optional arrays. Never omit active threats, wounds, debts, or named NPCs changed this turn.
</rolling_state>

<narrative>
(immersive prose paragraphs separated by blank lines — follow the [PROSE MODE: …] directive for paragraph count, sentence count, and character budget; default 2-3 paragraphs, 700-1200 characters when absent. Grounded sensory detail. No mechanics. No "What do you do?")
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
You must always output 4 to 6 choices labelled exactly A. B. C. D. in order (E. F. optional), with each label followed by a period and a space. Each choice must represent a meaningfully different intent. Where the scene supports it, include at least one CAUTIOUS option, one DIRECT / RISKY option, one INVESTIGATIVE option, and one SOCIAL / COMMUNICATION option. Never duplicate intents. Never omit the <choices> block. Never write "what do you do?" or hand control back to the player without a choice list.

<state>
Health: [stable / bruised / wounded / badly wounded / critical]
Stress: [clear / tense / overloaded / distorted / breaking]
Fatigue: [rested / tired / strained / exhausted / collapsing]
Danger: [none / low / elevated / high / critical]
Momentum: [surging / steady / stalling / declining / lost]
Position: [short in-world description of current location + cover/visibility]
Pressure: [the SINGLE most immediate problem or threatening condition the character faces RIGHT NOW, as a short in-world clause describing the PROBLEM, never the solution. Examples: "Bleeding wound worsening", "Nightfall approaching", "Unknown movement nearby", "Shelter feels unstable". NEVER phrase it as a goal, objective, task, instruction, or correct action (no "find", "secure", "locate", "reach", "get", "escape to", "must", "should"). If several pressures exist, state only the most immediate one. "—" only if genuinely nothing presses.]
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

NEVER include any text outside these tag blocks. NEVER add preamble, meta commentary, or closing remarks. Output <rolling_state> first, then <narrative>, <choices>, <state>, <ledger>, and optional <debug> only when [DEV_MODE: ON].

CONTINUITY MODE:
On subsequent turns the user message will start with a <prior_state> block containing authoritative engine state. Treat it as ground truth. Do NOT echo it back verbatim. Emit only a compact <rolling_state> update object first; omitted prior fields are preserved by the engine merge. The <prior_state> block is engine-only; the player never sees it.

MODE:
Every user message includes [MODE: basic] or [MODE: advanced]. This is also engine-only and must never be referenced in prose.
- basic: 4 choices, a few short paragraphs, simpler rolling_state update (you may omit empty optional arrays), no nested NPC structures. The anti-loop fields (`topic_ledger`, `recent_choice_signatures`) MUST still be maintained when touched. The player experience is the SAME — only the simulation depth changes.
- advanced: 4-6 choices, a few short paragraphs, bounded rolling_state update, deeper NPC/faction simulation, longer memory persistence, stronger consequence propagation. STILL nothing about the engine is exposed.

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
    # Presentation-only narration budget. Accepts new mode names
    # (brief/standard/story/cinematic) and legacy S/M/L aliases.
    prose_mode: Optional[str] = None
    scenario_id: Optional[str] = None
    custom_world_setup: Optional[Dict[str, Any]] = None
    # Client-generated idempotency key so a creation retry after a failed/lost
    # first attempt cannot create a duplicate completed session. Optional.
    creation_request_id: Optional[str] = Field(default=None, max_length=128)

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
    # Presentation-only narration budget (Prose Length System v2). Never
    # affects simulation truth, canonical events, or replay.
    prose_mode: str = prose_modes.DEFAULT_PROSE_MODE
    scenario_id: Optional[str] = None
    # Client idempotency key for safe creation retry (engine-only; excluded from
    # all player-facing payloads by the player_api allowlists).
    creation_request_id: Optional[str] = None
    # ---- AI routing (per-session lock) ----
    active_model: Optional[str] = None
    fallback_chain: Optional[List[str]] = None
    model_switches: List[Dict[str, Any]] = Field(default_factory=list)
    cost_mode: str = "normal"  # "normal" | "low"
    replayability_state: Optional[Dict[str, Any]] = None
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
        m = re.match(r"^([A-F])\.\s+(.+)$", line)
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


def _parse_rolling_state_json(block: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Parse a strict rolling_state JSON object and return a compact error."""
    candidate = (block or "").strip()
    if not candidate:
        return None, "missing <rolling_state> block"
    try:
        loaded = _json.loads(candidate)
    except Exception as exc:
        return None, str(exc)
    if not isinstance(loaded, dict):
        return None, f"rolling_state JSON root is {type(loaded).__name__}, expected object"
    return loaded, None


_ROLLING_STATE_OPEN_RE = re.compile(r"<\s*rolling_state\b[^>]*>", re.IGNORECASE)
_ROLLING_STATE_CLOSE_RE = re.compile(r"<\s*/\s*rolling_state\s*>", re.IGNORECASE)
_VALIDATION_DIAGNOSTIC_SNIPPET_CHARS = 220
_VALIDATION_DIAGNOSTICS_ENABLED = (
    os.environ.get("ENABLE_VALIDATION_DIAGNOSTIC_LOGS", "false").lower()
    in ("1", "true", "yes", "on")
)
_DIAGNOSTIC_REDACTIONS = (
    re.compile(
        r'((?:"?(?:secret|token|password|api[_-]?key|authorization)"?\s*[:=]\s*)'
        r')("[^"]*"|[^\s,}\]]+)',
        re.IGNORECASE,
    ),
    re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b"),
)


def _redact_validation_diagnostic_snippet(text: str) -> str:
    """Keep validation diagnostics useful without logging obvious credentials."""
    out = text or ""
    out = _DIAGNOSTIC_REDACTIONS[0].sub(r'\1"[REDACTED]"', out)
    out = _DIAGNOSTIC_REDACTIONS[1].sub("[REDACTED_KEY]", out)
    return out.replace("\r", "\\r").replace("\n", "\\n")


def _rolling_state_block_diagnostic(raw: str, validator_rule: str) -> Dict[str, Any]:
    """Diagnostic hook for rolling_state format failures.

    This deliberately does not repair or loosen parsing. It mirrors strict
    parser behaviour and reports only redacted, bounded evidence.
    """
    text = raw or ""
    open_match = _ROLLING_STATE_OPEN_RE.search(text)
    close_match = _ROLLING_STATE_CLOSE_RE.search(text, open_match.end() if open_match else 0)
    tag_exists = bool(open_match and close_match)
    extracted = ""
    if tag_exists and open_match and close_match:
        extracted = text[open_match.end():close_match.start()].strip()
    _, parse_error = _parse_rolling_state_json(extracted)

    if tag_exists and open_match and close_match:
        start_slice = text[open_match.start(): min(len(text), open_match.start() + _VALIDATION_DIAGNOSTIC_SNIPPET_CHARS)]
        end_slice = text[max(0, close_match.end() - _VALIDATION_DIAGNOSTIC_SNIPPET_CHARS): close_match.end()]
    else:
        needle = re.search(r"rolling_state", text, re.IGNORECASE)
        center = needle.start() if needle else 0
        start_slice = text[center: min(len(text), center + _VALIDATION_DIAGNOSTIC_SNIPPET_CHARS)]
        end_slice = text[max(0, len(text) - _VALIDATION_DIAGNOSTIC_SNIPPET_CHARS):]

    return {
        "validator_rule": validator_rule,
        "rolling_state_tag_exists": tag_exists,
        "rolling_state_open_tag_exists": bool(open_match),
        "rolling_state_close_tag_exists": bool(close_match),
        "rolling_state_extracted_length": len(extracted),
        "rolling_state_json_error": parse_error,
        "rolling_state_snippet_start": _redact_validation_diagnostic_snippet(start_slice),
        "rolling_state_snippet_end": _redact_validation_diagnostic_snippet(end_slice),
    }


def _log_validation_failure_diagnostic(
    raw: str,
    *,
    validator_kind: str,
    validator_reason: str,
    attempt: str,
    dev_on: bool,
) -> None:
    if not (dev_on or _VALIDATION_DIAGNOSTICS_ENABLED):
        return
    diag = _rolling_state_block_diagnostic(
        raw, f"{validator_kind}/{validator_reason}"
    )
    logger.info("Turn validation diagnostic (%s): %s", attempt, diag)

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
        # The block must be a strict JSON object. Invalid JSON is rejected by validation.
        rolling_state, _ = _parse_rolling_state_json(rolling_block)

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


def _sanitize_automatic_fallback_models(raw: Optional[List[str]]) -> List[str]:
    source = raw if isinstance(raw, list) else list(FALLBACK_MODELS)
    filtered: List[str] = []
    for model_id in source:
        if model_id in AUTOMATIC_FALLBACK_MODELS and model_id not in filtered:
            filtered.append(model_id)
    return filtered or list(FALLBACK_MODELS)


def _normalize_ai_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(settings)
    normalized["model"] = normalize_runtime_model(normalized.get("model") or DEFAULT_MODEL)
    normalized["fallback_models"] = _sanitize_automatic_fallback_models(
        normalized.get("fallback_models")
    )
    return normalized


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
    return _normalize_ai_settings(merged)


def _resolve_requested_model(session: Dict[str, Any], settings: Dict[str, Any]) -> str:
    settings_model = normalize_runtime_model(settings.get("model") or DEFAULT_MODEL)
    active_raw = session.get("active_model")
    if not active_raw:
        return settings_model

    active_text = str(active_raw).strip()
    active_model = normalize_runtime_model(active_text)
    if active_model != active_text:
        return settings_model
    fallback_chain = session.get("fallback_chain")
    if not isinstance(fallback_chain, list) or not fallback_chain:
        return settings_model if active_model != settings_model else active_model

    session_primary = normalize_runtime_model(str(fallback_chain[0]))
    if session_primary != settings_model:
        return settings_model
    return active_model


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


_STORY_ENGINE_UNAVAILABLE = "Story engine unavailable"


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


# Keys that must NEVER reach LLM-visible context until an explicit reveal
# trigger exists (Phase 1 Blocker A — secrets). They live in engine-side state
# only. `_PROMPT_HIDDEN_SETUP_KEYS` are stripped from the turn-1 custom-setup
# prompt block; `_PROMPT_HIDDEN_ROLLING_KEYS` are stripped from <prior_state>.
_PROMPT_HIDDEN_SETUP_KEYS = frozenset({"secret"})
_PROMPT_HIDDEN_ROLLING_KEYS = frozenset({
    "secret_registry",
    "engine_world_events",
    "world_events",
    "world_event_receipts",
    "evidence",
    "investigations",
    "investigation_receipts",
    "information_items",
    "information_receipts",
    "reputation_signals",
    "world_state_consumed_event_ids",
    "world_state_receipts",
    "world_state_guard_receipts",
    "npc_move_receipts",
    "npc_agendas",
    "npc_actions",
    "npc_action_receipts",
    "arc_diversity",
    "situations",
    "situation_receipts",
    "goals",
    "goal_receipts",
})


def _humanize_hook(value: Any) -> str:
    """Turn a catalog slug (e.g. 'losing-control') into prose ('losing control')."""
    return str(value or "").replace("-", " ").strip()


def _effective_relationships_level(setup: Optional[Dict[str, Any]]) -> str:
    """Option A: if 'whoMatters' is chosen (and not 'nobody'), raise the
    relationship content floor to at least 'low' so the bond is actually
    simulated. Pure — never mutates the input."""
    content = setup.get("contentSettings") if isinstance(setup, dict) else None
    current = str((content or {}).get("relationships") or "none").strip().lower()
    who = str((setup or {}).get("whoMatters") or "").strip().lower()
    if who and who != "nobody" and current in ("", "none"):
        return "low"
    return current or "none"


def _prompt_safe_rolling(rolling: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Shallow copy of rolling_state with engine-only hidden keys removed, for
    safe inclusion in the LLM <prior_state> block. Does not mutate input or
    persisted state."""
    if not isinstance(rolling, dict):
        return {}
    safe = {k: v for k, v in rolling.items() if k not in _PROMPT_HIDDEN_ROLLING_KEYS}
    if isinstance(safe.get("pressure_graph"), dict):
        safe["pressure_graph"] = pressure_graph.project_pressure_graph_for_prompt(
            safe["pressure_graph"]
        )
    return npc_action_engine.prompt_safe_rolling_state(
        goal_engine.prompt_safe_rolling_state(
            information_engine.prompt_safe_rolling_state(
                investigation_engine.prompt_safe_rolling_state(
                    world_event_engine.prompt_safe_rolling_state(
                        situation_engine.prompt_safe_rolling_state(
                            world_consumers.prompt_safe_world_state(safe)
                        )
                    )
                )
            )
        )
    )


def _prompt_projection_trait_kwargs(session: Dict[str, Any]) -> Dict[str, Any]:
    replay = session.get("replayability_state")
    npc_refs, settlement_refs = foundation_snapshot.trait_refs_from_replayability_state(
        replay
    )
    if not npc_refs and not settlement_refs:
        return {}
    rolling = session.get("rolling_state") if isinstance(session, dict) else {}
    rolling = rolling if isinstance(rolling, dict) else {}
    return {
        "npc_trait_refs": npc_refs,
        "settlement_trait_refs": settlement_refs,
        "location_ref": str(rolling.get("scene") or rolling.get("location") or ""),
    }


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
    # Never expose engine-only hidden keys (e.g. the player's Secret) to the model.
    visible = {k: v for k, v in setup.items() if k not in _PROMPT_HIDDEN_SETUP_KEYS}
    # Option A: surface the raised relationship floor so the model treats the
    # "who matters most" bond as an active social system, not none.
    rel_level = _effective_relationships_level(setup)
    if rel_level != "none":
        content = dict(visible.get("contentSettings") or {})
        content["relationships"] = rel_level
        visible["contentSettings"] = content
    clean = _clean_setup(visible)
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


def _normalise_world_instability_entry(value: Any) -> str:
    """Return a compact hashable world_instability entry for setup seeding."""
    if isinstance(value, str):
        return value
    try:
        cleaned = _clean_setup(value)
        return _json.dumps(
            cleaned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except Exception:
        return _short_text(value, 700)


def _dedupe_world_instability_entries(entries: List[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for entry in entries:
        normalised = _normalise_world_instability_entry(entry)
        if normalised in seen:
            continue
        seen.add(normalised)
        out.append(normalised)
    return out


def _simulation_hook_dedupe_key(value: Any) -> Tuple[str, Any]:
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, dict):
        return (
            "dict",
            _json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ),
        )
    try:
        hash(value)
    except TypeError:
        return (
            type(value).__name__,
            _json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ),
        )
    return (type(value).__name__, value)


def _dedupe_simulation_hooks(hooks: List[Any]) -> List[Any]:
    out: List[Any] = []
    seen = set()
    for hook in hooks:
        key = _simulation_hook_dedupe_key(hook)
        if key in seen:
            continue
        seen.add(key)
        out.append(hook)
    return out


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
    # Onboarding story hooks (Quick Start + Advanced hook pool). These ARE
    # intentionally prompt-visible: they shape NPC creation, pressure, and arcs.
    # NOTE: `secret` is deliberately excluded here — it is engine-only (below).
    for label, value in (
        ("core desire", setup.get("want")),
        ("core fear", setup.get("fear")),
        ("buried past (the ghost)", setup.get("ghost")),
        ("signature talent", setup.get("talent")),
        ("fatal flaw", setup.get("flaw")),
        ("moral line never to cross", setup.get("line")),
    ):
        if value:
            hooks.append(f"{label}: {_humanize_hook(value)}")
    who = _humanize_hook(setup.get("whoMatters"))
    if who and who != "nobody":
        hooks.append(f"person who matters most: {who}")
    out["simulation_hooks"] = _dedupe_simulation_hooks(hooks)[:16]

    existing_instability = out.get("world_instability")
    if isinstance(existing_instability, list):
        instability = list(existing_instability)
    elif existing_instability:
        instability = [existing_instability]
    else:
        instability = []
    for p in pressures:
        instability.append(f"active pressure: {_short_text(p, 120)}")
    if setup.get("danger"):
        instability.append(f"danger: {_short_text(setup.get('danger'), 220)}")
    out["world_instability"] = _dedupe_world_instability_entries(instability)[:12]

    if focus and not out.get("story_focus"):
        out["story_focus"] = focus[:8]

    rel = _effective_relationships_level(setup)
    if rel and rel != "none":
        threads = list(out.get("relationship_threads") or [])
        threads.append({
            "name": "social ecosystem",
            "dynamic": rel,
            "intensity": "medium",
            "leverage": "affects NPC memory, faction reactions, trust, stress, delayed consequences, and material choices",
        })
        if who and who != "nobody":
            threads.append({
                "name": f"the {who} who matters most",
                "dynamic": "attachment",
                "intensity": "medium",
                "leverage": "their safety and regard are primary emotional stakes; can be threatened, leveraged, or lost",
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

    # Secret (Phase 1 Blocker A): engine-only hidden state. NEVER seeded into
    # simulation_hooks or any prompt-visible field. Stored unrevealed until a
    # future explicit reveal trigger promotes it. Already excluded from the
    # LLM <prior_state> block (_prompt_safe_rolling) and from player API
    # (player_api blocks the nested key 'secret_registry').
    secret = setup.get("secret")
    if secret:
        registry = list(out.get("secret_registry") or [])
        registry.append({
            "secret_id": secrets.build_stable_secret_id(len(registry)),
            "secret": _short_text(secret, 400),
            "revealed": False,
            "turn_added": 1,
            "reveal_policy": secrets.DEFAULT_REVEAL_POLICY,
        })
        out["secret_registry"] = registry[:6]
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
    for marker in _INTERNAL_SYSTEM_MARKERS:
        if marker in out:
            out = out.replace(marker, "[…]")
            hits += 1
    if _INTERNAL_DIRECTIVE_PROSE_RE.search(out):
        out = _INTERNAL_DIRECTIVE_PROSE_RE.sub("[…]", out)
        hits += 1
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


_PROTECTED_ROLLING_KEYS = frozenset({"secret_registry"})


def _scrub_model_rolling_state_for_persistence(
    rolling_state: Dict[str, Any],
) -> Tuple[Dict[str, Any], int]:
    """Scrub LLM-owned rolling_state strings. Never touches secret_registry."""
    out = copy.deepcopy(rolling_state)
    hits = 0
    for key, val in list(out.items()):
        if key in _PROTECTED_ROLLING_KEYS:
            continue
        if isinstance(val, str):
            scrubbed, field_hits = _scrub_meta_from_text(val)
            if field_hits:
                out[key] = scrubbed
                hits += field_hits
        elif isinstance(val, list):
            new_list: List[Any] = []
            field_hits = 0
            for item in val:
                if isinstance(item, str):
                    scrubbed, item_hits = _scrub_meta_from_text(item)
                    field_hits += item_hits
                    if scrubbed and scrubbed != "[…]":
                        new_list.append(scrubbed)
                else:
                    new_list.append(item)
            if field_hits:
                out[key] = new_list
                hits += field_hits
    return out, hits


def _scrub_parsed_for_persistence(parsed: ParsedTurn) -> Tuple[ParsedTurn, List[str]]:
    """Strip internal directive leakage from fields persisted or replayed."""
    adjustments: List[str] = []
    narrative, narrative_hits = _scrub_meta_from_text(parsed.narrative or "")
    paragraphs: List[str] = []
    paragraph_hits = 0
    for paragraph in parsed.paragraphs or []:
        scrubbed, hits = _scrub_meta_from_text(paragraph)
        paragraph_hits += hits
        paragraphs.append(scrubbed)
    choices: List[Dict[str, str]] = []
    choice_hits = 0
    for choice in parsed.choices or []:
        row = dict(choice)
        scrubbed, hits = _scrub_meta_from_text(row.get("text") or "")
        choice_hits += hits
        row["text"] = scrubbed
        choices.append(row)
    state: Dict[str, str] = {}
    state_hits = 0
    for key, value in (parsed.state or {}).items():
        scrubbed, hits = _scrub_meta_from_text(str(value))
        state_hits += hits
        state[key] = scrubbed
    ledger: Dict[str, Any] = {}
    ledger_hits = 0
    for key, value in (parsed.ledger or {}).items():
        if isinstance(value, list):
            new_list: List[Any] = []
            for item in value:
                scrubbed, hits = _scrub_meta_from_text(str(item))
                ledger_hits += hits
                new_list.append(scrubbed)
            ledger[key] = new_list
        else:
            scrubbed, hits = _scrub_meta_from_text(str(value))
            ledger_hits += hits
            ledger[key] = scrubbed
    rolling_state = parsed.rolling_state
    rolling_hits = 0
    if isinstance(rolling_state, dict):
        rolling_state, rolling_hits = _scrub_model_rolling_state_for_persistence(
            rolling_state
        )
    total_hits = (
        narrative_hits
        + paragraph_hits
        + choice_hits
        + state_hits
        + ledger_hits
        + rolling_hits
    )
    if total_hits:
        adjustments.append(f"persistence_scrub:hits={total_hits}")
    return (
        ParsedTurn(
            narrative=narrative,
            paragraphs=paragraphs,
            choices=choices,
            state=state,
            ledger=ledger,
            rolling_state=rolling_state,
            debug=parsed.debug,
            raw=parsed.raw,
        ),
        adjustments,
    )


def _finalize_validated_turn(
    parsed: ParsedTurn, raw: str, meta: Dict[str, Any]
) -> Tuple[ParsedTurn, str, Dict[str, Any]]:
    """Scrub parsed player/replay fields, then enforce the prose-mode length
    budget LOCALLY before any persistence path.

    Prose Length System v2: over-budget narration is trimmed here at the
    nearest safe sentence boundary. This never requests a new simulation,
    never regenerates canonical events, and never makes another provider
    request — presentation only. Canonical state (rolling_state, ledger,
    choices, state) is untouched by trimming.
    """
    scrubbed, adjustments = _scrub_parsed_for_persistence(parsed)
    out_meta = dict(meta)
    if adjustments:
        out_meta["persistence_scrub"] = "; ".join(adjustments)

    mode = prose_modes.resolve_prose_mode(out_meta.get("prose_mode"))
    returned = prose_modes.measure_narration(scrubbed.paragraphs)
    trimmed_paragraphs, trimming_occurred = prose_modes.trim_narration(
        scrubbed.paragraphs, mode.max_chars
    )
    if trimming_occurred:
        scrubbed = scrubbed.model_copy(
            update={
                "paragraphs": trimmed_paragraphs,
                "narrative": "\n\n".join(trimmed_paragraphs),
            }
        )
    final = prose_modes.measure_narration(scrubbed.paragraphs)

    out_meta["prose"] = {
        "requested_prose_mode": out_meta.get("prose_mode_requested")
        or mode.name,
        "effective_prose_mode": mode.name,
        "requested_budget": mode.max_chars,
        "returned_character_count": returned["character_count"],
        "returned_paragraph_count": returned["paragraph_count"],
        "returned_sentence_count": returned["sentence_count"],
        "final_character_count": final["character_count"],
        "trimming_occurred": trimming_occurred,
        "retry_occurred": bool(out_meta.get("validation_retried")),
        "model_used": out_meta.get("model_used"),
        "latency_ms": (out_meta.get("telemetry") or {}).get("latency_ms"),
    }
    return scrubbed, raw, out_meta


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
    early_game_stage: Optional[int] = None,
    secret_reveal_directive: str = "",
    replayability_directives: Optional[Dict[str, str]] = None,
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

    pacing_directive = pacing.build_early_game_directive(
        early_game_stage, session.get("rolling_state")
    )
    if pacing_directive:
        messages.append({"role": "system", "content": pacing_directive})

    rb_directives = replayability_directives or {}
    include_opening = session.get("turn_count", 0) <= 0
    if include_opening:
        opening_body = (rb_directives.get("opening") or "").strip()
        if opening_body:
            messages.append({"role": "system", "content": opening_body})

    if secret_reveal_directive:
        messages.append({"role": "system", "content": secret_reveal_directive})

    for rb_body in replayability.combine_directive_messages(
        rb_directives, include_opening=False
    ):
        messages.append({"role": "system", "content": rb_body})

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
        rel_block = relationships.build_relationship_block(rolling)
        prior_state_block = (
            "<prior_state>\n"
            + _json.dumps(_prompt_safe_rolling(rolling), indent=2, ensure_ascii=False)
            + "\n</prior_state>\n\n"
        )
        prefix = ""
        if truth_block:
            prefix += truth_block + "\n\n"
        if rel_block:
            prefix += rel_block + "\n\n"
        user_text = prefix + prior_state_block + user_text

    messages.append({"role": "user", "content": user_text})
    return messages


async def _generate_turn(
    session: Dict[str, Any],
    user_text: str,
    early_game_stage: Optional[int] = None,
    secret_reveal_directive: str = "",
    replayability_directives: Optional[Dict[str, str]] = None,
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

    # ---- Prose Length System v2 (presentation-only) ----
    # Resolve the requested prose mode (legacy S/M/L aliases map onto the new
    # modes; unknown/missing → standard). Low cost mode deterministically caps
    # the effective mode at standard so cost guarantees are never violated.
    requested_prose_mode = prose_modes.resolve_prose_mode_name(
        session.get("prose_mode")
    )
    prose_mode = prose_modes.PROSE_MODES[requested_prose_mode]
    if cost_mode == "low" and prose_mode.max_chars > prose_modes.PROSE_MODES[
        "standard"
    ].max_chars:
        prose_mode = prose_modes.PROSE_MODES["standard"]

    max_tokens = int(settings.get("max_tokens", DEFAULT_MAX_TOKENS))
    # Larger prose modes raise the completion budget so structured output is
    # not token-truncated. Floors always LOSE to the explicit caps below.
    if prose_mode.max_tokens_floor:
        max_tokens = max(max_tokens, prose_mode.max_tokens_floor)
    cap = profile.get("max_tokens_cap")
    if cap:
        max_tokens = min(max_tokens, cap)
    if cost_mode == "low":
        max_tokens = min(max_tokens, LOW_COST_MAX_TOKENS)

    # ---- Session-level model lock + fallback chain ----
    requested_model = _resolve_requested_model(session, settings)
    fallback_chain = build_automatic_fallback_chain(
        requested_model,
        cost_mode=cost_mode,
    )

    # ---- Hints embedded into the upcoming user message ----
    hint_lines: List[str] = []
    primary_pref = normalize_runtime_model(settings.get("model") or DEFAULT_MODEL)
    if (
        requested_model != primary_pref
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
    # Structural narration guidance — presentation only, engine-only marker.
    hint_lines.append(prose_modes.build_prose_directive(prose_mode))
    augmented_user_text = (
        ("\n".join(hint_lines) + "\n\n" + user_text) if hint_lines else user_text
    )

    messages = await _build_messages(
        session,
        augmented_user_text,
        memory_depth=memory_depth,
        history_window_fallback=history_window,
        early_game_stage=early_game_stage,
        secret_reveal_directive=secret_reveal_directive,
        replayability_directives=replayability_directives,
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
        **_prompt_projection_trait_kwargs(session),
    )

    result = await gateway.invoke_llm(
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
    # Prose Length System v2 — carried on meta so finalize/trim + telemetry
    # know the active presentation budget without re-resolving settings.
    result["prose_mode_requested"] = requested_prose_mode
    result["prose_mode"] = prose_mode.name
    result["prose_budget"] = prose_mode.max_chars
    return result["content"], result


# ----------------------------------------------------------------------
# Output validation + single-shot retry
# ----------------------------------------------------------------------
# Narration length is NOT validated here any more (Prose Length System v2):
# over-budget narration is trimmed locally at a sentence boundary in
# _finalize_validated_turn and must never trigger another provider request.
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
_INTERNAL_SYSTEM_MARKERS = (
    secrets.DIRECTIVE_MARKER,
    pacing.PACING_DIRECTIVE_MARKER,
    *replayability.DIRECTIVE_MARKERS,
)
_INTERNAL_DIRECTIVE_PROSE_RE = re.compile(
    "|".join(
        list(secrets.DIRECTIVE_PROSE_PATTERNS)
        + list(replayability.DIRECTIVE_PROSE_PATTERNS)
    ),
    re.IGNORECASE,
)
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
def _text_contains_internal_system_leak(text: str) -> bool:
    if not text:
        return False
    if any(marker in text for marker in _INTERNAL_SYSTEM_MARKERS):
        return True
    return bool(_INTERNAL_DIRECTIVE_PROSE_RE.search(text))


_FAKE_CHOICE_RE = re.compile(
    r"\b(?:not\s+allowed|not\s+yet|unavailable|locked|blocked|disabled|"
    r"can(?:not|'t)\s+|won't\s+work|impossible\s+to|not\s+possible|"
    r"no\s+(?:ammo|ammunition|bullets)|out\s+of\s+(?:ammo|ammunition|bullets))\b",
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
    choice_labels = [(c.get("label") or "").upper() for c in parsed.choices]
    expected_labels = list("ABCDEF"[: len(choice_labels)])
    if choice_labels != expected_labels:
        return False, "choices must be labelled exactly A. B. C. D. in order"

    if not isinstance(parsed.rolling_state, dict):
        return False, "missing or invalid rolling_state JSON"

    paragraphs = parsed.paragraphs or []

    # 2. Narrative must be present. Paragraph COUNT is a style preference, not a
    #    validity rule: narration is never rejected merely for containing five or
    #    more paragraphs. Narration LENGTH is never a validation failure either
    #    (Prose Length System v2): over-budget narration is trimmed locally in
    #    _finalize_validated_turn — an extra LLM call is never made for length.
    if len(paragraphs) == 0:
        return False, "no narrative paragraphs"

    # 3. No leaked engine tags / mechanic labels inside narrative
    joined = "\n".join(paragraphs)
    if _ENGINE_TAG_IN_NARRATIVE_RE.search(joined):
        return False, "engine tag leaked into narrative"
    if _LEAK_LABEL_RE.search(joined):
        return False, "mechanic label leaked into narrative"
    if _MECHANIC_WORD_RE.search(joined):
        return False, "mechanic terminology leaked into narrative"
    if _SOFT_META_PHRASE_RE.search(joined):
        return False, "soft meta phrasing leaked into narrative"
    if _text_contains_internal_system_leak(joined):
        return False, "internal system directive leaked into narrative"

    for c in parsed.choices or []:
        if _FAKE_CHOICE_RE.search(c.get("text") or ""):
            return False, "fake or closed-off choice wording"
        if _text_contains_internal_system_leak(c.get("text") or ""):
            return False, "internal system directive leaked into choices"

    for value in (parsed.state or {}).values():
        if _text_contains_internal_system_leak(str(value)):
            return False, "internal system directive leaked into state"

    for value in (parsed.ledger or {}).values():
        if isinstance(value, list):
            leaked = any(_text_contains_internal_system_leak(str(item)) for item in value)
        else:
            leaked = _text_contains_internal_system_leak(str(value))
        if leaked:
            return False, "internal system directive leaked into ledger"

    if parsed.rolling_state and _text_contains_internal_system_leak(
        _json.dumps(parsed.rolling_state, default=str)
    ):
        return False, "internal system directive leaked into rolling_state"

    # 4. P1-B — direct inspection must resolve concretely
    inspection_reason = _check_direct_inspection_violation(parsed, player_action)
    if inspection_reason:
        return False, inspection_reason

    return True, ""


_RETRY_INSTRUCTION = (
    "[VALIDATION_RETRY: {reason}]\n"
    "Rewrite the previous response in valid player-facing format with "
    "<rolling_state> FIRST as one complete closed valid JSON object, then "
    "immersive prose paragraphs (a blank line starts a new paragraph; paragraph count is a style preference, not a limit) within the active [PROSE MODE: …] budget{length_clause} and 4–6 A–F choices. "
    "Do not reproduce the full prior_state; emit only a bounded continuity update. "
    "Every choice must be on its own line beginning with the letter and a period "
    "(A. B. C. D. and optionally E. F.). "
    "Do NOT include any Roll / Modifiers / Final / Active systems / Delayed trigger / "
    "Latent trigger / Scale text anywhere outside the <debug> block. "
    "Do NOT echo mechanic-probing words from the player (roll, modifier, trigger, hidden system, debug, simulation, JSON); translate the attempt into in-world uncertainty, suspicion, stress, superstition, or manipulation. "
    "Do NOT echo <prior_state>. Output ONLY the required tag blocks "
    "(<rolling_state>, <narrative>, <choices>, <state>, <ledger>"
    "{debug_clause}). <rolling_state> must contain one valid JSON object and no prose. "
    "If choices or state consume space, shorten prose, never omit rolling_state. "
    "If space is limited, preserve complete closed <rolling_state> and shorten all player-facing text; on retry keep narration at the LOW end of the prose-mode budget. "
    "Choices must cover meaningfully different intents — include a "
    "cautious option, a direct/risky option, an investigative option, and a "
    "social/communication option where the scene supports it."
)

def _build_format_retry_instruction(
    reason: str, debug_clause: str, prose_mode: Optional[str] = None
) -> str:
    """Format-failure retry note. NEVER emitted for narration length: length is
    enforced locally by trimming (Prose Length System v2), not by re-prompting.
    """
    mode = prose_modes.resolve_prose_mode(prose_mode)
    length_clause = (
        f" ({mode.min_paragraphs}-{mode.max_paragraphs} paragraphs, "
        f"approx {mode.min_chars}-{mode.max_chars} characters)"
    )
    return _RETRY_INSTRUCTION.format(
        reason=reason,
        debug_clause=debug_clause,
        length_clause=length_clause,
    )


_HALLUCINATION_RETRY_INSTRUCTION = (
    "[TRUTH_VIOLATION: {reason}]\n"
    "Your narrative contradicted established, FINAL facts of this world. "
    "Rewrite the response so it does NOT contradict them: a destroyed or consumed "
    "object is gone forever (it cannot be held, used, drawn, worn, or found intact); "
    "a dead character cannot speak, move, or act (reference them only as a corpse, "
    "memory, or absence). Keep the same scene, tone, and continuity, but obey the "
    "established truth. Output ONLY the required tag blocks, with <rolling_state> "
    "FIRST and closed before prose (<rolling_state>, <narrative>, <choices>, "
    "<state>, <ledger>{debug_clause}). Do NOT echo <prior_state> or "
    "<established_truth>."
)


def _full_validate(
    parsed: ParsedTurn,
    session: Dict[str, Any],
    player_action: Optional[str],
    early_game_stage: Optional[int] = None,
) -> Tuple[bool, str, str]:
    """Format validation, optional Stage-1 pacing check, then prose contradiction.

    Returns ``(ok, reason, kind)`` where kind ∈
    {"format", "pacing", "hallucination", "ok"}.
    """
    ok, reason = _validate_parsed(parsed, player_action=player_action)
    if not ok:
        return False, reason, "format"
    if early_game_stage == 1:
        pacing_reason = pacing.validate_opening_structure(parsed)
        if pacing_reason:
            return False, pacing_reason, "pacing"
    contradictions = gateway.detect_prose_contradictions(
        session.get("rolling_state"), parsed, player_action
    )
    if contradictions:
        return False, "; ".join(contradictions[:3]), "hallucination"
    return True, "", "ok"


async def _generate_validated_turn(
    session: Dict[str, Any], user_text: str,
    player_action: Optional[str] = None,
    secret_reveal_directive: str = "",
    replayability_directives: Optional[Dict[str, str]] = None,
) -> Tuple[ParsedTurn, str, Dict[str, Any]]:
    """Call the LLM, validate the parsed turn, and retry ONCE on failure.

    Returns ``(parsed, raw, meta)`` where meta aggregates model_used,
    fallback_events across both attempts, telemetry, and validation diagnostics.
    """
    early_game_stage = pacing.get_early_game_stage(session.get("turn_count", 0))
    dev_on = "[DEV_MODE: ON]" in user_text

    raw, meta = await _generate_turn(
        session,
        user_text,
        early_game_stage=early_game_stage,
        secret_reveal_directive=secret_reveal_directive,
        replayability_directives=replayability_directives,
    )
    parsed = parse_turn(raw)
    ok, reason, kind = _full_validate(
        parsed, session, player_action, early_game_stage=early_game_stage
    )
    if ok:
        if (
            dev_on
            and early_game_stage == 3
            and not pacing.has_engine_owned_development(session.get("rolling_state"))
        ):
            meta["pacing_stage3_no_engine_development"] = True
        return _finalize_validated_turn(parsed, raw, meta)

    debug_clause = ", <debug>" if dev_on else ""
    if kind == "hallucination":
        retry_note = _HALLUCINATION_RETRY_INSTRUCTION.format(
            reason=reason, debug_clause=debug_clause
        )
    elif kind == "pacing":
        retry_note = pacing.build_pacing_retry_instruction(reason, debug_clause)
    else:
        retry_note = _build_format_retry_instruction(
            reason, debug_clause, prose_mode=meta.get("prose_mode")
        )
    _log_validation_failure_diagnostic(
        raw,
        validator_kind=kind,
        validator_reason=reason,
        attempt="first",
        dev_on=dev_on,
    )
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
    # Same prose-mode completion floor as the first attempt (floors lose to caps).
    retry_prose_mode = prose_modes.resolve_prose_mode(meta.get("prose_mode"))
    if retry_prose_mode.max_tokens_floor:
        max_tokens = max(max_tokens, retry_prose_mode.max_tokens_floor)
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
            early_game_stage=early_game_stage,
            secret_reveal_directive=secret_reveal_directive,
            replayability_directives=replayability_directives,
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
            **_prompt_projection_trait_kwargs(session),
        )

        # Retry stays on the model that just answered; provider-level fallback
        # is still permitted if the retry call itself fails.
        primary_for_retry = normalize_runtime_model(
            meta.get("model_used") or settings.get("model") or DEFAULT_MODEL
        )
        retry_cost_mode = (
            session.get("cost_mode")
            or settings.get("cost_mode")
            or DEFAULT_COST_MODE
        )
        fallback_chain = build_automatic_fallback_chain(
            primary_for_retry,
            cost_mode=retry_cost_mode,
        )

        result2 = await gateway.invoke_llm(
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
        ok2, reason2, kind2 = _full_validate(
            parsed2, session, player_action, early_game_stage=early_game_stage
        )

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
            # Prose Length System v2 — same presentation budget across attempts.
            "prose_mode_requested": meta.get("prose_mode_requested"),
            "prose_mode": meta.get("prose_mode"),
            "prose_budget": meta.get("prose_budget"),
        }

        if ok2:
            if (
                dev_on
                and early_game_stage == 3
                and not pacing.has_engine_owned_development(session.get("rolling_state"))
            ):
                combined_meta["pacing_stage3_no_engine_development"] = True
            return _finalize_validated_turn(parsed2, raw2, combined_meta)

        _log_validation_failure_diagnostic(
            raw2,
            validator_kind=kind2,
            validator_reason=reason2,
            attempt="retry",
            dev_on=dev_on,
        )
        logger.warning(
            "Retry still invalid (%s/%s) — using best-available output",
            kind2,
            reason2,
        )
        if len(parsed2.choices or []) > len(parsed.choices or []):
            return _finalize_validated_turn(parsed2, raw2, combined_meta)

        first_with_retry = dict(meta)
        first_with_retry["validation_retried"] = True
        first_with_retry["validation_first_fail"] = reason
        first_with_retry["validation_second_fail"] = reason2
        first_with_retry["fallback_events"] = combined_meta["fallback_events"]
        return _finalize_validated_turn(parsed, raw, first_with_retry)
    except Exception as exc:
        logger.warning("Retry call raised %s — falling back to first attempt", exc)
        recovered = dict(meta)
        recovered["validation_retried"] = True
        recovered["validation_first_fail"] = reason
        recovered["retry_exception"] = str(exc)[:240]
        return _finalize_validated_turn(parsed, raw, recovered)


# ======================================================================
# ROUTES
# ======================================================================
def _session_debug_allowed(session: Dict[str, Any], settings: Dict[str, Any]) -> bool:
    """Per-turn debug is exposed only when server dev mode and session debug_mode are on."""
    return bool(settings.get("developer_mode")) and bool(session.get("debug_mode"))


def _meta_into_debug(
    base: Optional[Dict[str, str]], meta: Dict[str, Any]
) -> Dict[str, str]:
    """Merge engine telemetry from chat_completion_with_meta into the turn.debug dict.

    This dict is only surfaced behind the Developer Mode unlock — never shown to
    standard players (see player_api.build_player_turn).
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
    if meta.get("pacing_stage3_no_engine_development"):
        debug["pacing_stage3_no_engine_development"] = "true"
    if meta.get("secret_reveal_occurred"):
        debug["secret_reveal_occurred"] = "true"
    if meta.get("secret_reveal_mode"):
        debug["secret_reveal_mode"] = str(meta["secret_reveal_mode"])
    if meta.get("secret_reveal_index") is not None:
        debug["secret_reveal_index"] = str(meta["secret_reveal_index"])
    if meta.get("secret_reveal_id"):
        debug["secret_reveal_id"] = str(meta["secret_reveal_id"])
    # ---- Prose Length System v2 telemetry ----
    prose = meta.get("prose") or {}
    for key in (
        "requested_prose_mode",
        "effective_prose_mode",
        "requested_budget",
        "returned_character_count",
        "returned_paragraph_count",
        "returned_sentence_count",
        "final_character_count",
        "trimming_occurred",
        "retry_occurred",
    ):
        if prose.get(key) is not None:
            debug[f"prose_{key}"] = str(prose[key])
    # ---- Context Budget Governor v3.9 diagnostics ----
    budget = meta.get("budget") or {}
    for key, label in (
        ("estimated_prompt_tokens", "estimated_prompt_tokens"),
        ("context_budget_tokens", "context_budget_tokens"),
        ("context_over_budget", "context_over_budget"),
        ("context_trimmed", "context_trimmed"),
        ("compressed_prior_state", "compressed_prior_state"),
        ("projected_registry_caps", "projected_registry_caps"),
        ("trim_reason", "trim_reason"),
        ("estimated_tokens_removed", "estimated_tokens_removed"),
        ("protected_state_items_count", "protected_state_items_count"),
    ):
        if key in budget:
            debug[label] = str(budget[key])
    for key, value in meta.items():
        if not key.startswith("replayability_utility_ai_"):
            continue
        if key == "replayability_utility_ai_shadow_comparison":
            continue
        debug[key] = str(value)
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


async def ensure_story_creation_idempotency_indexes(db) -> None:
    """Prevent duplicate in-flight/completed creations for one device request key."""
    await db.sessions.create_index(
        [("device_id", 1), ("creation_request_id", 1)],
        unique=True,
        name="sessions_device_creation_request_unique",
        partialFilterExpression={"creation_request_id": {"$type": "string"}},
    )


@api_router.get("/")
async def root():
    return {"message": "Dice Reaction Story Engine v3.3"}


@api_router.get("/health")
async def health():
    return {
        "status": "ok",
        "llm_configured": ai_is_configured(),
    }


@api_router.get("/admin/runtime")
async def admin_runtime(_: None = Depends(require_admin)):
    """Snapshot of the AI routing runtime config (env + DB-resolved settings)."""
    if not ENABLE_DEBUG_PANEL:
        raise HTTPException(status_code=404, detail="Debug panel disabled")
    settings = await get_ai_settings()
    active_default_model = normalize_runtime_model(settings.get("model") or DEFAULT_MODEL)
    return {
        "active_default_model": active_default_model,
        "fallback_chain": build_automatic_fallback_chain(active_default_model),
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
async def admin_session_diagnostics(
    session_id: str, _: None = Depends(require_admin)
):
    """Per-session runtime diagnostics: active model, switch history, cost mode."""
    if not ENABLE_DEBUG_PANEL:
        raise HTTPException(status_code=404, detail="Debug panel disabled")
    session = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    settings = await get_ai_settings()
    effective_model = _resolve_requested_model(session, settings)
    latest = (
        await db.turns.find({"session_id": session_id}, {"_id": 0})
        .sort("turn_number", -1)
        .to_list(length=1)
    )
    last_debug = (latest[0].get("debug") if latest else None) or {}
    return {
        "session_id": session_id,
        "active_model": effective_model,
        "fallback_chain": build_automatic_fallback_chain(effective_model),
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
                "compressed_prior_state",
                "projected_registry_caps",
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
async def admin_get_settings(_: None = Depends(require_admin)):
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
async def admin_post_settings(
    req: AdminSettingsRequest, _: None = Depends(require_admin)
):
    # Validate model is in supported list (if provided)
    if req.model is not None:
        supported_ids = {m["id"] for m in get_supported_models()}
        if req.model not in supported_ids:
            raise HTTPException(status_code=400, detail=f"Unsupported model: {req.model}")
    if req.fallback_models is not None:
        if MODEL_QWEN_UNCENSORED in req.fallback_models:
            raise HTTPException(
                status_code=400,
                detail="Uncensored model cannot be placed in the automatic fallback chain",
            )
        for model_id in req.fallback_models:
            if model_id not in AUTOMATIC_FALLBACK_MODELS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported fallback model: {model_id}",
                )
    if req.default_mode is not None and req.default_mode not in ("basic", "advanced"):
        raise HTTPException(status_code=400, detail="default_mode must be 'basic' or 'advanced'")
    if req.compression_level is not None and req.compression_level not in ("light", "standard", "aggressive"):
        raise HTTPException(status_code=400, detail="compression_level must be light|standard|aggressive")

    patch = req.model_dump(exclude_none=True)
    updated = await set_ai_settings(patch)
    return {"settings": updated}


@api_router.get("/admin/models")
async def admin_list_models(_: None = Depends(require_admin)):
    return {"models": get_supported_models()}


# -------- Story flow --------------------------------------------------------
_CREATION_IN_PROGRESS_DETAIL = "Story creation already in progress"


def _normalize_creation_request_id(value: Optional[str]) -> Optional[str]:
    text = (value or "").strip()
    return text or None


async def _build_existing_creation_response(req: NewStoryRequest) -> Optional[Dict[str, Any]]:
    """Return an existing completed creation for a client idempotency key."""
    creation_request_id = _normalize_creation_request_id(req.creation_request_id)
    if not creation_request_id:
        return None
    session_doc = await db.sessions.find_one(
        {
            "device_id": req.device_id,
            "creation_request_id": creation_request_id,
        },
        {"_id": 0},
    )
    if not session_doc:
        return None
    if int(session_doc.get("turn_count") or 0) < 1:
        raise HTTPException(status_code=409, detail=_CREATION_IN_PROGRESS_DETAIL)
    turn_doc = await db.turns.find_one(
        {"session_id": session_doc["id"], "turn_number": 1},
        {"_id": 0},
    )
    if not turn_doc:
        raise HTTPException(status_code=409, detail=_CREATION_IN_PROGRESS_DETAIL)
    settings = await get_ai_settings()
    include_debug = _session_debug_allowed(session_doc, settings)
    return {
        "session_id": session_doc["id"],
        "turn": build_player_turn(turn_doc, include_debug=include_debug),
        "session": build_new_story_session_payload(session_doc),
    }


@api_router.post("/story/new")
async def new_story(req: NewStoryRequest, request: Request):
    existing = await _build_existing_creation_response(req)
    if existing:
        return existing

    client_ip = resolve_client_ip(request)
    consumed_buckets = await check_story_creation_limits(db, client_ip, req.device_id)
    acquired_slot = False
    try:
        try:
            await acquire_story_creation_slot(db)
            acquired_slot = True
        except HTTPException:
            await _rollback_bucket_reservations(db, consumed_buckets)
            raise
        return await _create_new_story(req)
    finally:
        if acquired_slot:
            await release_story_creation_slot(db)


async def _cleanup_provisional_story(session_id: str) -> None:
    """Remove session and any turns created during a failed story creation."""
    await db.turns.delete_many({"session_id": session_id})
    await db.sessions.delete_one({"id": session_id})


async def _rollback_story_action_persist(
    session_id: str,
    turn_id: str,
    session_snapshot: Dict[str, Any],
    attempted_update_set: Optional[Dict[str, Any]],
    *,
    turn_inserted: bool,
    session_updated: bool,
) -> None:
    """Compensate partial story_action persistence. Raises on rollback failure."""
    if turn_inserted:
        await db.turns.delete_one({"session_id": session_id, "id": turn_id})
    if session_updated:
        restore_fields = {
            key: session_snapshot[key]
            for key in (
                "turn_count",
                "last_narrative_snippet",
                "last_state",
                "rolling_state",
                "replayability_state",
                "updated_at",
                "debug_mode",
                "rolling_state_updated_at",
                "active_model",
                "model_switches",
            )
            if key in session_snapshot
        }
        cas_filter: Dict[str, Any] = {"id": session_id}
        if attempted_update_set:
            if "turn_count" in attempted_update_set:
                cas_filter["turn_count"] = attempted_update_set["turn_count"]
            if "rolling_state" in attempted_update_set:
                cas_filter["rolling_state"] = attempted_update_set["rolling_state"]
        result = await db.sessions.update_one(cas_filter, {"$set": restore_fields})
        if result.matched_count == 0:
            logger.warning(
                "session rollback skipped for session %s: compare-and-set miss",
                session_id,
            )


async def _insert_story_action_turn(turn_doc: Dict[str, Any]) -> None:
    await db.turns.insert_one(turn_doc)


async def _apply_story_action_session_update(
    session_id: str, update_set: Dict[str, Any]
) -> None:
    await db.sessions.update_one({"id": session_id}, {"$set": update_set})


async def _cas_update_story_action_session(
    session_id: str,
    lease_token: str,
    expected_turn_count: int,
    update_set: Dict[str, Any],
    meta: Dict[str, Any],
    turn_number: int,
) -> bool:
    """Final session write: lease token + expected turn_count CAS, model lock folded in."""
    model_set, model_push = build_model_lock_patch(meta, turn_number)
    final_set = {**update_set, **model_set}
    ops: Dict[str, Any] = {"$set": final_set}
    if model_push:
        ops["$push"] = model_push
    cas_filter = build_persist_cas_filter(
        session_id, lease_token, expected_turn_count
    )
    result = await db.sessions.update_one(cas_filter, ops)
    if result.matched_count:
        fe = list(meta.get("fallback_events") or [])
        if fe:
            logger.warning(
                "Session %s model switch: %s (turn %s)",
                session_id,
                " → ".join([fe[0].get("from") or ""] + [e.get("to") or "" for e in fe]),
                turn_number,
            )
        return True
    logger.info("action persistence CAS conflict for session %s", session_id)
    return False


async def _persist_story_action_turn(
    session_id: str,
    turn_number: int,
    turn_doc: Dict[str, Any],
    update_set: Dict[str, Any],
    session_snapshot: Dict[str, Any],
    meta: Dict[str, Any],
    *,
    lease_token: str,
    expected_turn_count: int,
) -> None:
    """Persist one story_action turn: insert turn, then lease+turn_count CAS session update."""
    turn_inserted = False
    session_updated = False
    try:
        await _insert_story_action_turn(turn_doc)
        turn_inserted = True
        if await _cas_update_story_action_session(
            session_id,
            lease_token,
            expected_turn_count,
            update_set,
            meta,
            turn_number,
        ):
            session_updated = True
            return
        await db.turns.delete_one({"session_id": session_id, "id": turn_doc["id"]})
        raise ActionLeaseLost()
    except ActionLeaseLost:
        raise
    except Exception:
        logger.exception("story persistence failed during story_action")
        try:
            await _rollback_story_action_persist(
                session_id,
                turn_doc["id"],
                session_snapshot,
                update_set,
                turn_inserted=turn_inserted,
                session_updated=session_updated,
            )
        except Exception:
            logger.exception(
                "story_action persistence rollback failed for session %s turn_id %s",
                session_id,
                turn_doc.get("id"),
            )
            raise HTTPException(status_code=502, detail=_STORY_ENGINE_UNAVAILABLE)
        raise HTTPException(status_code=502, detail=_STORY_ENGINE_UNAVAILABLE)


async def _create_new_story(req: NewStoryRequest):
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

    replayability_state, frozen_rb_directives = replayability.init_new_story(
        genre=effective_genre,
        role=effective_role,
        tone=effective_tone,
        difficulty=effective_difficulty,
        scenario_id=req.scenario_id,
        custom_premise=effective_premise,
        custom_world_setup=custom_setup,
        scenario=scenario,
    )

    primary_model = normalize_runtime_model(settings.get("model") or DEFAULT_MODEL)

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
        prose_mode=prose_modes.resolve_prose_mode_name(req.prose_mode),
        scenario_id=req.scenario_id,
        creation_request_id=_normalize_creation_request_id(req.creation_request_id),
        replayability_state=replayability_state,
        # ---- session-locked AI routing snapshot ----
        active_model=primary_model,
        fallback_chain=build_automatic_fallback_chain(
            primary_model,
            cost_mode=(settings.get("cost_mode") or DEFAULT_COST_MODE).lower(),
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
        f"Open in medias res with a specific immediate situation — not pure setup, routine, or generic exploration. "
        f"Give the player a reason to decide now and connect first choices to that situation. "
        f"Populate state Pressure and at least one objectives or unresolved stake. "
        f"Preserve hidden-threat secrecy; do not reveal latent threats merely to create pace. "
        f"Populate the inventory ledger with the starting kit. "
        f"Present the appropriate number of meaningful first choices for the mode. "
        f"Honour the difficulty modifier on this very first roll. "
        f"Emit <rolling_state> first, close it completely, then emit all remaining required blocks"
        + (", <debug>" if dev_mode else "")
        + "."
    )

    try:
        await db.sessions.insert_one(session.model_dump())
    except DuplicateKeyError:
        existing = await _build_existing_creation_response(req)
        if existing:
            return existing
        raise HTTPException(status_code=409, detail=_CREATION_IN_PROGRESS_DETAIL)

    try:
        parsed, raw, meta = await _generate_validated_turn(
            session.model_dump(),
            opening_prompt,
            replayability_directives=frozen_rb_directives,
        )
    except AIServiceError:
        logger.exception("AI service failed during new_story")
        await _cleanup_provisional_story(session.id)
        raise HTTPException(status_code=502, detail=_STORY_ENGINE_UNAVAILABLE)
    except Exception:
        logger.exception("LLM call failed during new_story")
        await _cleanup_provisional_story(session.id)
        raise HTTPException(status_code=502, detail=_STORY_ENGINE_UNAVAILABLE)

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
    # Ch 29 — seed NPC→player relationship vectors from the opening scene.
    guard_adjustments.extend(
        relationships.update_relationship_calculus(parsed, None, merged_rolling, None, 1)
    )
    # HUD — drop objective guidance; set Danger/Momentum chips + Pressure line.
    guard_adjustments.extend(hud.shape_hud(parsed.state, merged_rolling))
    guard_adjustments.extend(
        replayability.enforce_authoritative(merged_rolling, replayability_state)
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
    try:
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
                "replayability_state": replayability_state,
                "updated_at": datetime.now(timezone.utc),
            }},
        )

        # Persist session-level model lock + any fallback switch ledger.
        await _persist_model_lock(session.id, meta, at_turn=1)
    except Exception:
        logger.exception("story persistence failed during new_story")
        await _cleanup_provisional_story(session.id)
        raise HTTPException(status_code=502, detail=_STORY_ENGINE_UNAVAILABLE)

    session_doc = session.model_dump(mode="json")
    session_doc["replayability_state"] = replayability_state
    include_debug = _session_debug_allowed(session_doc, settings)
    return {
        "session_id": session.id,
        "turn": build_player_turn(turn.model_dump(mode="json"), include_debug=include_debug),
        "session": build_new_story_session_payload(session_doc),
    }


@api_router.post("/story/action")
async def story_action(req: ActionRequest, device_id: str = Depends(require_device_id)):
    lease_token: Optional[str] = None
    session_id = req.session_id
    try:
        session, lease_token = await acquire_action_lease(db, session_id, device_id)
        expected_turn_count = session.get("turn_count", 0)
        next_turn_number = expected_turn_count + 1

        debug_marker = "[DEV_MODE: ON]" if (await get_ai_settings()).get("developer_mode") and req.debug_mode else "[DEV_MODE: OFF]"
        difficulty_marker = f"[DIFFICULTY: {session.get('difficulty', 'standard')}]"
        mode_marker = f"[MODE: {session.get('mode', DEFAULT_MODE)}]"
        user_text = f"{debug_marker}\n{difficulty_marker}\n{mode_marker}\n\nPlayer action: {req.action_text}"

        working_rolling, secret_directive, reveal_diag = secrets.prepare_turn_reveal(
            session.get("rolling_state"),
            req.action_text,
            next_turn_number,
        )

        frozen_rb_directives: Optional[Dict[str, str]] = None
        working_replayability = copy.deepcopy(session.get("replayability_state"))
        rb_diag: Dict[str, Any] = {}
        if replayability.replayability_active(session):
            working_replayability, frozen_rb_directives, rb_diag, _rb_thresholds, cast_rolling = (
                replayability.prepare_action_turn(
                    working_replayability, next_turn_number, rolling_state=working_rolling
                )
            )
            if cast_rolling:
                working_rolling = cast_rolling

        gen_session = dict(session)
        gen_session["rolling_state"] = working_rolling

        try:
            parsed, raw, meta = await _generate_validated_turn(
                gen_session,
                user_text,
                player_action=req.action_text,
                secret_reveal_directive=secret_directive,
                replayability_directives=frozen_rb_directives,
            )
        except AIServiceError:
            logger.exception("AI service failed during story_action")
            raise HTTPException(status_code=502, detail=_STORY_ENGINE_UNAVAILABLE)
        except Exception:
            logger.exception("LLM call failed during story_action")
            raise HTTPException(status_code=502, detail=_STORY_ENGINE_UNAVAILABLE)

        secrets.merge_reveal_diagnostics(meta, reveal_diag)
        replayability.merge_replayability_diagnostics(meta, rb_diag)
        guard_adjustments = _apply_state_supremacy(session, parsed, req.action_text)
        guard_adjustments.extend(_apply_object_permanence(parsed))

        # ---- Anti-Hallucination Gateway (Ch 31) — STRIP illegal mutations ----
        prior_rolling = working_rolling
        guard_adjustments.extend(
            gateway.strip_illegal_state_changes(
                prior_rolling, session.get("last_state"), parsed, req.action_text
            )
        )
        enriched_debug = _meta_into_debug(parsed.debug, meta)

        # ---- Rolling Memory Compression v3.8 ----
        merged_rolling = consolidate_rolling_state(prior_rolling, parsed.rolling_state)
        guard_adjustments.extend(
            secrets.enforce_authoritative_registry(
                merged_rolling,
                working_rolling.get("secret_registry"),
            )
        )

        # Ch 14 P1 — actor_stress is engine-owned; restore it after the merge so
        # the LLM can never clobber accumulated stress (mirrors secret_registry).
        guard_adjustments.extend(
            stress.enforce_authoritative_stress(
                merged_rolling,
                working_rolling.get("actor_stress"),
            )
        )
        if replayability.replayability_active(session) and working_replayability:
            world_guard = world_consumers.enforce_consumer_world_state(
                merged_rolling,
                prior_rolling,
                working_replayability,
                next_turn_number,
            )
            guard_adjustments.extend(world_guard.get("adjustments") or [])
            for key, value in (world_guard.get("diagnostics") or {}).items():
                if value not in (0, False, None, [], {}):
                    rb_diag[key] = value

        guard_adjustments.extend(
            _apply_ledger_object_permanence(parsed, authoritative_state=merged_rolling)
        )
        guard_adjustments.extend(_apply_room_audit(parsed, merged_rolling))
        guard_adjustments.extend(
            _apply_npc_memory_bounds(merged_rolling, current_turn=next_turn_number)
        )
        guard_adjustments.extend(_apply_faction_consequence_tick(merged_rolling))
        guard_adjustments.extend(
            _apply_delayed_consequence_tick(merged_rolling, current_turn=next_turn_number)
        )
        guard_adjustments.extend(
            _apply_rumour_propagation_tick(merged_rolling, current_turn=next_turn_number)
        )
        guard_adjustments.extend(_apply_rolling_state_hygiene(merged_rolling))
        guard_adjustments.extend(
            gateway.update_death_registry(
                parsed, prior_rolling, merged_rolling, req.action_text
            )
        )
        # Ch 31 extension — active scene cast is engine-protected: NPCs the
        # model silently dropped are restored unless an engine-authorised
        # exit, movement, or death exists. Runs after the death registry so
        # it sees this turn's final `deceased` state.
        guard_adjustments.extend(
            gateway.preserve_active_scene_cast(prior_rolling, merged_rolling)
        )
        guard_adjustments.extend(
            gateway.update_destruction_registry(
                parsed, prior_rolling, merged_rolling, req.action_text
            )
        )
        guard_adjustments.extend(
            relationships.update_relationship_calculus(
                parsed, prior_rolling, merged_rolling, req.action_text, next_turn_number
            )
        )
        merged_after_calculus = copy.deepcopy(merged_rolling)
        if replayability.replayability_active(session):
            working_replayability, lc_adjustments = replayability.finalize_living_cast_relationships(
                working_replayability,
                merged_rolling,
                next_turn_number,
            )
            guard_adjustments.extend(lc_adjustments)
        guard_adjustments.extend(hud.shape_hud(parsed.state, merged_rolling))
        if replayability.replayability_active(session):
            guard_adjustments.extend(
                replayability.enforce_authoritative(merged_rolling, working_replayability)
            )
            qualifying_sources = replayability.collect_qualifying_echo_sources(
                prior_rolling=prior_rolling,
                merged_rolling=merged_after_calculus,
                turn_number=next_turn_number,
                guard_adjustments=guard_adjustments,
            )
            working_replayability = replayability.finalize_action_turn(
                working_replayability,
                qualifying_sources,
                next_turn_number,
            )
        if guard_adjustments:
            enriched_debug["state_guard_adjustments"] = "; ".join(guard_adjustments)

        settings_for_metrics = await get_ai_settings()
        memory_depth = int(settings_for_metrics.get("memory_depth", DEFAULT_MEMORY_DEPTH))
        older_threshold = next_turn_number - memory_depth
        older_turns = []
        if older_threshold > 0:
            older_turns = await db.turns.find(
                {"session_id": session_id, "turn_number": {"$lte": older_threshold}},
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
            session_id=session_id,
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

        session_snapshot = {
            "turn_count": expected_turn_count,
            "last_narrative_snippet": session.get("last_narrative_snippet"),
            "last_state": copy.deepcopy(session.get("last_state")),
            "rolling_state": copy.deepcopy(session.get("rolling_state")),
            "replayability_state": copy.deepcopy(session.get("replayability_state")),
            "updated_at": session.get("updated_at"),
            "debug_mode": session.get("debug_mode"),
            "rolling_state_updated_at": session.get("rolling_state_updated_at"),
            "active_model": session.get("active_model"),
            "model_switches": copy.deepcopy(session.get("model_switches") or []),
        }

        snippet = (parsed.paragraphs[0][:180] + "…") if parsed.paragraphs else ""
        update_set: Dict[str, Any] = {
            "turn_count": next_turn_number,
            "last_narrative_snippet": snippet,
            "last_state": parsed.state,
            "updated_at": datetime.now(timezone.utc),
            "debug_mode": req.debug_mode,
        }
        if merged_rolling:
            update_set["rolling_state"] = merged_rolling
            update_set["rolling_state_updated_at"] = datetime.now(timezone.utc)
        elif parsed.rolling_state:
            update_set["rolling_state"] = parsed.rolling_state
            update_set["rolling_state_updated_at"] = datetime.now(timezone.utc)
        if replayability.replayability_active(session) and working_replayability:
            update_set["replayability_state"] = working_replayability

        await _persist_story_action_turn(
            session_id,
            next_turn_number,
            turn.model_dump(),
            update_set,
            session_snapshot,
            meta,
            lease_token=lease_token,
            expected_turn_count=expected_turn_count,
        )

        settings = await get_ai_settings()
        include_debug = bool(settings.get("developer_mode")) and bool(req.debug_mode)
        return {
            "turn": build_player_turn(
                turn.model_dump(mode="json"),
                include_debug=include_debug,
            )
        }
    except ActionLeaseConflict:
        raise HTTPException(status_code=409, detail=ACTION_CONFLICT_DETAIL)
    except ActionLeaseLost:
        raise HTTPException(status_code=409, detail=ACTION_CONFLICT_DETAIL)
    finally:
        if lease_token:
            await release_action_lease(db, session_id, lease_token)


@api_router.post("/story/session/{session_id}/mode")
async def set_session_mode(
    session_id: str,
    req: SessionModeRequest,
    device_id: str = Depends(require_device_id),
):
    await fetch_owned_session(db, session_id, device_id)
    if req.mode not in ("basic", "advanced"):
        raise HTTPException(status_code=400, detail="mode must be 'basic' or 'advanced'")
    result = await db.sessions.update_one(
        {"id": session_id},
        {"$set": {"mode": req.mode, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"mode": req.mode}


@api_router.get("/story/session/{session_id}/history")
async def session_causal_history(session_id: str, device_id: str = Depends(require_device_id)):
    """Player-safe "Why this happened" causal chain — built from engine state only.

    Reads guard receipts, transition receipts, consequence-echo logs, and
    relationship vectors from persisted documents; never narrative prose.
    Output contains no internal identifiers or engine field names.
    """
    session = await fetch_owned_session(db, session_id, device_id)
    turns = await db.turns.find(
        {"session_id": session_id},
        {"_id": 0, "turn_number": 1, "player_action": 1, "debug": 1, "rolling_state": 1},
    ).sort("turn_number", 1).to_list(length=500)
    return {
        "session_id": session_id,
        "title": session.get("title"),
        "history": causal_history.build_causal_history(session, turns),
    }


@api_router.get("/story/session/{session_id}/export")
async def export_session(session_id: str, device_id: str = Depends(require_device_id)):
    """Player-safe export: verified ownership + always-sanitised chronicle payload."""
    session = await fetch_owned_session(db, session_id, device_id)
    turns = await db.turns.find({"session_id": session_id}, {"_id": 0}).sort("turn_number", 1).to_list(length=500)
    safe_session = build_player_session(session)
    safe_turns = [build_player_turn(t) for t in turns]
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "session": safe_session,
        "turns": safe_turns,
        "summary": {
            "turn_count": len(turns),
            "last_state": build_player_state(session.get("last_state")),
        },
    }


@api_router.get("/story/session/{session_id}/export/raw")
async def export_session_raw(
    session_id: str,
    _: None = Depends(require_admin),
):
    """Administrative export: full unsanitised session + turns (admin key only)."""
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
async def reset_session(session_id: str, device_id: str = Depends(require_device_id)):
    """Delete all turns and rolling state but keep the session shell (genre/role/difficulty/mode).
    The client should then re-call /story/action with a meaningful first action, or the next call
    to /story/new with the same scenario."""
    await fetch_owned_session(db, session_id, device_id)
    await db.turns.delete_many({"session_id": session_id})
    await db.sessions.update_one(
        {"id": session_id},
        {"$set": {
            "turn_count": 0,
            "last_narrative_snippet": "",
            "last_state": {},
            "rolling_state": None,
            "replayability_state": None,
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    return {"reset": True}


@api_router.get("/story/sessions")
async def list_sessions(device_id: str = Depends(require_device_id)):
    cursor = db.sessions.find({"device_id": device_id}, {"_id": 0}).sort("updated_at", -1)
    sessions = await cursor.to_list(length=200)
    sessions = [build_player_session(s) for s in sessions]
    return {"sessions": sessions}


@api_router.get("/story/session/{session_id}")
async def get_session(session_id: str, device_id: str = Depends(require_device_id)):
    raw_session = await fetch_owned_session(db, session_id, device_id)
    turns = await db.turns.find({"session_id": session_id}, {"_id": 0}).sort("turn_number", 1).to_list(length=500)
    settings = await get_ai_settings()
    include_debug = _session_debug_allowed(raw_session, settings)
    session = build_player_session(raw_session)
    turns = [build_player_turn(t, include_debug=include_debug) for t in turns]
    return {"session": session, "turns": turns}


@api_router.get("/story/session/{session_id}/latest")
async def get_latest_turn(session_id: str, device_id: str = Depends(require_device_id)):
    session = await fetch_owned_session(db, session_id, device_id)
    turn = await db.turns.find_one({"session_id": session_id}, {"_id": 0}, sort=[("turn_number", -1)])
    if not turn:
        raise HTTPException(status_code=404, detail="No turns found")
    settings = await get_ai_settings()
    include_debug = _session_debug_allowed(session, settings)
    return {"turn": build_player_turn(turn, include_debug=include_debug)}


@api_router.delete("/story/session/{session_id}")
async def delete_session(session_id: str, device_id: str = Depends(require_device_id)):
    await fetch_owned_session(db, session_id, device_id)
    await db.turns.delete_many({"session_id": session_id})
    result = await db.sessions.delete_one({"id": session_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True}


app.include_router(api_router)

_cors_origins_raw = os.environ.get("CORS_ORIGINS", "*")
_cors_origins = ["*"] if _cors_origins_raw.strip() == "*" else [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
_cors_allow_headers = [
    "Content-Type",
    "X-Device-Id",
    "X-Admin-Api-Key",
    "Authorization",
]

app.add_middleware(
    CORSMiddleware,
    allow_credentials=_cors_origins != ["*"],
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=_cors_allow_headers if _cors_origins != ["*"] else ["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup_rate_limit_indexes():
    await ensure_rate_limit_indexes(db)
    await ensure_action_concurrency_indexes(db)
    await ensure_story_creation_idempotency_indexes(db)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
