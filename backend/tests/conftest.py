"""Test harness (DESIGN §8).

Order matters: the environment is configured *before* anything imports the app,
so Settings and the engine bind to the test database and cheap Argon2 settings.
"""
import os
import re
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests.safety import UnsafeTestDatabase, assert_safe_test_database

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _dotenv_value(key: str) -> str | None:
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return None
    match = re.search(rf"^{key}=(.*)$", env_file.read_text(), re.MULTILINE)
    return match.group(1).strip() if match else None


TEST_DATABASE_URL = (
    os.environ.get("TEST_DATABASE_URL")
    or _dotenv_value("TEST_DATABASE_URL")
    or "postgresql+psycopg://localhost:5432/leave_test"
)

# Must run before anything below migrates or truncates.
try:
    assert_safe_test_database(TEST_DATABASE_URL)
except UnsafeTestDatabase as exc:
    raise pytest.UsageError(str(exc)) from None

os.environ["PASSWORD_HASH_FAST"] = "true"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef")
os.environ.setdefault("SIGNUP_CODE", "test-join-code")


@pytest.fixture(scope="session")
def engine():
    """Migrate the test DB once per session. Never uses metadata.create_all."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    eng = create_engine(TEST_DATABASE_URL)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def reset_db(engine):
    """Truncate between tests.

    TRUNCATE ... RESTART IDENTITY resets identity columns only. The standalone
    employee_code_seq must be restarted explicitly or EMP-0001 assertions drift.
    """
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE users, leave_balances, leave_requests RESTART IDENTITY CASCADE")
        )
        conn.execute(text("ALTER SEQUENCE employee_code_seq RESTART WITH 1"))
    yield


@pytest.fixture
def client(engine):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
