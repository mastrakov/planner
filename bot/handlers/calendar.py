from datetime import timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repo.calendar import CalendarRepo
from bot.db.repo.integrations import IntegrationRepo
from bot.keyboards.calendar import event_detail_keyboard, events_list_keyboard
from bot.services.integrations.registry import registry
from bot.utils.dt import fmt_full, fmt_time, now_utc

router = Router()


@router.message(Command("calendar"))
async def cmd_calendar(message: Message, user: User, session: AsyncSession) -> None:
    repo = CalendarRepo(session)
    now = now_utc()
    week_ahead = now + timedelta(days=7)
    events = await repo.get_for_date_range(user.id, now, week_ahead)
    if not events:
        await message.answer("Событий на ближайшие 7 дней нет.")
        return
    await message.answer("Ближайшие события:", reply_markup=events_list_keyboard(events, user.timezone))


@router.callback_query(F.data.startswith("event:"))
async def cb_event_detail(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    event_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = CalendarRepo(session)
    event = await repo.get_by_id(event_id)
    if not event or event.user_id != user.id:
        await callback.answer("Событие не найдено.")
        return

    time_str = fmt_full(event.starts_at, user.timezone)
    end_str = f" — {fmt_time(event.ends_at, user.timezone)}" if event.ends_at else ""
    reminder_str = f"\nНапоминание: за {event.reminder_minutes} мин." if event.reminder_minutes else ""
    text = f"<b>{event.title}</b>\n{time_str}{end_str}{reminder_str}"

    await callback.message.edit_text(  # type: ignore[union-attr]
        text, parse_mode="HTML", reply_markup=event_detail_keyboard(event)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("event_delete:"))
async def cb_event_delete(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    event_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = CalendarRepo(session)
    event = await repo.get_by_id(event_id)
    if not event or event.user_id != user.id:
        await callback.answer("Событие не найдено.")
        return

    if event.external_id:
        integration_repo = IntegrationRepo(session)
        active = await integration_repo.get_active_calendar_integration(user.id)
        if active and registry.has_calendar(active.provider_name):
            provider = registry.get_calendar(active.provider_name)
            try:
                await provider.delete_event(user.id, event.external_id)
            except Exception:
                pass

    await repo.delete(event)
    await callback.answer("Событие удалено.")
    await callback.message.delete()  # type: ignore[union-attr]


@router.callback_query(F.data == "calendar_back")
async def cb_calendar_back(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    repo = CalendarRepo(session)
    now = now_utc()
    week_ahead = now + timedelta(days=7)
    events = await repo.get_for_date_range(user.id, now, week_ahead)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Ближайшие события:", reply_markup=events_list_keyboard(events, user.timezone)
    )
    await callback.answer()
