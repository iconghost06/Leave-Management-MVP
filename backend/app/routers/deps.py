from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal


def get_db() -> Iterator[Session]:
    """One Session per request. Never commits: services commit once, as their last step.

    On any exception (including AppError) the open transaction is rolled back and the
    exception re-raised. close() always runs and also ends an uncommitted read-only txn.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
