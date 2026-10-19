from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import User


class LeaveRequest(Base):
    """The overlap exclusion constraint (ex_leave_requests_no_overlap, R9) is created
    by hand in migration 0001 and is deliberately not declared here."""

    __tablename__ = "leave_requests"
    __table_args__ = (
        CheckConstraint("leave_type IN ('EARNED','SICK')", name="ck_leave_requests_leave_type"),
        CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','CANCELLED')",
            name="ck_leave_requests_status",
        ),
        CheckConstraint("end_date >= start_date", name="ck_leave_requests_dates"),
        CheckConstraint("days > 0", name="ck_leave_requests_days"),
        # R15 backstop. A NULL decided_by passes, which cancel relies on (Q3).
        CheckConstraint("decided_by <> user_id", name="ck_leave_requests_not_self"),
        Index("ix_leave_requests_user_status", "user_id", "status"),
        Index("ix_leave_requests_status", "status"),
        Index("ix_leave_requests_dates", "start_date", "end_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    leave_type: Mapped[str] = mapped_column(String(8))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    days: Mapped[int] = mapped_column(SmallInteger)
    reason: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), server_default="PENDING")
    decided_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_comment: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Loaded in the same SELECT so responses can show the requester's name and code with no
    # lazy load after commit. Locking queries use FOR UPDATE OF leave_requests (users is not locked).
    requester: Mapped[User] = relationship(
        foreign_keys=[user_id], lazy="joined", innerjoin=True
    )
