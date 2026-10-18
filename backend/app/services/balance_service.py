from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.constants import ENTITLEMENTS
from app.models.leave_balance import LeaveBalance


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
