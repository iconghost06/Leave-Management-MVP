from datetime import date, datetime
from typing import Literal

from pydantic import AliasPath, BaseModel, ConfigDict, Field

LeaveType = Literal["EARNED", "SICK"]
RequestStatus = Literal["PENDING", "APPROVED", "REJECTED", "CANCELLED"]


class LeaveRequestIn(BaseModel):
    """Shape and length only. The date rules live in the service so each gets its own
    code, in SPEC section 6 order (§1.3)."""

    model_config = ConfigDict(extra="ignore")

    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=500)


class DecisionIn(BaseModel):
    """Body of approve (comment optional) and reject (comment required).

    The comment is optional here for both: whether it is required is a rule that depends on the
    request being PENDING (Q5), so reject checks it in the service and returns COMMENT_REQUIRED.
    """

    model_config = ConfigDict(extra="ignore")

    comment: str | None = Field(default=None, max_length=500)


class LeaveRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    requester_name: str = Field(validation_alias=AliasPath("requester", "name"))
    requester_employee_code: str = Field(validation_alias=AliasPath("requester", "employee_code"))
    leave_type: str
    start_date: date
    end_date: date
    days: int
    reason: str | None
    status: str
    decided_by: int | None
    decided_by_name: str | None = Field(default=None, validation_alias=AliasPath("decider", "name"))
    decided_at: datetime | None
    decision_comment: str | None
    created_at: datetime


class ManagerRequestOut(LeaveRequestOut):
    """A request as a manager sees it. `employee_available` is the requester's `available` for
    the request's type and year (R3, Q6); set on PENDING rows, null otherwise (DESIGN §5)."""

    employee_available: int | None = None
