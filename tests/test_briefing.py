from datetime import datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.db.models import AIModel
from bot.services.briefing import BriefingService
from bot.utils.dt import now_utc


def _make_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        first_name="Алексей",
        timezone="Europe/Moscow",
        ai_model=AIModel.CLAUDE,
        briefing_time=time(8, 0),
        is_active=True,
    )


def _make_task(task_id: int, title: str, due: datetime | None = None) -> SimpleNamespace:
    task_list = SimpleNamespace(name="Работа", emoji="💼")
    return SimpleNamespace(
        id=task_id,
        user_id=1,
        title=title,
        priority="medium",
        due_date=due,
        completed_at=None,
        task_list=task_list,
    )


def _make_event(event_id: int, title: str, starts_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        id=event_id,
        user_id=1,
        title=title,
        starts_at=starts_at,
        ends_at=None,
        reminder_minutes=None,
    )


@pytest.mark.asyncio
async def test_briefing_contains_overdue_tasks() -> None:
    session = AsyncMock()
    user = _make_user()
    overdue = _make_task(1, "Просроченная задача", due=datetime(2020, 1, 1))

    with (
        patch("bot.services.briefing.TaskRepo") as MockTaskRepo,
        patch("bot.services.briefing.CalendarRepo") as MockCalRepo,
        patch.object(BriefingService, "_get_ai_comment", new=AsyncMock(return_value="")),
    ):
        task_repo = MockTaskRepo.return_value
        task_repo.get_overdue = AsyncMock(return_value=[overdue])
        task_repo.get_by_user = AsyncMock(return_value=[])

        cal_repo = MockCalRepo.return_value
        cal_repo.get_for_date_range = AsyncMock(return_value=[])

        service = BriefingService(session)
        result = await service.build_morning_briefing(user)  # type: ignore[arg-type]

    assert "Просроченная задача" in result
    assert "Просроченные" in result


@pytest.mark.asyncio
async def test_briefing_contains_today_events() -> None:
    session = AsyncMock()
    user = _make_user()
    now = now_utc()
    event = _make_event(1, "Встреча с командой", starts_at=now.replace(hour=10))

    with (
        patch("bot.services.briefing.TaskRepo") as MockTaskRepo,
        patch("bot.services.briefing.CalendarRepo") as MockCalRepo,
        patch.object(BriefingService, "_get_ai_comment", new=AsyncMock(return_value="")),
    ):
        task_repo = MockTaskRepo.return_value
        task_repo.get_overdue = AsyncMock(return_value=[])
        task_repo.get_by_user = AsyncMock(return_value=[])

        cal_repo = MockCalRepo.return_value
        cal_repo.get_for_date_range = AsyncMock(return_value=[event])

        service = BriefingService(session)
        result = await service.build_morning_briefing(user)  # type: ignore[arg-type]

    assert "Встреча с командой" in result


@pytest.mark.asyncio
async def test_briefing_empty_day() -> None:
    session = AsyncMock()
    user = _make_user()

    with (
        patch("bot.services.briefing.TaskRepo") as MockTaskRepo,
        patch("bot.services.briefing.CalendarRepo") as MockCalRepo,
        patch.object(BriefingService, "_get_ai_comment", new=AsyncMock(return_value="Хороший день!")),
    ):
        task_repo = MockTaskRepo.return_value
        task_repo.get_overdue = AsyncMock(return_value=[])
        task_repo.get_by_user = AsyncMock(return_value=[])

        cal_repo = MockCalRepo.return_value
        cal_repo.get_for_date_range = AsyncMock(return_value=[])

        service = BriefingService(session)
        result = await service.build_morning_briefing(user)  # type: ignore[arg-type]

    assert "Доброе утро" in result
    assert "Хороший день!" in result


@pytest.mark.asyncio
async def test_briefing_ai_comment_failure_does_not_crash() -> None:
    session = AsyncMock()
    user = _make_user()
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("AI down"))

    with (
        patch("bot.services.briefing.TaskRepo") as MockTaskRepo,
        patch("bot.services.briefing.CalendarRepo") as MockCalRepo,
    ):
        task_repo = MockTaskRepo.return_value
        task_repo.get_overdue = AsyncMock(return_value=[])
        task_repo.get_by_user = AsyncMock(return_value=[])

        cal_repo = MockCalRepo.return_value
        cal_repo.get_for_date_range = AsyncMock(return_value=[])

        service = BriefingService(session, anthropic_client=mock_client)
        result = await service.build_morning_briefing(user)  # type: ignore[arg-type]

    assert "Доброе утро" in result


# ---------------------------------------------------------------------------
# build_weekly_plan
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_weekly_plan_with_tasks_contains_titles() -> None:
    session = AsyncMock()
    user = _make_user()
    now = now_utc()
    from datetime import timedelta
    task = _make_task(1, "Сделать отчёт", due=now + timedelta(days=3))

    with (
        patch("bot.services.briefing.TaskRepo") as MockTaskRepo,
        patch("bot.services.briefing.CalendarRepo") as MockCalRepo,
        patch.object(BriefingService, "_get_ai_comment", new=AsyncMock(return_value="")),
    ):
        task_repo = MockTaskRepo.return_value
        task_repo.get_by_user = AsyncMock(return_value=[task])

        cal_repo = MockCalRepo.return_value
        cal_repo.get_for_date_range = AsyncMock(return_value=[])

        service = BriefingService(session)
        result = await service.build_weekly_plan(user)  # type: ignore[arg-type]

    assert "Сделать отчёт" in result
    assert "Задачи с дедлайном" in result


@pytest.mark.asyncio
async def test_build_weekly_plan_with_events_contains_event_titles() -> None:
    session = AsyncMock()
    user = _make_user()
    now = now_utc()
    event = _make_event(1, "Конференция по Python", starts_at=now.replace(hour=14))

    with (
        patch("bot.services.briefing.TaskRepo") as MockTaskRepo,
        patch("bot.services.briefing.CalendarRepo") as MockCalRepo,
        patch.object(BriefingService, "_get_ai_comment", new=AsyncMock(return_value="")),
    ):
        task_repo = MockTaskRepo.return_value
        task_repo.get_by_user = AsyncMock(return_value=[])

        cal_repo = MockCalRepo.return_value
        cal_repo.get_for_date_range = AsyncMock(return_value=[event])

        service = BriefingService(session)
        result = await service.build_weekly_plan(user)  # type: ignore[arg-type]

    assert "Конференция по Python" in result
    assert "События" in result


@pytest.mark.asyncio
async def test_build_weekly_plan_empty_week_only_header() -> None:
    session = AsyncMock()
    user = _make_user()

    with (
        patch("bot.services.briefing.TaskRepo") as MockTaskRepo,
        patch("bot.services.briefing.CalendarRepo") as MockCalRepo,
        patch.object(BriefingService, "_get_ai_comment", new=AsyncMock(return_value="")),
    ):
        task_repo = MockTaskRepo.return_value
        task_repo.get_by_user = AsyncMock(return_value=[])

        cal_repo = MockCalRepo.return_value
        cal_repo.get_for_date_range = AsyncMock(return_value=[])

        service = BriefingService(session)
        result = await service.build_weekly_plan(user)  # type: ignore[arg-type]

    assert "План на неделю" in result
    assert "Задачи" not in result
    assert "События" not in result
