"""
P1 — Structural verification for immersion integrity + player trust patches.

LLM-free, deterministic. Validates:
  P1-A — Mechanic leak validator expansion (soft meta + disguised mechanics).
  P1-B — Direct inspection enforcement.
  P1-C — Room audit revisit reconciliation.
  P1-D — Bounded NPC memory + faction consequence tick.

Usage:
    python /app/backend/tests/verify_p1_immersion_integrity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from server import (  # noqa: E402
    ParsedTurn,
    _validate_parsed,
    _check_direct_inspection_violation,
    _apply_room_audit,
    _apply_npc_memory_bounds,
    _apply_faction_consequence_tick,
    _MECHANIC_WORD_RE,
    _SOFT_META_PHRASE_RE,
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


def _mk_parsed(
    paragraphs, choices=None, state=None, ledger=None, rolling_state=None
) -> ParsedTurn:
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
        ledger=ledger or {},
        rolling_state=rolling_state or {},
        debug={},
        raw="",
    )


# ---------------------------------------------------------------------------
# P1-A — Mechanic leak validator expansion
# ---------------------------------------------------------------------------
def scenario_leak_validator() -> bool:
    section("P1-A — Mechanic leak validator (soft meta + disguised mechanics)")
    ok = True

    # Should-block soft-meta phrasing
    blocked_phrases = [
        "The system carries you forward.",
        "This engine is harder than the last.",
        "Underlying mechanics shift somewhere out of sight.",
        "Internal logic resolves the moment.",
        "As an AI, I cannot describe further.",
        "My tokens are limited tonight.",
        "Meta commentary aside, the door creaks.",
        "The simulation hums.",
        "The parser noticed your move.",
    ]
    for phrase in blocked_phrases:
        parsed = _mk_parsed([phrase + " " + "Daylight bleeds through cracks." * 3])
        valid, reason = _validate_parsed(parsed)
        ok &= _expect(f"BLOCKED soft-meta: {phrase!r}",
                      not valid and "meta" in reason.lower() or "mechanic" in reason.lower(),
                      detail=f"valid={valid} reason={reason!r}")

    # Should-block disguised mechanic terms (P1-A additions)
    blocked_words = [
        "The runtime accepts your input.",
        "The state machine ticks once.",
        "Your narrative generator hesitates.",
        "AI reasoning is paused for a beat.",
        "JSON drifts in the back of your mind.",
        "The concealment mandate holds.",
    ]
    for phrase in blocked_words:
        parsed = _mk_parsed([phrase + " " + "Wind tugs the canvas." * 3])
        valid, reason = _validate_parsed(parsed)
        ok &= _expect(f"BLOCKED disguised mechanic: {phrase!r}",
                      not valid,
                      detail=f"valid={valid} reason={reason!r}")

    # Should-PASS normal narrative with valid in-world uses
    allowed = [
        "The steam engine clanks beneath the floor. Wind drives rain against the slats. You count five rounds left.",
        "Her immune system was already failing the last time you saw her. You count six. The medkit weighs nothing now.",
        "A ration token clinks against the bowl. You count two left. Outside, the dog falls quiet.",
    ]
    for phrase in allowed:
        parsed = _mk_parsed([phrase])
        valid, reason = _validate_parsed(parsed, player_action="count rounds")
        ok &= _expect(f"ALLOWED in-world: {phrase[:50]!r}",
                      valid,
                      detail=f"valid={valid} reason={reason!r}")
    return ok


# ---------------------------------------------------------------------------
# P1-B — Direct inspection enforcement
# ---------------------------------------------------------------------------
def scenario_direct_inspection() -> bool:
    section("P1-B — Direct inspection enforcement")
    ok = True

    vague_after_count = _mk_parsed([
        "You think there may be some kind of supplies inside.",
        "The amount is unclear. Hard to tell in this light." * 1,
    ])
    reason = _check_direct_inspection_violation(vague_after_count, "count rounds in the pouch")
    ok &= _expect("FLAGS vague reply when player counted",
                  reason is not None,
                  detail=f"reason={reason!r}")

    concrete_after_count = _mk_parsed([
        "You count eleven rounds, three brass, eight steel. The pouch is otherwise empty.",
    ])
    reason = _check_direct_inspection_violation(concrete_after_count, "count rounds in the pouch")
    ok &= _expect("PASSES concrete reply after counting",
                  reason is None,
                  detail=f"reason={reason!r}")

    # Vague but JUSTIFIED by darkness/distance — should NOT flag
    vague_justified = _mk_parsed([
        "Too dark to tell. You can feel weight in the satchel — coins, maybe — but the shapes blur.",
    ])
    reason = _check_direct_inspection_violation(vague_justified, "search the satchel")
    ok &= _expect("ALLOWS vague when darkness justifies",
                  reason is None,
                  detail=f"reason={reason!r}")

    # Player did NOT inspect — vague description allowed
    ambient_vague = _mk_parsed([
        "Something seems off about the shed. Hard to tell from here.",
    ])
    reason = _check_direct_inspection_violation(ambient_vague, "stand by the road")
    ok &= _expect("ALLOWS vague when player did not inspect",
                  reason is None,
                  detail=f"reason={reason!r}")

    # Full validator path
    parsed_bad = _mk_parsed([
        "You think there may be supplies. Hard to tell. Possibly food.",
    ])
    valid, reason = _validate_parsed(parsed_bad, player_action="open the satchel")
    ok &= _expect("Validator REJECTS vague reply to 'open the satchel'",
                  not valid,
                  detail=f"valid={valid} reason={reason!r}")
    return ok


# ---------------------------------------------------------------------------
# P1-C — Room audit revisit reconciliation
# ---------------------------------------------------------------------------
def scenario_room_audit() -> bool:
    section("P1-C — Room audit revisit reconciliation")
    ok = True

    # Turn 1: visit shed, two objects established here
    rolling = {
        "object_locations": [
            {"object": "old satchel", "status": "stored", "where": "shed corner"},
            {"object": "rusted key", "status": "stored", "where": "shed shelf"},
        ],
    }
    parsed1 = _mk_parsed(["..."], state={"Position": "shed corner, by the door"})
    adj1 = _apply_room_audit(parsed1, rolling)
    ok &= _expect("Turn 1 — no drift flag (room being seeded)", not adj1,
                  detail=str(adj1))
    rooms = rolling.get("known_rooms") or []
    ok &= _expect("Turn 1 — known_rooms seeded with current room",
                  any(r.get("key", "").startswith("shed") for r in rooms),
                  detail=str(rooms))

    # Turn 2: revisit shed, satchel silently missing AND not marked destroyed/taken
    rolling2 = {
        "object_locations": [
            {"object": "rusted key", "status": "stored", "where": "shed shelf"},
        ],
        "known_rooms": rooms,
    }
    parsed2 = _mk_parsed(["..."], state={"Position": "shed corner"})
    adj2 = _apply_room_audit(parsed2, rolling2)
    ok &= _expect("Turn 2 — drift flagged for vanished satchel",
                  any("room_audit_drift" in a and "satchel" in a for a in adj2),
                  detail=str(adj2))

    # Turn 3: revisit shed, satchel legitimately removed (status=taken)
    rolling3 = {
        "object_locations": [
            {"object": "old satchel", "status": "carried", "where": "on player"},
            {"object": "rusted key", "status": "stored", "where": "shed shelf"},
        ],
        "known_rooms": rooms,
    }
    parsed3 = _mk_parsed(["..."], state={"Position": "shed corner"})
    adj3 = _apply_room_audit(parsed3, rolling3)
    ok &= _expect("Turn 3 — no drift when satchel is now carried (legitimate move)",
                  not any("room_audit_drift" in a for a in adj3),
                  detail=str(adj3))
    return ok


# ---------------------------------------------------------------------------
# P1-D — Bounded NPC memory + faction consequence tick
# ---------------------------------------------------------------------------
def scenario_npc_memory_and_faction() -> bool:
    section("P1-D — Bounded NPC memory + faction consequence tick")
    ok = True

    # NPC with 10 minor memories + 2 major. Cap = 5. Major should survive.
    rolling = {
        "npc_memory": [
            {
                "name": "Greg",
                "remembers": [
                    {"event": "player nodded", "since_turn": 1},
                    {"event": "player asked the time", "since_turn": 2},
                    {"event": "player smiled", "since_turn": 3},
                    {"event": "player STOLE bread", "since_turn": 4},
                    {"event": "player said hello", "since_turn": 5},
                    {"event": "player BETRAYED him", "since_turn": 6},
                    {"event": "player walked past", "since_turn": 7},
                    {"event": "player muttered", "since_turn": 8},
                    {"event": "player coughed", "since_turn": 9},
                    {"event": "player sneezed", "since_turn": 10},
                    {"event": "player looked away", "since_turn": 11},
                    {"event": "player chewed gum", "since_turn": 12},
                ],
            }
        ],
        "faction_pressure": [
            {"name": "Town Guard", "movement": "patrolling", "player_reputation": "neutral"}
        ],
    }
    _apply_npc_memory_bounds(rolling, current_turn=14)
    greg = rolling["npc_memory"][0]
    ok &= _expect(f"NPC remembers capped at 5 (got {len(greg['remembers'])})",
                  len(greg["remembers"]) <= 5,
                  detail=str(greg["remembers"]))
    events_kept = [str(e.get("event", "")) for e in greg["remembers"]]
    ok &= _expect("Major theft event preserved",
                  any("STOLE" in e or "stole" in e.lower() for e in events_kept),
                  detail=str(events_kept))
    ok &= _expect("Major betrayal event preserved",
                  any("BETRAYED" in e or "betrayed" in e.lower() for e in events_kept),
                  detail=str(events_kept))

    # Faction tick — multiple theft/violence events should register
    rolling2 = {
        "npc_memory": [
            {"name": "Greg", "remembers": [
                {"event": "player stole bread"}, {"event": "player stole coins"},
                {"event": "player attacked Lin"},
            ]},
            {"name": "Mara", "remembers": [
                {"event": "player rescued the boy"}, {"event": "player saved the dog"},
            ]},
        ],
        "faction_pressure": [
            {"name": "Town Guard", "movement": "patrolling", "player_reputation": "neutral"}
        ],
    }
    adj = _apply_faction_consequence_tick(rolling2)
    ticks = (rolling2["faction_pressure"][0] or {}).get("ticks") or {}
    ok &= _expect("Faction tick registered for suspicion (theft repeats)",
                  ticks.get("suspicion", 0) >= 1,
                  detail=str(ticks))
    ok &= _expect("Faction tick registered for goodwill (rescues)",
                  ticks.get("goodwill", 0) >= 1,
                  detail=str(ticks))
    ok &= _expect("Single-occurrence theme NOT triggered (below threshold)",
                  ticks.get("guard_attention", 0) == 0,
                  detail=f"adjustments={adj} ticks={ticks}")

    # Minor decay: a minor entry older than 12 turns should be dropped
    rolling3 = {
        "npc_memory": [
            {"name": "Eli", "remembers": [
                {"event": "player smiled", "severity": "minor", "since_turn": 1},
                {"event": "player paid debt",  "severity": "major", "since_turn": 1},
            ]},
        ],
    }
    _apply_npc_memory_bounds(rolling3, current_turn=20)
    eli = rolling3["npc_memory"][0]
    events_kept = [str(e.get("event", "")) for e in eli["remembers"]]
    ok &= _expect("Minor stale memory decayed",
                  not any("smiled" in e for e in events_kept),
                  detail=str(events_kept))
    ok &= _expect("Major memory preserved through decay",
                  any("debt" in e for e in events_kept),
                  detail=str(events_kept))
    return ok


def main() -> int:
    results = []
    results.append(scenario_leak_validator())
    results.append(scenario_direct_inspection())
    results.append(scenario_room_audit())
    results.append(scenario_npc_memory_and_faction())
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{'=' * 50}")
    if passed == total:
        print(f"{GREEN}ALL {total} P1 VERIFICATION SCENARIOS PASSED{END}")
        return 0
    print(f"{RED}{passed}/{total} scenarios passed — P1 NOT GREEN{END}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
