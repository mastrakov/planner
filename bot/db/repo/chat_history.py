from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import ChatHistory, ChatRole


class ChatHistoryRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user_id: int, role: str, content: str) -> ChatHistory:
        entry = ChatHistory(user_id=user_id, role=role, content=content)
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def get_recent(self, user_id: int, limit: int = 10) -> list[ChatHistory]:
        result = await self._session.execute(
            select(ChatHistory)
            .where(ChatHistory.user_id == user_id)
            .order_by(ChatHistory.created_at.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()
        return rows

    async def clear(self, user_id: int) -> None:
        from sqlalchemy import delete

        await self._session.execute(delete(ChatHistory).where(ChatHistory.user_id == user_id))
        await self._session.flush()
