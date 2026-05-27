from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.models import User


def settings_keyboard(user: User, google_connected: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"Время брифинга: {user.briefing_time.strftime('%H:%M')}", callback_data="settings_briefing_time")
    builder.button(text=f"Часовой пояс: {user.timezone}", callback_data="settings_timezone")
    model_label = "Claude (claude-sonnet-4-6)" if user.ai_model == "claude" else "GPT-4o"
    builder.button(text=f"AI модель: {model_label}", callback_data="settings_model")
    if google_connected:
        builder.button(text="Google Calendar: подключён ✅", callback_data="settings_google_disconnect")
    else:
        builder.button(text="Подключить Google Calendar", callback_data="settings_google_connect")
    builder.adjust(1)
    return builder.as_markup()


def model_choice_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Claude (claude-sonnet-4-6)", callback_data="model_set:claude")
    builder.button(text="GPT-4o", callback_data="model_set:gpt4o")
    builder.button(text="Назад", callback_data="settings_back")
    builder.adjust(1)
    return builder.as_markup()
