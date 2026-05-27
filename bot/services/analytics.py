from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AIModel, User
from bot.db.repo.analytics import AnalyticsRepo
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
        analytics_repo: AnalyticsRepo | None = None,
        task_repo: TaskRepo | None = None,
    ) -> None:
        self._session = session
        self._task_repo = task_repo if task_repo is not None else TaskRepo(session)
        self._analytics_repo = analytics_repo if analytics_repo is not None else AnalyticsRepo(session)
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
        from datetime import timedelta
        now = now_utc()
        week_ago = now - timedelta(days=7)

        completed_count = await self._analytics_repo.get_completed_count(user.id, week_ago)
        created_count = await self._analytics_repo.get_created_count(user.id, week_ago)
        daily = await self._analytics_repo.get_completed_per_day(user.id, days=7)

        # By-list stats
        lists = await self._task_repo.get_lists_by_user(user.id)
        list_stats: list[str] = []
        for lst in lists:
            total, done = await self._analytics_repo.get_list_task_counts(lst.id, user.id)
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
            "<b>Статистика за неделю</b>",
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
        from datetime import timedelta
        now = now_utc()
        month_ago = now - timedelta(days=30)

        completed_count = await self._analytics_repo.get_completed_count(user.id, month_ago)
        created_count = await self._analytics_repo.get_created_count(user.id, month_ago)
        weekly = await self._analytics_repo.get_completed_per_week(user.id, weeks=4)

        lists = await self._task_repo.get_lists_by_user(user.id)
        list_stats: list[str] = []
        for lst in lists:
            total, done = await self._analytics_repo.get_list_task_counts(lst.id, user.id)
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
