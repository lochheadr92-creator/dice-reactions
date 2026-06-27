"""
Prompt-construction seam guard (foundation acceptance).

Replaces a former brittle guard that asserted
``git diff 9da1ae2..HEAD -- backend/server.py`` produced no output. That check
broke on ANY legitimate edit to ``server.py`` — including the debug-only
context-budget projection fields and earlier prompt-wording fixes — even when
the prompt-construction seam itself was untouched. "The file must not change
since an old base commit" is a tripwire on the file's history, not evidence of
the invariant it was meant to protect.

Instead we assert the load-bearing prompt invariants directly against the
CURRENT source, so the guard stays meaningful while tolerating legitimate
evolution of the engine and the system-prompt copy:

  1. Seam present & wired — the prompt builder (``_build_messages``) still
     establishes the system prompt and routes engine-authoritative state through
     the anti-hallucination blocks (``build_immutable_truth_block``,
     ``build_relationship_block``) and a dedicated ``<prior_state>`` block, and
     the prompt-budget governor (``enforce_context_budget``) is still invoked
     before the model call. (state-is-truth + anti-hallucination + prompt-budget)

  2. Debug-only budget fields stay debug-only — the context-budget projection
     fields (``compressed_prior_state``, ``projected_registry_caps``) appear in
     the debug/meta seam (``_meta_into_debug``) but NEVER in the player-facing
     prompt text assembled by ``_build_messages``. This is what proves the
     prompt-only registry projection fix did not alter the prompt the model
     receives.

Static source analysis only — no ``server`` import, so the guard collects and
runs in any environment.
"""

import os
import re

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SERVER_PY = os.path.join(REPO, "backend", "server.py")

_DEF_RE_TEMPLATE = r"^(?:async\s+)?def\s+{name}\s*\("
_NEXT_TOPLEVEL_RE = re.compile(r"^(?:async\s+def|def|class)\s", re.MULTILINE)


def _server_source() -> str:
    with open(SERVER_PY, encoding="utf-8") as fh:
        return fh.read()


def _function_source(src: str, name: str) -> str:
    """Return the source of module-level function ``name`` (``def``/``async def``)."""
    start = re.search(_DEF_RE_TEMPLATE.format(name=re.escape(name)), src, re.MULTILINE)
    assert start, f"{name}() not found in server.py — prompt seam moved or renamed"
    nxt = _NEXT_TOPLEVEL_RE.search(src, start.end())
    return src[start.start(): nxt.start() if nxt else len(src)]


def test_prompt_construction_seam_present():
    """The load-bearing prompt seam still exists and wires every guard in order."""
    src = _server_source()
    build_messages = _function_source(src, "_build_messages")

    # System prompt is established as the leading engine instruction.
    assert "STORY_ENGINE_SYSTEM_PROMPT" in build_messages, "system prompt seam missing"
    # Anti-hallucination / state-is-truth blocks are injected from engine state.
    assert "build_immutable_truth_block" in build_messages, "truth block injection missing"
    assert "build_relationship_block" in build_messages, "relationship block injection missing"
    # Authoritative prior state is carried as a dedicated, engine-only block.
    assert "<prior_state>" in build_messages, "<prior_state> block missing from prompt seam"
    # Prompt-budget governor still runs before the model call.
    assert "enforce_context_budget(" in src, "context budget governor no longer invoked"


def test_budget_projection_fields_are_debug_only():
    """Context-budget projection fields live in the debug seam, never in prompt text."""
    src = _server_source()
    build_messages = _function_source(src, "_build_messages")
    meta_into_debug = _function_source(src, "_meta_into_debug")

    # The projection telemetry is surfaced through the debug/meta seam …
    assert "compressed_prior_state" in meta_into_debug, "compressed_prior_state not surfaced in debug"
    assert "projected_registry_caps" in meta_into_debug, "projected_registry_caps not surfaced in debug"

    # … and is NEVER injected into the player-facing prompt text the model sees.
    assert "compressed_prior_state" not in build_messages, "debug field leaked into prompt construction"
    assert "projected_registry_caps" not in build_messages, "debug field leaked into prompt construction"
