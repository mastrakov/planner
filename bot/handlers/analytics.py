from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.services.analytics import AnalyticsService
from bot.services.briefing import BriefingService

router = Router()


@router.message(Command("analytics"))
async def cmd_analytics(message: Message, user: User, session: AsyncSession) -> None:
    service = AnalyticsService(session)
    text = await service.get_weekly_stats(user)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("weekly"))
async def cmd_weekly(message: Message, user: User, session: AsyncSession) -> None:
    service = AnalyticsService(session)
    text = await service.get_weekly_stats(user)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("morning"))
async def cmd_morning(message: Message, user: User, session: AsyncSession) -> None:
    service = BriefingService(session)
    text = await service.build_morning_briefing(user)
    await message.answer(text, parse_mode="HTML")
