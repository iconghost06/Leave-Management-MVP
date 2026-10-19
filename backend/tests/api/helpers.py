"""Small helpers shared by the step 2.2 API tests (balances, submit, cancel, views).

"Today" is frozen at Mon 2026-10-19 by the `frozen_today` fixture, so every date below is
a weekday range in Nov-Dec 2026: in the current year and in the future.
"""
from sqlalchemy import text

# Mon-Fri weeks, 5 working days each.
WEEK_1 = ("2026-11-02", "2026-11-06")
WEEK_2 = ("2026-11-09", "2026-11-13")
WEEK_3 = ("2026-11-16", "2026-11-20")


def body(start: str, end: str, leave_type: str = "EARNED", **extra) -> dict:
    return {"leave_type": leave_type, "start_date": start, "end_date": end, **extra}


def submit(client, headers, start: str, end: str, leave_type: str = "EARNED", **extra):
    return client.post("/leave-requests", headers=headers, json=body(start, end, leave_type, **extra))


def balance_of(client, headers, leave_type: str = "EARNED") -> dict:
    response = client.get("/balances", headers=headers)
    assert response.status_code == 200, response.text
    return next(b for b in response.json()["balances"] if b["leave_type"] == leave_type)


def request_row(engine, request_id: int):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT * FROM leave_requests WHERE id = :id"), {"id": request_id}
        ).one_or_none()


def count_requests(engine, user_id: int | None = None) -> int:
    with engine.connect() as conn:
        if user_id is None:
            return conn.execute(text("SELECT count(*) FROM leave_requests")).scalar_one()
        return conn.execute(
            text("SELECT count(*) FROM leave_requests WHERE user_id = :u"), {"u": user_id}
        ).scalar_one()
