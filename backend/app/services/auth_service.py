import hmac

from sqlalchemy import Text, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.core.time import current_year
from app.models.user import User
from app.schemas.auth import SignupIn
from app.services.balance_service import ensure_balance_rows

UNIQUE_VIOLATION = "23505"

# One message for a wrong and a missing code, so the two responses are byte-identical (A2).
SIGNUP_FAILED_MESSAGE = "Signup failed. Check your details and the company join code."


def normalize_email(email: str) -> str:
    return email.strip().lower()


def check_join_code(join_code: object) -> None:
    """Compare against SIGNUP_CODE in constant time. Wrong, missing or non-string -> 400."""
    supplied = join_code.encode() if isinstance(join_code, str) else b""
    expected = settings.signup_code.encode()
    if not hmac.compare_digest(supplied, expected):
        raise AppError(400, "SIGNUP_FAILED", SIGNUP_FAILED_MESSAGE)


def create_user(db: Session, *, name: str, email: str, password: str, role: str) -> User:
    """Insert a user with the next EMP-#### code. Flushes, does not commit.

    Shared by signup (always EMPLOYEE) and the seed (the only way to get a MANAGER).
    """
    user = User(
        name=name,
        email=normalize_email(email),
        password_hash=hash_password(password),
        role=role,
        employee_code=func.concat(
            "EMP-", func.lpad(cast(func.nextval("employee_code_seq"), Text), 4, "0")
        ),
    )
    db.add(user)
    db.flush()
    db.refresh(user)  # employee_code was a SQL expression; load the generated value
    return user


def signup(db: Session, data: SignupIn) -> User:
    check_join_code(data.join_code)  # first, before any DB access (R21)

    email = normalize_email(data.email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise _email_taken()

    try:
        user = create_user(
            db, name=data.name.strip(), email=email, password=data.password, role="EMPLOYEE"
        )
    except IntegrityError as exc:
        # Two signups for one email raced past the SELECT; the unique index decided.
        if getattr(exc.orig, "sqlstate", None) == UNIQUE_VIOLATION:
            raise _email_taken() from None
        raise

    ensure_balance_rows(db, user.id, current_year())
    db.commit()
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    # Verify even when the user is missing, and give one error for both cases.
    password_ok = verify_password(password, user.password_hash if user else None)
    if user is None or not password_ok:
        raise AppError(401, "INVALID_CREDENTIALS", "Incorrect email or password.")
    return user


def _email_taken() -> AppError:
    return AppError(409, "EMAIL_ALREADY_REGISTERED", "An account with this email already exists.")
