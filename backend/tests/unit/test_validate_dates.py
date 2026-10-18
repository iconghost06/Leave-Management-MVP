"""U5-U10: date validation in SPEC section 6 order (R5-R8, R11).

"Today" is frozen by patching the single source, app.core.time.company_today.
"""
from datetime import date

import pytest

from app.core.errors import AppError
from app.services.leave_request_service import validate_dates

FROZEN_TODAY = date(2026, 6, 15)  # Monday


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr("app.core.time.company_today", lambda: FROZEN_TODAY)


def assert_rejected(start: date, end: date, code: str) -> None:
    with pytest.raises(AppError) as exc:
        validate_dates(start, end)
    assert exc.value.status == 422
    assert exc.value.code == code


def test_u5_end_before_start_is_invalid_date_range():
    assert_rejected(date(2026, 6, 10), date(2026, 6, 9), "INVALID_DATE_RANGE")


def test_u6_weekend_only_range_has_no_working_days():
    assert_rejected(date(2026, 6, 20), date(2026, 6, 21), "NO_WORKING_DAYS")


def test_u7_range_across_new_year_spans_multiple_years():
    assert_rejected(date(2026, 12, 31), date(2027, 1, 1), "SPANS_MULTIPLE_YEARS")


def test_u8_last_year_and_next_year_are_not_current_year():
    assert_rejected(date(2025, 6, 2), date(2025, 6, 3), "NOT_CURRENT_YEAR")
    assert_rejected(date(2027, 6, 1), date(2027, 6, 2), "NOT_CURRENT_YEAR")


def test_u9_first_failing_rule_wins():
    # end < start AND wrong year -> INVALID_DATE_RANGE.
    assert_rejected(date(2025, 6, 10), date(2025, 6, 9), "INVALID_DATE_RANGE")
    # Sat 31 Dec -> Sun 1 Jan: no working days, spans years, wrong year -> NO_WORKING_DAYS.
    assert_rejected(date(2022, 12, 31), date(2023, 1, 1), "NO_WORKING_DAYS")
    # Spans years AND starts outside the current year -> SPANS_MULTIPLE_YEARS.
    assert_rejected(date(2025, 12, 31), date(2026, 1, 1), "SPANS_MULTIPLE_YEARS")


def test_valid_range_returns_days_and_year():
    assert validate_dates(date(2026, 6, 16), date(2026, 6, 19)) == (4, 2026)


def test_u10_backdated_date_earlier_this_year_is_accepted():
    assert validate_dates(date(2026, 1, 5), date(2026, 1, 6)) == (2, 2026)
