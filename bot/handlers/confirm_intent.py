"""FSM handler for confirming low-confidence or destructive AI intents."""

import json
import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User

logger = logging.getLogger(__name__)

router = Router()

# Positive answers
_YES = {"да", "yes", "конечно", "ок", "ok", "подтверждаю", "верно", "точно", "угу", "ага", "давай"}
_NO = {"нет", "no", "отмена", "cancel", "отменить", "стоп", "stop", "не надо", "неверно"}


class ConfirmIntentStates(StatesGroup):
    waiting_for_confirmation = State()


async def ask_confirmation(
    message: Message,
    state: FSMContext,
    summary: str,
    parsed_json: str,
    is_destructive: bool = False,
) -> None:
    """Store pending intent in FSM state and ask user for confirmation."""
    await state.set_state(ConfirmIntentStates.waiting_for_confirmation)
    await state.update_data(pending_intent_json=parsed_json)

    prefix = "Это действие нельзя отменить" if is_destructive else "Я понял вас так"
    await message.answer(
        f"{prefix}:\n{summary}\n\n"
        "Всё верно? Напишите <b>да</b> для подтверждения или <b>нет</b> для отмены.",
        parse_mode="HTML",
    )


@router.message(ConfirmIntentStates.waiting_for_confirmation)
async def handle_confirmation(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    text = (message.text or "").strip().lower()

    if text in _NO or text.startswith("отмен"):
        await state.clear()
        await message.answer("Действие отменено.")
        return

    if text not in _YES:
        await message.answer(
            "Пожалуйста, ответьте <b>да</b> для подтверждения или <b>нет</b> для отмены.",
            parse_mode="HTML",
        )
        return

    # User confirmed — execute the pending intent
    data = await state.get_data()
    await state.clear()

    pending_json: str | None = data.get("pending_intent_json")
    if not pending_json:
        await message.answer("Не удалось найти отложенное действие. Попробуйте снова.")
        return

    try:
        parsed_data = json.loads(pending_json)
    except (json.JSONDecodeError, TypeError):
        logger.exception("Failed to deserialize pending intent")
        await message.answer("Ошибка при восстановлении действия. Попробуйте снова.")
        return

    # Re-parse and execute
    from bot.services.analytics import AnalyticsService
    from bot.services.briefing import BriefingService
    from bot.services.calendar import CalendarService
    from bot.services.intent.models import ParsedResponse
    from bot.services.intent.router import IntentRouter
    from bot.services.reminders import ReminderService
    from bot.services.tasks import TaskService

    try:
        parsed = ParsedResponse.model_validate(parsed_data)
        # NOTE: we call execute_confirmed which bypasses confidence/destructive checks entirely.
        # Do NOT mutate parsed.confidence here — ParsedResponse may have validate_assignment
        # enabled in future and mutation would raise ValidationError.

        intent_router = IntentRouter(
            task_service=TaskService(session),
            calendar_service=CalendarService(session),
            reminder_service=ReminderService(session),
            briefing_service=BriefingService(session),
            analytics_service=AnalyticsService(session),
        )
        await intent_router.execute_confirmed(parsed, user, message)
    except Exception:
        logger.exception("Error executing confirmed intent for user %d", user.id)
        await message.answer("Произошла ошибка при выполнении. Попробуйте ещё раз.")
