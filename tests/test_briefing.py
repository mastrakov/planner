"""Tests for BriefingService — morning briefing and weekly plan."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.db.models import AIModel
from bot.services.briefing import BriefingService, _weekday_ru, _weekday_short_ru
from bot.utils.dt import now_utc


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        first_name="Алексей",
        timezone="Europe/Moscow",
        ai_model=AIModel.CLAUDE,
        briefing_time=time(8, 0),
        is_active=True,
    )


def _make_task(
    task_id: int,
    title: str,
    due: datetime | None = None,
    priority: str = "medium",
    scheduled_at: datetime | None = None,
) -> SimpleNamespace:
    task_list = SimpleNamespace(name="Работа", emoji="💼")
    return SimpleNamespace(
        id=task_id,
        user_id=1,
        title=title,
        priority=priority,
        due_date=due,
        scheduled_at=scheduled_at,
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
    )


def _make_reminder(reminder_id: int, title: str, remind_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(id=reminder_id, user_id=1, title=title, remind_at=remind_at, is_sent=False)


def _make_full_repos(
    *,
    overdue: list | None = None,
    today_tasks: list | None = None,
    high_prio_no_dl: list | None = None,
    week_tasks: list | None = None,
    events: list | None = None,
    today_reminders: list | None = None,
    event_has_reminder: bool = False,
    task_has_reminder: bool = False,
) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    """Return (MockTaskRepo instance, MockCalRepo instance, MockReminderRepo instance)."""
    task_repo = AsyncMock()
    task_repo.get_overdue = AsyncMock(return_value=overdue or [])
    task_repo.get_today = AsyncMock(return_value=today_tasks or [])
    task_repo.get_high_priority_no_deadline = AsyncMock(return_value=high_prio_no_dl or [])
    task_repo.get_week_range = AsyncMock(return_value=week_tasks or [])
    task_repo.get_by_user = AsyncMock(return_value=[])

    cal_repo = AsyncMock()
    cal_repo.get_for_date_range = AsyncMock(return_value=events or [])

    reminder_repo = AsyncMock()
    reminder_repo.get_today = AsyncMock(return_value=today_reminders or [])
    reminder_repo.has_reminder_for_event = AsyncMock(return_value=event_has_reminder)
    reminder_repo.has_reminder_for_task_today = AsyncMock(return_value=task_has_reminder)

    return task_repo, cal_repo, reminder_repo


def _patch_all(task_repo: AsyncMock, cal_repo: AsyncMock, reminder_repo: AsyncMock):
    """Return a context-manager that patches all three repos inside BriefingService."""
    return (
        patch("bot.services.briefing.TaskRepo", return_value=task_repo),
        patch("bot.services.briefing.CalendarRepo", return_value=cal_repo),
        patch("bot.services.briefing.ReminderRepo", return_value=reminder_repo),
    )


# ---------------------------------------------------------------------------
# build_morning / build_morning_briefing (legacy wrapper)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_morning_briefing_contains_overdue_tasks() -> None:
    session = AsyncMock()
    user = _make_user()
    overdue = _make_task(1, "Просроченная задача", due=datetime(2020, 1, 1))
    task_repo, cal_repo, rem_repo = _make_full_repos(overdue=[overdue])

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_morning_briefing(user)  # type: ignore[arg-type]

    assert "Просроченная задача" in result
    assert "Просрочено" in result


@pytest.mark.asyncio
async def test_morning_briefing_contains_today_events() -> None:
    session = AsyncMock()
    user = _make_user()
    now = now_utc()
    event = _make_event(1, "Встреча с командой", starts_at=now.replace(hour=10))
    task_repo, cal_repo, rem_repo = _make_full_repos(events=[event], event_has_reminder=True)

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_morning_briefing(user)  # type: ignore[arg-type]

    assert "Встреча с командой" in result


@pytest.mark.asyncio
async def test_morning_briefing_empty_day() -> None:
    session = AsyncMock()
    user = _make_user()
    task_repo, cal_repo, rem_repo = _make_full_repos()

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_morning_briefing(user)  # type: ignore[arg-type]

    assert "Доброе утро" in result


@pytest.mark.asyncio
async def test_morning_briefing_contains_today_tasks() -> None:
    session = AsyncMock()
    user = _make_user()
    now = now_utc()
    today_task = _make_task(2, "Написать отчёт", due=now.replace(hour=18), priority="high")
    task_repo, cal_repo, rem_repo = _make_full_repos(today_tasks=[today_task], task_has_reminder=True)

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_morning_briefing(user)  # type: ignore[arg-type]

    assert "Написать отчёт" in result
    assert "Задачи:" in result


@pytest.mark.asyncio
async def test_morning_briefing_high_priority_no_deadline_block() -> None:
    session = AsyncMock()
    user = _make_user()
    hp_task = _make_task(3, "Обновить резюме", priority="high")
    task_repo, cal_repo, rem_repo = _make_full_repos(high_prio_no_dl=[hp_task])

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_morning_briefing(user)  # type: ignore[arg-type]

    assert "Обновить резюме" in result
    assert "Задачи:" in result


@pytest.mark.asyncio
async def test_morning_build_returns_briefing_result_type() -> None:
    """build_morning returns BriefingResult, not a plain string."""
    from bot.services.briefing import BriefingResult

    session = AsyncMock()
    user = _make_user()
    task_repo, cal_repo, rem_repo = _make_full_repos()

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_morning(user)  # type: ignore[arg-type]

    assert isinstance(result, BriefingResult)
    assert isinstance(result.text, str)
    assert "Доброе утро" in result.text


@pytest.mark.asyncio
async def test_morning_briefing_shows_today_reminders() -> None:
    """Today's reminders appear in a dedicated section with their time."""
    session = AsyncMock()
    user = _make_user()
    now = now_utc()
    reminder = _make_reminder(1, "Позвонить маме", remind_at=now.replace(hour=14, minute=0))
    task_repo, cal_repo, rem_repo = _make_full_repos(today_reminders=[reminder])

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_morning_briefing(user)  # type: ignore[arg-type]

    assert "Напоминания на сегодня" in result
    assert "Позвонить маме" in result


