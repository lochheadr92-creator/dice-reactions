"""
NPC death/exit structured-marker prompt directive (Stage 3 — model-compliance
pressure, Ch 31 extension).

Static source analysis only — mirrors ``test_prompt_fingerprint.py``: reads
``backend/server.py`` as text rather than importing ``server`` (which pulls in
FastAPI/Motor), so this guard collects and runs in any environment.

Contract under test:
  1. The system prompt instructs the model that narrating an NPC death, exit,
     departure, disappearance, or removal must be accompanied by a matching
     STRUCTURED marker on that NPC's `rolling_state.npcs` row this same turn.
  2. The directive explicitly states prose alone is never authoritative — it
     must not weaken or contradict the gateway's authorisation rule.
  3. The directive's vocabulary (`alive`, `stance`, `status`, `absent`, and the
     death/exit marker words) stays in lockstep with the actual keyword sets
     `gateway._NPC_DEAD_MARKERS` / `gateway._NPC_EXIT_MARKERS` enforce, so the
     prompt cannot silently drift from the contract that decides authority.
  4. The directive lives in the developer-facing `rolling_state` contract, not
     inside `<debug>` — it must apply on every turn, not only when
     `[DEV_MODE: ON]` is present.
"""

import os
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

import gateway  # noqa: E402 — single-sourced death/exit marker contract

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SERVER_PY = os.path.join(REPO, "backend", "server.py")

_PROMPT_START_RE = re.compile(r'STORY_ENGINE_SYSTEM_PROMPT\s*=\s*"""')


def _server_source() -> str:
    with open(SERVER_PY, encoding="utf-8") as fh:
        return fh.read()


def _system_prompt_text(src: str) -> str:
    start = _PROMPT_START_RE.search(src)
    assert start, "STORY_ENGINE_SYSTEM_PROMPT definition not found in server.py"
    end = src.find('"""', start.end())
    assert end != -1, "STORY_ENGINE_SYSTEM_PROMPT closing triple-quote not found"
    return src[start.end():end]


def test_directive_present_in_system_prompt():
    """The structured-marker directive exists and covers death/exit/departure phrasing."""
    prompt = _system_prompt_text(_server_source())

    assert "NPC DEATH / EXIT STRUCTURED MARKER RULE" in prompt, (
        "NPC death/exit structured-marker directive missing from system prompt"
    )

    # Must cover the full expected-behaviour vocabulary from the task:
    # dies, exits, leaves, disappears, is removed, is no longer present.
    for phrase in ("dies", "leaves the scene", "exits", "disappears", "is removed", "is no longer present"):
        assert phrase in prompt, f"directive missing narrated-departure phrase: {phrase!r}"

    # Must name the concrete structured fields the gateway actually checks.
    for field in ('"alive"', '"stance"', '"status"', '"absent"'):
        assert field in prompt, f"directive missing structured field reference: {field}"


def test_directive_does_not_weaken_gateway_authority():
    """The directive must assert prose is never authoritative — it can only pressure
    the model toward compliance, never grant prose the power to create canon."""
    prompt = _system_prompt_text(_server_source())
    idx = prompt.find("NPC DEATH / EXIT STRUCTURED MARKER RULE")
    assert idx != -1
    section = prompt[idx: idx + 900]

    assert "never authoritative" in section.lower() or "not authoritative" in section.lower(), (
        "directive must explicitly state prose alone is not authoritative"
    )
    # Explicitly forbidden framing: the directive must not claim narration
    # itself creates/confirms death or removes NPCs from state.
    forbidden = [
        "narrative confirms the death",
        "narration authorises",
        "prose creates",
        "prose is authoritative",
    ]
    lowered = section.lower()
    for bad in forbidden:
        assert bad not in lowered, f"directive must not grant prose authority via: {bad!r}"


def test_directive_vocabulary_matches_gateway_marker_contract():
    """Directive wording must not drift from gateway's single-sourced marker sets."""
    prompt = _system_prompt_text(_server_source())
    idx = prompt.find("NPC DEATH / EXIT STRUCTURED MARKER RULE")
    assert idx != -1
    section = prompt[idx: idx + 900].lower()

    # Death markers the gateway actually recognises (gateway._NPC_DEAD_MARKERS
    # plus "alive":false) — the directive must reference the death state.
    assert "dead" in section, "directive must reference the 'dead' structured marker"
    assert "alive" in section, "directive must reference the 'alive' field"

    # Exit markers — spot check a representative subset actually present in
    # gateway._NPC_EXIT_MARKERS so the two cannot silently diverge.
    exit_markers_referenced = [m for m in gateway._NPC_EXIT_MARKERS if m in section]
    assert exit_markers_referenced, (
        f"directive references none of gateway._NPC_EXIT_MARKERS={gateway._NPC_EXIT_MARKERS}"
    )
    assert "absent" in section  # gateway also treats absent=True as an exit marker


def test_directive_is_outside_debug_only_block():
    """The directive must sit in the always-emitted rolling_state contract, not the
    developer-only <debug> block, so it applies on every turn regardless of
    [DEV_MODE: ON]."""
    prompt = _system_prompt_text(_server_source())
    directive_idx = prompt.find("NPC DEATH / EXIT STRUCTURED MARKER RULE")
    # Locate the actual <debug> BLOCK definition in OUTPUT FORMAT (not the
    # earlier prose references that merely mention the tag by name).
    debug_block_idx = prompt.find("<debug>\n(ONLY include this block")
    assert directive_idx != -1
    assert debug_block_idx != -1, "<debug> block definition not found in OUTPUT FORMAT"
    assert directive_idx < debug_block_idx, (
        "directive must precede the <debug> block, not be nested inside it"
    )
