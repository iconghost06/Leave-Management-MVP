from datetime import date, timedelta


def count_working_days(start: date, end: date) -> int:
    """Mon-Fri dates in [start, end] inclusive (R4). Holidays are ignored."""
    span = (end - start).days + 1
    return sum(1 for i in range(span) if (start + timedelta(days=i)).weekday() < 5)
