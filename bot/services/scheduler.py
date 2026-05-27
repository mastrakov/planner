import logging
from datetime import time

import pytz
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.db.base import async_session_factory
from bot.db.repo.users import UserRepo
from bot.utils.dt import now_utc

logger = logging.getLogger(__name__)


async def send_morning_briefings(bot: Bot) -> None:
    from bot.services.briefing import BriefingService

    async with async_session_factory() as session:
        repo = UserRepo(session)
        users = await repo.get_all_active()

        _now_utc = now_utc()
        for user in users:
            try:
                tz = pytz.timezone(user.timezone)
                local_now = pytz.utc.localize(_now_utc).astimezone(tz)
                briefing_time: time = user.briefing_time
                if local_now.hour == briefing_time.hour and local_now.minute < 5:
                    service = BriefingService(session)
                    text = await service.build_morning_briefing(user)
                    await bot.send_message(user.id, text, parse_mode="HTML")
                    # On Mondays also send weekly plan
                    if local_now.weekday() == 0:
                        plan = await service.build_weekly_plan(user)
                        await bot.send_message(user.id, plan, parse_mode="HTML")
            except Exception:
                logger.exception("Error sending morning briefing to user %d", user.id)


async def send_weekly_summary(bot: Bot) -> None:
    """Send weekly summary on Sunday at 20:00 in each user's local timezone."""
    from bot.services.analytics import AnalyticsService

    async with async_session_factory() as session:
        repo = UserRepo(session)
        users = await repo.get_all_active()

        _now_utc = now_utc()
        for user in users:
            try:
                tz = pytz.timezone(user.timezone)
                local_now = pytz.utc.localize(_now_utc).astimezone(tz)
                # Sunday == 6 in Python weekday(); send at 20:00 local time
                if local_now.weekday() != 6 or local_now.hour != 20 or local_now.minute >= 5:
                    continue
                service = AnalyticsService(session)
                text = await service.get_weekly_stats(user)
                await bot.send_message(user.id, text, parse_mode="HTML")
            except Exception:
                logger.exception("Error sending weekly summary to user %d", user.id)


async def check_reminders(bot: Bot) -> None:
    from bot.services.reminders import ReminderService

    async with async_session_factory() as session:
        service = ReminderService(session)
        await service.check_and_send(bot)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        send_morning_briefings,
        "cron",
        minute=0,  # every hour at :00
        kwargs={"bot": bot},
        id="morning_briefings",
        replace_existing=True,
    )
    scheduler.add_job(
        send_weekly_summary,
        "cron",
        minute=0,  # every hour at :00 — timezone check is done inside the job
        kwargs={"bot": bot},
        id="weekly_summary",
        replace_existing=True,
    )
    scheduler.add_job(
        check_reminders,
        "interval",
        minutes=1,
        kwargs={"bot": bot},
        id="check_reminders",
        replace_existing=True,
    )

    return scheduler