@pytest.mark.asyncio
async def test_morning_briefing_no_reminders_section_when_empty() -> None:
    """Reminders section is absent when there are no reminders today."""
    session = AsyncMock()
    user = _make_user()
    task_repo, cal_repo, rem_repo = _make_full_repos()

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_morning_briefing(user)  # type: ignore[arg-type]

    assert "Напоминания на сегодня" not in result


# ---------------------------------------------------------------------------
# build_weekly / build_weekly_plan (legacy wrapper)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_weekly_plan_with_tasks_contains_titles() -> None:
    session = AsyncMock()
    user = _make_user()
    now = now_utc()
    task = _make_task(1, "Сделать отчёт", due=now + timedelta(days=3))
    task_repo, cal_repo, rem_repo = _make_full_repos(week_tasks=[task])

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_weekly_plan(user)  # type: ignore[arg-type]

    assert "Сделать отчёт" in result
    assert "Задачи на неделю" in result


@pytest.mark.asyncio
async def test_build_weekly_plan_with_events_contains_event_titles() -> None:
    session = AsyncMock()
    user = _make_user()
    now = now_utc()
    event = _make_event(1, "Конференция по Python", starts_at=now.replace(hour=14))
    task_repo, cal_repo, rem_repo = _make_full_repos(events=[event], event_has_reminder=True)

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_weekly_plan(user)  # type: ignore[arg-type]

    assert "Конференция по Python" in result
    assert "События" in result


@pytest.mark.asyncio
async def test_build_weekly_plan_empty_week_only_header() -> None:
    session = AsyncMock()
    user = _make_user()
    task_repo, cal_repo, rem_repo = _make_full_repos()

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_weekly_plan(user)  # type: ignore[arg-type]

    assert "Неделя" in result
    # No task or event sections when empty
    assert "Задачи на неделю" not in result
    assert "События" not in result


