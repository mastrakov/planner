from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AIModel, User
from bot.db.repo.tasks import TaskRepo
from bot.utils.dt import fmt_full, parse_user_date
from bot.keyboards.tasks import (
    confirm_keyboard,
    list_detail_keyboard,
    lists_keyboard,
    move_task_keyboard,
    priority_keyboard,
    task_detail_keyboard,
    tasks_by_priority_keyboard,
    tasks_list_keyboard,
)

router = Router()


def _task_detail_text(task: object, tz: str) -> str:  # task is Task but avoid circular import hint
    from bot.db.models import Task as _Task
    t: _Task = task  # type: ignore[assignment]
    prio = {"high": "🔴 Высокий", "medium": "🟡 Средний", "low": "🟢 Низкий"}.get(t.priority, "")
    status = "Выполнена" if t.is_completed else "Активна"
    scheduled_str = f"\n🕐 Запланировано: {fmt_full(t.scheduled_at, tz)}" if t.scheduled_at else ""
    due_str = f"\n📅 Дедлайн: {fmt_full(t.due_date, tz)}" if t.due_date else ""
    return (
        f"<b>{t.title}</b>\n"
        f"Приоритет: {prio}\n"
        f"Статус: {status}"
        f"{scheduled_str}"
        f"{due_str}"
    )


class TaskDateStates(StatesGroup):
    waiting_scheduled_at = State()
    waiting_due_date = State()


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
    await callback.message.edit_text(  # type: ignore[union-attr]
        _task_detail_text(task, user.timezone),
        parse_mode="HTML",
        reply_markup=task_detail_keyboard(task, lists),
    )
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


@router.callback_query(F.data.startswith("task_priority_start:"))
async def cb_task_priority_start(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = TaskRepo(session)
    task = await repo.get_by_id(task_id)
    if not task or task.user_id != user.id:
        await callback.answer("Задача не найдена.")
        return
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"<b>{task.title}</b>\nВыберите приоритет:",
        parse_mode="HTML",
        reply_markup=priority_keyboard(task_id, task.priority),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("task_priority:"))
async def cb_task_priority_set(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    parts = callback.data.split(":")  # type: ignore[union-attr]
    task_id, new_priority = int(parts[1]), parts[2]
    repo = TaskRepo(session)
    task = await repo.get_by_id(task_id)
    if not task or task.user_id != user.id:
        await callback.answer("Задача не найдена.")
        return
    if task.priority == new_priority:
        await callback.answer("Приоритет не изменился.")
        return
    await repo.update(task, priority=new_priority)
    prio_label = {"high": "🔴 Высокий", "medium": "🟡 Средний", "low": "🟢 Низкий"}.get(new_priority, "")
    await callback.answer(f"Приоритет изменён: {prio_label}")
    # Refresh task detail view
    lists = await repo.get_lists_by_user(user.id)
    await callback.message.edit_text(  # type: ignore[union-attr]
        _task_detail_text(task, user.timezone),
        parse_mode="HTML",
        reply_markup=task_detail_keyboard(task, lists),
    )


@router.callback_query(F.data.startswith("task_set_scheduled:"))
async def cb_task_set_scheduled_start(callback: CallbackQuery, user: User, session: AsyncSession, state: FSMContext) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = TaskRepo(session)
    task = await repo.get_by_id(task_id)
    if not task or task.user_id != user.id:
        await callback.answer("Задача не найдена.")
        return
    await state.set_state(TaskDateStates.waiting_scheduled_at)
    await state.update_data(task_id=task_id)
    current = f" (сейчас: {fmt_full(task.scheduled_at, user.timezone)})" if task.scheduled_at else ""
    await callback.message.answer(  # type: ignore[union-attr]
        f"Задача: «{task.title}»{current}\n\n"
        "Напишите когда планируете выполнить — дату и время:\n"
        "<i>Примеры: «в субботу в 15:00», «завтра утром», «1 июня в 10:30», «убрать» — чтобы удалить</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("task_set_due:"))
async def cb_task_set_due_start(callback: CallbackQuery, user: User, session: AsyncSession, state: FSMContext) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = TaskRepo(session)
    task = await repo.get_by_id(task_id)
    if not task or task.user_id != user.id:
        await callback.answer("Задача не найдена.")
        return
    await state.set_state(TaskDateStates.waiting_due_date)
    await state.update_data(task_id=task_id)
    current = f" (сейчас: {fmt_full(task.due_date, user.timezone)})" if task.due_date else ""
    await callback.message.answer(  # type: ignore[union-attr]
        f"Задача: «{task.title}»{current}\n\n"
        "Напишите крайний срок (дедлайн):\n"
        "<i>Примеры: «до пятницы», «31 мая», «конец месяца», «убрать» — чтобы удалить</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(TaskDateStates.waiting_scheduled_at)
async def msg_task_scheduled_at(message: Message, user: User, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    task_id: int = data["task_id"]
    await state.clear()

    repo = TaskRepo(session)
    task = await repo.get_by_id(task_id)
    if not task or task.user_id != user.id:
        await message.answer("Задача не найдена.")
        return

    text = (message.text or "").strip().lower()

    # Clear value
    if text in ("убрать", "удалить", "нет", "clear", "remove", "-"):
        await repo.update(task, scheduled_at=None)
        await message.answer(f"✓ Время выполнения для «{task.title}» удалено.")
        return

    # Parse via AI
    use_gpt4o = user.ai_model == AIModel.GPT4O
    dt = await parse_user_date(
        message.text or "",
        tz_name=user.timezone,
        use_gpt4o=use_gpt4o,
    )
    if dt is None:
        await message.answer(
            "Не удалось распознать дату. Попробуйте ещё раз, например:\n"
            "«в субботу в 15:00», «завтра утром», «1 июня в 10:30»"
        )
        return

    await repo.update(task, scheduled_at=dt)
    await message.answer(
        f"✓ Запланировано: «{task.title}» — 🕐 {fmt_full(dt, user.timezone)}"
    )


@router.message(TaskDateStates.waiting_due_date)
async def msg_task_due_date(message: Message, user: User, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    task_id: int = data["task_id"]
    await state.clear()

    repo = TaskRepo(session)
    task = await repo.get_by_id(task_id)
    if not task or task.user_id != user.id:
        await message.answer("Задача не найдена.")
        return

    text = (message.text or "").strip().lower()

    # Clear value
    if text in ("убрать", "удалить", "нет", "clear", "remove", "-"):
        await repo.update(task, due_date=None)
        await message.answer(f"✓ Дедлайн для «{task.title}» удалён.")
        return

    # Parse via AI
    use_gpt4o = user.ai_model == AIModel.GPT4O
    dt = await parse_user_date(
        message.text or "",
        tz_name=user.timezone,
        use_gpt4o=use_gpt4o,
    )
    if dt is None:
        await message.answer(
            "Не удалось распознать дату. Попробуйте ещё раз, например:\n"
            "«до пятницы», «31 мая», «конец месяца»"
        )
        return

    await repo.update(task, due_date=dt)
    await message.answer(
        f"✓ Дедлайн установлен: «{task.title}» — 📅 {fmt_full(dt, user.timezone)}"
    )


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
