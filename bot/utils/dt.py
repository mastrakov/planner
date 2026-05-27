"""Datetime utilities.

Convention: the database stores all timestamps as UTC naive (TIMESTAMP WITHOUT TIME ZONE).

Helpers here cover the three common operations:
  - now_utc()         → current UTC naive datetime (replaces datetime.utcnow())
  - to_user_tz()      → convert UTC naive → aware datetime in user's timezone
  - fmt / fmt_date    → format a UTC naive DB value for display in user's timezone
  - parse_user_date() → parse a free-text date/time string via AI into UTC naive datetime
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from typing import TYPE_CHECKING

import pytz

if TYPE_CHECKING:
    pass

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


async def parse_user_date(
    text: str,
    tz_name: str,
    anthropic_client: object | None = None,
    openai_client: object | None = None,
    use_gpt4o: bool = False,
) -> datetime | None:
    """Parse a free-text date/time string into a UTC naive datetime.

    Uses a lightweight AI prompt (no full intent schema, just date extraction).
    Returns None if parsing fails or the text doesn't contain a recognisable date.
    """
    tz = pytz.timezone(tz_name)
    now_local = datetime.now(tz=UTC).astimezone(tz)
    dt_str = now_local.strftime("%d.%m.%Y %H:%M %z")

    system = (
        f"Сейчас: {dt_str} (часовой пояс: {tz_name}). "
        "Извлеки дату и время из текста пользователя и верни ТОЛЬКО JSON: "
        '{"datetime": "ISO 8601 с offset, например 2026-05-31T15:00:00+03:00"} '
        "или {\"datetime\": null} если дата не распознана. "
        "Никаких пояснений, только JSON."
    )

    try:
        if use_gpt4o and openai_client is not None:
            from openai import AsyncOpenAI  # type: ignore[import-untyped]
            client: AsyncOpenAI = openai_client  # type: ignore[assignment]
            response = await client.chat.completions.create(
                model="gpt-4o",
                max_tokens=64,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
        else:
            import anthropic as _anthropic  # type: ignore[import-untyped]
            if anthropic_client is None:
                from bot.config import settings
                anthropic_client = _anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            client_a: _anthropic.AsyncAnthropic = anthropic_client  # type: ignore[assignment]
            resp = await client_a.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=64,
                system=system,
                messages=[{"role": "user", "content": text}],
            )
            raw = resp.content[0].text  # type: ignore[union-attr]

        data = json.loads(raw)
        iso = data.get("datetime")
        if not iso:
            return None

        # Parse ISO string (has tzinfo) → convert to UTC naive
        parsed = datetime.fromisoformat(iso)
        if parsed.tzinfo is not None:
            return parsed.astimezone(pytz.utc).replace(tzinfo=None)
        # Naive fallback: assume user tz
        localized = tz.localize(parsed, is_dst=None)
        return localized.astimezone(pytz.utc).replace(tzinfo=None)
    except Exception:
        return None