@pytest.mark.asyncio
async def test_build_weekly_high_priority_no_deadline_block() -> None:
    session = AsyncMock()
    user = _make_user()
    hp_task = _make_task(10, "Записаться к врачу", priority="high")
    task_repo, cal_repo, rem_repo = _make_full_repos(high_prio_no_dl=[hp_task])

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_weekly_plan(user)  # type: ignore[arg-type]

    assert "Записаться к врачу" in result
    assert "Важные" in result


@pytest.mark.asyncio
async def test_build_weekly_event_reminder_buttons() -> None:
    """Events without reminders produce per-event keyboard buttons."""
    from bot.services.briefing import BriefingResult

    session = AsyncMock()
    user = _make_user()
    now = now_utc()
    event = _make_event(77, "Планёрка", starts_at=now + timedelta(days=1))
    task_repo, cal_repo, rem_repo = _make_full_repos(events=[event], event_has_reminder=False)

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_weekly(user)  # type: ignore[arg-type]

    assert isinstance(result, BriefingResult)
    assert result.combined_keyboard is not None
    buttons = [
        btn.callback_data
        for row in result.combined_keyboard.inline_keyboard
        for btn in row
    ]
    assert any("remind_event:60:77" in cb for cb in buttons)
    assert any("remind_event:1440:77" in cb for cb in buttons)
    assert any("remind_all_week_events" in cb for cb in buttons)


@pytest.mark.asyncio
async def test_build_weekly_no_keyboard_when_all_have_reminders() -> None:
    session = AsyncMock()
    user = _make_user()
    now = now_utc()
    event = _make_event(1, "Встреча", starts_at=now + timedelta(days=2))
    task_repo, cal_repo, rem_repo = _make_full_repos(events=[event], event_has_reminder=True)

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_weekly(user)  # type: ignore[arg-type]

    assert result.combined_keyboard is None


@pytest.mark.asyncio
async def test_build_weekly_tasks_grouped_by_list() -> None:
    """Week tasks should appear with their list label in the output."""
    session = AsyncMock()
    user = _make_user()
    now = now_utc()
    task1 = _make_task(1, "Квартальный отчёт", due=now + timedelta(days=1), priority="high")
    task2 = _make_task(2, "Код ревью", due=now + timedelta(days=3), priority="medium")
    task_repo, cal_repo, rem_repo = _make_full_repos(week_tasks=[task1, task2])

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_weekly_plan(user)  # type: ignore[arg-type]

    # Both tasks should appear
    assert "Квартальный отчёт" in result
    assert "Код ревью" in result
    # List label should appear (from task_list.emoji + task_list.name)
    assert "Работа" in result


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def test_weekday_ru_returns_correct_names() -> None:
    from datetime import date
    # 2026-05-25 is Monday
    monday = datetime(2026, 5, 25, 10, 0)
    assert _weekday_ru(monday) == "Понедельник"

    sunday = datetime(2026, 5, 31, 10, 0)
    assert _weekday_ru(sunday) == "Воскресенье"


def test_weekday_short_ru_returns_two_char() -> None:
    monday = datetime(2026, 5, 25)
    assert _weekday_short_ru(monday) == "Пн"
    friday = datetime(2026, 5, 29)
    assert _weekday_short_ru(friday) == "Пт"


# ---------------------------------------------------------------------------
# scheduled_at field tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_morning_briefing_task_with_scheduled_at_shows_time() -> None:
    """A task with scheduled_at today should display its time in the morning briefing."""
    session = AsyncMock()
    user = _make_user()
    now = now_utc()
    scheduled_time = now.replace(hour=15, minute=0, second=0, microsecond=0)
    today_task = _make_task(
        2, "Релиз проекта", due=None, priority="high", scheduled_at=scheduled_time
    )
    task_repo, cal_repo, rem_repo = _make_full_repos(today_tasks=[today_task])

    p1, p2, p3 = _patch_all(task_repo, cal_repo, rem_repo)
    with p1, p2, p3:
        service = BriefingService(session)
        result = await service.build_morning_briefing(user)  # type: ignore[arg-type]

    assert "Релиз проекта" in result
    # The task should show a time (from fmt_time of scheduled_at)
    # scheduled_time is UTC 15:00, Moscow (UTC+3) = 18:00
    assert "18:" in result
