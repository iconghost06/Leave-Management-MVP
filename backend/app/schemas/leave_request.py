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


class LeaveRequestOut(BaseModel):
    """`decided_by_name` is added in step 3.1, when approve and reject can set `decided_by`."""

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
    decided_at: datetime | None
    decision_comment: str | None
    created_at: datetime
