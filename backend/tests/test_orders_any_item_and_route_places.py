"""Standing orders can hand over any item in any setting, and a route leads only to a place the engine lists."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import order_engine  # noqa: E402
import route_engine  # noqa: E402
from play_facts import Context, MoveError  # noqa: E402

BAY = "the cargo bay"
BRIDGE = "the bridge"


def station(*, vex_inv=("plasma cutter", "encrypted data chip"), orin_at=BRIDGE):
    return {
        "scene": BAY, "location": BAY,
        "npcs": [
            {"name": "Vex Taro", "npc_id": "npc-vex", "location": BAY, "inventory": list(vex_inv), "stance": "neutral"},
            {"name": "Orin Hale", "npc_id": "npc-orin", "location": orin_at, "inventory": [], "stance": "neutral"},
        ],
        "relationship_vectors": [{"name": "Vex Taro", "trust": 60}], "deceased": [],
    }


def _vex(rolling):
    return rolling["npcs"][0]


@pytest.mark.parametrize("text,item", [
    ("When Orin Hale arrives, give him the encrypted data chip.", "encrypted data chip"),
    ("When Orin Hale arrives, hand the data chip over to Orin.", "data chip"),
    ("Pass my plasma cutter to Orin Hale when Orin Hale arrives.", "plasma cutter"),
    ("When Orin Hale arrives, hand him the parcel.", "parcel"),
])
def test_an_order_can_name_any_item_in_any_setting(text, item):
    rolling = station()
    parsed = order_engine.parse(text, rolling, None, _vex(rolling))
    assert parsed["can_commit"], parsed["issues"]
    assert parsed["_action"] == {"kind": "deliver_item", "item": item, "target": {"id": "npc-orin", "name": "Orin Hale"},
                                 "summary": f"hand the {item} to Orin Hale"}
    assert parsed["understood"]["action"] == f"hand the {item} to Orin Hale"


def test_a_preview_never_says_whether_the_person_carries_the_item():
    rolling = station()
    has = order_engine.parse("When Orin Hale arrives, give him the encrypted data chip.", rolling, None, _vex(rolling))
    lacks = order_engine.parse("When Orin Hale arrives, give him the royal seal.", rolling, None, _vex(rolling))
    assert has["can_commit"] and lacks["can_commit"]
    strip = lambda notes, item: [n.replace(item, "ITEM") for n in notes]  # noqa: E731
    assert strip(has["notes"], "encrypted data chip") == strip(lacks["notes"], "royal seal")
    assert not any("has the" in n or "not carrying" in n for n in has["notes"] + lacks["notes"])


def test_a_handover_needs_an_item_and_someone_to_receive_it():
    rolling = station()
    no_item = order_engine.parse("When Orin Hale arrives, give it to Orin Hale.", rolling, None, _vex(rolling))
    assert not no_item["can_commit"] and "what should be handed over" in " ".join(no_item["issues"])
    stranger = order_engine.parse("When Orin Hale arrives, give the data chip to Zed.", rolling, None, _vex(rolling))
    assert not stranger["can_commit"] and "Zed" in " ".join(stranger["issues"])
    nonsense = order_engine.parse("When Orin Hale arrives, sing loudly.", rolling, None, _vex(rolling))
    assert not nonsense["can_commit"] and nonsense["understood"] is None


def _run(text, **kw):
    rolling = station(**kw)
    state, order = order_engine.record_order(None, rolling, turn=2, request_id="req-1", recipient_ref="Vex Taro", text=text)
    assert order["status"] == "pending"
    rolling["npcs"][1]["location"] = BAY                      # Orin arrives
    state, _ = order_engine.tick(state, rolling, 3)
    order_engine.project(state, rolling)
    return state["orders"][0], rolling


def test_the_named_item_changes_hands_when_the_person_arrives_and_only_that_item():
    order, rolling = _run("When Orin Hale arrives, give him the data chip.")
    assert order["status"] == "done" and order["effect"] == {"kind": "item_given", "item": "encrypted data chip", "from": "npc-vex", "to": "npc-orin"}
    assert rolling["npcs"][0]["inventory"] == ["plasma cutter"] and rolling["npcs"][1]["inventory"] == ["encrypted data chip"]
    assert order_engine._result_line(order) == "Vex Taro handed the data chip to Orin Hale."


def test_without_the_item_nothing_changes_hands():
    order, rolling = _run("When Orin Hale arrives, give him the royal seal.")
    assert order["status"] == "no_means" and "effect" not in order
    assert rolling["npcs"][0]["inventory"] == ["plasma cutter", "encrypted data chip"] and rolling["npcs"][1]["inventory"] == []


def test_an_order_saved_before_delivery_covered_any_item_still_resolves():
    rolling = station(vex_inv=("plasma cutter", "sealed parcel"))
    state, order = order_engine.record_order(None, rolling, turn=2, request_id="req-1", recipient_ref="Vex Taro",
                                             text="When Orin Hale arrives, hand him the parcel.")
    order["action"] = {"kind": "deliver_parcel", "target": {"id": "npc-orin", "name": "Orin Hale"}, "summary": "hand the parcel to Orin Hale"}
    rolling["npcs"][1]["location"] = BAY
    state, _ = order_engine.tick(state, rolling, 3)
    done = state["orders"][0]
    assert done["status"] == "done" and done["effect"]["item"] == "sealed parcel"
    assert order_engine._result_line(done) == "Vex Taro handed the parcel to Orin Hale."
    old_effect = {**done, "effect": {**done["effect"], "kind": "parcel_given"}}
    assert order_engine._result_line(old_effect) == "Vex Taro handed the parcel to Orin Hale."


def _ctx():
    return Context(session={}, rolling={"location": "the lobby", "scene": "the lobby", "known_rooms": ["the boiler room"], "locations": []},
                   rows=[{"turn_number": 2, "paragraphs": ["A narrow stair winds down toward the wine cellar and the boiler room."]}],
                   ledger={"Carried": "torch"}, turn=3)


def test_a_route_leads_only_to_a_place_the_engine_lists():
    ctx = _ctx()
    assert route_engine._established(ctx, "the boiler room")
    assert not route_engine._established(ctx, "the wine cellar")          # named in prose only
    via = {"turn": 2, "paragraph": 0}
    with pytest.raises(MoveError) as refused:
        route_engine.apply({}, ctx, {"via": via, "to": "the wine cellar"}, turn=3, request_id="r-1")
    assert refused.value.status == 422 and "established" in refused.value.detail
    state, result = route_engine.apply({}, ctx, {"via": via, "to": "the boiler room"}, turn=3, request_id="r-2")
    assert state["route"]["routes"][0]["b"] == "the boiler room" and result["replayed"] is False
