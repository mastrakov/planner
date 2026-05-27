from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.models import Task, TaskList


def tasks_list_keyboard(tasks: list[Task]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for task in tasks:
        prio = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task.priority, "")
        builder.button(
            text=f"{prio} {task.title[:40]}",
            callback_data=f"task:{task.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def task_detail_keyboard(task: Task, lists: list[TaskList]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not task.is_completed:
        builder.button(text="Выполнить", callback_data=f"task_complete:{task.id}")
    builder.button(text="Удалить", callback_data=f"task_delete:{task.id}")
    if lists:
        builder.button(text="Переместить в список...", callback_data=f"task_move_start:{task.id}")
    builder.button(text="Назад", callback_data="tasks_back")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def move_task_keyboard(task_id: int, lists: list[TaskList]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for lst in lists:
        builder.button(
            text=f"{lst.emoji} {lst.name}",
            callback_data=f"task_move:{task_id}:{lst.id}",
        )
    builder.button(text="Отмена", callback_data=f"task:{task_id}")
    builder.adjust(1)
    return builder.as_markup()


def lists_keyboard(lists: list[TaskList], task_counts: dict[int, int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for lst in lists:
        count = task_counts.get(lst.id, 0)
        builder.button(
            text=f"{lst.emoji} {lst.name} ({count})",
            callback_data=f"list:{lst.id}",
        )
    builder.button(text="Создать список", callback_data="list_create")
    builder.adjust(1)
    return builder.as_markup()


def list_detail_keyboard(lst: TaskList) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Просмотр задач", callback_data=f"list_tasks:{lst.id}")
    builder.button(text="Переименовать", callback_data=f"list_rename:{lst.id}")
    builder.button(text="Удалить список", callback_data=f"list_delete:{lst.id}")
    builder.button(text="Назад", callback_data="lists_back")
    builder.adjust(1)
    return builder.as_markup()


def confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, подтвердить", callback_data=f"confirm:{action}")
    builder.button(text="Отмена", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()
