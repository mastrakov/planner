from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AIModel, User
from bot.db.repo.analytics import AnalyticsRepo
from bot.db.repo.tasks import TaskRepo

if TYPE_CHECKING:
    import anthropic
    from openai import AsyncOpenAI


# Bar chart width in characters
_BAR_WIDTH = 8
_WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _bar(value: int, max_val: int) -> str:
    if max_val == 0:
        return "░" * _BAR_WIDTH
    filled = round(value / max_val * _BAR_WIDTH)
    return "█" * filled + "░" * (_BAR_WIDTH - filled)


class AnalyticsService:
    def __init__(
        self,
        session: AsyncSession,
        analytics_repo: AnalyticsRepo | None = None,
        task_repo: TaskRepo | None = None,
        anthropic_client: anthropic.AsyncAnthropic | None = None,
        openai_client: AsyncOpenAI | None = None,
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

    async def _get_ai_insights(
        self,
        created: int,
        completed: int,
        daily: dict[str, int],
        user: User,
    ) -> str:
        """Generate a short AI insight for the analytics report."""
        best_day = max(daily, key=lambda k: daily[k]) if daily else "нет данных"
        completion_rate = round(completed / created * 100) if created else 0
        prompt = (
            f"Дай краткие AI-инсайты (2-3 предложения) по статистике задач пользователя. "
            f"Создано задач: {created}, выполнено: {completed} ({completion_rate}%). "
            f"Самый продуктивный период: {best_day}. "
            f"Назови паттерн и дай конкретную рекомендацию."
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

    async def get_stats(self, user: User, period: str = "week") -> str:
        if period == "month":
            return await self.get_monthly_stats(user)
        return await self.get_weekly_stats(user)

    async def get_weekly_stats(self, user: User) -> str:
        from datetime import timedelta

        from bot.utils.dt import now_utc
        now = now_utc()
        since = now - timedelta(days=7)

        open_count = await self._analytics_repo.get_open_count(user.id)
        overdue_count = await self._analytics_repo.get_overdue_count(user.id, tz_name=user.timezone)
        created_count = await self._analytics_repo.get_created_count(user.id, since)
        completed_count = await self._analytics_repo.get_completed_count(user.id, since)
        daily = await self._analytics_repo.get_daily_breakdown(user.id, tz_name=user.timezone, days=7)
        lists = await self._task_repo.get_lists_by_user(user.id)

        lines: list[str] = ["<b>📊 Аналитика за неделю</b>"]

        # --- Summary ---
        lines.append(
            f"\n🗂 Открытых задач: <b>{open_count}</b>"
            + (f"  (из них просрочено: <b>{overdue_count}</b>)" if overdue_count else "")
        )
        lines.append(f"✅ Закрыто за 7 дней: <b>{completed_count}</b>")
        lines.append(f"➕ Создано за 7 дней: <b>{created_count}</b>")

        # --- By-list stats ---
        list_lines: list[str] = []
        for lst in lists:
            total, done = await self._analytics_repo.get_list_task_counts(lst.id, user.id)
            if total == 0:
                continue
            pct = round(done / total * 100)
            list_lines.append(f"  {lst.emoji} {lst.name}: {done}/{total} ({pct}%)")
        if list_lines:
            lines.append("\n<b>По спискам (всё время):</b>")
            lines.extend(list_lines)

        # --- Daily breakdown ---
        max_created = max((r["created"] for r in daily), default=1) or 1
        max_completed = max((r["completed"] for r in daily), default=1) or 1
        max_val = max(max_created, max_completed)

        lines.append("\n<b>По дням:</b>")
        lines.append(f"<code>{'День':<9} {'созд':>4} {'закр':>4} {'просрч':>6}  график</code>")
        for row in daily:
            we = "🏖" if row["is_weekend"] else "  "
            ovr = f"⚠️{row['overdue']}" if row["overdue"] else "  —  "
            bar = _bar(row["completed"], max_val)
            lines.append(
                f"<code>{row['label']:<9}{we} {row['created']:>4} {row['completed']:>4} {ovr:>6}  {bar}</code>"
            )

        # --- Overdue pattern insight ---
        overdue_days = [r for r in daily if r["overdue"] > 0]
        if overdue_days:
            lines.append("\n<b>⚠️ Просрочки по дням:</b>")
            for row in overdue_days:
                we_label = " (выходной)" if row["is_weekend"] else ""
                load = row["created"] + row["completed"]
                load_hint = " — загруженный день" if load >= 5 else ""
                lines.append(
                    f"  {row['label']}{we_label}: {row['overdue']} задач просрочено{load_hint}"
                )

        # --- AI insights ---
        daily_counts = {r["label"]: r["completed"] for r in daily}
        ai_insight = await self._get_ai_insights(created_count, completed_count, daily_counts, user)
        if ai_insight:
            lines.append(f"\n💡 {ai_insight}")

        return "\n".join(lines)

    async def get_monthly_stats(self, user: User) -> str:
        from datetime import timedelta

        from bot.utils.dt import now_utc
        now = now_utc()
        since = now - timedelta(days=30)

        open_count = await self._analytics_repo.get_open_count(user.id)
        overdue_count = await self._analytics_repo.get_overdue_count(user.id, tz_name=user.timezone)
        created_count = await self._analytics_repo.get_created_count(user.id, since)
        completed_count = await self._analytics_repo.get_completed_count(user.id, since)
        weekly = await self._analytics_repo.get_weekly_breakdown(user.id, tz_name=user.timezone, weeks=4)
        lists = await self._task_repo.get_lists_by_user(user.id)

        lines: list[str] = ["<b>📊 Аналитика за месяц</b>"]

        lines.append(
            f"\n🗂 Открытых задач: <b>{open_count}</b>"
            + (f"  (из них просрочено: <b>{overdue_count}</b>)" if overdue_count else "")
        )
        lines.append(f"✅ Закрыто за 30 дней: <b>{completed_count}</b>")
        lines.append(f"➕ Создано за 30 дней: <b>{created_count}</b>")

        list_lines: list[str] = []
        for lst in lists:
            total, done = await self._analytics_repo.get_list_task_counts(lst.id, user.id)
            if total == 0:
                continue
            pct = round(done / total * 100)
            list_lines.append(f"  {lst.emoji} {lst.name}: {done}/{total} ({pct}%)")
        if list_lines:
            lines.append("\n<b>По спискам (всё время):</b>")
            lines.extend(list_lines)

        max_val = max((r["completed"] for r in weekly), default=1) or 1
        lines.append("\n<b>По неделям:</b>")
        lines.append(f"<code>{'Неделя':<15} {'созд':>4} {'закр':>4} {'просрч':>6}  график</code>")
        for row in weekly:
            ovr = f"⚠️{row['overdue']}" if row["overdue"] else "  —  "
            bar = _bar(row["completed"], max_val)
            lines.append(
                f"<code>{row['label']:<15} {row['created']:>4} {row['completed']:>4} {ovr:>6}  {bar}</code>"
            )

        overdue_weeks = [r for r in weekly if r["overdue"] > 0]
        if overdue_weeks:
            lines.append("\n<b>⚠️ Просрочки по неделям:</b>")
            for row in overdue_weeks:
                lines.append(f"  Неделя {row['label']}: {row['overdue']} задач просрочено")

        # --- AI insights ---
        weekly_counts = {r["label"]: r["completed"] for r in weekly}
        ai_insight = await self._get_ai_insights(created_count, completed_count, weekly_counts, user)
        if ai_insight:
            lines.append(f"\n💡 {ai_insight}")

        return "\n".join(lines)
