from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AIModel, User
from bot.db.repo.integrations import IntegrationRepo
from bot.db.repo.users import UserRepo
from bot.keyboards.settings import model_choice_keyboard, settings_keyboard, timezone_keyboard

router = Router()


class SettingsForm(StatesGroup):
    waiting_briefing_time = State()
    waiting_timezone = State()


@router.message(Command("settings"))
async def cmd_settings(message: Message, user: User, session: AsyncSession) -> None:
    repo = IntegrationRepo(session)
    google = await repo.get_active_calendar_integration(user.id)
    await message.answer(
        "<b>Настройки</b>",
        parse_mode="HTML",
        reply_markup=settings_keyboard(user, google is not None),
    )


@router.message(Command("model"))
async def cmd_model(message: Message) -> None:
    await message.answer("Выберите AI модель:", reply_markup=model_choice_keyboard())


@router.callback_query(F.data == "settings_model")
async def cb_settings_model(callback: CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Выберите AI модель:", reply_markup=model_choice_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("model_set:"))
async def cb_model_set(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    model_value = callback.data.split(":")[1]  # type: ignore[union-attr]
    if model_value not in ("claude", "gpt4o"):
        await callback.answer("Неизвестная модель.")
        return
    repo = UserRepo(session)
    await repo.update(user, ai_model=model_value)
    label = "Claude (claude-sonnet-4-6)" if model_value == "claude" else "GPT-4o"
    await callback.answer(f"Модель изменена: {label}")
    await callback.message.delete()  # type: ignore[union-attr]


@router.callback_query(F.data == "settings_briefing_time")
async def cb_settings_briefing_time(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsForm.waiting_briefing_time)
    await callback.message.answer(  # type: ignore[union-attr]
        "Введите время утреннего брифинга в формате HH:MM (например, 08:00):"
    )
    await callback.answer()


@router.message(SettingsForm.waiting_briefing_time)
async def process_briefing_time(message: Message, user: User, session: AsyncSession, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        from datetime import time

        parts = text.split(":")
        briefing_time = time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        await message.answer("Неверный формат. Введите время в формате HH:MM.")
        return

    repo = UserRepo(session)
    await repo.update(user, briefing_time=briefing_time)
    await state.clear()
    await message.answer(f"Время брифинга установлено: {text}")


@router.callback_query(F.data.startswith("tz_set:"))
async def cb_tz_set_settings(callback: CallbackQuery, user: User, session: AsyncSession, state: FSMContext) -> None:
    tz_name = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    repo = UserRepo(session)
    await repo.update(user, timezone=tz_name)
    await state.clear()
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ Часовой пояс установлен: <b>{tz_name}</b>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "settings_timezone")
async def cb_settings_timezone(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsForm.waiting_timezone)
    await callback.message.answer(  # type: ignore[union-attr]
        "Выберите часовой пояс или введите вручную (например, <code>Asia/Novosibirsk</code>):",
        parse_mode="HTML",
        reply_markup=timezone_keyboard(),
    )
    await callback.answer()


@router.message(SettingsForm.waiting_timezone)
async def process_timezone(message: Message, user: User, session: AsyncSession, state: FSMContext) -> None:
    tz_name = (message.text or "").strip()
    try:
        import pytz

        pytz.timezone(tz_name)
    except Exception:
        await message.answer("Неверный часовой пояс. Попробуйте ещё раз (например, <code>Europe/Moscow</code>).", parse_mode="HTML")
        return

    repo = UserRepo(session)
    await repo.update(user, timezone=tz_name)
    await state.clear()
    await message.answer(f"✅ Часовой пояс установлен: <b>{tz_name}</b>", parse_mode="HTML")


@router.callback_query(F.data == "settings_back")
async def cb_settings_back(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    repo = IntegrationRepo(session)
    google = await repo.get_active_calendar_integration(user.id)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "<b>Настройки</b>",
        parse_mode="HTML",
        reply_markup=settings_keyboard(user, google is not None),
    )
    await callback.answer()
