"""E1-E3: the seed is idempotent, its users can log in, and it assigns the manager hierarchy (E3, step 7.1)."""
import pytest
from sqlalchemy import bindparam, text

from scripts.seed import run_seed

SEEDED = {
    "supermanager@example.com": ("MANAGER", "Manager@123"),
    "manager1@example.com": ("MANAGER", "Manager@123"),
    "manager2@example.com": ("MANAGER", "Manager@123"),
    "employee1@example.com": ("EMPLOYEE", "Employee@123"),
    "employee2@example.com": ("EMPLOYEE", "Employee@123"),
    "employee3@example.com": ("EMPLOYEE", "Employee@123"),
    "employee4@example.com": ("EMPLOYEE", "Employee@123"),
}

# email -> the email of that user's manager (None: no manager, the super manager)
MANAGERS = {
    "supermanager@example.com": None,
    "manager1@example.com": "supermanager@example.com",
    "manager2@example.com": "supermanager@example.com",
    "employee1@example.com": "manager1@example.com",
    "employee2@example.com": "manager2@example.com",
    "employee3@example.com": "manager1@example.com",
    "employee4@example.com": "manager2@example.com",
}


def user_codes(engine) -> dict:
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT email, employee_code FROM users")).all())


def manager_emails(engine) -> dict:
    """email -> manager's email (None when manager_id is NULL)."""
    with engine.connect() as conn:
        return dict(
            conn.execute(
                text(
                    "SELECT u.email, m.email FROM users u LEFT JOIN users m ON m.id = u.manager_id"
                )
            ).all()
        )


def test_e1_seed_twice_creates_seven_users_once(engine):
    first = run_seed()
    codes_after_first = user_codes(engine)
    second = run_seed()

    assert first == 7
    assert second == 0
    assert user_codes(engine) == codes_after_first
    assert sorted(codes_after_first) == sorted(SEEDED)
    assert sorted(codes_after_first.values()) == [f"EMP-000{n}" for n in range(1, 8)]

    with engine.connect() as conn:
        balance_rows = conn.execute(text("SELECT count(*) FROM leave_balances")).scalar_one()
        totals = dict(
            conn.execute(
                text("SELECT leave_type, max(total_days) FROM leave_balances GROUP BY leave_type")
            ).all()
        )
    assert balance_rows == 14
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
        assert conn.execute(text("SELECT count(*) FROM leave_balances")).scalar_one() == 14


def test_e1_existing_seed_codes_do_not_shift(engine):
    """New seed users are appended, so the codes the earlier five users already have stay put."""
    run_seed()

    codes = user_codes(engine)

    assert [codes[f"manager{n}@example.com"] for n in (1, 2)] == ["EMP-0001", "EMP-0002"]
    assert [codes[f"employee{n}@example.com"] for n in (1, 2, 3)] == ["EMP-0003", "EMP-0004", "EMP-0005"]


# ---------------------------------------------------------------- hierarchy (step 7.1)


def test_e3_seed_assigns_the_hierarchy(engine):
    run_seed()

    assert manager_emails(engine) == MANAGERS


def test_e3_seed_twice_keeps_the_hierarchy_and_creates_nothing(engine):
    run_seed()
    with engine.connect() as conn:
        ids_after_first = dict(conn.execute(text("SELECT email, id FROM users")).all())
        manager_ids_after_first = dict(conn.execute(text("SELECT email, manager_id FROM users")).all())

    assert run_seed() == 0

    assert manager_emails(engine) == MANAGERS
    with engine.connect() as conn:
        assert dict(conn.execute(text("SELECT email, id FROM users")).all()) == ids_after_first
        assert dict(conn.execute(text("SELECT email, manager_id FROM users")).all()) == manager_ids_after_first
        assert conn.execute(text("SELECT count(*) FROM users")).scalar_one() == 7


def test_e3_exactly_one_seeded_manager_has_no_manager(engine):
    run_seed()

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT email FROM users WHERE role = 'MANAGER' AND manager_id IS NULL")
        ).scalars().all()

    assert rows == ["supermanager@example.com"]


def test_e3_seed_updates_manager_id_on_existing_rows(engine):
    """The five users of the earlier seed already exist, without a hierarchy (or with a wrong one)."""
    run_seed()
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET manager_id = NULL"))
        conn.execute(  # a wrong assignment, to be corrected
            text(
                "UPDATE users SET manager_id = (SELECT id FROM users WHERE email = 'employee1@example.com') "
                "WHERE email = 'employee2@example.com'"
            )
        )

    assert run_seed() == 0

    assert manager_emails(engine) == MANAGERS


def test_e3_seed_moves_users_from_the_previous_assignment_to_the_current_one(engine):
    """Step 7.4: a database seeded with employee1 and employee4 under manager2 and employee2 and
    employee3 under manager1 is repaired in place, with nobody created or renamed."""
    run_seed()
    old = {
        "employee1@example.com": "manager2@example.com",
        "employee2@example.com": "manager1@example.com",
        "employee3@example.com": "manager1@example.com",
        "employee4@example.com": "manager2@example.com",
    }
    with engine.begin() as conn:
        for email, manager in old.items():
            conn.execute(
                text("UPDATE users SET manager_id = (SELECT id FROM users WHERE email = :m) WHERE email = :e"),
                {"e": email, "m": manager},
            )
    assert manager_emails(engine)["employee1@example.com"] == "manager2@example.com"
    codes_before = user_codes(engine)

    assert run_seed() == 0

    assert manager_emails(engine) == MANAGERS
    assert user_codes(engine) == codes_before


def test_e3_employees_split_two_and_two_between_the_managers(engine):
    run_seed()

    by_manager = {}
    for email, manager in manager_emails(engine).items():
        if email.startswith("employee"):
            by_manager.setdefault(manager, []).append(email)

    assert {m: sorted(e) for m, e in by_manager.items()} == {
        "manager1@example.com": ["employee1@example.com", "employee3@example.com"],
        "manager2@example.com": ["employee2@example.com", "employee4@example.com"],
    }


def test_e3_seed_adds_the_new_users_to_a_database_seeded_before_the_hierarchy(engine):
    """Simulates the hosted database: the five old users exist, supermanager and employee4 do not."""
    run_seed()
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET manager_id = NULL"))
        conn.execute(
            text("DELETE FROM leave_balances WHERE user_id IN (SELECT id FROM users WHERE email IN :e)")
            .bindparams(bindparam("e", expanding=True)),
            {"e": ["supermanager@example.com", "employee4@example.com"]},
        )
        conn.execute(
            text("DELETE FROM users WHERE email IN :e").bindparams(bindparam("e", expanding=True)),
            {"e": ["supermanager@example.com", "employee4@example.com"]},
        )
    codes_before = {k: v for k, v in user_codes(engine).items()}

    assert run_seed() == 2

    assert manager_emails(engine) == MANAGERS
    assert {k: user_codes(engine)[k] for k in codes_before} == codes_before


def test_e3_seed_does_not_touch_names_or_passwords_while_fixing_manager_id(engine):
    run_seed()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET name = 'Renamed', password_hash = 'custom', manager_id = NULL WHERE email = 'employee1@example.com'")
        )

    run_seed()

    with engine.connect() as conn:
        name, password_hash = conn.execute(
            text("SELECT name, password_hash FROM users WHERE email = 'employee1@example.com'")
        ).one()
    assert (name, password_hash) == ("Renamed", "custom")
    assert manager_emails(engine)["employee1@example.com"] == "manager1@example.com"


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
