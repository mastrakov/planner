from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class CreateTaskIntent(BaseModel):
    type: Literal["create_task"]
    title: str
    list_name: str | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    due_date: datetime | None = None


class CreateEventIntent(BaseModel):
    type: Literal["create_event"]
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    reminder_minutes: int | None = None


class CreateReminderIntent(BaseModel):
    type: Literal["create_reminder"]
    title: str
    remind_at: datetime
    repeat: Literal["none", "daily", "weekly", "monthly"] = "none"


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


class ListEventsIntent(BaseModel):
    type: Literal["list_events"]
    date_from: datetime | None = None
    date_to: datetime | None = None


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
    | GetBriefingIntent
    | GetAnalyticsIntent
    | AIChatIntent,
    Field(discriminator="type"),
]

DESTRUCTIVE_INTENT_TYPES = {"delete_task"}


class ParsedResponse(BaseModel):
    intents: list[ParsedIntent]
    confidence: float = Field(ge=0.0, le=1.0)
    clarification_needed: str | None = None
