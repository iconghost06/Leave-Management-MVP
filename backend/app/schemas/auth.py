from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import JWT_EXPIRE_MINUTES
from app.schemas.user import UserOut


class SignupIn(BaseModel):
    """No `role` field, and extra="ignore": a role sent by the client is dropped before
    the service sees it (A3). `join_code` is optional here so a missing code reaches the
    service and gets the same SIGNUP_FAILED body as a wrong one (A2)."""

    model_config = ConfigDict(extra="ignore")

    join_code: str | None = None
    name: str = Field(min_length=1, max_length=100)
    # ASCII only, so Python's lower() and the users.email CHECK (PostgreSQL lower()) always agree.
    email: str = Field(max_length=254, pattern=r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = JWT_EXPIRE_MINUTES * 60
    user: UserOut
