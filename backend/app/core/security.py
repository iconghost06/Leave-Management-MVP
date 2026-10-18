from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings
from app.core.constants import JWT_ALG, JWT_EXPIRE_MINUTES

if settings.password_hash_fast:
    # Tests only (DESIGN §6.4): cheap parameters so the suite is not dominated by Argon2.
    _hasher = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=1024, parallelism=1),))
else:
    _hasher = PasswordHash((Argon2Hasher(),))

# Verified against when the email is unknown, so login takes about as long either way.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """False for a wrong password. With no stored hash it still does the work, then returns False."""
    if password_hash is None:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    return _hasher.verify(password, password_hash)


def create_access_token(user_id: int, role: str) -> str:
    """The role claim is informational only; get_current_user reads the role from the DB (§6.1)."""
    issued_at = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "role": role,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=JWT_ALG)


def decode_access_token(token: str) -> dict:
    """Raises jwt.InvalidTokenError (including ExpiredSignatureError) for any bad token."""
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[JWT_ALG],
        options={"require": ["sub", "exp", "iat"]},
    )
