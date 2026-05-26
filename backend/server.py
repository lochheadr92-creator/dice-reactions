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
)
from scenarios import get_scenarios, get_scenario  # noqa: E402

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
  "npcs": [{"name": "name", "role": "what they are", "stance": "ally/neutral/hostile/unknown", "last_seen": "where", "note": "one-line memory"}],
  "factions": [{"name": "name", "pressure": "what they're doing this turn", "scale": "local/regional/systemic"}],
  "pressure_horizon": {"immediate": "the threat landing this turn or next", "emerging": "the threat building 2-4 turns out", "latent": "the buried threat that will fire when conditions align"},
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
    title: str = "Untitled Chronicle"
    turn_count: int = 0
    last_narrative_snippet: str = ""
    last_state: Dict[str, str] = Field(default_factory=dict)
    rolling_state: Optional[Dict[str, Any]] = None  # latest compressed packet
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
        prior_state_block = (
            "<prior_state>\n"
            + _json.dumps(rolling, indent=2, ensure_ascii=False)
            + "\n</prior_state>\n\n"
        )
        user_text = prior_state_block + user_text

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

    result = await chat_completion_with_meta(
        messages=messages,
        primary_model=requested_model,
        fallback_chain=fallback_chain,
        temperature=settings.get("temperature"),
        max_tokens=max_tokens,
        max_retries_per_model=MAX_RETRIES,
    )
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


def _validate_parsed(parsed: ParsedTurn) -> Tuple[bool, str]:
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

    return True, ""


_RETRY_INSTRUCTION = (
    "[VALIDATION_RETRY: {reason}]\n"
    "Rewrite the previous response in valid player-facing format with "
    "2–4 short paragraphs (under 1200 characters total) and 4–6 A–F choices. "
    "Every choice must be on its own line beginning with the letter and a period "
    "(A. B. C. D. and optionally E. F.). "
    "Do NOT include any Roll / Modifiers / Final / Active systems / Delayed trigger / "
    "Latent trigger / Scale text anywhere outside the <debug> block. "
    "Do NOT echo <prior_state>. Output ONLY the required tag blocks "
    "(<narrative>, <choices>, <state>, <ledger>, <rolling_state>"
    "{debug_clause}). Choices must cover meaningfully different intents — include a "
    "cautious option, a direct/risky option, an investigative option, and a "
    "social/communication option where the scene supports it."
)


async def _generate_validated_turn(
    session: Dict[str, Any], user_text: str
) -> Tuple[ParsedTurn, str, Dict[str, Any]]:
    """Call the LLM, validate the parsed turn, and retry ONCE on failure.

    Returns ``(parsed, raw, meta)`` where meta aggregates model_used,
    fallback_events across both attempts, telemetry, and validation diagnostics.
    """
    raw, meta = await _generate_turn(session, user_text)
    parsed = parse_turn(raw)
    ok, reason = _validate_parsed(parsed)
    if ok:
        return parsed, raw, meta

    dev_on = "[DEV_MODE: ON]" in user_text
    debug_clause = ", <debug>" if dev_on else ""
    retry_note = _RETRY_INSTRUCTION.format(reason=reason, debug_clause=debug_clause)
    logger.info("Turn validation failed (%s) — retrying once", reason)

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
        raw2 = result2["content"]
        parsed2 = parse_turn(raw2)
        ok2, reason2 = _validate_parsed(parsed2)

        combined_meta: Dict[str, Any] = {
            "model_used": result2["model_used"],
            "model_requested": meta.get("model_requested"),
            "telemetry": result2.get("telemetry"),
            "fallback_events": list(meta.get("fallback_events") or [])
            + list(result2.get("fallback_events") or []),
            "attempts_per_model": result2.get("attempts_per_model"),
            "validation_retried": True,
            "validation_first_fail": reason,
            "validation_second_fail": None if ok2 else reason2,
        }

        if ok2:
            return parsed2, raw2, combined_meta

        logger.warning(
            "Retry still invalid (%s) — using best-available output",
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
    if meta.get("validation_first_fail"):
        debug["validation_first_fail"] = str(meta["validation_first_fail"])
    if meta.get("validation_second_fail"):
        debug["validation_second_fail"] = str(meta["validation_second_fail"])
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

    enriched_debug = _meta_into_debug(parsed.debug, meta)

    turn = TurnRecord(
        session_id=session.id,
        turn_number=1,
        player_action=None,
        narrative=parsed.narrative,
        paragraphs=parsed.paragraphs,
        choices=parsed.choices,
        state=parsed.state,
        ledger=parsed.ledger,
        rolling_state=parsed.rolling_state,
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
            "rolling_state": parsed.rolling_state,
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
        parsed, raw, meta = await _generate_validated_turn(session, user_text)
    except AIServiceError as e:
        logger.exception("AI service failed")
        raise HTTPException(status_code=502, detail=f"Story engine error: {e}")
    except Exception as e:
        logger.exception("LLM call failed")
        raise HTTPException(status_code=502, detail=f"Story engine error: {e}")

    next_turn_number = session.get("turn_count", 0) + 1
    enriched_debug = _meta_into_debug(parsed.debug, meta)

    turn = TurnRecord(
        session_id=req.session_id,
        turn_number=next_turn_number,
        player_action=req.action_text,
        narrative=parsed.narrative,
        paragraphs=parsed.paragraphs,
        choices=parsed.choices,
        state=parsed.state,
        ledger=parsed.ledger,
        rolling_state=parsed.rolling_state,
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
    # Only overwrite rolling_state if the model actually emitted one
    if parsed.rolling_state:
        update_set["rolling_state"] = parsed.rolling_state
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
