"""
Deterministic tests for the Foundation Completion Phase 2 promotion layer.

Covers the acceptance matrix: feature flags, promotion path, fallback path,
replay determinism / identical seeds, divergence reporting, rollback behaviour,
prompt stability, context-budget stability, and leakage protection. All offline
and deterministic — no live LLM, no MongoDB.
"""
from __future__ import annotations

import pytest

import ai_config
import foundation_promotion as fp
import memory


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------
def test_promotion_defaults_keep_utility_live():
    # Utility is accepted for the beta path; remaining promotions stay opt-in.
    assert ai_config.ENABLE_CANONICAL_ACTOR_RESOLUTION is False
    assert ai_config.ENABLE_CANONICAL_GRAVITY is False
    assert ai_config.ENABLE_CANONICAL_UTILITY is True
    assert ai_config.ENABLE_CANONICAL_MEMORY_RETRIEVAL is False
    assert ai_config.CANONICAL_MEMORY_RETRIEVAL_PROMPT_INJECTION_ACCEPTED is False
    assert fp.promotion_flags() == {
        "actor_resolution": False,
        "gravity": False,
        "utility": True,
        "memory_retrieval": False,
        "memory_retrieval_prompt_injection_allowed": False,
    }


def test_utility_live_reads_canonical_or_legacy_alias(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_UTILITY_AI_LIVE_SELECTION", False)
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_UTILITY", False)
    assert fp.utility_live_enabled() is False
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_UTILITY", True)
    assert fp.utility_live_enabled() is True
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_UTILITY", False)
    monkeypatch.setattr(ai_config, "ENABLE_UTILITY_AI_LIVE_SELECTION", True)
    assert fp.utility_live_enabled() is True


# ---------------------------------------------------------------------------
# Stage 1 — Actor Resolution routing
# ---------------------------------------------------------------------------
def _actor_prepared(tiers_by_name):
    return {
        "referenceable_registry": [
            {"display_name": name, "tier": tier} for name, tier in tiers_by_name.items()
        ]
    }


def _move(npc_id, name, agenda="ag", kind="observe", target="p1", receipt="r1"):
    row = {
        "npc_id": npc_id,
        "display_name": name,
        "agenda_id": agenda,
        "move_kind": kind,
        "target_id": target,
        "target_type": "player",
    }
    if receipt is not None:
        row["receipt_id"] = receipt
    return row


def test_actor_route_disabled_returns_legacy_unchanged():
    legacy = _move("n1", "Mara")
    prepared = _actor_prepared({"Mara": "dormant"})
    out, diag = fp.route_actor_move(legacy, [], prepared, enabled=False)
    assert out == legacy
    assert diag["actor_resolution_enabled"] is False
    assert diag["actor_resolution_applied"] is False


def test_actor_route_keeps_acting_legacy():
    legacy = _move("n1", "Mara")
    prepared = _actor_prepared({"Mara": "active"})
    out, diag = fp.route_actor_move(legacy, [], prepared, enabled=True)
    assert out == legacy
    assert diag["actor_resolution_applied"] is True
    assert diag["actor_resolution_changed"] is False
    assert diag["actor_resolution_legacy_canonical_tier"] == "active"


def test_actor_route_unmapped_legacy_fails_open():
    # Mapping gap must NOT suppress — fail open to the legacy pick.
    legacy = _move("n1", "Ghost")
    prepared = _actor_prepared({"Mara": "active"})
    out, diag = fp.route_actor_move(legacy, [], prepared, enabled=True)
    assert out == legacy
    assert diag["actor_resolution_changed"] is False
    assert diag["actor_resolution_legacy_canonical_tier"] == "unmapped"


def test_actor_route_vetoes_nonacting_and_repicks():
    legacy = _move("n1", "Mara")  # canonical dormant -> vetoed
    candidate = _move("n2", "Bran", receipt=None)  # canonical active -> repick
    prepared = _actor_prepared({"Mara": "dormant", "Bran": "active"})
    out, diag = fp.route_actor_move(legacy, [legacy, candidate], prepared, enabled=True)
    assert out is not None
    assert out["npc_id"] == "n2"
    assert diag["actor_resolution_changed"] is True
    assert diag["actor_resolution_reason"] == "legacy_actor_non_acting"
    assert diag["actor_resolution_authoritative_actor"] == "n2"


def test_actor_route_vetoes_with_no_acting_candidate_suppresses():
    legacy = _move("n1", "Mara")
    prepared = _actor_prepared({"Mara": "archived"})
    out, diag = fp.route_actor_move(legacy, [legacy], prepared, enabled=True)
    assert out is None
    assert diag["actor_resolution_reason"] == "no_acting_candidate"


def test_actor_route_error_fails_closed_to_legacy():
    legacy = _move("n1", "Mara")
    # referenceable_registry as a non-iterable forces an internal error.
    broken = {"referenceable_registry": 123}
    out, diag = fp.route_actor_move(legacy, [], broken, enabled=True)
    assert out == legacy
    assert "actor_resolution_error" in diag
    assert diag["actor_resolution_applied"] is False


def test_actor_route_deterministic():
    legacy = _move("n1", "Mara")
    candidate = _move("n2", "Bran", receipt=None)
    prepared = _actor_prepared({"Mara": "dormant", "Bran": "active"})
    a = fp.route_actor_move(legacy, [legacy, candidate], prepared, enabled=True)
    b = fp.route_actor_move(legacy, [legacy, candidate], prepared, enabled=True)
    assert a == b


def test_actor_route_rollback_restores_legacy(monkeypatch):
    legacy = _move("n1", "Mara")
    candidate = _move("n2", "Bran", receipt=None)
    prepared = _actor_prepared({"Mara": "dormant", "Bran": "active"})
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", True)
    on, _ = fp.route_actor_move(legacy, [legacy, candidate], prepared)
    assert on["npc_id"] == "n2"  # promoted
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_ACTOR_RESOLUTION", False)
    off, diag = fp.route_actor_move(legacy, [legacy, candidate], prepared)
    assert off == legacy  # rolled back to legacy
    assert diag["actor_resolution_applied"] is False


# ---------------------------------------------------------------------------
# Stage 2 — Gravity retention ordering
# ---------------------------------------------------------------------------
def _npc_row(name, *, major=False, count=1):
    sev = "major" if major else "minor"
    return {
        "name": name,
        "remembers": [
            {"severity": sev, "event": f"{name} event {i}", "since_turn": i}
            for i in range(count)
        ],
    }


def test_gravity_order_disabled_returns_none():
    order, diag = fp.order_npc_memory_by_gravity([_npc_row("A")], enabled=False)
    assert order is None
    assert diag["gravity_applied"] is False


def test_gravity_major_scores_above_base():
    major = fp.gravity_retention_score_for_npc_memory(_npc_row("A", major=True))
    base = fp.gravity_retention_score_for_npc_memory(_npc_row("B", major=False))
    assert major > base


def test_gravity_order_ranks_major_first_and_preserves_length():
    rows = [_npc_row("A"), _npc_row("B", major=True), _npc_row("C")]
    order, diag = fp.order_npc_memory_by_gravity(rows, enabled=True)
    assert diag["gravity_applied"] is True
    assert order[0] == 1  # the major row wins
    assert sorted(order) == [0, 1, 2]  # every index present exactly once


def test_gravity_order_stable_tie_by_index():
    rows = [_npc_row("A"), _npc_row("B"), _npc_row("C")]  # all equal score
    order, _ = fp.order_npc_memory_by_gravity(rows, enabled=True)
    assert order == [0, 1, 2]


def test_gravity_order_deterministic():
    rows = [_npc_row("A", major=True), _npc_row("B"), _npc_row("C", count=3)]
    assert fp.order_npc_memory_by_gravity(rows, enabled=True) == fp.order_npc_memory_by_gravity(
        rows, enabled=True
    )


def test_gravity_order_error_returns_none():
    order, diag = fp.order_npc_memory_by_gravity(123, enabled=True)  # type: ignore[arg-type]
    assert order is None
    assert "gravity_error" in diag


# ---------------------------------------------------------------------------
# Stage 2 — real seam: memory._cap_prompt_registry
# ---------------------------------------------------------------------------
def _npc_memory_items(n, major_indices):
    return [
        _npc_row(f"npc{i}", major=(i in major_indices), count=1 + (i % 2))
        for i in range(n)
    ]


def test_cap_npc_memory_off_is_legacy_path(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", False)
    items = _npc_memory_items(6, {0, 1})
    capped, meta = memory._cap_prompt_registry("npc_memory", items, 3)
    assert len(capped) == 3  # context-budget stability: count == cap
    assert "ranker" not in meta  # legacy path, gravity not engaged


def test_cap_npc_memory_on_uses_gravity_and_keeps_count(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    items = _npc_memory_items(6, {0, 1})
    capped, meta = memory._cap_prompt_registry("npc_memory", items, 3)
    assert len(capped) == 3  # budget preserved
    assert meta["ranker"] == "gravity_governance"
    assert meta["protected_kept"] == 2  # both major rows retained


def test_cap_npc_memory_gravity_deterministic(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    items = _npc_memory_items(8, {2, 5})
    assert memory._cap_prompt_registry("npc_memory", items, 4) == memory._cap_prompt_registry(
        "npc_memory", items, 4
    )


def test_cap_other_registry_ignores_gravity_flag(monkeypatch):
    # Gravity only governs npc_memory; object_locations must use the legacy path.
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_GRAVITY", True)
    items = [{"id": f"o{i}", "status": "loose"} for i in range(5)]
    _, meta = memory._cap_prompt_registry("object_locations", items, 2)
    assert "ranker" not in meta


# ---------------------------------------------------------------------------
# Stage 4 — Memory Retrieval leakage protection (prompt injection blocked)
# ---------------------------------------------------------------------------
def test_memory_injection_blocked_even_when_flag_on(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_MEMORY_RETRIEVAL", True)
    # Acceptance constant is still False -> injection must remain blocked.
    assert fp.memory_retrieval_prompt_injection_allowed() is False


def test_memory_injection_allowed_only_with_acceptance(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_MEMORY_RETRIEVAL", True)
    monkeypatch.setattr(
        ai_config, "CANONICAL_MEMORY_RETRIEVAL_PROMPT_INJECTION_ACCEPTED", True
    )
    assert fp.memory_retrieval_prompt_injection_allowed() is True


def test_memory_retrieval_diagnostics_report_blocker(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_MEMORY_RETRIEVAL", True)
    prepared = {"shadow_mode": True, "selected_memory_ids": ["m1", "m2"]}
    diag = fp.memory_retrieval_diagnostics(prepared)
    assert diag["memory_retrieval_enabled"] is True
    assert diag["memory_retrieval_prompt_injection_allowed"] is False
    assert diag["memory_retrieval_blocker_code"] == "SEPARATE_SHADOW_ACCEPTANCE_REQUIRED"
    assert diag["memory_retrieval_canonical_selected_ids"] == ["m1", "m2"]


def test_memory_retrieval_diagnostics_clears_blocker_when_accepted(monkeypatch):
    monkeypatch.setattr(ai_config, "ENABLE_CANONICAL_MEMORY_RETRIEVAL", True)
    monkeypatch.setattr(
        ai_config, "CANONICAL_MEMORY_RETRIEVAL_PROMPT_INJECTION_ACCEPTED", True
    )
    diag = fp.memory_retrieval_diagnostics({"shadow_mode": False, "selected_memory_ids": []})
    assert diag["memory_retrieval_prompt_injection_allowed"] is True
    assert diag["memory_retrieval_blocker_code"] is None


# ---------------------------------------------------------------------------
# Stage 1 chain smoke — compute_actor_resolution_prepared over a real snapshot
# ---------------------------------------------------------------------------
def test_compute_actor_resolution_prepared_runs_gravity_then_actor():
    from foundation_snapshot import FoundationTurnSnapshot

    snapshot = FoundationTurnSnapshot.build(
        run_seed="seed-1",
        turn_sequence=1,
        rolling_state={"npcs": [{"name": "Mara", "stance": "ally"}]},
        replayability_state={"run_seed": "seed-1"},
    )
    prepared = fp.compute_actor_resolution_prepared(snapshot)
    assert "tiers_by_actor_id" in prepared
    # Deterministic: identical snapshot inputs -> identical prepared state hash.
    again = fp.compute_actor_resolution_prepared(snapshot)
    assert prepared["state_hash"] == again["state_hash"]
