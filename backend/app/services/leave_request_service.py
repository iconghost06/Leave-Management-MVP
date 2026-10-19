from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import FORBIDDEN, NOT_FOUND, AppError
from app.core.time import current_year
from app.models.leave_request import LeaveRequest
from app.models.user import User
from app.schemas.leave_request import LeaveRequestIn
from app.services.balance_service import (
    ensure_balance_rows,
    lock_balance,
    pending_days,
)
from app.services.working_days import count_working_days

EXCLUSION_VIOLATION = "23P01"

OVERLAPPING_MESSAGE = "These dates overlap one of your pending or approved requests."


def validate_dates(start: date, end: date) -> tuple[int, int]:
    """Return (days, year) or raise the first failing rule (R5-R8, R11).

    Order is SPEC section 6: INVALID_DATE_RANGE, NO_WORKING_DAYS,
    SPANS_MULTIPLE_YEARS, NOT_CURRENT_YEAR. "Today" comes from core.time only.
    """
    if end < start:
        raise AppError(422, "INVALID_DATE_RANGE", "End date must not be before start date")

    days = count_working_days(start, end)
    if days == 0:
        raise AppError(422, "NO_WORKING_DAYS", "The selected range has no working days")

    if start.year != end.year:
        raise AppError(
            422,
            "SPANS_MULTIPLE_YEARS",
            "Leave cannot span two calendar years; submit one request per year",
        )

    if start.year != current_year():
        raise AppError(422, "NOT_CURRENT_YEAR", "Leave must be within the current calendar year")

    return days, start.year


def _has_overlap(db: Session, user_id: int, start: date, end: date) -> bool:
    """Any of the user's own PENDING/APPROVED requests, of either type, sharing a day (R9, R12)."""
    window = func.daterange(start, end, "[]")
    stored = func.daterange(LeaveRequest.start_date, LeaveRequest.end_date, "[]")
    found = db.scalar(
        select(LeaveRequest.id)
        .where(
            LeaveRequest.user_id == user_id,
            LeaveRequest.status.in_(("PENDING", "APPROVED")),
            stored.op("&&")(window),
        )
        .limit(1)
    )
    return found is not None


def submit_request(db: Session, user: User, data: LeaveRequestIn) -> LeaveRequest:
    """DESIGN §4.1. Lock order: advisory(user) -> balance row. One commit, last.

    The advisory lock serializes every submit by this user, across both leave types, so the
    overlap and balance checks below always see the previous submit's committed row.
    """
    days, year = validate_dates(data.start_date, data.end_date)  # step 1; year = start_date.year

    db.execute(select(func.pg_advisory_xact_lock(user.id)))  # step 2
    ensure_balance_rows(db, user.id, year)  # step 3
    balance = lock_balance(db, user.id, data.leave_type, year)  # step 4

    if _has_overlap(db, user.id, data.start_date, data.end_date):  # step 5
        raise AppError(409, "OVERLAPPING_REQUEST", OVERLAPPING_MESSAGE)

    pending = pending_days(db, user.id, data.leave_type, year)  # step 6
    available = balance.total_days - balance.used_days - pending
    if days > available:
        raise AppError(
            409,
            "INSUFFICIENT_BALANCE",
            f"Requested {days} day(s) but only {available} {data.leave_type.title()} day(s) are available.",
        )

    request = LeaveRequest(
        user_id=user.id,
        leave_type=data.leave_type,
        start_date=data.start_date,
        end_date=data.end_date,
        days=days,
        reason=data.reason,
        requester=user,
    )
    db.add(request)
    try:
        db.flush()  # step 7
    except IntegrityError as exc:
        # Backstop for a write path that skipped the check above. No further statements; get_db rolls back.
        if getattr(exc.orig, "sqlstate", None) == EXCLUSION_VIOLATION:
            raise AppError(409, "OVERLAPPING_REQUEST", OVERLAPPING_MESSAGE) from None
        raise
    db.commit()  # step 8
    return request


def cancel_request(db: Session, user: User, request_id: int) -> LeaveRequest:
    """DESIGN §4.4. Locks only the request row. Ownership (403) is checked before status (409) (Q14).

    decided_by and decided_at stay NULL: the CHECK forbids the requester as decided_by, and a
    cancel is not a decision (Q3).
    """
    request = _lock_request(db, request_id)
    if request.user_id != user.id:
        raise AppError(403, FORBIDDEN, "Only the requester can cancel this request.")
    if request.status != "PENDING":
        raise AppError(409, "ALREADY_ACTIONED", "Only a pending request can be cancelled.")
    request.status = "CANCELLED"
    db.commit()
    return request


def list_own_requests(db: Session, user: User, status: str | None = None) -> list[LeaveRequest]:
    """The caller's own requests, newest first, optionally one status (V5)."""
    query = select(LeaveRequest).where(LeaveRequest.user_id == user.id)
    if status is not None:
        query = query.where(LeaveRequest.status == status)
    return list(db.scalars(query.order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc())))


def get_request_for_viewer(db: Session, viewer: User, request_id: int) -> LeaveRequest:
    """The owner or any manager may read a request; anyone else gets 403 (R20, Q13)."""
    request = db.get(LeaveRequest, request_id)
    if request is None:
        raise _not_found()
    if request.user_id != viewer.id and viewer.role != "MANAGER":
        raise AppError(403, FORBIDDEN, "You can only view your own requests.")
    return request


def _lock_request(db: Session, request_id: int) -> LeaveRequest:
    """SELECT ... FOR UPDATE OF leave_requests (the joined users row is not locked)."""
    request = db.scalar(
        select(LeaveRequest)
        .where(LeaveRequest.id == request_id)
        .with_for_update(of=LeaveRequest)
        .execution_options(populate_existing=True)
    )
    if request is None:
        raise _not_found()
    return request


def _not_found() -> AppError:
    return AppError(404, NOT_FOUND, "Leave request not found.")
