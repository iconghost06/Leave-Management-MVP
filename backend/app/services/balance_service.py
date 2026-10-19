from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.constants import ENTITLEMENTS
from app.models.leave_balance import LeaveBalance
from app.models.leave_request import LeaveRequest
from app.schemas.balance import BalanceOut


def ensure_balance_rows(db: Session, user_id: int, year: int) -> None:
    """Create the user's balance rows for `year` if missing (R1, R2).

    The only writer of total_days: values come from ENTITLEMENTS. ON CONFLICT DO NOTHING
    makes it safe to call repeatedly and concurrently. Does not commit; the caller does.
    """
    rows = [
        {"user_id": user_id, "leave_type": leave_type, "year": year, "total_days": total}
        for leave_type, total in ENTITLEMENTS.items()
    ]
    db.execute(insert(LeaveBalance).values(rows).on_conflict_do_nothing())


def lock_balance(db: Session, user_id: int, leave_type: str, year: int) -> LeaveBalance:
    """SELECT ... FOR UPDATE the balance row. Call ensure_balance_rows first (§4.1 step 3-4).

    populate_existing makes the locked read win over anything already in the identity map.
    """
    return db.execute(
        select(LeaveBalance)
        .where(
            LeaveBalance.user_id == user_id,
            LeaveBalance.leave_type == leave_type,
            LeaveBalance.year == year,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()


def pending_days(db: Session, user_id: int, leave_type: str, year: int) -> int:
    """SUM(days) of the user's PENDING requests for the type and year (R3).

    A request never spans two years, so its year is the year of its start_date.
    """
    total = db.scalar(
        select(func.coalesce(func.sum(LeaveRequest.days), 0)).where(
            LeaveRequest.user_id == user_id,
            LeaveRequest.leave_type == leave_type,
            LeaveRequest.status == "PENDING",
            LeaveRequest.start_date >= date(year, 1, 1),
            LeaveRequest.start_date <= date(year, 12, 31),
        )
    )
    return int(total)


def get_balance_summary(db: Session, user_id: int, year: int) -> list[BalanceOut]:
    """entitlement / used / pending / available per leave type (R3), creating missing rows (R2).

    Writes (the ensure step), so it commits once at the end.
    """
    ensure_balance_rows(db, user_id, year)
    balances = {
        b.leave_type: b
        for b in db.scalars(
            select(LeaveBalance).where(LeaveBalance.user_id == user_id, LeaveBalance.year == year)
        )
    }
    summary = []
    for leave_type in ENTITLEMENTS:
        row = balances[leave_type]
        pending = pending_days(db, user_id, leave_type, year)
        summary.append(
            BalanceOut(
                leave_type=leave_type,
                entitlement=row.total_days,
                used=row.used_days,
                pending=pending,
                available=row.total_days - row.used_days - pending,
            )
        )
    db.commit()
    return summary
