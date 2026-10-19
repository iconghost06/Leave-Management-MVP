from pydantic import BaseModel


class BalanceOut(BaseModel):
    leave_type: str
    entitlement: int
    used: int
    pending: int
    available: int


class BalancesOut(BaseModel):
    year: int
    balances: list[BalanceOut]
