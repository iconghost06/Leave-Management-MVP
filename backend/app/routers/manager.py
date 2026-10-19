from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.user import User
from app.routers.deps import get_db, require_manager
from app.schemas.error import ErrorOut
from app.schemas.leave_request import ManagerRequestOut, RequestStatus
from app.services import approval_service

router = APIRouter(prefix="/manager", tags=["manager"])


@router.get(
    "/requests",
    response_model=list[ManagerRequestOut],
    responses={401: {"model": ErrorOut}, 403: {"model": ErrorOut}},
)
def list_requests(
    status: RequestStatus | None = None,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> list[ManagerRequestOut]:
    return approval_service.list_manager_requests(db, manager, status)
