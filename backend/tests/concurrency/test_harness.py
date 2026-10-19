"""The harness must be able to fail: a green race test means nothing if it cannot go red.

These run once each (no repeats). They are the proof that the three failure paths work:
a non-AppError exception, a hang, and a broken invariant.
"""
import threading

import pytest
from sqlalchemy import text

from app.core.errors import AppError
from tests.concurrency import conftest as harness
from tests.concurrency.conftest import Call, assert_invariants


def test_an_app_error_counts_as_its_http_status(seeded, race):
    def conflict(db, user):
        raise AppError(409, "ALREADY_ACTIONED", "x")

    ok, conflicted = race(
        Call(seeded["employee1@example.com"], lambda db, user: None),
        Call(seeded["employee2@example.com"], conflict, ok_status=200),
    )

    assert (ok.status, conflicted.status, conflicted.code) == (200, 409, "ALREADY_ACTIONED")


def test_a_non_app_error_fails_the_run(seeded, race):
    def boom(db, user):
        raise ValueError("not an AppError")

    with pytest.raises(AssertionError, match="ValueError"):
        race(Call(seeded["employee1@example.com"], boom), Call(seeded["employee2@example.com"], lambda db, u: None))


def test_a_thread_that_never_finishes_fails_instead_of_hanging(seeded, race, monkeypatch):
    monkeypatch.setattr(harness, "JOIN_TIMEOUT", 1)
    release = threading.Event()
    try:
        with pytest.raises(AssertionError, match="deadlock or hang"):
            race(
                Call(seeded["employee1@example.com"], lambda db, user: release.wait(10)),
                Call(seeded["employee2@example.com"], lambda db, user: None),
            )
    finally:
        release.set()


def test_a_missing_barrier_partner_fails_instead_of_hanging(seeded, monkeypatch):
    """If one thread never reaches the barrier, the others get BrokenBarrierError, which is a failure."""
    import threading as t

    barrier = t.Barrier(2, timeout=0.5)
    results = [None]
    harness._worker(0, Call(seeded["employee1@example.com"], lambda db, u: None), barrier, results)

    assert results[0].crashed and results[0].code == "BrokenBarrierError"


def test_invariants_catch_used_that_disagrees_with_approved_rows(seeded, engine):
    with engine.begin() as conn:
        conn.execute(text("UPDATE leave_balances SET used_days = 3 WHERE leave_type = 'EARNED' AND user_id = :u"),
                     {"u": seeded["employee1@example.com"]})

    with pytest.raises(AssertionError, match="used != sum of APPROVED days"):
        assert_invariants(engine)


def test_invariants_catch_negative_available(seeded, engine, create_request):
    create_request("employee1", ("2026-11-02", "2026-11-06"))  # 5 pending
    with engine.begin() as conn:
        # used 12 with 5 pending: available = 12 - 12 - 5 < 0 (and used != approved)
        conn.execute(text("UPDATE leave_balances SET used_days = 12 WHERE leave_type = 'EARNED' AND user_id = :u"),
                     {"u": seeded["employee1@example.com"]})

    with pytest.raises(AssertionError, match="available < 0"):
        assert_invariants(engine)


def test_invariants_pass_on_a_clean_database(seeded, engine):
    assert_invariants(engine)
