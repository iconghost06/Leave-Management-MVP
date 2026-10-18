from datetime import date

from app.core.errors import AppError
from app.core.time import current_year
from app.services.working_days import count_working_days


def validate_dates(start: date, end: date) -> tuple[int, int]:
    """Return (days, year) or raise the first failing rule (R5-R8, R11).

    Order is SPEC section 6: INVALID_DATE_RANGE, NO_WORKING_DAYS,
    SPANS_MULTIPLE_YEARS, NOT_CURRENT_YEAR. "Today" comes from core.time only.
    """
    if end < start:
        raise AppError(422, "INVALID_DATE_RANGE", "End date must not be before start date")

    days = count_working_days(start, end)
    if days == 0:
        raise AppError(422, "NO_WORKING_DAYS", "The selected range has no working days")

    if start.year != end.year:
        raise AppError(
            422,
            "SPANS_MULTIPLE_YEARS",
            "Leave cannot span two calendar years; submit one request per year",
        )

    if start.year != current_year():
        raise AppError(422, "NOT_CURRENT_YEAR", "Leave must be within the current calendar year")

    return days, start.year
