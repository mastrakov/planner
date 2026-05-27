from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Reminder, RepeatType


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
