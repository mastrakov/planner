from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AIModel, User
from bot.db.repo.calendar import CalendarRepo
from bot.db.repo.reminders import ReminderRepo
from bot.db.repo.tasks import TaskRepo
from bot.utils.dt import fmt_date, fmt_time, now_utc

if TYPE_CHECKING:
    import anthropic
    from openai import AsyncOpenAI


@dataclass
class BriefingResult:
    """Return type for BriefingService build methods.

    text: HTML-formatted message body.
    keyboards: Per-entity keyboards keyed by a label describing the entity
               (used when the handler sends multiple messages or attaches a single combined keyboard).
    combined_keyboard: A single merged keyboard appended to the main message (used in briefing).
    """

    text: str
    combined_keyboard: InlineKeyboardMarkup | None = None
    # Extra per-event / per-task keyboards for individual messages (optional, currently unused)
    extra_keyboards: dict[str, InlineKeyboardMarkup] = field(default_factory=dict)


class BriefingService:
    def __init__(
        self,
        session: AsyncSession,
        anthropic_client: anthropic.AsyncAnthropic | None = None,
        openai_client: AsyncOpenAI | None = None,
    ) -> None:
        self._session = session
        self._task_repo = TaskRepo(session)
        self._calendar_repo = CalendarRepo(session)
        self._reminder_repo = ReminderRepo(session)
        self._anthropic_client = anthropic_client
        self._openai_client = openai_client

    def _get_anthropic_client(self) -> anthropic.AsyncAnthropic:
        if self._anthropic_client is None:
            import anthropic as _anthropic

            from bot.config import settings
            self._anthropic_client = _anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._anthropic_client

    def _get_openai_client(self) -> AsyncOpenAI:
        if self._openai_client is None:
            from openai import AsyncOpenAI

            from bot.config import settings
            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    # ------------------------------------------------------------------
    # Morning briefing
    # ------------------------------------------------------------------

    async def build_morning(self, user: User) -> BriefingResult:
        """Build the morning briefing.

        Sections:
        1. Overdue tasks (with ✅ + 🗑 buttons)
        2. Today's calendar events (with 🔔 button if no reminder)
        3. Today's tasks sorted by priority DESC (with ✅ button)
        4. High-priority tasks with no deadline (up to 5)
        5. Reminder suggestions (inline buttons collected into combined_keyboard)
        6. AI comment
        """
        import pytz as _pytz
        now = now_utc()
        _tz = _pytz.timezone(user.timezone)
        _now_local = datetime.now(_tz)
        _day_start_local = _now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        _day_end_local = _day_start_local + timedelta(days=1)
        day_start_utc = _day_start_local.astimezone(_pytz.utc).replace(tzinfo=None)
        today_end = _day_end_local.astimezone(_pytz.utc).replace(tzinfo=None)

        overdue_tasks = await self._task_repo.get_overdue(user.id, tz_name=user.timezone)
        today_tasks = await self._task_repo.get_today(user.id, tz_name=user.timezone)
        high_priority_no_dl = await self._task_repo.get_high_priority_no_deadline(user.id, limit=5)
        today_events = await self._calendar_repo.get_for_date_range(user.id, day_start_utc, today_end)

        # Check which events already have reminders
        events_without_reminder: list = []
        for ev in today_events:
            has_rem = await self._reminder_repo.has_reminder_for_event(ev.id)
            if not has_rem:
                events_without_reminder.append(ev)

        # Check which today-tasks already have reminders
        tasks_today_without_reminder: list = []
        for t in today_tasks:
            has_rem = await self._reminder_repo.has_reminder_for_task_today(t.id)
            if not has_rem:
                tasks_today_without_reminder.append(t)

        # --- Build text ---
        lines: list[str] = []

        # Header
        weekday_ru = _weekday_ru(now)
        date_str = fmt_date(now, user.timezone)
        lines.append(f"<b>☀️ Доброе утро! {weekday_ru}, {date_str}</b>")

        # 1. Overdue tasks
        if overdue_tasks:
            lines.append(f"\n<b>⚠️ Просрочено ({len(overdue_tasks)}):</b>")
            for t in overdue_tasks:
                due_str = fmt_date(t.due_date, user.timezone) if t.due_date else ""
                prio = {"high": "high", "medium": "medium", "low": "low"}.get(t.priority, "")
                days_overdue = (now - t.due_date).days if t.due_date else 0
                overdue_label = f"просрочено на {days_overdue} д." if days_overdue > 0 else "просрочено"
                lines.append(f"• [{prio}] {t.title} — {overdue_label}")

        # 2. Events today
        if today_events:
            lines.append("\n<b>📅 Сегодня в календаре:</b>")
            for ev in today_events:
                time_str = fmt_time(ev.starts_at, user.timezone)
                reminder_hint = "  [🔔 нет напоминания]" if ev in events_without_reminder else ""
                lines.append(f"• {time_str} — {ev.title}{reminder_hint}")

        # 3. Today's tasks
        if today_tasks:
            lines.append(f"\n<b>✅ Задачи на сегодня ({len(today_tasks)}):</b>")
            for t in today_tasks:
                prio = {"high": "high", "medium": "medium", "low": "low"}.get(t.priority, "")
                lines.append(f"• [{prio}] {t.title}")

        # 4. High-priority tasks without deadline
        if high_priority_no_dl:
            lines.append("\n<b>🔥 Важные задачи (без дедлайна):</b>")
            for t in high_priority_no_dl:
                lines.append(f"• [high] {t.title}")

        # 5. AI comment
        context = (
            f"Просроченных задач: {len(overdue_tasks)}. "
            f"Событий сегодня: {len(today_events)}. "
            f"Задач на сегодня: {len(today_tasks)}. "
            f"Важных без дедлайна: {len(high_priority_no_dl)}."
        )
        ai_comment = await self._get_ai_comment(context, user)
        if ai_comment:
            lines.append(f"\n🤖 {ai_comment}")

        text = "\n".join(lines)

        # --- Build combined keyboard for reminder suggestions ---
        kb_builder = InlineKeyboardBuilder()
        has_buttons = False

        for ev in events_without_reminder:
            kb_builder.button(
                text=f"🔔 {fmt_time(ev.starts_at, user.timezone)} {ev.title[:20]} — за 15 мин",
                callback_data=f"remind_event:15:{ev.id}",
            )
            has_buttons = True

        for t in tasks_today_without_reminder:
            kb_builder.button(
                text=f"🔔 {t.title[:25]} — в 09:00",
                callback_data=f"remind_task_morning:{t.id}",
            )
            has_buttons = True

        kb_builder.adjust(1)
        combined_kb = kb_builder.as_markup() if has_buttons else None

        return BriefingResult(text=text, combined_keyboard=combined_kb)

    # ------------------------------------------------------------------
    # Weekly plan
    # ------------------------------------------------------------------

    async def build_weekly(self, user: User) -> BriefingResult:
        """Build the weekly plan (sent on Monday mornings).

        Sections:
        1. Tasks with due_date in [today, +6d], grouped by list
        2. High-priority tasks with no deadline (up to 5)
        3. Events for the week, grouped by day
        4. Reminder buttons per event + bulk "remind all" button
        5. AI comment
        """
        import pytz as _pytz
        now = now_utc()
        _tz = _pytz.timezone(user.timezone)
        _now_local = datetime.now(_tz)
        _day_start_local = _now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start = _day_start_local.astimezone(_pytz.utc).replace(tzinfo=None)
        week_end = day_start + timedelta(days=7)

        week_tasks = await self._task_repo.get_week_range(user.id, tz_name=user.timezone)
        high_priority_no_dl = await self._task_repo.get_high_priority_no_deadline(user.id, limit=5)
        week_events = await self._calendar_repo.get_for_date_range(user.id, day_start, week_end)

        # Check which events already have reminders
        events_without_reminder: list = []
        for ev in week_events:
            has_rem = await self._reminder_repo.has_reminder_for_event(ev.id)
            if not has_rem:
                events_without_reminder.append(ev)

        lines: list[str] = []

        # Header
        lines.append(
            f"<b>📆 Неделя {fmt_date(now, user.timezone)} – {fmt_date(week_end - timedelta(days=1), user.timezone)}</b>"
        )

        # 1. Tasks grouped by list
        if week_tasks:
            lines.append("\n<b>✅ Задачи на неделю:</b>")
            grouped: dict[str, list[str]] = {}
            for t in week_tasks:
                list_label = f"{t.task_list.emoji} {t.task_list.name}"
                prio = {"high": "high", "medium": "medium", "low": "low"}.get(t.priority, "")
                due_str = _weekday_short_ru(t.due_date) if t.due_date else ""
                grouped.setdefault(list_label, []).append(f"  • {due_str} [{prio}] {t.title}")
            for list_label, items in grouped.items():
                lines.append(f"{list_label}:")
                lines.extend(items)

        # 2. High-priority tasks without deadline
        if high_priority_no_dl:
            lines.append("\n<b>🔥 Важные (без дедлайна):</b>")
            for t in high_priority_no_dl:
                lines.append(f"  • [high] {t.title}")

        # 3. Events grouped by day
        if week_events:
            lines.append("\n<b>📅 События:</b>")
            days: dict[str, list] = {}
            for ev in week_events:
                day_key = fmt_date(ev.starts_at, user.timezone)
                day_label = f"{_weekday_ru(ev.starts_at)}, {day_key}"
                days.setdefault(day_label, []).append(ev)
            for day_label, evs in days.items():
                lines.append(f"{day_label}:")
                for ev in evs:
                    time_str = fmt_time(ev.starts_at, user.timezone)
                    no_rem = " [нет напом.]" if ev in events_without_reminder else ""
                    lines.append(f"  • {time_str} {ev.title}{no_rem}")

        # 4. AI comment
        context = (
            f"Задач с дедлайном на неделе: {len(week_tasks)}. "
            f"Важных без дедлайна: {len(high_priority_no_dl)}. "
            f"Встреч на неделе: {len(week_events)}."
        )
        ai_comment = await self._get_ai_comment(context, user, sentences=3)
        if ai_comment:
            lines.append(f"\n🤖 {ai_comment}")

        text = "\n".join(lines)

        # --- Build combined keyboard ---
        kb_builder = InlineKeyboardBuilder()
        has_buttons = False

        for ev in events_without_reminder:
            time_str = fmt_time(ev.starts_at, user.timezone)
            kb_builder.button(
                text=f"🔔 {time_str} {ev.title[:20]} — за 1ч",
                callback_data=f"remind_event:60:{ev.id}",
            )
            kb_builder.button(
                text=f"🔔 {ev.title[:20]} — за день",
                callback_data=f"remind_event:1440:{ev.id}",
            )
            has_buttons = True

        if events_without_reminder:
            kb_builder.button(
                text="📌 Поставить напоминания для всех событий",
                callback_data="remind_all_week_events",
            )
            has_buttons = True

        kb_builder.adjust(2)
        combined_kb = kb_builder.as_markup() if has_buttons else None

        return BriefingResult(text=text, combined_keyboard=combined_kb)

    # ------------------------------------------------------------------
    # Legacy wrappers (keep for backward compat with existing callers)
    # ------------------------------------------------------------------

    async def build_morning_briefing(self, user: User) -> str:
        """Legacy string-only wrapper around build_morning."""
        result = await self.build_morning(user)
        return result.text

    async def build_weekly_plan(self, user: User) -> str:
        """Legacy string-only wrapper around build_weekly."""
        result = await self.build_weekly(user)
        return result.text

    # ------------------------------------------------------------------
    # AI comment helper
    # ------------------------------------------------------------------

    async def _get_ai_comment(self, context: str, user: User, sentences: int = 2) -> str:
        prompt = (
            f"Составь короткий мотивирующий комментарий ({sentences} предложения) к брифингу пользователя. "
            f"Данные: {context}. Не повторяй данные дословно, дай совет или оценку."
        )
        try:
            if user.ai_model == AIModel.GPT4O:
                resp = await self._get_openai_client().chat.completions.create(
                    model="gpt-4o",
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.choices[0].message.content or ""
            else:
                resp = await self._get_anthropic_client().messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text  # type: ignore[union-attr]
        except Exception:
            return ""


# ------------------------------------------------------------------
# Date helpers
# ------------------------------------------------------------------

_WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
_WEEKDAYS_SHORT_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _weekday_ru(dt: object) -> str:
    """Return full Russian weekday name for a datetime-like object."""
    from datetime import datetime as _dt
    if hasattr(dt, "weekday"):
        return _WEEKDAYS_RU[dt.weekday()]  # type: ignore[union-attr]
    return ""


def _weekday_short_ru(dt: object) -> str:
    """Return short Russian weekday name (2 chars)."""
    if hasattr(dt, "weekday"):
        return _WEEKDAYS_SHORT_RU[dt.weekday()]  # type: ignore[union-attr]
    return ""
