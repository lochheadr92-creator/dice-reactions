from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
import logging
import uuid
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

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
PARAGRAPH PRESERVATION RULE
============================
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

NEVER include any text outside these four tag blocks. NEVER add preamble, meta commentary, or closing remarks. The tags <narrative>, <choices>, <state>, <ledger>, and <debug> are mandatory wrappers.

INVENTORY COMMAND:
If the player asks to check inventory/gear/pack/pockets/weapons/supplies, still output all four sections. The narrative paragraphs should reflect the act of checking (a moment of pause, tactile detail) and the ledger must be fully populated.

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
    debug: Optional[Dict[str, str]] = None
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SessionSummary(BaseModel):
    id: str
    genre: str
    role: Optional[str]
    difficulty: str
    title: str
    turn_count: int
    last_narrative_snippet: str
    last_state: Dict[str, str]
    created_at: datetime
    updated_at: datetime

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
    debug_block = _extract_block(raw, "debug")

    # Fallback: if no tagged blocks, treat whole text as narrative
    if not narrative and not choices_block and not state_block:
        narrative = raw

    paragraphs = _parse_paragraphs(narrative)
    choices = _parse_choices(choices_block)
    state = _parse_kv_block(state_block)
    ledger = _parse_ledger(ledger_block)
    debug = _parse_kv_block(debug_block) if debug_block else None

    return ParsedTurn(
        narrative=narrative,
        paragraphs=paragraphs,
        choices=choices,
        state=state,
        ledger=ledger,
        debug=debug,
        raw=raw,
    )

# ======================================================================
# LLM WRAPPER
# ======================================================================
async def _call_claude_with_history(session_id: str, user_text: str) -> str:
    """Create a fresh LlmChat per call, replaying history as a single context block before the new action."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="EMERGENT_LLM_KEY is not configured")

    # Fetch only the most recent N turns for context to avoid unbounded growth.
    HISTORY_LIMIT = 30
    recent_desc = await db.turns.find(
        {"session_id": session_id}, {"_id": 0}
    ).sort("turn_number", -1).to_list(length=HISTORY_LIMIT)
    prior_turns = list(reversed(recent_desc))

    # Build a compact recap of history so continuity survives across stateless chat instances.
    history_lines = []
    for t in prior_turns:
        pa = t.get("player_action")
        if pa:
            history_lines.append(f"[Player]: {pa}")
        # Include prior narrative + state so Claude can continue consistently
        if t.get("narrative"):
            history_lines.append(f"[Engine last narrative]: {t['narrative'][:1200]}")
        if t.get("state"):
            state_str = "; ".join(f"{k}: {v}" for k, v in t["state"].items())
            history_lines.append(f"[Engine last state]: {state_str}")
        if t.get("ledger"):
            ledger_str = "; ".join(f"{k}: {v}" for k, v in t["ledger"].items() if v)
            history_lines.append(f"[Engine last ledger]: {ledger_str}")

    history_block = "\n".join(history_lines)

    composed = (
        (f"=== PRIOR SESSION CONTEXT (continuity reference — do NOT repeat narrative) ===\n{history_block}\n\n=== END PRIOR CONTEXT ===\n\n"
         if history_block else "")
        + user_text
    )

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=STORY_ENGINE_SYSTEM_PROMPT,
    ).with_model("anthropic", CLAUDE_MODEL)

    response = await chat.send_message(UserMessage(text=composed))
    return response

# ======================================================================
# ROUTES
# ======================================================================
@api_router.get("/")
async def root():
    return {"message": "Dice Reaction Story Engine v3.3"}

@api_router.get("/health")
async def health():
    return {"status": "ok", "llm_configured": bool(EMERGENT_LLM_KEY), "model": CLAUDE_MODEL}


@api_router.post("/story/new")
async def new_story(req: NewStoryRequest):
    session = SessionRecord(
        device_id=req.device_id,
        genre=req.genre,
        role=req.role,
        tone=req.tone,
        difficulty=req.difficulty,
        debug_mode=req.debug_mode,
        custom_premise=req.custom_premise,
        title=f"{req.genre.title()} — {(req.role or 'Wanderer').title()}",
    )

    setup_lines = [
        f"Genre: {req.genre}",
        f"Character role: {req.role or 'unspecified — choose a fitting archetype for the genre'}",
        f"Tone: {req.tone or 'cinematic and grounded'}",
        f"Difficulty: {req.difficulty}",
    ]
    if req.custom_premise:
        setup_lines.append(f"Premise hook: {req.custom_premise}")

    setup_text = "\n".join(setup_lines)
    debug_marker = "[DEBUG_MODE: ON]" if req.debug_mode else "[DEBUG_MODE: OFF]"

    opening_prompt = (
        f"{debug_marker}\n\n"
        f"Begin the story now. Use the following setup:\n{setup_text}\n\n"
        f"Open with an immersive in-medias-res scene that establishes location, sensory atmosphere, the character's immediate situation, and one active pressure or hook. "
        f"Populate the inventory ledger with a small, plausible starting kit fitting the genre and role. "
        f"Present 4-6 meaningful first choices. "
        f"Remember: output ONLY the four required tag blocks (<narrative>, <choices>, <state>, <ledger>"
        + (", <debug>" if req.debug_mode else "")
        + ")."
    )

    await db.sessions.insert_one(session.model_dump())

    try:
        raw = await _call_claude_with_history(session.id, opening_prompt)
    except Exception as e:
        logger.exception("LLM call failed")
        await db.sessions.delete_one({"id": session.id})
        raise HTTPException(status_code=502, detail=f"Story engine error: {str(e)}")

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
        debug=parsed.debug,
    )
    await db.turns.insert_one(turn.model_dump())

    snippet = (parsed.paragraphs[0][:180] + "…") if parsed.paragraphs else ""
    await db.sessions.update_one(
        {"id": session.id},
        {"$set": {
            "turn_count": 1,
            "last_narrative_snippet": snippet,
            "last_state": parsed.state,
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
        },
    }


@api_router.post("/story/action")
async def story_action(req: ActionRequest):
    session = await db.sessions.find_one({"id": req.session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    debug_marker = "[DEBUG_MODE: ON]" if req.debug_mode else "[DEBUG_MODE: OFF]"
    user_text = f"{debug_marker}\n\nPlayer action: {req.action_text}"

    try:
        raw = await _call_claude_with_history(req.session_id, user_text)
    except Exception as e:
        logger.exception("LLM call failed")
        raise HTTPException(status_code=502, detail=f"Story engine error: {str(e)}")

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
        debug=parsed.debug,
    )
    await db.turns.insert_one(turn.model_dump())

    snippet = (parsed.paragraphs[0][:180] + "…") if parsed.paragraphs else ""
    await db.sessions.update_one(
        {"id": req.session_id},
        {"$set": {
            "turn_count": next_turn_number,
            "last_narrative_snippet": snippet,
            "last_state": parsed.state,
            "updated_at": datetime.now(timezone.utc),
            "debug_mode": req.debug_mode,
        }},
    )

    return {"turn": turn.model_dump(mode="json")}


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
