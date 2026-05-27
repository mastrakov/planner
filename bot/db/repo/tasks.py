from datetime import datetime, timedelta

import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.db.models import Priority, Task, TaskEvent, TaskEventType, TaskList
from bot.utils.dt import now_utc


def _day_bounds_utc(tz_name: str) -> tuple[datetime, datetime]:
    """Return (day_start, day_end) as UTC naive datetimes for today in the given timezone."""
    tz = pytz.timezone(tz_name)
    now_local = datetime.now(tz)
    local_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    # Convert to UTC naive
    utc_start = local_start.astimezone(pytz.utc).replace(tzinfo=None)
    utc_end = local_end.astimezone(pytz.utc).replace(tzinfo=None)
    return utc_start, utc_end


class TaskRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: int,
        list_id: int,
        title: str,
        priority: str = "medium",
        due_date: datetime | None = None,
    ) -> Task:
        task = Task(user_id=user_id, list_id=list_id, title=title, priority=priority, due_date=due_date)
        self._session.add(task)
        await self._session.flush()
        event = TaskEvent(task_id=task.id, user_id=user_id, event_type=TaskEventType.CREATED)
        self._session.add(event)
        await self._session.flush()
        return task

    async def get_by_id(self, task_id: int) -> Task | None:
        return await self._session.get(Task, task_id)

    async def get_by_user(self, user_id: int, include_completed: bool = False) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.user_id == user_id)
            .options(selectinload(Task.task_list))
            .order_by(Task.created_at.desc())
        )
        if not include_completed:
            stmt = stmt.where(Task.completed_at.is_(None))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_overdue(self, user_id: int, tz_name: str = "UTC") -> list[Task]:
        """Return active tasks whose due_date is before today's start in the user's timezone."""
        day_start, _ = _day_bounds_utc(tz_name)
        stmt = (
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.completed_at.is_(None))
            .where(Task.due_date < day_start)
            .options(selectinload(Task.task_list))
            .order_by(Task.due_date)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_today(self, user_id: int, tz_name: str = "UTC") -> list[Task]:
        """Return active tasks with due_date = today in the user's timezone, sorted by priority DESC."""
        day_start, day_end = _day_bounds_utc(tz_name)
        stmt = (
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.completed_at.is_(None))
            .where(Task.due_date >= day_start)
            .where(Task.due_date < day_end)
            .options(selectinload(Task.task_list))
            .order_by(Task.due_date)
        )
        result = await self._session.execute(stmt)
        tasks = list(result.scalars().all())
        # Sort by priority DESC: high → medium → low
        priority_order = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
        tasks.sort(key=lambda t: priority_order.get(t.priority, 1))
        return tasks

    async def get_carrying_over(self, user_id: int, before_utc: datetime) -> list[Task]:
        """Return active tasks with due_date < before_utc (not completed).

        Used for briefing on future dates: tasks that aren't closed yet and
        whose deadline falls before the target day.
        """
        stmt = (
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.completed_at.is_(None))
            .where(Task.due_date < before_utc)
            .options(selectinload(Task.task_list))
            .order_by(Task.due_date)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_date(self, user_id: int, day_start_utc: datetime, day_end_utc: datetime) -> list[Task]:
        """Return active tasks with due_date within [day_start, day_end) UTC."""
        stmt = (
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.completed_at.is_(None))
            .where(Task.due_date >= day_start_utc)
            .where(Task.due_date < day_end_utc)
            .options(selectinload(Task.task_list))
            .order_by(Task.due_date)
        )
        result = await self._session.execute(stmt)
        tasks = list(result.scalars().all())
        priority_order = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
        tasks.sort(key=lambda t: priority_order.get(t.priority, 1))
        return tasks

    async def get_high_priority_no_deadline(self, user_id: int, limit: int = 5) -> list[Task]:
        """Return up to `limit` active high-priority tasks with no due_date."""
        stmt = (
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.completed_at.is_(None))
            .where(Task.priority == Priority.HIGH)
            .where(Task.due_date.is_(None))
            .options(selectinload(Task.task_list))
            .order_by(Task.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_week_range(self, user_id: int, tz_name: str = "UTC") -> list[Task]:
        """Return active tasks with due_date in [today, today+6 days] in the user's timezone."""
        day_start, _ = _day_bounds_utc(tz_name)
        week_end = day_start + timedelta(days=7)
        stmt = (
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.completed_at.is_(None))
            .where(Task.due_date >= day_start)
            .where(Task.due_date < week_end)
            .options(selectinload(Task.task_list))
            .order_by(Task.due_date)
        )
        result = await self._session.execute(stmt)
        tasks = list(result.scalars().all())
        priority_order = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
        tasks.sort(key=lambda t: (t.due_date or day_start, priority_order.get(t.priority, 1)))
        return tasks

    async def complete(self, task: Task) -> Task:
        task.completed_at = now_utc()
        event = TaskEvent(task_id=task.id, user_id=task.user_id, event_type=TaskEventType.COMPLETED)
        self._session.add(event)
        await self._session.flush()
        return task

    async def delete(self, task: Task) -> None:
        event = TaskEvent(task_id=task.id, user_id=task.user_id, event_type=TaskEventType.DELETED)
        self._session.add(event)
        await self._session.flush()
        await self._session.delete(task)
        await self._session.flush()

    async def update(self, task: Task, **kwargs: object) -> Task:
        for key, value in kwargs.items():
            setattr(task, key, value)
        event = TaskEvent(task_id=task.id, user_id=task.user_id, event_type=TaskEventType.UPDATED)
        self._session.add(event)
        await self._session.flush()
        return task

    async def move_to_list(self, task: Task, list_id: int) -> Task:
        task.list_id = list_id
        event = TaskEvent(task_id=task.id, user_id=task.user_id, event_type=TaskEventType.UPDATED)
        self._session.add(event)
        await self._session.flush()
        return task

    async def get_lists_by_user(self, user_id: int) -> list[TaskList]:
        result = await self._session.execute(
            select(TaskList).where(TaskList.user_id == user_id).order_by(TaskList.position)
        )
        return list(result.scalars().all())

    async def create_list(self, user_id: int, name: str, emoji: str = "📋", color: str = "#5865F2", position: int = 0) -> TaskList:
        task_list = TaskList(user_id=user_id, name=name, emoji=emoji, color=color, position=position)
        self._session.add(task_list)
        await self._session.flush()
        return task_list

    async def get_list_by_id(self, list_id: int) -> TaskList | None:
        return await self._session.get(TaskList, list_id)

    async def delete_list(self, task_list: TaskList) -> None:
        await self._session.delete(task_list)
        await self._session.flush()
