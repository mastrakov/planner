from datetime import datetime, timedelta

import anthropic
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.db.models import AIModel, User
from bot.db.repo.calendar import CalendarRepo
from bot.db.repo.tasks import TaskRepo

_anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
_openai_client = AsyncOpenAI(api_key=settings.openai_api_key)


class BriefingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._task_repo = TaskRepo(session)
        self._calendar_repo = CalendarRepo(session)

    async def build_morning_briefing(self, user: User) -> str:
        now = datetime.utcnow()
        today_end = now.replace(hour=23, minute=59, second=59)

        overdue_tasks = await self._task_repo.get_overdue(user.id)
        today_tasks = [
            t for t in await self._task_repo.get_by_user(user.id)
            if t.due_date and t.due_date.date() == now.date()
        ]
        today_events = await self._calendar_repo.get_for_date_range(user.id, now, today_end)
        all_tasks = await self._task_repo.get_by_user(user.id)

        lines: list[str] = [f"<b>Доброе утро!</b> {now.strftime('%d.%m.%Y')}"]

        if overdue_tasks:
            lines.append("\n<b>Просроченные задачи:</b>")
            for t in overdue_tasks:
                due_str = t.due_date.strftime("%d.%m") if t.due_date else ""
                lines.append(f"  ❗ {t.title} (до {due_str})")

        if today_events:
            lines.append("\n<b>События сегодня:</b>")
            for ev in today_events:
                lines.append(f"  📅 {ev.starts_at.strftime('%H:%M')} — {ev.title}")

        if today_tasks:
            lines.append("\n<b>Задачи на сегодня:</b>")
            for t in today_tasks:
                prio = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.priority, "")
                lines.append(f"  {prio} {t.title}")

        # AI comment
        context = (
            f"Просроченных задач: {len(overdue_tasks)}. "
            f"Событий сегодня: {len(today_events)}. "
            f"Задач на сегодня: {len(today_tasks)}. "
            f"Всего активных задач: {len(all_tasks)}."
        )
        ai_comment = await self._get_ai_comment(context, user)
        if ai_comment:
            lines.append(f"\n💡 {ai_comment}")

        return "\n".join(lines)

    async def _get_ai_comment(self, context: str, user: User) -> str:
        prompt = (
            f"Составь короткий мотивирующий комментарий (1-2 предложения) к утреннему брифингу пользователя. "
            f"Данные: {context}. Не повторяй данные, дай совет или оценку дня."
        )
        try:
            if user.ai_model == AIModel.GPT4O:
                resp = await _openai_client.chat.completions.create(
                    model="gpt-4o",
                    max_tokens=150,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.choices[0].message.content or ""
            else:
                resp = await _anthropic_client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=150,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text  # type: ignore[union-attr]
        except Exception:
            return ""

    async def build_weekly_plan(self, user: User) -> str:
        now = datetime.utcnow()
        week_end = now + timedelta(days=7)

        week_tasks = [
            t for t in await self._task_repo.get_by_user(user.id)
            if t.due_date and now <= t.due_date <= week_end
        ]
        week_events = await self._calendar_repo.get_for_date_range(user.id, now, week_end)

        lines: list[str] = [f"<b>План на неделю</b> ({now.strftime('%d.%m')} — {week_end.strftime('%d.%m')})"]

        if week_events:
            lines.append("\n<b>События:</b>")
            for ev in week_events:
                lines.append(f"  📅 {ev.starts_at.strftime('%d.%m %H:%M')} — {ev.title}")

        if week_tasks:
            lines.append("\n<b>Задачи с дедлайном:</b>")
            grouped: dict[str, list[str]] = {}
            for t in week_tasks:
                lbl = f"{t.task_list.emoji} {t.task_list.name}"
                due = t.due_date.strftime("%d.%m") if t.due_date else ""
                grouped.setdefault(lbl, []).append(f"  • {t.title} (до {due})")
            for lbl, items in grouped.items():
                lines.append(f"\n{lbl}")
                lines.extend(items)

        context = f"Встреч на неделе: {len(week_events)}, задач с дедлайном: {len(week_tasks)}."
        ai_comment = await self._get_ai_comment(context, user)
        if ai_comment:
            lines.append(f"\n💡 {ai_comment}")

        return "\n".join(lines)
