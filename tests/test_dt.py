"""Tests for bot/utils/dt.py — pure datetime helpers."""

from datetime import datetime

from bot.utils.dt import fmt_date, fmt_full, fmt_time, now_utc, to_user_tz


def test_now_utc_returns_naive_datetime() -> None:
    result = now_utc()
    assert isinstance(result, datetime)
    assert result.tzinfo is None


def test_to_user_tz_returns_aware_datetime() -> None:
    dt = datetime(2025, 6, 15, 10, 0, 0)
    result = to_user_tz(dt, "Europe/Moscow")
    assert result.tzinfo is not None


def test_to_user_tz_moscow_offset() -> None:
    # Moscow is UTC+3 in summer (no DST)
    dt = datetime(2025, 6, 15, 10, 0, 0)  # 10:00 UTC
    result = to_user_tz(dt, "Europe/Moscow")
    assert result.hour == 13  # 10 + 3


def test_to_user_tz_utc_returns_same_value() -> None:
    dt = datetime(2025, 6, 15, 12, 30, 0)
    result = to_user_tz(dt, "UTC")
    assert result.hour == 12
    assert result.minute == 30


def test_fmt_date_returns_correct_format() -> None:
    dt = datetime(2025, 6, 15, 0, 0, 0)
    result = fmt_date(dt, "UTC")
    assert result == "15.06"


def test_fmt_time_returns_correct_format() -> None:
    dt = datetime(2025, 6, 15, 14, 30, 0)
    result = fmt_time(dt, "UTC")
    assert result == "14:30"


def test_fmt_full_returns_correct_format() -> None:
    dt = datetime(2025, 6, 15, 14, 30, 0)
    result = fmt_full(dt, "UTC")
    assert result == "15.06.2025 14:30"


def test_fmt_date_with_timezone_converts() -> None:
    # 23:00 UTC on June 15 is 02:00 on June 16 in Moscow (UTC+3)
    dt = datetime(2025, 6, 15, 23, 0, 0)
    result = fmt_date(dt, "Europe/Moscow")
    assert result == "16.06"


def test_fmt_time_with_timezone_converts() -> None:
    # 10:00 UTC = 13:00 Moscow
    dt = datetime(2025, 6, 15, 10, 0, 0)
    result = fmt_time(dt, "Europe/Moscow")
    assert result == "13:00"


def test_fmt_full_with_timezone_converts() -> None:
    dt = datetime(2025, 6, 15, 10, 30, 0)
    result = fmt_full(dt, "Europe/Moscow")
    assert result == "15.06.2025 13:30"


def test_to_user_tz_new_york_offset() -> None:
    # New York is UTC-4 in summer (EDT)
    dt = datetime(2025, 6, 15, 15, 0, 0)  # 15:00 UTC
    result = to_user_tz(dt, "America/New_York")
    assert result.hour == 11  # 15 - 4
