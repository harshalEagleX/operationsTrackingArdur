"""The only sanctioned clock.

The business runs on IST. Every timestamp that lands in a report, a break
record or a work session comes from here — never from ``datetime.now()``
(which is naive and machine-local) and never from the browser (which is
attacker-controlled).

A ruff rule in pyproject.toml bans the alternatives.
"""

from __future__ import annotations

import datetime as _dt
import zoneinfo

from django.utils import timezone as _django_tz

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


def now_ist() -> _dt.datetime:
    """Timezone-aware 'now' in IST."""
    return _django_tz.now().astimezone(IST)


def today_ist() -> _dt.date:
    """Today's date in IST. Note this is NOT utcnow().date() — between
    18:30 and 00:00 UTC those two disagree, which is exactly the window
    the evening shift works in."""
    return now_ist().date()


def to_ist(value: _dt.datetime | None) -> _dt.datetime | None:
    """Normalise any datetime to IST. Naive values are assumed to be IST
    already, which matches how the legacy Flask app wrote them."""
    if value is None:
        return None
    if _django_tz.is_naive(value):
        return value.replace(tzinfo=IST)
    return value.astimezone(IST)


def start_of_day(day: _dt.date | None = None) -> _dt.datetime:
    """00:00:00 IST on the given day (default: today)."""
    day = day or today_ist()
    return _dt.datetime.combine(day, _dt.time.min, tzinfo=IST)


def end_of_day(day: _dt.date | None = None) -> _dt.datetime:
    """23:59:59.999999 IST on the given day (default: today)."""
    day = day or today_ist()
    return _dt.datetime.combine(day, _dt.time.max, tzinfo=IST)


def day_bounds(day: _dt.date | None = None) -> tuple[_dt.datetime, _dt.datetime]:
    """Half-open [start, next_start) bounds — use with ``__gte`` / ``__lt``.

    Preferred over end_of_day() for range filters: it has no microsecond
    boundary bug and lets the database use the index cleanly.
    """
    day = day or today_ist()
    start = start_of_day(day)
    return start, start + _dt.timedelta(days=1)


def elapsed_seconds(start: _dt.datetime, end: _dt.datetime | None = None) -> float:
    """Seconds between two instants, clamped at zero.

    Clock skew or a bad legacy row must never produce a negative duration
    that then poisons an average in a report.
    """
    end = end or now_ist()
    return max((to_ist(end) - to_ist(start)).total_seconds(), 0.0)
