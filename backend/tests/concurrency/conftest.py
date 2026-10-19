"""Barrier harness and invariant checker for the race tests (DESIGN §8.3, §4.5).

Each racing call runs in its own thread with its own Session, calling the service function
directly. A threading.Barrier releases them together once every thread has opened its
transaction (the user SELECT, as get_current_user does), so the service's locks decide who wins.

Outcomes: an AppError counts as its HTTP status. Any other exception (a deadlock 40P01, an
IntegrityError, a bug) counts as a 500 and fails the test. A barrier or thread that times out
fails the test instead of hanging the suite.
"""
import threading
import traceback
from dataclasses import dataclass
from typing import Any, Callable

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

BARRIER_TIMEOUT = 10  # seconds for all threads to arrive
JOIN_TIMEOUT = 30  # seconds for all threads to finish once released
REPEATS = 20  # DESIGN §8: every scenario runs 20 times

repeat = pytest.mark.parametrize("attempt", range(REPEATS))


def pytest_collection_modifyitems(items):
    """Everything under tests/concurrency is a concurrency test (`pytest -m concurrency`)."""
    for item in items:
        if "tests/concurrency/" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.concurrency)


@dataclass
class Call:
    """One racing transaction: run `fn(db, user)` as `user_id`; a normal return counts as `ok_status`."""

    user_id: int
    fn: Callable[[Session, Any], Any]
    ok_status: int = 200


@dataclass
class Outcome:
    status: int
    code: str | None = None
    error: BaseException | None = None
    trace: str = ""

    @property
    def crashed(self) -> bool:
        return self.error is not None


def _worker(index: int, call: Call, barrier: threading.Barrier, results: list) -> None:
    from app.core.errors import AppError
    from app.db.session import SessionLocal
    from app.models.user import User

    db = SessionLocal()  # one session per thread
    try:
        user = db.get(User, call.user_id)  # opens the transaction, like get_current_user
        barrier.wait(timeout=BARRIER_TIMEOUT)
        call.fn(db, user)
        results[index] = Outcome(call.ok_status)
    except AppError as exc:
        _rollback(db)  # what get_db does on any exception
        results[index] = Outcome(exc.status, exc.code)
    except BaseException as exc:  # noqa: BLE001 - anything that is not an AppError is a failure
        _rollback(db)
        results[index] = Outcome(500, type(exc).__name__, exc, traceback.format_exc())
    finally:
        db.close()


def _rollback(db: Session) -> None:
    try:
        db.rollback()
    except Exception:  # noqa: BLE001 - a broken connection must not hide the original error
        pass


def assert_invariants(engine) -> None:
    """The safety properties that must hold after every race (DESIGN §8.3, SPEC §3).

    1. 0 <= used <= total on every balance row.
    2. available = total - used - pending >= 0 on every balance row.
    3. No two PENDING/APPROVED requests of one user share a day.
    4. used equals the sum of that row's APPROVED days (every approval counted exactly once).
    """
    problems: list[str] = []
    with engine.connect() as conn:
        for row in conn.execute(
            text("SELECT user_id, leave_type, year, total_days, used_days FROM leave_balances "
                 "WHERE used_days < 0 OR used_days > total_days")
        ):
            problems.append(f"used out of range: {tuple(row)}")

        for row in conn.execute(
            text(
                """
                SELECT b.user_id, b.leave_type, b.year, b.total_days, b.used_days, p.pending
                FROM leave_balances b
                CROSS JOIN LATERAL (
                    SELECT COALESCE(SUM(r.days), 0) AS pending
                    FROM leave_requests r
                    WHERE r.user_id = b.user_id AND r.leave_type = b.leave_type
                      AND r.status = 'PENDING'
                      AND EXTRACT(YEAR FROM r.start_date) = b.year
                ) p
                WHERE b.total_days - b.used_days - p.pending < 0
                """
            )
        ):
            problems.append(f"available < 0: {tuple(row)}")

        for row in conn.execute(
            text(
                """
                SELECT a.id, b.id FROM leave_requests a
                JOIN leave_requests b ON a.user_id = b.user_id AND a.id < b.id
                WHERE a.status IN ('PENDING','APPROVED') AND b.status IN ('PENDING','APPROVED')
                  AND daterange(a.start_date, a.end_date, '[]') && daterange(b.start_date, b.end_date, '[]')
                """
            )
        ):
            problems.append(f"overlapping active requests: {tuple(row)}")

        for row in conn.execute(
            text(
                """
                SELECT b.user_id, b.leave_type, b.year, b.used_days, a.approved
                FROM leave_balances b
                CROSS JOIN LATERAL (
                    SELECT COALESCE(SUM(r.days), 0) AS approved
                    FROM leave_requests r
                    WHERE r.user_id = b.user_id AND r.leave_type = b.leave_type
                      AND r.status = 'APPROVED'
                      AND EXTRACT(YEAR FROM r.start_date) = b.year
                ) a
                WHERE b.used_days <> a.approved
                """
            )
        ):
            problems.append(f"used != sum of APPROVED days: {tuple(row)}")

    assert not problems, "invariants violated:\n  " + "\n  ".join(problems)


@pytest.fixture
def race(engine):
    """race(*calls) -> [Outcome, ...] in call order. Fails on a crash, a hang or a broken invariant."""

    def run(*calls: Call) -> list[Outcome]:
        barrier = threading.Barrier(len(calls), timeout=BARRIER_TIMEOUT)
        results: list[Outcome | None] = [None] * len(calls)
        threads = [
            threading.Thread(target=_worker, args=(i, c, barrier, results), daemon=True)
            for i, c in enumerate(calls)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=JOIN_TIMEOUT)

        hung = [i for i, t in enumerate(threads) if t.is_alive()]
        assert not hung, f"thread(s) {hung} did not finish in {JOIN_TIMEOUT}s: deadlock or hang"

        crashed = [o for o in results if o is None or o.crashed]
        assert not crashed, "a racing call raised something other than AppError (a 500):\n" + "\n".join(
            "no outcome recorded" if o is None else o.trace for o in crashed
        )

        assert_invariants(engine)  # after every X run
        return results  # type: ignore[return-value]

    return run


# ---------------------------------------------------------------- setup helpers


@pytest.fixture
def create_request(seeded):
    """create_request("employee1", ("2026-11-02", "2026-11-06"), "EARNED") -> request id (PENDING)."""
    from datetime import date

    from app.db.session import SessionLocal
    from app.models.user import User
    from app.schemas.leave_request import LeaveRequestIn
    from app.services.leave_request_service import submit_request

    def _create(who: str, dates: tuple[str, str], leave_type: str = "EARNED") -> int:
        with SessionLocal() as db:
            user = db.get(User, seeded[f"{who}@example.com"])
            data = LeaveRequestIn(
                leave_type=leave_type,
                start_date=date.fromisoformat(dates[0]),
                end_date=date.fromisoformat(dates[1]),
            )
            return submit_request(db, user, data).id

    return _create


@pytest.fixture
def snapshot(engine):
    """snapshot(request_id) -> (status, decided_by); used_of(user_id, type) -> used_days."""

    def _status(request_id: int):
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT status, decided_by FROM leave_requests WHERE id = :id"),
                {"id": request_id},
            ).one()

    return _status


@pytest.fixture
def used_of(engine):
    def _used(user_id: int, leave_type: str = "EARNED") -> int:
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT used_days FROM leave_balances WHERE user_id = :u AND leave_type = :t"),
                {"u": user_id, "t": leave_type},
            ).scalar_one()

    return _used
