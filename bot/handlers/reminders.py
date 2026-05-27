from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repo.reminders import ReminderRepo
from bot.utils.dt import fmt_full

router = Router()


def _reminders_keyboard(reminders: list) -> object:
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    for r in reminders:
        icon = "📅" if r.event_id else "🔔"
        builder.button(
            text=f"{icon} {r.title[:40]}",
            callback_data=f"reminder:{r.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def _reminder_detail_keyboard(reminder_id: int) -> object:
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    builder.button(text="Удалить", callback_data=f"reminder_delete:{reminder_id}")
    builder.button(text="Назад", callback_data="reminders_back")
    builder.adjust(2)
    return builder.as_markup()


def _confirm_keyboard(action: str) -> object:
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    builder.button(text="Да, удалить", callback_data=f"confirm:{action}")
    builder.button(text="Отмена", callback_data="cancel_reminder")
    builder.adjust(2)
    return builder.as_markup()


@router.message(Command("reminders"))
async def cmd_reminders(message: Message, user: User, session: AsyncSession) -> None:
    repo = ReminderRepo(session)
    reminders = await repo.get_by_user(user.id)
    if not reminders:
        await message.answer("У вас нет активных напоминаний.")
        return
    await message.answer("Ваши напоминания:", reply_markup=_reminders_keyboard(reminders))


@router.callback_query(F.data.startswith("reminder:"))
async def cb_reminder_detail(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    reminder_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = ReminderRepo(session)
    reminder = await repo.get_by_id(reminder_id)
    if not reminder or reminder.user_id != user.id:
        await callback.answer("Напоминание не найдено.")
        return

    time_str = fmt_full(reminder.remind_at, user.timezone)
    repeat_str = f"\nПовтор: {reminder.repeat}" if reminder.repeat != "none" else ""
    event_str = "\n📅 Привязано к событию" if reminder.event_id else ""
    text = f"🔔 <b>{reminder.title}</b>\n{time_str}{repeat_str}{event_str}"

    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        parse_mode="HTML",
        reply_markup=_reminder_detail_keyboard(reminder.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("reminder_delete:"))
async def cb_reminder_delete_confirm(callback: CallbackQuery) -> None:
    reminder_id = callback.data.split(":")[1]  # type: ignore[union-attr]
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Удалить напоминание? Это действие нельзя отменить.",
        reply_markup=_confirm_keyboard(f"reminder_delete_confirmed:{reminder_id}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm:reminder_delete_confirmed:"))
async def cb_reminder_delete_confirmed(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    reminder_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    repo = ReminderRepo(session)
    reminder = await repo.get_by_id(reminder_id)
    if not reminder or reminder.user_id != user.id:
        await callback.answer("Напоминание не найдено.")
        return
    await repo.delete(reminder)
    await session.commit()
    await callback.answer("Напоминание удалено.")
    await callback.message.delete()  # type: ignore[union-attr]


@router.callback_query(F.data == "reminders_back")
async def cb_reminders_back(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    repo = ReminderRepo(session)
    reminders = await repo.get_by_user(user.id)
    if not reminders:
        await callback.message.edit_text("У вас нет активных напоминаний.")  # type: ignore[union-attr]
    else:
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Ваши напоминания:",
            reply_markup=_reminders_keyboard(reminders),
        )
    await callback.answer()


@router.callback_query(F.data == "cancel_reminder")
async def cb_cancel_reminder(callback: CallbackQuery) -> None:
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.answer("Отменено.")
