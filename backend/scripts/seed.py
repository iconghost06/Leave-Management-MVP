"""Idempotent seed (DESIGN §6.3): `python -m scripts.seed`, run after `alembic upgrade head`.

The only way a MANAGER can exist (R23). Demo passwords are for non-production use only.
Existing users keep their name, role and password, so re-running does not reset them and does
not consume an employee_code_seq value. The one thing the seed does set on existing users is
`manager_id`, so a database seeded before the hierarchy existed picks it up on the next run.
"""
from sqlalchemy import select

from app.core.time import current_year
from app.db.session import SessionLocal
from app.models.user import User
from app.services.auth_service import create_user, normalize_email
from app.services.balance_service import ensure_balance_rows

# New users go at the end, so the employee codes the earlier seed users already have do not shift.
SEED_USERS = [
    ("Manager One", "manager1@example.com", "MANAGER", "Manager@123"),
    ("Manager Two", "manager2@example.com", "MANAGER", "Manager@123"),
    ("Employee One", "employee1@example.com", "EMPLOYEE", "Employee@123"),
    ("Employee Two", "employee2@example.com", "EMPLOYEE", "Employee@123"),
    ("Employee Three", "employee3@example.com", "EMPLOYEE", "Employee@123"),
    ("Super Manager", "supermanager@example.com", "MANAGER", "Manager@123"),
    ("Employee Four", "employee4@example.com", "EMPLOYEE", "Employee@123"),
]

# email -> email of that user's manager. None is the super manager: a MANAGER with no manager.
MANAGERS = {
    "supermanager@example.com": None,
    "manager1@example.com": "supermanager@example.com",
    "manager2@example.com": "supermanager@example.com",
    "employee1@example.com": "manager1@example.com",
    "employee2@example.com": "manager2@example.com",
    "employee3@example.com": "manager1@example.com",
    "employee4@example.com": "manager2@example.com",
}


def run_seed() -> int:
    """Insert any missing seed users, set every seed user's manager, and give every user
    current-year balance rows.

    Returns the number of users created. One commit, as the last step.
    """
    created = 0
    with SessionLocal() as db:
        for name, email, role, password in SEED_USERS:
            exists = db.scalar(select(User.id).where(User.email == normalize_email(email)))
            if exists is None:
                create_user(db, name=name, email=email, password=password, role=role)
                created += 1

        _assign_managers(db)

        year = current_year()
        for user_id in db.scalars(select(User.id)):
            ensure_balance_rows(db, user_id, year)
        db.commit()
    return created


def _assign_managers(db) -> None:
    """Second pass, once every seed user exists: a manager may be created after their report."""
    ids = {u.email: u.id for u in db.scalars(select(User))}
    for email, manager_email in MANAGERS.items():
        user = db.get(User, ids[normalize_email(email)])
        user.manager_id = ids[normalize_email(manager_email)] if manager_email else None


def main() -> None:
    created = run_seed()
    print(f"Seed complete: {created} created, {len(SEED_USERS) - created} already existed.")


if __name__ == "__main__":
    main()
