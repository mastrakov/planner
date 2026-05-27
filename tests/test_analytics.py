"""Tests for AnalyticsService."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.db.models import AIModel
from bot.services.analytics import AnalyticsService


def _make_user(ai_model: str = AIModel.CLAUDE) -> SimpleNamespace:
    return SimpleNamespace(id=1, timezone="Europe/Moscow", ai_model=ai_model)


def _make_task_repo(lists: list[SimpleNamespace] | None = None) -> AsyncMock:
    repo = AsyncMock()
    repo.get_lists_by_user = AsyncMock(return_value=lists or [])
    return repo


def _make_analytics_repo(
    completed: int = 5,
    created: int = 8,
    daily: dict[str, int] | None = None,
    weekly: dict[str, int] | None = None,
    list_counts: tuple[int, int] = (10, 5),
) -> AsyncMock:
    repo = AsyncMock()
    repo.get_completed_count = AsyncMock(return_value=completed)
    repo.get_created_count = AsyncMock(return_value=created)
    daily_data = daily or {
        "Mon 09.06": 1,
        "Tue 10.06": 2,
        "Wed 11.06": 0,
        "Thu 12.06": 3,
        "Fri 13.06": 1,
        "Sat 14.06": 0,
        "Sun 15.06": 2,
    }
    weekly_data = weekly or {
        "Неделя 1 (19.05–26.05)": 3,
        "Неделя 2 (26.05–02.06)": 4,
        "Неделя 3 (02.06–09.06)": 2,
        "Неделя 4 (09.06–16.06)": 5,
    }
    repo.get_completed_per_day = AsyncMock(return_value=daily_data)
    repo.get_completed_per_week = AsyncMock(return_value=weekly_data)
    repo.get_list_task_counts = AsyncMock(return_value=list_counts)
    return repo


def _make_service(
    task_repo: AsyncMock | None = None,
    analytics_repo: AsyncMock | None = None,
    anthropic_client: AsyncMock | None = None,
) -> AnalyticsService:
    session = AsyncMock()
    return AnalyticsService(
        session=session,
        anthropic_client=anthropic_client,
        analytics_repo=analytics_repo or _make_analytics_repo(),
        task_repo=task_repo or _make_task_repo(),
    )


# ---------------------------------------------------------------------------
# get_stats delegates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_stats_week_delegates_to_weekly() -> None:
    service = _make_service()
    user = _make_user()
    result = await service.get_stats(user, "week")  # type: ignore[arg-type]
    assert "Статистика за неделю" in result


@pytest.mark.asyncio
async def test_get_stats_month_delegates_to_monthly() -> None:
    service = _make_service()
    user = _make_user()
    result = await service.get_stats(user, "month")  # type: ignore[arg-type]
    assert "Статистика за месяц" in result


# ---------------------------------------------------------------------------
# get_weekly_stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weekly_stats_contains_header_and_counts() -> None:
    analytics_repo = _make_analytics_repo(completed=5, created=8)
    service = _make_service(analytics_repo=analytics_repo)

    result = await service.get_weekly_stats(_make_user())  # type: ignore[arg-type]

    assert "Статистика за неделю" in result
    assert "Создано задач: 8" in result
    assert "Выполнено: 5" in result


@pytest.mark.asyncio
async def test_weekly_stats_contains_bar_chart_lines() -> None:
    daily = {"Mon 09.06": 5, "Tue 10.06": 0, "Wed 11.06": 3}
    analytics_repo = _make_analytics_repo(daily=daily)
    service = _make_service(analytics_repo=analytics_repo)

    result = await service.get_weekly_stats(_make_user())  # type: ignore[arg-type]

    assert "Динамика по дням" in result
    # Max is 5 → Mon should have full bar (10 blocks)
    assert "Mon 09.06: ██████████ 5" in result


@pytest.mark.asyncio
async def test_weekly_stats_with_list_stats() -> None:
    lst = SimpleNamespace(id=1, name="Работа", emoji="💼")
    task_repo = _make_task_repo(lists=[lst])
    analytics_repo = _make_analytics_repo(list_counts=(10, 7))
    service = _make_service(task_repo=task_repo, analytics_repo=analytics_repo)

    result = await service.get_weekly_stats(_make_user())  # type: ignore[arg-type]

    assert "По спискам" in result
    assert "Работа" in result
    assert "7/10" in result


# ---------------------------------------------------------------------------
# get_monthly_stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_monthly_stats_contains_header_and_counts() -> None:
    analytics_repo = _make_analytics_repo(completed=20, created=30)
    service = _make_service(analytics_repo=analytics_repo)

    result = await service.get_monthly_stats(_make_user())  # type: ignore[arg-type]

    assert "Статистика за месяц" in result
    assert "Создано задач: 30" in result
    assert "Выполнено: 20" in result


@pytest.mark.asyncio
async def test_monthly_stats_contains_weekly_bar_chart() -> None:
    analytics_repo = _make_analytics_repo()
    service = _make_service(analytics_repo=analytics_repo)

    result = await service.get_monthly_stats(_make_user())  # type: ignore[arg-type]

    assert "Динамика по неделям" in result
    assert "Неделя" in result


# ---------------------------------------------------------------------------
# AI failure — graceful degradation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weekly_stats_ai_failure_still_returns_stats() -> None:
    """If _get_ai_insights raises, output still contains stats."""
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("AI down"))

    analytics_repo = _make_analytics_repo(completed=3, created=5)
    service = _make_service(analytics_repo=analytics_repo, anthropic_client=mock_client)

    result = await service.get_weekly_stats(_make_user())  # type: ignore[arg-type]

    assert "Статистика за неделю" in result
    assert "Выполнено: 3" in result


# ---------------------------------------------------------------------------
# Edge case: all-zero daily completions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weekly_stats_all_zero_completions_shows_empty_bars() -> None:
    daily = {f"Day {i}": 0 for i in range(7)}
    analytics_repo = _make_analytics_repo(completed=0, daily=daily)
    service = _make_service(analytics_repo=analytics_repo)

    result = await service.get_weekly_stats(_make_user())  # type: ignore[arg-type]

    # All bars should be empty (max_val defaults to 1 when all zero)
    assert "░░░░░░░░░░" in result
    # And no filled blocks
    assert "██" not in result
