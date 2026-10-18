"""E1-E2 (MUST): the seed is idempotent and its users can log in."""
import pytest
from sqlalchemy import text

from scripts.seed import run_seed

SEEDED = {
    "manager1@example.com": ("MANAGER", "Manager@123"),
    "manager2@example.com": ("MANAGER", "Manager@123"),
    "employee1@example.com": ("EMPLOYEE", "Employee@123"),
    "employee2@example.com": ("EMPLOYEE", "Employee@123"),
    "employee3@example.com": ("EMPLOYEE", "Employee@123"),
}


def user_codes(engine) -> dict:
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT email, employee_code FROM users")).all())


def test_e1_seed_twice_creates_five_users_once(engine):
    first = run_seed()
    codes_after_first = user_codes(engine)
    second = run_seed()

    assert first == 5
    assert second == 0
    assert user_codes(engine) == codes_after_first
    assert sorted(codes_after_first) == sorted(SEEDED)
    assert sorted(codes_after_first.values()) == [f"EMP-000{n}" for n in range(1, 6)]

    with engine.connect() as conn:
        balance_rows = conn.execute(text("SELECT count(*) FROM leave_balances")).scalar_one()
        totals = dict(
            conn.execute(
                text("SELECT leave_type, max(total_days) FROM leave_balances GROUP BY leave_type")
            ).all()
        )
    assert balance_rows == 10
    assert totals == {"EARNED": 12, "SICK": 10}


def test_e1_seed_does_not_touch_existing_users(engine):
    run_seed()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET name = 'Renamed', password_hash = 'custom' WHERE email = :e"),
            {"e": "employee1@example.com"},
        )

    assert run_seed() == 0

    with engine.connect() as conn:
        name, password_hash = conn.execute(
            text("SELECT name, password_hash FROM users WHERE email = 'employee1@example.com'")
        ).one()
    assert (name, password_hash) == ("Renamed", "custom")


def test_e1_seed_backfills_missing_balance_rows(engine):
    run_seed()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM leave_balances"))

    assert run_seed() == 0

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM leave_balances")).scalar_one() == 10


@pytest.mark.parametrize("email", sorted(SEEDED))
def test_e2_seeded_users_can_log_in_with_correct_role(client, email):
    run_seed()
    role, password = SEEDED[email]

    login = client.post("/auth/login", json={"email": email, "password": password})

    assert login.status_code == 200
    assert login.json()["user"]["role"] == role
    me = client.get("/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == email
    assert me.json()["role"] == role
