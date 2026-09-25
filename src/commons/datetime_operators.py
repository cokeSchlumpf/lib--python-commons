from datetime import date, datetime, timedelta, timezone
from typing import Iterator


def date_range(start: date, end: date, *, inclusive: bool = True) -> Iterator[date]:
    """Creates a iterable range between two dates."""
    day = start
    stop = end if inclusive else end - timedelta(days=1)

    while day <= stop:
        yield day
        day += timedelta(days=1)


def utc_now() -> datetime:
    """Returns now datetime based on UTC time."""
    return datetime.now(timezone.utc)


def is_today(dt: datetime) -> bool:
    """Check if the given datetime is today (UTC)."""
    today = utc_now().date()
    return dt.date() == today


def is_past_week(dt: datetime) -> bool:
    """Check if the given datetime is within the past 7 days (UTC)."""
    now = utc_now()
    week_ago = now - timedelta(days=7)
    return week_ago <= dt <= now


def is_past_month(dt: datetime) -> bool:
    """Check if the given datetime is within the past 30 days (UTC)."""
    now = utc_now()
    month_ago = now - timedelta(days=30)
    return month_ago <= dt <= now


def is_past_three_months(dt: datetime) -> bool:
    """Check if the given datetime is within the past 90 days (UTC)."""
    now = utc_now()
    three_months_ago = now - timedelta(days=90)
    return three_months_ago <= dt <= now


def is_this_year(dt: datetime, year: int | None = None) -> bool:
    """Check if the given datetime is in the specified year. Defaults to current year (UTC).

    If year is negative, it is treated as a relative offset from the current year.
    For example: -1 means last year, -2 means two years ago.
    """
    current_year = utc_now().year
    if year is None:
        year = current_year
    elif year < 0:
        year = current_year + year
    return dt.year == year
