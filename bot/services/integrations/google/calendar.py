import asyncio
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any, TypeVar

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build  # type: ignore[import-untyped]

from bot.services.integrations.base import CalendarEventDTO, CalendarProvider

_T = TypeVar("_T")


async def _run_sync(fn: Callable[[], _T]) -> _T:
    """Run a blocking callable in the default thread-pool executor."""
    return await asyncio.get_running_loop().run_in_executor(None, fn)


def _build_service(credentials_dict: dict[str, object]) -> Any:
    creds = Credentials(
        token=str(credentials_dict.get("token", "")),
        refresh_token=str(credentials_dict.get("refresh_token", "")),
        token_uri=str(credentials_dict.get("token_uri", "https://oauth2.googleapis.com/token")),
        client_id=str(credentials_dict.get("client_id", "")),
        client_secret=str(credentials_dict.get("client_secret", "")),
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _to_rfc3339(dt: datetime) -> str:
    return dt.isoformat() + "Z" if dt.tzinfo is None else dt.isoformat()


class GoogleCalendarProvider(CalendarProvider):
    """Calendar provider for Google Calendar.

    Credentials are fetched lazily via ``get_creds_fn``, a callable that
    accepts a ``user_id`` and returns a credentials dict.  This keeps the
    provider session-agnostic and easy to wire up in different contexts.
    """

    def __init__(self, get_creds_fn: Callable[[int], Awaitable[dict[str, object]]]) -> None:
        self._get_creds_fn = get_creds_fn

    async def _get_creds(self, user_id: int) -> dict[str, object]:
        return await self._get_creds_fn(user_id)

    async def create_event(self, user_id: int, event: CalendarEventDTO) -> str:
        creds = await self._get_creds(user_id)
        service = _build_service(creds)

        body: dict[str, object] = {
            "summary": event.title,
            "start": {"dateTime": _to_rfc3339(event.starts_at)},
            "end": {
                "dateTime": _to_rfc3339(event.ends_at or event.starts_at)
            },
        }
        if event.reminder_minutes is not None:
            body["reminders"] = {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": event.reminder_minutes}],
            }

        result = await _run_sync(
            lambda: service.events().insert(calendarId="primary", body=body).execute()
        )
        return str(result.get("id", ""))

    async def list_events(
        self,
        user_id: int,
        date_from: date,
        date_to: date,
    ) -> list[CalendarEventDTO]:
        creds = await self._get_creds(user_id)
        service = _build_service(creds)

        time_min = datetime(date_from.year, date_from.month, date_from.day).isoformat() + "Z"
        time_max = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59).isoformat() + "Z"

        result = await _run_sync(
            lambda: service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events: list[CalendarEventDTO] = []
        for item in result.get("items", []):
            start_raw = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date", "")
            end_raw = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date", "")
            starts_at = datetime.fromisoformat(start_raw.replace("Z", "+00:00")) if start_raw else datetime.utcnow()
            ends_at = datetime.fromisoformat(end_raw.replace("Z", "+00:00")) if end_raw else None
            events.append(
                CalendarEventDTO(
                    title=item.get("summary", ""),
                    starts_at=starts_at,
                    ends_at=ends_at,
                    external_id=item.get("id"),
                )
            )
        return events

    async def delete_event(self, user_id: int, event_id: str) -> None:
        creds = await self._get_creds(user_id)
        service = _build_service(creds)
        await _run_sync(
            lambda: service.events().delete(calendarId="primary", eventId=event_id).execute()
        )

    async def update_event(self, user_id: int, event_id: str, event: CalendarEventDTO) -> None:
        creds = await self._get_creds(user_id)
        service = _build_service(creds)

        body: dict[str, object] = {
            "summary": event.title,
            "start": {"dateTime": _to_rfc3339(event.starts_at)},
            "end": {
                "dateTime": _to_rfc3339(event.ends_at or event.starts_at)
            },
        }
        await _run_sync(
            lambda: service.events().update(calendarId="primary", eventId=event_id, body=body).execute()
        )
