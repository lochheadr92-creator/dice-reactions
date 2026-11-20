"""The test suite must never run against a non-test database (review finding 1)."""

import os

import pytest

import db_guard


def test_session_database_is_a_test_database():
    assert os.environ["DB_NAME"].endswith("_test")


def test_server_module_uses_the_guarded_database():
    import server

    assert server.db.name == os.environ["DB_NAME"]
    assert server.db.name.endswith("_test")


def test_db_name_from_env_file_or_shell_is_overwritten():
    env = {"DB_NAME": "dice_reaction", "MONGO_URL": "mongodb://127.0.0.1:27017"}
    assert db_guard.apply_test_environment(env) == "dice_reactions_test"
    assert env["DB_NAME"] == "dice_reactions_test"


def test_explicit_test_db_name_is_used():
    env = {"TEST_DB_NAME": "dice_reactions_ci_test"}
    assert db_guard.apply_test_environment(env) == "dice_reactions_ci_test"
    assert env["DB_NAME"] == "dice_reactions_ci_test"


@pytest.mark.parametrize("name", ["dice_reaction", "dice_reactions_ci", "test_dice", "prod"])
def test_non_test_database_names_are_refused(name):
    with pytest.raises(db_guard.UnsafeTestDatabase):
        db_guard.apply_test_environment({"TEST_DB_NAME": name})


def test_provider_keys_default_to_empty_but_keep_shell_values():
    env = {"OPENROUTER_API_KEY": "from-shell"}
    db_guard.apply_test_environment(env)
    assert env["OPENROUTER_API_KEY"] == "from-shell"
    assert env["OPENAI_API_KEY"] == ""
    assert env["NVIDIA_API_KEY"] == ""
