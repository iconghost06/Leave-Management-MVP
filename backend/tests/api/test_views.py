"""V3, V4 (requester fields only), V5 (SHOULD): read views of leave requests.

`decided_by_name` is not part of V4 yet: it arrives in step 3.1 with approve and reject.
"""
import pytest

from tests.api.helpers import WEEK_1, WEEK_2, WEEK_3, submit


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


# ---------------------------------------------------------------- V3


@pytest.mark.parametrize("viewer", ["employee1", "manager1", "manager2"])
def test_v3_owner_and_any_manager_can_open_a_request(client, seeded, login_headers, viewer):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()

    response = client.get(f"/leave-requests/{created['id']}", headers=login_headers(viewer))

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_v3_a_manager_can_open_their_own_request(client, seeded, login_headers):
    headers = login_headers("manager1")
    created = submit(client, headers, *WEEK_1).json()
    assert client.get(f"/leave-requests/{created['id']}", headers=headers).status_code == 200


def test_v3_another_employee_gets_403(client, seeded, login_headers):
    """Q13: 403, not 404, for a request that exists but belongs to someone else."""
    created = submit(client, login_headers("employee1"), *WEEK_1).json()

    response = client.get(f"/leave-requests/{created['id']}", headers=login_headers("employee2"))

    assert_error(response, 403, "FORBIDDEN")


def test_v3_a_missing_request_gets_404(client, seeded, login_headers):
    response = client.get("/leave-requests/999999", headers=login_headers("employee1"))
    assert_error(response, 404, "NOT_FOUND")
    assert "Leave request" in response.json()["message"]


def test_v3_detail_requires_authentication(client, seeded):
    assert_error(client.get("/leave-requests/1"), 401, "UNAUTHENTICATED")


# ---------------------------------------------------------------- V4 (requester fields)


def test_v4_every_response_carries_the_requester_name_and_code(client, seeded, login_headers):
    employee = login_headers("employee1")
    expected = {"requester_name": "Employee One", "requester_employee_code": "EMP-0003"}

    created = submit(client, employee, *WEEK_1)
    listed = client.get("/leave-requests", headers=employee)
    detail_as_manager = client.get(
        f"/leave-requests/{created.json()['id']}", headers=login_headers("manager1")
    )
    cancelled = client.post(f"/leave-requests/{created.json()['id']}/cancel", headers=employee)

    for body in (created.json(), listed.json()[0], detail_as_manager.json(), cancelled.json()):
        assert {k: body[k] for k in expected} == expected


def test_v4_a_managers_view_names_the_employee_not_the_manager(client, seeded, login_headers):
    created = submit(client, login_headers("employee2"), *WEEK_1).json()

    detail = client.get(f"/leave-requests/{created['id']}", headers=login_headers("manager1")).json()

    assert detail["requester_name"] == "Employee Two"
    assert detail["user_id"] == seeded["employee2@example.com"]


# ---------------------------------------------------------------- V5


def test_v5_list_returns_only_own_requests_newest_first(client, seeded, login_headers):
    mine = login_headers("employee1")
    first = submit(client, mine, *WEEK_1).json()
    second = submit(client, mine, *WEEK_2).json()
    submit(client, login_headers("employee2"), *WEEK_1)  # someone else's, never listed
    submit(client, login_headers("manager1"), *WEEK_1)

    response = client.get("/leave-requests", headers=mine)

    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == [second["id"], first["id"]]
    assert {r["user_id"] for r in response.json()} == {seeded["employee1@example.com"]}


def test_v5_a_manager_lists_only_their_own_requests_here(client, seeded, login_headers):
    submit(client, login_headers("employee1"), *WEEK_1)
    mine = submit(client, login_headers("manager1"), *WEEK_2).json()

    response = client.get("/leave-requests", headers=login_headers("manager1"))

    assert [r["id"] for r in response.json()] == [mine["id"]]


def test_v5_status_filter_returns_only_that_status(client, seeded, login_headers, set_status):
    headers = login_headers("employee1")
    pending = submit(client, headers, *WEEK_1).json()
    cancelled = submit(client, headers, *WEEK_2).json()
    client.post(f"/leave-requests/{cancelled['id']}/cancel", headers=headers)  # frees its 5 days
    approved = submit(client, headers, *WEEK_3).json()
    set_status(approved["id"], "APPROVED", decided_by=seeded["manager1@example.com"])

    def ids(status: str | None) -> set[int]:
        params = {"status": status} if status else {}
        response = client.get("/leave-requests", headers=headers, params=params)
        assert response.status_code == 200
        return {r["id"] for r in response.json()}

    assert ids("PENDING") == {pending["id"]}
    assert ids("CANCELLED") == {cancelled["id"]}
    assert ids("APPROVED") == {approved["id"]}
    assert ids("REJECTED") == set()
    assert ids(None) == {pending["id"], cancelled["id"], approved["id"]}


def test_v5_unknown_status_is_a_validation_error(client, seeded, login_headers):
    response = client.get("/leave-requests?status=DONE", headers=login_headers("employee1"))
    assert_error(response, 422, "VALIDATION_ERROR")


def test_v5_list_requires_authentication(client, seeded):
    assert_error(client.get("/leave-requests"), 401, "UNAUTHENTICATED")
