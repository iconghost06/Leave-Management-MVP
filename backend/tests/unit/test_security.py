"""U12 (SHOULD): password hashing and JWT helpers."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.constants import JWT_ALG
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_u12_password_hash_round_trip():
    hashed = hash_password("Employee@123")
    assert hashed != "Employee@123"
    assert verify_password("Employee@123", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_u12_token_lifetime_is_3600_seconds():
    claims = decode_access_token(create_access_token(user_id=7, role="EMPLOYEE"))
    assert claims["sub"] == "7"
    assert claims["role"] == "EMPLOYEE"
    assert claims["exp"] - claims["iat"] == 3600


def test_u12_expired_token_is_rejected():
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    expired = jwt.encode(
        {"sub": "7", "role": "EMPLOYEE", "iat": past, "exp": past + timedelta(minutes=60)},
        settings.secret_key,
        algorithm=JWT_ALG,
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(expired)


def test_u12_token_signed_with_another_key_is_rejected():
    forged = jwt.encode(
        {"sub": "7", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "some-other-secret-key-0123456789abcdef",
        algorithm=JWT_ALG,
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(forged)
