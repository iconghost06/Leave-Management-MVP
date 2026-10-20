"""Step 7.1: super manager and manager assignment.

A MANAGER whose `manager_id` is NULL is the "super manager" (supermanager@example.com in the seed).
Seed hierarchy: manager1 and manager2 report to supermanager; employee1 and employee3 to manager1;
employee2 and employee4 to manager2. The assignment is informational (step 7.4): it never changes
who may decide a request.

Rules under test:
- a manager's leave can be decided only by that manager's `manager_id`; anyone else gets 403
  NOT_REQUESTERS_MANAGER, after the self check and before the status check;
- an employee's request stays open to any manager;
- GET /manager/requests hides manager-requests the viewer cannot act on;
- the super manager cannot submit leave (403 MANAGER_HAS_NO_MANAGER);
- signup assigns a random MANAGER that has a manager (never the super manager); NULL if none;
- /me and the auth responses carry manager_name.
"""
import pytest
from sqlalchemy import text

from tests.api.test_approve_reject import approve, assert_error, reject, used_days
from tests.api.helpers import WEEK_1, WEEK_2, WEEK_3, request_row, submit
from tests.api.test_auth import JOIN_CODE, auth_header, signup_body

NOT_REQUESTERS_MANAGER = "NOT_REQUESTERS_MANAGER"
NO_MANAGER = "MANAGER_HAS_NO_MANAGER"


def manager_id_of(engine, user_id: int) -> int | None:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT manager_id FROM users WHERE id = :u"), {"u": user_id}
        ).scalar_one()


