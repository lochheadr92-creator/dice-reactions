"""
Relationship Calculus (Ch 29) unit tests. Pure-Python (imports `relationships`).
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import relationships as rc  # noqa: E402


class _P:
    def __init__(self, narrative=""):
        self.narrative = narrative
        self.paragraphs = [narrative] if narrative else []


def _vec(merged, name):
    for v in merged.get("relationship_vectors", []):
        if v["name"].lower() == name.lower():
            return v
    return None


def test_new_npc_gets_zeroed_vector():
    merged = {"npcs": [{"name": "Garrett", "stance": "neutral"}]}
    rc.update_relationship_calculus(_P("The hall is quiet."), None, merged, "wait", 1)
    v = _vec(merged, "Garrett")
    assert v and v["trust"] == 0 and v["loyalty"] == 0 and v["fear"] == 0 and v["resentment"] == 0
    assert v["state"] == "neutral"


def test_help_raises_trust_and_loyalty():
    merged = {"npcs": [{"name": "Garrett"}]}
    rc.update_relationship_calculus(
        _P("You help Garrett to his feet and support him."), None, merged, "help Garrett", 2)
    v = _vec(merged, "Garrett")
    assert v["trust"] == rc.EVENT_DELTAS["help"]["trust"]
    assert v["loyalty"] == rc.EVENT_DELTAS["help"]["loyalty"]


def test_threaten_raises_fear_lowers_trust():
    merged = {"npcs": [{"name": "Garrett"}]}
    rc.update_relationship_calculus(
        _P("You threaten Garrett, pointing your blade at him."), None, merged, "threaten Garrett", 2)
    v = _vec(merged, "Garrett")
    assert v["fear"] >= 25 and v["trust"] < 0


def test_betrayal_of_loyal_ally_triggers_betrayal_risk():
    prior = {"relationship_vectors": [
        {"name": "Garrett", "trust": 40, "loyalty": 80, "fear": 0, "resentment": 0,
         "last_turn": 1, "bond": "neutral"}]}
    merged = {"npcs": [{"name": "Garrett"}]}
    rc.update_relationship_calculus(
        _P("You betray Garrett and lie to his face about the deal."), prior, merged, "betray Garrett", 3)
    v = _vec(merged, "Garrett")
    # betrayal only (lie subsumed): trust 40-60=-20, loyalty 80-50=30, resentment 0+70=70
    assert v["trust"] == -20 and v["resentment"] == 70 and v["loyalty"] == 30
    assert v["state"] == "betrayal_risk"


def test_save_life_subsumes_help():
    merged = {"npcs": [{"name": "Mira"}]}
    rc.update_relationship_calculus(
        _P("You help Mira up and drag her clear of the blast, saving her."), None, merged, "save Mira", 2)
    v = _vec(merged, "Mira")
    assert v["trust"] == 30          # save_life delta (not help's +12)
    assert v["fear"] == 0            # -10 delta clamped to the 0..100 floor


def test_hypothetical_threat_is_not_an_event():
    merged = {"npcs": [{"name": "Garrett"}]}
    rc.update_relationship_calculus(
        _P("You consider whether to threaten Garrett, but hold back."), None, merged, "think about it", 2)
    v = _vec(merged, "Garrett")
    assert v["fear"] == 0 and v["trust"] == 0


def test_neglect_decay_toward_neutral():
    prior = {"relationship_vectors": [
        {"name": "Garrett", "trust": 50, "loyalty": 80, "fear": 40, "resentment": 30,
         "last_turn": 1, "bond": "neutral", "state": "trusting"}]}
    merged = {"npcs": [{"name": "Garrett"}]}
    rc.update_relationship_calculus(_P("You walk on alone."), prior, merged, "walk", 5)
    v = _vec(merged, "Garrett")
    assert v["trust"] < 50 and v["fear"] < 40 and v["resentment"] < 30
    assert v["loyalty"] >= 79  # loyalty decays very slowly


def test_engine_owns_vectors_ignores_llm_injection():
    prior = {"relationship_vectors": [
        {"name": "Garrett", "trust": 20, "loyalty": 0, "fear": 0, "resentment": 0,
         "last_turn": 1, "bond": "neutral"}]}
    # LLM tried to inject a bogus vector into the merged state.
    merged = {"npcs": [{"name": "Garrett"}],
              "relationship_vectors": [{"name": "Garrett", "trust": 999}]}
    rc.update_relationship_calculus(_P("Silence."), prior, merged, "wait", 2)
    v = _vec(merged, "Garrett")
    assert v["trust"] <= 20  # decayed from prior 20, NOT 999


def test_deceased_npc_excluded():
    merged = {"npcs": [{"name": "Garrett"}], "deceased": ["Garrett"]}
    rc.update_relationship_calculus(_P("You help Garrett."), None, merged, "help", 2)
    assert _vec(merged, "Garrett") is None


def test_stance_synced_from_strong_signal():
    merged = {"npcs": [{"name": "Garrett", "stance": "neutral"}]}
    # Devotion via repeated reward + save would take turns; force via prior high loyalty.
    prior = {"relationship_vectors": [
        {"name": "Garrett", "trust": 60, "loyalty": 80, "fear": 0, "resentment": 0,
         "last_turn": 1, "bond": "neutral"}]}
    rc.update_relationship_calculus(_P("You travel together."), prior, merged, "travel", 2)
    assert merged["npcs"][0]["stance"] == "ally"


def test_build_block_renders_nonzero_only():
    assert rc.build_relationship_block(None) == ""
    assert rc.build_relationship_block({"relationship_vectors": [
        {"name": "X", "trust": 0, "loyalty": 0, "fear": 0, "resentment": 0, "state": "neutral"}]}) == ""
    block = rc.build_relationship_block({"relationship_vectors": [
        {"name": "Garrett", "trust": 40, "loyalty": 65, "fear": 5, "resentment": 10, "state": "devoted"}]})
    assert "relationships" in block and "Garrett" in block and "trust 40" in block
