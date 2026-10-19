"""V1 (MUST): the manager queue. R19, Q6-Q8.

GET /manager/requests never returns the caller's own requests. PENDING rows are oldest first
and carry `employee_available`.
"""
from tests.api.helpers import WEEK_1, WEEK_2, WEEK_3, submit


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def queue(client, headers, **params):
    response = client.get("/manager/requests", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- V1


def test_v1_queue_excludes_the_callers_own_requests(client, seeded, login_headers):
    mine = submit(client, login_headers("manager1"), *WEEK_1).json()
    theirs = submit(client, login_headers("employee1"), *WEEK_1).json()

    ids = [r["id"] for r in queue(client, login_headers("manager1"), status="PENDING")]

    assert ids == [theirs["id"]]
    assert mine["id"] not in ids


def test_v1_another_manager_does_see_the_request(client, seeded, login_headers):
    """The exclusion is by caller, not by role: manager2 can act on manager1's leave (P9)."""
    mine = submit(client, login_headers("manager1"), *WEEK_1).json()

    ids = [r["id"] for r in queue(client, login_headers("manager2"), status="PENDING")]

    assert ids == [mine["id"]]


def test_v1_pending_queue_is_oldest_first(client, seeded, login_headers):
    first = submit(client, login_headers("employee2"), *WEEK_1).json()
    second = submit(client, login_headers("employee1"), *WEEK_1).json()
    third = submit(client, login_headers("employee3"), *WEEK_2).json()

    rows = queue(client, login_headers("manager1"), status="PENDING")

    assert [r["id"] for r in rows] == [first["id"], second["id"], third["id"]]


def test_v1_pending_rows_carry_employee_available_for_their_own_type(client, seeded, login_headers):
    submit(client, login_headers("employee1"), *WEEK_1, leave_type="EARNED")  # 5 of 12
    submit(client, login_headers("employee2"), *WEEK_1, leave_type="SICK")  # 5 of 10

    rows = queue(client, login_headers("manager1"), status="PENDING")

    by_name = {r["requester_name"]: r["employee_available"] for r in rows}
    # Q6: the figure already subtracts the request under review.
    assert by_name == {"Employee One": 7, "Employee Two": 5}


def test_v1_employee_available_counts_all_of_that_employees_pending_in_the_type(
    client, seeded, login_headers
):
    employee = login_headers("employee1")
    submit(client, employee, *WEEK_1)  # EARNED 5
    submit(client, employee, *WEEK_2)  # EARNED 5
    submit(client, employee, *WEEK_3, leave_type="SICK")  # SICK 5

    rows = queue(client, login_headers("manager1"), status="PENDING")

    assert [(r["leave_type"], r["employee_available"]) for r in rows] == [
        ("EARNED", 2),
        ("EARNED", 2),
        ("SICK", 5),
    ]


def test_v1_employee_available_subtracts_used_days_too(client, seeded, login_headers):
    first = submit(client, login_headers("employee1"), *WEEK_1).json()
    assert client.post(f"/leave-requests/{first['id']}/approve", headers=login_headers("manager1")).status_code == 200
    submit(client, login_headers("employee1"), *WEEK_2)  # 5 used + 5 pending of 12

    rows = queue(client, login_headers("manager1"), status="PENDING")

    assert [r["employee_available"] for r in rows] == [2]


def test_v1_an_employee_gets_403(client, seeded, login_headers):
    assert_error(client.get("/manager/requests", headers=login_headers("employee1")), 403, "FORBIDDEN")


def test_v1_requires_authentication(client, seeded):
    assert_error(client.get("/manager/requests"), 401, "UNAUTHENTICATED")


# ---------------------------------------------------------------- V2 (SHOULD)


def _mixed_history(client, login_headers, seeded):
    """employee1: one PENDING, one REJECTED, one CANCELLED. employee2: one APPROVED. manager1: own PENDING."""
    employee = login_headers("employee1")
    pending = submit(client, employee, *WEEK_1).json()
    to_reject = submit(client, employee, *WEEK_2).json()
    to_cancel = submit(client, employee, *WEEK_3, leave_type="SICK").json()  # 3 x 5 EARNED would not fit
    client.post(f"/leave-requests/{to_cancel['id']}/cancel", headers=employee)
    reject = client.post(
        f"/leave-requests/{to_reject['id']}/reject",
        headers=login_headers("manager2"),
        json={"comment": "Busy week"},
    )
    assert reject.status_code == 200, reject.text
    approved = submit(client, login_headers("employee2"), *WEEK_1).json()
    approve = client.post(f"/leave-requests/{approved['id']}/approve", headers=login_headers("manager2"))
    assert approve.status_code == 200, approve.text
    own = submit(client, login_headers("manager1"), *WEEK_1).json()
    return {
        "PENDING": pending["id"],
        "REJECTED": to_reject["id"],
        "CANCELLED": to_cancel["id"],
        "APPROVED": approved["id"],
        "own": own["id"],
    }


def test_v2_status_filter_returns_only_that_status(client, seeded, login_headers):
    ids = _mixed_history(client, login_headers, seeded)
    manager = login_headers("manager1")

    for status in ("PENDING", "APPROVED", "REJECTED", "CANCELLED"):
        assert [r["id"] for r in queue(client, manager, status=status)] == [ids[status]]


def test_v2_history_excludes_the_callers_own_requests_in_every_status(
    client, seeded, login_headers
):
    ids = _mixed_history(client, login_headers, seeded)
    # manager2 approves manager1's request, so it is also in a non-PENDING status.
    client.post(f"/leave-requests/{ids['own']}/approve", headers=login_headers("manager2"))

    seen = {r["id"] for r in queue(client, login_headers("manager1"))}

    assert ids["own"] not in seen
    assert seen == {ids["PENDING"], ids["REJECTED"], ids["CANCELLED"], ids["APPROVED"]}


def test_v2_no_filter_returns_every_status_newest_first(client, seeded, login_headers):
    ids = _mixed_history(client, login_headers, seeded)

    rows = queue(client, login_headers("manager1"))

    created = [ids["PENDING"], ids["REJECTED"], ids["CANCELLED"], ids["APPROVED"]]  # submission order
    assert [r["id"] for r in rows] == sorted(created, reverse=True)
    assert {r["status"] for r in rows} == {"PENDING", "APPROVED", "REJECTED", "CANCELLED"}


def test_v2_employee_available_is_null_unless_pending(client, seeded, login_headers):
    _mixed_history(client, login_headers, seeded)

    for row in queue(client, login_headers("manager1")):
        if row["status"] == "PENDING":
            assert isinstance(row["employee_available"], int)
        else:
            assert row["employee_available"] is None


def test_v2_unknown_status_is_a_validation_error(client, seeded, login_headers):
    response = client.get("/manager/requests?status=DONE", headers=login_headers("manager1"))
    assert_error(response, 422, "VALIDATION_ERROR")


# ---------------------------------------------------------------- V4 (SHOULD)


def test_v4_manager_rows_carry_requester_and_decider_fields(client, seeded, login_headers):
    approved = submit(client, login_headers("employee1"), *WEEK_1).json()
    client.post(
        f"/leave-requests/{approved['id']}/approve",
        headers=login_headers("manager2"),
        json={"comment": "Enjoy"},
    )
    pending = submit(client, login_headers("employee2"), *WEEK_1).json()

    rows = {r["id"]: r for r in queue(client, login_headers("manager1"))}

    assert rows[approved["id"]]["requester_name"] == "Employee One"
    assert rows[approved["id"]]["requester_employee_code"] == "EMP-0003"
    assert rows[approved["id"]]["decided_by_name"] == "Manager Two"
    assert rows[approved["id"]]["decision_comment"] == "Enjoy"
    assert rows[pending["id"]]["requester_name"] == "Employee Two"
    assert rows[pending["id"]]["decided_by_name"] is None
