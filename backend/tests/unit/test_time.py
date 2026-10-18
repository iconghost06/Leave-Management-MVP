"""U11 (SHOULD): company "today" is the Asia/Kolkata date, not the server's UTC date (R24)."""
from datetime import date, datetime, timezone

import pytest

from app.core import time as company_time


def freeze_utc(monkeypatch, instant: datetime) -> None:
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz)

    monkeypatch.setattr(company_time, "datetime", FrozenDatetime)


def test_u11_company_today_is_next_day_in_ist_at_1900_utc(monkeypatch):
    # 19:00Z on 31 Dec is 00:30 IST on 1 Jan.
    freeze_utc(monkeypatch, datetime(2026, 12, 31, 19, 0, tzinfo=timezone.utc))
    assert company_time.company_today() == date(2027, 1, 1)
    assert company_time.current_year() == 2027


def test_company_today_is_same_day_in_ist_before_1830_utc(monkeypatch):
    freeze_utc(monkeypatch, datetime(2026, 12, 31, 18, 0, tzinfo=timezone.utc))
    assert company_time.company_today() == date(2026, 12, 31)
