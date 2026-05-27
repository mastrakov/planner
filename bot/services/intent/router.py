from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Coroutine

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config import settings
from bot.db.models import ChatHistory, User
from bot.services.intent.models import (
    DESTRUCTIVE_INTENT_TYPES,
    AIChatIntent,
    CompleteTaskIntent,
    CreateEventIntent,
    CreateReminderIntent,
    CreateTaskIntent,
    DeleteReminderIntent,
    DeleteTaskIntent,
    GetAnalyticsIntent,
    GetBriefingIntent,
    ListEventsIntent,
    ListRemindersIntent,
    ListTasksIntent,
    ParsedIntent,
    ParsedResponse,
    UpdateReminderIntent,
    UpdateTaskIntent,
)

if TYPE_CHECKING:
    import anthropic
    from openai import AsyncOpenAI

    from bot.services.analytics import AnalyticsService
    from bot.services.briefing import BriefingService
    from bot.services.calendar import CalendarService
    from bot.services.reminders import ReminderService
    from bot.services.tasks import TaskService

from bot.services.ai.clients import AIClients

logger = logging.getLogger(__name__)


class IntentRouter:
    def __init__(
        self,
        task_service: TaskService,
        calendar_service: CalendarService,
        reminder_service: ReminderService,
        briefing_service: BriefingService,
        analytics_service: AnalyticsService,
        anthropic_client: anthropic.AsyncAnthropic | None = None,
        openai_client: AsyncOpenAI | None = None,
        ai_clients: AIClients | None = None,
    ) -> None:
        self._tasks = task_service
        self._calendar = calendar_service
        self._reminders = reminder_service
        self._briefing = briefing_service
        self._analytics = analytics_service
        if ai_clients is None:
            ai_clients = AIClients(anthropic_client=anthropic_client, openai_client=openai_client)
        self._ai_clients = ai_clients

        # Dispatch table: intent type → (execute coroutine, summarize callable)
        self._handlers: dict[
            type,
            tuple[
                Callable[..., Coroutine],  # execute
                Callable[[ParsedIntent], str],  # summarize
            ],
        ] = {
            CreateTaskIntent: (
                self._exec_create_task,
                lambda i: f"• Создать задачу: «{i.title}»",
            ),
            ListTasksIntent: (
                self._exec_list_tasks,
                lambda i: "• Показать задачи",
            ),
            CompleteTaskIntent: (
                self._exec_complete_task,
                lambda i: f"• Завершить задачу: «{i.task_title}»",
            ),
            DeleteTaskIntent: (
                self._exec_delete_task,
                lambda i: f"• Удалить задачу: «{i.task_title}»",
            ),
            UpdateTaskIntent: (
                self._exec_update_task,
                lambda i: f"• Изменить задачу: «{i.task_title}»",
            ),
            CreateEventIntent: (
                self._exec_create_event,
                lambda i: f"• Создать событие: «{i.title}» в {i.starts_at}",
            ),
            ListEventsIntent: (
                self._exec_list_events,
                lambda i: "• Показать события",
            ),
            CreateReminderIntent: (
                self._exec_create_reminder,
                lambda i: f"• Напоминание: «{i.title}» в {i.remind_at}",
            ),
            ListRemindersIntent: (
                self._exec_list_reminders,
                lambda i: "• Показать напоминания",
            ),
            DeleteReminderIntent: (
                self._exec_delete_reminder,
                lambda i: f"• Удалить напоминание: «{i.reminder_title}»",
            ),
            UpdateReminderIntent: (
                self._exec_update_reminder,
                lambda i: f"• Изменить напоминание: «{i.reminder_title}»",
            ),
            GetBriefingIntent: (
                self._exec_briefing,
                lambda i: "• Показать брифинг",
            ),
            GetAnalyticsIntent: (
                self._exec_analytics,
                lambda i: "• Показать аналитику",
            ),
            AIChatIntent: (
                self._exec_ai_chat,
                lambda i: f"• Диалог: «{i.message[:60]}»",
            ),
        }

    async def route(
        self,
        parsed: ParsedResponse,
        user: User,
        message: Message,
        state: FSMContext | None = None,
        history: list[ChatHistory] | None = None,
    ) -> str | None:
        """Route parsed intents to services and return the bot's reply text (for chat history).

        Returns the text of the bot's reply if it is a free-form AI chat response,
        otherwise returns None (structured actions don't need verbatim history).
        """
        logger.debug(
            "Routing: user_id=%d intents=%s confidence=%.2f",
            user.id, [i.type for i in parsed.intents], parsed.confidence,
        )

        if parsed.clarification_needed:
            logger.debug("Routing: clarification needed → %r", parsed.clarification_needed)
            await message.answer(parsed.clarification_needed)
            return None

        has_destructive = any(
            intent.type in DESTRUCTIVE_INTENT_TYPES for intent in parsed.intents
        )

        if parsed.confidence < 0.8 or has_destructive:
            logger.debug(
                "Routing: low confidence (%.2f) or destructive=%s → asking confirmation",
                parsed.confidence, has_destructive,
            )
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
            return None

        reply_lines: list[str] = []
        for intent in parsed.intents:
            reply = await self._dispatch(intent, user, message, history=history)
            if reply is not None:
                reply_lines.append(reply)

        if reply_lines:
            await message.answer("\n".join(reply_lines), parse_mode="HTML")

        return "\n".join(reply_lines) if reply_lines else None

    async def execute_confirmed(
        self,
        parsed: ParsedResponse,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> None:
        """Execute intents that were already confirmed by the user."""
        reply_lines: list[str] = []
        for intent in parsed.intents:
            reply = await self._dispatch(intent, user, message, history=history)
            if reply is not None:
                reply_lines.append(reply)
        if reply_lines:
            await message.answer("\n".join(reply_lines), parse_mode="HTML")

    async def _dispatch(
        self,
        intent: ParsedIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> str | None:
        """Dispatch a single intent. Returns AI reply text for ai_chat intents, None otherwise."""
        logger.debug("Dispatching intent=%s for user_id=%d", intent.type, user.id)
        try:
            handler_pair = self._handlers.get(type(intent))
            if handler_pair is None:
                logger.warning("No handler for intent type %s", type(intent).__name__)
                return None
            execute, _ = handler_pair
            return await execute(intent, user, message, history)
        except Exception:
            logger.exception("Error dispatching intent %s for user %d", intent.type, user.id)
            await message.answer("Произошла ошибка при выполнении команды. Попробуйте ещё раз.")
        return None

    def _summarize(self, parsed: ParsedResponse) -> str:
        lines: list[str] = []
        for intent in parsed.intents:
            handler_pair = self._handlers.get(type(intent))
            if handler_pair:
                _, summarize = handler_pair
                lines.append(summarize(intent))
            else:
                lines.append(f"• {intent.type}")
        return "\n".join(lines)

    # ---------------------------------------------------------------------------
    # _exec_* handlers — one per intent type
    # ---------------------------------------------------------------------------

    async def _exec_create_task(
        self,
        intent: CreateTaskIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> str:
        """Handle create_task with list auto-classification and deadline button.

        Returns a human-readable confirmation string so it can be stored in chat
        history — this prevents the AI from re-creating the same task when it sees
        the next message (the previous opaque "(выполнено: create_task)" label gave
        the model no information about what was actually created).
        """
        from bot.keyboards.tasks import select_list_keyboard, task_created_keyboard
        from bot.services.tasks import TaskCreateResult

        result = await self._tasks.create_task_smart(user=user, intent=intent)

        # No lists — error string returned
        if isinstance(result, str):
            await message.answer(result)
            return result

        task = result.task
        target_list = result.target_list

        if result.low_confidence:
            # Ask user which list to use — task was tentatively placed in the first candidate
            lists = await self._tasks.get_lists(user.id)
            # Put the suggested list first
            if intent.suggested_list_id is not None:
                lists = sorted(lists, key=lambda l: 0 if l.id == intent.suggested_list_id else 1)
            text = f"В какой список добавить «{task.title}»?"
            kb = select_list_keyboard(task.id, lists)
            await message.answer(text, reply_markup=kb)
        else:
            # High confidence or single list — confirm to user
            text = f"Добавил в {target_list.emoji} {target_list.name}: «{task.title}»"
            kb = task_created_keyboard(task.id, has_due_date=task.due_date is not None)
            # Only attach keyboard if there's at least one button (no deadline → show deadline button)
            has_buttons = not task.due_date
            await message.answer(text, reply_markup=kb if has_buttons else None)
        return text

    async def _exec_list_tasks(
        self,
        intent: ListTasksIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> None:
        result = await self._tasks.get_tasks_for_user(user=user, intent=intent)
        await message.answer(result, parse_mode="HTML")

    async def _exec_complete_task(
        self,
        intent: CompleteTaskIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> str:
        return await self._tasks.complete_task(user=user, intent=intent)

    async def _exec_delete_task(
        self,
        intent: DeleteTaskIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> str:
        return await self._tasks.delete_task(user=user, intent=intent)

    async def _exec_update_task(
        self,
        intent: UpdateTaskIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> str:
        return await self._tasks.update_task(user=user, intent=intent)

    async def _exec_create_event(
        self,
        intent: CreateEventIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> str:
        return await self._calendar.create_event(user=user, intent=intent)

    async def _exec_list_events(
        self,
        intent: ListEventsIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> None:
        result = await self._calendar.get_events(user=user, intent=intent)
        await message.answer(result, parse_mode="HTML")

    async def _exec_create_reminder(
        self,
        intent: CreateReminderIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> str:
        return await self._reminders.create(user=user, intent=intent)

    async def _exec_list_reminders(
        self,
        intent: ListRemindersIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> None:
        result = await self._reminders.list_reminders(user=user, intent=intent)
        await message.answer(result, parse_mode="HTML")

    async def _exec_delete_reminder(
        self,
        intent: DeleteReminderIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> str:
        return await self._reminders.delete_reminder(user=user, intent=intent)

    async def _exec_update_reminder(
        self,
        intent: UpdateReminderIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> str:
        return await self._reminders.update_reminder(user=user, intent=intent)

    async def _exec_briefing(
        self,
        intent: GetBriefingIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> None:
        briefing = await self._dispatch_briefing(intent, user)
        await message.answer(briefing.text, parse_mode="HTML", reply_markup=briefing.combined_keyboard)

    async def _exec_analytics(
        self,
        intent: GetAnalyticsIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> None:
        result = await self._analytics.get_stats(user=user, period=intent.period)
        await message.answer(result, parse_mode="HTML")

    async def _exec_ai_chat(
        self,
        intent: AIChatIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> str:
        return await self._handle_ai_chat(intent, user, message, history=history)

    async def _dispatch_briefing(
        self,
        intent: GetBriefingIntent,
        user: User,
    ):
        """Route get_briefing to the right BriefingService method."""
        import pytz
        from datetime import datetime as _dt

        tz = pytz.timezone(user.timezone)
        now_local = _dt.now(tz).replace(tzinfo=None)

        if intent.scope == "week":
            if intent.target_date:
                # target_date is UTC naive — convert to local
                local_dt = pytz.utc.localize(intent.target_date).astimezone(tz).replace(tzinfo=None)
            else:
                local_dt = now_local
            # Find Monday of the target week
            monday = local_dt - __import__("datetime").timedelta(days=local_dt.weekday())
            return await self._briefing.build_for_week(user=user, week_start_local=monday)
        else:
            if intent.target_date:
                local_dt = pytz.utc.localize(intent.target_date).astimezone(tz).replace(tzinfo=None)
            else:
                local_dt = now_local
            # For today specifically use build_morning (has overdue section)
            today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            target_day = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            if target_day == today_local:
                return await self._briefing.build_morning(user=user)
            return await self._briefing.build_for_date(user=user, target_local=target_day)

    async def _handle_ai_chat(
        self,
        intent: AIChatIntent,
        user: User,
        message: Message,
        history: list[ChatHistory] | None = None,
    ) -> str:
        from bot.config import settings
        from bot.db.models import AIModel

        # Build conversation history for context.
        # history is fetched BEFORE the current message is added to DB (see handle_text/handle_voice),
        # so ALL entries are prior context — do NOT slice off the last one.
        history_messages: list[dict[str, str]] = []
        if history:
            for h in history:
                history_messages.append({"role": h.role, "content": h.content})

        if user.ai_model == AIModel.GPT4O:
            messages = history_messages + [{"role": "user", "content": intent.message}]
            response = await self._ai_clients.get_openai().chat.completions.create(
                model=settings.openai_model,
                max_tokens=1024,
                messages=messages,  # type: ignore[arg-type]
            )
            text = response.choices[0].message.content or "Нет ответа."
        else:
            messages = history_messages + [{"role": "user", "content": intent.message}]
            resp = await self._ai_clients.get_anthropic().messages.create(
                model=settings.claude_model,
                max_tokens=1024,
                messages=messages,  # type: ignore[arg-type]
            )
            text = resp.content[0].text  # type: ignore[union-attr]

        await message.answer(text)
        return text
