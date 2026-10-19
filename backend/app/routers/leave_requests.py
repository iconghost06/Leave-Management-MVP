from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.leave_request import LeaveRequest
from app.models.user import User
from app.routers.deps import get_current_user, get_db, require_manager
from app.schemas.error import ErrorOut
from app.schemas.leave_request import DecisionIn, LeaveRequestIn, LeaveRequestOut, RequestStatus
from app.services import approval_service, leave_request_service

router = APIRouter(prefix="/leave-requests", tags=["leave-requests"])

_ERRORS = {401: {"model": ErrorOut}}


@router.post(
    "",
    status_code=201,
    response_model=LeaveRequestOut,
    responses={**_ERRORS, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def submit(
    data: LeaveRequestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> LeaveRequest:
    return leave_request_service.submit_request(db, user, data)


@router.get("", response_model=list[LeaveRequestOut], responses=_ERRORS)
def list_own(
    status: RequestStatus | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LeaveRequest]:
    return leave_request_service.list_own_requests(db, user, status)


@router.get(
    "/{request_id}",
    response_model=LeaveRequestOut,
    responses={**_ERRORS, 403: {"model": ErrorOut}, 404: {"model": ErrorOut}},
)
def detail(
    request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> LeaveRequest:
    return leave_request_service.get_request_for_viewer(db, user, request_id)


@router.post(
    "/{request_id}/cancel",
    response_model=LeaveRequestOut,
    responses={
        **_ERRORS,
        403: {"model": ErrorOut},
        404: {"model": ErrorOut},
        409: {"model": ErrorOut},
    },
)
def cancel(
    request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> LeaveRequest:
    return leave_request_service.cancel_request(db, user, request_id)


_DECISION_ERRORS = {
    **_ERRORS,
    403: {"model": ErrorOut},
    404: {"model": ErrorOut},
    409: {"model": ErrorOut},
}


@router.post(
    "/{request_id}/approve", response_model=LeaveRequestOut, responses=_DECISION_ERRORS
)
def approve(
    request_id: int,
    data: DecisionIn | None = None,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> LeaveRequest:
    return approval_service.approve_request(
        db, manager, request_id, data.comment if data else None
    )


@router.post(
    "/{request_id}/reject",
    response_model=LeaveRequestOut,
    responses={**_DECISION_ERRORS, 422: {"model": ErrorOut}},
)
def reject(
    request_id: int,
    data: DecisionIn | None = None,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> LeaveRequest:
    return approval_service.reject_request(
        db, manager, request_id, data.comment if data else None
    )