def queue(client, headers, **params) -> list[dict]:
    response = client.get("/manager/requests", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def queue_ids(client, headers, **params) -> list[int]:
    return [r["id"] for r in queue(client, headers, **params)]


# ---------------------------------------------------------------- approve / reject a manager's request


@pytest.mark.parametrize("requester", ["manager1", "manager2"])
def test_h1_the_super_manager_approves_a_managers_request(
    client, engine, seeded, login_headers, requester
):
    created = submit(client, login_headers(requester), *WEEK_1).json()

    response = approve(client, login_headers("supermanager"), created["id"])

    assert response.status_code == 200, response.text
    out = response.json()
    assert out["status"] == "APPROVED"
    assert out["decided_by"] == seeded["supermanager@example.com"]
    assert out["decided_by_name"] == "Super Manager"
    assert used_days(engine, seeded[f"{requester}@example.com"]) == 5


@pytest.mark.parametrize("requester", ["manager1", "manager2"])
def test_h1_the_super_manager_rejects_a_managers_request(
    client, engine, seeded, login_headers, requester
):
    created = submit(client, login_headers(requester), *WEEK_1).json()

    response = reject(client, login_headers("supermanager"), created["id"], comment="Not now")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REJECTED"
    assert used_days(engine, seeded[f"{requester}@example.com"]) == 0


@pytest.mark.parametrize("action", [approve, reject])
@pytest.mark.parametrize("requester, other", [("manager1", "manager2"), ("manager2", "manager1")])
def test_h2_another_manager_cannot_decide_a_managers_request(
    client, engine, seeded, login_headers, action, requester, other
):
    created = submit(client, login_headers(requester), *WEEK_1).json()

    response = action(client, login_headers(other), created["id"], comment="mine to decide")

    assert_error(response, 403, NOT_REQUESTERS_MANAGER)
    assert set(response.json()) == {"code", "message"}
    row = request_row(engine, created["id"])
    assert row.status == "PENDING" and row.decided_by is None and row.decided_at is None
    assert used_days(engine, seeded[f"{requester}@example.com"]) == 0


@pytest.mark.parametrize("action", [approve, reject])
def test_h2_the_error_is_not_the_role_gate_or_the_self_check(
    client, seeded, login_headers, action
):
    created = submit(client, login_headers("manager1"), *WEEK_1).json()

    other = action(client, login_headers("manager2"), created["id"], comment="x")
    own = action(client, login_headers("manager1"), created["id"], comment="x")

    assert other.json()["code"] == NOT_REQUESTERS_MANAGER
    assert own.json()["code"] == "SELF_ACTION_FORBIDDEN"


@pytest.mark.parametrize("action", [approve, reject])
def test_h2_an_employee_still_gets_the_plain_forbidden(client, seeded, login_headers, action):
    created = submit(client, login_headers("manager1"), *WEEK_1).json()

    assert_error(action(client, login_headers("employee1"), created["id"], comment="x"), 403, "FORBIDDEN")


@pytest.mark.parametrize("action", [approve, reject])
def test_h3_the_authorization_check_comes_before_the_status_check(
    client, seeded, login_headers, set_status, action
):
    """403 first: a manager who may not decide the request is told so even when it is already actioned."""
    created = submit(client, login_headers("manager1"), *WEEK_1).json()
    set_status(created["id"], "APPROVED", decided_by=seeded["supermanager@example.com"])

    assert_error(
        action(client, login_headers("manager2"), created["id"], comment="late"),
        403,
        NOT_REQUESTERS_MANAGER,
    )


@pytest.mark.parametrize("action", [approve, reject])
@pytest.mark.parametrize("final_status", ["APPROVED", "REJECTED", "CANCELLED"])
def test_h3_the_right_manager_gets_409_on_an_actioned_manager_request(
    client, seeded, login_headers, set_status, action, final_status
):
    created = submit(client, login_headers("manager1"), *WEEK_1).json()
    decider = seeded["supermanager@example.com"] if final_status != "CANCELLED" else None
    set_status(created["id"], final_status, decided_by=decider)

    assert_error(
        action(client, login_headers("supermanager"), created["id"], comment="late"),
        409,
        "ALREADY_ACTIONED",
    )


@pytest.mark.parametrize("final_status", ["APPROVED", "REJECTED", "CANCELLED"])
def test_h3_the_self_check_still_comes_before_everything(
    client, seeded, login_headers, set_status, final_status
):
    manager = login_headers("manager1")
    created = submit(client, manager, *WEEK_1).json()
    decider = seeded["supermanager@example.com"] if final_status != "CANCELLED" else None
    set_status(created["id"], final_status, decided_by=decider)

    assert_error(approve(client, manager, created["id"]), 403, "SELF_ACTION_FORBIDDEN")


def test_h3_the_authorization_check_comes_before_the_comment_check(client, seeded, login_headers):
    created = submit(client, login_headers("manager1"), *WEEK_1).json()

    response = reject(client, login_headers("manager2"), created["id"], comment="   ")

    assert_error(response, 403, NOT_REQUESTERS_MANAGER)


def test_h3_a_blank_comment_from_the_right_manager_is_still_422(client, seeded, login_headers):
    created = submit(client, login_headers("manager1"), *WEEK_1).json()

    response = reject(client, login_headers("supermanager"), created["id"], comment="   ")

    assert_error(response, 422, "COMMENT_REQUIRED")


def test_h4_a_manager_request_nobody_manages_cannot_be_decided(client, engine, seeded, login_headers):
    """A manager whose manager_id was cleared after submitting: no one is their manager now."""
    created = submit(client, login_headers("manager1"), *WEEK_1).json()
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET manager_id = NULL WHERE email = 'manager1@example.com'"))

    for who in ("supermanager", "manager2"):
        assert_error(approve(client, login_headers(who), created["id"]), 403, NOT_REQUESTERS_MANAGER)


# ---------------------------------------------------------------- employee requests stay open to any manager


@pytest.mark.parametrize("manager", ["supermanager", "manager1", "manager2"])
@pytest.mark.parametrize("employee", ["employee1", "employee2", "employee3", "employee4"])
def test_h5_any_manager_can_approve_an_employees_request(
    client, engine, seeded, login_headers, manager, employee
):
    created = submit(client, login_headers(employee), *WEEK_1).json()

    response = approve(client, login_headers(manager), created["id"])

    assert response.status_code == 200, response.text
    assert response.json()["decided_by"] == seeded[f"{manager}@example.com"]


@pytest.mark.parametrize("manager", ["supermanager", "manager1", "manager2"])
def test_h5_any_manager_can_reject_an_employees_request(client, seeded, login_headers, manager):
    created = submit(client, login_headers("employee1"), *WEEK_1).json()

    response = reject(client, login_headers(manager), created["id"], comment="No")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REJECTED"


# ---------------------------------------------------------------- the queue and history


def test_h6_pending_queue_shows_a_manager_request_only_to_that_managers_manager(
    client, seeded, login_headers
):
    mine = submit(client, login_headers("manager1"), *WEEK_1).json()

    assert queue_ids(client, login_headers("supermanager"), status="PENDING") == [mine["id"]]
    assert queue_ids(client, login_headers("manager2"), status="PENDING") == []
    assert queue_ids(client, login_headers("manager1"), status="PENDING") == []


def test_h6_every_manager_still_sees_employee_requests(client, seeded, login_headers):
    theirs = submit(client, login_headers("employee1"), *WEEK_1).json()

    for who in ("supermanager", "manager1", "manager2"):
        assert queue_ids(client, login_headers(who), status="PENDING") == [theirs["id"]]


def test_h6_ordering_is_unchanged_and_only_unactionable_rows_drop_out(
    client, seeded, login_headers
):
    first = submit(client, login_headers("employee2"), *WEEK_1).json()
    m1 = submit(client, login_headers("manager1"), *WEEK_1).json()
    second = submit(client, login_headers("employee1"), *WEEK_2).json()
    m2 = submit(client, login_headers("manager2"), *WEEK_1).json()
    third = submit(client, login_headers("employee3"), *WEEK_3).json()

    # Oldest first for the super manager, who can act on every row.
    assert queue_ids(client, login_headers("supermanager"), status="PENDING") == [
        first["id"], m1["id"], second["id"], m2["id"], third["id"],
    ]
    assert queue_ids(client, login_headers("manager1"), status="PENDING") == [
        first["id"], second["id"], third["id"],
    ]
    assert queue_ids(client, login_headers("manager2"), status="PENDING") == [
        first["id"], second["id"], third["id"],
    ]


def test_h6_rows_carry_only_the_expected_fields(client, seeded, login_headers):
    submit(client, login_headers("manager1"), *WEEK_1)

    row = queue(client, login_headers("supermanager"), status="PENDING")[0]

    assert set(row) == {
        "id", "user_id", "requester_name", "requester_employee_code", "leave_type",
        "start_date", "end_date", "days", "reason", "status", "decided_by", "decided_by_name",
        "decided_at", "decision_comment", "created_at", "employee_available", "requester_role",
        "employee_manager_name",
    }


def test_h7_history_hides_decided_manager_requests_from_other_managers(
    client, seeded, login_headers
):
    created = submit(client, login_headers("manager1"), *WEEK_1).json()
    approve(client, login_headers("supermanager"), created["id"])
    employee_done = submit(client, login_headers("employee1"), *WEEK_2).json()
    approve(client, login_headers("manager2"), employee_done["id"])

    assert queue_ids(client, login_headers("supermanager"), status="APPROVED") == [
        employee_done["id"], created["id"],
    ]
    assert queue_ids(client, login_headers("manager2"), status="APPROVED") == [employee_done["id"]]
    assert created["id"] not in queue_ids(client, login_headers("manager2"))
    assert created["id"] not in queue_ids(client, login_headers("manager1"))


@pytest.mark.parametrize("status", ["APPROVED", "REJECTED", "CANCELLED"])
def test_h7_every_status_filter_hides_unactionable_manager_requests(
    client, seeded, login_headers, set_status, status
):
    created = submit(client, login_headers("manager1"), *WEEK_1).json()
    decider = seeded["supermanager@example.com"] if status != "CANCELLED" else None
    set_status(created["id"], status, decided_by=decider)

    assert queue_ids(client, login_headers("supermanager"), status=status) == [created["id"]]
    assert queue_ids(client, login_headers("manager2"), status=status) == []


def test_h7_a_manager_request_nobody_manages_is_hidden_from_everyone(
    client, engine, seeded, login_headers
):
    created = submit(client, login_headers("manager1"), *WEEK_1).json()
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET manager_id = NULL WHERE email = 'manager1@example.com'"))

    for who in ("supermanager", "manager1", "manager2"):
        assert created["id"] not in queue_ids(client, login_headers(who))


def test_h7_the_detail_page_is_still_open_to_any_manager(client, seeded, login_headers):
    created = submit(client, login_headers("manager1"), *WEEK_1).json()

    for who in ("supermanager", "manager2"):
        response = client.get(f"/leave-requests/{created['id']}", headers=login_headers(who))
        assert response.status_code == 200, response.text


# ---------------------------------------------------------------- the super manager cannot take leave


def test_h8_the_super_manager_cannot_submit_leave(client, engine, seeded, login_headers):
    response = submit(client, login_headers("supermanager"), *WEEK_1)

    assert_error(response, 403, NO_MANAGER)
    assert set(response.json()) == {"code", "message"}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM leave_requests")).scalar_one() == 0


def test_h8_the_check_runs_before_date_validation(client, seeded, login_headers):
    response = submit(client, login_headers("supermanager"), "2026-11-06", "2026-11-02")

    assert_error(response, 403, NO_MANAGER)


@pytest.mark.parametrize("who", ["manager1", "manager2", "employee1", "employee4"])
def test_h8_everyone_else_can_still_submit(client, seeded, login_headers, who):
    assert submit(client, login_headers(who), *WEEK_1).status_code == 201


def test_h8_a_manager_who_gains_a_manager_can_submit(client, engine, seeded, login_headers):
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE users SET manager_id = (SELECT id FROM users WHERE email = 'manager1@example.com') "
                "WHERE email = 'supermanager@example.com'"
            )
        )

    assert submit(client, login_headers("supermanager"), *WEEK_1).status_code == 201


