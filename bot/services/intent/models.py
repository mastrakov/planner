from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


def _to_utc_naive(v: datetime | None) -> datetime | None:
    """Convert aware datetime to UTC naive (strips tzinfo). Naive datetimes pass through."""
    if v is None:
        return None
    if v.tzinfo is not None:
        v = v.astimezone(timezone.utc).replace(tzinfo=None)
    return v


class CreateTaskIntent(BaseModel):
    type: Literal["create_task"]
    title: str
    list_name: str | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    due_date: datetime | None = None

    @field_validator("due_date", mode="after")
    @classmethod
    def normalize_due_date(cls, v: datetime | None) -> datetime | None:
        return _to_utc_naive(v)


class CreateEventIntent(BaseModel):
    type: Literal["create_event"]
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    # Multiple reminder offsets in minutes before the event start (e.g. [60, 10])
    reminder_minutes: list[int] = []

    @field_validator("starts_at", "ends_at", mode="after")
    @classmethod
    def normalize_datetimes(cls, v: datetime | None) -> datetime | None:
        return _to_utc_naive(v)


class CreateReminderIntent(BaseModel):
    type: Literal["create_reminder"]
    title: str
    remind_at: datetime
    repeat: Literal["none", "daily", "weekly", "monthly"] = "none"

    @field_validator("remind_at", mode="after")
    @classmethod
    def normalize_remind_at(cls, v: datetime | None) -> datetime | None:
        return _to_utc_naive(v)


class ListTasksIntent(BaseModel):
    type: Literal["list_tasks"]
    list_name: str | None = None
    filter: Literal["all", "today", "overdue", "high_priority"] = "all"


class CompleteTaskIntent(BaseModel):
    type: Literal["complete_task"]
    task_title: str


class DeleteTaskIntent(BaseModel):
    type: Literal["delete_task"]
    task_title: str


class UpdateTaskIntent(BaseModel):
    type: Literal["update_task"]
    task_title: str
    new_title: str | None = None
    new_priority: Literal["low", "medium", "high"] | None = None
    new_due_date: datetime | None = None
    new_list_name: str | None = None

    @field_validator("new_due_date", mode="after")
    @classmethod
    def normalize_new_due_date(cls, v: datetime | None) -> datetime | None:
        return _to_utc_naive(v)


class ListEventsIntent(BaseModel):
    type: Literal["list_events"]
    date_from: datetime | None = None
    date_to: datetime | None = None

    @field_validator("date_from", "date_to", mode="after")
    @classmethod
    def normalize_dates(cls, v: datetime | None) -> datetime | None:
        return _to_utc_naive(v)


class ListRemindersIntent(BaseModel):
    type: Literal["list_reminders"]


class DeleteReminderIntent(BaseModel):
    type: Literal["delete_reminder"]
    reminder_title: str


class UpdateReminderIntent(BaseModel):
    type: Literal["update_reminder"]
    reminder_title: str
    new_remind_at: datetime | None = None
    new_title: str | None = None

    @field_validator("new_remind_at", mode="after")
    @classmethod
    def normalize_new_remind_at(cls, v: datetime | None) -> datetime | None:
        return _to_utc_naive(v)


class GetBriefingIntent(BaseModel):
    type: Literal["get_briefing"]


class GetAnalyticsIntent(BaseModel):
    type: Literal["get_analytics"]
    period: Literal["week", "month"] = "week"


class AIChatIntent(BaseModel):
    type: Literal["ai_chat"]
    message: str


ParsedIntent = Annotated[
    CreateTaskIntent
    | CreateEventIntent
    | CreateReminderIntent
    | ListTasksIntent
    | CompleteTaskIntent
    | DeleteTaskIntent
    | UpdateTaskIntent
    | ListEventsIntent
    | ListRemindersIntent
    | DeleteReminderIntent
    | UpdateReminderIntent
    | GetBriefingIntent
    | GetAnalyticsIntent
    | AIChatIntent,
    Field(discriminator="type"),
]

DESTRUCTIVE_INTENT_TYPES = {"delete_task", "delete_reminder"}


class ParsedResponse(BaseModel):
    intents: list[ParsedIntent]
    confidence: float = Field(ge=0.0, le=1.0)
    clarification_needed: str | None = None
