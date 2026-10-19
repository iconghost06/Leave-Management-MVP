"""S1-S10 (MUST): POST /leave-requests (R4-R12, DESIGN §4.1).

APPROVED rows are created with direct SQL (`set_status`), because approve does not exist yet.
"""
import pytest
from sqlalchemy import event

from tests.api.helpers import (
    WEEK_1,
    WEEK_2,
    WEEK_3,
    balance_of,
    count_requests,
    request_row,
    submit,
)


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


# ---------------------------------------------------------------- S1


def test_s1_submit_stores_days_and_status_pending(client, engine, seeded, login_headers):
    headers = login_headers("employee1")

    response = submit(client, headers, *WEEK_1, reason="Family trip")

    assert response.status_code == 201
    out = response.json()
    assert out["days"] == 5
    assert out["status"] == "PENDING"
    assert out["leave_type"] == "EARNED"
    assert (out["start_date"], out["end_date"]) == WEEK_1
    assert out["reason"] == "Family trip"
    assert out["user_id"] == seeded["employee1@example.com"]
    assert out["decided_by"] is None and out["decided_at"] is None
    assert out["decision_comment"] is None
    row = request_row(engine, out["id"])
    assert (row.days, row.status, row.user_id) == (5, "PENDING", out["user_id"])


def test_s1_days_count_working_days_only(client, seeded, login_headers):
    # Fri 6 Nov to Mon 9 Nov: the weekend in between is not counted (R4).
    response = submit(client, login_headers("employee1"), "2026-11-06", "2026-11-09")
    assert response.status_code == 201
    assert response.json()["days"] == 2


def test_s1_a_manager_can_submit_their_own_leave(client, seeded, login_headers):
    response = submit(client, login_headers("manager1"), *WEEK_1)
    assert response.status_code == 201
    assert response.json()["user_id"] == seeded["manager1@example.com"]


def test_s1_submit_requires_authentication(client, frozen_today):
    assert_error(client.post("/leave-requests", json={}), 401, "UNAUTHENTICATED")


def test_s1_unknown_leave_type_is_a_validation_error(client, seeded, login_headers):
    response = submit(client, login_headers("employee1"), *WEEK_1, leave_type="CASUAL")
    assert_error(response, 422, "VALIDATION_ERROR")


def test_s1_submit_takes_locks_in_the_documented_order(client, seeded, login_headers):
    """DESIGN §4.1: advisory -> ensure balance -> lock balance -> overlap -> pending -> insert."""
    from app.db.session import engine as app_engine

    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.split()))

    headers = login_headers("employee1")
    event.listen(app_engine, "before_cursor_execute", record)
    try:
        assert submit(client, headers, *WEEK_1).status_code == 201
    finally:
        event.remove(app_engine, "before_cursor_execute", record)

    def first(fragment: str, after: int = -1) -> int:
        for i, sql in enumerate(statements):
            if i > after and fragment in sql:
                return i
        raise AssertionError(f"{fragment!r} not found in {statements}")

    advisory = first("pg_advisory_xact_lock")
    ensure = first("INSERT INTO leave_balances", advisory)
    lock = first("FOR UPDATE", ensure)
    overlap = first("daterange", lock)
    pending = first("sum(leave_requests.days)", overlap)
    insert = first("INSERT INTO leave_requests", pending)
    assert advisory < ensure < lock < overlap < pending < insert


# ---------------------------------------------------------------- S2


def test_s2_days_above_available_is_insufficient_balance(client, engine, seeded, login_headers):
    headers = login_headers("employee1")

    # Mon 2 Nov to Wed 18 Nov = 13 working days, one more than the 12 Earned entitlement.
    response = submit(client, headers, "2026-11-02", "2026-11-18")

    assert_error(response, 409, "INSUFFICIENT_BALANCE")
    assert count_requests(engine) == 0


