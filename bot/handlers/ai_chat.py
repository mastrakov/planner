import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repo.chat_history import ChatHistoryRepo
from bot.db.repo.tasks import TaskRepo
from bot.services.intent.parser import IntentParser
from bot.services.intent.router import IntentRouter

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.")


@router.message()
async def handle_text(message: Message, user: User, session: AsyncSession, state: FSMContext) -> None:
    if not message.text:
        return

    logger.debug("handle_text: user_id=%d text=%r", user.id, message.text)

    from bot.services.analytics import AnalyticsService
    from bot.services.briefing import BriefingService
    from bot.services.calendar import CalendarService
    from bot.services.reminders import ReminderService
    from bot.services.tasks import TaskService

    history_repo = ChatHistoryRepo(session)
    await history_repo.add(user.id, "user", message.text)

    history = await history_repo.get_recent(user.id, limit=10)
    task_repo = TaskRepo(session)
    parser = IntentParser(task_repo)

    try:
        parsed = await parser.parse(message.text, user, history)
    except Exception:
        logger.exception("Intent parsing error for user %d", user.id)
        await message.answer("Произошла ошибка при обработке запроса.")
        return

    intent_router = IntentRouter(
        task_service=TaskService(session),
        calendar_service=CalendarService(session),
        reminder_service=ReminderService(session),
        briefing_service=BriefingService(session),
        analytics_service=AnalyticsService(session),
    )
    await intent_router.route(parsed, user, message, state=state, history=history)

    if parsed.intents:
        intent_type = parsed.intents[0].type
        await history_repo.add(user.id, "assistant", f"(выполнено: {intent_type})")
