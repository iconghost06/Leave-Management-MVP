"""B2 (MUST): GET /balances creates missing current-year rows (R2).

B1 (balances after a submit *and an approve*) is completed in step 3.1, because it needs approve.
The pending/used figures below are the R3 arithmetic that B1 builds on.
"""
from datetime import date

from sqlalchemy import text

from tests.api.helpers import WEEK_1, WEEK_2, balance_of, submit


def rows_for(engine, user_id: int):
    with engine.connect() as conn:
        return [
            tuple(r)
            for r in conn.execute(
                text(
                    "SELECT leave_type, year, total_days, used_days FROM leave_balances "
                    "WHERE user_id = :u ORDER BY year, leave_type"
                ),
                {"u": user_id},
            )
        ]


def test_b2_get_balances_creates_missing_rows_when_deleted(client, engine, seeded, login_headers):
    uid = seeded["employee1@example.com"]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM leave_balances WHERE user_id = :u"), {"u": uid})
    assert rows_for(engine, uid) == []

    response = client.get("/balances", headers=login_headers("employee1"))

    assert response.status_code == 200
    assert response.json() == {
        "year": 2026,
        "balances": [
            {"leave_type": "EARNED", "entitlement": 12, "used": 0, "pending": 0, "available": 12},
            {"leave_type": "SICK", "entitlement": 10, "used": 0, "pending": 0, "available": 10},
        ],
    }
    assert rows_for(engine, uid) == [("EARNED", 2026, 12, 0), ("SICK", 2026, 10, 0)]


def test_b2_get_balances_creates_next_years_rows_when_the_clock_rolls_over(
    client, engine, seeded, login_headers, monkeypatch
):
    uid = seeded["employee1@example.com"]
    headers = login_headers("employee1")
    monkeypatch.setattr("app.core.time.company_today", lambda: date(2027, 1, 5))

    response = client.get("/balances", headers=headers)

    assert response.status_code == 200
    assert response.json()["year"] == 2027
    assert [b["available"] for b in response.json()["balances"]] == [12, 10]
    # 2026 rows are untouched and nothing carries forward.
    assert rows_for(engine, uid) == [
        ("EARNED", 2026, 12, 0),
        ("SICK", 2026, 10, 0),
        ("EARNED", 2027, 12, 0),
        ("SICK", 2027, 10, 0),
    ]


def test_b2_repeated_get_balances_does_not_duplicate_or_reset_rows(
    client, engine, seeded, login_headers
):
    uid = seeded["employee1@example.com"]
    headers = login_headers("employee1")
    with engine.begin() as conn:
        conn.execute(text("UPDATE leave_balances SET used_days = 3 WHERE leave_type = 'EARNED'"))

    assert client.get("/balances", headers=headers).status_code == 200
    assert client.get("/balances", headers=headers).status_code == 200

    assert rows_for(engine, uid) == [("EARNED", 2026, 12, 3), ("SICK", 2026, 10, 0)]


def test_balances_require_authentication(client):
    response = client.get("/balances")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_available_is_entitlement_minus_used_minus_pending(
    client, engine, seeded, login_headers, set_status
):
    """R3: pending is computed from PENDING rows; used only moves when a row is APPROVED."""
    headers = login_headers("employee1")
    manager_id = seeded["manager1@example.com"]
    approved = submit(client, headers, *WEEK_1).json()
    set_status(approved["id"], "APPROVED", decided_by=manager_id)
    submit(client, headers, *WEEK_2)

    assert balance_of(client, headers, "EARNED") == {
        "leave_type": "EARNED",
        "entitlement": 12,
        "used": 5,
        "pending": 5,
        "available": 2,
    }
    assert balance_of(client, headers, "SICK")["available"] == 10  # types are tracked separately
