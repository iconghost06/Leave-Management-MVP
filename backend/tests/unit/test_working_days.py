"""U1-U4 (MUST): working-day count, Mon-Fri inclusive, holidays ignored (R4)."""
from datetime import date

from app.services.working_days import count_working_days

# June 2026: 1 Mon, 5 Fri, 6 Sat, 7 Sun, 8 Mon, 12 Fri.


def test_u1_monday_to_friday_is_five_days():
    assert count_working_days(date(2026, 6, 1), date(2026, 6, 5)) == 5


def test_u2_saturday_to_sunday_is_zero():
    assert count_working_days(date(2026, 6, 6), date(2026, 6, 7)) == 0


def test_u3_single_weekday_is_one_and_single_saturday_is_zero():
    assert count_working_days(date(2026, 6, 3), date(2026, 6, 3)) == 1
    assert count_working_days(date(2026, 6, 6), date(2026, 6, 6)) == 0


def test_u4_friday_to_monday_is_two_and_two_work_weeks_is_ten():
    assert count_working_days(date(2026, 6, 5), date(2026, 6, 8)) == 2
    assert count_working_days(date(2026, 6, 1), date(2026, 6, 12)) == 10


def test_range_starting_on_a_weekend_skips_the_weekend_days():
    # Sat 6 -> Tue 9: Mon + Tue only.
    assert count_working_days(date(2026, 6, 6), date(2026, 6, 9)) == 2


def test_range_ending_on_a_weekend_skips_the_weekend_days():
    # Fri 5 -> Sun 7: Fri only.
    assert count_working_days(date(2026, 6, 5), date(2026, 6, 7)) == 1
