"""P1-P4, P6-P9 (MUST): POST /leave-requests/{id}/approve and /reject (R14-R18, DESIGN §4.2, §4.3, Q4, Q5).

P5 (SHOULD, self check before status) is at the end of the file.
"""
import pytest
from sqlalchemy import text

from tests.api.helpers import WEEK_1, WEEK_2, balance_of, request_row, submit


def approve(client, headers, request_id: int, **json):
    return client.post(f"/leave-requests/{request_id}/approve", headers=headers, json=json or None)


def reject(client, headers, request_id: int, **json):
    return client.post(f"/leave-requests/{request_id}/reject", headers=headers, json=json or None)


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def used_days(engine, user_id: int, leave_type: str = "EARNED") -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT used_days FROM leave_balances WHERE user_id = :u AND leave_type = :t"),
            {"u": user_id, "t": leave_type},
        ).scalar_one()


# ---------------------------------------------------------------- P1


def test_p1_approve_marks_approved_and_adds_days_to_used(client, engine, seeded, login_headers):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()

    response = approve(client, login_headers("manager1"), created["id"])

    assert response.status_code == 200, response.text
    out = response.json()
    assert out["id"] == created["id"]
    assert out["status"] == "APPROVED"
    assert out["decided_by"] == seeded["manager1@example.com"]
    assert out["decided_by_name"] == "Manager One"
    assert out["decided_at"] is not None
    assert out["requester_name"] == "Employee One"
    row = request_row(engine, created["id"])
    assert row.status == "APPROVED" and row.decided_by == seeded["manager1@example.com"]
    assert row.decided_at is not None
    assert used_days(engine, seeded["employee1@example.com"]) == 5


def test_p1_optional_comment_is_stored(client, engine, seeded, login_headers):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()

    out = approve(client, login_headers("manager1"), created["id"], comment="  Enjoy!  ").json()

    assert out["decision_comment"] == "Enjoy!"
    assert request_row(engine, created["id"]).decision_comment == "Enjoy!"


def test_p1_without_a_comment_it_stays_null(client, seeded, login_headers):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()

    out = approve(client, login_headers("manager1"), created["id"], comment="   ").json()

    assert out["decision_comment"] is None


def test_p1_approve_only_moves_the_matching_balance(client, engine, seeded, login_headers):
    created = submit(client, login_headers("employee1"), *WEEK_1, leave_type="SICK").json()

    approve(client, login_headers("manager1"), created["id"])

    uid = seeded["employee1@example.com"]
    assert used_days(engine, uid, "SICK") == 5
    assert used_days(engine, uid, "EARNED") == 0


def test_p1_unknown_request_is_404(client, seeded, login_headers):
    response = approve(client, login_headers("manager1"), 999999)

    assert_error(response, 404, "NOT_FOUND")
    assert "Leave request" in response.json()["message"]


def test_p1_approve_requires_authentication(client, seeded):
    assert_error(client.post("/leave-requests/1/approve"), 401, "UNAUTHENTICATED")
    assert_error(client.post("/leave-requests/1/reject"), 401, "UNAUTHENTICATED")


# ---------------------------------------------------------------- P2


def test_p2_reject_with_comment_marks_rejected_and_leaves_balance(
    client, engine, seeded, login_headers
):
    employee = login_headers("employee1")
    created = submit(client, employee, *WEEK_1).json()

    response = reject(client, login_headers("manager1"), created["id"], comment="Team is short")

    assert response.status_code == 200, response.text
    out = response.json()
    assert out["status"] == "REJECTED"
    assert out["decision_comment"] == "Team is short"
    assert out["decided_by"] == seeded["manager1@example.com"]
    assert out["decided_by_name"] == "Manager One"
    assert out["decided_at"] is not None
    assert used_days(engine, seeded["employee1@example.com"]) == 0
    # The reservation is released, so the days are available again.
    assert balance_of(client, employee) == {
        "leave_type": "EARNED", "entitlement": 12, "used": 0, "pending": 0, "available": 12,
    }


def test_p2_rejected_range_can_be_requested_again(client, seeded, login_headers):
    employee = login_headers("employee1")
    created = submit(client, employee, *WEEK_1).json()
    reject(client, login_headers("manager1"), created["id"], comment="No")

    assert submit(client, employee, *WEEK_1).status_code == 201


# ---------------------------------------------------------------- P3


@pytest.mark.parametrize("action", [approve, reject])
def test_p3_employee_cannot_decide_someone_elses_request(
    client, engine, seeded, login_headers, action
):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()

    response = action(client, login_headers("employee2"), created["id"], comment="x")

    assert_error(response, 403, "FORBIDDEN")
    assert request_row(engine, created["id"]).status == "PENDING"
    assert used_days(engine, seeded["employee1@example.com"]) == 0