def test_s2_days_equal_to_available_is_accepted(client, seeded, login_headers):
    headers = login_headers("employee1")

    # Mon 2 Nov to Tue 17 Nov = exactly 12 working days.
    response = submit(client, headers, "2026-11-02", "2026-11-17")

    assert response.status_code == 201
    assert balance_of(client, headers)["available"] == 0


def test_s2_sick_leave_is_checked_against_the_sick_balance(client, seeded, login_headers):
    headers = login_headers("employee1")
    # 11 working days exceeds Sick (10) although it fits Earned (12).
    assert_error(
        submit(client, headers, "2026-11-02", "2026-11-16", leave_type="SICK"),
        409,
        "INSUFFICIENT_BALANCE",
    )
    assert submit(client, headers, "2026-11-02", "2026-11-16").status_code == 201


# ---------------------------------------------------------------- S3


def test_s3_pending_days_are_reserved(client, engine, seeded, login_headers):
    headers = login_headers("employee1")
    # 8 pending: Mon 2 Nov to Wed 11 Nov.
    assert submit(client, headers, "2026-11-02", "2026-11-11").status_code == 201
    assert balance_of(client, headers)["available"] == 4

    response = submit(client, headers, *WEEK_3)  # 5 more, only 4 left

    assert_error(response, 409, "INSUFFICIENT_BALANCE")
    assert count_requests(engine) == 1
    assert submit(client, headers, "2026-11-16", "2026-11-19").status_code == 201  # 4 fits


# ---------------------------------------------------------------- S4 / S5


def test_s4_overlap_with_pending_is_rejected(client, engine, seeded, login_headers):
    headers = login_headers("employee1")
    assert submit(client, headers, *WEEK_1).status_code == 201

    # Partial overlap: Wed 4 Nov to Tue 10 Nov.
    response = submit(client, headers, "2026-11-04", "2026-11-10")

    assert_error(response, 409, "OVERLAPPING_REQUEST")
    assert count_requests(engine) == 1


def test_s4_a_single_shared_day_counts_as_overlap(client, seeded, login_headers):
    headers = login_headers("employee1")
    assert submit(client, headers, *WEEK_1).status_code == 201
    assert_error(submit(client, headers, "2026-11-06", "2026-11-09"), 409, "OVERLAPPING_REQUEST")


def test_s4_other_users_dates_do_not_block(client, seeded, login_headers):
    assert submit(client, login_headers("employee1"), *WEEK_1).status_code == 201
    assert submit(client, login_headers("employee2"), *WEEK_1).status_code == 201


def test_s5_overlap_with_approved_is_rejected(client, engine, seeded, login_headers, set_status):
    headers = login_headers("employee1")
    first = submit(client, headers, *WEEK_1).json()
    set_status(first["id"], "APPROVED", decided_by=seeded["manager1@example.com"])

    response = submit(client, headers, "2026-11-04", "2026-11-10")

    assert_error(response, 409, "OVERLAPPING_REQUEST")
    assert count_requests(engine) == 1


# ---------------------------------------------------------------- S6


@pytest.mark.parametrize(
    "first_type, second_type", [("EARNED", "SICK"), ("SICK", "EARNED")], ids=["earned-sick", "sick-earned"]
)
def test_s6_overlap_is_checked_across_leave_types(
    client, seeded, login_headers, first_type, second_type
):
    headers = login_headers("employee1")
    assert submit(client, headers, *WEEK_1, leave_type=first_type).status_code == 201

    response = submit(client, headers, "2026-11-04", "2026-11-04", leave_type=second_type)

    assert_error(response, 409, "OVERLAPPING_REQUEST")


# ---------------------------------------------------------------- S7


@pytest.mark.parametrize("old_status", ["REJECTED", "CANCELLED"])
def test_s7_same_dates_after_rejected_or_cancelled_are_accepted(
    client, seeded, login_headers, set_status, old_status
):
    headers = login_headers("employee1")
    first = submit(client, headers, *WEEK_1).json()
    set_status(first["id"], old_status)

    response = submit(client, headers, *WEEK_1)

    assert response.status_code == 201
    assert response.json()["id"] != first["id"]


