from __future__ import annotations

import copy
import json
import re
from typing import Any, Dict, List

import ai_config
import gravity_governance

from memory import (
    PROMPT_REGISTRY_CAPS,
    enforce_context_budget,
    estimate_messages_tokens,
)


_PRIOR_STATE_RE = re.compile(
    r"<prior_state>\s*([\s\S]*?)\s*</prior_state>",
    re.IGNORECASE,
)


def _prior_state_from_final_user(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    match = _PRIOR_STATE_RE.search(messages[-1]["content"])
    assert match, messages[-1]["content"]
    return json.loads(match.group(1))


def _growth_rows(prefix: str, count: int) -> List[Dict[str, Any]]:
    return [
        {
            "object": f"{prefix} object {idx:03d}",
            "status": "stored",
            "where": f"old room {idx:03d}",
            "turn": idx,
            "notes": "stable historical spatial fact",
        }
        for idx in range(count)
    ]


def _live_growth_state() -> Dict[str, Any]:
    object_locations = _growth_rows("registry", 120)
    object_locations[2] = {
        "object": "field radio",
        "status": "carried",
        "where": "player pack",
        "turn": 3,
        "notes": "active current tool",
    }
    object_locations[7] = {
        "object": "sealed vault door",
        "status": "destroyed",
        "where": "north concourse",
        "turn": 7,
        "notes": "terminal physical truth",
    }

    inventory_objects = [
        {
            "object": f"cached supply {idx:03d}",
            "location_state": "stored",
            "turn": idx,
        }
        for idx in range(90)
    ]
    inventory_objects[4] = {
        "object": "flare pistol",
        "location_state": "carried",
        "turn": 4,
    }

    known_rooms = [
        {
            "key": f"old room {idx:03d}",
            "objects": [f"cached supply {idx:03d}"],
            "last_visited_turn": idx,
        }
        for idx in range(52)
    ]
    known_rooms[5] = {
        "key": "current platform",
        "objects": ["field radio"],
        "last_visited_turn": 21,
        "current": True,
    }

    npc_memory = [
        {
            "name": f"witness {idx:03d}",
            "remembers": [
                {
                    "event": f"minor market exchange {idx:03d}",
                    "severity": "minor",
                    "since_turn": idx,
                }
            ],
            "goal": "stay out of trouble",
        }
        for idx in range(64)
    ]
    npc_memory[3] = {
        "name": "Mira",
        "remembers": [
            {
                "event": "player promised to bring medicine",
                "severity": "major",
                "since_turn": 3,
            }
        ],
        "next_move": "search for the player near the checkpoint",
    }
    npc_memory[10] = {
        "name": "Vale",
        "remembers": [
            {
                "event": "player betrayed the guard patrol",
                "severity": "major",
                "since_turn": 10,
            }
        ],
    }

    return {
        "scene": "current platform under floodlights",
        "current_objective": "reach the generator room before water rises",
        "objectives": ["restore generator access"],
        "active_consequences": [
            {"id": "consequence-active", "status": "active", "text": "water rising"}
        ],
        "delayed_consequences": [
            {"id": "delay-open", "status": "pending", "turn": 23}
        ],
        "active_threats": [{"id": "threat-active", "status": "active"}],
        "promises": [{"id": "promise-medicine", "status": "open"}],
        "clues": [{"id": "clue-generator-code", "status": "unresolved"}],
        "active_pressures": ["water rising", "generator failing"],
        "relationship_vectors": [
            {
                "name": "Mira",
                "trust": 2,
                "loyalty": 1,
                "fear": 0,
                "resentment": 0,
            }
        ],
        "relationship_threads": [
            {"name": "Mira", "thread": "medicine promise remains open"}
        ],
        "object_locations": object_locations,
        "inventory_objects": inventory_objects,
        "known_rooms": known_rooms,
        "npc_memory": npc_memory,
        "recent_beats": [f"beat {idx}" for idx in range(20)],
        "recent_choice_signatures": [f"choice {idx}" for idx in range(20)],
        "archived": [{"old": idx} for idx in range(80)],
    }


def _messages_for_state(rolling_state: Dict[str, Any]) -> List[Dict[str, str]]:
    prior = json.dumps(rolling_state, indent=2, ensure_ascii=False)
    return [
        {"role": "system", "content": "system prompt " + ("x" * 500)},
        {
            "role": "user",
            "content": f"<prior_state>\n{prior}\n</prior_state>\n\nPlayer action: move.",
        },
    ]


def test_over_budget_prior_state_projection_caps_prompt_only_registries():
    rolling_state = _live_growth_state()
    persisted_snapshot = copy.deepcopy(rolling_state)
    messages = _messages_for_state(rolling_state)
    before_tokens = estimate_messages_tokens(messages)
    budget = 5000

    trimmed, diag = enforce_context_budget(
        messages,
        budget_tokens=budget,
        protected_recent_msgs=0,
    )
    projected = _prior_state_from_final_user(trimmed)

    assert rolling_state == persisted_snapshot
    assert len(rolling_state["object_locations"]) == 120
    assert len(rolling_state["inventory_objects"]) == 90
    assert len(rolling_state["known_rooms"]) == 52
    assert len(rolling_state["npc_memory"]) == 64

    assert diag["context_trimmed"] is True
    assert diag["compressed_prior_state"] is True
    assert diag["estimated_prompt_tokens"] <= budget
    assert diag["estimated_tokens_removed"] == before_tokens - diag["estimated_prompt_tokens"]
    assert "compressed_prior_state" in diag["trim_reason"]

    caps = diag["projected_registry_caps"]
    for key, cap in PROMPT_REGISTRY_CAPS.items():
        assert len(projected[key]) <= cap
        assert caps[key]["kept"] == len(projected[key])
        assert caps[key]["elided"] > 0

    assert projected["active_consequences"] == rolling_state["active_consequences"]
    assert projected["delayed_consequences"] == rolling_state["delayed_consequences"]
    assert projected["active_threats"] == rolling_state["active_threats"]
    assert projected["promises"] == rolling_state["promises"]
    assert projected["clues"] == rolling_state["clues"]
    assert projected["active_pressures"] == rolling_state["active_pressures"]
    assert projected["relationship_vectors"] == rolling_state["relationship_vectors"]
    assert projected["relationship_threads"] == rolling_state["relationship_threads"]
    assert projected["current_objective"] == rolling_state["current_objective"]

    projected_objects = {row["object"] for row in projected["object_locations"]}
    assert "field radio" in projected_objects
    assert "sealed vault door" in projected_objects

    projected_inventory = {row["object"] for row in projected["inventory_objects"]}
    assert "flare pistol" in projected_inventory

    projected_rooms = {row["key"] for row in projected["known_rooms"]}
    assert "current platform" in projected_rooms

    projected_npcs = {row["name"] for row in projected["npc_memory"]}
    assert {"Mira", "Vale"} <= projected_npcs

    trimmed_again, diag_again = enforce_context_budget(
        _messages_for_state(copy.deepcopy(persisted_snapshot)),
        budget_tokens=budget,
        protected_recent_msgs=0,
    )
    assert trimmed_again[-1]["content"] == trimmed[-1]["content"]
    assert diag_again == diag


def _trait_projection_state() -> Dict[str, Any]:
    return {
        "scene": "loc-town",
        "npc_memory": [
            {
                "name": f"NPC {idx:02d}",
                "remembers": [
                    {
                        "severity": "minor",
                        "event": f"routine market note {idx:02d}",
                        "since_turn": idx,
                    }
                ],
            }
            for idx in range(19)
        ]
        + [
            {
                "name": "Mara",
                "remembers": [
                    {
                        "severity": "minor",
                        "event": "quiet supply concern at the water cache",
                        "since_turn": 19,
                    }
                ],
            }
        ],
        "recent_beats": [f"beat {idx}" for idx in range(40)],
        "recent_choice_signatures": [f"choice {idx}" for idx in range(40)],
        "archived": [{"old": idx, "text": "x" * 120} for idx in range(80)],
    }


def _matching_trait_refs() -> Dict[str, Any]:
    return {
        "npc_refs": {
            "version": 1,
            "by_npc_id": {
                "npc-mara": {
                    "ambition": "high",
                    "fear": "scarcity",
                    "loyalty_anchor": "player",
                    "personal_stakes": "survival",
                    "risk_tolerance": "high",
                    "pressure_sensitivity": "high",
                    "social_role": "leader",
                    "display_name": "Mara",
                }
            },
        },
        "settlement_refs": {
            "version": 1,
            "by_location_id": {
                "loc-town": {
                    "dominant_pressure": "resource",
                    "local_stakes": "supply",
                    "prosperity": "low",
                    "stability": "low",
                    "crime": "high",
                }
            },
        },
    }


def test_trait_projection_refs_absent_or_empty_preserve_projection(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    messages = _messages_for_state(_trait_projection_state())
    base_trimmed, base_diag = enforce_context_budget(
        messages,
        budget_tokens=1200,
        protected_recent_msgs=0,
    )
    empty_trimmed, empty_diag = enforce_context_budget(
        _messages_for_state(_trait_projection_state()),
        budget_tokens=1200,
        protected_recent_msgs=0,
        npc_trait_refs={"version": 1, "by_npc_id": {}},
        settlement_trait_refs={"version": 1, "by_location_id": {}},
        location_ref="loc-town",
    )

    assert empty_trimmed == base_trimmed
    assert empty_diag == base_diag


def test_passive_default_trait_refs_preserve_projection(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    passive_npc_refs = {
        "version": 1,
        "by_npc_id": {
            "npc-mara": {
                "ambition": "medium",
                "fear": "injury",
                "loyalty_anchor": "unknown",
                "personal_stakes": "unknown",
                "risk_tolerance": "medium",
                "pressure_sensitivity": "medium",
                "social_role": "unknown",
                "display_name": "Mara",
            }
        },
    }
    passive_settlement_refs = {
        "version": 1,
        "by_location_id": {
            "loc-town": {
                "dominant_pressure": "unknown",
                "local_stakes": "unknown",
                "prosperity": "medium",
                "stability": "medium",
                "crime": "medium",
            }
        },
    }

    base_trimmed, base_diag = enforce_context_budget(
        _messages_for_state(_trait_projection_state()),
        budget_tokens=1200,
        protected_recent_msgs=0,
    )
    passive_trimmed, passive_diag = enforce_context_budget(
        _messages_for_state(_trait_projection_state()),
        budget_tokens=1200,
        protected_recent_msgs=0,
        npc_trait_refs=passive_npc_refs,
        settlement_trait_refs=passive_settlement_refs,
        location_ref="loc-town",
    )

    assert passive_trimmed == base_trimmed
    assert passive_diag == base_diag


def test_matching_traits_can_change_prompt_projection_priority_with_same_shape(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    refs = _matching_trait_refs()

    base_trimmed, base_diag = enforce_context_budget(
        _messages_for_state(_trait_projection_state()),
        budget_tokens=1200,
        protected_recent_msgs=0,
    )
    trait_trimmed, trait_diag = enforce_context_budget(
        _messages_for_state(_trait_projection_state()),
        budget_tokens=1200,
        protected_recent_msgs=0,
        npc_trait_refs=refs["npc_refs"],
        settlement_trait_refs=refs["settlement_refs"],
        location_ref="loc-town",
    )
    base_projected = _prior_state_from_final_user(base_trimmed)
    trait_projected = _prior_state_from_final_user(trait_trimmed)

    assert "Mara" not in {row["name"] for row in base_projected["npc_memory"]}
    assert "Mara" in {row["name"] for row in trait_projected["npc_memory"]}
    assert len(base_projected["npc_memory"]) == len(trait_projected["npc_memory"])
    assert set(base_projected.keys()) == set(trait_projected.keys())
    assert [set(row.keys()) for row in base_projected["npc_memory"]] == [
        set(row.keys()) for row in trait_projected["npc_memory"]
    ]
    assert set(base_diag["projected_registry_caps"]["npc_memory"]) == set(
        trait_diag["projected_registry_caps"]["npc_memory"]
    )
    assert "npc_traits" not in trait_trimmed[-1]["content"]
    assert "settlement_traits" not in trait_trimmed[-1]["content"]

    modifier = gravity_governance.trait_significance_modifier(
        _trait_projection_state()["npc_memory"][-1],
        npc_trait_refs=refs["npc_refs"],
        settlement_trait_refs=refs["settlement_refs"],
        location_ref="loc-town",
    )
    assert 0 < modifier["gravity"] <= gravity_governance.MAX_TRAIT_GRAVITY_MODIFIER
    assert 0 <= modifier["connectivity"] <= gravity_governance.MAX_TRAIT_CONNECTIVITY_MODIFIER
