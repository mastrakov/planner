from aiogram import Router

from bot.handlers import ai_chat, analytics, calendar, google_auth, settings, start, tasks, voice


def get_main_router() -> Router:
    router = Router()
    # Order matters: more specific handlers before catch-all
    router.include_router(start.router)
    router.include_router(tasks.router)
    router.include_router(calendar.router)
    router.include_router(settings.router)
    router.include_router(analytics.router)
    router.include_router(google_auth.router)
    router.include_router(voice.router)
    router.include_router(ai_chat.router)  # catch-all last
    return router


__all__ = ["get_main_router"]
