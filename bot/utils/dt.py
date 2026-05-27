"""Datetime utilities.

Convention: the database stores all timestamps as UTC naive (TIMESTAMP WITHOUT TIME ZONE).

Helpers here cover the three common operations:
  - now_utc()         → current UTC naive datetime (replaces datetime.utcnow())
  - to_user_tz()      → convert UTC naive → aware datetime in user's timezone
  - fmt / fmt_date    → format a UTC naive DB value for display in user's timezone
"""

from datetime import datetime, timezone

import pytz

# -------------------------------------------------------------------
# UTC "now"
# -------------------------------------------------------------------

def now_utc() -> datetime:
    """Return current UTC time as a naive datetime (for DB comparisons)."""
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


# -------------------------------------------------------------------
# Conversion helpers
# -------------------------------------------------------------------

def to_user_tz(dt: datetime, tz_name: str) -> datetime:
    """Convert a UTC naive datetime from the DB to the user's local timezone (aware)."""
    tz = pytz.timezone(tz_name)
    return pytz.utc.localize(dt).astimezone(tz)


# -------------------------------------------------------------------
# Formatting helpers
# -------------------------------------------------------------------

def fmt(dt: datetime, tz_name: str, fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Format a UTC naive DB datetime as a localised string for the user."""
    return to_user_tz(dt, tz_name).strftime(fmt)


def fmt_date(dt: datetime, tz_name: str) -> str:
    """Short date only: DD.MM"""
    return fmt(dt, tz_name, "%d.%m")


def fmt_time(dt: datetime, tz_name: str) -> str:
    """Time only: HH:MM"""
    return fmt(dt, tz_name, "%H:%M")


def fmt_full(dt: datetime, tz_name: str) -> str:
    """Full datetime: DD.MM.YYYY HH:MM"""
    return fmt(dt, tz_name, "%d.%m.%Y %H:%M")
