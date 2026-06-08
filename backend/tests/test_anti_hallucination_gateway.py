"""
Anti-Hallucination Gateway (Ch 31) unit tests.

Pure-Python: imports `gateway` directly (no DB / no HTTP).
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import gateway  # noqa: E402


class _Parsed:
    """Lightweight stand-in for ParsedTurn for unit testing."""

    def __init__(self, narrative="", paragraphs=None, rolling_state=None, ledger=None):
        self.narrative = narrative
        self.paragraphs = paragraphs if paragraphs is not None else (
            [narrative] if narrative else []
        )
        self.rolling_state = rolling_state
        self.ledger = ledger or {}


# ---------------------------------------------------------------------------
# build_truth / build_immutable_truth_block
# ---------------------------------------------------------------------------
def test_build_truth_extracts_terminal_objects_deceased_injuries():
    prior = {
        "object_locations": [
            {"object": "iron key", "status": "destroyed"},
            {"object": "ration pack", "status": "consumed"},
            {"object": "torch", "status": "carried"},
        ],
        "deceased": ["Mira"],
        "injuries": [
            {"name": "gunshot wound", "severity": "critical", "status": "active"},
            {"name": "scratch", "severity": "minor", "status": "stable"},
        ],
    }
    truth = gateway.build_truth(prior)
    assert "key" in truth["terminal_objects"]
    assert "pack ration" in truth["terminal_objects"] or any(
        "ration" in k for k in truth["terminal_objects"]
    )
    assert "torch" not in truth["terminal_objects"]
    assert truth["deceased"] == ["Mira"]
    names = {i["name"] for i in truth["serious_injuries"]}
    assert "gunshot wound" in names
    assert "scratch" not in names  # minor + stable is not serious


def test_truth_block_renders_or_empty():
    assert gateway.build_immutable_truth_block(None) == ""
    assert gateway.build_immutable_truth_block({}) == ""
    block = gateway.build_immutable_truth_block(
        {"object_locations": [{"object": "old map", "status": "destroyed"}]}
    )
    assert "established_truth" in block
    assert "GONE FOREVER" in block


# ---------------------------------------------------------------------------
# strip_illegal_state_changes
# ---------------------------------------------------------------------------
def test_strip_reverts_terminal_object_revival_in_rolling_and_ledger():
    prior = {"object_locations": [{"object": "iron key", "status": "destroyed"}]}
    parsed = _Parsed(
        narrative="You move on.",
        rolling_state={
            "object_locations": [{"object": "iron key", "status": "carried"}],
            "inventory_objects": [{"object": "iron key", "location_state": "carried"}],
        },
        ledger={"Carried": "iron key; torch"},
    )
    adj = gateway.strip_illegal_state_changes(prior, {}, parsed, "walk forward")
    assert parsed.rolling_state["object_locations"][0]["status"] == "destroyed"
    assert parsed.rolling_state["inventory_objects"][0]["location_state"] == "destroyed"
    assert "iron key" not in parsed.ledger["Carried"]
    assert "torch" in parsed.ledger["Carried"]
    assert any("terminal_object_revival_blocked" in a for a in adj)


def test_strip_blocks_silent_injury_resolution_without_cue():
    prior = {"injuries": [{"name": "broken leg", "severity": "severe", "status": "active"}]}
    parsed = _Parsed(
        narrative="You keep walking down the corridor.",
        rolling_state={"injuries": [{"name": "broken leg", "severity": "minor", "status": "resolved"}]},
    )
    adj = gateway.strip_illegal_state_changes(prior, {}, parsed, "keep walking")
    inj = parsed.rolling_state["injuries"][0]
    assert inj["status"] == "active"      # reverted
    assert inj["severity"] == "severe"    # reverted
    assert any("silent_injury_recovery_blocked" in a for a in adj)


def test_strip_allows_injury_resolution_with_recovery_cue():
    prior = {"injuries": [{"name": "broken leg", "severity": "severe", "status": "active"}]}
    parsed = _Parsed(
        narrative="You rest and bandage the wound carefully until it is treated.",
        rolling_state={"injuries": [{"name": "broken leg", "severity": "moderate", "status": "treating"}]},
    )
    gateway.strip_illegal_state_changes(prior, {}, parsed, "rest and treat the leg")
    # Recovery cue present → no revert.
    inj = parsed.rolling_state["injuries"][0]
    assert inj["status"] == "treating"
    assert inj["severity"] == "moderate"


def test_strip_neutralises_deceased_npc_revival():
    prior = {"deceased": ["Garrett"]}
    parsed = _Parsed(
        narrative="The hall is quiet.",
        rolling_state={
            "npcs": [{"name": "Garrett", "stance": "ally", "last_seen": "the hall"}],
            "npc_memory": [{"name": "Garrett", "next_move": "help the player"}],
        },
    )
    adj = gateway.strip_illegal_state_changes(prior, {}, parsed, "look around")
    assert parsed.rolling_state["npcs"][0]["stance"] == "dead"
    assert "deceased" in parsed.rolling_state["npc_memory"][0]["next_move"].lower()
    assert any("deceased_npc_revival_blocked" in a for a in adj)


# ---------------------------------------------------------------------------
# update_death_registry
# ---------------------------------------------------------------------------
def test_death_registry_records_clear_death():
    prior = {"npc_memory": [{"name": "Mira"}]}
    merged = {"npc_memory": [{"name": "Mira"}]}
    parsed = _Parsed(narrative="The blade finds its mark and Mira lies dead on the cold stone.")
    adj = gateway.update_death_registry(parsed, prior, merged, "stab Mira")
    assert "Mira" in merged.get("deceased", [])
    assert any("death_recorded" in a for a in adj)


def test_death_registry_ignores_threats_and_hypotheticals():
    prior = {"npc_memory": [{"name": "Mira"}]}
    merged = {"npc_memory": [{"name": "Mira"}]}
    parsed = _Parsed(narrative="Mira warns that she could be killed if the guards find her.")
    adj = gateway.update_death_registry(parsed, prior, merged, "talk to Mira")
    assert "Mira" not in merged.get("deceased", [])
    assert adj == []


# ---------------------------------------------------------------------------
# detect_prose_contradictions
# ---------------------------------------------------------------------------
def test_detect_flags_terminal_object_used_as_intact():
    prior = {"object_locations": [{"object": "brass lantern", "status": "destroyed"}]}
    parsed = _Parsed(narrative="You grab the brass lantern and light the way ahead.")
    reasons = gateway.detect_prose_contradictions(prior, parsed, "move forward")
    assert any("lantern" in r for r in reasons)


def test_detect_ignores_terminal_object_acknowledged_as_gone():
    prior = {"object_locations": [{"object": "brass lantern", "status": "destroyed"}]}
    parsed = _Parsed(narrative="You stare at the charred remains of the brass lantern, useless now.")
    reasons = gateway.detect_prose_contradictions(prior, parsed, "look at the lantern")
    assert reasons == []


def test_detect_flags_dead_npc_speaking():
    prior = {"deceased": ["Garrett"]}
    parsed = _Parsed(narrative="Garrett says you should hurry before the gate closes.")
    reasons = gateway.detect_prose_contradictions(prior, parsed, "wait")
    assert any("Garrett" in r for r in reasons)


def test_detect_ignores_dead_npc_referenced_as_memory():
    prior = {"deceased": ["Garrett"]}
    parsed = _Parsed(narrative="You remember how Garrett used to laugh; his grave lies behind you.")
    reasons = gateway.detect_prose_contradictions(prior, parsed, "mourn")
    assert reasons == []


def test_no_prior_state_is_safe():
    parsed = _Parsed(narrative="You grab the brass lantern and run.")
    assert gateway.detect_prose_contradictions(None, parsed, "run") == []
    assert gateway.strip_illegal_state_changes(None, None, parsed, "run") == []


# ---------------------------------------------------------------------------
# update_destruction_registry — the live-model gap (rename / drop instead of status)
# ---------------------------------------------------------------------------
def _terminal_status(merged, needle):
    for r in merged.get("object_locations", []):
        if needle in str(r.get("object", "")).lower():
            return r.get("status")
    return None


def test_destruction_registry_handles_rename_to_fragments():
    # Model renamed "iron lantern" -> "lantern fragments" in inventory only.
    prior = {"object_locations": [{"object": "iron lantern", "status": "carried"}]}
    merged = {
        "object_locations": [{"object": "iron lantern", "status": "carried"}],
        "inventory_objects": [
            {"object": "lantern fragments", "location_state": "dropped", "condition": "broken"}
        ],
    }
    parsed = _Parsed(narrative="The lantern bursts apart against the wall.")
    adj = gateway.update_destruction_registry(parsed, prior, merged, "smash the lantern")
    assert _terminal_status(merged, "lantern") == "destroyed"
    # Husk row removed from inventory.
    assert not any("fragment" in str(r.get("object", "")).lower()
                   for r in merged.get("inventory_objects", []))
    assert any("object_terminal_recorded" in a for a in adj)


def test_destruction_registry_verb_based_destroy():
    prior = {"object_locations": [{"object": "wooden crate", "status": "stored"}]}
    merged = {"object_locations": [{"object": "wooden crate", "status": "stored"}]}
    parsed = _Parsed(narrative="You smash the wooden crate to splinters with the axe.")
    gateway.update_destruction_registry(parsed, prior, merged, "break open the wooden crate")
    assert _terminal_status(merged, "crate") == "destroyed"


def test_destruction_registry_verb_based_consume():
    prior = {"object_locations": [{"object": "ration pack", "status": "carried"}]}
    # Model silently dropped the consumed item from current state.
    merged = {"object_locations": []}
    parsed = _Parsed(narrative="You tear open the ration pack and eat every crumb.")
    gateway.update_destruction_registry(parsed, prior, merged, "eat the ration pack")
    assert _terminal_status(merged, "ration") == "consumed"


def test_destruction_registry_ignores_hypothetical():
    prior = {"object_locations": [{"object": "old map", "status": "carried"}]}
    merged = {"object_locations": [{"object": "old map", "status": "carried"}]}
    parsed = _Parsed(narrative="You could burn the old map if the guards get close.")
    adj = gateway.update_destruction_registry(parsed, prior, merged, "consider burning the map")
    assert _terminal_status(merged, "map") == "carried"  # unchanged
    assert adj == []


def test_destruction_then_strip_blocks_revival_next_turn():
    # Turn N: destroy. Turn N+1: model tries to carry it again -> strip reverts.
    prior = {"object_locations": [{"object": "brass key", "status": "carried"}]}
    merged = {"object_locations": [{"object": "brass key", "status": "carried"}]}
    parsed = _Parsed(narrative="The brass key melts to slag in the furnace.")
    gateway.update_destruction_registry(parsed, prior, merged, "throw the brass key into the furnace")
    assert _terminal_status(merged, "key") == "destroyed"

    # Next turn: prior is `merged` (key destroyed); model revives it.
    next_parsed = _Parsed(
        narrative="You pocket the key.",
        rolling_state={"object_locations": [{"object": "brass key", "status": "carried"}]},
    )
    gateway.strip_illegal_state_changes(merged, {}, next_parsed, "grab the key")
    assert next_parsed.rolling_state["object_locations"][0]["status"] == "destroyed"


def test_destruction_registry_no_known_objects_is_safe():
    parsed = _Parsed(narrative="You smash everything in sight.")
    assert gateway.update_destruction_registry(parsed, None, {"object_locations": []}, "smash") == []
