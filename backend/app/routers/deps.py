from collections.abc import Iterator

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import UNAUTHENTICATED, AppError
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.user import User

# auto_error=False: a missing header is reported by us, as {code, message}, not FastAPI's default body.
bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    """One Session per request. Never commits: services commit once, as their last step.

    On any exception (including AppError) the open transaction is rolled back and the
    exception re-raised. close() always runs and also ends an uncommitted read-only txn.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _unauthenticated() -> AppError:
    return AppError(401, UNAUTHENTICATED, "Authentication required.")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """JWT -> users row. Any bad, expired or orphaned token is a 401.

    The role comes from the loaded row, never from the token's role claim (§6.1), so a
    forged or stale claim cannot grant or keep manager rights.
    """
    if credentials is None:
        raise _unauthenticated()
    try:
        claims = decode_access_token(credentials.credentials)
        user_id = int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError):
        raise _unauthenticated() from None
    user = db.get(User, user_id)
    if user is None:
        raise _unauthenticated()
    return user


def require_manager(user: User = Depends(get_current_user)) -> User:
    if user.role != "MANAGER":
        raise AppError(403, "FORBIDDEN", "Manager access required.")
    return user
