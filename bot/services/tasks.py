from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Priority, User
from bot.db.repo.tasks import TaskRepo
from bot.services.intent.models import (
    CompleteTaskIntent,
    CreateTaskIntent,
    DeleteTaskIntent,
    ListTasksIntent,
    UpdateTaskIntent,
)

DEFAULT_LISTS = [
    ("Работа", "💼", "#4A90D9"),
    ("Дом", "🏠", "#27AE60"),
    ("Личное", "👤", "#9B59B6"),
]


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TaskRepo(session)

    async def create_default_lists(self, user_id: int) -> None:
        existing = await self._repo.get_lists_by_user(user_id)
        if existing:
            return
        for i, (name, emoji, color) in enumerate(DEFAULT_LISTS):
            await self._repo.create_list(user_id, name, emoji, color, position=i)
        await self._session.commit()

    async def create_task(self, user: User, intent: CreateTaskIntent) -> str:
        lists = await self._repo.get_lists_by_user(user.id)
        target_list = None
        if intent.list_name:
            for lst in lists:
                if intent.list_name.lower() in lst.name.lower():
                    target_list = lst
                    break
        if target_list is None and lists:
            target_list = lists[0]
        if target_list is None:
            return "У вас нет списков задач. Используйте /start для создания."

        task = await self._repo.create(
            user_id=user.id,
            list_id=target_list.id,
            title=intent.title,
            priority=intent.priority,
            due_date=intent.due_date,
        )
        await self._session.commit()
        due_str = f" (до {task.due_date.strftime('%d.%m %H:%M')})" if task.due_date else ""
        return f"Задача добавлена в список {target_list.emoji} {target_list.name}: «{task.title}»{due_str}"

    async def complete_task(self, user: User, intent: CompleteTaskIntent) -> str:
        tasks = await self._repo.get_by_user(user.id)
        found = next(
            (t for t in tasks if intent.task_title.lower() in t.title.lower()), None
        )
        if not found:
            return f"Задача «{intent.task_title}» не найдена."
        await self._repo.complete(found)
        await self._session.commit()
        return f"Задача «{found.title}» отмечена как выполненная."

    async def delete_task(self, user: User, intent: DeleteTaskIntent) -> str:
        tasks = await self._repo.get_by_user(user.id)
        found = next(
            (t for t in tasks if intent.task_title.lower() in t.title.lower()), None
        )
        if not found:
            return f"Задача «{intent.task_title}» не найдена."
        await self._repo.delete(found)
        await self._session.commit()
        return f"Задача «{found.title}» удалена."

    async def update_task(self, user: User, intent: UpdateTaskIntent) -> str:
        tasks = await self._repo.get_by_user(user.id)
        found = next(
            (t for t in tasks if intent.task_title.lower() in t.title.lower()), None
        )
        if not found:
            return f"Задача «{intent.task_title}» не найдена."

        kwargs: dict[str, object] = {}
        if intent.new_title:
            kwargs["title"] = intent.new_title
        if intent.new_priority:
            kwargs["priority"] = intent.new_priority
        if intent.new_due_date:
            kwargs["due_date"] = intent.new_due_date

        if intent.new_list_name:
            lists = await self._repo.get_lists_by_user(user.id)
            new_list = next(
                (lst for lst in lists if intent.new_list_name.lower() in lst.name.lower()), None
            )
            if new_list:
                await self._repo.move_to_list(found, new_list.id)

        if kwargs:
            await self._repo.update(found, **kwargs)

        await self._session.commit()
        return f"Задача «{found.title}» обновлена."

    async def get_tasks_for_user(self, user: User, intent: ListTasksIntent) -> str:
        from datetime import datetime

        tasks = await self._repo.get_by_user(user.id)
        if not tasks:
            return "У вас нет активных задач."

        now = datetime.utcnow()

        if intent.filter == "overdue":
            tasks = [t for t in tasks if t.due_date and t.due_date < now]
        elif intent.filter == "today":
            tasks = [
                t for t in tasks
                if t.due_date and t.due_date.date() == now.date()
            ]
        elif intent.filter == "high_priority":
            tasks = [t for t in tasks if t.priority == Priority.HIGH]
        elif intent.list_name:
            tasks = [
                t for t in tasks
                if intent.list_name.lower() in t.task_list.name.lower()
            ]

        if not tasks:
            return "Задач по выбранному фильтру нет."

        # group by list
        grouped: dict[str, list[str]] = {}
        for task in tasks:
            list_label = f"{task.task_list.emoji} {task.task_list.name}"
            prio_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task.priority, "")
            due_str = f" — до {task.due_date.strftime('%d.%m')}" if task.due_date else ""
            grouped.setdefault(list_label, []).append(f"  {prio_icon} {task.title}{due_str}")

        lines = ["<b>Задачи:</b>"]
        for list_name, items in grouped.items():
            lines.append(f"\n<b>{list_name}</b>")
            lines.extend(items)
        return "\n".join(lines)

    async def move_task(self, task_id: int, list_id: int) -> str:
        task = await self._repo.get_by_id(task_id)
        if not task:
            return "Задача не найдена."
        await self._repo.move_to_list(task, list_id)
        await self._session.commit()
        return f"Задача перемещена."
