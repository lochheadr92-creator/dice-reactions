"""Test-environment guard (not collected by pytest).

Several test fixtures delete every session and turn in ``DB_NAME``. The real
local game database is named in ``backend/.env``, which ``server.py`` loads on
import without overriding variables that are already set. So the test process
must set ``DB_NAME`` itself before ``server`` is imported, and must never use a
database that is not clearly a test database.

Rules:
  * The test database is ``TEST_DB_NAME`` when set, else ``dice_reactions_test``.
    ``DB_NAME`` from the shell or ``backend/.env`` is ignored and overwritten.
  * The name must end in ``_test``; anything else stops the run.
  * Provider keys default to empty, so a deterministic run can never pick up
    the real keys from ``backend/.env``. A key exported in the shell is kept
    (an explicit choice for live runs).
"""

from __future__ import annotations

from typing import MutableMapping

DEFAULT_TEST_DB_NAME = "dice_reactions_test"
REQUIRED_SUFFIX = "_test"
PROVIDER_KEY_VARS = ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "NVIDIA_API_KEY")


class UnsafeTestDatabase(RuntimeError):
    """The configured test database name does not look like a test database."""


def resolve_test_db_name(env: MutableMapping[str, str]) -> str:
    name = (env.get("TEST_DB_NAME") or "").strip() or DEFAULT_TEST_DB_NAME
    if not name.endswith(REQUIRED_SUFFIX):
        raise UnsafeTestDatabase(
            f"Refusing to run tests against database {name!r}: the test database name "
            f"must end in {REQUIRED_SUFFIX!r} because test fixtures delete all sessions "
            "and turns. Set TEST_DB_NAME to a disposable *_test database."
        )
    return name


def apply_test_environment(env: MutableMapping[str, str]) -> str:
    name = resolve_test_db_name(env)
    env["DB_NAME"] = name
    env.setdefault("MONGO_URL", "mongodb://localhost:27017")
    for key in PROVIDER_KEY_VARS:
        env.setdefault(key, "")
    return name
