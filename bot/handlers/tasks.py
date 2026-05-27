from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repo.tasks import TaskRepo
from bot.utils.dt import fmt_full
from bot.keyboards.tasks import (
    confirm_keyboard,
    list_detail_keyboard,
    lists_keyboard,
    move_task_keyboard,
    task_detail_keyboard,
    tasks_by_priority_keyboard,
    tasks_list_keyboard,
)

router = Router()


@router.message(Command("tasks"))
async def cmd_tasks(message: Message, user: User, session: AsyncSession) -> None:
    repo = TaskRepo(session)
    tasks = await repo.get_by_user(user.id)
    if not tasks:
        await message.answer("У вас нет активных задач. Напишите что-нибудь чтобы создать задачу!")
        return
    text, kb = tasks_by_priority_keyboard(tasks, user.timezone)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(Command("lists"))
async def cmd_lists(message: Message, user: User, session: AsyncSession) -> None:
    repo = TaskRepo(session)
    lists = await repo.get_lists_by_user(user.id)
    if not lists:
        await message.answer("У вас нет списков. Используйте /start для создания.")
        return

    all_tasks = await repo.get_by_user(user.id)
    task_counts: dict[int, int] = {
        lst.id: sum(1 for t in all_tasks if t.list_id == lst.id)
        for lst in lists
    }

    await message.answer("Ваши списки:", reply_markup=lists_keyboard(lists, task_counts))


@router.callback_query(F.data.startswith("task:"))
async def cb_task_detail(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = TaskRepo(session)
    task = await repo.get_by_id(task_id)
    if not task or task.user_id != user.id:
        await callback.answer("Задача не найдена.")
        return

    lists = await repo.get_lists_by_user(user.id)
    prio = {"high": "🔴 Высокий", "medium": "🟡 Средний", "low": "🟢 Низкий"}.get(task.priority, "")
    due_str = f"\nДедлайн: {fmt_full(task.due_date, user.timezone)}" if task.due_date else ""
    status = "Выполнена" if task.is_completed else "Активна"
    text = (
        f"<b>{task.title}</b>\n"
        f"Приоритет: {prio}\n"
        f"Статус: {status}"
        f"{due_str}"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=task_detail_keyboard(task, lists))  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("task_complete:"))
async def cb_task_complete(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = TaskRepo(session)
    task = await repo.get_by_id(task_id)
    if not task or task.user_id != user.id:
        await callback.answer("Задача не найдена.")
        return
    await repo.complete(task)
    await callback.answer("Задача выполнена!")
    await callback.message.delete()  # type: ignore[union-attr]


@router.callback_query(F.data.startswith("task_delete:"))
async def cb_task_delete_confirm(callback: CallbackQuery) -> None:
    task_id = callback.data.split(":")[1]  # type: ignore[union-attr]
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Удалить задачу? Это действие нельзя отменить.",
        reply_markup=confirm_keyboard(f"task_delete_confirmed:{task_id}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm:task_delete_confirmed:"))
async def cb_task_delete_confirmed(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    task_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    repo = TaskRepo(session)
    task = await repo.get_by_id(task_id)
    if not task or task.user_id != user.id:
        await callback.answer("Задача не найдена.")
        return
    await repo.delete(task)
    await callback.answer("Задача удалена.")
    await callback.message.delete()  # type: ignore[union-attr]


@router.callback_query(F.data.startswith("task_move_start:"))
async def cb_task_move_start(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = TaskRepo(session)
    lists = await repo.get_lists_by_user(user.id)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Выберите список для перемещения:",
        reply_markup=move_task_keyboard(task_id, lists),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("task_move:"))
async def cb_task_move(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    parts = callback.data.split(":")  # type: ignore[union-attr]
    task_id, list_id = int(parts[1]), int(parts[2])
    repo = TaskRepo(session)
    task = await repo.get_by_id(task_id)
    if not task or task.user_id != user.id:
        await callback.answer("Задача не найдена.")
        return
    await repo.move_to_list(task, list_id)
    await callback.answer("Задача перемещена!")
    await callback.message.delete()  # type: ignore[union-attr]


@router.callback_query(F.data == "tasks_back")
async def cb_tasks_back(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    repo = TaskRepo(session)
    tasks = await repo.get_by_user(user.id)
    if not tasks:
        await callback.message.edit_text("У вас нет активных задач.")  # type: ignore[union-attr]
        await callback.answer()
        return
    text, kb = tasks_by_priority_keyboard(tasks, user.timezone)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("list:"))
async def cb_list_detail(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    list_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = TaskRepo(session)
    lst = await repo.get_list_by_id(list_id)
    if not lst or lst.user_id != user.id:
        await callback.answer("Список не найден.")
        return
    tasks = await repo.get_by_user(user.id)
    count = sum(1 for t in tasks if t.list_id == lst.id)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"<b>{lst.emoji} {lst.name}</b>\nАктивных задач: {count}",
        parse_mode="HTML",
        reply_markup=list_detail_keyboard(lst),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("list_tasks:"))
async def cb_list_tasks(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    list_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = TaskRepo(session)
    tasks = await repo.get_by_user(user.id)
    tasks = [t for t in tasks if t.list_id == list_id]
    if not tasks:
        await callback.answer("Задач в этом списке нет.")
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Задачи в списке:",
        reply_markup=tasks_list_keyboard(tasks),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("list_delete:"))
async def cb_list_delete_confirm(callback: CallbackQuery) -> None:
    list_id = callback.data.split(":")[1]  # type: ignore[union-attr]
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Удалить список со всеми задачами? Это действие нельзя отменить.",
        reply_markup=confirm_keyboard(f"list_delete_confirmed:{list_id}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm:list_delete_confirmed:"))
async def cb_list_delete_confirmed(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    list_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    repo = TaskRepo(session)
    lst = await repo.get_list_by_id(list_id)
    if not lst or lst.user_id != user.id:
        await callback.answer("Список не найден.")
        return
    await repo.delete_list(lst)
    await callback.answer("Список удалён.")
    await callback.message.delete()  # type: ignore[union-attr]


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery) -> None:
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.answer("Отменено.")


@router.callback_query(F.data == "lists_back")
async def cb_lists_back(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    repo = TaskRepo(session)
    lists = await repo.get_lists_by_user(user.id)
    tasks = await repo.get_by_user(user.id)
    task_counts = {lst.id: sum(1 for t in tasks if t.list_id == lst.id) for lst in lists}
    await callback.message.edit_text("Ваши списки:", reply_markup=lists_keyboard(lists, task_counts))  # type: ignore[union-attr]
    await callback.answer()
