from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.db.models import User
from bot.services.intent.models import (
    AIChatIntent,
    CompleteTaskIntent,
    CreateEventIntent,
    CreateReminderIntent,
    CreateTaskIntent,
    DeleteTaskIntent,
    DESTRUCTIVE_INTENT_TYPES,
    GetAnalyticsIntent,
    GetBriefingIntent,
    ListEventsIntent,
    ListTasksIntent,
    ParsedIntent,
    ParsedResponse,
    UpdateTaskIntent,
)

if TYPE_CHECKING:
    from bot.services.analytics import AnalyticsService
    from bot.services.briefing import BriefingService
    from bot.services.calendar import CalendarService
    from bot.services.reminders import ReminderService
    from bot.services.tasks import TaskService

logger = logging.getLogger(__name__)


class IntentRouter:
    def __init__(
        self,
        task_service: TaskService,
        calendar_service: CalendarService,
        reminder_service: ReminderService,
        briefing_service: BriefingService,
        analytics_service: AnalyticsService,
    ) -> None:
        self._tasks = task_service
        self._calendar = calendar_service
        self._reminders = reminder_service
        self._briefing = briefing_service
        self._analytics = analytics_service

    async def route(
        self,
        parsed: ParsedResponse,
        user: User,
        message: Message,
        state: "FSMContext | None" = None,
    ) -> None:
        if parsed.clarification_needed:
            await message.answer(parsed.clarification_needed)
            return

        has_destructive = any(
            intent.type in DESTRUCTIVE_INTENT_TYPES for intent in parsed.intents
        )

        if parsed.confidence < 0.8 or has_destructive:
            if state is not None:
                from bot.handlers.confirm_intent import ask_confirmation

                summary = self._summarize(parsed)
                await ask_confirmation(
                    message,
                    state,
                    summary,
                    parsed_json=parsed.model_dump_json(),
                    is_destructive=has_destructive,
                )
            else:
                # Fallback when no FSM context available
                summary = self._summarize(parsed)
                prefix = "Это действие нельзя отменить" if has_destructive else "Я понял вас так"
                await message.answer(
                    f"{prefix}:\n{summary}\n\nПодтвердите, написав «да»."
                )
            return

        for intent in parsed.intents:
            await self._dispatch(intent, user, message)

    async def execute_confirmed(
        self,
        parsed: ParsedResponse,
        user: User,
        message: Message,
    ) -> None:
        """Execute intents that were already confirmed by the user."""
        for intent in parsed.intents:
            await self._dispatch(intent, user, message)

    async def _dispatch(self, intent: ParsedIntent, user: User, message: Message) -> None:
        try:
            if isinstance(intent, CreateTaskIntent):
                result = await self._tasks.create_task(user=user, intent=intent)
                await message.answer(result)

            elif isinstance(intent, ListTasksIntent):
                result = await self._tasks.get_tasks_for_user(user=user, intent=intent)
                await message.answer(result, parse_mode="HTML")

            elif isinstance(intent, CompleteTaskIntent):
                result = await self._tasks.complete_task(user=user, intent=intent)
                await message.answer(result)

            elif isinstance(intent, DeleteTaskIntent):
                result = await self._tasks.delete_task(user=user, intent=intent)
                await message.answer(result)

            elif isinstance(intent, UpdateTaskIntent):
                result = await self._tasks.update_task(user=user, intent=intent)
                await message.answer(result)

            elif isinstance(intent, CreateEventIntent):
                result = await self._calendar.create_event(user=user, intent=intent)
                await message.answer(result)

            elif isinstance(intent, ListEventsIntent):
                result = await self._calendar.get_events(user=user, intent=intent)
                await message.answer(result, parse_mode="HTML")

            elif isinstance(intent, CreateReminderIntent):
                result = await self._reminders.create(user=user, intent=intent)
                await message.answer(result)

            elif isinstance(intent, GetBriefingIntent):
                result = await self._briefing.build_morning_briefing(user=user)
                await message.answer(result, parse_mode="HTML")

            elif isinstance(intent, GetAnalyticsIntent):
                result = await self._analytics.get_weekly_stats(user=user)
                await message.answer(result, parse_mode="HTML")

            elif isinstance(intent, AIChatIntent):
                await self._handle_ai_chat(intent, user, message)

        except Exception:
            logger.exception("Error dispatching intent %s for user %d", intent.type, user.id)
            await message.answer("Произошла ошибка при выполнении команды. Попробуйте ещё раз.")

    async def _handle_ai_chat(self, intent: AIChatIntent, user: User, message: Message) -> None:
        import anthropic as _anthropic
        from openai import AsyncOpenAI

        from bot.config import settings
        from bot.db.models import AIModel

        if user.ai_model == AIModel.GPT4O:
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            response = await client.chat.completions.create(
                model="gpt-4o",
                max_tokens=1024,
                messages=[{"role": "user", "content": intent.message}],
            )
            text = response.choices[0].message.content or "Нет ответа."
        else:
            client_a = _anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            resp = await client_a.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": intent.message}],
            )
            text = resp.content[0].text  # type: ignore[union-attr]

        await message.answer(text)

    def _summarize(self, parsed: ParsedResponse) -> str:
        lines: list[str] = []
        for intent in parsed.intents:
            if isinstance(intent, CreateTaskIntent):
                lines.append(f"• Создать задачу: «{intent.title}»")
            elif isinstance(intent, CompleteTaskIntent):
                lines.append(f"• Завершить задачу: «{intent.task_title}»")
            elif isinstance(intent, DeleteTaskIntent):
                lines.append(f"• Удалить задачу: «{intent.task_title}»")
            elif isinstance(intent, CreateEventIntent):
                lines.append(f"• Создать событие: «{intent.title}» в {intent.starts_at}")
            elif isinstance(intent, CreateReminderIntent):
                lines.append(f"• Напоминание: «{intent.title}» в {intent.remind_at}")
            elif isinstance(intent, ListTasksIntent):
                lines.append("• Показать задачи")
            elif isinstance(intent, ListEventsIntent):
                lines.append("• Показать события")
            elif isinstance(intent, GetBriefingIntent):
                lines.append("• Показать брифинг")
            elif isinstance(intent, GetAnalyticsIntent):
                lines.append("• Показать аналитику")
            elif isinstance(intent, AIChatIntent):
                lines.append(f"• Диалог: «{intent.message[:60]}»")
            else:
                lines.append(f"• {intent.type}")
        return "\n".join(lines)
