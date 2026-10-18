from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LeaveBalance(Base):
    __tablename__ = "leave_balances"
    __table_args__ = (
        CheckConstraint("leave_type IN ('EARNED','SICK')", name="ck_leave_balances_leave_type"),
        # R17 backstop: used can never exceed entitlement, even if a service has a bug.
        CheckConstraint(
            "used_days >= 0 AND used_days <= total_days", name="ck_leave_balances_used_range"
        ),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    leave_type: Mapped[str] = mapped_column(String(8), primary_key=True)
    year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    total_days: Mapped[int] = mapped_column(SmallInteger)
    used_days: Mapped[int] = mapped_column(SmallInteger, server_default="0")
