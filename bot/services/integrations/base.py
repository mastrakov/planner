from abc import ABC, abstractmethod
from datetime import date, datetime

from pydantic import BaseModel


class CalendarEventDTO(BaseModel):
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    external_id: str | None = None


class CalendarProvider(ABC):
    @abstractmethod
    async def create_event(self, user_id: int, event: CalendarEventDTO) -> str:
        """Create event and return its external id."""

    @abstractmethod
    async def list_events(
        self,
        user_id: int,
        date_from: date,
        date_to: date,
    ) -> list[CalendarEventDTO]: ...

    @abstractmethod
    async def delete_event(self, user_id: int, event_id: str) -> None: ...

    @abstractmethod
    async def update_event(
        self,
        user_id: int,
        event_id: str,
        event: CalendarEventDTO,
    ) -> None: ...
