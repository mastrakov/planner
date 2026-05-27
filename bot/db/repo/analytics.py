from datetime import datetime, timedelta

import pytz
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Task, TaskEvent, TaskEventType
from bot.utils.dt import now_utc


def _day_bounds_utc_for_date(local_date: datetime, tz_name: str) -> tuple[datetime, datetime]:
    """Return (day_start_utc, day_end_utc) for a given local date."""
    tz = pytz.timezone(tz_name)
    local_start = local_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    aware_start = tz.localize(local_start)
    aware_end = aware_start + timedelta(days=1)
    return aware_start.astimezone(pytz.utc).replace(tzinfo=None), aware_end.astimezone(pytz.utc).replace(tzinfo=None)


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

    async def get_open_count(self, user_id: int) -> int:
        """Return count of all active (not completed) tasks."""
        result = await self._session.execute(
            select(func.count(Task.id))
            .where(Task.user_id == user_id)
            .where(Task.completed_at.is_(None))
        )
        return result.scalar_one()  # type: ignore[return-value]

    async def get_overdue_count(self, user_id: int, tz_name: str = "UTC") -> int:
        """Return count of active tasks past their due_date (before today's start in user tz)."""
        import pytz as _pytz
        tz = _pytz.timezone(tz_name)
        now_local = datetime.now(tz)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start.astimezone(_pytz.utc).replace(tzinfo=None)
        result = await self._session.execute(
            select(func.count(Task.id))
            .where(Task.user_id == user_id)
            .where(Task.completed_at.is_(None))
            .where(Task.due_date < day_start_utc)
        )
        return result.scalar_one()  # type: ignore[return-value]

    async def get_daily_breakdown(
        self,
        user_id: int,
        tz_name: str,
        days: int = 7,
    ) -> list[dict]:
        """Return per-day stats for the last `days` days.

        Each entry:
            date       – datetime (local midnight)
            label      – "Пн 26.05"
            is_weekend – bool
            created    – int
            completed  – int
            overdue    – int  (tasks whose due_date fell on that day but weren't completed by EOD)
        """
        import pytz as _pytz
        tz = _pytz.timezone(tz_name)
        now_local = datetime.now(tz)
        today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)

        _WEEKDAYS_RU_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

        rows: list[dict] = []
        for i in range(days - 1, -1, -1):
            local_day = today_local - timedelta(days=i)
            day_start_utc, day_end_utc = _day_bounds_utc_for_date(local_day, tz_name)

            created_r = await self._session.execute(
                select(func.count(TaskEvent.id))
                .where(TaskEvent.user_id == user_id)
                .where(TaskEvent.event_type == TaskEventType.CREATED)
                .where(TaskEvent.occurred_at >= day_start_utc)
                .where(TaskEvent.occurred_at < day_end_utc)
            )
            completed_r = await self._session.execute(
                select(func.count(TaskEvent.id))
                .where(TaskEvent.user_id == user_id)
                .where(TaskEvent.event_type == TaskEventType.COMPLETED)
                .where(TaskEvent.occurred_at >= day_start_utc)
                .where(TaskEvent.occurred_at < day_end_utc)
            )
            # Overdue = tasks whose due_date was within this day but weren't completed by EOD.
            # Only meaningful for past days — for today/future the day hasn't ended yet.
            import pytz as _pytz2
            now_utc_naive = now_utc()
            if day_end_utc <= now_utc_naive:
                overdue_r = await self._session.execute(
                    select(func.count(Task.id))
                    .where(Task.user_id == user_id)
                    .where(Task.due_date >= day_start_utc)
                    .where(Task.due_date < day_end_utc)
                    .where(
                        (Task.completed_at.is_(None)) |
                        (Task.completed_at >= day_end_utc)
                    )
                )
                overdue_count_day = overdue_r.scalar_one()
            else:
                overdue_count_day = 0

            wd = local_day.weekday()
            rows.append({
                "date": local_day,
                "label": f"{_WEEKDAYS_RU_SHORT[wd]} {local_day.strftime('%d.%m')}",
                "is_weekend": wd >= 5,
                "created": created_r.scalar_one(),
                "completed": completed_r.scalar_one(),
                "overdue": overdue_count_day,
            })
        return rows

    async def get_weekly_breakdown(
        self,
        user_id: int,
        tz_name: str,
        weeks: int = 4,
    ) -> list[dict]:
        """Return per-week stats for the last `weeks` weeks."""
        import pytz as _pytz
        tz = _pytz.timezone(tz_name)
        now_local = datetime.now(tz)
        today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)

        rows: list[dict] = []
        for i in range(weeks - 1, -1, -1):
            week_start_local = today_local - timedelta(days=today_local.weekday() + 7 * i)
            week_end_local = week_start_local + timedelta(days=7)
            ws_utc, _ = _day_bounds_utc_for_date(week_start_local, tz_name)
            we_utc, _ = _day_bounds_utc_for_date(week_end_local, tz_name)

            created_r = await self._session.execute(
                select(func.count(TaskEvent.id))
                .where(TaskEvent.user_id == user_id)
                .where(TaskEvent.event_type == TaskEventType.CREATED)
                .where(TaskEvent.occurred_at >= ws_utc)
                .where(TaskEvent.occurred_at < we_utc)
            )
            completed_r = await self._session.execute(
                select(func.count(TaskEvent.id))
                .where(TaskEvent.user_id == user_id)
                .where(TaskEvent.event_type == TaskEventType.COMPLETED)
                .where(TaskEvent.occurred_at >= ws_utc)
                .where(TaskEvent.occurred_at < we_utc)
            )
            # Only count overdue for weeks that have fully ended
            now_utc_naive = now_utc()
            if we_utc <= now_utc_naive:
                overdue_r = await self._session.execute(
                    select(func.count(Task.id))
                    .where(Task.user_id == user_id)
                    .where(Task.due_date >= ws_utc)
                    .where(Task.due_date < we_utc)
                    .where(
                        (Task.completed_at.is_(None)) |
                        (Task.completed_at >= we_utc)
                    )
                )
                overdue_week = overdue_r.scalar_one()
            else:
                overdue_week = 0

            label = f"{week_start_local.strftime('%d.%m')}–{(week_end_local - timedelta(days=1)).strftime('%d.%m')}"
            rows.append({
                "label": label,
                "created": created_r.scalar_one(),
                "completed": completed_r.scalar_one(),
                "overdue": overdue_week,
            })
        return rows

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
