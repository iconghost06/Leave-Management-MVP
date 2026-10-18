from fastapi import APIRouter, Depends

from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.error import ErrorOut
from app.schemas.user import UserOut

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserOut, responses={401: {"model": ErrorOut}})
def me(user: User = Depends(get_current_user)) -> User:
    return user
