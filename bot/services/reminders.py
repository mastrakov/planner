import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repo.reminders import ReminderRepo
from bot.services.intent.models import (
    CreateReminderIntent,
    DeleteReminderIntent,
    ListRemindersIntent,
    UpdateReminderIntent,
)
from bot.utils.dt import fmt_full

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
        time_str = fmt_full(reminder.remind_at, user.timezone)
        return f"Напоминание создано: «{reminder.title}» в {time_str}"

    async def list_reminders(self, user: User, intent: ListRemindersIntent) -> str:  # noqa: ARG002
        reminders = await self._repo.get_by_user(user.id)
        if not reminders:
            return "У вас нет активных напоминаний."
        lines = ["<b>Напоминания:</b>"]
        for r in reminders:
            time_str = fmt_full(r.remind_at, user.timezone)
            repeat_str = f" 🔁 {r.repeat}" if r.repeat != "none" else ""
            event_str = " 📅" if r.event_id else ""
            lines.append(f"• {time_str} — {r.title}{repeat_str}{event_str}")
        return "\n".join(lines)

    def _find_reminders(self, reminders: list, query: str) -> list:
        q = query.lower()
        return [r for r in reminders if q in r.title.lower()]

    async def delete_reminder(self, user: User, intent: DeleteReminderIntent) -> str:
        reminders = await self._repo.get_by_user(user.id)
        matches = self._find_reminders(reminders, intent.reminder_title)
        if not matches:
            return f"Напоминание «{intent.reminder_title}» не найдено."
        if len(matches) > 1:
            titles = "\n".join(f"  • {r.title}" for r in matches)
            return f"Найдено несколько напоминаний по запросу «{intent.reminder_title}»:\n{titles}\n\nУточните название."
        found = matches[0]
        await self._repo.delete(found)
        return f"Напоминание «{found.title}» удалено."

    async def update_reminder(self, user: User, intent: UpdateReminderIntent) -> str:
        reminders = await self._repo.get_by_user(user.id)
        matches = self._find_reminders(reminders, intent.reminder_title)
        if not matches:
            return f"Напоминание «{intent.reminder_title}» не найдено."
        if len(matches) > 1:
            titles = "\n".join(f"  • {r.title}" for r in matches)
            return f"Найдено несколько напоминаний по запросу «{intent.reminder_title}»:\n{titles}\n\nУточните название."
        found = matches[0]
        kwargs: dict[str, object] = {}
        if intent.new_remind_at:
            kwargs["remind_at"] = intent.new_remind_at
        if intent.new_title:
            kwargs["title"] = intent.new_title
        if kwargs:
            await self._repo.update(found, **kwargs)
        time_str = fmt_full(found.remind_at, user.timezone)
        return f"Напоминание обновлено: «{found.title}» в {time_str}"

    async def check_and_send(self, bot: Bot) -> None:
        pending = await self._repo.get_pending()
        for reminder in pending:
            try:
                await bot.send_message(
                    reminder.user_id,
                    f"🔔 Напоминание: {reminder.title}",
                )
                await self._repo.mark_sent(reminder)
            except Exception:
                logger.exception("Failed to send reminder %d to user %d", reminder.id, reminder.user_id)
        await self._session.commit()
