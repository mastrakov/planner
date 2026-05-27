"""Callback handlers for inline buttons produced by BriefingService
and the task-creation flow (list selection, deadline button, reminder buttons).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repo.reminders import ReminderRepo
from bot.db.repo.tasks import TaskRepo
from bot.utils.dt import fmt_time, now_utc

logger = logging.getLogger(__name__)
router = Router()


# ---------------------------------------------------------------------------
# Task list selection — created after low-confidence auto-classification
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("task_assign_list:"))
async def cb_task_assign_list(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    """Move task to the user-chosen list after low-confidence classification."""
    # callback_data format: task_assign_list:{task_id}:{list_id}
    parts = callback.data.split(":")  # type: ignore[union-attr]
    if len(parts) != 3:
        await callback.answer("Неверный формат.")
        return

    task_id, list_id = int(parts[1]), int(parts[2])
    repo = TaskRepo(session)

    task = await repo.get_by_id(task_id)
    if not task or task.user_id != user.id:
        await callback.answer("Задача не найдена.")
        return

    target_list = await repo.get_list_by_id(list_id)
    if not target_list or target_list.user_id != user.id:
        await callback.answer("Список не найден.")
        return

    await repo.move_to_list(task, list_id)

    from bot.keyboards.tasks import task_created_keyboard
    text = f"Добавил в {target_list.emoji} {target_list.name}: «{task.title}»"
    kb = task_created_keyboard(task.id, has_due_date=task.due_date is not None)
    await callback.message.edit_text(text, reply_markup=kb if not task.due_date else None)  # type: ignore[union-attr]
    await callback.answer()


# ---------------------------------------------------------------------------
# Add deadline button
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("task_set_deadline:"))
async def cb_task_set_deadline(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    """Prompt user to send a date for the task deadline (simplified: ask for text)."""
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = TaskRepo(session)
    task = await repo.get_by_id(task_id)
    if not task or task.user_id != user.id:
        await callback.answer("Задача не найдена.")
        return

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"Задача: «{task.title}»\n\nНапишите дедлайн текстом (например «31 мая», «завтра», «пятница»).\n"
        f"Я распознаю и установлю дату автоматически."
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Reminder for calendar event — remind_event:{minutes}:{event_id}
# ---------------------------------------------------------------------------

@router.callback_query(F.data.regexp(r"^remind_event:\d+:\d+$"))
async def cb_remind_event(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    """Create a reminder N minutes before the event."""
    parts = callback.data.split(":")  # type: ignore[union-attr]
    minutes, event_id = int(parts[1]), int(parts[2])

    from bot.db.repo.calendar import CalendarRepo
    cal_repo = CalendarRepo(session)
    event = await cal_repo.get_by_id(event_id)
    if not event or event.user_id != user.id:
        await callback.answer("Событие не найдено.")
        return

    remind_at = event.starts_at - timedelta(minutes=minutes)
    if remind_at <= now_utc():
        await callback.answer("Событие уже прошло или напоминание было бы в прошлом.")
        return

    reminder_repo = ReminderRepo(session)
    label = f"{minutes} мин" if minutes < 60 else f"{minutes // 60} ч"
    await reminder_repo.create(
        user_id=user.id,
        title=f"🔔 {event.title}",
        remind_at=remind_at,
        event_id=event.id,
    )

    await callback.answer(f"Напоминание за {label} установлено!")
    # Remove the button from the message by editing without the keyboard
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Reminder for calendar event — custom time
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("remind_event_custom:"))
async def cb_remind_event_custom(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    """Ask user to specify custom reminder offset."""
    event_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]

    from bot.db.repo.calendar import CalendarRepo
    cal_repo = CalendarRepo(session)
    event = await cal_repo.get_by_id(event_id)
    if not event or event.user_id != user.id:
        await callback.answer("Событие не найдено.")
        return

    await callback.message.answer(  # type: ignore[union-attr]
        f"Для события «{event.title}» напишите, за сколько напомнить (например «за 30 минут», «за 2 часа»)."
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Reminder for today-task — remind_task_morning:{task_id}
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("remind_task_morning:"))
async def cb_remind_task_morning(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    """Create a reminder at 09:00 today for a task with a today deadline."""
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = TaskRepo(session)
    task = await repo.get_by_id(task_id)
    if not task or task.user_id != user.id:
        await callback.answer("Задача не найдена.")
        return

    import pytz
    tz = pytz.timezone(user.timezone)
    now_local = pytz.utc.localize(now_utc()).astimezone(tz)
    remind_local = now_local.replace(hour=9, minute=0, second=0, microsecond=0)
    remind_utc = remind_local.astimezone(pytz.utc).replace(tzinfo=None)

    if remind_utc <= now_utc():
        await callback.answer("09:00 уже прошло сегодня.")
        return

    reminder_repo = ReminderRepo(session)
    # Embed task_id in title so has_reminder_for_task_today can find it
    await reminder_repo.create(
        user_id=user.id,
        title=f"task:{task_id}: {task.title}",
        remind_at=remind_utc,
    )

    await callback.answer(f"Напомню в 09:00!")
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Remind all weekly events — single button
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "remind_all_week_events")
async def cb_remind_all_week_events(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    """Create 1-hour-before reminders for all events in the current week that lack one."""
    from datetime import timedelta as _td

    from bot.db.repo.calendar import CalendarRepo
    cal_repo = CalendarRepo(session)
    reminder_repo = ReminderRepo(session)

    now = now_utc()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = day_start + _td(days=7)
    week_events = await cal_repo.get_for_date_range(user.id, day_start, week_end)

    created = 0
    for ev in week_events:
        has_rem = await reminder_repo.has_reminder_for_event(ev.id)
        if has_rem:
            continue
        remind_at = ev.starts_at - _td(hours=1)
        if remind_at <= now:
            continue
        await reminder_repo.create(
            user_id=user.id,
            title=f"🔔 {ev.title}",
            remind_at=remind_at,
            event_id=ev.id,
        )
        created += 1

    if created:
        await callback.answer(f"Создано {created} напоминаний за 1 час до событий!")
    else:
        await callback.answer("Все события уже имеют напоминания.")

    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
