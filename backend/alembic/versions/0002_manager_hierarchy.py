"""manager hierarchy: users.manager_id

Hand-written. A MANAGER whose manager_id is NULL is the "super manager" (no new role). Existing
users keep manager_id NULL until the seed or signup assigns one.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("manager_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_users_manager_id", "users", "users", ["manager_id"], ["id"], ondelete="SET NULL"
    )
    op.create_check_constraint("ck_users_manager_not_self", "users", "manager_id <> id")


def downgrade() -> None:
    op.drop_constraint("ck_users_manager_not_self", "users", type_="check")
    op.drop_constraint("fk_users_manager_id", "users", type_="foreignkey")
    op.drop_column("users", "manager_id")
