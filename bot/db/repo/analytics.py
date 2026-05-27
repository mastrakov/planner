from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Task, TaskEvent, TaskEventType
from bot.utils.dt import now_utc


class AnalyticsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_completed_count(self, user_id: int, since: datetime) -> int:
        result = await self._session.execute(
            select(func.count(TaskEvent.id))
            .where(TaskEvent.user_id == user_id)
            .where(TaskEvent.event_type == TaskEventType.COMPLETED)
            .where(TaskEvent.occurred_at >= since)
        )
        return result.scalar_one()  # type: ignore[return-value]

    async def get_created_count(self, user_id: int, since: datetime) -> int:
        result = await self._session.execute(
            select(func.count(TaskEvent.id))
            .where(TaskEvent.user_id == user_id)
            .where(TaskEvent.event_type == TaskEventType.CREATED)
            .where(TaskEvent.occurred_at >= since)
        )
        return result.scalar_one()  # type: ignore[return-value]

    async def get_completed_per_day(self, user_id: int, days: int = 7) -> dict[str, int]:
        """Return day_label -> count mapping for the last `days` days."""
        now = now_utc()
        daily: dict[str, int] = {}
        for i in range(days):
            day = (now - timedelta(days=days - 1 - i)).date()
            day_start = datetime(day.year, day.month, day.day)
            day_end = day_start + timedelta(days=1)
            result = await self._session.execute(
                select(func.count(TaskEvent.id))
                .where(TaskEvent.user_id == user_id)
                .where(TaskEvent.event_type == TaskEventType.COMPLETED)
                .where(TaskEvent.occurred_at >= day_start)
                .where(TaskEvent.occurred_at < day_end)
            )
            cnt = result.scalar_one()
            day_label = day.strftime("%a %d.%m")
            daily[day_label] = cnt
        return daily

    async def get_completed_per_week(self, user_id: int, weeks: int = 4) -> dict[str, int]:
        """Return week_label -> count mapping for the last `weeks` weeks."""
        now = now_utc()
        weekly: dict[str, int] = {}
        for i in range(weeks):
            week_start = now - timedelta(days=(weeks - 1 - i) * 7 + 7)
            week_end = week_start + timedelta(days=7)
            result = await self._session.execute(
                select(func.count(TaskEvent.id))
                .where(TaskEvent.user_id == user_id)
                .where(TaskEvent.event_type == TaskEventType.COMPLETED)
                .where(TaskEvent.occurred_at >= week_start)
                .where(TaskEvent.occurred_at < week_end)
            )
            label = f"Неделя {i + 1} ({week_start.strftime('%d.%m')}–{week_end.strftime('%d.%m')})"
            weekly[label] = result.scalar_one()
        return weekly

    async def get_list_task_counts(self, list_id: int, user_id: int) -> tuple[int, int]:
        """Return (total, done) for the given list."""
        total_result = await self._session.execute(
            select(func.count(Task.id))
            .where(Task.user_id == user_id)
            .where(Task.list_id == list_id)
        )
        total = total_result.scalar_one()
        done_result = await self._session.execute(
            select(func.count(Task.id))
            .where(Task.user_id == user_id)
            .where(Task.list_id == list_id)
            .where(Task.completed_at.isnot(None))
        )
        done = done_result.scalar_one()
        return total, done  # type: ignore[return-value]
