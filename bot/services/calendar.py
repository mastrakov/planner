from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repo.calendar import CalendarRepo
from bot.db.repo.integrations import IntegrationRepo
from bot.db.repo.reminders import ReminderRepo
from bot.services.integrations.base import CalendarEventDTO
from bot.services.integrations.registry import registry
from bot.services.intent.models import CreateEventIntent, ListEventsIntent
from bot.utils.dt import fmt_full, fmt_time, now_utc


class CalendarService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CalendarRepo(session)
        self._reminder_repo = ReminderRepo(session)
        self._integration_repo = IntegrationRepo(session)

    async def create_event(self, user: User, intent: CreateEventIntent) -> str:
        external_id: str | None = None

        active_integration = await self._integration_repo.get_active_calendar_integration(user.id)
        if active_integration and registry.has_calendar(active_integration.provider_name):
            provider = registry.get_calendar(active_integration.provider_name)
            dto = CalendarEventDTO(
                title=intent.title,
                starts_at=intent.starts_at,
                ends_at=intent.ends_at,
            )
            external_id = await provider.create_event(user.id, dto)

        event = await self._repo.create(
            user_id=user.id,
            title=intent.title,
            starts_at=intent.starts_at,
            ends_at=intent.ends_at,
            external_id=external_id,
        )

        # Create a Reminder row for each requested offset
        for minutes in intent.reminder_minutes:
            remind_at = intent.starts_at - timedelta(minutes=minutes)
            await self._reminder_repo.create(
                user_id=user.id,
                title=f"Напоминание: {intent.title}",
                remind_at=remind_at,
                event_id=event.id,
            )

        time_str = fmt_full(event.starts_at, user.timezone)
        sync_note = " (синхронизировано с Google Calendar)" if external_id else ""
        reminder_note = ""
        if intent.reminder_minutes:
            offsets = ", ".join(
                f"за {m} мин." if m < 60 else f"за {m // 60} ч." + (f" {m % 60} мин." if m % 60 else "")
                for m in sorted(intent.reminder_minutes)
            )
            reminder_note = f"\nНапоминания: {offsets}"
        return f"Событие создано: «{event.title}» — {time_str}{sync_note}{reminder_note}"

    async def get_events(self, user: User, intent: ListEventsIntent) -> str:
        now = now_utc()
        date_from = intent.date_from or now
        date_to = intent.date_to or (now + timedelta(days=7))

        events = await self._repo.get_for_date_range(user.id, date_from, date_to)
        if not events:
            return "Событий не найдено."

        lines = ["<b>События:</b>"]
        for ev in events:
            time_str = fmt_full(ev.starts_at, user.timezone)
            lines.append(f"• {time_str} — {ev.title}")
        return "\n".join(lines)

    async def delete_event(self, event_id: int, user: User) -> str:
        event = await self._repo.get_by_id(event_id)
        if not event or event.user_id != user.id:
            return "Событие не найдено."

        if event.external_id:
            active_integration = await self._integration_repo.get_active_calendar_integration(user.id)
            if active_integration and registry.has_calendar(active_integration.provider_name):
                provider = registry.get_calendar(active_integration.provider_name)
                try:
                    await provider.delete_event(user.id, event.external_id)
                except Exception:
                    pass

        await self._repo.delete(event)
        return f"Событие «{event.title}» удалено."
