from datetime import datetime, time
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AIModel(StrEnum):
    CLAUDE = "claude"
    GPT4O = "gpt4o"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RepeatType(StrEnum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class TaskEventType(StrEnum):
    CREATED = "created"
    COMPLETED = "completed"
    POSTPONED = "postponed"
    DELETED = "deleted"
    UPDATED = "updated"


class IntegrationType(StrEnum):
    CALENDAR = "calendar"
    TASKS = "tasks"
    STORAGE = "storage"


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram user_id
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    ai_model: Mapped[str] = mapped_column(Enum(AIModel), default=AIModel.CLAUDE)
    briefing_time: Mapped[time] = mapped_column(Time, default=time(8, 0))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    task_lists: Mapped[list["TaskList"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    calendar_events: Mapped[list["CalendarEvent"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    integrations: Mapped[list["UserIntegration"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    chat_history: Mapped[list["ChatHistory"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class TaskList(Base):
    __tablename__ = "task_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128))
    emoji: Mapped[str] = mapped_column(String(8), default="📋")
    color: Mapped[str] = mapped_column(String(16), default="#5865F2")
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="task_lists")
    tasks: Mapped[list["Task"]] = relationship(back_populates="task_list", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(Integer, ForeignKey("task_lists.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(512))
    priority: Mapped[str] = mapped_column(Enum(Priority), default=Priority.MEDIUM)
    due_date: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="tasks")
    task_list: Mapped["TaskList"] = relationship(back_populates="tasks")
    events: Mapped[list["TaskEvent"]] = relationship(back_populates="task", cascade="all, delete-orphan")

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None


class TaskEvent(Base):
    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(Enum(TaskEventType))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    task: Mapped["Task"] = relationship(back_populates="events")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(512))
    remind_at: Mapped[datetime] = mapped_column(DateTime)
    repeat: Mapped[str] = mapped_column(Enum(RepeatType), default=RepeatType.NONE)
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="reminders")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    external_id: Mapped[str | None] = mapped_column(String(256))  # Google Calendar event id
    title: Mapped[str] = mapped_column(String(512))
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    reminder_minutes: Mapped[int | None] = mapped_column(Integer)
    repeat: Mapped[str] = mapped_column(Enum(RepeatType), default=RepeatType.NONE)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="calendar_events")


class UserIntegration(Base):
    __tablename__ = "user_integrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    integration_type: Mapped[str] = mapped_column(Enum(IntegrationType))
    provider_name: Mapped[str] = mapped_column(String(64))  # google, notion, ...
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    credentials: Mapped[str | None] = mapped_column(Text)  # зашифровано Fernet
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="integrations")


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(Enum(ChatRole))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="chat_history")
