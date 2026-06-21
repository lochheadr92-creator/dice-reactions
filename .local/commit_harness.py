import subprocess

REPO = r"C:\Users\RJLoc\OneDrive\Desktop\dice-reaction\dice-reactions"
FILES = [
    "backend/utility_dimensions.py",
    "backend/utility_ai.py",
    "backend/foundation_snapshot.py",
    "backend/tests/test_utility_dimensions.py",
    "backend/tests/foundation_acceptance/__init__.py",
    "backend/tests/foundation_acceptance/models.py",
    "backend/tests/foundation_acceptance/delta_ledger.py",
    "backend/tests/foundation_acceptance/comparison.py",
    "backend/tests/foundation_acceptance/coverage.py",
    "backend/tests/foundation_acceptance/artifact.py",
    "backend/tests/foundation_acceptance/adapters.py",
    "backend/tests/foundation_acceptance/utility_oracle.py",
    "backend/tests/foundation_acceptance/test_delta_ledger.py",
    "backend/tests/foundation_acceptance/test_comparison_classifier.py",
    "backend/tests/foundation_acceptance/test_acceptance_artifact.py",
    "backend/tests/foundation_acceptance/test_utility_oracle.py",
    "backend/tests/foundation_acceptance/test_doc_consistency.py",
    "backend/tests/foundation_acceptance/test_prompt_fingerprint.py",
    "backend/tests/foundation_acceptance/test_grace_fixtures.py",
    "backend/tests/foundation_acceptance/test_leakage.py",
    "backend/tests/foundation_acceptance/test_d_sel_activation.py",
    "docs/foundation-canon-deltas.md",
    "docs/foundation-acceptance-harness-v1.md",
    "docs/utility-ai-v01.md",
    "docs/foundation-systems-v01.md",
]

def run(args):
    subprocess.check_call(args, cwd=REPO)

run(["git", "add", *FILES])
run(["git", "commit", "-m", "feat: foundation acceptance harness and utility dimension contract"])
run(["git", "log", "--oneline", "-1"])
run(["git", "diff", "--stat", "9da1ae2..HEAD"])