"""X1, X2, X6 (MUST): races between approve, cancel and other decisions (DESIGN §4.2, §4.4, §4.5, §8.3).

Each scenario runs 20 times. The harness fails on any non-AppError exception (a 500) and checks the
invariants after every run (see conftest.py).
"""
from app.services.approval_service import approve_request, reject_request
from app.services.leave_request_service import cancel_request
from tests.api.helpers import WEEK_1, WEEK_2
from tests.concurrency.conftest import Call, repeat


def approve_as(user_id: int, request_id: int) -> Call:
    return Call(user_id, lambda db, user: approve_request(db, user, request_id))


def reject_as(user_id: int, request_id: int) -> Call:
    return Call(user_id, lambda db, user: reject_request(db, user, request_id, "No"))


def cancel_as(user_id: int, request_id: int) -> Call:
    return Call(user_id, lambda db, user: cancel_request(db, user, request_id))


@repeat
def test_x1_double_approval_one_wins_one_already_actioned(
    attempt, seeded, race, create_request, snapshot, used_of
):
    m1, m2 = seeded["manager1@example.com"], seeded["manager2@example.com"]
    rid = create_request("employee1", WEEK_1)

    first, second = race(approve_as(m1, rid), approve_as(m2, rid))

    assert sorted([first.status, second.status]) == [200, 409]
    loser = first if first.status == 409 else second
    assert loser.code == "ALREADY_ACTIONED"
    winner_id = m1 if first.status == 200 else m2
    status, decided_by = snapshot(rid)
    assert (status, decided_by) == ("APPROVED", winner_id)
    assert used_of(seeded["employee1@example.com"]) == 5  # incremented once, not twice


@repeat
def test_x2_two_requests_that_both_fit_are_both_approved(
    attempt, seeded, race, create_request, snapshot, used_of
):
    m1, m2 = seeded["manager1@example.com"], seeded["manager2@example.com"]
    a = create_request("employee1", WEEK_1)  # 5 days
    b = create_request("employee1", WEEK_2)  # 5 days; 10 <= 12

    first, second = race(approve_as(m1, a), approve_as(m2, b))

    assert (first.status, second.status) == (200, 200)
    assert snapshot(a) == ("APPROVED", m1)
    assert snapshot(b) == ("APPROVED", m2)
    assert used_of(seeded["employee1@example.com"]) == 10  # both increments survive (no lost update)


@repeat
def test_x6_cancel_vs_approve_exactly_one_succeeds(
    attempt, seeded, race, create_request, snapshot, used_of
):
    employee, manager = seeded["employee1@example.com"], seeded["manager1@example.com"]
    rid = create_request("employee1", WEEK_1)

    cancelled, approved = race(cancel_as(employee, rid), approve_as(manager, rid))

    assert sorted([cancelled.status, approved.status]) == [200, 409]
    loser = approved if cancelled.status == 200 else cancelled
    assert loser.code == "ALREADY_ACTIONED"
    status, decided_by = snapshot(rid)
    if approved.status == 200:
        assert (status, decided_by) == ("APPROVED", manager)
        assert used_of(employee) == 5
    else:
        assert (status, decided_by) == ("CANCELLED", None)
        assert used_of(employee) == 0  # used matches the final status


# ---------------------------------------------------------------- SHOULD


@repeat
def test_x7_approve_vs_reject_exactly_one_succeeds(
    attempt, seeded, race, create_request, snapshot, used_of
):
    m1, m2 = seeded["manager1@example.com"], seeded["manager2@example.com"]
    rid = create_request("employee1", WEEK_1)

    approved, rejected = race(approve_as(m1, rid), reject_as(m2, rid))

    assert sorted([approved.status, rejected.status]) == [200, 409]
    loser = rejected if approved.status == 200 else approved
    assert loser.code == "ALREADY_ACTIONED"
    status, _ = snapshot(rid)
    if approved.status == 200:
        assert status == "APPROVED" and used_of(seeded["employee1@example.com"]) == 5
    else:
        assert status == "REJECTED" and used_of(seeded["employee1@example.com"]) == 0