# ---------------------------------------------------------------- S8


@pytest.mark.parametrize(
    "start, end, code",
    [
        ("2026-11-06", "2026-11-02", "INVALID_DATE_RANGE"),
        ("2026-11-07", "2026-11-08", "NO_WORKING_DAYS"),  # Sat-Sun
        ("2026-12-31", "2027-01-01", "SPANS_MULTIPLE_YEARS"),
        ("2025-11-03", "2025-11-07", "NOT_CURRENT_YEAR"),  # last year
        ("2027-01-04", "2027-01-08", "NOT_CURRENT_YEAR"),  # next year
    ],
)
def test_s8_date_rules_return_their_422_codes(client, engine, seeded, login_headers, start, end, code):
    response = submit(client, login_headers("employee1"), start, end)

    assert_error(response, 422, code)
    assert count_requests(engine) == 0


def test_s8_the_last_working_day_of_the_year_is_accepted(client, seeded, login_headers):
    # Thu 31 Dec 2026 is in the current year, so a one-day request there is valid.
    assert submit(client, login_headers("employee1"), "2026-12-31", "2026-12-31").status_code == 201


def test_s8_backdating_within_the_current_year_is_allowed(client, seeded, login_headers):
    # Frozen today is Mon 19 Oct; Mon 5 Oct is earlier this year (R8).
    assert submit(client, login_headers("employee1"), "2026-10-05", "2026-10-05").status_code == 201


# ---------------------------------------------------------------- S9


def test_s9_reason_over_500_characters_is_rejected(client, engine, seeded, login_headers):
    response = submit(client, login_headers("employee1"), *WEEK_1, reason="x" * 501)

    assert_error(response, 422, "VALIDATION_ERROR")
    assert count_requests(engine) == 0


def test_s9_reason_of_exactly_500_characters_is_accepted(client, seeded, login_headers):
    response = submit(client, login_headers("employee1"), *WEEK_1, reason="x" * 500)
    assert response.status_code == 201
    assert len(response.json()["reason"]) == 500


def test_s9_reason_is_optional(client, seeded, login_headers):
    response = submit(client, login_headers("employee1"), *WEEK_1)
    assert response.status_code == 201
    assert response.json()["reason"] is None


# ---------------------------------------------------------------- S10


def test_s10_overlap_wins_over_insufficient_balance(client, engine, seeded, login_headers):
    headers = login_headers("employee1")
    assert submit(client, headers, "2026-11-02", "2026-11-11").status_code == 201  # 8 days

    # Overlaps the first request AND is 13 days with 4 available: the overlap is reported (R11).
    response = submit(client, headers, "2026-11-04", "2026-11-20")

    assert_error(response, 409, "OVERLAPPING_REQUEST")
    assert count_requests(engine) == 1


def test_s10_date_rules_win_over_overlap_and_balance(client, seeded, login_headers):
    headers = login_headers("employee1")
    assert submit(client, headers, *WEEK_1).status_code == 201
    # end < start, and it also touches WEEK_1: the 422 comes first.
    assert_error(submit(client, headers, "2026-11-06", "2026-11-03"), 422, "INVALID_DATE_RANGE")


# ---------------------------------------------------------------- backstop (R9, §2.1)


def test_exclusion_violation_in_the_insert_maps_to_409(client, engine, seeded, login_headers, monkeypatch):
    """If the app-level overlap check misses (a path that skipped it), the DB constraint
    answers and SQLSTATE 23P01 is mapped to the same 409, not a 500."""
    headers = login_headers("employee1")
    assert submit(client, headers, *WEEK_1).status_code == 201
    monkeypatch.setattr("app.services.leave_request_service._has_overlap", lambda *a, **k: False)

    response = submit(client, headers, "2026-11-04", "2026-11-04", leave_type="SICK")

    assert_error(response, 409, "OVERLAPPING_REQUEST")
    assert count_requests(engine) == 1
