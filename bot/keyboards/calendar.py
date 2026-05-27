from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.models import CalendarEvent


def events_list_keyboard(events: list[CalendarEvent]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ev in events:
        time_str = ev.starts_at.strftime("%d.%m %H:%M")
        builder.button(
            text=f"📅 {time_str} — {ev.title[:35]}",
            callback_data=f"event:{ev.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def event_detail_keyboard(event: CalendarEvent) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Удалить событие", callback_data=f"event_delete:{event.id}")
    builder.button(text="Назад", callback_data="calendar_back")
    builder.adjust(2)
    return builder.as_markup()
