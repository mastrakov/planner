"""FSM handlers for creating and renaming task lists via inline buttons."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repo.tasks import TaskRepo
from bot.keyboards.tasks import list_detail_keyboard, lists_keyboard

logger = logging.getLogger(__name__)

router = Router()

# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

EMOJI_CHOICES = ["📋", "🎯", "💼", "🏠", "📚", "🛒", "💡", "🔧", "❤️", "⭐"]
DEFAULT_EMOJI = "📋"


class CreateListStates(StatesGroup):
    waiting_for_name = State()


class RenameListStates(StatesGroup):
    waiting_for_new_name = State()


# ---------------------------------------------------------------------------
# Create list flow
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "list_create")
async def cb_list_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreateListStates.waiting_for_name)
    await callback.message.answer(  # type: ignore[union-attr]
        "Введите название нового списка:\n"
        "(Можно добавить эмодзи в начале, например: <b>🎯 Работа</b>)",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CreateListStates.waiting_for_name)
async def fsm_create_list_name(message: Message, state: FSMContext, user: User, session: AsyncSession) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Название не может быть пустым. Введите название списка:")
        return

    # Extract leading emoji if present
    emoji = DEFAULT_EMOJI
    name = text
    if text and _is_emoji(text[0]):
        parts = text.split(None, 1)
        emoji = parts[0]
        name = parts[1].strip() if len(parts) > 1 else ""

    if not name:
        await message.answer("Введите название (можно без эмодзи, например: <b>Работа</b>):", parse_mode="HTML")
        return

    repo = TaskRepo(session)
    await repo.create_list(user_id=user.id, name=name, emoji=emoji)
    await state.clear()

    lists = await repo.get_lists_by_user(user.id)
    all_tasks = await repo.get_by_user(user.id)
    task_counts = {lst.id: sum(1 for t in all_tasks if t.list_id == lst.id) for lst in lists}

    await message.answer(
        f"Список <b>{emoji} {name}</b> создан! ✅",
        parse_mode="HTML",
        reply_markup=lists_keyboard(lists, task_counts),
    )


# ---------------------------------------------------------------------------
# Rename list flow
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("list_rename:"))
async def cb_list_rename(callback: CallbackQuery, state: FSMContext, user: User, session: AsyncSession) -> None:
    list_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = TaskRepo(session)
    lst = await repo.get_list_by_id(list_id)
    if not lst or lst.user_id != user.id:
        await callback.answer("Список не найден.")
        return

    await state.update_data(list_id=list_id)
    await state.set_state(RenameListStates.waiting_for_new_name)
    await callback.message.answer(  # type: ignore[union-attr]
        f"Текущее название: <b>{lst.emoji} {lst.name}</b>\n"
        "Введите новое название (можно изменить эмодзи, добавив его в начале):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(RenameListStates.waiting_for_new_name)
async def fsm_rename_list_name(message: Message, state: FSMContext, user: User, session: AsyncSession) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Название не может быть пустым. Введите новое название:")
        return

    data = await state.get_data()
    list_id: int = data["list_id"]

    repo = TaskRepo(session)
    lst = await repo.get_list_by_id(list_id)
    if not lst or lst.user_id != user.id:
        await state.clear()
        await message.answer("Список не найден.")
        return

    # Extract leading emoji if present
    new_emoji = lst.emoji  # keep existing if not provided
    new_name = text
    if text and _is_emoji(text[0]):
        parts = text.split(None, 1)
        new_emoji = parts[0]
        new_name = parts[1].strip() if len(parts) > 1 else ""

    if not new_name:
        await message.answer("Введите название (можно без эмодзи):")
        return

    lst.name = new_name
    lst.emoji = new_emoji
    await state.clear()

    await message.answer(
        f"Список переименован: <b>{new_emoji} {new_name}</b> ✅",
        parse_mode="HTML",
        reply_markup=list_detail_keyboard(lst),
    )


# ---------------------------------------------------------------------------
# Cancel FSM on /cancel command (already in ai_chat.py but also handle here)
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "fsm_cancel")
async def cb_fsm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.answer("Отменено.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_emoji(char: str) -> bool:
    """Rough check: character is outside ASCII printable range."""
    return ord(char) > 127
