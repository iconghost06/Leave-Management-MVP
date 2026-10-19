"""D1-D3 (MUST), D4 (users.manager_id): the database itself rejects invalid direct writes.

These bypass the application on purpose. They prove the DB-level backstops for
R17 (used range), R9 (overlap exclusion) and R15 (no self-decision) hold even if
a service has a bug. Assertions use SQLSTATE and the constraint name, not message text.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

CHECK_VIOLATION = "23514"
EXCLUSION_VIOLATION = "23P01"


def add_user(conn, n: int, role: str = "EMPLOYEE") -> int:
    return conn.execute(
        text(
            "INSERT INTO users (employee_code, name, email, password_hash, role) "
            "VALUES (:code, :name, :email, 'x', :role) RETURNING id"
        ),
        {
            "code": f"EMP-{n:04d}",
            "name": f"User {n}",
            "email": f"user{n}@example.com",
            "role": role,
        },
    ).scalar_one()


def add_request(
    conn, user_id: int, start: str, end: str, status: str = "PENDING", leave_type: str = "EARNED"
):
    conn.execute(
        text(
            "INSERT INTO leave_requests (user_id, leave_type, start_date, end_date, days, status) "
            "VALUES (:u, :t, :s, :e, 1, :st)"
        ),
        {"u": user_id, "t": leave_type, "s": start, "e": end, "st": status},
    )


def assert_violation(excinfo, sqlstate: str, constraint: str):
    orig = excinfo.value.orig
    assert orig.sqlstate == sqlstate
    assert orig.diag.constraint_name == constraint


# ---------------------------------------------------------------- D1


@pytest.mark.parametrize("bad_used", ["total_days + 1", "-1"])
def test_d1_used_days_outside_range_is_rejected(engine, bad_used):
    with engine.begin() as conn:
        uid = add_user(conn, 1)
        conn.execute(
            text(
                "INSERT INTO leave_balances (user_id, leave_type, year, total_days, used_days) "
                "VALUES (:u, 'EARNED', 2026, 12, 0)"
            ),
            {"u": uid},
        )

    with pytest.raises(IntegrityError) as excinfo:
        with engine.begin() as conn:
            conn.execute(text(f"UPDATE leave_balances SET used_days = {bad_used}"))
    assert_violation(excinfo, CHECK_VIOLATION, "ck_leave_balances_used_range")


def test_d1_used_days_equal_to_total_is_allowed(engine):
    with engine.begin() as conn:
        uid = add_user(conn, 1)
        conn.execute(
            text(
                "INSERT INTO leave_balances (user_id, leave_type, year, total_days, used_days) "
                "VALUES (:u, 'EARNED', 2026, 12, 0)"
            ),
            {"u": uid},
        )
        conn.execute(text("UPDATE leave_balances SET used_days = total_days"))


# ---------------------------------------------------------------- D2


def test_d2_overlapping_pending_inserts_raise_23p01(engine):
    with engine.begin() as conn:
        uid = add_user(conn, 1)
        add_request(conn, uid, "2026-11-02", "2026-11-06")

    with pytest.raises(IntegrityError) as excinfo:
        with engine.begin() as conn:
            add_request(conn, uid, "2026-11-04", "2026-11-10")
    assert_violation(excinfo, EXCLUSION_VIOLATION, "ex_leave_requests_no_overlap")


def test_d2_range_is_inclusive_on_both_ends(engine):
    with engine.begin() as conn:
        uid = add_user(conn, 1)
        add_request(conn, uid, "2026-11-02", "2026-11-06")

    with pytest.raises(IntegrityError) as excinfo:
        with engine.begin() as conn:
            add_request(conn, uid, "2026-11-06", "2026-11-06")  # shares only the end date
    assert_violation(excinfo, EXCLUSION_VIOLATION, "ex_leave_requests_no_overlap")


def test_d2_cross_type_overlap_with_approved_raises_23p01(engine):
    with engine.begin() as conn:
        uid = add_user(conn, 1)
        add_request(conn, uid, "2026-11-02", "2026-11-06", status="APPROVED", leave_type="EARNED")

    with pytest.raises(IntegrityError) as excinfo:
        with engine.begin() as conn:
            add_request(conn, uid, "2026-11-03", "2026-11-03", leave_type="SICK")
    assert_violation(excinfo, EXCLUSION_VIOLATION, "ex_leave_requests_no_overlap")


@pytest.mark.parametrize("old_status", ["REJECTED", "CANCELLED"])
def test_d2_rejected_and_cancelled_do_not_block(engine, old_status):
    with engine.begin() as conn:
        uid = add_user(conn, 1)
        add_request(conn, uid, "2026-11-02", "2026-11-06", status=old_status)
        add_request(conn, uid, "2026-11-02", "2026-11-06")  # same dates, no error


def test_d2_adjacent_ranges_and_other_users_are_allowed(engine):
    with engine.begin() as conn:
        u1 = add_user(conn, 1)
        u2 = add_user(conn, 2)
        add_request(conn, u1, "2026-11-02", "2026-11-06")
        add_request(conn, u1, "2026-11-07", "2026-11-09")  # starts the day after
        add_request(conn, u2, "2026-11-02", "2026-11-06")  # same dates, different user


# ---------------------------------------------------------------- D3


def test_d3_decided_by_equal_to_user_id_is_rejected(engine):
    with engine.begin() as conn:
        uid = add_user(conn, 1, role="MANAGER")
        add_request(conn, uid, "2026-11-02", "2026-11-06")

    with pytest.raises(IntegrityError) as excinfo:
        with engine.begin() as conn:
            conn.execute(text("UPDATE leave_requests SET decided_by = user_id"))
    assert_violation(excinfo, CHECK_VIOLATION, "ck_leave_requests_not_self")


def test_d3_a_different_decider_and_null_decider_are_allowed(engine):
    with engine.begin() as conn:
        requester = add_user(conn, 1)
        manager = add_user(conn, 2, role="MANAGER")
        add_request(conn, requester, "2026-11-02", "2026-11-06")
        conn.execute(text("UPDATE leave_requests SET decided_by = :m"), {"m": manager})
        conn.execute(text("UPDATE leave_requests SET decided_by = NULL"))  # cancel path (Q3)


# ---------------------------------------------------------------- D4 (step 7.1: users.manager_id)


def test_d4_a_user_cannot_be_their_own_manager(engine):
    with engine.begin() as conn:
        add_user(conn, 1, role="MANAGER")

    with pytest.raises(IntegrityError) as excinfo:
        with engine.begin() as conn:
            conn.execute(text("UPDATE users SET manager_id = id"))
    assert_violation(excinfo, CHECK_VIOLATION, "ck_users_manager_not_self")


def test_d4_manager_id_must_point_at_an_existing_user(engine):
    with engine.begin() as conn:
        add_user(conn, 1)

    with pytest.raises(IntegrityError) as excinfo:
        with engine.begin() as conn:
            conn.execute(text("UPDATE users SET manager_id = 999999"))
    assert_violation(excinfo, "23503", "fk_users_manager_id")


def test_d4_null_and_another_user_are_allowed(engine):
    with engine.begin() as conn:
        manager = add_user(conn, 1, role="MANAGER")
        report = add_user(conn, 2)
        conn.execute(text("UPDATE users SET manager_id = :m WHERE id = :r"), {"m": manager, "r": report})
        conn.execute(text("UPDATE users SET manager_id = NULL WHERE id = :r"), {"r": report})


def test_d4_deleting_a_manager_sets_their_reports_manager_id_to_null(engine):
    with engine.begin() as conn:
        manager = add_user(conn, 1, role="MANAGER")
        report = add_user(conn, 2)
        conn.execute(text("UPDATE users SET manager_id = :m WHERE id = :r"), {"m": manager, "r": report})

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :m"), {"m": manager})

    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT manager_id FROM users WHERE id = :r"), {"r": report}
        ).scalar_one() is None
