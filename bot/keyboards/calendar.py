from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.models import CalendarEvent
from bot.utils.dt import fmt_full


def events_list_keyboard(events: list[CalendarEvent], tz_name: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ev in events:
        time_str = fmt_full(ev.starts_at, tz_name)
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


def morning_event_reminder_keyboard(event_id: int) -> InlineKeyboardMarkup:
    """Per-event reminder buttons in the morning briefing."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔔 за 15 мин", callback_data=f"remind_event:15:{event_id}")
    builder.button(text="Другое время", callback_data=f"remind_event_custom:{event_id}")
    builder.adjust(2)
    return builder.as_markup()


def morning_task_reminder_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Reminder button for today-deadline task without a reminder."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔔 Напомнить в 09:00", callback_data=f"remind_task_morning:{task_id}")
    builder.adjust(1)
    return builder.as_markup()


def weekly_event_reminder_keyboard(event_id: int) -> InlineKeyboardMarkup:
    """Per-event reminder buttons in the weekly briefing."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔔 за 1ч", callback_data=f"remind_event:60:{event_id}")
    builder.button(text="🔔 за день", callback_data=f"remind_event:1440:{event_id}")
    builder.adjust(2)
    return builder.as_markup()


def remind_all_events_keyboard() -> InlineKeyboardMarkup:
    """Single button to set reminders for all weekly events at once."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📌 Поставить напоминания для всех событий", callback_data="remind_all_week_events")
    builder.adjust(1)
    return builder.as_markup()
