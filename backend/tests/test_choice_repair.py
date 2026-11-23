"""Choice repair: a choice naming an unknown person is replaced, the turn is kept.

Before this change one such choice failed the whole turn: a retry, and when the
retry failed too, the fail-forward fallback. In the 2026-11-21 eval runs every
turn lost that way was a false positive (an established place name, or a capital
that only opened a sentence).
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scenario_coherence as sc  # noqa: E402
import server  # noqa: E402

# Two paragraphs: the default turn length shows 2 to 4, and a one-paragraph reply is now re-broken at delivery.
NARRATIVE = "Rain streaks the lane.\n\nYou clutch your satchel near the well."

PRIOR = {
    "scene": "small settlement lane",
    "character": "a weary scholar",
    "active_pressures": [{"id": "scar", "label": "scarcity", "status": "active"}],
    "inventory_objects": [{"object": "satchel"}],
    "object_locations": [{"object": "well", "location": "lane"}],
    "npcs": [{"name": "Mira", "alive": True}],
}

GOOD = {
    "A": "Check the well carefully",
    "B": "Ask Harwood for directions out of town",
    "C": "Watch Mira closely",
    "D": "Hold position and wait",
}


def _session(**over):
    base = {
        "id": "sess-repair",
        "genre": "fantasy",
        "role": "a scholar",
        "tone": "grim",
        "difficulty": "hard",
        "mode": "basic",
        "turn_count": 2,
        "last_state": {"Health": "stable", "Pressure": "scarcity", "Position": "lane"},
        "rolling_state": copy.deepcopy(PRIOR),
        "custom_world_setup": {
            "creationFlow": "guided",
            "want": "knowledge",
            "fear": "failure",
            "whoMatters": "nobody",
            "pressures": ["scarcity"],
            "startingLocation": "small_settlement",
            "worldExclusions": "firearms",
            "settingGroundedness": "mostly_grounded",
        },
    }
    base.update(over)
    return base


def _raw(choices=None, rolling=None, narrative=NARRATIVE):
    choices = choices or GOOD
    choice_block = "\n".join(f"{label}. {text}" for label, text in choices.items())
    return (
        f"<rolling_state>{json.dumps(rolling if rolling is not None else PRIOR)}</rolling_state>\n"
        f"<narrative>\n{narrative}\n</narrative>\n"
        f"<paragraphs><p>{narrative}</p></paragraphs>\n"
        f"<choices>\n{choice_block}\n</choices>\n"
        "<state>\nHealth: stable\nPressure: scarcity\nPosition: lane\n</state>\n"
        "<ledger>\nCarried: satchel\n</ledger>\n"
    )


def _fail(raw, session=None):
    session = session or _session()
    parsed = server.parse_turn(raw)
    ok, reason, kind = server._full_validate(parsed, session, "ask around", early_game_stage=None)
    return parsed, session, ok, reason, kind


def _repair(raw, session=None, *, kind=None, reason=None):
    parsed, session, ok, why, k = _fail(raw, session)
    assert not ok
    return server._repair_unknown_person_choices(
        parsed, raw, session, "ask around", None, kind or k, reason or why
    )


def test_repair_replaces_only_the_bad_choice_and_keeps_the_turn():
    raw = _raw()
    parsed, session, ok, reason, kind = _fail(raw)
    assert (ok, kind) == (False, "coherence")
    assert reason.startswith(sc.UNKNOWN_PERSON_REASON_PREFIX) and "Harwood" in reason

    result = server._repair_unknown_person_choices(
        parsed, raw, session, "ask around", None, kind, reason
    )
    assert result is not None
    repaired, new_raw, note = result
    assert note == "B:Harwood"
    assert [c["label"] for c in repaired.choices] == ["A", "B", "C", "D"]
    assert repaired.choices[0]["text"] == GOOD["A"]
    assert repaired.choices[2]["text"] == GOOD["C"]
    assert repaired.choices[3]["text"] == GOOD["D"]
    assert repaired.choices[1]["text"] == "Look over the scene again for anything you missed"
    assert repaired.narrative == parsed.narrative
    assert repaired.rolling_state == parsed.rolling_state
    assert "Harwood" not in new_raw and "Harwood" not in repaired.raw
    assert NARRATIVE in new_raw
    ok2, why2, _ = server._full_validate(repaired, session, "ask around", early_game_stage=None)
    assert ok2, why2


def test_repair_declines_when_too_many_choices_are_bad():
    raw = _raw(
        {
            "A": "Follow Harwood into the trees",
            "B": "Ask Brannock for directions",
            "C": "Trade with Selwyn at the gate",
            "D": "Hold position and wait",
        }
    )
    assert _repair(raw) is None


def test_repair_declines_when_the_name_is_also_in_the_models_state():
    # The person would enter the story without ever being shown to the player.
    rolling = copy.deepcopy(PRIOR)
    rolling["npcs"].append({"name": "Harwood", "alive": True})
    assert _repair(_raw(rolling=rolling)) is None


def test_repair_declines_on_openings():
    raw = _raw()
    parsed = server.parse_turn(raw)
    session = _session(turn_count=0)
    reason = f"{sc.UNKNOWN_PERSON_REASON_PREFIX} 'Harwood' before narrative/state introduction"
    assert server._repair_unknown_person_choices(
        parsed, raw, session, None, None, "coherence", reason
    ) is None


def test_repair_declines_for_other_failure_kinds():
    raw = _raw()
    parsed, session, *_ = _fail(raw)
    reason = f"{sc.UNKNOWN_PERSON_REASON_PREFIX} 'Harwood' before narrative/state introduction"
    assert server._repair_unknown_person_choices(
        parsed, raw, session, "ask around", None, "format", reason
    ) is None
    assert server._repair_unknown_person_choices(
        parsed, raw, session, "ask around", None, "coherence", "choice uses excluded technology"
    ) is None


def test_repair_declines_when_the_repaired_turn_still_fails():
    # The unknown person is fixable; the firearm choice is not, so the normal
    # retry and fallback path must still run.
    raw = _raw(
        {
            "A": "Check the well carefully",
            "B": "Ask Harwood for directions out of town",
            "C": "Fire the shotgun at the crowd",
            "D": "Hold position and wait",
        }
    )
    assert _repair(raw) is None


def _run_turn(session, first_raw, second_raw=None):
    calls = {"generate": 0, "invoke": 0}

    async def fake_generate(*_a, **_k):
        calls["generate"] += 1
        return first_raw, {
            "model_used": "test-model",
            "model_requested": "test-model",
            "telemetry": {},
            "fallback_events": [],
            "prose_mode": "standard",
            "prose_mode_requested": "standard",
            "prose_budget": 1200,
        }

    async def fake_invoke(**_k):
        calls["invoke"] += 1
        return {
            "content": second_raw,
            "model_used": "test-model",
            "model_requested": "test-model",
            "telemetry": {},
            "fallback_events": [],
            "attempts_per_model": {"test-model": 1},
        }

    async def fake_messages(*_a, **_k):
        return [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}]

    async def fake_settings():
        return {
            "model": "test-model",
            "default_mode": "basic",
            "memory_depth": 4,
            "history_window": 6,
            "cost_mode": "normal",
            "max_tokens": 800,
            "temperature": 0.7,
            "developer_mode": False,
        }

    import gateway as _gw

    orig = (server._generate_turn, _gw.invoke_llm, server._build_messages, server.get_ai_settings)
    server._generate_turn = fake_generate
    _gw.invoke_llm = fake_invoke
    server._build_messages = fake_messages
    server.get_ai_settings = fake_settings
    try:
        parsed, raw, meta = asyncio.run(
            server._generate_validated_turn(
                session, "[DEV_MODE: OFF]\n\nPlayer action: ask around", player_action="ask around"
            )
        )
    finally:
        (server._generate_turn, _gw.invoke_llm, server._build_messages, server.get_ai_settings) = orig
    return parsed, raw, meta, calls


def test_unknown_person_choice_keeps_the_turn_without_a_retry():
    parsed, raw, meta, calls = _run_turn(_session(), _raw())
    assert calls == {"generate": 1, "invoke": 0}
    assert meta.get("validation_choice_repair") == "B:Harwood"
    assert not meta.get("validation_retried")
    assert not meta.get("validation_hard_fallback")
    assert parsed.paragraphs == NARRATIVE.split("\n\n")
    assert "Harwood" not in " ".join(c["text"] for c in parsed.choices)
    assert "Harwood" not in raw
    assert server._meta_into_debug({}, meta)["validation_choice_repair"] == "B:Harwood"


def test_retry_output_with_a_bad_choice_is_repaired_too():
    first = _raw({"A": "Check the well carefully", "B": "Watch Mira closely"})  # only two choices
    parsed, raw, meta, calls = _run_turn(_session(), first, _raw())
    assert calls == {"generate": 1, "invoke": 1}
    assert meta.get("validation_retried") is True
    assert meta.get("validation_second_fail") is None
    assert meta.get("validation_choice_repair") == "B:Harwood"
    assert not meta.get("validation_hard_fallback")
    assert "Harwood" not in " ".join(c["text"] for c in parsed.choices)
