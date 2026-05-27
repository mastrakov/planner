from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.db.models import Task, TaskEvent, TaskEventType, TaskList
from bot.utils.dt import now_utc


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

    async def get_overdue(self, user_id: int) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.completed_at.is_(None))
            .where(Task.due_date < now_utc())
            .options(selectinload(Task.task_list))
            .order_by(Task.due_date)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

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
