from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import CalendarEvent


class CalendarRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: int,
        title: str,
        starts_at: datetime,
        ends_at: datetime | None = None,
        external_id: str | None = None,
        repeat: str = "none",
    ) -> CalendarEvent:
        event = CalendarEvent(
            user_id=user_id,
            title=title,
            starts_at=starts_at,
            ends_at=ends_at,
            external_id=external_id,
            repeat=repeat,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def get_by_user(self, user_id: int) -> list[CalendarEvent]:
        result = await self._session.execute(
            select(CalendarEvent)
            .where(CalendarEvent.user_id == user_id)
            .order_by(CalendarEvent.starts_at)
        )
        return list(result.scalars().all())

    async def get_for_date_range(
        self,
        user_id: int,
        date_from: datetime,
        date_to: datetime,
    ) -> list[CalendarEvent]:
        result = await self._session.execute(
            select(CalendarEvent)
            .where(CalendarEvent.user_id == user_id)
            .where(CalendarEvent.starts_at >= date_from)
            .where(CalendarEvent.starts_at <= date_to)
            .order_by(CalendarEvent.starts_at)
        )
        return list(result.scalars().all())

    async def get_by_id(self, event_id: int) -> CalendarEvent | None:
        result = await self._session.execute(
            select(CalendarEvent)
            .where(CalendarEvent.id == event_id)
            .options(selectinload(CalendarEvent.reminders))
        )
        return result.scalar_one_or_none()

    async def delete(self, event: CalendarEvent) -> None:
        await self._session.delete(event)
        await self._session.flush()

    async def update(self, event: CalendarEvent, **kwargs: object) -> CalendarEvent:
        for key, value in kwargs.items():
            setattr(event, key, value)
        await self._session.flush()
        return event
