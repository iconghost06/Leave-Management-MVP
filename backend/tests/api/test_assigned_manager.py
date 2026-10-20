"""Step 7.4: the assigned manager is shown to managers.

Manager request rows (GET /manager/requests) and the request detail for a manager viewer carry
`employee_manager_name`: the requester's manager's name, null when the requester has none. An
employee's own views do not carry it (the screens use `manager_name` from /me). The assignment is
informational: who may decide a request is unchanged and covered by test_hierarchy.py.
"""
import pytest
from sqlalchemy import text

from tests.api.helpers import WEEK_1, WEEK_2, WEEK_3, submit
from tests.api.test_approve_reject import approve
from tests.api.test_hierarchy import queue, queue_ids

# requester -> the manager the seed assigns them to
ASSIGNED = {
    "employee1": "Manager One",
    "employee2": "Manager Two",
    "employee3": "Manager One",
    "employee4": "Manager Two",
    "manager1": "Super Manager",
    "manager2": "Super Manager",
}


def detail(client, headers, request_id: int) -> dict:
    response = client.get(f"/leave-requests/{request_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- queue and history rows


def test_a1_queue_rows_name_each_requesters_assigned_manager(client, seeded, login_headers):
    ids = {}
    for who, week in (("employee1", WEEK_1), ("employee2", WEEK_1), ("employee3", WEEK_2), ("employee4", WEEK_3)):
        ids[submit(client, login_headers(who), *week).json()["id"]] = who

    rows = queue(client, login_headers("supermanager"), status="PENDING")

    assert {ids[r["id"]]: r["employee_manager_name"] for r in rows} == {
        who: ASSIGNED[who] for who in ids.values()
    }


def test_a2_a_manager_sees_the_name_of_an_employee_assigned_to_the_other_manager(
    client, seeded, login_headers
):
    """The assignment is informational: manager1 still sees employee2, who is manager2's."""
    submit(client, login_headers("employee2"), *WEEK_1)

    rows = queue(client, login_headers("manager1"), status="PENDING")

    assert [(r["requester_name"], r["employee_manager_name"]) for r in rows] == [
        ("Employee Two", "Manager Two")
    ]


def test_a3_history_rows_carry_the_name_for_every_decided_status(client, seeded, login_headers):
    first = submit(client, login_headers("employee1"), *WEEK_1).json()
    second = submit(client, login_headers("employee2"), *WEEK_2).json()
    assert approve(client, login_headers("manager1"), first["id"]).status_code == 200
    assert (
        client.post(
            f"/leave-requests/{second['id']}/reject",
            headers=login_headers("manager1"),
            json={"comment": "no"},
        ).status_code
        == 200
    )

    rows = {r["id"]: r for r in queue(client, login_headers("manager2"))}

    assert rows[first["id"]]["employee_manager_name"] == "Manager One"
    assert rows[second["id"]]["employee_manager_name"] == "Manager Two"


def test_a4_a_managers_request_shows_the_super_manager(client, seeded, login_headers):
    created = submit(client, login_headers("manager1"), *WEEK_1).json()

    rows = queue(client, login_headers("supermanager"), status="PENDING")

    assert [(r["id"], r["employee_manager_name"]) for r in rows] == [(created["id"], "Super Manager")]


def test_a5_the_name_is_null_when_the_requester_has_no_manager(client, engine, seeded, login_headers):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET manager_id = NULL WHERE email = 'employee1@example.com'"))

    rows = queue(client, login_headers("manager2"), status="PENDING")

    assert [r["id"] for r in rows] == [created["id"]]
    assert rows[0]["employee_manager_name"] is None


def test_a6_the_name_follows_a_reassignment(client, engine, seeded, login_headers):
    submit(client, login_headers("employee1"), *WEEK_1)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE users SET manager_id = (SELECT id FROM users WHERE email = 'manager2@example.com') "
                "WHERE email = 'employee1@example.com'"
            )
        )

    rows = queue(client, login_headers("manager1"), status="PENDING")

    assert rows[0]["employee_manager_name"] == "Manager Two"


