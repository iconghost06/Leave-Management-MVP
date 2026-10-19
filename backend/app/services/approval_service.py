from sqlalchemy import extract, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import ENTITLEMENTS
from app.core.errors import AppError
from app.models.leave_balance import LeaveBalance
from app.models.leave_request import LeaveRequest
from app.models.user import User
from app.schemas.leave_request import ManagerRequestOut
from app.services.balance_service import ensure_balance_rows, lock_balance
from app.services.leave_request_service import lock_request

CHECK_VIOLATION = "23514"
USED_RANGE_CONSTRAINT = "ck_leave_balances_used_range"

INSUFFICIENT_MESSAGE = "Approving this request would use more days than the employee's entitlement."


def _fits(balance: LeaveBalance, days: int) -> bool:
    """R17: used + days must stay within the entitlement."""
    return balance.used_days + days <= balance.total_days


def _lock_for_decision(
    db: Session, decider: User, request_id: int
) -> tuple[LeaveRequest, LeaveBalance]:
    """Shared steps 1-4 of approve and reject (DESIGN §4.2, §4.3).

    Lock order: request row, then the requester's balance row (Q4). Then self (403), then
    status (409), in that order (R15, R16): the self check comes first, so a manager gets
    SELF_ACTION_FORBIDDEN even on their own already-actioned request (P5).
    """
    request = lock_request(db, request_id)  # step 1
    year = request.start_date.year  # Q11: the balance year is the year of start_date
    ensure_balance_rows(db, request.user_id, year)  # step 2
    balance = lock_balance(db, request.user_id, request.leave_type, year)

    if request.user_id == decider.id:  # step 3
        raise AppError(403, "SELF_ACTION_FORBIDDEN", "You cannot approve or reject your own request.")
    if request.status != "PENDING":  # step 4
        raise AppError(409, "ALREADY_ACTIONED", "This request has already been actioned.")
    return request, balance


def _record_decision(
    request: LeaveRequest, decider: User, status: str, comment: str | None
) -> None:
    request.status = status
    request.decider = decider  # sets decided_by on flush and lets the response show the name
    request.decided_at = func.now()
    request.decision_comment = comment


def approve_request(
    db: Session, decider: User, request_id: int, comment: str | None = None
) -> LeaveRequest:
    """DESIGN §4.2. Locks request -> balance. One commit, last. `require_manager` runs in the router."""
    request, balance = _lock_for_decision(db, decider, request_id)

    if not _fits(balance, request.days):  # step 5
        raise AppError(409, "INSUFFICIENT_BALANCE", INSUFFICIENT_MESSAGE)

    balance.used_days += request.days  # step 6
    _record_decision(request, decider, "APPROVED", _clean(comment))
    _flush(db, request)
    db.commit()  # step 7
    return request


def reject_request(
    db: Session, decider: User, request_id: int, comment: str | None
) -> LeaveRequest:
    """DESIGN §4.3. Same locks as approve (Q4). The balance is read-locked but never changed.

    The comment check comes after the status check (Q5), so a blank comment on an
    already-actioned request is 409, not 422.
    """
    request, _ = _lock_for_decision(db, decider, request_id)

    cleaned = _clean(comment)
    if cleaned is None:  # step 5
        raise AppError(422, "COMMENT_REQUIRED", "A comment is required when rejecting a request.")

    _record_decision(request, decider, "REJECTED", cleaned)  # step 6
    _flush(db, request)
    db.commit()  # step 7
    return request


def list_manager_requests(
    db: Session, manager: User, status: str | None = None
) -> list[ManagerRequestOut]:
    """Pending queue and history for a manager (R19, Q7, Q8). Read-only: no lock, no commit.

    Never returns the caller's own requests. PENDING is oldest first (`created_at` asc); every
    other filter, and no filter at all, is newest first. `employee_available` is set on PENDING
    rows only.
    """
    query = select(LeaveRequest).where(LeaveRequest.user_id != manager.id)
    if status is not None:
        query = query.where(LeaveRequest.status == status)
    if status == "PENDING":
        query = query.order_by(LeaveRequest.created_at.asc(), LeaveRequest.id.asc())
    else:
        query = query.order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc())
    requests = list(db.scalars(query))

    available = _employee_available(db, [r for r in requests if r.status == "PENDING"])
    return [
        ManagerRequestOut.model_validate(r).model_copy(
            update={"employee_available": available.get(r.id)}
        )
        for r in requests
    ]


def _employee_available(db: Session, pending: list[LeaveRequest]) -> dict[int, int]:
    """request id -> the requester's `available` for that request's type and year (R3).

    Two queries for the whole page, not two per row. A missing balance row (the lazy-creation
    rule, R2) counts as the full entitlement with nothing used.
    """
    if not pending:
        return {}
    user_ids = {r.user_id for r in pending}
    years = {r.start_date.year for r in pending}

    used = {
        (b.user_id, b.leave_type, b.year): (b.total_days, b.used_days)
        for b in db.scalars(
            select(LeaveBalance).where(
                LeaveBalance.user_id.in_(user_ids), LeaveBalance.year.in_(years)
            )
        )
    }
    year_of = extract("year", LeaveRequest.start_date)
    reserved = {
        (user_id, leave_type, int(year)): int(days)
        for user_id, leave_type, year, days in db.execute(
            select(LeaveRequest.user_id, LeaveRequest.leave_type, year_of, func.sum(LeaveRequest.days))
            .where(LeaveRequest.status == "PENDING", LeaveRequest.user_id.in_(user_ids))
            .group_by(LeaveRequest.user_id, LeaveRequest.leave_type, year_of)
        )
    }

    result = {}
    for r in pending:
        key = (r.user_id, r.leave_type, r.start_date.year)
        total, used_days = used.get(key, (ENTITLEMENTS[r.leave_type], 0))
        result[r.id] = total - used_days - reserved.get(key, 0)
    return result


def _clean(comment: str | None) -> str | None:
    """Trim; a blank comment counts as no comment (R18, Q5)."""
    if comment is None:
        return None
    return comment.strip() or None


def _flush(db: Session, request: LeaveRequest) -> None:
    """Write the decision inside the open transaction, so commit() stays the last statement.

    `decided_at` was set to now() (the DB clock); read it back so the response can serialise it.
    """
    try:
        db.flush()
    except IntegrityError as exc:
        # Backstop for the check in approve. No further statements; get_db rolls back.
        if _violated_constraint(exc) == USED_RANGE_CONSTRAINT:
            raise AppError(409, "INSUFFICIENT_BALANCE", INSUFFICIENT_MESSAGE) from None
        raise
    db.refresh(request, ["decided_at"])


def _violated_constraint(exc: IntegrityError) -> str | None:
    if getattr(exc.orig, "sqlstate", None) != CHECK_VIOLATION:
        return None
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
