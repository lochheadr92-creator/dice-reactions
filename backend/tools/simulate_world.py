"""
Stage 6A — Headless Simulation Harness & Telemetry (developer-only).

Advances the deterministic engine seams used by normal turns for hundreds or
thousands of turns WITHOUT the FastAPI app, player prose, or any LLM call,
then exports structured telemetry for offline analysis.

Seam order per simulated turn mirrors server.py `story_action` minus narration:

    1. replayability.prepare_action_turn        (pressure tick, echoes, NPC
       world move, npc_action_engine, pressure evolution, world-state
       consumers, situation_engine, goal_engine, projections, stress,
       foundation/memory-retrieval shadow, simulation clock)
    2. merged_rolling = deepcopy(working_rolling)   # headless: the model
       contributes nothing; engine authority is unchanged
    3. world_state_consumers.enforce_consumer_world_state
    4. replayability.finalize_living_cast_relationships
    5. replayability.enforce_authoritative          (prompt-safe projections)
    6. replayability.collect_qualifying_echo_sources
    7. replayability.finalize_action_turn

Turn numbering matches production: `init_new_story` is turn 1 (opening), so
`--turns N` simulates action turns 2..N+1.

Outputs (one directory per run):
    metrics.jsonl       one JSON object per simulated turn
    timeline.jsonl      important events only (status transitions, moves,
                        echoes, threshold crossings, world events)
    final_snapshot.json full replayability_state + rolling_state at end
    summary.json        deterministic aggregate (same seed => same bytes)
    anomalies.json      deduplicated anomaly report

Guarantees:
    - No LLM/provider calls: never imports gateway, ai_service, or server.
      Any of those pulled in by the engine import chain is a hard error.
    - No wall-clock, PID, or unseeded randomness in any output.
    - Read-only with respect to production routes and engine authority.

Usage:
    python backend/tools/simulate_world.py --turns 500 --seed 42 \
        --out .nw_tmp/sim_runs/run_001
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Import bootstrap — engine modules live flat in backend/.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Modules whose presence would mean live-provider or app-route code was
# reached. The harness must never import them; if the engine import chain
# pulls one in, that is a Stage 6A contract violation.
FORBIDDEN_MODULES = ("gateway", "ai_service", "server")

_FORBIDDEN_PRELOADED = sorted(m for m in FORBIDDEN_MODULES if m in sys.modules)

import consequence_echoes as echoes  # noqa: E402
import goal_engine  # noqa: E402
import information_engine  # noqa: E402
import investigation_engine  # noqa: E402
import npc_action_engine  # noqa: E402
import pressure_graph  # noqa: E402
import replayability  # noqa: E402
import situation_engine  # noqa: E402
import world_event_engine  # noqa: E402
import world_state_consumers as world_consumers  # noqa: E402

_FORBIDDEN_IMPORTED_BY_ENGINE = sorted(
    m
    for m in FORBIDDEN_MODULES
    if m in sys.modules and m not in _FORBIDDEN_PRELOADED
)
if _FORBIDDEN_IMPORTED_BY_ENGINE:  # pragma: no cover - contract violation
    raise ImportError(
        "simulation harness engine import chain loaded forbidden modules: "
        f"{_FORBIDDEN_IMPORTED_BY_ENGINE}"
    )

# ---------------------------------------------------------------------------
# Tunables — anomaly thresholds (developer telemetry only, not gameplay).
# ---------------------------------------------------------------------------
STUCK_GOAL_TURNS = 40
STUCK_SITUATION_TURNS = 40
PRESSURE_NO_DECAY_TURNS = 30
EVENT_EXPLOSION_PER_TURN = 8
STUCK_WORLD_EVENT_TURNS = 36
WORLD_EVENT_EXPLOSION_PER_TURN = 6
WORLD_EVENT_LOOP_EVENT_COUNT = 4
TIMELINE_EVENTS_PER_TURN_CAP = 32

GOAL_TERMINAL = goal_engine.TERMINAL_STATUSES
SITUATION_TERMINAL = situation_engine.TERMINAL_STATUSES
WORLD_EVENT_TERMINAL = world_event_engine.TERMINAL_STATUSES
INVESTIGATION_TERMINAL = investigation_engine.TERMINAL_STATUSES

# Prompt-safe projection allowlists — mirrors of the engine projection
# contracts (project_active_*_for_rolling / prompt_safe_rolling_state).
PROMPT_GOAL_FIELDS = frozenset(
    {"title", "status", "priority", "progress", "next_step_summary"}
)
PROMPT_SITUATION_FIELDS = frozenset(
    {
        "situation_id",
        "type",
        "title",
        "status",
        "priority",
        "severity",
        "progress",
        "affected_locations",
        "affected_factions",
        "objectives",
        "blockers",
    }
)
PROMPT_ACTION_FIELDS = frozenset(npc_action_engine.PROMPT_ACTION_FIELDS)
PROMPT_WORLD_EVENT_FIELDS = frozenset(
    {"title", "severity", "status", "affected_locations", "affected_factions", "progress"}
)
PROMPT_INVESTIGATION_FIELDS = investigation_engine.PROMPT_INVESTIGATION_FIELDS
PROMPT_INFORMATION_FIELDS = frozenset(
    {"information_type", "summary", "reliability_band", "distortion_level", "visibility_scope", "gravity", "subjects"}
)
PROMPT_REPUTATION_FIELDS = frozenset(
    {"subject_type", "subject_id", "observer_scope", "dimension", "score_band", "confidence_band"}
)
# Mirror of pressure_graph._PROMPT_NODE_FIELDS — evidence_refs is part of the
# engine's deliberate node projection contract, so it is allowlisted HERE and
# forbidden everywhere else. Drift between this mirror and the engine flags a
# review point, which is intended.
PROMPT_PRESSURE_NODE_FIELDS = frozenset(
    {
        "id", "kind", "origin", "scope", "magnitude", "trend", "trend_label",
        "actor_ids", "location_ids", "faction_ids", "tags", "linked_node_ids",
        "status", "created_turn", "updated_turn", "evidence_refs", "label",
    }
)

# Keys that must never appear anywhere inside a prompt-safe projection.
# (evidence_refs is enforced per-collection via allowlists instead: legal on
# pressure nodes, illegal on goal/situation/action projections.)
FORBIDDEN_PROMPT_KEYS = frozenset(
    {
        "source_event_ids",
        "run_seed",
        "dedupe_key",
        "parent_situation_ids",
        "originating_pressure_ids",
        "originating_world_event_ids",
        "supporting_pressure_ids",
        "source_action_ids",
        "related_case_ids",
        "related_evidence_ids",
        "reliability",
        "information_id",
        "signal_id",
        "known_by",
        "observer_access",
        "access_type",
        "acquired_at",
        "last_decay_turn",
        "decay_ready",
        "stale",
    }
)
FORBIDDEN_PROMPT_KEY_SUBSTRINGS = ("receipt",)

# Authoritative replayability collections that must never sit in rolling_state.
FORBIDDEN_ROLLING_TOP_LEVEL = frozenset(
    {
        "goals",
        "situations",
        "npc_actions",
        "engine_world_events",
        "world_events",
        "world_event_receipts",
        "evidence",
        "investigations",
        "investigation_receipts",
        "information_items",
        "information_receipts",
        "reputation_signals",
        "transition_receipts",
        "goal_receipts",
        "situation_receipts",
        "npc_action_receipts",
        "npc_agendas",
        "consequence_echoes",
    }
)


# Bounded-collection contract: (state key, cap).
def _collection_caps() -> List[Tuple[str, int]]:
    return [
        ("goals", goal_engine.MAX_GOALS),
        ("goal_receipts", goal_engine.MAX_GOAL_RECEIPTS),
        ("situations", situation_engine.MAX_SITUATIONS),
        ("situation_receipts", situation_engine.MAX_SITUATION_RECEIPTS),
        ("npc_actions", npc_action_engine.MAX_NPC_ACTIONS),
        ("npc_action_receipts", npc_action_engine.MAX_NPC_ACTION_RECEIPTS),
        ("engine_world_events", replayability.MAX_ENGINE_WORLD_EVENTS),
        ("world_events", world_event_engine.MAX_WORLD_EVENTS),
        ("world_event_receipts", world_event_engine.MAX_WORLD_EVENT_RECEIPTS),
        ("evidence", investigation_engine.MAX_EVIDENCE),
        ("investigations", investigation_engine.MAX_INVESTIGATIONS),
        ("investigation_receipts", investigation_engine.MAX_INVESTIGATION_RECEIPTS),
        ("information_items", information_engine.MAX_INFORMATION_ITEMS),
        ("information_receipts", information_engine.MAX_INFORMATION_RECEIPTS),
        ("reputation_signals", information_engine.MAX_REPUTATION_SIGNALS),
        ("transition_receipts", replayability.TRANSITION_RECEIPTS_MAX),
        (
            "relationship_effect_receipts",
            replayability.RELATIONSHIP_EFFECT_RECEIPTS_MAX,
        ),
    ]


PRESSURE_NODES_CAP = pressure_graph.MAX_TOTAL_NODES
ECHO_SCHEDULED_CAP = echoes.MAX_SCHEDULED
ECHO_FIRED_CAP = echoes.MAX_FIRED_LOG
STATE_BUDGET_BYTES = replayability.REPLAYABILITY_STATE_BUDGET_BYTES


# ---------------------------------------------------------------------------
# Small pure helpers.
# ---------------------------------------------------------------------------
def _rows(state: Mapping[str, Any], key: str) -> List[Dict[str, Any]]:
    return [row for row in state.get(key) or [] if isinstance(row, dict)]


def _ids(rows: Iterable[Mapping[str, Any]], id_key: str) -> List[str]:
    return [str(r.get(id_key) or "") for r in rows if r.get(id_key)]


def _duplicates(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    dupes: Set[str] = set()
    for v in values:
        if v in seen:
            dupes.add(v)
        seen.add(v)
    return sorted(dupes)


def _avg_age(rows: List[Dict[str, Any]], turn: int, terminal: frozenset) -> float:
    ages = [
        max(0, turn - int(r.get("created_turn") or 0))
        for r in rows
        if str(r.get("status") or "") not in terminal
    ]
    return round(sum(ages) / len(ages), 3) if ages else 0.0


def _avg_values(values: Iterable[int]) -> float:
    rows = [max(0, int(value or 0)) for value in values]
    return round(sum(rows) / len(rows), 3) if rows else 0.0


def scan_forbidden_keys(value: Any, path: str = "$") -> List[str]:
    """Recursively find forbidden internal keys inside a prompt-safe view."""
    hits: List[str] = []
    if isinstance(value, Mapping):
        for key, inner in value.items():
            key_s = str(key)
            lowered = key_s.lower()
            if key_s in FORBIDDEN_PROMPT_KEYS or any(
                sub in lowered for sub in FORBIDDEN_PROMPT_KEY_SUBSTRINGS
            ):
                hits.append(f"{path}.{key_s}")
            hits.extend(scan_forbidden_keys(inner, f"{path}.{key_s}"))
    elif isinstance(value, list):
        for idx, inner in enumerate(value):
            hits.extend(scan_forbidden_keys(inner, f"{path}[{idx}]"))
    return hits


def prompt_safety_violations(merged_rolling: Mapping[str, Any]) -> List[str]:
    """
    Build the chained prompt-safe view exactly as prompt assembly would and
    flag any leakage of receipts/source_event_ids/internal metadata, plus any
    authoritative replayability collection sitting in rolling_state itself.
    """
    violations: List[str] = []
    if not isinstance(merged_rolling, Mapping):
        return violations
    for key in sorted(FORBIDDEN_ROLLING_TOP_LEVEL):
        if key in merged_rolling:
            violations.append(f"rolling.{key}:authoritative_key_in_rolling")

    safe = goal_engine.prompt_safe_rolling_state(dict(merged_rolling))
    safe = information_engine.prompt_safe_rolling_state(safe)
    safe = investigation_engine.prompt_safe_rolling_state(safe)
    safe = situation_engine.prompt_safe_rolling_state(safe)
    safe = world_event_engine.prompt_safe_rolling_state(safe)
    safe = npc_action_engine.prompt_safe_rolling_state(safe)
    safe = world_consumers.prompt_safe_world_state(safe)

    scan_targets = {
        "active_goals": PROMPT_GOAL_FIELDS,
        "active_situations": PROMPT_SITUATION_FIELDS,
        "active_npc_actions": PROMPT_ACTION_FIELDS,
        "active_world_events": PROMPT_WORLD_EVENT_FIELDS,
        "active_investigations": PROMPT_INVESTIGATION_FIELDS,
        "active_information": PROMPT_INFORMATION_FIELDS,
        "active_reputation": PROMPT_REPUTATION_FIELDS,
    }
    for key, allowed in scan_targets.items():
        for idx, row in enumerate(safe.get(key) or []):
            if not isinstance(row, Mapping):
                continue
            extra = sorted(set(map(str, row.keys())) - allowed)
            if extra:
                violations.append(f"{key}[{idx}]:unexpected_keys={','.join(extra)}")
    pg_projection = safe.get("pressure_graph") or {}
    if isinstance(pg_projection, Mapping):
        for idx, node in enumerate(pg_projection.get("nodes") or []):
            if not isinstance(node, Mapping):
                continue
            extra = sorted(set(map(str, node.keys())) - PROMPT_PRESSURE_NODE_FIELDS)
            if extra:
                violations.append(
                    f"pressure_graph.nodes[{idx}]:unexpected_keys={','.join(extra)}"
                )
    for key in ("active_goals", "active_situations", "active_npc_actions",
                "active_world_events",
                "active_investigations",
                "active_information",
                "active_reputation",
                "pressure_graph", "active_pressures"):
        violations.extend(scan_forbidden_keys(safe.get(key), f"safe.{key}"))
    return violations


def duplicate_id_report(state: Mapping[str, Any]) -> Dict[str, List[str]]:
    """Duplicate IDs within each authoritative collection."""
    pg = state.get("pressure_graph") or {}
    report = {
        "goals": _duplicates(_ids(_rows(state, "goals"), "goal_id")),
        "situations": _duplicates(_ids(_rows(state, "situations"), "situation_id")),
        "npc_actions": _duplicates(_ids(_rows(state, "npc_actions"), "action_id")),
        "world_events": _duplicates(
            _ids(_rows(state, "world_events"), "world_event_id")
        ),
        "evidence": _duplicates(_ids(_rows(state, "evidence"), "evidence_id")),
        "investigations": _duplicates(
            _ids(_rows(state, "investigations"), "investigation_id")
        ),
        "information_items": _duplicates(
            _ids(_rows(state, "information_items"), "information_id")
        ),
        "reputation_signals": _duplicates(
            _ids(_rows(state, "reputation_signals"), "signal_id")
        ),
        "engine_world_events": _duplicates(
            _ids(_rows(state, "engine_world_events"), "event_id")
        ),
        "pressure_nodes": _duplicates(
            _ids([n for n in pg.get("nodes") or [] if isinstance(n, dict)], "id")
        ),
    }
    return {k: v for k, v in report.items() if v}


def missing_source_event_ids(state: Mapping[str, Any]) -> Dict[str, List[str]]:
    """Rows in provenance-bearing collections with no source_event_ids."""
    out: Dict[str, List[str]] = {}
    for key, id_key in (
        ("goals", "goal_id"),
        ("situations", "situation_id"),
        ("npc_actions", "action_id"),
        ("world_events", "world_event_id"),
        ("evidence", "evidence_id"),
        ("information_items", "information_id"),
        ("reputation_signals", "signal_id"),
    ):
        missing = [
            str(row.get(id_key) or f"{key}[{idx}]")
            for idx, row in enumerate(_rows(state, key))
            if not [s for s in row.get("source_event_ids") or [] if str(s).strip()]
            and not [s for s in row.get("source_action_ids") or [] if str(s).strip()]
        ]
        if missing:
            out[key] = missing
    return out


def evidence_cycle_ids(state: Mapping[str, Any]) -> List[str]:
    """Evidence related_evidence_ids must form a DAG."""
    graph: Dict[str, List[str]] = {}
    for row in _rows(state, "evidence"):
        evidence_id = str(row.get("evidence_id") or "")
        if not evidence_id:
            continue
        graph[evidence_id] = [
            str(ref)
            for ref in row.get("related_evidence_ids") or []
            if str(ref) in graph or str(ref)
        ]
    visiting: Set[str] = set()
    visited: Set[str] = set()
    cycles: Set[str] = set()

    def visit(node: str, path: List[str]) -> None:
        if node in visiting:
            cycles.update(path[path.index(node):] if node in path else [node])
            return
        if node in visited:
            return
        visiting.add(node)
        for child in graph.get(node, []):
            if child in graph:
                visit(child, path + [child])
        visiting.remove(node)
        visited.add(node)

    for evidence_id in sorted(graph):
        visit(evidence_id, [evidence_id])
    return sorted(cycles)


def bounded_collection_report(state: Mapping[str, Any]) -> Dict[str, Any]:
    """Sizes vs caps for every bounded engine collection."""
    sizes: Dict[str, Any] = {}
    over: List[str] = []
    for label, cap in _collection_caps():
        size = len(state.get(label) or [])
        sizes[label] = {"size": size, "cap": cap}
        if size > cap:
            over.append(label)
    pg = state.get("pressure_graph") or {}
    node_count = len(pg.get("nodes") or [])
    sizes["pressure_nodes"] = {"size": node_count, "cap": PRESSURE_NODES_CAP}
    if node_count > PRESSURE_NODES_CAP:
        over.append("pressure_nodes")
    echo_state = state.get("consequence_echoes") or {}
    scheduled = len(echo_state.get("scheduled") or [])
    fired = len(echo_state.get("fired") or [])
    sizes["echoes_scheduled"] = {"size": scheduled, "cap": ECHO_SCHEDULED_CAP}
    sizes["echoes_fired"] = {"size": fired, "cap": ECHO_FIRED_CAP}
    if scheduled > ECHO_SCHEDULED_CAP:
        over.append("echoes_scheduled")
    if fired > ECHO_FIRED_CAP:
        over.append("echoes_fired")
    return {"sizes": sizes, "over_cap": sorted(over)}


# ---------------------------------------------------------------------------
# Telemetry collector.
# ---------------------------------------------------------------------------
class TelemetryCollector:
    """
    Tracks ever-seen IDs, status transitions, decay behaviour, and anomalies
    across the run. Pure bookkeeping — never mutates engine state.
    """

    def __init__(self) -> None:
        self.seen_goal_ids: Set[str] = set()
        self.seen_situation_ids: Set[str] = set()
        self.seen_action_ids: Set[str] = set()
        self.seen_world_event_ids: Set[str] = set()
        self.seen_evidence_ids: Set[str] = set()
        self.seen_investigation_ids: Set[str] = set()
        self.seen_information_ids: Set[str] = set()
        self.seen_reputation_signal_ids: Set[str] = set()
        self.seen_event_ids: Set[str] = set()
        self.seen_pressure_ids: Set[str] = set()
        self.goal_status: Dict[str, str] = {}
        self.situation_status: Dict[str, str] = {}
        self.world_event_status: Dict[str, str] = {}
        self.investigation_status: Dict[str, str] = {}
        self.pressure_status: Dict[str, str] = {}
        self.goal_created_turn: Dict[str, int] = {}
        self.situation_created_turn: Dict[str, int] = {}
        self.world_event_created_turn: Dict[str, int] = {}
        self.investigation_created_turn: Dict[str, int] = {}
        self.pressure_created_turn: Dict[str, int] = {}
        self.goal_lifetimes: List[int] = []
        self.situation_lifetimes: List[int] = []
        self.world_event_lifetimes: List[int] = []
        self.investigation_lifetimes: List[int] = []
        self.pressure_lifetimes: List[int] = []
        self.goal_terminal_counts = {"completed": 0, "failed": 0, "abandoned": 0}
        self.situation_terminal_counts = {"resolved": 0, "failed": 0, "archived": 0}
        self.world_event_terminal_counts = {"resolved": 0, "failed": 0, "archived": 0}
        self.investigation_terminal_counts = {"closed": 0, "failed": 0, "archived": 0}
        self.pressure_created_cum = 0
        self.pressure_resolved_ids: Set[str] = set()
        self.events_appended_cum = 0
        self.echoes_fired_cum = 0
        self.goal_recreation_count = 0
        self.world_event_recreation_count = 0
        self.world_event_merge_count = 0
        self.world_event_archive_count = 0
        self.pressure_decay_count = 0
        self.situation_archive_count = 0
        self.budget_warning_count = 0
        self.world_event_category_counts: Dict[str, int] = {}
        self.world_event_engine_event_counts: Dict[str, int] = {}
        # node_id -> (last_magnitude, last_decrease_or_first_seen_turn)
        self.pressure_decay_watch: Dict[str, Tuple[int, int]] = {}
        # (code, subject) -> anomaly record
        self.anomalies: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.mean_active_pressure_acc = 0.0
        self.turns_observed = 0

    # -- anomaly bookkeeping --------------------------------------------------
    def flag(self, code: str, subject: str, turn: int, detail: str) -> bool:
        key = (code, subject)
        record = self.anomalies.get(key)
        if record is None:
            self.anomalies[key] = {
                "code": code,
                "subject": subject,
                "first_turn": turn,
                "last_turn": turn,
                "occurrences": 1,
                "detail": detail,
            }
            return True
        record["last_turn"] = turn
        record["occurrences"] += 1
        return False

    # -- per-turn observation ---------------------------------------------------
    def observe_turn(
        self,
        turn: int,
        state: Mapping[str, Any],
        merged_rolling: Mapping[str, Any],
        diagnostics: Mapping[str, Any],
        threshold_events: List[Mapping[str, Any]],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Returns (metrics_row, timeline_events) for this turn."""
        timeline: List[Dict[str, Any]] = []
        self.turns_observed += 1

        goals = _rows(state, "goals")
        situations = _rows(state, "situations")
        actions = _rows(state, "npc_actions")
        world_events = _rows(state, "world_events")
        evidence = _rows(state, "evidence")
        investigations = _rows(state, "investigations")
        information_items = _rows(state, "information_items")
        reputation_signals = _rows(state, "reputation_signals")
        events = _rows(state, "engine_world_events")
        pg = state.get("pressure_graph") or {}
        nodes = [n for n in pg.get("nodes") or [] if isinstance(n, dict)]
        echo_state = state.get("consequence_echoes") or {}

        # --- status transitions (goals / situations) -> timeline + counters
        for row in goals:
            gid = str(row.get("goal_id") or "")
            status = str(row.get("status") or "")
            if not gid:
                continue
            created_turn = int(row.get("created_turn") or turn)
            self.goal_created_turn.setdefault(gid, created_turn)
            prev = self.goal_status.get(gid)
            if prev != status:
                if prev is not None or status not in ("forming", "active"):
                    timeline.append(
                        {
                            "turn": turn,
                            "kind": "goal_status",
                            "id": gid,
                            "from": prev,
                            "to": status,
                        }
                    )
                if status in self.goal_terminal_counts and prev not in GOAL_TERMINAL:
                    self.goal_terminal_counts[status] += 1
                    self.goal_lifetimes.append(
                        max(0, turn - self.goal_created_turn.get(gid, created_turn))
                    )
                self.goal_status[gid] = status
        for row in situations:
            sid = str(row.get("situation_id") or "")
            status = str(row.get("status") or "")
            if not sid:
                continue
            created_turn = int(row.get("created_turn") or turn)
            self.situation_created_turn.setdefault(sid, created_turn)
            prev = self.situation_status.get(sid)
            if prev != status:
                if prev is not None or status not in ("forming", "active"):
                    timeline.append(
                        {
                            "turn": turn,
                            "kind": "situation_status",
                            "id": sid,
                            "from": prev,
                            "to": status,
                        }
                    )
                if status == "archived" and prev != "archived":
                    self.situation_archive_count += 1
                if (
                    status in self.situation_terminal_counts
                    and prev not in SITUATION_TERMINAL
                ):
                    self.situation_terminal_counts[status] += 1
                    self.situation_lifetimes.append(
                        max(0, turn - self.situation_created_turn.get(sid, created_turn))
                    )
                self.situation_status[sid] = status
        for row in world_events:
            wid = str(row.get("world_event_id") or "")
            status = str(row.get("status") or "")
            if not wid:
                continue
            created_turn = int(row.get("created_turn") or turn)
            self.world_event_created_turn.setdefault(wid, created_turn)
            category = str(row.get("event_type") or "unknown")
            prev = self.world_event_status.get(wid)
            if prev != status:
                if prev is not None or status not in ("forming", "active"):
                    timeline.append(
                        {
                            "turn": turn,
                            "kind": "canonical_world_event_status",
                            "id": wid,
                            "from": prev,
                            "to": status,
                            "event_type": category,
                        }
                    )
                if status == "archived" and prev != "archived":
                    self.world_event_archive_count += 1
                if (
                    status in self.world_event_terminal_counts
                    and prev not in WORLD_EVENT_TERMINAL
                ):
                    self.world_event_terminal_counts[status] += 1
                    self.world_event_lifetimes.append(
                        max(0, turn - self.world_event_created_turn.get(wid, created_turn))
                    )
                self.world_event_status[wid] = status
        for row in investigations:
            iid = str(row.get("investigation_id") or "")
            status = str(row.get("status") or "")
            if not iid:
                continue
            created_turn = int(row.get("created_turn") or turn)
            self.investigation_created_turn.setdefault(iid, created_turn)
            prev = self.investigation_status.get(iid)
            if prev != status:
                if prev is not None or status not in ("open", "active"):
                    timeline.append(
                        {
                            "turn": turn,
                            "kind": "investigation_status",
                            "id": iid,
                            "from": prev,
                            "to": status,
                        }
                    )
                if (
                    status in self.investigation_terminal_counts
                    and prev not in INVESTIGATION_TERMINAL
                ):
                    self.investigation_terminal_counts[status] += 1
                    self.investigation_lifetimes.append(
                        max(0, turn - self.investigation_created_turn.get(iid, created_turn))
                    )
                self.investigation_status[iid] = status

        # --- ever-seen sets + creation counters
        new_world_events = [
            e for e in world_events
            if str(e.get("world_event_id") or "") not in self.seen_world_event_ids
        ]
        for e in new_world_events:
            category = str(e.get("event_type") or "unknown")
            self.world_event_category_counts[category] = self.world_event_category_counts.get(category, 0) + 1
            timeline.append(
                {
                    "turn": turn,
                    "kind": "canonical_world_event",
                    "id": str(e.get("world_event_id") or ""),
                    "event_type": category,
                    "status": str(e.get("status") or ""),
                }
            )
        new_events = [
            e for e in events if str(e.get("event_id") or "") not in self.seen_event_ids
        ]
        self.events_appended_cum += len(new_events)
        for e in new_events:
            world_event_id = str(e.get("world_event_id") or "")
            if world_event_id:
                self.world_event_engine_event_counts[world_event_id] = (
                    self.world_event_engine_event_counts.get(world_event_id, 0) + 1
                )
            timeline.append(
                {
                    "turn": turn,
                    "kind": "world_event",
                    "id": str(e.get("event_id") or ""),
                    "event_kind": str(e.get("kind") or e.get("event_kind") or ""),
                }
            )
        node_ids = set(_ids(nodes, "id"))
        new_nodes = node_ids - self.seen_pressure_ids
        self.pressure_created_cum += len(new_nodes)
        pressure_terminal = {"reduced", "resolved", "archived"}
        for node in nodes:
            nid = str(node.get("id") or "")
            if not nid:
                continue
            created_turn = int(node.get("created_turn") or turn)
            self.pressure_created_turn.setdefault(nid, created_turn)
            status = str(node.get("status") or "")
            prev = self.pressure_status.get(nid)
            if status == "resolved":
                self.pressure_resolved_ids.add(nid)
            if (
                prev != status
                and status in pressure_terminal
                and prev not in pressure_terminal
            ):
                self.pressure_lifetimes.append(
                    max(0, turn - self.pressure_created_turn.get(nid, created_turn))
                )
            self.pressure_status[nid] = status
        self.seen_goal_ids.update(_ids(goals, "goal_id"))
        self.seen_situation_ids.update(_ids(situations, "situation_id"))
        self.seen_action_ids.update(_ids(actions, "action_id"))
        self.seen_world_event_ids.update(_ids(world_events, "world_event_id"))
        self.seen_evidence_ids.update(_ids(evidence, "evidence_id"))
        self.seen_investigation_ids.update(_ids(investigations, "investigation_id"))
        self.seen_information_ids.update(_ids(information_items, "information_id"))
        self.seen_reputation_signal_ids.update(_ids(reputation_signals, "signal_id"))
        self.seen_event_ids.update(_ids(events, "event_id"))
        self.seen_pressure_ids.update(node_ids)

        # --- diagnostics-driven timeline entries
        if diagnostics.get("echo_fired"):
            self.echoes_fired_cum += 1
            timeline.append(
                {"turn": turn, "kind": "echo_fired", "id": str(diagnostics["echo_fired"])}
            )
        self.goal_recreation_count += int(diagnostics.get("goal_recreated") or 0)
        self.world_event_recreation_count += int(diagnostics.get("world_event_recreated") or 0)
        self.world_event_merge_count += int(diagnostics.get("world_event_merged") or 0)
        if diagnostics.get("npc_move_kind"):
            timeline.append(
                {
                    "turn": turn,
                    "kind": "npc_move_committed",
                    "move_kind": str(diagnostics["npc_move_kind"]),
                }
            )
        for evt in threshold_events or []:
            timeline.append(
                {
                    "turn": turn,
                    "kind": "pressure_threshold_crossed",
                    "id": str(evt.get("event_id") or ""),
                    "pressure_kind": str(evt.get("pressure_kind") or ""),
                }
            )

        # --- anomaly: event explosion
        if len(new_events) > EVENT_EXPLOSION_PER_TURN:
            self.flag(
                "event_explosion",
                f"turn-{turn}",
                turn,
                f"{len(new_events)} world events appended in one turn "
                f"(threshold {EVENT_EXPLOSION_PER_TURN})",
            )
        if len(new_world_events) > WORLD_EVENT_EXPLOSION_PER_TURN:
            self.flag(
                "runaway_world_event_creation",
                f"turn-{turn}",
                turn,
                f"{len(new_world_events)} canonical world events created in one turn "
                f"(threshold {WORLD_EVENT_EXPLOSION_PER_TURN})",
            )
        for wid, count in self.world_event_engine_event_counts.items():
            if count > WORLD_EVENT_LOOP_EVENT_COUNT:
                self.flag(
                    "world_event_loop",
                    wid,
                    turn,
                    f"world event emitted {count} engine events "
                    f"(threshold {WORLD_EVENT_LOOP_EVENT_COUNT})",
                )

        # --- anomaly: stuck goals / situations
        for row in goals:
            gid = str(row.get("goal_id") or "")
            status = str(row.get("status") or "")
            age = turn - int(row.get("created_turn") or 0)
            if gid and status not in GOAL_TERMINAL and age >= STUCK_GOAL_TURNS:
                self.flag(
                    "goal_stuck",
                    gid,
                    turn,
                    f"goal non-terminal for {age} turns (status={status})",
                )
        for row in situations:
            sid = str(row.get("situation_id") or "")
            status = str(row.get("status") or "")
            age = turn - int(row.get("created_turn") or 0)
            if sid and status not in SITUATION_TERMINAL and age >= STUCK_SITUATION_TURNS:
                self.flag(
                    "situation_stuck",
                    sid,
                    turn,
                    f"situation non-terminal for {age} turns (status={status})",
                )
        for row in world_events:
            wid = str(row.get("world_event_id") or "")
            status = str(row.get("status") or "")
            age = turn - int(row.get("created_turn") or 0)
            if wid and status not in WORLD_EVENT_TERMINAL and age >= STUCK_WORLD_EVENT_TURNS:
                self.flag(
                    "world_event_immortal",
                    wid,
                    turn,
                    f"world event non-terminal for {age} turns (status={status})",
                )

        # --- anomaly: pressure never decays
        active_node_ids: Set[str] = set()
        for node in nodes:
            nid = str(node.get("id") or "")
            if not nid or str(node.get("status") or "") != "active":
                continue
            active_node_ids.add(nid)
            magnitude = int(node.get("magnitude") or 0)
            prev = self.pressure_decay_watch.get(nid)
            if prev is None:
                self.pressure_decay_watch[nid] = (magnitude, turn)
            else:
                prev_mag, last_decrease = prev
                if magnitude < prev_mag:
                    self.pressure_decay_count += 1
                    self.pressure_decay_watch[nid] = (magnitude, turn)
                else:
                    self.pressure_decay_watch[nid] = (magnitude, last_decrease)
                    if turn - last_decrease >= PRESSURE_NO_DECAY_TURNS:
                        self.flag(
                            "pressure_never_decays",
                            nid,
                            turn,
                            f"active pressure magnitude has not decreased for "
                            f"{turn - last_decrease} turns (magnitude={magnitude})",
                        )
        for nid in list(self.pressure_decay_watch):
            if nid not in active_node_ids:
                del self.pressure_decay_watch[nid]

        # --- anomaly: duplicate IDs
        dupes = duplicate_id_report(state)
        for collection, ids in dupes.items():
            for dup in ids:
                self.flag(
                    "duplicate_id",
                    f"{collection}:{dup}",
                    turn,
                    f"duplicate id {dup!r} in {collection}",
                )

        # --- anomaly: missing provenance
        missing = missing_source_event_ids(state)
        for collection, ids in missing.items():
            for rid in ids:
                self.flag(
                    "missing_source_event_ids",
                    f"{collection}:{rid}",
                    turn,
                    f"{collection} row {rid!r} has no source_event_ids",
                )

        # --- anomaly: dangling references (against ever-seen sets)
        orphaned_goals = 0
        for row in goals:
            gid = str(row.get("goal_id") or "")
            refs = [str(s) for s in row.get("parent_situation_ids") or [] if s]
            dangling = [r for r in refs if r not in self.seen_situation_ids]
            if dangling:
                orphaned_goals += 1
                self.flag(
                    "goal_missing_situation",
                    gid,
                    turn,
                    f"goal references unknown situation ids {dangling}",
                )
        orphaned_situations = 0
        for row in situations:
            sid = str(row.get("situation_id") or "")
            p_refs = [str(s) for s in row.get("originating_pressure_ids") or [] if s]
            e_refs = [str(s) for s in row.get("originating_world_event_ids") or [] if s]
            dangling_p = [r for r in p_refs if r not in self.seen_pressure_ids]
            dangling_e = [
                r for r in e_refs
                if r not in self.seen_event_ids and r not in self.seen_world_event_ids
            ]
            if dangling_p or dangling_e:
                orphaned_situations += 1
                self.flag(
                    "situation_missing_source",
                    sid,
                    turn,
                    f"situation references unknown pressure ids {dangling_p} "
                    f"/ world event ids {dangling_e}",
                )
        orphaned_world_events = 0
        for row in world_events:
            wid = str(row.get("world_event_id") or "")
            p_refs = [str(s) for s in row.get("originating_pressure_ids") or [] if s]
            s_refs = [str(s) for s in row.get("originating_situation_ids") or [] if s]
            g_refs = [str(s) for s in row.get("originating_goal_ids") or [] if s]
            a_refs = [str(s) for s in row.get("originating_action_ids") or [] if s]
            dangling = (
                [f"pressure:{r}" for r in p_refs if r not in self.seen_pressure_ids]
                + [f"situation:{r}" for r in s_refs if r not in self.seen_situation_ids]
                + [f"goal:{r}" for r in g_refs if r not in self.seen_goal_ids]
                + [f"action:{r}" for r in a_refs if r not in self.seen_action_ids]
            )
            if dangling:
                orphaned_world_events += 1
                self.flag(
                    "orphaned_world_event",
                    wid,
                    turn,
                    f"world event references unknown sources {dangling}",
                )
        dangling_action_refs = 0
        for row in actions:
            aid = str(row.get("action_id") or "")
            goal_ref = str(row.get("goal_id") or "")
            situation_ref = str(row.get("situation_id") or "")
            problems = []
            if goal_ref and goal_ref not in self.seen_goal_ids:
                problems.append(f"goal:{goal_ref}")
            if situation_ref and situation_ref not in self.seen_situation_ids:
                problems.append(f"situation:{situation_ref}")
            if problems:
                dangling_action_refs += 1
                self.flag(
                    "npc_action_missing_ref",
                    aid,
                    turn,
                    f"npc action references unknown {problems}",
                )
        orphaned_evidence = 0
        known_source_ids = (
            self.seen_event_ids
            | self.seen_world_event_ids
            | self.seen_situation_ids
            | self.seen_pressure_ids
            | self.seen_investigation_ids
        )
        for row in evidence:
            eid = str(row.get("evidence_id") or "")
            source_refs = [str(s) for s in row.get("source_event_ids") or [] if s]
            action_refs = [str(s) for s in row.get("source_action_ids") or [] if s]
            case_refs = [str(s) for s in row.get("related_case_ids") or [] if s]
            related_refs = [str(s) for s in row.get("related_evidence_ids") or [] if s]
            dangling = (
                [f"source:{r}" for r in source_refs if r not in known_source_ids]
                + [f"action:{r}" for r in action_refs if r not in self.seen_action_ids]
                + [f"case:{r}" for r in case_refs if r not in self.seen_investigation_ids]
                + [f"evidence:{r}" for r in related_refs if r not in self.seen_evidence_ids]
            )
            if dangling:
                orphaned_evidence += 1
                self.flag(
                    "orphan_evidence",
                    eid,
                    turn,
                    f"evidence references unknown sources {dangling}",
                )
        orphaned_investigations = 0
        for row in investigations:
            iid = str(row.get("investigation_id") or "")
            world_event_ref = str(row.get("world_event_id") or "")
            situation_ref = str(row.get("situation_id") or "")
            evidence_refs = [str(s) for s in row.get("evidence_ids") or [] if s]
            dangling = (
                ([f"world_event:{world_event_ref}"] if world_event_ref and world_event_ref not in self.seen_world_event_ids else [])
                + ([f"situation:{situation_ref}"] if situation_ref and situation_ref not in self.seen_situation_ids else [])
                + [f"evidence:{r}" for r in evidence_refs if r not in self.seen_evidence_ids]
            )
            if dangling:
                orphaned_investigations += 1
                self.flag(
                    "orphan_investigation",
                    iid,
                    turn,
                    f"investigation references unknown sources {dangling}",
                )
        impossible_confidence = 0
        for row in evidence:
            eid = str(row.get("evidence_id") or "")
            for field in ("reliability", "confidence"):
                value = row.get(field)
                if not isinstance(value, (int, float)) or value < 0 or value > 100:
                    impossible_confidence += 1
                    self.flag(
                        "impossible_confidence",
                        f"evidence:{eid}:{field}",
                        turn,
                        f"evidence {eid!r} has impossible {field}={value!r}",
                    )
        for row in investigations:
            iid = str(row.get("investigation_id") or "")
            for field in ("confidence", "progress"):
                value = row.get(field)
                if not isinstance(value, (int, float)) or value < 0 or value > 100:
                    impossible_confidence += 1
                    self.flag(
                        "impossible_confidence",
                        f"investigation:{iid}:{field}",
                        turn,
                        f"investigation {iid!r} has impossible {field}={value!r}",
                    )
        cycles = evidence_cycle_ids(state)
        for evidence_id in cycles:
            self.flag(
                "evidence_cycle",
                evidence_id,
                turn,
                f"evidence related_evidence_ids contains a cycle at {evidence_id!r}",
            )

        # --- anomaly: prompt-safety leakage
        leakage = prompt_safety_violations(merged_rolling)
        for violation in leakage:
            self.flag("prompt_leakage", violation, turn, violation)

        # --- anomaly: unbounded growth
        bounded = bounded_collection_report(state)
        for label in bounded["over_cap"]:
            self.flag(
                "unbounded_growth",
                label,
                turn,
                f"collection {label} exceeded cap "
                f"({bounded['sizes'][label]['size']} > {bounded['sizes'][label]['cap']})",
            )

        # --- metrics row
        active_goals = [g for g in goals if str(g.get("status")) not in GOAL_TERMINAL]
        active_situations = [
            s for s in situations if str(s.get("status")) not in SITUATION_TERMINAL
        ]
        active_world_events = [
            w for w in world_events if str(w.get("status")) not in WORLD_EVENT_TERMINAL
        ]
        active_investigations = [
            i for i in investigations
            if str(i.get("status")) not in INVESTIGATION_TERMINAL
            and not i.get("archived")
        ]
        active_evidence = [e for e in evidence if not e.get("archived")]
        active_information = information_items
        active_reputation = reputation_signals
        active_actions = [a for a in actions if str(a.get("status")) == "selected"]
        active_nodes = [n for n in nodes if str(n.get("status")) == "active"]
        self.mean_active_pressure_acc += len(active_nodes)
        npc_memory = merged_rolling.get("npc_memory") or []
        memory_entries = sum(
            len(row.get("remembers") or [])
            for row in npc_memory
            if isinstance(row, dict)
        )
        retrieval_diag = diagnostics.get("memory_retrieval_promotion")
        retrieval = retrieval_diag if isinstance(retrieval_diag, Mapping) else {}
        state_bytes = replayability.replayability_state_byte_size(dict(state))
        if state_bytes > STATE_BUDGET_BYTES:
            self.budget_warning_count += 1
            self.flag(
                "state_budget_exceeded",
                "replayability_state",
                turn,
                f"serialized replayability_state {state_bytes} bytes exceeds "
                f"production budget {STATE_BUDGET_BYTES}",
            )
        turns_so_far = max(1, self.turns_observed)
        average_evidence_age = 0.0
        if active_evidence:
            average_evidence_age = round(
                sum(max(0, turn - int(row.get("discovered_turn") or 0)) for row in active_evidence)
                / len(active_evidence),
                3,
            )
        completed_cases = self.investigation_terminal_counts["closed"]
        case_completion_rate = round(
            completed_cases / max(1, len(self.seen_investigation_ids)),
            4,
        )
        average_confidence = _avg_values(
            int(row.get("confidence") or 0) for row in active_investigations
        )
        unsolved_investigations = len(
            [
                row for row in investigations
                if not row.get("solved")
                and str(row.get("status") or "") not in INVESTIGATION_TERMINAL
            ]
        )
        cold_cases = len(
            [
                row for row in investigations
                if (row.get("archived") or str(row.get("status") or "") == "archived")
                and not row.get("solved")
            ]
        )
        metrics_row = {
            "turn": turn,
            "pressure_nodes_total": len(nodes),
            "pressure_nodes_active": len(active_nodes),
            "pressure_created_cum": self.pressure_created_cum,
            "pressure_resolved_cum": len(self.pressure_resolved_ids),
            "pressure_creation_rate": round(self.pressure_created_cum / turns_so_far, 4),
            "pressure_resolution_rate": round(
                len(self.pressure_resolved_ids) / turns_so_far, 4
            ),
            "situations_total": len(situations),
            "situations_active": len(active_situations),
            "situations_resolved_cum": self.situation_terminal_counts["resolved"],
            "situations_failed_cum": self.situation_terminal_counts["failed"],
            "situations_archived_cum": self.situation_archive_count,
            "situation_archive_count": self.situation_archive_count,
            "avg_situation_age": _avg_age(situations, turn, SITUATION_TERMINAL),
            "avg_situation_lifetime": _avg_values(self.situation_lifetimes),
            "world_events_total": len(world_events),
            "active_world_events": len(active_world_events),
            "world_events_resolved_cum": self.world_event_terminal_counts["resolved"],
            "world_events_failed_cum": self.world_event_terminal_counts["failed"],
            "world_events_archived_cum": self.world_event_archive_count,
            "world_event_creation_rate": round(len(self.seen_world_event_ids) / turns_so_far, 4),
            "world_event_resolution_rate": round(
                self.world_event_terminal_counts["resolved"] / turns_so_far, 4
            ),
            "average_world_event_age": _avg_age(world_events, turn, WORLD_EVENT_TERMINAL),
            "average_world_event_lifetime": _avg_values(self.world_event_lifetimes),
            "world_event_merge_count": self.world_event_merge_count,
            "world_event_archive_count": self.world_event_archive_count,
            "world_event_category_counts": dict(sorted(self.world_event_category_counts.items())),
            "active_investigations": len(active_investigations),
            "active_evidence": len(active_evidence),
            "active_information": len(active_information),
            "active_reputation": len(active_reputation),
            "average_evidence_age": average_evidence_age,
            "case_completion_rate": case_completion_rate,
            "average_investigation_lifetime": _avg_values(self.investigation_lifetimes),
            "average_confidence": average_confidence,
            "unsolved_investigations": unsolved_investigations,
            "cold_cases": cold_cases,
            "goals_total": len(goals),
            "goals_active": len(active_goals),
            "goals_completed_cum": self.goal_terminal_counts["completed"],
            "goals_failed_cum": self.goal_terminal_counts["failed"],
            "goals_abandoned_cum": self.goal_terminal_counts["abandoned"],
            "avg_goal_age": _avg_age(goals, turn, GOAL_TERMINAL),
            "avg_goal_lifetime": _avg_values(self.goal_lifetimes),
            "goal_recreation_count": self.goal_recreation_count,
            "npc_actions_total": len(actions),
            "npc_actions_active": len(active_actions),
            "engine_world_events_total": len(events),
            "world_events_appended_turn": len(new_events),
            "world_events_appended_cum": self.events_appended_cum,
            "echoes_scheduled": len(echo_state.get("scheduled") or []),
            "echoes_fired_cum": self.echoes_fired_cum,
            "transition_receipts": len(state.get("transition_receipts") or []),
            "npc_memory_rows": len(npc_memory),
            "npc_memory_entries": memory_entries,
            "retrieval_blocker": str(
                retrieval.get("memory_retrieval_blocker_code") or ""
            ),
            "orphaned_goals": orphaned_goals,
            "orphaned_situations": orphaned_situations,
            "orphaned_world_events": orphaned_world_events,
            "orphaned_evidence": orphaned_evidence,
            "orphaned_investigations": orphaned_investigations,
            "dangling_action_refs": dangling_action_refs,
            "impossible_confidence_rows": impossible_confidence,
            "evidence_cycles": len(cycles),
            "duplicate_id_collections": len(dupes),
            "missing_source_event_id_rows": sum(len(v) for v in missing.values()),
            "prompt_leakage_hits": len(leakage),
            "state_bytes": state_bytes,
            "state_size_bytes": state_bytes,
            "state_within_budget": state_bytes <= STATE_BUDGET_BYTES,
            "budget_warnings": self.budget_warning_count,
            "collections_over_cap": len(bounded["over_cap"]),
            "avg_pressure_lifetime": _avg_values(self.pressure_lifetimes),
            "pressure_decay_count": self.pressure_decay_count,
            "projected_active_goals": len(merged_rolling.get("active_goals") or []),
            "projected_active_situations": len(
                merged_rolling.get("active_situations") or []
            ),
            "projected_active_npc_actions": len(
                merged_rolling.get("active_npc_actions") or []
            ),
            "projected_active_world_events": len(
                merged_rolling.get("active_world_events") or []
            ),
            "projected_active_investigations": len(
                merged_rolling.get("active_investigations") or []
            ),
            "projected_active_information": len(
                merged_rolling.get("active_information") or []
            ),
            "projected_active_reputation": len(
                merged_rolling.get("active_reputation") or []
            ),
            "projected_active_pressures": len(
                merged_rolling.get("active_pressures") or []
            ),
        }
        return metrics_row, timeline[:TIMELINE_EVENTS_PER_TURN_CAP]

    # -- end-of-run aggregates --------------------------------------------------
    def anomaly_records(self) -> List[Dict[str, Any]]:
        return sorted(
            self.anomalies.values(), key=lambda r: (r["code"], r["subject"])
        )

    def anomaly_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for record in self.anomalies.values():
            counts[record["code"]] = counts.get(record["code"], 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Simulation core.
# ---------------------------------------------------------------------------
def init_world(
    seed: str,
    *,
    genre: str = "dark fantasy",
    role: str = "wandering sellsword",
    tone: str = "grounded",
    difficulty: str = "standard",
) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """Deterministic world start via the production init seam (no LLM)."""
    run_seed = f"sim-{seed}"
    state, _directives = replayability.init_new_story(
        genre=genre,
        role=role,
        tone=tone,
        difficulty=difficulty,
        scenario_id=None,
        custom_premise=None,
        custom_world_setup=None,
        scenario=None,
        run_seed=run_seed,
    )
    rolling: Dict[str, Any] = {}
    replayability.enforce_authoritative(rolling, state)
    return state, rolling, run_seed


def advance_turn(
    state: Dict[str, Any],
    prior_rolling: Dict[str, Any],
    turn_number: int,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """
    One headless action turn through the production seams (narration omitted).

    Returns (state, merged_rolling, diagnostics, threshold_events).
    """
    state, _directives, diagnostics, threshold_events, working_rolling = (
        replayability.prepare_action_turn(
            state, turn_number, rolling_state=prior_rolling
        )
    )
    # Headless: the model contributes no rolling_state mutations.
    merged_rolling = copy.deepcopy(working_rolling)

    guard_adjustments: List[str] = []
    world_guard = world_consumers.enforce_consumer_world_state(
        merged_rolling, working_rolling, state, turn_number
    )
    guard_adjustments.extend(world_guard.get("adjustments") or [])

    state, lc_adjustments = replayability.finalize_living_cast_relationships(
        state, merged_rolling, turn_number
    )
    guard_adjustments.extend(lc_adjustments)
    guard_adjustments.extend(
        replayability.enforce_authoritative(merged_rolling, state)
    )
    qualifying_sources = replayability.collect_qualifying_echo_sources(
        prior_rolling=prior_rolling,
        merged_rolling=merged_rolling,
        turn_number=turn_number,
        guard_adjustments=guard_adjustments,
    )
    state = replayability.finalize_action_turn(
        state, qualifying_sources, turn_number
    )
    return state, merged_rolling, diagnostics, threshold_events


def _canonical_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def run_simulation(
    *,
    turns: int,
    seed: str,
    out_dir: Path,
    genre: str = "dark fantasy",
    role: str = "wandering sellsword",
    tone: str = "grounded",
    difficulty: str = "standard",
) -> Dict[str, Any]:
    """
    Run `turns` headless action turns and write all telemetry files.

    Deterministic: identical arguments produce byte-identical outputs.
    Returns the summary dict.
    """
    if turns < 1:
        raise ValueError("turns must be >= 1")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    state, rolling, run_seed = init_world(
        seed, genre=genre, role=role, tone=tone, difficulty=difficulty
    )
    collector = TelemetryCollector()

    start_turn = 2  # turn 1 is the opening created by init_new_story
    end_turn = start_turn + turns - 1
    metrics_path = out_dir / "metrics.jsonl"
    timeline_path = out_dir / "timeline.jsonl"
    metrics_row: Dict[str, Any] = {}
    with metrics_path.open("w", encoding="utf-8", newline="\n") as metrics_f, \
            timeline_path.open("w", encoding="utf-8", newline="\n") as timeline_f:
        for turn in range(start_turn, end_turn + 1):
            state, rolling, diagnostics, threshold_events = advance_turn(
                state, rolling, turn
            )
            metrics_row, timeline_events = collector.observe_turn(
                turn, state, rolling, diagnostics, threshold_events
            )
            metrics_f.write(_canonical_dumps(metrics_row) + "\n")
            for event in timeline_events:
                timeline_f.write(_canonical_dumps(event) + "\n")

    anomaly_records = collector.anomaly_records()
    anomalies_doc = {
        "schema": "sim_anomalies_v1",
        "total": len(anomaly_records),
        "counts_by_code": collector.anomaly_counts(),
        "anomalies": anomaly_records,
    }
    snapshot_doc = {
        "schema": "sim_snapshot_v1",
        "end_turn": end_turn,
        "replayability_state": state,
        "rolling_state": rolling,
    }
    final_bounded = bounded_collection_report(state)
    fingerprint = hashlib.sha256(
        _canonical_dumps(
            {"state": state, "rolling": rolling, "final_metrics": metrics_row}
        ).encode("utf-8")
    ).hexdigest()
    summary = {
        "schema": "sim_summary_v1",
        "config": {
            "turns": turns,
            "seed": str(seed),
            "run_seed": run_seed,
            "genre": genre,
            "role": role,
            "tone": tone,
            "difficulty": difficulty,
            "start_turn": start_turn,
            "end_turn": end_turn,
        },
        "engine": {
            "replayability_version": replayability.REPLAYABILITY_VERSION,
            "state_budget_bytes": STATE_BUDGET_BYTES,
        },
        "final_metrics": metrics_row,
        "aggregates": {
            "mean_active_pressures": round(
                collector.mean_active_pressure_acc / max(1, collector.turns_observed), 4
            ),
            "goals_terminal": dict(collector.goal_terminal_counts),
            "situations_terminal": dict(collector.situation_terminal_counts),
            "investigations_terminal": dict(collector.investigation_terminal_counts),
            "avg_goal_lifetime": _avg_values(collector.goal_lifetimes),
            "avg_pressure_lifetime": _avg_values(collector.pressure_lifetimes),
            "avg_situation_lifetime": _avg_values(collector.situation_lifetimes),
            "average_investigation_lifetime": _avg_values(collector.investigation_lifetimes),
            "average_world_event_lifetime": _avg_values(collector.world_event_lifetimes),
            "world_event_merge_count": collector.world_event_merge_count,
            "world_event_archive_count": collector.world_event_archive_count,
            "world_event_category_counts": dict(sorted(collector.world_event_category_counts.items())),
            "world_events_terminal": dict(collector.world_event_terminal_counts),
            "world_event_recreation_count": collector.world_event_recreation_count,
            "goal_recreation_count": collector.goal_recreation_count,
            "pressure_decay_count": collector.pressure_decay_count,
            "situation_archive_count": collector.situation_archive_count,
            "budget_warnings": collector.budget_warning_count,
            "pressure_created_cum": collector.pressure_created_cum,
            "pressure_resolved_cum": len(collector.pressure_resolved_ids),
            "world_events_appended_cum": collector.events_appended_cum,
            "echoes_fired_cum": collector.echoes_fired_cum,
            "unique_goal_ids": len(collector.seen_goal_ids),
            "unique_situation_ids": len(collector.seen_situation_ids),
            "unique_action_ids": len(collector.seen_action_ids),
            "unique_world_event_ids": len(collector.seen_world_event_ids),
            "unique_evidence_ids": len(collector.seen_evidence_ids),
            "unique_investigation_ids": len(collector.seen_investigation_ids),
            "unique_information_ids": len(collector.seen_information_ids),
            "unique_reputation_signal_ids": len(collector.seen_reputation_signal_ids),
            "unique_engine_world_event_ids": len(collector.seen_event_ids),
            "unique_pressure_ids": len(collector.seen_pressure_ids),
        },
        "bounded_collections": final_bounded,
        "anomaly_total": len(anomaly_records),
        "anomaly_counts": collector.anomaly_counts(),
        "forbidden_modules_preloaded": _FORBIDDEN_PRELOADED,
        "forbidden_modules_imported_by_engine": _FORBIDDEN_IMPORTED_BY_ENGINE,
        "fingerprint": fingerprint,
    }
    (out_dir / "anomalies.json").write_text(
        json.dumps(anomalies_doc, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (out_dir / "final_snapshot.json").write_text(
        json.dumps(snapshot_doc, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (out_dir / "summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return summary


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simulate_world",
        description=(
            "Headless deterministic world simulation (developer telemetry only; "
            "no LLM calls, no narrative, no production routes)."
        ),
    )
    parser.add_argument("--turns", type=int, default=500, help="action turns to simulate")
    parser.add_argument("--seed", required=True, help="deterministic run seed")
    parser.add_argument(
        "--out",
        required=True,
        help="output directory for the telemetry files",
    )
    parser.add_argument("--genre", default="dark fantasy")
    parser.add_argument("--role", default="wandering sellsword")
    parser.add_argument("--tone", default="grounded")
    parser.add_argument("--difficulty", default="standard")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit with status 2 if any anomaly was flagged",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_simulation(
        turns=args.turns,
        seed=str(args.seed),
        out_dir=Path(args.out),
        genre=args.genre,
        role=args.role,
        tone=args.tone,
        difficulty=args.difficulty,
    )
    sys.stdout.write(
        f"simulated {summary['config']['turns']} turns "
        f"(run_seed={summary['config']['run_seed']}) -> {args.out} | "
        f"anomalies={summary['anomaly_total']} "
        f"fingerprint={summary['fingerprint'][:12]}\n"
    )
    if args.strict and summary["anomaly_total"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
