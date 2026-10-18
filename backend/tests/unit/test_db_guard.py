"""The harness refuses to run against anything but a local *_test database."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.safety import UnsafeTestDatabase, assert_safe_test_database

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://localhost:5432/leave_test",
        "postgresql+psycopg://user:pw@localhost/other_test",
        "postgresql+psycopg://127.0.0.1/leave_test",
    ],
)
def test_local_test_databases_are_accepted(url):
    assert_safe_test_database(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://localhost:5432/leave",  # dev database
        "postgresql+psycopg://localhost/leave_test_backup",  # name must END in _test
        "postgresql+psycopg://db.example.com/leave_test",  # remote host
        "postgresql+psycopg://u:secret@ep-host.neon.tech/leave",  # hosted, wrong name
        "postgresql+psycopg:///leave_test",  # no host (unix socket)
        "not a url",
    ],
)
def test_unsafe_databases_are_refused(url):
    with pytest.raises(UnsafeTestDatabase):
        assert_safe_test_database(url)


def test_refusal_message_does_not_leak_credentials():
    with pytest.raises(UnsafeTestDatabase) as excinfo:
        assert_safe_test_database("postgresql+psycopg://u:hunter2@remote.example.com/leave")
    assert "hunter2" not in str(excinfo.value)


@pytest.mark.parametrize(
    "url",
    ["postgresql+psycopg://localhost/leave", "postgresql+psycopg://remote.example.com/leave_test"],
)
def test_conftest_aborts_the_session_before_touching_the_database(url):
    """End to end: a fresh pytest run with an unsafe TEST_DATABASE_URL fails as a usage error (exit code 4)."""
    env = {**os.environ, "TEST_DATABASE_URL": url}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/api/test_health.py", "-q"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == pytest.ExitCode.USAGE_ERROR
    assert "Refusing to run tests" in result.stdout + result.stderr
