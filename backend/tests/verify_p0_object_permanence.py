"""
P0 — Structural verification for object permanence + memory bloat fixes.

Runs deterministic, LLM-free simulations of the rolling-state merge across
multiple turns to confirm:

  1. The SAME physical object never accumulates contradictory rows in
     rolling_state.object_locations or rolling_state.inventory_objects.
  2. Cross-category ledger deduplication removes the object from any
     ledger category that doesn't match its canonical status.
  3. Identity collapsing handles label drift ("the iron key" vs "iron key").

Usage:
    python /app/backend/tests/verify_p0_object_permanence.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from memory import consolidate_rolling_state, canonicalize_object_registry  # noqa: E402
from server import (  # noqa: E402
    ParsedTurn,
    _apply_object_permanence,
    _apply_ledger_object_permanence,
    _normalize_object_identity,
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


def count_object_rows(state, ident: str) -> int:
    rows = state.get("object_locations") or []
    return sum(1 for r in rows if _normalize_object_identity(r.get("object")) == ident)


# ---------------------------------------------------------------------------
# Scenario 1 — Same object, status drift across turns
# ---------------------------------------------------------------------------
def scenario_status_drift() -> bool:
    section("Scenario 1 — Same key carried → stored across turns")
    # Turn 1: key is carried
    t1 = {
        "object_locations": [
            {"object": "iron key", "status": "carried", "where": "left pocket", "turn_changed": 1}
        ],
        "inventory_objects": [
            {"object": "iron key", "qty": "1", "condition": "usable",
             "location_state": "carried", "where": "left pocket"}
        ],
    }
    # Turn 2: model emits same object as stored, with slightly different label
    t2 = {
        "object_locations": [
            {"object": "the iron key", "status": "stored", "where": "under shelf", "turn_changed": 2}
        ],
        "inventory_objects": [
            {"object": "the iron key", "qty": "1", "condition": "usable",
             "location_state": "stored", "where": "under shelf"}
        ],
    }

    # BEFORE-state simulation (no canonicalization): manual union as old code did
    pre = {"object_locations": list(t1["object_locations"]) + list(t2["object_locations"])}
    print(f"  pre-patch object_locations rows: {len(pre['object_locations'])}  "
          f"(contradictory status accumulated)")

    # AFTER-state: real merge with canonicalization
    merged_a = consolidate_rolling_state(t1, t2)
    print(f"  post-patch object_locations: "
          f"{json.dumps(merged_a.get('object_locations'), indent=2)}")
    print(f"  post-patch inventory_objects: "
          f"{json.dumps(merged_a.get('inventory_objects'), indent=2)}")

    ok = True
    ok &= _expect(
        "single canonical row for 'iron key' identity",
        count_object_rows(merged_a, _normalize_object_identity("iron key")) == 1,
    )
    rows = merged_a.get("object_locations") or []
    ok &= _expect(
        "row reflects MOST RECENT status (stored)",
        len(rows) == 1 and str(rows[0].get("status")).lower() == "stored",
        detail=str(rows),
    )
    inv = merged_a.get("inventory_objects") or []
    ok &= _expect(
        "inventory_objects.location_state aligned to truth (stored)",
        len(inv) == 1 and str(inv[0].get("location_state")).lower() == "stored",
        detail=str(inv),
    )
    return ok


# ---------------------------------------------------------------------------
# Scenario 2 — Repeated compression cycles (memory bloat)
# ---------------------------------------------------------------------------
def scenario_compression_cycles() -> bool:
    section("Scenario 2 — 10 compression cycles must NOT bloat object_locations")
    state = {}
    statuses = ["carried", "carried", "stored", "stored", "carried",
                "hidden", "hidden", "dropped", "stored", "carried"]
    for i, s in enumerate(statuses, start=1):
        turn = {
            "object_locations": [
                {"object": "old satchel", "status": s, "where": "scene", "turn_changed": i}
            ],
            "inventory_objects": [
                {"object": "old satchel", "qty": "1", "condition": "usable",
                 "location_state": s, "where": "scene"}
            ],
        }
        state = consolidate_rolling_state(state, turn)
    rows = state.get("object_locations") or []
    inv = state.get("inventory_objects") or []
    ok = True
    ok &= _expect(
        f"object_locations stays at 1 row after 10 cycles (got {len(rows)})",
        len(rows) == 1, detail=str(rows),
    )
    ok &= _expect(
        f"inventory_objects stays at 1 row after 10 cycles (got {len(inv)})",
        len(inv) == 1, detail=str(inv),
    )
    ok &= _expect(
        "final status equals LAST emitted (carried)",
        rows and str(rows[0].get("status")).lower() == "carried",
    )
    return ok


# ---------------------------------------------------------------------------
# Scenario 3 — Cross-category ledger dedup
# ---------------------------------------------------------------------------
def scenario_ledger_dedup() -> bool:
    section("Scenario 3 — Ledger says Carried AND Stored, rolling truth says stored")
    parsed = ParsedTurn(
        narrative="...",
        paragraphs=[],
        choices=[],
        state={},
        ledger={
            "Carried": "iron key (1, usable); old satchel (1, worn)",
            "Worn": "—",
            "Stored": "shelf — iron key (1, usable)",
            "Weapons": "—",
            "Supplies": "—",
            "Uncertain": "—",
            "Load": "light",
        },
        rolling_state={
            "object_locations": [
                {"object": "iron key", "status": "stored", "where": "under shelf"},
                {"object": "old satchel", "status": "carried", "where": "shoulder"},
            ]
        },
        debug={},
        raw="",
    )
    adjustments = _apply_ledger_object_permanence(parsed)
    print(f"  adjustments: {adjustments}")
    print(f"  post-patch Carried: {parsed.ledger.get('Carried')}")
    print(f"  post-patch Stored:  {parsed.ledger.get('Stored')}")

    ok = True
    carried = parsed.ledger.get("Carried", "")
    stored = parsed.ledger.get("Stored", "")
    ok &= _expect(
        "iron key REMOVED from Carried (truth says stored)",
        "iron key" not in carried.lower(),
        detail=f"Carried={carried!r}",
    )
    ok &= _expect(
        "iron key KEPT in Stored",
        "iron key" in stored.lower(),
        detail=f"Stored={stored!r}",
    )
    ok &= _expect(
        "old satchel KEPT in Carried (truth agrees)",
        "satchel" in carried.lower(),
        detail=f"Carried={carried!r}",
    )
    return ok


# ---------------------------------------------------------------------------
# Scenario 4 — Custom-world setup seeding survives canonicalization
# ---------------------------------------------------------------------------
def scenario_setup_seed_canonical() -> bool:
    section("Scenario 4 — Setup-seeded inventory + model emission stays single row")
    # Player setup seed-row (turn 1 boot)
    seeded = {
        "inventory_objects": [
            {"object": "bone-handled knife", "qty": "1",
             "condition": "player-described", "location_state": "carried",
             "where": "on player at story start"}
        ],
        "object_locations": [
            {"object": "bone-handled knife", "status": "carried",
             "where": "on player at story start", "turn_changed": 1}
        ],
    }
    # Model emission also references the knife with slightly different wording
    fresh = {
        "inventory_objects": [
            {"object": "bone handled knife", "qty": "1",
             "condition": "usable", "location_state": "carried",
             "where": "hip sheath"}
        ],
        "object_locations": [
            {"object": "bone handled knife", "status": "carried",
             "where": "hip sheath", "turn_changed": 1}
        ],
    }
    merged = consolidate_rolling_state(seeded, fresh)
    canonicalize_object_registry(merged)
    rows = merged.get("object_locations") or []
    inv = merged.get("inventory_objects") or []
    ok = True
    ok &= _expect(f"object_locations collapsed to 1 row (got {len(rows)})", len(rows) == 1, detail=str(rows))
    ok &= _expect(f"inventory_objects collapsed to 1 row (got {len(inv)})", len(inv) == 1, detail=str(inv))
    return ok


def main() -> int:
    results = []
    results.append(scenario_status_drift())
    results.append(scenario_compression_cycles())
    results.append(scenario_ledger_dedup())
    results.append(scenario_setup_seed_canonical())
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{'=' * 50}")
    if passed == total:
        print(f"{GREEN}ALL {total} P0 VERIFICATION SCENARIOS PASSED{END}")
        return 0
    print(f"{RED}{passed}/{total} scenarios passed — P0 NOT GREEN{END}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
