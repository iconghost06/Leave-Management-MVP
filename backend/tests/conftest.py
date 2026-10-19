"""Test harness (DESIGN §8).

Order matters: the environment is configured *before* anything imports the app,
so Settings and the engine bind to the test database and cheap Argon2 settings.
"""
import os
import re
from datetime import date
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


# ---------------------------------------------------------------- step 2.2 fixtures

FROZEN_TODAY = date(2026, 10, 19)  # Monday; Nov 2026 dates used by the tests are in the future


@pytest.fixture
def frozen_today(monkeypatch):
    """Freeze "today" in 2026 by patching its single source (R24)."""
    monkeypatch.setattr("app.core.time.company_today", lambda: FROZEN_TODAY)
    return FROZEN_TODAY


@pytest.fixture
def seeded(engine, frozen_today):
    """The five seed users, with this year's balance rows. Returns {email: user_id}."""
    from scripts.seed import run_seed

    run_seed()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT email, id FROM users")).all()
    return {email: uid for email, uid in rows}


@pytest.fixture
def login_headers(client, seeded):
    """login_headers("employee1") -> {"Authorization": "Bearer ..."}"""
    passwords = {"manager": "Manager@123", "employee": "Employee@123"}

    def _login(name: str) -> dict:
        password = passwords[name.rstrip("0123456789")]
        response = client.post(
            "/auth/login", json={"email": f"{name}@example.com", "password": password}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login


@pytest.fixture
def set_status(engine):
    """Direct SQL status change, because approve/reject do not exist yet (step 2.2).

    Mirrors what a decision writes: APPROVED also moves used_days, so balances stay consistent.
    """

    def _set(request_id: int, status: str, decided_by: int | None = None) -> None:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "UPDATE leave_requests SET status = :s, decided_by = CAST(:d AS bigint), "
                    "decided_at = CASE WHEN CAST(:d AS bigint) IS NULL THEN NULL ELSE now() END "
                    "WHERE id = :id RETURNING user_id, leave_type, days, start_date"
                ),
                {"s": status, "d": decided_by, "id": request_id},
            ).one()
            if status == "APPROVED":
                conn.execute(
                    text(
                        "UPDATE leave_balances SET used_days = used_days + :days "
                        "WHERE user_id = :u AND leave_type = :t AND year = :y"
                    ),
                    {
                        "days": row.days,
                        "u": row.user_id,
                        "t": row.leave_type,
                        "y": row.start_date.year,
                    },
                )

    return _set
