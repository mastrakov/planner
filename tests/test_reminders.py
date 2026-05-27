"""Tests for ReminderService."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.db.models import AIModel
from bot.services.intent.models import (
    CreateReminderIntent,
    DeleteReminderIntent,
    ListRemindersIntent,
    UpdateReminderIntent,
)
from bot.services.reminders import ReminderService


def _make_user() -> SimpleNamespace:
    return SimpleNamespace(id=1, timezone="Europe/Moscow", ai_model=AIModel.CLAUDE)


def _make_reminder(
    reminder_id: int,
    title: str,
    remind_at: datetime,
    repeat: str = "none",
    event_id: int | None = None,
    task_id: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=reminder_id,
        user_id=1,
        title=title,
        remind_at=remind_at,
        repeat=repeat,
        event_id=event_id,
        task_id=task_id,
        is_sent=False,
    )


def _make_service(repo: AsyncMock | None = None) -> ReminderService:
    session = AsyncMock()
    repo = repo or AsyncMock()
    return ReminderService(session=session, repo=repo)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_returns_formatted_string() -> None:
    remind_at = datetime(2025, 6, 15, 10, 0, 0)
    reminder = _make_reminder(1, "Позвонить врачу", remind_at)

    repo = AsyncMock()
    repo.create = AsyncMock(return_value=reminder)
    service = _make_service(repo=repo)

    result = await service.create(
        user=_make_user(),  # type: ignore[arg-type]
        intent=CreateReminderIntent(type="create_reminder", title="Позвонить врачу", remind_at=remind_at),
    )

    assert "Позвонить врачу" in result
    assert "Напоминание создано" in result


# ---------------------------------------------------------------------------
# list_reminders
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_reminders_empty_returns_no_reminders_text() -> None:
    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=[])
    service = _make_service(repo=repo)

    result = await service.list_reminders(
        user=_make_user(),  # type: ignore[arg-type]
        intent=ListRemindersIntent(type="list_reminders"),
    )

    assert "нет активных напоминаний" in result.lower()


@pytest.mark.asyncio
async def test_list_reminders_with_repeat_shows_repeat_icon() -> None:
    remind_at = datetime(2025, 6, 15, 9, 0, 0)
    reminders = [_make_reminder(1, "Зарядка", remind_at, repeat="daily")]

    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=reminders)
    service = _make_service(repo=repo)

    result = await service.list_reminders(
        user=_make_user(),  # type: ignore[arg-type]
        intent=ListRemindersIntent(type="list_reminders"),
    )

    assert "🔁" in result


@pytest.mark.asyncio
async def test_list_reminders_with_event_shows_calendar_icon() -> None:
    remind_at = datetime(2025, 6, 15, 9, 0, 0)
    reminders = [_make_reminder(1, "Встреча", remind_at, event_id=42)]

    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=reminders)
    service = _make_service(repo=repo)

    result = await service.list_reminders(
        user=_make_user(),  # type: ignore[arg-type]
        intent=ListRemindersIntent(type="list_reminders"),
    )

    assert "📅" in result


# ---------------------------------------------------------------------------
# delete_reminder
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_reminder_not_found() -> None:
    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=[])
    service = _make_service(repo=repo)

    result = await service.delete_reminder(
        user=_make_user(),  # type: ignore[arg-type]
        intent=DeleteReminderIntent(type="delete_reminder", reminder_title="Несуществующее"),
    )

    assert "не найдено" in result.lower()
    repo.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_reminder_ambiguous_returns_disambiguation() -> None:
    remind_at = datetime(2025, 6, 15, 9, 0, 0)
    reminders = [
        _make_reminder(1, "Позвонить Ивану", remind_at),
        _make_reminder(2, "Позвонить Марии", remind_at),
    ]

    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=reminders)
    service = _make_service(repo=repo)

    result = await service.delete_reminder(
        user=_make_user(),  # type: ignore[arg-type]
        intent=DeleteReminderIntent(type="delete_reminder", reminder_title="позвонить"),
    )

    assert "Найдено несколько" in result
    assert "Позвонить Ивану" in result
    assert "Позвонить Марии" in result
    repo.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_reminder_exact_match_deletes_and_confirms() -> None:
    remind_at = datetime(2025, 6, 15, 9, 0, 0)
    reminder = _make_reminder(1, "Позвонить врачу", remind_at)

    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=[reminder])
    repo.delete = AsyncMock()
    service = _make_service(repo=repo)

    result = await service.delete_reminder(
        user=_make_user(),  # type: ignore[arg-type]
        intent=DeleteReminderIntent(type="delete_reminder", reminder_title="врачу"),
    )

    repo.delete.assert_called_once_with(reminder)
    assert "удалено" in result.lower()
    assert "Позвонить врачу" in result


# ---------------------------------------------------------------------------
# update_reminder
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_reminder_calls_repo_update_with_kwargs() -> None:
    remind_at = datetime(2025, 6, 15, 9, 0, 0)
    new_remind_at = datetime(2025, 6, 16, 9, 0, 0)
    reminder = _make_reminder(1, "Позвонить врачу", remind_at)

    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=[reminder])
    repo.update = AsyncMock()
    service = _make_service(repo=repo)

    await service.update_reminder(
        user=_make_user(),  # type: ignore[arg-type]
        intent=UpdateReminderIntent(
            type="update_reminder",
            reminder_title="врачу",
            new_remind_at=new_remind_at,
        ),
    )

    repo.update.assert_called_once()
    call_kwargs = repo.update.call_args.kwargs
    assert "remind_at" in call_kwargs


# ---------------------------------------------------------------------------
# check_and_send
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_and_send_sends_and_marks_all_pending() -> None:
    remind_at = datetime(2025, 6, 15, 9, 0, 0)
    reminders = [
        _make_reminder(1, "Зарядка", remind_at),
        _make_reminder(2, "Таблетки", remind_at),
    ]

    repo = AsyncMock()
    repo.get_pending = AsyncMock(return_value=reminders)
    repo.mark_sent = AsyncMock()

    session = AsyncMock()
    session.commit = AsyncMock()

    service = ReminderService(session=session, repo=repo)

    bot = AsyncMock()
    bot.send_message = AsyncMock()

    await service.check_and_send(bot)

    assert bot.send_message.call_count == 2
    assert repo.mark_sent.call_count == 2
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_check_and_send_exception_does_not_stop_other_reminders() -> None:
    """If one send fails, the remaining reminders still get processed."""
    remind_at = datetime(2025, 6, 15, 9, 0, 0)
    reminders = [
        _make_reminder(1, "Зарядка", remind_at),
        _make_reminder(2, "Таблетки", remind_at),
    ]

    repo = AsyncMock()
    repo.get_pending = AsyncMock(return_value=reminders)
    repo.mark_sent = AsyncMock()

    session = AsyncMock()
    session.commit = AsyncMock()

    service = ReminderService(session=session, repo=repo)

    call_count = 0

    async def send_side_effect(user_id: int, text: str) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Telegram API error")

    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=send_side_effect)

    await service.check_and_send(bot)

    assert bot.send_message.call_count == 2
    # First failed, second succeeded
    assert repo.mark_sent.call_count == 1
    session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# create — with task_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_reminder_with_task_id() -> None:
    """task_id from intent is forwarded to ReminderRepo.create."""
    remind_at = datetime(2025, 6, 15, 10, 0, 0)
    reminder = _make_reminder(1, "Напомнить о задаче", remind_at, task_id=42)

    repo = AsyncMock()
    repo.create = AsyncMock(return_value=reminder)
    service = _make_service(repo=repo)

    await service.create(
        user=_make_user(),  # type: ignore[arg-type]
        intent=CreateReminderIntent(
            type="create_reminder",
            title="Напомнить о задаче",
            remind_at=remind_at,
            task_id=42,
        ),
    )

    repo.create.assert_called_once()
    call_kwargs = repo.create.call_args.kwargs
    assert call_kwargs.get("task_id") == 42
