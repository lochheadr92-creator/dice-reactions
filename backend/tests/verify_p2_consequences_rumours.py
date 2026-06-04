import sys
from pathlib import Path
import json

# Add backend dir to path so we can import server.py functions
sys.path.append(str(Path('/app/backend')))

from server import _apply_delayed_consequence_tick, _apply_rumour_propagation_tick

def run_tests():
    print("Running P2 - Delayed Consequence & Rumour Propagation Verification...\n")
    
    # ---------------------------------------------------------
    # TEST 1: delayed consequence fires on fire_on_turn
    # ---------------------------------------------------------
    rs = {
        "delayed_consequences": [
            {
                "description": "Bomb explodes",
                "trigger": {"condition": "fire_on_turn", "turn": 5},
                "state": "pending"
            }
        ]
    }
    adj = _apply_delayed_consequence_tick(rs, 4)
    assert not adj, f"Test 1a failed: Should not fire on turn 4. Adjustments: {adj}"
    assert rs["delayed_consequences"][0]["state"] == "pending"
    
    adj = _apply_delayed_consequence_tick(rs, 5)
    assert "delayed_fired:0" in adj[0], "Test 1b failed: Should fire on turn 5"
    assert rs["delayed_consequences"][0]["state"] == "fired"
    assert rs["delayed_consequences"][0]["fired_turn"] == 5
    assert "FIRED CONSEQUENCE: Bomb explodes" in rs.get("unresolved", []), "Test 1c failed: Not added to unresolved"
    print("✅ 1. delayed consequence fires on fire_on_turn")

    # ---------------------------------------------------------
    # TEST 2: delayed consequence fires only once
    # ---------------------------------------------------------
    adj = _apply_delayed_consequence_tick(rs, 6)
    assert not adj, "Test 2 failed: Should not fire again on turn 6"
    print("✅ 2. delayed consequence fires only once")

    # ---------------------------------------------------------
    # TEST 3: delayed consequence ignores legacy entries without trigger fields
    # ---------------------------------------------------------
    rs = {
        "delayed_consequences": [
            {
                "description": "Legacy format",
                "condition": "when it rains",
                "state": "pending"
            }
        ]
    }
    adj = _apply_delayed_consequence_tick(rs, 5)
    assert not adj, "Test 3 failed: Should ignore legacy entry"
    print("✅ 3. delayed consequence ignores legacy entries without trigger fields")

    # ---------------------------------------------------------
    # TEST 4: witness_count>=N works deterministically
    # ---------------------------------------------------------
    rs = {
        "delayed_consequences": [
            {
                "description": "Town mob",
                "trigger": {"condition": "witness_count>=N", "N": 2},
                "state": "pending"
            }
        ],
        "npc_memory": [
            {"name": "Alice", "remembers": [{"event": "player killed guard", "severity": "major"}]}
        ]
    }
    adj = _apply_delayed_consequence_tick(rs, 1)
    assert not adj, "Test 4a failed: Should not fire with 1 witness"
    
    # Add a second witness
    rs["npc_memory"].append(
        {"name": "Bob", "remembers": [{"event": "player stole", "severity": "major"}]}
    )
    adj = _apply_delayed_consequence_tick(rs, 2)
    assert "delayed_fired:0" in adj[0], "Test 4b failed: Should fire with 2 witnesses"
    assert "FIRED CONSEQUENCE: Town mob" in rs.get("unresolved", [])
    print("✅ 4. witness_count>=N works deterministically")

    # ---------------------------------------------------------
    # TEST 5: rumour seeds from major npc_memory event
    # ---------------------------------------------------------
    rs = {
        "npc_memory": [
            {"name": "Charlie", "remembers": [{"event": "player burned the cart", "severity": "major"}]}
        ]
    }
    adj = _apply_rumour_propagation_tick(rs, 1)
    assert "rumour_seeded" in adj[0], "Test 5a failed: Rumour should be seeded"
    assert len(rs["rumours"]) == 1
    r = rs["rumours"][0]
    assert r["summary"] == "player burned the cart"
    assert r["seed_event"] == "player burned the cart"
    assert r["state"] == "active"
    assert r["hops"] == 0
    print("✅ 5. rumour seeds from major npc_memory event")

    # ---------------------------------------------------------
    # TEST 6: rumour propagates one hop per tick
    # ---------------------------------------------------------
    adj = _apply_rumour_propagation_tick(rs, 2)
    r = rs["rumours"][0]
    assert r["hops"] == 1, f"Test 6 failed: Hops should be 1, got {r['hops']}"
    assert r["last_propagated_turn"] == 2
    assert r["spread_count"] == 1
    assert r["heat_level"] == 2
    print("✅ 6. rumour propagates one hop per tick")

    # ---------------------------------------------------------
    # TEST 7: rumour does not mutate summary text
    # ---------------------------------------------------------
    adj = _apply_rumour_propagation_tick(rs, 3)
    r = rs["rumours"][0]
    assert r["summary"] == "player burned the cart", "Test 7 failed: Summary text mutated!"
    assert r["hops"] == 2
    print("✅ 7. rumour does not mutate summary text")

    # ---------------------------------------------------------
    # TEST 8: rumour updates faction tick only on first delivery
    # ---------------------------------------------------------
    rs = {
        "rumours": [
            {
                "summary": "player is a thief",
                "seed_event": "player is a thief",
                "spread_count": 0,
                "heat_level": 1,
                "delivered_factions": [],
                "witnesses": ["Dave"],
                "hops": 0,
                "last_propagated_turn": 1,
                "state": "active",
                "turn_seeded": 1
            }
        ],
        "faction_pressure": [
            {"name": "Guards", "ticks": {}},
            {"name": "Thieves Guild", "ticks": {}}
        ]
    }
    adj = _apply_rumour_propagation_tick(rs, 2)
    r = rs["rumours"][0]
    assert len(r["delivered_factions"]) == 1, "Test 8a failed: Should deliver to 1 faction"
    assert r["delivered_factions"][0] == "Guards"
    assert rs["faction_pressure"][0]["ticks"].get("suspicion", 0) == 1, "Test 8b failed: Guards suspicion should be 1"
    
    # Tick again
    adj = _apply_rumour_propagation_tick(rs, 3)
    assert len(r["delivered_factions"]) == 2, "Test 8c failed: Should deliver to 2nd faction"
    assert r["delivered_factions"][1] == "Thieves Guild"
    assert rs["faction_pressure"][1]["ticks"].get("suspicion", 0) == 1
    assert rs["faction_pressure"][0]["ticks"].get("suspicion", 0) == 1, "Test 8d failed: Guards suspicion should not increase again from same rumour"
    print("✅ 8. rumour updates faction tick only on first delivery")

    # ---------------------------------------------------------
    # TEST 9: rumour decays/expires
    # ---------------------------------------------------------
    rs = {
        "rumours": [
            {
                "summary": "old news",
                "state": "active",
                "hops": 5, # Max hops is 6
                "last_propagated_turn": 10
            }
        ]
    }
    adj = _apply_rumour_propagation_tick(rs, 11)
    r = rs["rumours"][0]
    assert r["hops"] == 6
    assert r["state"] == "expired", "Test 9 failed: Rumour should be expired at max hops"
    print("✅ 9. rumour decays/expires")

    # ---------------------------------------------------------
    # TEST 10: rumour caps prevent unbounded growth
    # ---------------------------------------------------------
    rs = {"rumours": []}
    for i in range(20):
        rs["rumours"].append({
            "summary": f"rumour {i}",
            "state": "active" if i < 5 else "expired",
            "turn_seeded": i,
            "last_propagated_turn": 100
        })
    adj = _apply_rumour_propagation_tick(rs, 101)
    assert len(rs["rumours"]) == 15, f"Test 10 failed: Should be capped at 15, got {len(rs['rumours'])}"
    assert rs["rumours"][0]["state"] == "active", "Test 10 failed: Active rumours should be prioritized"
    print("✅ 10. rumour caps prevent unbounded growth")

    # ---------------------------------------------------------
    # TEST 11: repeated same-turn tick is idempotent
    # ---------------------------------------------------------
    rs = {
        "rumours": [
            {
                "summary": "test",
                "state": "active",
                "hops": 1,
                "last_propagated_turn": 1,
                "heat_level": 1
            }
        ]
    }
    _apply_rumour_propagation_tick(rs, 2)
    assert rs["rumours"][0]["hops"] == 2
    
    # Tick again on same turn
    _apply_rumour_propagation_tick(rs, 2)
    assert rs["rumours"][0]["hops"] == 2, "Test 11 failed: Hops increased twice on same turn"
    print("✅ 11. repeated same-turn tick is idempotent")

    # ---------------------------------------------------------
    # TEST 12: save/load compatible JSON shape
    # ---------------------------------------------------------
    try:
        json_str = json.dumps(rs)
        loaded = json.loads(json_str)
        assert loaded == rs, "Test 12 failed: Reloaded JSON does not match"
        print("✅ 12. save/load compatible JSON shape")
    except Exception as e:
        print(f"❌ 12. save/load compatible JSON shape FAILED: {e}")
        raise

    # ---------------------------------------------------------
    # TEST 13: Scoped witness_count fires when enough NPC memories match the same subject/tag.
    # ---------------------------------------------------------
    rs = {
        "delayed_consequences": [
            {
                "description": "Tavern mob",
                "trigger": {"condition": "witness_count>=N", "N": 2},
                "subject": "tavern_fire",
                "state": "pending"
            }
        ],
        "npc_memory": [
            {"name": "Alice", "remembers": [{"event": "saw fire", "severity": "major", "subject": "Tavern_Fire"}]},
            {"name": "Bob", "remembers": [{"event": "saw smoke", "severity": "major", "subject": "tavern_fire"}]}
        ]
    }
    adj = _apply_delayed_consequence_tick(rs, 1)
    assert "delayed_fired:0" in adj[0], "Test 13 failed: Should fire with 2 scoped witnesses"
    print("✅ 13. Scoped witness_count fires when enough NPC memories match the same subject/tag")

    # ---------------------------------------------------------
    # TEST 14: Scoped witness_count does not fire when NPCs only remember unrelated major events.
    # ---------------------------------------------------------
    rs = {
        "delayed_consequences": [
            {
                "description": "Tavern mob",
                "trigger": {"condition": "witness_count>=N", "N": 2},
                "subject": "tavern_fire",
                "state": "pending"
            }
        ],
        "npc_memory": [
            {"name": "Alice", "remembers": [{"event": "saw fire", "severity": "major", "subject": "tavern_fire"}]},
            {"name": "Bob", "remembers": [{"event": "saw theft", "severity": "major", "subject": "market_theft"}]},
            {"name": "Charlie", "remembers": [{"event": "saw murder", "severity": "major"}]}
        ]
    }
    adj = _apply_delayed_consequence_tick(rs, 1)
    assert not adj, "Test 14 failed: Should not fire because only 1 scoped witness exists"
    print("✅ 14. Scoped witness_count does not fire when NPCs only remember unrelated major events")

    # ---------------------------------------------------------
    # TEST 15: Legacy unscoped witness_count still works as before.
    # ---------------------------------------------------------
    rs = {
        "delayed_consequences": [
            {
                "description": "General mob",
                "trigger": {"condition": "witness_count>=N", "N": 2},
                "state": "pending"
            }
        ],
        "npc_memory": [
            {"name": "Alice", "remembers": [{"event": "player killed guard", "severity": "major"}]},
            {"name": "Bob", "remembers": [{"event": "saw player sneak", "severity": "major"}]}
        ]
    }
    adj = _apply_delayed_consequence_tick(rs, 1)
    assert "delayed_fired:0" in adj[0], "Test 15 failed: Should fire with legacy unscoped witnesses"
    print("✅ 15. Legacy unscoped witness_count still works as before")


    print("\nAll synthetic tests passed successfully! 🎉")

if __name__ == "__main__":
    run_tests()