@pytest.mark.parametrize("action", [approve, reject])
def test_p3_employee_cannot_decide_their_own_request_either(client, seeded, login_headers, action):
    employee = login_headers("employee1")
    created = submit(client, employee, *WEEK_1).json()

    # Role gate first: FORBIDDEN, not SELF_ACTION_FORBIDDEN.
    assert_error(action(client, employee, created["id"], comment="x"), 403, "FORBIDDEN")


@pytest.mark.parametrize("action", [approve, reject])
def test_p3_role_gate_runs_before_the_lookup(client, seeded, login_headers, action):
    assert_error(action(client, login_headers("employee1"), 999999, comment="x"), 403, "FORBIDDEN")


# ---------------------------------------------------------------- P4


@pytest.mark.parametrize("action", [approve, reject])
def test_p4_manager_cannot_decide_their_own_request(client, engine, seeded, login_headers, action):
    manager = login_headers("manager1")
    created = submit(client, manager, *WEEK_1).json()

    response = action(client, manager, created["id"], comment="mine")

    assert_error(response, 403, "SELF_ACTION_FORBIDDEN")
    row = request_row(engine, created["id"])
    assert row.status == "PENDING" and row.decided_by is None
    assert used_days(engine, seeded["manager1@example.com"]) == 0


# ---------------------------------------------------------------- P6


@pytest.mark.parametrize("action", [approve, reject])
@pytest.mark.parametrize("final_status", ["APPROVED", "REJECTED", "CANCELLED"])
def test_p6_acting_on_a_non_pending_request_is_already_actioned(
    client, engine, seeded, login_headers, set_status, action, final_status
):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()
    decider = seeded["manager2@example.com"] if final_status != "CANCELLED" else None
    set_status(created["id"], final_status, decided_by=decider)
    used_before = used_days(engine, seeded["employee1@example.com"])

    response = action(client, login_headers("manager1"), created["id"], comment="late")

    assert_error(response, 409, "ALREADY_ACTIONED")
    assert request_row(engine, created["id"]).status == final_status
    assert used_days(engine, seeded["employee1@example.com"]) == used_before


def test_p6_second_approve_does_not_add_days_twice(client, engine, seeded, login_headers):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()
    assert approve(client, login_headers("manager1"), created["id"]).status_code == 200

    assert_error(approve(client, login_headers("manager2"), created["id"]), 409, "ALREADY_ACTIONED")

    assert used_days(engine, seeded["employee1@example.com"]) == 5


def test_p6_a_cancelled_request_cannot_be_approved(client, seeded, login_headers):
    employee = login_headers("employee1")
    created = submit(client, employee, *WEEK_1).json()
    client.post(f"/leave-requests/{created['id']}/cancel", headers=employee)

    assert_error(approve(client, login_headers("manager1"), created["id"]), 409, "ALREADY_ACTIONED")


# ---------------------------------------------------------------- P7


@pytest.mark.parametrize("payload", [{}, {"comment": None}, {"comment": ""}, {"comment": "   \n\t"}])
def test_p7_reject_without_a_real_comment_is_422(client, engine, seeded, login_headers, payload):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()
    manager = login_headers("manager1")

    response = client.post(
        f"/leave-requests/{created['id']}/reject", headers=manager, json=payload
    )

    assert_error(response, 422, "COMMENT_REQUIRED")
    assert request_row(engine, created["id"]).status == "PENDING"


def test_p7_reject_with_no_body_at_all_is_comment_required(client, seeded, login_headers):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()

    response = client.post(
        f"/leave-requests/{created['id']}/reject", headers=login_headers("manager1")
    )

    assert_error(response, 422, "COMMENT_REQUIRED")


def test_p7_blank_comment_on_an_actioned_request_is_409_not_422(
    client, seeded, login_headers, set_status
):
    """Q5: the status check comes first, so COMMENT_REQUIRED only applies to a PENDING request."""
    created = submit(client, login_headers("employee1"), *WEEK_1).json()
    set_status(created["id"], "APPROVED", decided_by=seeded["manager2@example.com"])

    response = reject(client, login_headers("manager1"), created["id"], comment="  ")

    assert_error(response, 409, "ALREADY_ACTIONED")


def test_p7_self_check_still_beats_the_comment_check(client, seeded, login_headers):
    manager = login_headers("manager1")
    created = submit(client, manager, *WEEK_1).json()

    assert_error(reject(client, manager, created["id"], comment=" "), 403, "SELF_ACTION_FORBIDDEN")


def test_p7_comment_is_trimmed_and_capped_at_500(client, seeded, login_headers):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()
    manager = login_headers("manager1")

    too_long = reject(client, manager, created["id"], comment="x" * 501)
    assert_error(too_long, 422, "VALIDATION_ERROR")

    ok = reject(client, manager, created["id"], comment="  needs cover  ")
    assert ok.json()["decision_comment"] == "needs cover"


