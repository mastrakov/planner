from aiogram import Router

from bot.handlers import (
    ai_chat,
    analytics,
    calendar,
    confirm_intent,
    google_auth,
    lists_fsm,
    reminders,
    settings,
    start,
    tasks,
    voice,
)


def get_main_router() -> Router:
    router = Router()
    # Order matters: more specific handlers before catch-all
    router.include_router(start.router)
    router.include_router(tasks.router)
    router.include_router(lists_fsm.router)       # FSM: create/rename lists
    router.include_router(confirm_intent.router)  # FSM: confirm low-confidence intents
    router.include_router(calendar.router)
    router.include_router(reminders.router)
    router.include_router(settings.router)
    router.include_router(analytics.router)
    router.include_router(google_auth.router)
    router.include_router(voice.router)
    router.include_router(ai_chat.router)  # catch-all last
    return router


__all__ = ["get_main_router"]
