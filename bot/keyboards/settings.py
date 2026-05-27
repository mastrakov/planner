from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.models import User

# Popular timezones shown as buttons during onboarding and in settings
POPULAR_TIMEZONES = [
    ("🇬🇧 Лондон (UTC+0/+1)", "Europe/London"),
    ("🇵🇹 Лиссабон (UTC+0/+1)", "Europe/Lisbon"),
    ("🇫🇷 Париж (UTC+1/+2)", "Europe/Paris"),
    ("🇩🇪 Берлин (UTC+1/+2)", "Europe/Berlin"),
    ("🇪🇸 Мадрид (UTC+1/+2)", "Europe/Madrid"),
    ("🇮🇹 Рим (UTC+1/+2)", "Europe/Rome"),
    ("🇵🇱 Варшава (UTC+1/+2)", "Europe/Warsaw"),
    ("🇳🇱 Амстердам (UTC+1/+2)", "Europe/Amsterdam"),
    ("🇨🇭 Цюрих (UTC+1/+2)", "Europe/Zurich"),
    ("🇸🇪 Стокгольм (UTC+1/+2)", "Europe/Stockholm"),
    ("🇫🇮 Хельсинки (UTC+2/+3)", "Europe/Helsinki"),
    ("🇷🇴 Бухарест (UTC+2/+3)", "Europe/Bucharest"),
    ("🇺🇦 Киев (UTC+2/+3)", "Europe/Kyiv"),
    ("🇧🇾 Минск (UTC+3)", "Europe/Minsk"),
    ("🇷🇺 Москва (UTC+3)", "Europe/Moscow"),
    ("🇷🇺 Калининград (UTC+2)", "Europe/Kaliningrad"),
]


def timezone_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, tz in POPULAR_TIMEZONES:
        builder.button(text=label, callback_data=f"tz_set:{tz}")
    builder.adjust(2)
    return builder.as_markup()


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
