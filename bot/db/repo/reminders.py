from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Reminder, RepeatType
from bot.utils.dt import now_utc


def _add_month(dt: datetime) -> datetime:
    """Advance datetime by exactly one calendar month."""
    month = dt.month + 1
    year = dt.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    import calendar
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


class ReminderRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: int,
        title: str,
        remind_at: datetime,
        repeat: str = RepeatType.NONE,
        event_id: int | None = None,
    ) -> Reminder:
        reminder = Reminder(
            user_id=user_id,
            title=title,
            remind_at=remind_at,
            repeat=repeat,
            event_id=event_id,
        )
        self._session.add(reminder)
        await self._session.flush()
        return reminder

    async def get_pending(self) -> list[Reminder]:
        result = await self._session.execute(
            select(Reminder)
            .where(Reminder.remind_at <= now_utc())
            .where(Reminder.is_sent.is_(False))
        )
        return list(result.scalars().all())

    async def mark_sent(self, reminder: Reminder) -> None:
        """Mark reminder as sent. If it repeats — advance remind_at past now."""
        if reminder.repeat == RepeatType.NONE:
            reminder.is_sent = True
        else:
            now = now_utc()
            next_at = reminder.remind_at
            if reminder.repeat == RepeatType.DAILY:
                while next_at <= now:
                    next_at += timedelta(days=1)
            elif reminder.repeat == RepeatType.WEEKLY:
                while next_at <= now:
                    next_at += timedelta(weeks=1)
            elif reminder.repeat == RepeatType.MONTHLY:
                while next_at <= now:
                    next_at = _add_month(next_at)
            else:
                reminder.is_sent = True
                await self._session.flush()
                return
            reminder.remind_at = next_at
        await self._session.flush()

    async def get_by_user(self, user_id: int) -> list[Reminder]:
        result = await self._session.execute(
            select(Reminder)
            .where(Reminder.user_id == user_id)
            .where(Reminder.is_sent.is_(False))
            .order_by(Reminder.remind_at)
        )
        return list(result.scalars().all())

    async def get_by_id(self, reminder_id: int) -> Reminder | None:
        return await self._session.get(Reminder, reminder_id)

    async def update(self, reminder: Reminder, **kwargs: object) -> Reminder:
        for key, value in kwargs.items():
            setattr(reminder, key, value)
        await self._session.flush()
        return reminder

    async def delete(self, reminder: Reminder) -> None:
        await self._session.delete(reminder)
        await self._session.flush()
