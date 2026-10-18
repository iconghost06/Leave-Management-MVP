"""Idempotent seed (DESIGN §6.3): `python -m scripts.seed`, run after `alembic upgrade head`.

The only way a MANAGER can exist (R23). Demo passwords are for non-production use only.
Existing users are never modified, so re-running does not reset a password or role and
does not consume an employee_code_seq value.
"""
from sqlalchemy import select

from app.core.time import current_year
from app.db.session import SessionLocal
from app.models.user import User
from app.services.auth_service import create_user, normalize_email
from app.services.balance_service import ensure_balance_rows

SEED_USERS = [
    ("Manager One", "manager1@example.com", "MANAGER", "Manager@123"),
    ("Manager Two", "manager2@example.com", "MANAGER", "Manager@123"),
    ("Employee One", "employee1@example.com", "EMPLOYEE", "Employee@123"),
    ("Employee Two", "employee2@example.com", "EMPLOYEE", "Employee@123"),
    ("Employee Three", "employee3@example.com", "EMPLOYEE", "Employee@123"),
]


def run_seed() -> int:
    """Insert any missing seed users and every user's current-year balance rows.

    Returns the number of users created. One commit, as the last step.
    """
    created = 0
    with SessionLocal() as db:
        for name, email, role, password in SEED_USERS:
            exists = db.scalar(select(User.id).where(User.email == normalize_email(email)))
            if exists is None:
                create_user(db, name=name, email=email, password=password, role=role)
                created += 1

        year = current_year()
        for user_id in db.scalars(select(User.id)):
            ensure_balance_rows(db, user_id, year)
        db.commit()
    return created


def main() -> None:
    created = run_seed()
    print(f"Seed complete: {created} created, {len(SEED_USERS) - created} already existed.")


if __name__ == "__main__":
    main()
