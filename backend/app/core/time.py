from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.constants import COMPANY_TZ


def company_today() -> date:
    """The only source of "today" (R24). Tests monkeypatch this one function."""
    return datetime.now(ZoneInfo(COMPANY_TZ)).date()


def current_year() -> int:
    return company_today().year
