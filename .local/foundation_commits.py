import subprocess
import sys

REPO = r"C:\Users\RJLoc\OneDrive\Desktop\dice-reaction\dice-reactions"

COMMITS = [
    (
        "feat: add foundation determinism primitives",
        [
            "backend/engine_determinism.py",
            "backend/engine_projection.py",
            "backend/tests/test_engine_determinism.py",
        ],
    ),
    (
        "feat: implement actor resolution v0.1",
        ["backend/actor_resolution.py", "backend/tests/test_actor_resolution.py"],
    ),
    (
        "feat: implement gravity governance v0.1",
        ["backend/gravity_governance.py", "backend/tests/test_gravity_governance.py"],
    ),
    (
        "feat: implement utility ai v0.1",
        ["backend/utility_ai.py", "backend/tests/test_utility_ai.py"],
    ),
    (
        "feat: implement memory retrieval v0.1",
        [
            "backend/foundation_snapshot.py",
            "backend/memory_retrieval.py",
            "backend/tests/test_memory_retrieval.py",
        ],
    ),
    (
        "test: verify foundation systems integration",
        [
            "backend/foundation_integration.py",
            "backend/replayability.py",
            "backend/tests/test_foundation_integration.py",
        ],
    ),
    (
        "docs: document foundation systems v0.1",
        [
            "docs/foundation-canon-source-map.md",
            "docs/foundation-canon-deltas.md",
            "docs/actor-resolution-v01.md",
            "docs/gravity-governance-v01.md",
            "docs/utility-ai-v01.md",
            "docs/memory-retrieval-v01.md",
            "docs/foundation-systems-v01.md",
        ],
    ),
]


def run(args):
    print("+", " ".join(args))
    subprocess.check_call(args, cwd=REPO)


def main():
    for message, files in COMMITS:
        run(["git", "add", *files])
        run(["git", "commit", "-m", message])
    run(["git", "log", "--oneline", "-7"])


if __name__ == "__main__":
    main()