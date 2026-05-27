from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Reminder, RepeatType


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
    ) -> Reminder:
        reminder = Reminder(user_id=user_id, title=title, remind_at=remind_at, repeat=repeat)
        self._session.add(reminder)
        await self._session.flush()
        return reminder

    async def get_pending(self) -> list[Reminder]:
        now = datetime.utcnow()
        result = await self._session.execute(
            select(Reminder)
            .where(Reminder.remind_at <= now)
            .where(Reminder.is_sent.is_(False))
        )
        return list(result.scalars().all())

    async def mark_sent(self, reminder: Reminder) -> None:
        """Mark reminder as sent. If it repeats — schedule next occurrence instead."""
        if reminder.repeat == RepeatType.NONE:
            reminder.is_sent = True
        elif reminder.repeat == RepeatType.DAILY:
            reminder.remind_at = reminder.remind_at + timedelta(days=1)
        elif reminder.repeat == RepeatType.WEEKLY:
            reminder.remind_at = reminder.remind_at + timedelta(weeks=1)
        elif reminder.repeat == RepeatType.MONTHLY:
            reminder.remind_at = _add_month(reminder.remind_at)
        else:
            reminder.is_sent = True
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

    async def delete(self, reminder: Reminder) -> None:
        await self._session.delete(reminder)
        await self._session.flush()
