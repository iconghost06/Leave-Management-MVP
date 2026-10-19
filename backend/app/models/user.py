from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
        CheckConstraint("role IN ('EMPLOYEE','MANAGER')", name="ck_users_role"),
        CheckConstraint("manager_id <> id", name="ck_users_manager_not_self"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), server_default="EMPLOYEE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # NULL on a MANAGER marks the "super manager": nobody approves their leave, and they cannot
    # submit any. SET NULL, so deleting a manager never deletes their reports.
    manager_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL", name="fk_users_manager_id")
    )

    # Joined so responses can show manager_name with no lazy load after the session closes.
    manager: Mapped["User | None"] = relationship(
        remote_side=[id], foreign_keys=[manager_id], lazy="joined"
    )
