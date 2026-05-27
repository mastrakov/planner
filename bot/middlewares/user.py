import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TelegramUser

from bot.db.base import async_session_factory
from bot.db.repo.users import UserRepo

logger = logging.getLogger(__name__)


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TelegramUser | None = data.get("event_from_user")

        if tg_user is None:
            logger.debug("UserMiddleware: no event_from_user, skipping")
            return await handler(event, data)

        logger.debug("UserMiddleware: resolving user id=%d (@%s)", tg_user.id, tg_user.username)

        async with async_session_factory() as session:
            repo = UserRepo(session)
            user = await repo.get_by_id(tg_user.id)
            if user is None:
                logger.debug("UserMiddleware: new user id=%d, creating", tg_user.id)
                user = await repo.create(
                    user_id=tg_user.id,
                    first_name=tg_user.first_name,
                    username=tg_user.username,
                )
                await session.commit()
                logger.debug("UserMiddleware: created user id=%d", tg_user.id)
            else:
                logger.debug("UserMiddleware: found existing user id=%d", tg_user.id)

            data["user"] = user
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            return result
