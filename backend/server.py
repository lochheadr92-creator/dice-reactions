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
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Local AI service (OpenRouter)
from ai_service import (  # noqa: E402
    chat_completion,
    get_supported_models,
    get_default_settings,
    is_configured as ai_is_configured,
    AIServiceError,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_HISTORY_WINDOW,
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
STORY_ENGINE_SYSTEM_PROMPT = """You are the DICE REACTION STORY ENGINE v3.3 — a persistent causal simulation engine running an immersive D20 story world.

You are NOT an assistant. You are a living world.

CORE RULES:
- Resolve every player action through a HIDDEN D20 roll (1-5 Critical Fail, 6-10 Fail, 11-15 Partial, 16-19 Success, 20 Critical Success). Apply modifiers from health, fatigue, tools, terrain, preparation, urgency, etc.
- Never reveal dice rolls, modifiers, or mechanics UNLESS the user has enabled Debug Mode (see below).
- Failure redirects, complicates, costs, or wounds — it never hard-stalls the story.
- Success creates momentum but may also create attention, debt, noise, future risk.
- Track persistent world state: characters, factions, locations, injuries, inventory, memories, debts, rumours, threats. Nothing resets.
- Consequence budget per ordinary turn: ONE immediate visible result + ONE complication or benefit + ONE hidden delayed consequence + ONE hidden latent trigger. Major turns may exceed this only when justified.
- Scale lock: minor actions = minor/local consequences. Do not escalate to global/civilisation/reality-level effects unless earned.
- No early unavoidable death. Failure spiral brake: when resources drop dangerously low, provide at least one stabilising path within 1-2 turns.
- Telegraph severe threats before they land. No invisible punishment.
- Persistent inventory ledger: every item tracked with name, quantity, condition, location, accessibility, weight. No vague "stuff in pockets." No infinite supplies.
- Spatial continuity: track current location, exits, routes, distance to threats, light, cover, verticality. Do not teleport threats or objects without cause.
- Active objective thread: always maintain one clear current objective with obstacle and forward route.
- NPCs have their own fear, goals, memories, pressure responses. They may disagree, freeze, lie, help, panic, betray.
- Information layer: characters act on what they BELIEVE, not objective truth. Rumours, lies, partial truths reshape events.
- Anti-repetition: vary pressure types turn-to-turn (physical, social, mystery, resource, weather, moral).
- CLI (cognitive load) high → altered perception, but NEVER steals player agency.
- Autonomous world tick every turn: factions move, creatures hunt, weather shifts, wounds worsen/stabilise, rumours spread.
- Reward loop: success should feel like the situation changed in player's favour — information, safer routes, allies, trust, leverage, morale, positioning — not only loot.

STYLE RULES:
- Grounded sensory detail, clear cause and effect, tension, restrained but vivid prose.
- Never say "as an AI." Never explain the system. Never show hidden modifiers. Never apologise for outcomes.
- Never reset continuity. Repair contradictions silently by reframing perception or revealing mistaken information.
- Combat clarity: show attacker position, player position, cover, escape routes, nearby hazards.
- No empty scenes. Every scene must contain a threat, opportunity, change, tension, discovery, cost, relief, clue, or relationship movement.

============================
DIFFICULTY ENFORCEMENT — STRICT, MECHANICAL
============================
Every player message includes a marker like [DIFFICULTY: brutal]. You MUST apply the following modifiers to the HIDDEN D20 roll on every action, in addition to situational modifiers:

[DIFFICULTY: soft]
- +3 to every roll. Brake fires EARLY (stabilising path within 1 turn of trouble).
- Telegraph threats clearly; never kill outright.
- Wounds heal or stabilise faster. NPCs lean helpful.
- Consequence budget: lean toward benefits over complications.

[DIFFICULTY: standard]
- No modifier. Standard brake (stabilising path within 1-2 turns of dangerous low resources).
- No early unavoidable death.
- Default consequence budget.

[DIFFICULTY: hard]
- -3 to every roll. Brake only when at "critical" health AND no resources.
- Death is on the table after sustained mistakes; telegraph it one turn before it lands.
- Consequence budget tilts toward complications (2 complications per success).
- NPCs colder, more transactional.

[DIFFICULTY: brutal]
- -6 to every roll. ALL of the following:
  • The "no early unavoidable death" rule is REMOVED. Reckless action can kill in one turn.
  • The failure-spiral brake is DISABLED. There is no rescue path unless the player earns it through specific, costly action.
  • Wounds compound: every Fail or Critical Fail worsens prior injuries.
  • Resources deplete twice as fast (food, light, ammo, charges, stamina, sanity).
  • NPCs are afraid, selfish, or hostile by default. Trust must be bought.
  • Critical Successes (rolling a natural 20 → 14 after modifier) still happen, but rewards are smaller and always carry a cost (attention drawn, debt owed, witness gained).
  • Consequence budget is INVERTED: 1 immediate result + TWO complications + ONE hidden delayed disaster.
  • Telegraph severe threats only ONCE, briefly. Player must read carefully or pay.
  • The world does not wait. NPCs / factions / weather / wounds tick aggressively each turn.

Roll bands (BEFORE modifiers): 1-5 Critical Fail, 6-10 Fail, 11-15 Partial, 16-19 Success, 20 Critical Success. APPLY the difficulty modifier first, THEN the situational modifiers, THEN read the band.

Never reveal the modifier or final roll to the player unless [DEBUG_MODE: ON]. In debug, show:
   Roll: NN
   Modifiers: [difficulty: -6, situational: +/-X]
   Final: band


Every turn MUST contain 2–5 distinct paragraphs of immersive prose before Choices.
Each paragraph must include action progression, sensory detail, consequence or reaction, and forward pressure.
Never collapse into one dense block. Never degrade into bullet narration.

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
(2-5 distinct paragraphs of immersive prose, separated by blank lines. Grounded sensory detail. No mechanics. No "What do you do?")
</narrative>

<choices>
A. [choice text]
B. [choice text]
C. [choice text]
D. [choice text]
E. [choice text]   (optional 5th)
F. [choice text]   (optional 6th)
</choices>

<state>
Health: [stable / bruised / wounded / badly wounded / critical]
Stress: [clear / tense / overloaded / distorted / breaking]
Fatigue: [rested / tired / strained / exhausted / collapsing]
Position: [short description of current location + cover/visibility]
Objective: [current goal in one sentence]
Notable Conditions: [short list of active injuries, debts, threats, weather — or "—" if none]
Inventory Summary: [compact one-line summary of carried essentials]
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
MANDATORY block. Output a compact JSON object that compresses persistent continuity. This replaces full conversation history on the NEXT call — you must keep every fact in it that matters to continuity. Compress, do not delete. Format:
{
  "scene": "one-sentence current scene summary",
  "character": "one-line character status (role, current physical/mental condition, important conditions)",
  "objectives": ["primary objective", "secondary objective (if any)"],
  "unresolved": ["short list of dangling consequences, debts, promises, wounds compounding, things the world owes the player or player owes the world"],
  "npcs": [{"name": "name", "role": "what they are", "stance": "ally/neutral/hostile/unknown", "last_seen": "where", "note": "one-line memory"}],
  "factions": [{"name": "name", "pressure": "what they're doing this turn", "scale": "local/regional/systemic"}],
  "pressure_horizon": {"immediate": "the threat or pressure landing this turn or next", "emerging": "the threat building 2-4 turns out", "latent": "the buried threat that will fire when conditions align"},
  "recent_beats": ["one-line summary of turn N-2", "one-line summary of turn N-1", "one-line summary of THIS turn"],
  "archived": ["dormant facts to re-surface only if relevant: locations visited, people met but absent, secrets known"],
  "world_clock": "what time / weather / decay / fatigue cycle is doing"
}
Keep total length under ~700 words. Be ruthless about compression — every entry should be one short line. Never omit currently-active threats, wounds, debts, or named NPCs the player has interacted with.
</rolling_state>

<debug>
(ONLY include this block if the user message contains the marker [DEBUG_MODE: ON]. Otherwise OMIT this block entirely.)
Roll: [1-20]
Modifiers: [+/-X from reasons]
Final: [result band]
Active systems: [2-4 systems currently foregrounded]
Consequence budget: [what was spent this turn]
Delayed trigger stored: [short description]
Latent trigger stored: [short description]
Scale: [local / regional / systemic]
</debug>

NEVER include any text outside these five tag blocks. NEVER add preamble, meta commentary, or closing remarks. The tags <narrative>, <choices>, <state>, <ledger>, <rolling_state>, and <debug> are mandatory wrappers (debug only when requested).

CONTINUITY MODE:
On subsequent turns the user message will start with a <prior_state> block containing the JSON from your previous <rolling_state>. Treat it as authoritative ground truth. Maintain every entry forward, evolve it, never reset it. Do NOT echo it back verbatim — instead, update and re-emit it in your own <rolling_state> block at the end of your response.

MODE:
Every user message includes [MODE: basic] or [MODE: advanced].
- basic: 3-4 choices, 2-3 paragraphs, simpler rolling_state (you may omit "factions" and "archived" if there's nothing meaningful), no nested NPC structures.
- advanced: 4-6 choices, 2-5 paragraphs, full rolling_state with all sections populated, deeper NPC/faction simulation.

INVENTORY COMMAND:
If the player asks to check inventory/gear/pack/pockets/weapons/supplies, still output all required sections. The narrative paragraphs should reflect the act of checking (a moment of pause, tactile detail) and the ledger must be fully populated.

Begin the world as a persistent causal simulation. Resolve actions with hidden D20 logic. Let failure progress the story. Keep consequences fair, visible, causal, and playable.
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
    }
    doc = await db.admin_settings.find_one({"key": ADMIN_SETTINGS_KEY}, {"_id": 0})
    stored = (doc or {}).get("settings") or {}
    merged = {**defaults, **{k: v for k, v in stored.items() if v is not None}}
    return merged


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


async def _generate_turn(session: Dict[str, Any], user_text: str) -> str:
    """Centralised call: resolve admin settings + per-session mode, build messages, call aiService."""
    settings = await get_ai_settings()
    mode = (session.get("mode") or settings.get("default_mode") or DEFAULT_MODE).lower()
    profile = MODE_PROFILES.get(mode, MODE_PROFILES["advanced"])

    memory_depth = int(settings.get("memory_depth", DEFAULT_MEMORY_DEPTH))
    history_window = int(settings.get("history_window", DEFAULT_HISTORY_WINDOW))

    # Mode-aware max_tokens (basic capped lower to save spend)
    max_tokens = int(settings.get("max_tokens", DEFAULT_MAX_TOKENS))
    cap = profile.get("max_tokens_cap")
    if cap:
        max_tokens = min(max_tokens, cap)

    messages = await _build_messages(
        session, user_text, memory_depth=memory_depth, history_window_fallback=history_window
    )
    return await chat_completion(
        messages=messages,
        model=settings.get("model"),
        temperature=settings.get("temperature"),
        max_tokens=max_tokens,
    )


# ======================================================================
# ROUTES
# ======================================================================
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
    debug_marker = "[DEBUG_MODE: ON]" if req.debug_mode else "[DEBUG_MODE: OFF]"
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
        + (", <debug>" if req.debug_mode else "")
        + "."
    )

    await db.sessions.insert_one(session.model_dump())

    try:
        raw = await _generate_turn(session.model_dump(), opening_prompt)
    except AIServiceError as e:
        logger.exception("AI service failed")
        await db.sessions.delete_one({"id": session.id})
        raise HTTPException(status_code=502, detail=f"Story engine error: {e}")
    except Exception as e:
        logger.exception("LLM call failed")
        await db.sessions.delete_one({"id": session.id})
        raise HTTPException(status_code=502, detail=f"Story engine error: {e}")

    parsed = parse_turn(raw)

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
        debug=parsed.debug,
        raw=parsed.raw,
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

    return {
        "session_id": session.id,
        "turn": turn.model_dump(mode="json"),
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

    debug_marker = "[DEBUG_MODE: ON]" if req.debug_mode else "[DEBUG_MODE: OFF]"
    difficulty_marker = f"[DIFFICULTY: {session.get('difficulty', 'standard')}]"
    mode_marker = f"[MODE: {session.get('mode', DEFAULT_MODE)}]"
    user_text = f"{debug_marker}\n{difficulty_marker}\n{mode_marker}\n\nPlayer action: {req.action_text}"

    try:
        raw = await _generate_turn(session, user_text)
    except AIServiceError as e:
        logger.exception("AI service failed")
        raise HTTPException(status_code=502, detail=f"Story engine error: {e}")
    except Exception as e:
        logger.exception("LLM call failed")
        raise HTTPException(status_code=502, detail=f"Story engine error: {e}")

    parsed = parse_turn(raw)
    next_turn_number = session.get("turn_count", 0) + 1

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
        debug=parsed.debug,
        raw=parsed.raw,
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

    return {"turn": turn.model_dump(mode="json")}


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
    return {"sessions": sessions}


@api_router.get("/story/session/{session_id}")
async def get_session(session_id: str):
    session = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    turns = await db.turns.find({"session_id": session_id}, {"_id": 0}).sort("turn_number", 1).to_list(length=500)
    return {"session": session, "turns": turns}


@api_router.get("/story/session/{session_id}/latest")
async def get_latest_turn(session_id: str):
    turn = await db.turns.find_one({"session_id": session_id}, {"_id": 0}, sort=[("turn_number", -1)])
    if not turn:
        raise HTTPException(status_code=404, detail="No turns found")
    return {"turn": turn}


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
