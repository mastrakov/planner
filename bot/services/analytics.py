from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AIModel, Task, TaskEvent, TaskEventType, User
from bot.db.repo.tasks import TaskRepo
from bot.utils.dt import now_utc

if TYPE_CHECKING:
    import anthropic
    from openai import AsyncOpenAI


class AnalyticsService:
    def __init__(
        self,
        session: AsyncSession,
        anthropic_client: anthropic.AsyncAnthropic | None = None,
        openai_client: AsyncOpenAI | None = None,
    ) -> None:
        self._session = session
        self._task_repo = TaskRepo(session)
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

    async def get_stats(self, user: User, period: str = "week") -> str:
        """Return stats for the given period ('week' or 'month')."""
        if period == "month":
            return await self.get_monthly_stats(user)
        return await self.get_weekly_stats(user)

    async def get_weekly_stats(self, user: User) -> str:
        now = now_utc()
        week_ago = now - timedelta(days=7)

        # Tasks completed this week
        completed_result = await self._session.execute(
            select(func.count(TaskEvent.id))
            .where(TaskEvent.user_id == user.id)
            .where(TaskEvent.event_type == TaskEventType.COMPLETED)
            .where(TaskEvent.occurred_at >= week_ago)
        )
        completed_count = completed_result.scalar_one()

        # Tasks created this week
        created_result = await self._session.execute(
            select(func.count(TaskEvent.id))
            .where(TaskEvent.user_id == user.id)
            .where(TaskEvent.event_type == TaskEventType.CREATED)
            .where(TaskEvent.occurred_at >= week_ago)
        )
        created_count = created_result.scalar_one()

        # Daily breakdown of completions
        daily: dict[str, int] = {}
        for i in range(7):
            day = (now - timedelta(days=6 - i)).date()
            day_start = datetime(day.year, day.month, day.day)
            day_end = day_start + timedelta(days=1)
            result = await self._session.execute(
                select(func.count(TaskEvent.id))
                .where(TaskEvent.user_id == user.id)
                .where(TaskEvent.event_type == TaskEventType.COMPLETED)
                .where(TaskEvent.occurred_at >= day_start)
                .where(TaskEvent.occurred_at < day_end)
            )
            cnt = result.scalar_one()
            day_label = day.strftime("%a %d.%m")
            daily[day_label] = cnt

        # By-list stats
        lists = await self._task_repo.get_lists_by_user(user.id)
        list_stats: list[str] = []
        for lst in lists:
            total_result = await self._session.execute(
                select(func.count(Task.id))
                .where(Task.user_id == user.id)
                .where(Task.list_id == lst.id)
            )
            total = total_result.scalar_one()
            done_result = await self._session.execute(
                select(func.count(Task.id))
                .where(Task.user_id == user.id)
                .where(Task.list_id == lst.id)
                .where(Task.completed_at.isnot(None))
            )
            done = done_result.scalar_one()
            pct = round(done / total * 100) if total > 0 else 0
            list_stats.append(f"  {lst.emoji} {lst.name}: {done}/{total} ({pct}%)")

        # bar chart
        max_val = max(daily.values()) if daily else 1
        bar_lines: list[str] = []
        for day_label, cnt in daily.items():
            bar_len = round(cnt / max_val * 10) if max_val > 0 else 0
            bar = "█" * bar_len + "░" * (10 - bar_len)
            bar_lines.append(f"  {day_label}: {bar} {cnt}")

        lines: list[str] = [
            f"<b>Статистика за неделю</b>",
            f"\nСоздано задач: {created_count}",
            f"Выполнено: {completed_count}",
        ]
        if list_stats:
            lines.append("\n<b>По спискам:</b>")
            lines.extend(list_stats)
        if bar_lines:
            lines.append("\n<b>Динамика по дням:</b>")
            lines.extend(bar_lines)

        ai_comment = await self._get_ai_insights(created_count, completed_count, daily, user)
        if ai_comment:
            lines.append(f"\n💡 {ai_comment}")

        return "\n".join(lines)

    async def get_monthly_stats(self, user: User) -> str:
        now = now_utc()
        month_ago = now - timedelta(days=30)

        completed_result = await self._session.execute(
            select(func.count(TaskEvent.id))
            .where(TaskEvent.user_id == user.id)
            .where(TaskEvent.event_type == TaskEventType.COMPLETED)
            .where(TaskEvent.occurred_at >= month_ago)
        )
        completed_count = completed_result.scalar_one()

        created_result = await self._session.execute(
            select(func.count(TaskEvent.id))
            .where(TaskEvent.user_id == user.id)
            .where(TaskEvent.event_type == TaskEventType.CREATED)
            .where(TaskEvent.occurred_at >= month_ago)
        )
        created_count = created_result.scalar_one()

        # Weekly breakdown (4 weeks)
        weekly: dict[str, int] = {}
        for i in range(4):
            week_start = now - timedelta(days=(3 - i) * 7 + 7)
            week_end = week_start + timedelta(days=7)
            result = await self._session.execute(
                select(func.count(TaskEvent.id))
                .where(TaskEvent.user_id == user.id)
                .where(TaskEvent.event_type == TaskEventType.COMPLETED)
                .where(TaskEvent.occurred_at >= week_start)
                .where(TaskEvent.occurred_at < week_end)
            )
            label = f"Неделя {i + 1} ({week_start.strftime('%d.%m')}–{week_end.strftime('%d.%m')})"
            weekly[label] = result.scalar_one()

        lists = await self._task_repo.get_lists_by_user(user.id)
        list_stats: list[str] = []
        for lst in lists:
            total_result = await self._session.execute(
                select(func.count(Task.id))
                .where(Task.user_id == user.id)
                .where(Task.list_id == lst.id)
            )
            total = total_result.scalar_one()
            done_result = await self._session.execute(
                select(func.count(Task.id))
                .where(Task.user_id == user.id)
                .where(Task.list_id == lst.id)
                .where(Task.completed_at.isnot(None))
            )
            done = done_result.scalar_one()
            pct = round(done / total * 100) if total > 0 else 0
            list_stats.append(f"  {lst.emoji} {lst.name}: {done}/{total} ({pct}%)")

        max_val = max(weekly.values()) if weekly else 1
        bar_lines: list[str] = []
        for label, cnt in weekly.items():
            bar_len = round(cnt / max_val * 10) if max_val > 0 else 0
            bar = "█" * bar_len + "░" * (10 - bar_len)
            bar_lines.append(f"  {label}: {bar} {cnt}")

        lines: list[str] = [
            "<b>Статистика за месяц</b>",
            f"\nСоздано задач: {created_count}",
            f"Выполнено: {completed_count}",
        ]
        if list_stats:
            lines.append("\n<b>По спискам:</b>")
            lines.extend(list_stats)
        if bar_lines:
            lines.append("\n<b>Динамика по неделям:</b>")
            lines.extend(bar_lines)

        ai_comment = await self._get_ai_insights(created_count, completed_count, weekly, user)
        if ai_comment:
            lines.append(f"\n💡 {ai_comment}")

        return "\n".join(lines)

    async def _get_ai_insights(
        self,
        created: int,
        completed: int,
        daily: dict[str, int],
        user: User,
    ) -> str:
        best_day = max(daily, key=lambda k: daily[k]) if daily else "нет данных"
        prompt = (
            f"Дай краткие AI-инсайты (2-3 предложения) по недельной статистике задач. "
            f"Создано задач: {created}, выполнено: {completed}. "
            f"Самый продуктивный день: {best_day}. "
            f"Назови паттерны и дай рекомендацию на следующую неделю."
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
