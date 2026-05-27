"""Tests for AnalyticsService."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.db.models import AIModel
from bot.services.analytics import AnalyticsService


def _make_user() -> SimpleNamespace:
    return SimpleNamespace(id=1, timezone="Europe/Moscow", ai_model=AIModel.CLAUDE)


def _make_task_repo(lists: list[SimpleNamespace] | None = None) -> AsyncMock:
    repo = AsyncMock()
    repo.get_lists_by_user = AsyncMock(return_value=lists or [])
    return repo


def _make_daily_rows(
    overdue_day: str | None = None,
    overdue_count: int = 0,
) -> list[dict]:
    """Build 7-day breakdown rows. Optionally set one day to have overdue tasks."""
    days = ["Пн 26.05", "Вт 27.05", "Ср 28.05", "Чт 29.05", "Пт 30.05", "Сб 31.05", "Вс 01.06"]
    rows = []
    for i, label in enumerate(days):
        is_weekend = i >= 5
        ovr = overdue_count if label == overdue_day else 0
        rows.append({
            "label": label,
            "is_weekend": is_weekend,
            "created": 2,
            "completed": 1,
            "overdue": ovr,
        })
    return rows


def _make_weekly_rows() -> list[dict]:
    return [
        {"label": "19.05–25.05", "created": 5, "completed": 3, "overdue": 1},
        {"label": "26.05–01.06", "created": 8, "completed": 6, "overdue": 0},
        {"label": "02.06–08.06", "created": 3, "completed": 2, "overdue": 2},
        {"label": "09.06–15.06", "created": 6, "completed": 5, "overdue": 0},
    ]


def _make_analytics_repo(
    open_count: int = 10,
    overdue_count: int = 2,
    completed: int = 5,
    created: int = 8,
    daily_rows: list[dict] | None = None,
    weekly_rows: list[dict] | None = None,
    list_counts: tuple[int, int] = (10, 5),
) -> AsyncMock:
    repo = AsyncMock()
    repo.get_open_count = AsyncMock(return_value=open_count)
    repo.get_overdue_count = AsyncMock(return_value=overdue_count)
    repo.get_completed_count = AsyncMock(return_value=completed)
    repo.get_created_count = AsyncMock(return_value=created)
    repo.get_daily_breakdown = AsyncMock(return_value=daily_rows or _make_daily_rows())
    repo.get_weekly_breakdown = AsyncMock(return_value=weekly_rows or _make_weekly_rows())
    repo.get_list_task_counts = AsyncMock(return_value=list_counts)
    return repo


def _make_service(
    task_repo: AsyncMock | None = None,
    analytics_repo: AsyncMock | None = None,
) -> AnalyticsService:
    session = AsyncMock()
    return AnalyticsService(
        session=session,
        analytics_repo=analytics_repo or _make_analytics_repo(),
        task_repo=task_repo or _make_task_repo(),
    )


# ---------------------------------------------------------------------------
# get_stats delegates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_stats_week_delegates_to_weekly() -> None:
    service = _make_service()
    result = await service.get_stats(_make_user(), "week")  # type: ignore[arg-type]
    assert "Аналитика за неделю" in result


@pytest.mark.asyncio
async def test_get_stats_month_delegates_to_monthly() -> None:
    service = _make_service()
    result = await service.get_stats(_make_user(), "month")  # type: ignore[arg-type]
    assert "Аналитика за месяц" in result


# ---------------------------------------------------------------------------
# get_weekly_stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weekly_stats_contains_open_and_overdue() -> None:
    repo = _make_analytics_repo(open_count=12, overdue_count=3)
    service = _make_service(analytics_repo=repo)
    result = await service.get_weekly_stats(_make_user())  # type: ignore[arg-type]
    assert "Открытых задач" in result
    assert "12" in result
    assert "просрочено" in result
    assert "3" in result


@pytest.mark.asyncio
async def test_weekly_stats_contains_created_and_completed() -> None:
    repo = _make_analytics_repo(completed=5, created=8)
    service = _make_service(analytics_repo=repo)
    result = await service.get_weekly_stats(_make_user())  # type: ignore[arg-type]
    assert "Закрыто за 7 дней" in result
    assert "5" in result
    assert "Создано за 7 дней" in result
    assert "8" in result


@pytest.mark.asyncio
async def test_weekly_stats_bar_chart_present() -> None:
    service = _make_service()
    result = await service.get_weekly_stats(_make_user())  # type: ignore[arg-type]
    assert "По дням" in result
    assert "█" in result or "░" in result


@pytest.mark.asyncio
async def test_weekly_stats_overdue_section_shown_when_present() -> None:
    rows = _make_daily_rows(overdue_day="Ср 28.05", overdue_count=3)
    repo = _make_analytics_repo(daily_rows=rows)
    service = _make_service(analytics_repo=repo)
    result = await service.get_weekly_stats(_make_user())  # type: ignore[arg-type]
    assert "Просрочки по дням" in result
    assert "Ср 28.05" in result


@pytest.mark.asyncio
async def test_weekly_stats_no_overdue_section_when_clean() -> None:
    rows = _make_daily_rows()  # all overdue=0
    repo = _make_analytics_repo(daily_rows=rows, overdue_count=0)
    service = _make_service(analytics_repo=repo)
    result = await service.get_weekly_stats(_make_user())  # type: ignore[arg-type]
    assert "Просрочки по дням" not in result


@pytest.mark.asyncio
async def test_weekly_stats_weekend_marked() -> None:
    service = _make_service()
    result = await service.get_weekly_stats(_make_user())  # type: ignore[arg-type]
    # Сб and Вс rows should exist
    assert "Сб" in result or "Вс" in result


@pytest.mark.asyncio
async def test_weekly_stats_with_list_stats() -> None:
    lst = SimpleNamespace(id=1, name="Работа", emoji="💼")
    task_repo = _make_task_repo(lists=[lst])
    repo = _make_analytics_repo(list_counts=(10, 7))
    service = _make_service(task_repo=task_repo, analytics_repo=repo)
    result = await service.get_weekly_stats(_make_user())  # type: ignore[arg-type]
    assert "По спискам" in result
    assert "Работа" in result
    assert "7/10" in result


# ---------------------------------------------------------------------------
# get_monthly_stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_monthly_stats_contains_header() -> None:
    service = _make_service()
    result = await service.get_monthly_stats(_make_user())  # type: ignore[arg-type]
    assert "Аналитика за месяц" in result


@pytest.mark.asyncio
async def test_monthly_stats_contains_weekly_chart() -> None:
    service = _make_service()
    result = await service.get_monthly_stats(_make_user())  # type: ignore[arg-type]
    assert "По неделям" in result


@pytest.mark.asyncio
async def test_monthly_stats_overdue_weeks_section() -> None:
    rows = _make_weekly_rows()  # row 0 and 2 have overdue
    repo = _make_analytics_repo(weekly_rows=rows)
    service = _make_service(analytics_repo=repo)
    result = await service.get_monthly_stats(_make_user())  # type: ignore[arg-type]
    assert "Просрочки по неделям" in result
    assert "19.05" in result


@pytest.mark.asyncio
async def test_monthly_stats_no_overdue_weeks_when_clean() -> None:
    rows = [{"label": f"0{i}.06–0{i+6}.06", "created": 3, "completed": 3, "overdue": 0} for i in range(1, 5)]
    repo = _make_analytics_repo(weekly_rows=rows, overdue_count=0)
    service = _make_service(analytics_repo=repo)
    result = await service.get_monthly_stats(_make_user())  # type: ignore[arg-type]
    assert "Просрочки по неделям" not in result
