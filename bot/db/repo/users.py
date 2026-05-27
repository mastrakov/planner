from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User


class UserRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def create(self, user_id: int, first_name: str, username: str | None = None) -> User:
        user = User(id=user_id, first_name=first_name, username=username)
        self._session.add(user)
        await self._session.flush()
        return user

    async def update(self, user: User, **kwargs: object) -> User:
        for key, value in kwargs.items():
            setattr(user, key, value)
        await self._session.flush()
        return user

    async def get_all_active(self) -> list[User]:
        result = await self._session.execute(select(User).where(User.is_active.is_(True)))
        return list(result.scalars().all())
