"""Tests for CalendarService."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.db.models import AIModel
from bot.services.calendar import CalendarService
from bot.services.intent.models import CreateEventIntent, ListEventsIntent


def _make_user() -> SimpleNamespace:
    return SimpleNamespace(id=1, timezone="Europe/Moscow", ai_model=AIModel.CLAUDE)


def _make_event(
    event_id: int,
    title: str,
    starts_at: datetime,
    user_id: int = 1,
    external_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=event_id,
        user_id=user_id,
        title=title,
        starts_at=starts_at,
        ends_at=None,
        external_id=external_id,
    )


def _make_service(
    repo: AsyncMock | None = None,
    reminder_repo: AsyncMock | None = None,
    integration_repo: AsyncMock | None = None,
) -> CalendarService:
    session = AsyncMock()
    repo = repo or AsyncMock()
    reminder_repo = reminder_repo or AsyncMock()
    integration_repo = integration_repo or AsyncMock()
    return CalendarService(
        session=session,
        repo=repo,
        reminder_repo=reminder_repo,
        integration_repo=integration_repo,
    )


# ---------------------------------------------------------------------------
# create_event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_event_no_google_integration() -> None:
    """Event created in DB only when no active integration."""
    starts_at = datetime(2025, 6, 15, 10, 0, 0)
    event = _make_event(1, "Встреча", starts_at)

    repo = AsyncMock()
    repo.create = AsyncMock(return_value=event)
    integration_repo = AsyncMock()
    integration_repo.get_active_calendar_integration = AsyncMock(return_value=None)

    with patch("bot.services.calendar.registry") as mock_registry:
        mock_registry.has_calendar.return_value = False
        service = _make_service(repo=repo, integration_repo=integration_repo)
        result = await service.create_event(
            user=_make_user(),  # type: ignore[arg-type]
            intent=CreateEventIntent(type="create_event", title="Встреча", starts_at=starts_at),
        )

    assert "Встреча" in result
    assert "Google Calendar" not in result
    repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_create_event_with_google_integration() -> None:
    """provider.create_event called; response contains sync note."""
    starts_at = datetime(2025, 6, 15, 10, 0, 0)
    event = _make_event(1, "Встреча", starts_at, external_id="gcal-123")

    repo = AsyncMock()
    repo.create = AsyncMock(return_value=event)

    integration = SimpleNamespace(provider_name="google")
    integration_repo = AsyncMock()
    integration_repo.get_active_calendar_integration = AsyncMock(return_value=integration)

    provider = AsyncMock()
    provider.create_event = AsyncMock(return_value="gcal-123")

    with patch("bot.services.calendar.registry") as mock_registry:
        mock_registry.has_calendar.return_value = True
        mock_registry.get_calendar.return_value = provider
        service = _make_service(repo=repo, integration_repo=integration_repo)
        result = await service.create_event(
            user=_make_user(),  # type: ignore[arg-type]
            intent=CreateEventIntent(type="create_event", title="Встреча", starts_at=starts_at),
        )

    provider.create_event.assert_called_once()
    assert "Google Calendar" in result


@pytest.mark.asyncio
async def test_create_event_with_reminder_minutes() -> None:
    """reminder_repo.create called for each requested offset; response contains reminder text."""
    starts_at = datetime(2025, 6, 15, 10, 0, 0)
    event = _make_event(1, "Встреча", starts_at)

    repo = AsyncMock()
    repo.create = AsyncMock(return_value=event)
    reminder_repo = AsyncMock()
    reminder_repo.create = AsyncMock()
    integration_repo = AsyncMock()
    integration_repo.get_active_calendar_integration = AsyncMock(return_value=None)

    with patch("bot.services.calendar.registry") as mock_registry:
        mock_registry.has_calendar.return_value = False
        service = _make_service(repo=repo, reminder_repo=reminder_repo, integration_repo=integration_repo)
        result = await service.create_event(
            user=_make_user(),  # type: ignore[arg-type]
            intent=CreateEventIntent(
                type="create_event",
                title="Встреча",
                starts_at=starts_at,
                reminder_minutes=[60, 10],
            ),
        )

    assert reminder_repo.create.call_count == 2
    assert "Напоминания" in result


# ---------------------------------------------------------------------------
# get_events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_events_no_events_returns_not_found() -> None:
    repo = AsyncMock()
    repo.get_for_date_range = AsyncMock(return_value=[])
    service = _make_service(repo=repo)
    result = await service.get_events(
        user=_make_user(),  # type: ignore[arg-type]
        intent=ListEventsIntent(type="list_events"),
    )
    assert result == "Событий не найдено."


@pytest.mark.asyncio
async def test_get_events_with_events_returns_html_list() -> None:
    starts_at = datetime(2025, 6, 15, 10, 0, 0)
    events = [
        _make_event(1, "Встреча с Иваном", starts_at),
        _make_event(2, "Обед с командой", starts_at),
    ]
    repo = AsyncMock()
    repo.get_for_date_range = AsyncMock(return_value=events)
    service = _make_service(repo=repo)
    result = await service.get_events(
        user=_make_user(),  # type: ignore[arg-type]
        intent=ListEventsIntent(type="list_events"),
    )
    assert "Встреча с Иваном" in result
    assert "Обед с командой" in result
    assert "<b>События:</b>" in result


# ---------------------------------------------------------------------------
# delete_event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_event_not_found() -> None:
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    service = _make_service(repo=repo)
    result = await service.delete_event(event_id=999, user=_make_user())  # type: ignore[arg-type]
    assert result == "Событие не найдено."


@pytest.mark.asyncio
async def test_delete_event_wrong_user_not_found() -> None:
    """Event exists but belongs to different user → not found."""
    starts_at = datetime(2025, 6, 15, 10, 0, 0)
    event = _make_event(1, "Чужое событие", starts_at, user_id=999)

    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=event)
    service = _make_service(repo=repo)
    result = await service.delete_event(event_id=1, user=_make_user())  # type: ignore[arg-type]
    assert result == "Событие не найдено."


@pytest.mark.asyncio
async def test_delete_event_no_external_id_only_local_delete() -> None:
    """Event with no external_id → only local delete, no provider.delete_event."""
    starts_at = datetime(2025, 6, 15, 10, 0, 0)
    event = _make_event(1, "Встреча", starts_at, external_id=None)

    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=event)
    repo.delete = AsyncMock()
    integration_repo = AsyncMock()
    integration_repo.get_active_calendar_integration = AsyncMock(return_value=None)

    with patch("bot.services.calendar.registry") as mock_registry:
        mock_registry.has_calendar.return_value = False
        service = _make_service(repo=repo, integration_repo=integration_repo)
        result = await service.delete_event(event_id=1, user=_make_user())  # type: ignore[arg-type]

    repo.delete.assert_called_once_with(event)
    assert "Встреча" in result
    assert "удалено" in result.lower()


@pytest.mark.asyncio
async def test_delete_event_with_external_id_calls_provider() -> None:
    """Event with external_id + active integration → provider.delete_event called."""
    starts_at = datetime(2025, 6, 15, 10, 0, 0)
    event = _make_event(1, "Встреча", starts_at, external_id="gcal-abc")

    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=event)
    repo.delete = AsyncMock()

    integration = SimpleNamespace(provider_name="google")
    integration_repo = AsyncMock()
    integration_repo.get_active_calendar_integration = AsyncMock(return_value=integration)

    provider = AsyncMock()
    provider.delete_event = AsyncMock()

    with patch("bot.services.calendar.registry") as mock_registry:
        mock_registry.has_calendar.return_value = True
        mock_registry.get_calendar.return_value = provider
        service = _make_service(repo=repo, integration_repo=integration_repo)
        result = await service.delete_event(event_id=1, user=_make_user())  # type: ignore[arg-type]

    provider.delete_event.assert_called_once_with(1, "gcal-abc")
    repo.delete.assert_called_once()
    assert "Встреча" in result
