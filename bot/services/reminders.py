import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repo.reminders import ReminderRepo
from bot.services.intent.models import CreateReminderIntent

logger = logging.getLogger(__name__)


class ReminderService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ReminderRepo(session)

    async def create(self, user: User, intent: CreateReminderIntent) -> str:
        reminder = await self._repo.create(
            user_id=user.id,
            title=intent.title,
            remind_at=intent.remind_at,
            repeat=intent.repeat,
        )
        await self._session.commit()
        time_str = reminder.remind_at.strftime("%d.%m.%Y %H:%M")
        return f"Напоминание создано: «{reminder.title}» в {time_str}"

    async def check_and_send(self, bot: Bot, session: AsyncSession) -> None:
        repo = ReminderRepo(session)
        pending = await repo.get_pending()
        for reminder in pending:
            try:
                await bot.send_message(
                    reminder.user_id,
                    f"Напоминание: {reminder.title}",
                )
                await repo.mark_sent(reminder)
            except Exception:
                logger.exception("Failed to send reminder %d to user %d", reminder.id, reminder.user_id)
        await session.commit()
