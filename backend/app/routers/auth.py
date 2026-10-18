from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.user import User
from app.routers.deps import get_db
from app.schemas.auth import LoginIn, SignupIn, TokenOut
from app.schemas.error import ErrorOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


async def join_code_gate(request: Request) -> None:
    """Check the join code from the raw JSON before FastAPI validates the body.

    FastAPI would otherwise answer a bad body (a short password, say) with 422 before the
    service ran, so a caller without the code would get a different error than SIGNUP_FAILED.
    As a dependency this runs first, so a wrong or missing code always gets the generic 400.
    """
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    auth_service.check_join_code(payload.get("join_code") if isinstance(payload, dict) else None)


def _token_response(user: User) -> TokenOut:
    return TokenOut(access_token=create_access_token(user.id, user.role), user=user)


@router.post(
    "/signup",
    status_code=201,
    response_model=TokenOut,
    dependencies=[Depends(join_code_gate)],
    responses={400: {"model": ErrorOut}, 409: {"model": ErrorOut}},
)
def signup(data: SignupIn, db: Session = Depends(get_db)) -> TokenOut:
    return _token_response(auth_service.signup(db, data))


@router.post("/login", response_model=TokenOut, responses={401: {"model": ErrorOut}})
def login(data: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    return _token_response(auth_service.authenticate(db, data.email, data.password))
