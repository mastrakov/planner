from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from bot.config import settings


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not settings.allowed_user_ids:
            return await handler(event, data)

        update: Update | None = data.get("event_update")
        user_id: int | None = None

        if update and update.effective_user:
            user_id = update.effective_user.id

        if user_id is None:
            # non-user updates (e.g. channel posts) — skip silently
            return await handler(event, data)

        if user_id not in settings.allowed_user_ids:
            from aiogram.types import Message

            if isinstance(event, Message):
                await event.answer("У вас нет доступа к этому боту.")
            return None

        return await handler(event, data)
