"""
Run Identity v1 — deterministic replay identity from run_seed + setup.

Closed enums only. Exposes ``has_secret`` as a boolean — never secret text.
Causal dimensions seed opening and pressure systems directly.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Mapping, Optional, Tuple

TENSION_PROFILES = (
    "slow_burn",
    "acute",
    "oscillating",
    "creeping",
    "volatile",
)

STAKE_SHAPES = (
    "personal",
    "relational",
    "survival",
    "reputational",
    "moral",
)

PACING_BIASES = (
    "patient",
    "urgent",
    "alternating",
    "compressed",
)

NPC_TEMPERATURES = (
    "guarded",
    "warm",
    "brittle",
    "predatory",
    "weary",
)

COMPLICATION_STYLES = (
    "social",
    "environmental",
    "resource",
    "political",
    "bodily",
)

REVELATION_PACES = (
    "delayed",
    "early_hints",
    "midgame",
    "late",
)

PRESSURE_KINDS = (
    "resource",
    "social",
    "political",
    "environmental",
    "bodily",
    "moral",
)

SCARCITY_AXES = (
    "medicine",
    "food",
    "fuel",
    "shelter",
    "time",
    "trust",
    "ammo",
    "information",
)

RELATIONSHIP_FAULT_LINES = (
    "loyalty",
    "debt",
    "rivalry",
    "duty",
    "secrets",
    "authority",
)

MORAL_TENSIONS = (
    "duty_vs_survival",
    "truth_vs_safety",
    "mercy_vs_justice",
    "loyalty_vs_gain",
)

OPPORTUNITY_STYLES = (
    "risky_alliance",
    "narrow_window",
    "hidden_leverage",
    "desperate_trade",
)

ECHO_BIASES = (
    "debts",
    "betrayals",
    "violence",
    "losses",
    "exposure",
)

NARRATIVE_ENUM_FIELDS = {
    "tension_profile": TENSION_PROFILES,
    "stake_shape": STAKE_SHAPES,
    "pacing_bias": PACING_BIASES,
    "npc_temperature": NPC_TEMPERATURES,
    "complication_style": COMPLICATION_STYLES,
    "revelation_pace": REVELATION_PACES,
}

CAUSAL_ENUM_FIELDS = {
    "primary_pressure_kind": PRESSURE_KINDS,
    "secondary_pressure_kind": PRESSURE_KINDS,
    "scarcity_axis": SCARCITY_AXES,
    "relationship_fault_line": RELATIONSHIP_FAULT_LINES,
    "moral_tension": MORAL_TENSIONS,
    "opportunity_style": OPPORTUNITY_STYLES,
    "echo_bias": ECHO_BIASES,
}

CLOSED_ENUM_FIELDS = {**NARRATIVE_ENUM_FIELDS, **CAUSAL_ENUM_FIELDS}

DIFFICULTY_SEVERITY = {
    "easy": 0.85,
    "standard": 1.0,
    "hard": 1.15,
    "brutal": 1.3,
}


def _stable_setup_key(setup: Mapping[str, Any]) -> str:
    parts = [
        str(setup.get("genre") or ""),
        str(setup.get("role") or ""),
        str(setup.get("tone") or ""),
        str(setup.get("difficulty") or ""),
        str(setup.get("scenario_id") or ""),
        str(setup.get("custom_premise") or ""),
    ]
    custom = setup.get("custom_world_setup")
    if isinstance(custom, dict):
        for key in sorted(custom.keys()):
            val = custom.get(key)
            if key == "secret":
                parts.append("secret:present" if val else "secret:absent")
            elif isinstance(val, (str, int, float, bool)):
                parts.append(f"{key}:{val}")
    return "|".join(parts)


def select_from_namespace(run_seed: str, namespace: str, options: tuple) -> str:
    """Deterministic index selection via sha256(run_seed:namespace)."""
    if not options:
        raise ValueError("options must not be empty")
    digest = hashlib.sha256(f"{run_seed}:{namespace}".encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(options)
    return options[idx]


def derive_has_secret(setup: Mapping[str, Any]) -> bool:
    """True when setup carries a player secret or scenario hidden threat."""
    custom = setup.get("custom_world_setup")
    if isinstance(custom, dict):
        secret = custom.get("secret")
        if isinstance(secret, str) and secret.strip():
            return True
    hidden = setup.get("hidden_threat")
    if isinstance(hidden, str) and hidden.strip():
        return True
    return False


def difficulty_severity_multiplier(setup: Mapping[str, Any]) -> float:
    """Difficulty scales severity downstream — not identity enum selection."""
    diff = str(setup.get("difficulty") or "standard").strip().lower()
    return DIFFICULTY_SEVERITY.get(diff, 1.0)


def _identity_setup_key(setup: Mapping[str, Any]) -> str:
    """Setup fingerprint for identity enums — excludes difficulty (severity only)."""
    slim = dict(setup)
    slim.pop("difficulty", None)
    return _stable_setup_key(slim)


def derive_run_identity(run_seed: str, setup: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Build closed-enum identity from seed + setup fingerprint.

    The setup fingerprint is mixed into enum namespaces so identical seeds with
    different setups diverge, while identical seed+setup pairs are stable.
    Difficulty adjusts ``severity_multiplier`` only — not enum selection.
    """
    fingerprint = _stable_setup_key(setup)
    identity_key = _identity_setup_key(setup)
    mixed_seed = hashlib.sha256(f"{run_seed}:{identity_key}".encode("utf-8")).hexdigest()

    identity: Dict[str, Any] = {
        "has_secret": derive_has_secret(setup),
        "severity_multiplier": difficulty_severity_multiplier(setup),
    }
    for field, options in CLOSED_ENUM_FIELDS.items():
        identity[field] = select_from_namespace(mixed_seed, field, options)
    identity["setup_fingerprint"] = fingerprint
    return identity


def identity_public_view(identity: Mapping[str, Any]) -> Dict[str, Any]:
    """Player-safe projection — enums + has_secret only."""
    out = {"has_secret": bool(identity.get("has_secret"))}
    for field in CLOSED_ENUM_FIELDS:
        if field in identity:
            out[field] = identity[field]
    return out


def is_closed_enum_identity(identity: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(identity, dict):
        return False
    for field, options in CLOSED_ENUM_FIELDS.items():
        if identity.get(field) not in options:
            return False
    return isinstance(identity.get("has_secret"), bool)


def causal_fields_tuple(identity: Mapping[str, Any]) -> Tuple[str, ...]:
    return tuple(str(identity.get(f) or "") for f in CAUSAL_ENUM_FIELDS)