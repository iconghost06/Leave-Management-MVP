"""C1-C4 (MUST): POST /leave-requests/{id}/cancel (R13, R16, DESIGN §4.4, Q3, Q14).

Non-PENDING rows are set with direct SQL (`set_status`), because approve and reject do not exist yet.
"""
import pytest

from tests.api.helpers import WEEK_1, balance_of, request_row, submit


def cancel(client, headers, request_id: int):
    return client.post(f"/leave-requests/{request_id}/cancel", headers=headers)


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


# ---------------------------------------------------------------- C1


def test_c1_owner_cancels_pending(client, engine, seeded, login_headers):
    headers = login_headers("employee1")
    created = submit(client, headers, *WEEK_1).json()

    response = cancel(client, headers, created["id"])

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["status"] == "CANCELLED"
    assert request_row(engine, created["id"]).status == "CANCELLED"


def test_c1_cancel_leaves_decided_by_and_decided_at_empty(client, engine, seeded, login_headers):
    """Q3: the CHECK forbids the requester as decided_by, and a cancel is not a decision."""
    headers = login_headers("employee1")
    created = submit(client, headers, *WEEK_1).json()

    out = cancel(client, headers, created["id"]).json()

    assert out["decided_by"] is None and out["decided_at"] is None
    row = request_row(engine, created["id"])
    assert row.decided_by is None and row.decided_at is None and row.decision_comment is None


def test_c1_a_manager_can_cancel_their_own_pending_request(client, seeded, login_headers):
    headers = login_headers("manager1")
    created = submit(client, headers, *WEEK_1).json()
    assert cancel(client, headers, created["id"]).json()["status"] == "CANCELLED"


def test_c1_cancel_requires_authentication(client, seeded):
    assert_error(client.post("/leave-requests/1/cancel"), 401, "UNAUTHENTICATED")


def test_c1_unknown_request_is_404(client, seeded, login_headers):
    response = cancel(client, login_headers("employee1"), 999999)

    assert_error(response, 404, "NOT_FOUND")
    assert "Leave request" in response.json()["message"]  # from the service, not "no such route"


# ---------------------------------------------------------------- C2


@pytest.mark.parametrize("other", ["employee2", "manager1"])
def test_c2_someone_else_cannot_cancel(client, engine, seeded, login_headers, other):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()

    response = cancel(client, login_headers(other), created["id"])

    assert_error(response, 403, "FORBIDDEN")
    assert request_row(engine, created["id"]).status == "PENDING"


# ---------------------------------------------------------------- C3


@pytest.mark.parametrize("final_status", ["APPROVED", "REJECTED", "CANCELLED"])
def test_c3_cancel_of_a_non_pending_request_is_already_actioned(
    client, engine, seeded, login_headers, set_status, final_status
):
    headers = login_headers("employee1")
    created = submit(client, headers, *WEEK_1).json()
    decider = seeded["manager1@example.com"] if final_status != "CANCELLED" else None
    set_status(created["id"], final_status, decided_by=decider)

    response = cancel(client, headers, created["id"])

    assert_error(response, 409, "ALREADY_ACTIONED")
    assert request_row(engine, created["id"]).status == final_status


def test_c3_cancelling_twice_gives_409_the_second_time(client, seeded, login_headers):
    headers = login_headers("employee1")
    created = submit(client, headers, *WEEK_1).json()
    assert cancel(client, headers, created["id"]).status_code == 200
    assert_error(cancel(client, headers, created["id"]), 409, "ALREADY_ACTIONED")


def test_c3_approved_cancel_does_not_touch_used_days(client, seeded, login_headers, set_status):
    headers = login_headers("employee1")
    created = submit(client, headers, *WEEK_1).json()
    set_status(created["id"], "APPROVED", decided_by=seeded["manager1@example.com"])

    assert cancel(client, headers, created["id"]).status_code == 409

    assert balance_of(client, headers)["used"] == 5


def test_c3_ownership_is_checked_before_status(client, seeded, login_headers, set_status):
    """Q14: a non-owner gets 403 even when the request is already actioned (not 409)."""
    created = submit(client, login_headers("employee1"), *WEEK_1).json()
    set_status(created["id"], "APPROVED", decided_by=seeded["manager1@example.com"])

    assert_error(cancel(client, login_headers("employee2"), created["id"]), 403, "FORBIDDEN")
    assert_error(cancel(client, login_headers("manager2"), created["id"]), 403, "FORBIDDEN")


# ---------------------------------------------------------------- C4


def test_c4_cancel_restores_available(client, seeded, login_headers):
    headers = login_headers("employee1")
    created = submit(client, headers, *WEEK_1).json()
    assert balance_of(client, headers) == {
        "leave_type": "EARNED", "entitlement": 12, "used": 0, "pending": 5, "available": 7,
    }

    cancel(client, headers, created["id"])

    assert balance_of(client, headers) == {
        "leave_type": "EARNED", "entitlement": 12, "used": 0, "pending": 0, "available": 12,
    }


def test_c4_a_cancelled_range_can_be_requested_again(client, seeded, login_headers):
    headers = login_headers("employee1")
    created = submit(client, headers, *WEEK_1).json()
    cancel(client, headers, created["id"])
    assert submit(client, headers, *WEEK_1).status_code == 201
