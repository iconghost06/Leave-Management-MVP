"""Step 7.2: what the super manager sees in the queue and history.

The super manager (supermanager@example.com) supervises manager1 and manager2 and can act on every
employee, so history holds decided requests from all of them. The queue stays pending only.
Rows carry `requester_role` so the History page can tag Employee or Manager. Approval rules are
unchanged and covered by test_hierarchy.py.
"""
import pytest

from tests.api.helpers import WEEK_1, WEEK_2, WEEK_3, submit
from tests.api.test_approve_reject import approve, reject
from tests.api.test_hierarchy import queue, queue_ids


@pytest.fixture
def decided(client, seeded, login_headers):
    """One decided request each from employee1, employee2, manager1 and manager2."""
    ids = {}
    for who, week in (("employee1", WEEK_1), ("employee2", WEEK_2), ("manager1", WEEK_3), ("manager2", WEEK_1)):
        ids[who] = submit(client, login_headers(who), *week).json()["id"]
    boss = login_headers("supermanager")
    assert approve(client, boss, ids["employee1"]).status_code == 200
    assert reject(client, boss, ids["employee2"], comment="no").status_code == 200
    assert approve(client, boss, ids["manager1"]).status_code == 200
    assert reject(client, boss, ids["manager2"], comment="no").status_code == 200
    return ids


def test_s1_super_manager_history_has_employees_and_supervised_managers(
    client, login_headers, decided
):
    ids = queue_ids(client, login_headers("supermanager"))

    assert set(ids) == set(decided.values())


@pytest.mark.parametrize("status", ["APPROVED", "REJECTED"])
def test_s2_the_status_filter_works_across_both_kinds_of_requester(
    client, login_headers, decided, status
):
    rows = queue(client, login_headers("supermanager"), status=status)

    assert {r["requester_role"] for r in rows} == {"EMPLOYEE", "MANAGER"}
    assert {r["status"] for r in rows} == {status}


def test_s3_the_super_manager_queue_is_pending_only(client, login_headers, decided):
    pending_employee = submit(client, login_headers("employee3"), *WEEK_1).json()
    pending_manager = submit(client, login_headers("manager1"), *WEEK_1).json()

    rows = queue(client, login_headers("supermanager"), status="PENDING")

    assert [r["id"] for r in rows] == [pending_employee["id"], pending_manager["id"]]
    assert {r["status"] for r in rows} == {"PENDING"}


def test_s4_requester_role_tells_employees_from_managers(client, login_headers, decided):
    rows = {r["id"]: r for r in queue(client, login_headers("supermanager"))}

    assert rows[decided["employee1"]]["requester_role"] == "EMPLOYEE"
    assert rows[decided["employee2"]]["requester_role"] == "EMPLOYEE"
    assert rows[decided["manager1"]]["requester_role"] == "MANAGER"
    assert rows[decided["manager2"]]["requester_role"] == "MANAGER"


def test_s5_the_super_manager_never_sees_their_own_requests(client, engine, login_headers, decided):
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET manager_id = NULL WHERE email = 'manager1@example.com'"))

    ids = queue_ids(client, login_headers("supermanager"))

    assert decided["manager1"] not in ids  # nobody manages manager1 any more
    assert decided["employee1"] in ids


@pytest.mark.parametrize("who", ["manager1", "manager2"])
def test_s6_a_normal_managers_history_has_no_manager_requests(client, login_headers, decided, who):
    rows = queue(client, login_headers(who))

    assert {r["id"] for r in rows} == {decided["employee1"], decided["employee2"]}
    assert {r["requester_role"] for r in rows} == {"EMPLOYEE"}


def test_s7_employee_views_do_not_gain_requester_role(client, login_headers, decided):
    mine = client.get("/leave-requests", headers=login_headers("employee1")).json()
    detail = client.get(f"/leave-requests/{decided['employee1']}", headers=login_headers("employee1")).json()

    assert mine and all("requester_role" not in r for r in mine)
    assert "requester_role" not in detail