def test_h8_the_super_manager_still_has_balances_and_can_decide(client, seeded, login_headers):
    headers = login_headers("supermanager")

    assert client.get("/balances", headers=headers).status_code == 200
    assert client.get("/manager/requests", headers=headers).status_code == 200


# ---------------------------------------------------------------- signup


def sign_up(client, n: int = 1, **overrides):
    response = client.post(
        "/auth/signup", json=signup_body(email=f"new{n}@example.com", **overrides)
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_h9_signup_assigns_manager1_or_manager2_never_the_super_manager(client, engine, seeded):
    allowed = {seeded["manager1@example.com"], seeded["manager2@example.com"]}

    assigned = {manager_id_of(engine, sign_up(client, n)["user"]["id"]) for n in range(12)}

    assert assigned <= allowed
    assert seeded["supermanager@example.com"] not in assigned


def test_h9_the_random_choice_is_replaceable(client, engine, seeded, monkeypatch):
    seen = []

    def pick_last(candidates):
        seen.append(list(candidates))
        return candidates[-1]

    monkeypatch.setattr("app.services.auth_service.choose_manager_id", pick_last)
    m1, m2 = seeded["manager1@example.com"], seeded["manager2@example.com"]

    user = sign_up(client)["user"]

    assert seen == [sorted([m1, m2])]  # candidates are exactly the managers that have a manager
    assert manager_id_of(engine, user["id"]) == m2
    assert user["manager_name"] == "Manager Two"


def test_h9_the_choice_can_pick_the_first_manager_too(client, engine, seeded, monkeypatch):
    monkeypatch.setattr("app.services.auth_service.choose_manager_id", lambda ids: ids[0])

    user = sign_up(client)["user"]

    assert manager_id_of(engine, user["id"]) == seeded["manager1@example.com"]
    assert user["manager_name"] == "Manager One"


def test_h9_signup_leaves_manager_null_when_no_manager_has_a_manager(client, engine):
    """No seed: no managers at all."""
    user = sign_up(client)["user"]

    assert manager_id_of(engine, user["id"]) is None
    assert user["manager_name"] is None


def test_h9_signup_leaves_manager_null_when_only_the_super_manager_exists(client, engine, seeded):
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET manager_id = NULL WHERE email IN ('manager1@example.com', 'manager2@example.com')")
        )

    user = sign_up(client)["user"]

    assert manager_id_of(engine, user["id"]) is None


