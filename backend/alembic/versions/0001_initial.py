"""initial schema

Hand-written: autogenerate cannot emit the EXCLUDE constraint (DESIGN §2.3).

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Must come first: the exclusion constraint below mixes = on user_id with && on a daterange.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.execute("CREATE SEQUENCE employee_code_seq")

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("employee_code", sa.String(16), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(16), server_default="EMPLOYEE", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("employee_code", name="uq_users_employee_code"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
        sa.CheckConstraint("role IN ('EMPLOYEE','MANAGER')", name="ck_users_role"),
    )

    op.create_table(
        "leave_balances",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("leave_type", sa.String(8), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("total_days", sa.SmallInteger(), nullable=False),
        sa.Column("used_days", sa.SmallInteger(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("user_id", "leave_type", "year", name="pk_leave_balances"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_leave_balances_user_id"),
        sa.CheckConstraint("leave_type IN ('EARNED','SICK')", name="ck_leave_balances_leave_type"),
        sa.CheckConstraint(
            "used_days >= 0 AND used_days <= total_days", name="ck_leave_balances_used_range"
        ),
    )

    op.create_table(
        "leave_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("leave_type", sa.String(8), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("days", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("status", sa.String(16), server_default="PENDING", nullable=False),
        sa.Column("decided_by", sa.BigInteger(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_comment", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_leave_requests"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_leave_requests_user_id"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], name="fk_leave_requests_decided_by"),
        sa.CheckConstraint("leave_type IN ('EARNED','SICK')", name="ck_leave_requests_leave_type"),
        sa.CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','CANCELLED')",
            name="ck_leave_requests_status",
        ),
        sa.CheckConstraint("end_date >= start_date", name="ck_leave_requests_dates"),
        sa.CheckConstraint("days > 0", name="ck_leave_requests_days"),
        sa.CheckConstraint("decided_by <> user_id", name="ck_leave_requests_not_self"),
    )

    # R9 backstop: no overlapping PENDING/APPROVED ranges per user, any leave type.
    # Violation is SQLSTATE 23P01, mapped to 409 OVERLAPPING_REQUEST by the service layer.
    op.execute(
        """
        ALTER TABLE leave_requests
        ADD CONSTRAINT ex_leave_requests_no_overlap
        EXCLUDE USING gist (
            user_id WITH =,
            daterange(start_date, end_date, '[]') WITH &&
        ) WHERE (status IN ('PENDING','APPROVED'))
        """
    )

    op.create_index("ix_leave_requests_user_status", "leave_requests", ["user_id", "status"])
    op.create_index("ix_leave_requests_status", "leave_requests", ["status"])
    op.create_index("ix_leave_requests_dates", "leave_requests", ["start_date", "end_date"])


def downgrade() -> None:
    # Dropping the table drops its indexes and the exclusion constraint.
    op.drop_table("leave_requests")
    op.drop_table("leave_balances")
    op.drop_table("users")
    op.execute("DROP SEQUENCE employee_code_seq")
    # btree_gist is left installed on purpose: other objects may depend on it.
