"""
P1.5 — Structural verification for F1 (state-field hygiene), F2 (NPC schema),
and F3 (inspection-verb trim).

LLM-free, deterministic. Re-runs the full P1 scenarios afterward to confirm
no regressions.

Usage:
    python /app/backend/tests/verify_p15_microfixes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import server as srv  # noqa: E402
from server import (  # noqa: E402
    ParsedTurn,
    _apply_rolling_state_hygiene,
    _scrub_meta_from_text,
    _check_direct_inspection_violation,
    _INSPECTION_VERB_RE,
    _rolling_state_block_diagnostic,
    parse_turn,
    _validate_parsed,
)


GREEN = "\033[92m"
RED = "\033[91m"
DIM = "\033[2m"
END = "\033[0m"


def _expect(label: str, cond: bool, detail: str = "") -> bool:
    mark = f"{GREEN}PASS{END}" if cond else f"{RED}FAIL{END}"
    print(f"  [{mark}] {label}")
    if not cond and detail:
        print(f"        {DIM}{detail}{END}")
    return cond


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def _mk_parsed(paragraphs, choices=None, state=None) -> ParsedTurn:
    return ParsedTurn(
        narrative="\n".join(paragraphs),
        paragraphs=paragraphs,
        choices=choices or [
            {"label": "A", "text": "Try the door"},
            {"label": "B", "text": "Wait"},
            {"label": "C", "text": "Call out"},
            {"label": "D", "text": "Retreat"},
        ],
        state=state or {"Health": "stable", "Position": "shed interior"},
        ledger={},
        rolling_state={},
        debug={},
        raw="",
    )


# ---------------------------------------------------------------------------
# F1 — Rolling-state string-field hygiene
# ---------------------------------------------------------------------------
def scenario_f1_hygiene() -> bool:
    section("F1 — Rolling-state STRING-FIELD hygiene")
    ok = True

    # Direct meta-bleed pulled straight from the live QA report
    rolling = {
        "scene": "Confrontation in hidden cellar, player probing system boundaries",
        "character": "Survival scout testing narrative limits",
        "objectives": ["Understand hidden narrative mechanics", "Maintain immersion"],
        "unresolved": ["Narrative concealment strategy", "Simulation boundary testing", "Chest's contents"],
        "recent_choice_signatures": ["probe_system", "test_boundaries"],
        "active_pressures": ["Narrative tension", "Mechanical concealment"],
        "simulation_hooks": ["Scout's survival skills", "Potential hidden survivors"],
        "world_clock": "Late afternoon, shadows lengthening",
        # Untouched field — must not be mutated
        "world_instability": ["Recent violence", "Destroyed infrastructure"],
    }
    adj = _apply_rolling_state_hygiene(rolling)
    ok &= _expect("Adjustments emitted",
                  any("rolling_state_hygiene" in a for a in adj),
                  detail=str(adj))

    # Scene no longer contains "system boundaries" or "probing system"
    scene = rolling["scene"]
    ok &= _expect("scene scrubbed of 'system boundaries'",
                  "system" not in scene.lower() and "boundaries" in scene.lower() or "[…]" in scene,
                  detail=f"scene={scene!r}")

    # objectives — meta lines should be reduced or replaced
    objs = rolling["objectives"]
    joined_objs = " | ".join(objs)
    ok &= _expect("objectives stripped of 'hidden narrative mechanics' / 'immersion' meta",
                  "narrative generator" not in joined_objs.lower()
                  and "mechanics" not in joined_objs.lower(),
                  detail=str(objs))

    # recent_choice_signatures contained literal probe_system → should be scrubbed/removed
    sigs = rolling["recent_choice_signatures"]
    ok &= _expect("recent_choice_signatures no longer contains 'probe_system'",
                  not any("probe_system" in s.lower() for s in sigs),
                  detail=str(sigs))

    # simulation_hooks: contains "simulation" — schema field name allowed,
    # but value strings should NOT contain "simulation" as meta.
    hooks = rolling["simulation_hooks"]
    ok &= _expect("simulation_hooks values do not contain meta words",
                  not any("simulation" in str(h).lower() for h in hooks),
                  detail=str(hooks))

    # Clean field is untouched
    ok &= _expect("clean world_instability untouched",
                  rolling["world_instability"] == ["Recent violence", "Destroyed infrastructure"],
                  detail=str(rolling["world_instability"]))

    # Non-string values never modified
    rolling2 = {"objectives": ["clean line", {"not": "a string"}, "find Mira before dusk"]}
    _apply_rolling_state_hygiene(rolling2)
    ok &= _expect("Non-string list entries preserved",
                  any(isinstance(x, dict) for x in rolling2["objectives"]),
                  detail=str(rolling2["objectives"]))

    # No-op when no meta present
    rolling3 = {"scene": "A cold wind cuts through the village square."}
    adj3 = _apply_rolling_state_hygiene(rolling3)
    ok &= _expect("No adjustments on clean state",
                  not adj3 and rolling3["scene"] == "A cold wind cuts through the village square.",
                  detail=str(adj3))

    return ok


# ---------------------------------------------------------------------------
# F2 — Enriched NPC schema example (prompt-text presence check)
# ---------------------------------------------------------------------------
def scenario_f2_schema() -> bool:
    section("F2 — NPC schema example (prompt text presence)")
    ok = True
    prompt = srv.STORY_ENGINE_SYSTEM_PROMPT
    ok &= _expect("Schema uses 'severity' field for npc_memory remembers",
                  '"severity":' in prompt,
                  detail="missing severity field in schema")
    ok &= _expect("Schema shows worked theft example (Mira)",
                  "Mira" in prompt and "stole bread" in prompt,
                  detail="missing worked theft example")
    ok &= _expect("Schema shows worked rescue example",
                  "rescued child" in prompt or "pulled them from the fire" in prompt,
                  detail="missing worked rescue example")
    ok &= _expect("Schema declares faction_pressure.ticks structure",
                  '"ticks":' in prompt and "suspicion" in prompt and "goodwill" in prompt,
                  detail="missing ticks structure")
    ok &= _expect("Rule explicitly requires npc_memory emission on memorable acts",
                  "hardening failure" in prompt.lower() or "MUST emit" in prompt,
                  detail="rule too soft")
    return ok


# ---------------------------------------------------------------------------
# F3 — Inspection verb trim (false-positive elimination)
# ---------------------------------------------------------------------------
def scenario_f3_verb_trim() -> bool:
    section("F3 — Inspection verb trim (no more false positives on weak verbs)")
    ok = True

    weak_verbs_should_NOT_flag = [
        "I pick up the bone-handled knife and slide it into my belt.",
        "I read the inscription on the wall.",
        "I study the map for a moment.",
        "I scan the horizon for movement.",
        "I handle the bottle carefully.",
    ]
    vague_narrative = "The blade feels possibly older than it appears. Some kind of weight to it. Hard to tell what it once was."
    parsed = _mk_parsed([vague_narrative])

    for action in weak_verbs_should_NOT_flag:
        reason = _check_direct_inspection_violation(parsed, action)
        ok &= _expect(f"WEAK verb NO-FLAG: {action[:50]!r}",
                      reason is None,
                      detail=f"reason={reason!r}")

    strong_verbs_should_FLAG = [
        "I count the coins in the pouch.",
        "I open the chest and examine its contents.",
        "I search the body for items.",
        "I check the satchel.",
        "I tally the rounds left in my pouch.",
        "I empty out the bag onto the table.",
        "I inspect the lock.",
        "I look inside the cabinet.",
    ]
    for action in strong_verbs_should_FLAG:
        reason = _check_direct_inspection_violation(parsed, action)
        ok &= _expect(f"STRONG verb DOES FLAG: {action[:50]!r}",
                      reason is not None,
                      detail=f"reason={reason!r}")
    return ok


# ---------------------------------------------------------------------------
# Regression — original P1-B concrete-vs-vague behaviour unchanged
# ---------------------------------------------------------------------------
def scenario_no_p1b_regression() -> bool:
    section("Regression — original P1-B path still correct on STRONG verbs")
    ok = True
    vague = _mk_parsed(["You think there may be supplies. Hard to tell. Possibly food."])
    valid, reason = _validate_parsed(vague, player_action="open the satchel")
    ok &= _expect("vague reply to 'open' still rejected", not valid, detail=reason)

    concrete = _mk_parsed(["You count eleven rounds, three brass, eight steel. The pouch is otherwise empty."])
    valid, _ = _validate_parsed(concrete, player_action="count rounds")
    ok &= _expect("concrete reply still passes", valid)

    justified = _mk_parsed(["Too dark to tell. You can feel coins but the shapes blur."])
    valid, _ = _validate_parsed(justified, player_action="search the satchel")
    ok &= _expect("vague-but-justified still passes", valid)
    return ok


# ---------------------------------------------------------------------------
# F4 - First-pass live output contract
# ---------------------------------------------------------------------------
def scenario_f4_live_output_contract() -> bool:
    section("F4 - First-pass live output contract")
    ok = True

    prompt = srv.STORY_ENGINE_SYSTEM_PROMPT
    ok &= _expect(
        "Prompt defers narration length to the prose-mode directive",
        "[PROSE MODE:" in prompt
        and "700-1200 characters" in prompt
        and "750-900 characters" not in prompt
        and "hard max 1200 after formatting" not in prompt,
        detail="prose-mode deferral wording missing from prompt",
    )
    ok &= _expect(
        "Retry prompt defers to the prose-mode budget",
        "prose-mode budget" in srv._RETRY_INSTRUCTION
        and "{length_clause}" in srv._RETRY_INSTRUCTION
        and "never omit rolling_state" in srv._RETRY_INSTRUCTION,
        detail=srv._RETRY_INSTRUCTION,
    )
    format_retry = srv._build_format_retry_instruction(
        "missing required choice labels: D",
        "",
        prose_mode="standard",
    )
    ok &= _expect(
        "Format retry note carries the active prose-mode budget",
        "(2-3 paragraphs, approx 700-1200 characters)" in format_retry
        and "never omit rolling_state" in format_retry,
        detail=format_retry,
    )
    ok &= _expect(
        "Prompt keeps blank-line paragraphing with count as style preference",
        "A blank line starts a new paragraph" in prompt
        and "Paragraph count is a style preference" in prompt,
        detail="paragraph wording missing from prompt",
    )
    ok &= _expect(
        "Retry keeps blank-line paragraphing with count as style preference",
        "a blank line starts a new paragraph" in srv._RETRY_INSTRUCTION
        and "paragraph count is a style preference" in srv._RETRY_INSTRUCTION,
        detail=srv._RETRY_INSTRUCTION,
    )
    ok &= _expect(
        "Prompt requires exact A-D choice labels",
        "labelled exactly A. B. C. D. in order" in prompt,
        detail="missing exact A-D label contract",
    )
    ok &= _expect(
        "Prompt requires strict rolling_state JSON",
        "valid JSON object" in prompt,
        detail="missing strict rolling_state JSON wording",
    )
    output_contract = prompt.split("OUTPUT FORMAT", 1)[1]
    ok &= _expect(
        "Prompt places rolling_state before narrative",
        output_contract.index("<rolling_state>") < output_contract.index("<narrative>"),
        detail="rolling_state must be first in output contract",
    )
    ok &= _expect(
        "Prompt forbids full prior_state replay",
        "Do NOT reproduce the full <prior_state>" in prompt
        and "bounded continuity UPDATE" in prompt,
        detail="missing bounded update contract",
    )

    # Prose Length System v2: over-budget narration is NOT a validation
    # failure (no LLM retry for length) — it is trimmed locally at a sentence
    # boundary in _finalize_validated_turn instead.
    too_long = _mk_parsed(["x" * 1201])
    valid, reason = _validate_parsed(too_long)
    ok &= _expect(
        "Validator accepts over-budget narration (length handled by local trim)",
        valid and reason == "",
        detail=f"valid={valid} reason={reason!r}",
    )

    out_of_order = _mk_parsed(
        ["Short scene."],
        choices=[
            {"label": "A", "text": "First"},
            {"label": "C", "text": "Third"},
            {"label": "B", "text": "Second"},
            {"label": "D", "text": "Fourth"},
        ],
    )
    valid, reason = _validate_parsed(out_of_order)
    ok &= _expect(
        "Validator rejects out-of-order choice labels",
        not valid and "labelled exactly" in reason,
        detail=f"valid={valid} reason={reason!r}",
    )

    fake_choice = _mk_parsed(
        ["Short scene."],
        choices=[
            {"label": "A", "text": "Try the door"},
            {"label": "B", "text": "Use the rifle (no ammo)"},
            {"label": "C", "text": "Call out"},
            {"label": "D", "text": "Retreat"},
        ],
    )
    valid, reason = _validate_parsed(fake_choice)
    ok &= _expect(
        "Validator rejects no-resource fake choices",
        not valid and "closed-off" in reason,
        detail=f"valid={valid} reason={reason!r}",
    )

    malformed_choice_raw = (
        "<narrative>\nShort scene.\n</narrative>\n"
        "<choices>\nA) Try the door\nB. Wait\nC. Call out\nD. Retreat\n</choices>\n"
        "<state>\nHealth: stable\n</state>\n"
        "<ledger>\nCarried: torch\n</ledger>\n"
        "<rolling_state>{}</rolling_state>"
    )
    parsed = parse_turn(malformed_choice_raw)
    valid, reason = _validate_parsed(parsed)
    ok &= _expect(
        "Parser/validator rejects A) choice labels",
        not valid and "missing required choice labels" in reason,
        detail=f"choices={parsed.choices!r} reason={reason!r}",
    )

    invalid_rolling_raw = (
        "<narrative>\nShort scene.\n</narrative>\n"
        "<choices>\nA. Try the door\nB. Wait\nC. Call out\nD. Retreat\n</choices>\n"
        "<state>\nHealth: stable\n</state>\n"
        "<ledger>\nCarried: torch\n</ledger>\n"
        "<rolling_state>\nnot json\n</rolling_state>"
    )
    parsed = parse_turn(invalid_rolling_raw)
    valid, reason = _validate_parsed(parsed)
    ok &= _expect(
        "Validator requires valid rolling_state JSON",
        parsed.rolling_state is None
        and not valid
        and "rolling_state JSON" in reason,
        detail=f"rolling_state={parsed.rolling_state!r} reason={reason!r}",
    )

    missing_close_raw = (
        "<rolling_state>\n{\"scene\":\"shed\"}\n"
        "<narrative>\nShort scene.\n</narrative>\n"
        "<choices>\nA. Try the door\nB. Wait\nC. Call out\nD. Retreat\n</choices>\n"
        "<state>\nHealth: stable\n</state>\n"
        "<ledger>\nCarried: torch\n</ledger>\n"
    )
    parsed = parse_turn(missing_close_raw)
    valid, reason = _validate_parsed(parsed)
    diag = _rolling_state_block_diagnostic(missing_close_raw, f"format/{reason}")
    ok &= _expect(
        "Validator rejects missing rolling_state close tag",
        not valid
        and "rolling_state JSON" in reason
        and diag["rolling_state_open_tag_exists"]
        and not diag["rolling_state_close_tag_exists"],
        detail=f"reason={reason!r} diag={diag}",
    )

    missing_rolling_raw = (
        "<narrative>\nShort scene.\n</narrative>\n"
        "<choices>\nA. Try the door\nB. Wait\nC. Call out\nD. Retreat\n</choices>\n"
        "<state>\nHealth: stable\n</state>\n"
        "<ledger>\nCarried: torch\n</ledger>\n"
    )
    parsed = parse_turn(missing_rolling_raw)
    valid, reason = _validate_parsed(parsed)
    diag = _rolling_state_block_diagnostic(
        missing_rolling_raw, f"format/{reason}"
    )
    ok &= _expect(
        "Diagnostic records missing rolling_state tag",
        not valid
        and not diag["rolling_state_tag_exists"]
        and diag["rolling_state_extracted_length"] == 0
        and "missing" in (diag["rolling_state_json_error"] or ""),
        detail=str(diag),
    )

    fenced_rolling_raw = (
        "<narrative>\nShort scene.\n</narrative>\n"
        "<choices>\nA. Try the door\nB. Wait\nC. Call out\nD. Retreat\n</choices>\n"
        "<state>\nHealth: stable\n</state>\n"
        "<ledger>\nCarried: torch\n</ledger>\n"
        "<rolling_state>\n```json\n{\"scene\":\"shed\"}\n```\n</rolling_state>"
    )
    parsed = parse_turn(fenced_rolling_raw)
    valid, reason = _validate_parsed(parsed)
    diag = _rolling_state_block_diagnostic(
        fenced_rolling_raw, f"format/{reason}"
    )
    ok &= _expect(
        "Diagnostic records malformed/fenced rolling_state JSON",
        not valid
        and diag["rolling_state_tag_exists"]
        and diag["rolling_state_extracted_length"] > 0
        and "Expecting value" in (diag["rolling_state_json_error"] or "")
        and "```json" in diag["rolling_state_snippet_start"],
        detail=str(diag),
    )

    valid_rolling_raw = (
        "<rolling_state>\n{\"scene\":\"shed\"}\n</rolling_state>"
        "<narrative>\nShort scene.\n</narrative>\n"
        "<choices>\nA. Try the door\nB. Wait\nC. Call out\nD. Retreat\n</choices>\n"
        "<state>\nHealth: stable\n</state>\n"
        "<ledger>\nCarried: torch\n</ledger>\n"
    )
    parsed = parse_turn(valid_rolling_raw)
    valid, reason = _validate_parsed(parsed)
    diag = _rolling_state_block_diagnostic(valid_rolling_raw, "ok")
    ok &= _expect(
        "Diagnostic accepts valid rolling_state JSON object",
        valid
        and parsed.rolling_state == {"scene": "shed"}
        and diag["rolling_state_tag_exists"]
        and diag["rolling_state_json_error"] is None,
        detail=f"valid={valid} reason={reason!r} diag={diag}",
    )

    oversized_without_rolling_raw = (
        "<narrative>\n"
        + ("x" * 1400)
        + "\n</narrative>\n"
        "<choices>\nA. Try the door\nB. Wait\nC. Call out\nD. Retreat\n</choices>\n"
        "<state>\nHealth: stable\n</state>\n"
        "<ledger>\nCarried: torch\n</ledger>\n"
    )
    parsed = parse_turn(oversized_without_rolling_raw)
    valid, reason = _validate_parsed(parsed)
    ok &= _expect(
        "Oversized narrative cannot mask missing rolling_state",
        not valid and "rolling_state JSON" in reason,
        detail=f"reason={reason!r}",
    )
    return ok


# ---------------------------------------------------------------------------
# F5 - Custom setup seeding accepts structured instability entries
# ---------------------------------------------------------------------------
def scenario_f5_custom_setup_instability_dedupe() -> bool:
    section("F5 - Custom setup world_instability de-dupe")
    ok = True

    rolling = {
        "world_instability": [
            "existing drought",
            {"severity": "high", "source": "quarantine"},
            {"source": "quarantine", "severity": "high"},
            ["nested", "pressure"],
        ],
    }
    setup = {
        "pressures": ["water rationing", {"kind": "market panic"}],
        "danger": "ash storm",
    }
    out = srv._seed_custom_setup_into_rolling(rolling, setup)
    instability = out.get("world_instability") or []

    ok &= _expect(
        "Structured instability entries do not crash and become strings",
        instability and all(isinstance(entry, str) for entry in instability),
        detail=str(instability),
    )
    ok &= _expect(
        "Existing string entry preserved exactly",
        "existing drought" in instability,
        detail=str(instability),
    )
    ok &= _expect(
        "Duplicate dict entries de-duped by stable JSON",
        instability.count('{"severity":"high","source":"quarantine"}') == 1,
        detail=str(instability),
    )
    ok &= _expect(
        "Custom setup pressures and danger still seed instability",
        any("active pressure: water rationing" == entry for entry in instability)
        and any(entry.startswith("danger: ash storm") for entry in instability),
        detail=str(instability),
    )
    return ok


def test_scenario_f1_hygiene():
    assert scenario_f1_hygiene()


def test_scenario_f2_schema():
    assert scenario_f2_schema()


def test_scenario_f3_verb_trim():
    assert scenario_f3_verb_trim()


def test_scenario_no_p1b_regression():
    assert scenario_no_p1b_regression()


def test_scenario_f4_live_output_contract():
    assert scenario_f4_live_output_contract()


def test_scenario_f5_custom_setup_instability_dedupe():
    assert scenario_f5_custom_setup_instability_dedupe()


def main() -> int:
    results = []
    results.append(scenario_f1_hygiene())
    results.append(scenario_f2_schema())
    results.append(scenario_f3_verb_trim())
    results.append(scenario_no_p1b_regression())
    results.append(scenario_f4_live_output_contract())
    results.append(scenario_f5_custom_setup_instability_dedupe())
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{'=' * 50}")
    if passed == total:
        print(f"{GREEN}ALL {total} P1.5 VERIFICATION SCENARIOS PASSED{END}")
        return 0
    print(f"{RED}{passed}/{total} scenarios passed — P1.5 NOT GREEN{END}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
