"""A1-A7 (signup, login, /me) and the rule that role comes from the DB row.

A1, A2, A3 are MUST; A4-A7 are SHOULD but A5 and A7 are in the step 1.2 gate.
"""
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import text

from app.core.config import settings
from app.core.constants import JWT_ALG
from app.core.time import current_year

JOIN_CODE = "test-join-code"  # set by tests/conftest.py


def signup_body(**overrides) -> dict:
    body = {
        "name": "Asha Rao",
        "email": "asha@example.com",
        "password": "Sup3rSecret",
        "join_code": JOIN_CODE,
    }
    body.update(overrides)
    return body


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_a1_signup_creates_employee_with_code_and_balances(client, engine):
    response = client.post("/auth/signup", json=signup_body())

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert body["access_token"]
    user = body["user"]
    assert user["role"] == "EMPLOYEE"
    assert user["employee_code"] == "EMP-0001"
    assert user["email"] == "asha@example.com"
    assert "password_hash" not in user and "password" not in user

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT leave_type, year, total_days, used_days FROM leave_balances "
                "WHERE user_id = :u ORDER BY leave_type"
            ),
            {"u": user["id"]},
        ).all()
    assert [tuple(r) for r in rows] == [
        ("EARNED", current_year(), 12, 0),
        ("SICK", current_year(), 10, 0),
    ]


def test_a1_second_signup_gets_next_employee_code(client):
    client.post("/auth/signup", json=signup_body())
    second = client.post("/auth/signup", json=signup_body(email="ben@example.com"))
    assert second.json()["user"]["employee_code"] == "EMP-0002"


def test_a2_wrong_and_missing_join_code_return_identical_body(client):
    wrong = client.post("/auth/signup", json=signup_body(join_code="not-the-code"))
    missing_body = signup_body()
    del missing_body["join_code"]
    missing = client.post("/auth/signup", json=missing_body)

    assert wrong.status_code == 400
    assert missing.status_code == 400
    assert wrong.json()["code"] == "SIGNUP_FAILED"
    assert wrong.content == missing.content


def test_a2_join_code_is_checked_before_anything_else(client):
    client.post("/auth/signup", json=signup_body())

    # Existing email + bad code must not reveal that the email is taken.
    taken = client.post("/auth/signup", json=signup_body(join_code="not-the-code"))
    assert taken.status_code == 400
    assert taken.json()["code"] == "SIGNUP_FAILED"

    # A short password with a bad code still reports the generic signup error, not a 422.
    short = client.post(
        "/auth/signup", json=signup_body(email="new@example.com", password="x", join_code="nope")
    )
    assert short.status_code == 400
    assert short.json()["code"] == "SIGNUP_FAILED"

    # Empty body: no code supplied at all.
    empty = client.post("/auth/signup", json={})
    assert empty.status_code == 400
    assert empty.json()["code"] == "SIGNUP_FAILED"


def test_a3_role_in_body_is_ignored(client, engine):
    response = client.post("/auth/signup", json=signup_body(role="MANAGER"))

    assert response.status_code == 201
    assert response.json()["user"]["role"] == "EMPLOYEE"
    with engine.connect() as conn:
        role = conn.execute(
            text("SELECT role FROM users WHERE email = 'asha@example.com'")
        ).scalar_one()
    assert role == "EMPLOYEE"


def test_a4_short_password_is_rejected(client):
    response = client.post("/auth/signup", json=signup_body(password="short"))
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_a5_email_is_lowercased_and_login_is_case_insensitive(client, engine):
    signed_up = client.post("/auth/signup", json=signup_body(email="Mixed.Case@Example.COM"))
    assert signed_up.status_code == 201
    assert signed_up.json()["user"]["email"] == "mixed.case@example.com"
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT email FROM users")).scalar_one()
    assert stored == "mixed.case@example.com"

    login = client.post(
        "/auth/login", json={"email": "MIXED.CASE@EXAMPLE.COM", "password": "Sup3rSecret"}
    )
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "mixed.case@example.com"


def test_a6_duplicate_email_is_rejected(client):
    client.post("/auth/signup", json=signup_body())
    duplicate = client.post("/auth/signup", json=signup_body(email="ASHA@example.com"))
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "EMAIL_ALREADY_REGISTERED"


def test_login_returns_token_and_user(client):
    client.post("/auth/signup", json=signup_body())
    response = client.post(
        "/auth/login", json={"email": "asha@example.com", "password": "Sup3rSecret"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert body["user"]["role"] == "EMPLOYEE"


def test_a7_bad_password_and_unknown_email_return_401(client):
    client.post("/auth/signup", json=signup_body())

    bad_password = client.post(
        "/auth/login", json={"email": "asha@example.com", "password": "wrong-password"}
    )
    unknown = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "Sup3rSecret"}
    )

    assert bad_password.status_code == 401
    assert bad_password.json()["code"] == "INVALID_CREDENTIALS"
    assert unknown.status_code == 401
    assert unknown.content == bad_password.content


def test_a7_me_without_token_returns_401(client):
    response = client.get("/me")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_a7_me_with_garbage_token_returns_401(client):
    response = client.get("/me", headers=auth_header("not-a-jwt"))
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_a7_me_with_expired_token_returns_401(client):
    user = client.post("/auth/signup", json=signup_body()).json()["user"]
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    expired = jwt.encode(
        {
            "sub": str(user["id"]),
            "role": "EMPLOYEE",
            "iat": past,
            "exp": past + timedelta(minutes=60),
        },
        settings.secret_key,
        algorithm=JWT_ALG,
    )

    response = client.get("/me", headers=auth_header(expired))
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_a7_me_with_token_for_deleted_user_returns_401(client, engine):
    token = client.post("/auth/signup", json=signup_body()).json()["access_token"]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM leave_balances"))
        conn.execute(text("DELETE FROM users"))

    response = client.get("/me", headers=auth_header(token))
    assert response.status_code == 401


def test_me_returns_the_current_user(client):
    signed_up = client.post("/auth/signup", json=signup_body()).json()

    response = client.get("/me", headers=auth_header(signed_up["access_token"]))

    assert response.status_code == 200
    assert response.json() == signed_up["user"]


def test_role_comes_from_the_database_not_the_token(client, engine):
    user = client.post("/auth/signup", json=signup_body()).json()["user"]
    now = datetime.now(timezone.utc)
    forged = jwt.encode(
        {
            "sub": str(user["id"]),
            "role": "MANAGER",  # claim says manager, the DB row says employee
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.secret_key,
        algorithm=JWT_ALG,
    )

    response = client.get("/me", headers=auth_header(forged))
    assert response.status_code == 200
    assert response.json()["role"] == "EMPLOYEE"

    # And the reverse: promote in the DB, an old EMPLOYEE token now reads as MANAGER.
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET role = 'MANAGER' WHERE id = :u"), {"u": user["id"]})
    token = client.post(
        "/auth/login", json={"email": "asha@example.com", "password": "Sup3rSecret"}
    ).json()["access_token"]
    assert client.get("/me", headers=auth_header(token)).json()["role"] == "MANAGER"