# ---------------------------------------------------------------- P8


def test_p8_forced_impossible_state_is_insufficient_balance(client, engine, seeded, login_headers):
    """Submit reserves pending days, so this state is only reachable by editing the balance directly."""
    uid = seeded["employee1@example.com"]
    created = submit(client, login_headers("employee1"), *WEEK_1).json()  # 5 days
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE leave_balances SET used_days = total_days - 1 WHERE user_id = :u AND leave_type = 'EARNED'"),
            {"u": uid},
        )
    assert used_days(engine, uid) == 11

    response = approve(client, login_headers("manager1"), created["id"])

    assert_error(response, 409, "INSUFFICIENT_BALANCE")
    assert used_days(engine, uid) == 11
    row = request_row(engine, created["id"])
    assert row.status == "PENDING" and row.decided_by is None


def test_p8_exactly_filling_the_balance_is_allowed(client, engine, seeded, login_headers):
    uid = seeded["employee1@example.com"]
    created = submit(client, login_headers("employee1"), *WEEK_1).json()  # 5 days
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE leave_balances SET used_days = 7 WHERE user_id = :u AND leave_type = 'EARNED'"),
            {"u": uid},
        )

    assert approve(client, login_headers("manager1"), created["id"]).status_code == 200
    assert used_days(engine, uid) == 12


def test_p8_the_check_constraint_maps_to_409_when_the_app_check_is_bypassed(
    client, engine, seeded, login_headers, monkeypatch
):
    """23514 on ck_leave_balances_used_range is the backstop for the app-level check (§2.1)."""
    from app.services import approval_service

    uid = seeded["employee1@example.com"]
    created = submit(client, login_headers("employee1"), *WEEK_1).json()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE leave_balances SET used_days = 11 WHERE user_id = :u AND leave_type = 'EARNED'"),
            {"u": uid},
        )
    monkeypatch.setattr(approval_service, "_fits", lambda balance, days: True)

    response = approve(client, login_headers("manager1"), created["id"])

    assert_error(response, 409, "INSUFFICIENT_BALANCE")
    assert used_days(engine, uid) == 11
    assert request_row(engine, created["id"]).status == "PENDING"


# ---------------------------------------------------------------- P9


def test_p9_the_requesters_manager_can_approve_a_managers_request(
    client, engine, seeded, login_headers
):
    """Step 7.1: only the requester's manager (here the super manager) may decide a manager's leave."""
    created = submit(client, login_headers("manager1"), *WEEK_1).json()

    response = approve(client, login_headers("supermanager"), created["id"])

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "APPROVED"
    assert response.json()["decided_by_name"] == "Super Manager"
    assert used_days(engine, seeded["manager1@example.com"]) == 5


def test_p9_the_requesters_manager_can_reject_a_managers_request(client, seeded, login_headers):
    created = submit(client, login_headers("manager1"), *WEEK_1).json()

    response = reject(client, login_headers("supermanager"), created["id"], comment="Not this week")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REJECTED"


def test_p9_another_manager_can_no_longer_decide_a_managers_request(
    client, engine, seeded, login_headers
):
    """Was: manager2 approves manager1's request (200). Now 403 NOT_REQUESTERS_MANAGER (test_hierarchy H2)."""
    created = submit(client, login_headers("manager1"), *WEEK_1).json()

    assert_error(approve(client, login_headers("manager2"), created["id"]), 403, "NOT_REQUESTERS_MANAGER")
    assert request_row(engine, created["id"]).status == "PENDING"


def test_p9_a_manager_can_approve_an_employees_request_for_a_later_week(
    client, seeded, login_headers
):
    """Dates do not matter: pending requests stay actionable (SPEC §4)."""
    created = submit(client, login_headers("employee2"), *WEEK_2).json()

    assert approve(client, login_headers("manager1"), created["id"]).status_code == 200


# ---------------------------------------------------------------- P5 (SHOULD)


@pytest.mark.parametrize("action", [approve, reject])
@pytest.mark.parametrize("final_status", ["APPROVED", "REJECTED", "CANCELLED"])
def test_p5_own_already_actioned_request_is_403_not_409(
    client, seeded, login_headers, set_status, action, final_status
):
    """R15: the self check runs before the status check."""
    manager = login_headers("manager1")
    created = submit(client, manager, *WEEK_1).json()
    decider = seeded["manager2@example.com"] if final_status != "CANCELLED" else None
    set_status(created["id"], final_status, decided_by=decider)

    assert_error(action(client, manager, created["id"], comment="mine"), 403, "SELF_ACTION_FORBIDDEN")
