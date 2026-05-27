from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Priority, Task, TaskList, User
from bot.db.repo.tasks import TaskRepo
from bot.services.intent.models import (
    CompleteTaskIntent,
    CreateTaskIntent,
    DeleteTaskIntent,
    ListTasksIntent,
    UpdateTaskIntent,
)
from bot.utils.dt import fmt_date, fmt_full, now_utc


@dataclass
class TaskCreateResult:
    """Return value of TaskService.create_task_smart."""
    task: Task
    target_list: TaskList
    auto_assigned: bool  # True if list was auto-assigned with high confidence
    low_confidence: bool  # True if list confidence was < 0.8 and multiple lists exist

DEFAULT_LISTS = [
    ("Работа", "💼", "#4A90D9"),
    ("Дом", "🏠", "#27AE60"),
    ("Личное", "👤", "#9B59B6"),
]


class TaskService:
    def __init__(self, session: AsyncSession, repo: TaskRepo | None = None) -> None:
        self._session = session
        self._repo = repo if repo is not None else TaskRepo(session)

    async def create_default_lists(self, user_id: int) -> None:
        existing = await self._repo.get_lists_by_user(user_id)
        if existing:
            return
        for i, (name, emoji, color) in enumerate(DEFAULT_LISTS):
            await self._repo.create_list(user_id, name, emoji, color, position=i)

    async def create_task_smart(self, user: User, intent: CreateTaskIntent) -> TaskCreateResult | str:
        """Create a task applying AI list classification logic.

        Returns:
            TaskCreateResult — when a task was successfully created.
            str — error message when no lists are available.

        Classification rules:
        - Single list → always use it (auto_assigned=True, low_confidence=False).
        - Multiple lists + confidence >= 0.8 → auto-assign to suggested_list_id (or first).
        - Multiple lists + confidence < 0.8 → assign to best candidate but mark low_confidence=True
          so the caller can show a list-selection keyboard.
        """
        lists = await self._repo.get_lists_by_user(user.id)
        if not lists:
            return "У вас нет списков задач. Используйте /start для создания."

        auto_assigned = False
        low_confidence = False

        if len(lists) == 1:
            target_list = lists[0]
            auto_assigned = True
        elif intent.suggested_list_id is not None and intent.list_confidence >= 0.8:
            target_list = next((l for l in lists if l.id == intent.suggested_list_id), lists[0])
            auto_assigned = True
        else:
            # Low confidence or no suggestion — pick best candidate, flag for user choice
            if intent.suggested_list_id is not None:
                target_list = next((l for l in lists if l.id == intent.suggested_list_id), lists[0])
            elif intent.list_name:
                target_list = next(
                    (l for l in lists if intent.list_name.lower() in l.name.lower()),
                    lists[0],
                )
            else:
                target_list = lists[0]
            low_confidence = True if len(lists) > 1 else False

        task = await self._repo.create(
            user_id=user.id,
            list_id=target_list.id,
            title=intent.title,
            priority=intent.priority,
            due_date=intent.due_date,
            scheduled_at=intent.scheduled_at,
        )
        return TaskCreateResult(
            task=task,
            target_list=target_list,
            auto_assigned=auto_assigned,
            low_confidence=low_confidence,
        )

    async def get_lists(self, user_id: int) -> list[TaskList]:
        """Return the user's task lists sorted by position."""
        return await self._repo.get_lists_by_user(user_id)

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
        due_str = f" (до {fmt_full(task.due_date, user.timezone)})" if task.due_date else ""
        return f"Задача добавлена в список {target_list.emoji} {target_list.name}: «{task.title}»{due_str}"

    def _find_tasks(self, tasks: list, query: str) -> list:
        """Return tasks whose title contains query (case-insensitive)."""
        q = query.lower()
        return [t for t in tasks if q in t.title.lower()]

    def _ambiguous_msg(self, query: str, matches: list) -> str:
        titles = "\n".join(f"  • {t.title}" for t in matches)
        return (
            f"Найдено несколько задач по запросу «{query}»:\n{titles}\n\n"
            f"Уточните название точнее."
        )

    async def complete_task(self, user: User, intent: CompleteTaskIntent) -> str:
        tasks = await self._repo.get_by_user(user.id)
        matches = self._find_tasks(tasks, intent.task_title)
        if not matches:
            return f"Задача «{intent.task_title}» не найдена."
        if len(matches) > 1:
            return self._ambiguous_msg(intent.task_title, matches)
        found = matches[0]
        await self._repo.complete(found)
        return f"Задача «{found.title}» отмечена как выполненная."

    async def delete_task(self, user: User, intent: DeleteTaskIntent) -> str:
        tasks = await self._repo.get_by_user(user.id)
        matches = self._find_tasks(tasks, intent.task_title)
        if not matches:
            return f"Задача «{intent.task_title}» не найдена."
        if len(matches) > 1:
            return self._ambiguous_msg(intent.task_title, matches)
        found = matches[0]
        await self._repo.delete(found)
        return f"Задача «{found.title}» удалена."

    async def update_task(self, user: User, intent: UpdateTaskIntent) -> str:
        tasks = await self._repo.get_by_user(user.id)
        matches = self._find_tasks(tasks, intent.task_title)
        if not matches:
            return f"Задача «{intent.task_title}» не найдена."
        if len(matches) > 1:
            return self._ambiguous_msg(intent.task_title, matches)
        found = matches[0]

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

        return f"Задача «{found.title}» обновлена."

    async def get_tasks_for_user(self, user: User, intent: ListTasksIntent) -> str:
        tasks = await self._repo.get_by_user(user.id)
        if not tasks:
            return "У вас нет активных задач."

        now = now_utc()

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
            due_str = f" — до {fmt_date(task.due_date, user.timezone)}" if task.due_date else ""
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
        return "Задача перемещена."
