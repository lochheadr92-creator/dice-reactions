import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from foundation_acceptance.artifact import artifact_bytes, artifact_hash, build_artifact
from foundation_acceptance.delta_ledger import LEDGER_VERSION, build_delta_ledger, ledger_hash


def test_artifact_byte_identical():
    entries = build_delta_ledger()
    l_hash = ledger_hash(entries)
    art = build_artifact(
        ledger_entries=entries,
        ledger_version=LEDGER_VERSION,
        l_hash=l_hash,
        corpus_version="0",
        corpus_hash="none",
        commit_sha="9da1ae2",
        records=[{"classification": "MATCH", "fixture_id": "f1"}],
    )
    b1 = artifact_bytes(art)
    b2 = artifact_bytes(art)
    assert b1 == b2
    assert artifact_hash(art) == artifact_hash(art)