# ---------------------------------------------------------------- request detail


@pytest.mark.parametrize("requester", sorted(ASSIGNED))
def test_a7_detail_for_a_manager_carries_the_assigned_manager_name(
    client, seeded, login_headers, requester
):
    created = submit(client, login_headers(requester), *WEEK_1).json()

    body = detail(client, login_headers("supermanager"), created["id"])

    assert body["employee_manager_name"] == ASSIGNED[requester]


def test_a8_detail_for_a_manager_names_the_assigned_manager_even_when_another_manager_views(
    client, seeded, login_headers
):
    created = submit(client, login_headers("employee2"), *WEEK_1).json()

    assert detail(client, login_headers("manager1"), created["id"])["employee_manager_name"] == "Manager Two"


def test_a9_detail_name_is_null_when_the_requester_has_no_manager(client, engine, seeded, login_headers):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET manager_id = NULL WHERE email = 'employee1@example.com'"))

    body = detail(client, login_headers("manager1"), created["id"])

    assert "employee_manager_name" in body
    assert body["employee_manager_name"] is None


def test_a10_a_manager_viewing_their_own_request_gets_the_name_too(client, seeded, login_headers):
    created = submit(client, login_headers("manager1"), *WEEK_1).json()

    assert detail(client, login_headers("manager1"), created["id"])["employee_manager_name"] == "Super Manager"


def test_a11_detail_for_an_employee_does_not_carry_the_field(client, seeded, login_headers):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()

    body = detail(client, login_headers("employee1"), created["id"])

    assert "employee_manager_name" not in body


def test_a12_the_employee_list_and_action_responses_do_not_carry_the_field(client, seeded, login_headers):
    created = submit(client, login_headers("employee1"), *WEEK_1)
    mine = client.get("/leave-requests", headers=login_headers("employee1")).json()
    decided = approve(client, login_headers("manager1"), created.json()["id"])

    assert "employee_manager_name" not in created.json()
    assert mine and all("employee_manager_name" not in r for r in mine)
    assert "employee_manager_name" not in decided.json()


def test_a13_the_detail_has_exactly_the_documented_fields(client, seeded, login_headers):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()
    base = {
        "id", "user_id", "requester_name", "requester_employee_code", "leave_type", "start_date",
        "end_date", "days", "reason", "status", "decided_by", "decided_by_name", "decided_at",
        "decision_comment", "created_at",
    }

    assert set(detail(client, login_headers("employee1"), created["id"])) == base
    assert set(detail(client, login_headers("manager1"), created["id"])) == base | {"employee_manager_name"}


def test_a14_detail_missing_and_forbidden_responses_are_unchanged(client, seeded, login_headers):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()

    other = client.get(f"/leave-requests/{created['id']}", headers=login_headers("employee2"))
    missing = client.get("/leave-requests/999999", headers=login_headers("manager1"))

    assert (other.status_code, other.json()["code"]) == (403, "FORBIDDEN")
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")


# ---------------------------------------------------------------- the rules do not change


def test_a15_any_manager_may_still_decide_an_employee_request_whoever_it_is_assigned_to(
    client, seeded, login_headers
):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()  # assigned to manager1

    response = approve(client, login_headers("manager2"), created["id"])

    assert response.status_code == 200, response.text
    assert response.json()["decided_by_name"] == "Manager Two"


def test_a16_the_queue_still_lists_every_employee_request_to_every_manager(client, seeded, login_headers):
    ids = [
        submit(client, login_headers(who), *week).json()["id"]
        for who, week in (("employee1", WEEK_1), ("employee2", WEEK_2), ("employee3", WEEK_3))
    ]

    for who in ("manager1", "manager2", "supermanager"):
        assert queue_ids(client, login_headers(who), status="PENDING") == ids