def test_h9_a_signed_up_employee_is_still_an_employee_whose_request_any_manager_can_decide(
    client, seeded, login_headers
):
    token = sign_up(client)["access_token"]
    created = submit(client, auth_header(token), *WEEK_1)
    assert created.status_code == 201, created.text

    for who in ("supermanager", "manager1", "manager2"):
        assert queue_ids(client, login_headers(who), status="PENDING") == [created.json()["id"]]


def test_h9_signup_still_ignores_a_client_supplied_manager(client, engine, seeded):
    body = signup_body(email="sneaky@example.com", manager_id=seeded["supermanager@example.com"])
    body["join_code"] = JOIN_CODE

    user = client.post("/auth/signup", json=body).json()["user"]

    assert manager_id_of(engine, user["id"]) != seeded["supermanager@example.com"]


# ---------------------------------------------------------------- manager_name


@pytest.mark.parametrize(
    "who, expected",
    [
        ("supermanager", None),
        ("manager1", "Super Manager"),
        ("manager2", "Super Manager"),
        ("employee1", "Manager One"),
        ("employee2", "Manager Two"),
        ("employee3", "Manager One"),
        ("employee4", "Manager Two"),
    ],
)
def test_h10_me_returns_manager_name(client, seeded, login_headers, who, expected):
    response = client.get("/me", headers=login_headers(who))

    assert response.status_code == 200, response.text
    assert response.json()["manager_name"] == expected


def test_h10_login_returns_manager_name_too(client, seeded):
    login = client.post(
        "/auth/login", json={"email": "employee1@example.com", "password": "Employee@123"}
    )

    assert login.json()["user"]["manager_name"] == "Manager One"


def test_h10_me_does_not_expose_the_manager_id_or_email(client, seeded, login_headers):
    body = client.get("/me", headers=login_headers("employee1")).json()

    assert set(body) == {"id", "employee_code", "name", "email", "role", "manager_name"}
