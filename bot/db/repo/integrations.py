import json

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.db.models import IntegrationType, UserIntegration


def _fernet() -> Fernet:
    return Fernet(settings.encryption_key.encode())


class IntegrationRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_and_type(
        self,
        user_id: int,
        integration_type: str,
        provider_name: str,
    ) -> UserIntegration | None:
        result = await self._session.execute(
            select(UserIntegration)
            .where(UserIntegration.user_id == user_id)
            .where(UserIntegration.integration_type == integration_type)
            .where(UserIntegration.provider_name == provider_name)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: int,
        integration_type: str,
        provider_name: str,
        is_active: bool = True,
    ) -> UserIntegration:
        existing = await self.get_by_user_and_type(user_id, integration_type, provider_name)
        if existing:
            existing.is_active = is_active
            await self._session.flush()
            return existing
        integration = UserIntegration(
            user_id=user_id,
            integration_type=integration_type,
            provider_name=provider_name,
            is_active=is_active,
        )
        self._session.add(integration)
        await self._session.flush()
        return integration

    async def delete(self, integration: UserIntegration) -> None:
        await self._session.delete(integration)
        await self._session.flush()

    async def get_credentials(self, integration: UserIntegration) -> dict[str, object] | None:
        if not integration.credentials:
            return None
        decrypted = _fernet().decrypt(integration.credentials.encode()).decode()
        return dict(json.loads(decrypted))  # type: ignore[arg-type]

    async def save_credentials(self, integration: UserIntegration, credentials: dict[str, object]) -> None:
        raw = json.dumps(credentials)
        integration.credentials = _fernet().encrypt(raw.encode()).decode()
        await self._session.flush()

    async def get_all_by_user(self, user_id: int) -> list[UserIntegration]:
        result = await self._session.execute(
            select(UserIntegration).where(UserIntegration.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_active_calendar_integration(self, user_id: int) -> UserIntegration | None:
        result = await self._session.execute(
            select(UserIntegration)
            .where(UserIntegration.user_id == user_id)
            .where(UserIntegration.integration_type == IntegrationType.CALENDAR)
            .where(UserIntegration.is_active.is_(True))
        )
        return result.scalar_one_or_none()
