import asyncio
import logging
import os
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from aiohttp import web

from bot.config import settings
from bot.handlers import get_main_router
from bot.middlewares import AuthMiddleware, UserMiddleware
from bot.services.integrations.google.calendar import GoogleCalendarProvider
from bot.services.integrations.registry import registry
from bot.services.scheduler import setup_scheduler

_log_level = logging.DEBUG if os.getenv("ENV", "local") == "local" else logging.INFO
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Keep noisy libs at INFO even in local mode
logging.getLogger("aiogram").setLevel(logging.INFO)
logging.getLogger("aiohttp").setLevel(logging.INFO)
logging.getLogger("sqlalchemy").setLevel(logging.INFO)
logger = logging.getLogger(__name__)


def build_bot() -> Bot:
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.outer_middleware(AuthMiddleware())
    dp.message.outer_middleware(UserMiddleware())
    dp.callback_query.outer_middleware(UserMiddleware())

    dp.include_router(get_main_router())
    return dp


def _register_integrations() -> None:
    from bot.db.base import async_session_factory
    from bot.db.models import IntegrationType
    from bot.db.repo.integrations import IntegrationRepo

    async def _get_google_creds(user_id: int) -> dict[str, object]:
        """Open a short-lived session to fetch credentials for the given user."""
        async with async_session_factory() as session:
            repo = IntegrationRepo(session)
            integration = await repo.get_by_user_and_type(user_id, IntegrationType.CALENDAR, "google")
            if not integration:
                raise ValueError(f"No Google Calendar integration for user {user_id}")
            creds = await repo.get_credentials(integration)
            if not creds:
                raise ValueError(f"No credentials for user {user_id}")
            return creds

    registry.register_calendar("google", GoogleCalendarProvider(_get_google_creds))


async def run_polling() -> None:
    bot = build_bot()
    dp = build_dispatcher()
    _register_integrations()
    scheduler = setup_scheduler(bot)

    logger.info("Starting bot in polling mode")
    scheduler.start()
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


async def run_webhook() -> None:
    bot = build_bot()
    dp = build_dispatcher()
    _register_integrations()
    scheduler = setup_scheduler(bot)

    await bot.set_webhook(
        url=settings.webhook_url,
        secret_token=settings.webhook_secret,
        allowed_updates=dp.resolve_used_update_types(),
    )

    app = web.Application()

    async def handle_webhook(request: web.Request) -> web.Response:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if secret != settings.webhook_secret:
            return web.Response(status=403)
        data = await request.json()
        update = Update.model_validate(data)
        await dp.feed_update(bot, update)
        return web.Response()

    async def handle_google_callback(request: web.Request) -> web.Response:
        code = request.rel_url.query.get("code", "")
        state = request.rel_url.query.get("state", "")
        if not code:
            return web.Response(text="Missing code", status=400)

        from bot.db.base import async_session_factory
        from bot.handlers.google_auth import handle_oauth_callback

        async with async_session_factory() as session:
            success = await handle_oauth_callback(code, state, session)

        if success:
            try:
                await bot.send_message(int(state), "Google Calendar успешно подключён!")
            except Exception:
                pass
            return web.Response(text="Google Calendar подключён. Можете закрыть эту страницу.")
        return web.Response(text="Ошибка авторизации", status=400)

    app.router.add_post("/webhook/" + settings.webhook_secret, handle_webhook)
    app.router.add_get("/oauth/google/callback", handle_google_callback)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)

    logger.info("Starting bot in webhook mode on :8080")
    scheduler.start()
    try:
        await site.start()
        await asyncio.Event().wait()  # run forever
    finally:
        scheduler.shutdown(wait=False)
        await runner.cleanup()
        await bot.session.close()


async def main() -> None:
    if settings.is_local:
        await run_polling()
    else:
        await run_webhook()


if __name__ == "__main__":
    from bot.db.base import run_migrations
    run_migrations()
    asyncio.run(main())
