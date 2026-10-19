from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.time import current_year
from app.models.user import User
from app.routers.deps import get_current_user, get_db
from app.schemas.balance import BalancesOut
from app.schemas.error import ErrorOut
from app.services import balance_service

router = APIRouter(tags=["balances"])


@router.get("/balances", response_model=BalancesOut, responses={401: {"model": ErrorOut}})
def balances(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> BalancesOut:
    year = current_year()
    return BalancesOut(year=year, balances=balance_service.get_balance_summary(db, user.id, year))
