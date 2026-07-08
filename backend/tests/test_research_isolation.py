"""Guard: production runtime code must never read or import the research tree.

ADR-026 (`docs/adr-026-research-runtime-isolation.md`) establishes that
material under the locations named in RESEARCH_MARKERS is non-runtime
documentation. It may inform future development but must never be imported,
opened, or otherwise consumed by the deployed application until an explicit
migration decision promotes a specific concept (a separate, dedicated ADR).

This guard is deliberately narrow and cheap to maintain:

1. No production runtime source file (backend excluding tests/, frontend
   app/ and src/ excluding __tests__/) or tracked build/deploy config may
   contain a literal reference to a known research-location marker.
2. No production backend source file may call a generic recursive
   filesystem-walk primitive (os.walk / Path.rglob / glob.glob). None
   currently do -- this keeps it that way. If a future feature legitimately
   needs one outside the research boundary, that is a deliberate change:
   extend this file's scope deliberately rather than letting the check rot.

It intentionally does NOT scan tests/ or docs/ -- referring to the research
path in a test (like this file) or in documentation is expected and is not
a violation.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Iterator

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
FRONTEND_DIR = REPO_ROOT / "frontend"

# Known non-runtime research locations (ADR-026). Add new research roots
# here if they are ever introduced -- do NOT add runtime directories.
RESEARCH_MARKERS = (
    "Simulation-Kernel-Research",
    "simulation-kernel-research",
    "simulation_kernel_research",
)

# Build / deploy configuration that could package or reference the research
# tree without ever being "source code".
_CONFIG_FILES = (
    BACKEND_DIR / "requirements.txt",
    FRONTEND_DIR / "package.json",
    FRONTEND_DIR / "app.json",
    FRONTEND_DIR / "metro.config.js",
    REPO_ROOT / ".github" / "workflows" / "deterministic-ci.yml",
    REPO_ROOT / ".emergent" / "emergent.yml",
)

_WALK_PATTERN = re.compile(r"os\.walk\(|\.rglob\(|glob\.glob\(")

# Never our own runtime source: virtualenvs, caches, and VCS metadata that
# may happen to exist inside backend/ in a given checkout. Third-party
# dependency code is explicitly out of scope for this guard.
_EXCLUDED_DIR_NAMES = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    "site-packages",
}


def _iter_backend_runtime_files() -> Iterator[Path]:
    for path in BACKEND_DIR.rglob("*.py"):
        rel = path.relative_to(BACKEND_DIR)
        if rel.parts[0] == "tests":
            continue
        if _EXCLUDED_DIR_NAMES.intersection(rel.parts):
            continue
        yield path


def _iter_frontend_runtime_files() -> Iterator[Path]:
    for sub in ("app", "src"):
        base = FRONTEND_DIR / sub
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in (".ts", ".tsx", ".js", ".jsx"):
                continue
            if "__tests__" in path.parts:
                continue
            yield path


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _marker_offenders(paths: Iterable[Path]) -> list[str]:
    hits = []
    for path in paths:
        text = _read(path)
        for marker in RESEARCH_MARKERS:
            if marker in text:
                hits.append(f"{path}: contains {marker!r}")
    return hits


def test_backend_runtime_does_not_reference_research_tree():
    hits = _marker_offenders(_iter_backend_runtime_files())
    assert not hits, (
        "Backend runtime code must not reference the research tree "
        "(ADR-026):\n" + "\n".join(hits)
    )


def test_frontend_runtime_does_not_reference_research_tree():
    hits = _marker_offenders(_iter_frontend_runtime_files())
    assert not hits, (
        "Frontend runtime code must not reference the research tree "
        "(ADR-026):\n" + "\n".join(hits)
    )


def test_build_and_deploy_config_does_not_reference_research_tree():
    hits = _marker_offenders(p for p in _CONFIG_FILES if p.exists())
    assert not hits, (
        "Build/deploy configuration must not reference the research tree "
        "(ADR-026):\n" + "\n".join(hits)
    )


def test_backend_runtime_has_no_recursive_filesystem_walk():
    hits = []
    for path in _iter_backend_runtime_files():
        if _WALK_PATTERN.search(_read(path)):
            hits.append(str(path))
    assert not hits, (
        "Production backend code must not perform recursive filesystem "
        "walks (os.walk/.rglob/glob.glob) -- see ADR-026. This keeps "
        "docs/research directories from ever being swept into a prompt or "
        "config path by accident. Offending files:\n" + "\n".join(hits)
    )
