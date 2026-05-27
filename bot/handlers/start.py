from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.db.models import User
from bot.services.tasks import TaskService

router = Router()

HELP_TEXT = """
<b>Команды бота:</b>

<b>Задачи</b>
/tasks — все активные задачи
/lists — управление списками задач

<b>Календарь</b>
/calendar — события на ближайшие 7 дней

<b>Брифинг и аналитика</b>
/morning — утренний брифинг
/weekly — недельное саммари

<b>Аналитика</b>
/analytics — статистика за неделю

<b>Настройки</b>
/settings — настройки бота
/model — выбор AI модели

<b>Google Calendar</b>
/connect_google — подключить Google Calendar
/disconnect_google — отключить Google Calendar

<b>Другое</b>
/help — эта справка
/cancel — отмена текущего действия

Также вы можете отправить голосовое сообщение или просто написать что хотите сделать.
"""


@router.message(Command("start"))
async def cmd_start(message: Message, user: User, session: object) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    service = TaskService(session)
    await service.create_default_lists(user.id)

    await message.answer(
        f"Привет, {user.first_name}! Я твой персональный ассистент.\n\n"
        "Напиши мне что сделать или используй команды ниже.\n\n"
        + HELP_TEXT,
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")
