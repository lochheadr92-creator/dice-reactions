import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def test_server_prompt_unchanged_since_base():
    result = subprocess.run(
        ["git", "diff", "9da1ae2..HEAD", "--", "backend/server.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout.strip() == "", "server.py prompt construction changed"