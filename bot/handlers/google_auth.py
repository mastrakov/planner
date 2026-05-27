from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.db.models import IntegrationType, User
from bot.db.repo.integrations import IntegrationRepo
from bot.services.integrations.google.auth import exchange_code, get_authorization_url

router = Router()


@router.message(Command("connect_google"))
async def cmd_connect_google(message: Message, user: User) -> None:
    if not settings.google_client_id:
        await message.answer("Google Calendar интеграция не настроена.")
        return

    # Use user_id as state to verify callback
    state = str(user.id)
    url = get_authorization_url(state)
    await message.answer(
        f"Для подключения Google Calendar перейдите по ссылке:\n{url}\n\n"
        "После авторизации вы будете перенаправлены обратно."
    )


@router.message(Command("disconnect_google"))
async def cmd_disconnect_google(message: Message, user: User, session: AsyncSession) -> None:
    repo = IntegrationRepo(session)
    integration = await repo.get_by_user_and_type(user.id, IntegrationType.CALENDAR, "google")
    if not integration:
        await message.answer("Google Calendar не подключён.")
        return
    await repo.delete(integration)
    await message.answer("Google Calendar отключён.")


async def handle_oauth_callback(code: str, state: str, session: AsyncSession) -> bool:
    """Called by the webhook handler when Google redirects back with an auth code."""
    try:
        user_id = int(state)
    except ValueError:
        return False

    credentials = exchange_code(code)

    repo = IntegrationRepo(session)
    integration = await repo.upsert(user_id, IntegrationType.CALENDAR, "google", is_active=True)
    await repo.save_credentials(integration, credentials)
    await session.commit()
    return True
