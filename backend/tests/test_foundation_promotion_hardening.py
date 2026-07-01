"""
Foundation Completion Phase 2 — verification & hardening regression tests.

Formalises the turn-/integration-level guarantees the original promotion suite
did not assert directly:

  • full-turn replay determinism across the ENTIRE promotion flag matrix,
  • full-turn rollback to the all-flags-OFF baseline (no state migration),
  • Gravity never mutates its input (persisted-state proxy),
  • Memory Retrieval stays byte-identical (shadow-locked) when its flag flips,
  • integration diagnostics expose the complete promotion picture,
  • foundation_authority() compact per-subsystem authority summary.

All offline & deterministic — no live LLM, no MongoDB.
"""
from __future__ import annotations

import copy
import itertools
import json

import pytest

import ai_config
import foundation_integration as fi
import foundation_promotion as fp
import memory
import replayability
from engine_determinism import canonical_json

SEED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_PROMO_FLAGS = (
    "ENABLE_CANONICAL_ACTOR_RESOLUTION",
    "ENABLE_CANONICAL_GRAVITY",
    "ENABLE_CANONICAL_UTILITY",
    "ENABLE_CANONICAL_MEMORY_RETRIEVAL",
)
_ALL_COMBOS = list(itertools.product([False, True], repeat=len(_PROMO_FLAGS)))


def _set_flags(monkeypatch, combo):
    for name, value in zip(_PROMO_FLAGS, combo):
        monkeypatch.setattr(ai_config, name, value)


def _fresh_state():
    state, _ = replayability.init_new_story(
        genre="horror", role="survivor", tone="dark", difficulty="hard",
        scenario_id=None, custom_premise=None, custom_world_setup=None, run_seed=SEED,
    )
    return state


def _turn_fingerprint(base_state):
    out = replayability.prepare_action_turn(copy.deepcopy(base_state), 2)
    return canonical_json(json.loads(json.dumps(out, default=str)))


# --- Objective 2: deterministic replay across the entire flag matrix ---
@pytest.mark.parametrize("combo", _ALL_COMBOS)
def test_turn_is_deterministic_under_every_flag_combo(monkeypatch, combo):
    base = _fresh_state()
    _set_flags(monkeypatch, combo)
    assert _turn_fingerprint(base) == _turn_fingerprint(base)


# --- Objective 3: rollback restores the all-OFF baseline with no residue ---
def test_all_off_is_stable_baseline(monkeypatch):
    base = _fresh_state()
    _set_flags(monkeypatch, (False, False, False, False))
    assert _turn_fingerprint(base) == _turn_fingerprint(base)


@pytest.mark.parametrize("idx", range(len(_PROMO_FLAGS)))
def test_single_flag_rollback_restores_baseline(monkeypatch, idx):
    base = _fresh_state()
    _set_flags(monkeypatch, (False, False, False, False))
    baseline = _turn_fingerprint(base)
    combo = [False] * len(_PROMO_FLAGS)
    combo[idx] = True
    _set_flags(monkeypatch, tuple(combo))
    _turn_fingerprint(base)  # promoted turn (may legitimately differ)
    _set_flags(monkeypatch, (False, False, False, False))  # rollback
    assert _turn_fingerprint(base) == baseline


# --- Objective 4: Gravity never mutates its input (persisted-state proxy) ---
def _npc_row(name, *, major=False, count=1):
    sev = "major" if major else "minor"
    return {
        "name": name,
        "remembers": [
            {"severity": sev, "event": f"{name} e{i}", "since_turn": i}
            for i in range(count)
        ],
    }


def test_gravity_cap_does_not_mutate_input(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    items = [_npc_row(f"npc{i}", major=(i in {0, 1}), count=1 + (i % 2)) for i in range(6)]
    before = copy.deepcopy(items)
    capped, meta = memory._cap_prompt_registry("npc_memory", items, 3)
    assert meta["ranker"] == "gravity_governance"
    assert len(capped) == 3  # count == cap
    assert items == before  # input list & rows unchanged (State Is Truth)
    assert all(any(c is it for it in items) for c in capped)  # references, no copies


# --- Objective 6: Memory flag flip leaves retrieval byte-identical (shadow-locked) ---
def _eval(**over):
    kw = dict(
        run_seed="seed-xyz",
        turn_sequence=3,
        rolling_state={"npcs": [{"name": "Mara", "stance": "ally"}, {"name": "Bran", "stance": "rival"}]},
        replayability_state={"run_seed": "seed-xyz"},
    )
    kw.update(over)
    return fi.evaluate_foundation_turn(**kw)


def test_memory_flag_does_not_change_prompt_bundle(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_MEMORY_RETRIEVAL", False)
    b_off, _ = _eval()
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_MEMORY_RETRIEVAL", True)
    b_on, d_on = _eval()
    assert b_off["retrieval"]["state_hash"] == b_on["retrieval"]["state_hash"]
    assert b_off["prepared_bytes"] == b_on["prepared_bytes"]
    assert b_on["retrieval"]["shadow_mode"] is True
    mrp = d_on["memory_retrieval_promotion"]
    assert mrp["memory_retrieval_prompt_injection_allowed"] is False
    assert mrp["memory_retrieval_blocker_code"] == "SEPARATE_SHADOW_ACCEPTANCE_REQUIRED"


# --- Objective 5: integration diagnostics expose the complete promotion picture ---
def test_integration_diag_is_complete(monkeypatch):
    _, diag = _eval()
    assert diag["foundation_promotion_flags"] == fp.promotion_flags()
    assert set(diag["foundation_authority"]) == {"actor", "gravity", "utility", "memory"}
    mrp = diag["memory_retrieval_promotion"]
    for key in (
        "memory_retrieval_enabled",
        "memory_retrieval_prompt_injection_allowed",
        "memory_retrieval_blocker_code",
        "memory_retrieval_shadow_mode",
        "memory_retrieval_canonical_selected_ids",
    ):
        assert key in mrp


# --- Objective 7: foundation_authority() reflects flag state precisely ---
def test_foundation_authority_all_off_is_legacy(monkeypatch):
    for name in _PROMO_FLAGS:
        monkeypatch.setattr(ai_config, name, False)
    assert fp.foundation_authority() == {
        "actor": "legacy", "gravity": "legacy", "utility": "legacy", "memory": "legacy",
    }


def test_foundation_authority_flags_promote_each_subsystem(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", True)
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_UTILITY", True)
    a = fp.foundation_authority()
    assert a["actor"] == "canonical"
    assert a["gravity"] == "canonical"
    assert a["utility"] == "canonical"


def test_foundation_authority_memory_never_canonical_until_accepted(monkeypatch):
    # Flag ON alone keeps memory shadow-only — it never feeds the prompt.
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_MEMORY_RETRIEVAL", True)
    assert fp.foundation_authority()["memory"] == "shadow_diagnostics"
    # Only granting the acceptance constant flips it to canonical.
    monkeypatch.setattr(ai_config, "CANONICAL_MEMORY_RETRIEVAL_PROMPT_INJECTION_ACCEPTED", True)
    assert fp.foundation_authority()["memory"] == "canonical"
