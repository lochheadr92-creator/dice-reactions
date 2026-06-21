"""Corpus source interfaces — no database queries."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Mapping, Optional, Protocol

from .models import BaselineSource, ComparisonInput


class FixtureSource(ABC):
    @abstractmethod
    def iter_fixtures(self) -> Iterable[Dict[str, Any]]:
        raise NotImplementedError


class SyntheticFixtureSource(FixtureSource):
    def __init__(self, fixtures: Iterable[Dict[str, Any]]):
        self._fixtures = tuple(fixtures)

    def iter_fixtures(self) -> Iterable[Dict[str, Any]]:
        return self._fixtures


class ExistingTestFixtureSource(FixtureSource):
    """Wraps in-repo deterministic test payloads."""

    def __init__(self, fixtures: Iterable[Dict[str, Any]]):
        self._fixtures = tuple(fixtures)

    def iter_fixtures(self) -> Iterable[Dict[str, Any]]:
        return self._fixtures


class LocalTurnSnapshotSource(FixtureSource):
    def __init__(self, snapshots: Iterable[Mapping[str, Any]]):
        self._snapshots = tuple(snapshots)

    def iter_fixtures(self) -> Iterable[Dict[str, Any]]:
        for snap in self._snapshots:
            yield {"kind": "turn_snapshot", "payload": dict(snap)}


class LocalSessionSnapshotSource(FixtureSource):
    def __init__(self, sessions: Iterable[Mapping[str, Any]]):
        self._sessions = tuple(sessions)

    def iter_fixtures(self) -> Iterable[Dict[str, Any]]:
        for session in self._sessions:
            yield {"kind": "session_snapshot", "payload": dict(session)}


class OptionalPersistedDecisionSource(FixtureSource):
    """Interface for future recorded decisions — not wired to Mongo."""

    def __init__(self, decisions: Optional[Iterable[Mapping[str, Any]]] = None):
        self._decisions = tuple(decisions or ())

    def iter_fixtures(self) -> Iterable[Dict[str, Any]]:
        return self._decisions


class BaselineStore(Protocol):
    def load(self, fixture_id: str) -> Optional[Mapping[str, Any]]: ...


def normalise_comparison_input(raw: Mapping[str, Any]) -> ComparisonInput:
    return ComparisonInput(
        schema_version=int(raw.get("schema_version", 1)),
        fixture_id=str(raw["fixture_id"]),
        source_state_hash=str(raw.get("source_state_hash", "")),
        run_seed=str(raw.get("run_seed", "")),
        turn_sequence=int(raw.get("turn_sequence", 0)),
        canonical_actor_registry=tuple(raw.get("canonical_actor_registry") or ()),
        provisional_state=dict(raw.get("provisional_state") or {}),
        foundation_snapshot=dict(raw.get("foundation_snapshot") or {}),
        pressure_refs=tuple(raw.get("pressure_refs") or ()),
        consequence_refs=tuple(raw.get("consequence_refs") or ()),
        relationship_refs=tuple(raw.get("relationship_refs") or ()),
        agenda_refs=tuple(raw.get("agenda_refs") or ()),
        location_ref=str(raw.get("location_ref", "")),
        secret_access_flags=tuple(raw.get("secret_access_flags") or ()),
        schema_versions=dict(raw.get("schema_versions") or {}),
        baseline_source=raw.get("baseline_source", "NO_BASELINE_AVAILABLE"),
        baseline_selector_commit=str(raw.get("baseline_selector_commit", "")),
        baseline_result_hash=str(raw.get("baseline_result_hash", "")),
        provisional_result=dict(raw.get("provisional_result") or {}),
        foundation_result=dict(raw.get("foundation_result") or {}),
        utility_inputs_complete=bool(raw.get("utility_inputs_complete")),
    )