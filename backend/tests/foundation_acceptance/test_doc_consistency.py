import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from foundation_acceptance.delta_ledger import build_delta_ledger

DOC_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "docs", "foundation-canon-deltas.md"
)


def _read_doc():
    with open(DOC_PATH, encoding="utf-8") as fh:
        return fh.read()


def test_executable_delta_ids_in_markdown():
    entries = build_delta_ledger()
    doc = _read_doc()
    for entry in entries:
        assert entry.id in doc, f"missing delta id {entry.id} in foundation-canon-deltas.md"


def test_machine_checkable_deltas_have_executable_entries():
    doc = _read_doc()
    for entry in build_delta_ledger():
        if entry.status.value in ("ACTIVE", "PLACEHOLDER_BLOCKED"):
            assert f"`{entry.id}`" in doc or entry.id in doc