"""
Active scene cast preservation + death authorisation gate (Ch 31 extension).

Pure-Python: imports `gateway` and `memory` directly (no DB / no HTTP).

Contract under test:
  • `rolling_state["npcs"]` (the active scene cast) is engine-protected —
    an NPC silently dropped by the model is restored after consolidation.
  • Explicit exits (absent/removed/departed markers) are allowed.
  • Prose-only deaths never enter the engine-owned `deceased` registry;
    deaths corroborated by structured state are accepted.
  • Anti-resurrection behaviour is preserved.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import gateway  # noqa: E402
from memory import consolidate_rolling_state  # noqa: E402


class _Parsed:
    def __init__(self, narrative="", rolling_state=None, ledger=None):
        self.narrative = narrative
        self.paragraphs = [narrative] if narrative else []
        self.rolling_state = rolling_state
        self.ledger = ledger or {}


def _prior():
    return {
        "scene": "dock warehouse",
        "npcs": [
            {"name": "Mara", "npc_id": "npc-mara", "stance": "ally", "last_seen": "dock"},
            {"name": "Garrick", "npc_id": "npc-garrick", "stance": "neutral", "last_seen": "dock"},
        ],
        "deceased": [],
    }


# ---------------------------------------------------------------------------
# 1. Dropped NPC restored
# ---------------------------------------------------------------------------
def test_silently_dropped_npc_is_restored():
    prior = _prior()
    merged = {
        "scene": "dock warehouse",
        "npcs": [{"name": "Mara", "npc_id": "npc-mara", "stance": "ally", "last_seen": "dock"}],
        "deceased": [],
    }
    adj = gateway.preserve_active_scene_cast(prior, merged)
    names = {n["name"] for n in merged["npcs"]}
    assert "Garrick" in names, "silently dropped NPC must be restored"
    assert "Mara" in names
    assert any("scene_cast_npc_restored" in a for a in adj)
    restored = [n for n in merged["npcs"] if n["name"] == "Garrick"][0]
    assert restored["npc_id"] == "npc-garrick"  # full row restored, not a stub


# ---------------------------------------------------------------------------
# 2. Explicit exit allowed
# ---------------------------------------------------------------------------
def test_explicit_exit_marker_is_allowed():
    prior = _prior()
    # Fresh state marks Garrick as explicitly absent — an explicit exit, kept as-is.
    merged = {
        "scene": "dock warehouse",
        "npcs": [
            {"name": "Mara", "npc_id": "npc-mara", "stance": "ally"},
            {"name": "Garrick", "npc_id": "npc-garrick", "stance": "neutral", "absent": True},
        ],
        "deceased": [],
    }
    adj = gateway.preserve_active_scene_cast(prior, merged)
    assert adj == []
    garrick = [n for n in merged["npcs"] if n["name"] == "Garrick"][0]
    assert garrick["absent"] is True


def test_previously_exited_npc_is_not_resurrected_into_cast():
    prior = _prior()
    prior["npcs"][1]["absent"] = True  # Garrick already exited on an earlier turn
    merged = {
        "scene": "dock warehouse",
        "npcs": [{"name": "Mara", "npc_id": "npc-mara", "stance": "ally"}],
        "deceased": [],
    }
    adj = gateway.preserve_active_scene_cast(prior, merged)
    assert adj == []
    assert {n["name"] for n in merged["npcs"]} == {"Mara"}


def test_scene_change_authorises_cast_turnover():
    prior = _prior()
    merged = {
        "scene": "harbour master's office",
        "npcs": [{"name": "Harbour Master", "stance": "neutral"}],
        "deceased": [],
    }
    adj = gateway.preserve_active_scene_cast(prior, merged)
    assert adj == []
    assert {n["name"] for n in merged["npcs"]} == {"Harbour Master"}


# ---------------------------------------------------------------------------
# 3. Prose-only death blocked
# ---------------------------------------------------------------------------
def test_prose_only_death_is_blocked():
    prior = _prior()
    merged = {
        "scene": "dock warehouse",
        # Structured state still shows Garrick alive — prose alone is not authority.
        "npcs": [
            {"name": "Mara", "stance": "ally"},
            {"name": "Garrick", "stance": "neutral"},
        ],
        "deceased": [],
    }
    parsed = _Parsed(
        narrative="The shot echoes across the water and Garrick lies dead on the planks.",
        rolling_state={"npcs": list(merged["npcs"])},
    )
    adj = gateway.update_death_registry(parsed, prior, merged, "shoot Garrick")
    assert "Garrick" not in (merged.get("deceased") or [])
    assert any("prose_only_death_blocked" in a for a in adj)
    assert not any("death_recorded" in a for a in adj)


# ---------------------------------------------------------------------------
# 4. Authorised death accepted
# ---------------------------------------------------------------------------
def test_state_corroborated_death_is_accepted():
    prior = _prior()
    merged = {
        "scene": "dock warehouse",
        "npcs": [
            {"name": "Mara", "stance": "ally"},
            {"name": "Garrick", "stance": "dead"},
        ],
        "deceased": [],
    }
    parsed = _Parsed(
        narrative="The shot echoes across the water and Garrick lies dead on the planks.",
        rolling_state={"npcs": list(merged["npcs"])},
    )
    adj = gateway.update_death_registry(parsed, prior, merged, "shoot Garrick")
    assert "Garrick" in merged["deceased"]
    assert any("death_recorded" in a for a in adj)
    # Deceased NPCs may leave the cast — the guard must not restore them.
    merged["npcs"] = [n for n in merged["npcs"] if n["name"] != "Garrick"]
    cast_adj = gateway.preserve_active_scene_cast(prior, merged)
    assert cast_adj == []
    assert {n["name"] for n in merged["npcs"]} == {"Mara"}


# ---------------------------------------------------------------------------
# 5. Dead NPC cannot revive (anti-resurrection preserved)
# ---------------------------------------------------------------------------
def test_dead_npc_cannot_revive():
    prior = {"deceased": ["Garrick"]}
    parsed = _Parsed(
        narrative="The warehouse is silent.",
        rolling_state={
            "npcs": [{"name": "Garrick", "stance": "ally", "last_seen": "dock"}],
            "npc_memory": [{"name": "Garrick", "next_move": "help the player"}],
        },
    )
    adj = gateway.strip_illegal_state_changes(prior, {}, parsed, "look around")
    assert parsed.rolling_state["npcs"][0]["stance"] == "dead"
    assert "deceased" in parsed.rolling_state["npc_memory"][0]["next_move"].lower()
    assert any("deceased_npc_revival_blocked" in a for a in adj)


def test_guard_never_restores_deceased_npc_into_cast():
    prior = _prior()
    merged = {
        "scene": "dock warehouse",
        "npcs": [{"name": "Mara", "stance": "ally"}],
        "deceased": ["Garrick"],
    }
    adj = gateway.preserve_active_scene_cast(prior, merged)
    assert adj == []
    assert {n["name"] for n in merged["npcs"]} == {"Mara"}


# ---------------------------------------------------------------------------
# 6. Scene cast survives rolling-state consolidation
# ---------------------------------------------------------------------------
def test_scene_cast_survives_rolling_state_consolidation():
    """Full post-turn pipeline: consolidate → death registry → cast guard."""
    prior = _prior()
    fresh = {
        "scene": "dock warehouse",
        # Model re-emitted the cast but silently dropped Garrick.
        "npcs": [{"name": "Mara", "npc_id": "npc-mara", "stance": "ally"}],
        "recent_beats": ["Mara checks the manifest."],
    }
    parsed = _Parsed(narrative="Mara checks the manifest.", rolling_state=fresh)
    merged = consolidate_rolling_state(prior, fresh)
    adj = gateway.update_death_registry(parsed, prior, merged, "read the manifest")
    adj += gateway.preserve_active_scene_cast(prior, merged)
    names = {n["name"] for n in merged["npcs"]}
    assert names == {"Mara", "Garrick"}, "cast must survive consolidation"
    assert any("scene_cast_npc_restored" in a for a in adj)


def test_consolidation_dropping_whole_npcs_key_keeps_prior_cast():
    prior = _prior()
    fresh = {"scene": "dock warehouse", "recent_beats": ["Quiet."]}
    merged = consolidate_rolling_state(prior, fresh)
    adj = gateway.preserve_active_scene_cast(prior, merged)
    names = {n["name"] for n in merged["npcs"]}
    assert names == {"Mara", "Garrick"}
    assert adj == []  # prior cast already carried through — nothing to restore
