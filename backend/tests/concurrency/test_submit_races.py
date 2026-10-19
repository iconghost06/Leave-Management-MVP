"""X3, X4, X5 (MUST): races between two submits by the same user (DESIGN §4.1, §4.5, §8.3).

The per-user advisory lock serialises the two transactions, so the second one always sees the
first one's committed row. Each scenario runs 20 times; any 500 (including 40P01) fails it.
"""
from datetime import date

from sqlalchemy import text

from app.schemas.leave_request import LeaveRequestIn
from app.services.leave_request_service import submit_request
from tests.api.helpers import WEEK_1
from tests.concurrency.conftest import Call, repeat


def submit_as(user_id: int, leave_type: str, dates: tuple[str, str]) -> Call:
    data = LeaveRequestIn(
        leave_type=leave_type,
        start_date=date.fromisoformat(dates[0]),
        end_date=date.fromisoformat(dates[1]),
    )
    return Call(user_id, lambda db, user: submit_request(db, user, data), ok_status=201)


def active_requests(engine, user_id: int) -> list[tuple]:
    with engine.connect() as conn:
        return [
            tuple(r)
            for r in conn.execute(
                text(
                    "SELECT leave_type, days FROM leave_requests "
                    "WHERE user_id = :u AND status = 'PENDING' ORDER BY id"
                ),
                {"u": user_id},
            )
        ]


# Earned has 12 days. Each range is 7 working days: it fits alone, but 7 + 7 = 14 does not.
SEVEN_DAYS_A = ("2026-11-02", "2026-11-10")  # Mon-Fri + Mon-Tue
SEVEN_DAYS_B = ("2026-11-16", "2026-11-24")  # no overlap with A


@repeat
def test_x3_double_submit_each_fits_alone_but_not_together(attempt, seeded, race, engine):
    uid = seeded["employee1@example.com"]

    first, second = race(
        submit_as(uid, "EARNED", SEVEN_DAYS_A), submit_as(uid, "EARNED", SEVEN_DAYS_B)
    )

    assert sorted([first.status, second.status]) == [201, 409]
    loser = first if first.status == 409 else second
    assert loser.code == "INSUFFICIENT_BALANCE"
    assert active_requests(engine, uid) == [("EARNED", 7)]  # pending 7 <= entitlement 12


@repeat
def test_x4_double_submit_identical_dates(attempt, seeded, race, engine):
    uid = seeded["employee1@example.com"]

    first, second = race(submit_as(uid, "EARNED", WEEK_1), submit_as(uid, "EARNED", WEEK_1))

    assert sorted([first.status, second.status]) == [201, 409]
    loser = first if first.status == 409 else second
    assert loser.code == "OVERLAPPING_REQUEST"
    assert active_requests(engine, uid) == [("EARNED", 5)]


@repeat
def test_x5_double_submit_overlapping_earned_vs_sick(attempt, seeded, race, engine):
    """Different balance rows, so only the advisory lock keeps this from becoming a 40P01 deadlock.

    This proves the outcome (one 201, one 409, no 500, invariants hold). It cannot prove the lock
    is what prevents the deadlock: the deadlock window is a few microseconds and I could not
    widen it reliably. The lock itself is pinned deterministically by the SQL-order test in
    tests/api/test_submit.py.
    """
    uid = seeded["employee1@example.com"]

    earned, sick = race(
        submit_as(uid, "EARNED", WEEK_1),
        submit_as(uid, "SICK", ("2026-11-05", "2026-11-10")),  # shares Thu 5 and Fri 6
    )

    assert sorted([earned.status, sick.status]) == [201, 409]
    loser = earned if earned.status == 409 else sick
    assert loser.code == "OVERLAPPING_REQUEST"
    assert len(active_requests(engine, uid)) == 1
