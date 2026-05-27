from datetime import datetime, timedelta

import pytz
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.services.analytics import AnalyticsService
from bot.services.briefing import BriefingService

router = Router()


def _analytics_period_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 За неделю", callback_data="analytics:week")
    builder.button(text="📊 За месяц", callback_data="analytics:month")
    builder.adjust(2)
    return builder.as_markup()


def _morning_nav_keyboard() -> InlineKeyboardMarkup:
    """Quick navigation from morning briefing."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 На завтра", callback_data="briefing:day:1")
    builder.button(text="📆 На неделю", callback_data="briefing:week:0")
    builder.adjust(2)
    return builder.as_markup()


@router.message(Command("analytics"))
async def cmd_analytics(message: Message, user: User, session: AsyncSession) -> None:
    service = AnalyticsService(session)
    text = await service.get_weekly_stats(user)
    await message.answer(text, parse_mode="HTML", reply_markup=_analytics_period_keyboard())


@router.callback_query(F.data.startswith("analytics:"))
async def cb_analytics_period(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    period = callback.data.split(":")[1]  # type: ignore[union-attr]
    service = AnalyticsService(session)
    if period == "month":
        text = await service.get_monthly_stats(user)
    else:
        text = await service.get_weekly_stats(user)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_analytics_period_keyboard())  # type: ignore[union-attr]
    await callback.answer()


@router.message(Command("weekly"))
async def cmd_weekly(message: Message, user: User, session: AsyncSession) -> None:
    service = AnalyticsService(session)
    text = await service.get_weekly_stats(user)
    await message.answer(text, parse_mode="HTML", reply_markup=_analytics_period_keyboard())


@router.message(Command("morning"))
async def cmd_morning(message: Message, user: User, session: AsyncSession) -> None:
    service = BriefingService(session)
    result = await service.build_morning(user)
    await message.answer(result.text, parse_mode="HTML", reply_markup=_morning_nav_keyboard())


@router.callback_query(F.data.startswith("briefing:"))
async def cb_briefing(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    """briefing:day:<offset_days>  or  briefing:week:<offset_weeks>"""
    parts = callback.data.split(":")  # type: ignore[union-attr]
    scope, offset = parts[1], int(parts[2])

    tz = pytz.timezone(user.timezone)
    now_local = datetime.now(tz).replace(tzinfo=None)
    today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

    service = BriefingService(session)

    if scope == "week":
        monday = today_local - timedelta(days=today_local.weekday()) + timedelta(weeks=offset)
        result = await service.build_for_week(user, week_start_local=monday)
    else:
        target = today_local + timedelta(days=offset)
        if offset == 0:
            result = await service.build_morning(user)
        else:
            result = await service.build_for_date(user, target_local=target)

    await callback.message.answer(result.text, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()
