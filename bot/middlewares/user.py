from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.db.base import async_session_factory
from bot.db.repo.users import UserRepo


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from aiogram.types import Update

        update: Update | None = data.get("event_update")
        tg_user = update.effective_user if update else None

        if tg_user is None:
            return await handler(event, data)

        async with async_session_factory() as session:
            repo = UserRepo(session)
            user = await repo.get_by_id(tg_user.id)
            if user is None:
                user = await repo.create(
                    user_id=tg_user.id,
                    first_name=tg_user.first_name,
                    username=tg_user.username,
                )
                await session.commit()

            data["user"] = user
            data["session"] = session
            result = await handler(event, data)
            await session.commit()
            return result
