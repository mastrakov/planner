import logging

from aiogram import Bot, F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repo.chat_history import ChatHistoryRepo
from bot.db.repo.tasks import TaskRepo
from bot.services.intent.parser import IntentParser
from bot.services.intent.router import IntentRouter
from bot.services.voice import VoiceService

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.voice)
async def handle_voice(message: Message, user: User, session: AsyncSession, bot: Bot) -> None:
    logger.info("Received voice message from user %d", user.id)

    from bot.services.analytics import AnalyticsService
    from bot.services.briefing import BriefingService
    from bot.services.calendar import CalendarService
    from bot.services.reminders import ReminderService
    from bot.services.tasks import TaskService

    voice_service = VoiceService(bot)
    try:
        text = await voice_service.voice_to_text(message.voice)  # type: ignore[arg-type]
    except Exception as exc:
        logger.exception(
            "Voice transcription failed for user %d: %s: %s",
            user.id, type(exc).__name__, exc,
        )
        await message.answer("Не удалось распознать голосовое сообщение. Попробуйте ещё раз.")
        return

    await message.answer(f"Распознано: «{text}»")

    history_repo = ChatHistoryRepo(session)
    await history_repo.add(user.id, "user", f"[голосовое] {text}")

    history = await history_repo.get_recent(user.id, limit=10)
    task_repo = TaskRepo(session)
    parser = IntentParser(task_repo)
    parsed = await parser.parse(text, user, history)

    intent_router = IntentRouter(
        task_service=TaskService(session),
        calendar_service=CalendarService(session),
        reminder_service=ReminderService(session),
        briefing_service=BriefingService(session),
        analytics_service=AnalyticsService(session),
    )
    await intent_router.route(parsed, user, message)
    await history_repo.add(user.id, "assistant", f"(обработано намерение: {parsed.intents[0].type if parsed.intents else 'unknown'})")
