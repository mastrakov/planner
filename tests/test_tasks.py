from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.db.models import AIModel, Priority
from bot.services.intent.models import (
    CompleteTaskIntent,
    CreateTaskIntent,
    DeleteTaskIntent,
    ListTasksIntent,
    UpdateTaskIntent,
)
from bot.services.tasks import DEFAULT_LISTS, TaskService
from bot.utils.dt import now_utc


def _make_user() -> SimpleNamespace:
    return SimpleNamespace(id=42, timezone="Europe/Moscow", ai_model=AIModel.CLAUDE)


def _make_list(list_id: int, name: str = "Работа") -> SimpleNamespace:
    return SimpleNamespace(id=list_id, user_id=42, name=name, emoji="💼", color="#4A90D9", position=0)


def _make_task(task_id: int, title: str, list_id: int = 1, priority: str = Priority.MEDIUM) -> SimpleNamespace:
    task_list = _make_list(list_id)
    return SimpleNamespace(
        id=task_id,
        user_id=42,
        list_id=list_id,
        title=title,
        priority=priority,
        due_date=None,
        scheduled_at=None,
        completed_at=None,
        created_at=now_utc(),
        task_list=task_list,
    )


@pytest.mark.asyncio
async def test_create_task_adds_to_first_list() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    user = _make_user()
    task_list = _make_list(1)
    created_task = _make_task(10, "Новая задача")

    with patch("bot.services.tasks.TaskRepo") as MockRepo:
        repo_instance = MockRepo.return_value
        repo_instance.get_lists_by_user = AsyncMock(return_value=[task_list])
        repo_instance.create = AsyncMock(return_value=created_task)

        service = TaskService(session)
        result = await service.create_task(
            user=user,  # type: ignore[arg-type]
            intent=CreateTaskIntent(type="create_task", title="Новая задача"),
        )

    assert "Новая задача" in result
    assert "Работа" in result


@pytest.mark.asyncio
async def test_create_task_returns_error_if_no_lists() -> None:
    session = AsyncMock()
    user = _make_user()

    with patch("bot.services.tasks.TaskRepo") as MockRepo:
        repo_instance = MockRepo.return_value
        repo_instance.get_lists_by_user = AsyncMock(return_value=[])

        service = TaskService(session)
        result = await service.create_task(
            user=user,  # type: ignore[arg-type]
            intent=CreateTaskIntent(type="create_task", title="Задача"),
        )

    assert "нет списков" in result.lower()


@pytest.mark.asyncio
async def test_complete_task_found() -> None:
    session = AsyncMock()
    user = _make_user()
    task = _make_task(1, "Купить молоко")

    with patch("bot.services.tasks.TaskRepo") as MockRepo:
        repo_instance = MockRepo.return_value
        repo_instance.get_by_user = AsyncMock(return_value=[task])
        repo_instance.complete = AsyncMock(return_value=task)

        service = TaskService(session)
        result = await service.complete_task(
            user=user,  # type: ignore[arg-type]
            intent=CompleteTaskIntent(type="complete_task", task_title="молоко"),
        )

    assert "выполнен" in result.lower()
    assert "Купить молоко" in result


@pytest.mark.asyncio
async def test_complete_task_not_found() -> None:
    session = AsyncMock()
    user = _make_user()

    with patch("bot.services.tasks.TaskRepo") as MockRepo:
        repo_instance = MockRepo.return_value
        repo_instance.get_by_user = AsyncMock(return_value=[])

        service = TaskService(session)
        result = await service.complete_task(
            user=user,  # type: ignore[arg-type]
            intent=CompleteTaskIntent(type="complete_task", task_title="несуществующая"),
        )

    assert "не найдена" in result.lower()


@pytest.mark.asyncio
async def test_delete_task() -> None:
    session = AsyncMock()
    user = _make_user()
    task = _make_task(5, "Удалить меня")

    with patch("bot.services.tasks.TaskRepo") as MockRepo:
        repo_instance = MockRepo.return_value
        repo_instance.get_by_user = AsyncMock(return_value=[task])
        repo_instance.delete = AsyncMock()

        service = TaskService(session)
        result = await service.delete_task(
            user=user,  # type: ignore[arg-type]
            intent=DeleteTaskIntent(type="delete_task", task_title="Удалить меня"),
        )

    assert "удалена" in result.lower()


@pytest.mark.asyncio
async def test_get_tasks_empty() -> None:
    session = AsyncMock()
    user = _make_user()

    with patch("bot.services.tasks.TaskRepo") as MockRepo:
        repo_instance = MockRepo.return_value
        repo_instance.get_by_user = AsyncMock(return_value=[])

        service = TaskService(session)
        result = await service.get_tasks_for_user(
            user=user,  # type: ignore[arg-type]
            intent=ListTasksIntent(type="list_tasks"),
        )

    assert "нет активных задач" in result.lower()


@pytest.mark.asyncio
async def test_get_tasks_high_priority_filter() -> None:
    session = AsyncMock()
    user = _make_user()
    tasks = [
        _make_task(1, "Важная задача", priority=Priority.HIGH),
        _make_task(2, "Обычная задача", priority=Priority.MEDIUM),
    ]

    with patch("bot.services.tasks.TaskRepo") as MockRepo:
        repo_instance = MockRepo.return_value
        repo_instance.get_by_user = AsyncMock(return_value=tasks)

        service = TaskService(session)
        result = await service.get_tasks_for_user(
            user=user,  # type: ignore[arg-type]
            intent=ListTasksIntent(type="list_tasks", filter="high_priority"),
        )

    assert "Важная задача" in result
    assert "Обычная задача" not in result


@pytest.mark.asyncio
async def test_create_task_matches_list_name() -> None:
    session = AsyncMock()
    user = _make_user()
    lists = [_make_list(1, "Работа"), _make_list(2, "Дом")]
    created_task = _make_task(10, "Новая задача домашняя", list_id=2)

    with patch("bot.services.tasks.TaskRepo") as MockRepo:
        repo_instance = MockRepo.return_value
        repo_instance.get_lists_by_user = AsyncMock(return_value=lists)
        repo_instance.create = AsyncMock(return_value=created_task)

        service = TaskService(session)
        await service.create_task(
            user=user,  # type: ignore[arg-type]
            intent=CreateTaskIntent(type="create_task", title="Новая задача", list_name="Дом"),
        )

    # Verify it searched for "дом" in list names
    call_kwargs = repo_instance.create.call_args
    assert call_kwargs.kwargs["list_id"] == 2


# ---------------------------------------------------------------------------
# complete_task / delete_task — ambiguous match
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_task_ambiguous_match_no_complete_called() -> None:
    """When multiple tasks match, complete is NOT called and disambiguation returned."""
    session = AsyncMock()
    user = _make_user()
    tasks = [
        _make_task(1, "Купить молоко"),
        _make_task(2, "Купить хлеб"),
    ]

    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=tasks)
    repo.complete = AsyncMock()

    service = TaskService(session, repo=repo)
    result = await service.complete_task(
        user=user,  # type: ignore[arg-type]
        intent=CompleteTaskIntent(type="complete_task", task_title="купить"),
    )

    repo.complete.assert_not_called()
    assert "Найдено несколько" in result
    assert "Купить молоко" in result
    assert "Купить хлеб" in result


@pytest.mark.asyncio
async def test_delete_task_ambiguous_match_no_delete_called() -> None:
    """When multiple tasks match, delete is NOT called and disambiguation returned."""
    session = AsyncMock()
    user = _make_user()
    tasks = [
        _make_task(1, "Отправить отчёт"),
        _make_task(2, "Отправить письмо"),
    ]

    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=tasks)
    repo.delete = AsyncMock()

    service = TaskService(session, repo=repo)
    result = await service.delete_task(
        user=user,  # type: ignore[arg-type]
        intent=DeleteTaskIntent(type="delete_task", task_title="отправить"),
    )

    repo.delete.assert_not_called()
    assert "Найдено несколько" in result


# ---------------------------------------------------------------------------
# update_task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_task_change_title() -> None:
    session = AsyncMock()
    user = _make_user()
    task = _make_task(1, "Старое название")

    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=[task])
    repo.update = AsyncMock()

    service = TaskService(session, repo=repo)
    result = await service.update_task(
        user=user,  # type: ignore[arg-type]
        intent=UpdateTaskIntent(type="update_task", task_title="Старое название", new_title="Новое название"),
    )

    repo.update.assert_called_once()
    call_kwargs = repo.update.call_args.kwargs
    assert call_kwargs.get("title") == "Новое название"
    assert "обновлена" in result.lower()


@pytest.mark.asyncio
async def test_update_task_move_to_list() -> None:
    session = AsyncMock()
    user = _make_user()
    task = _make_task(1, "Задача")
    lists = [_make_list(1, "Работа"), _make_list(2, "Личное")]

    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=[task])
    repo.get_lists_by_user = AsyncMock(return_value=lists)
    repo.move_to_list = AsyncMock()
    repo.update = AsyncMock()

    service = TaskService(session, repo=repo)
    result = await service.update_task(
        user=user,  # type: ignore[arg-type]
        intent=UpdateTaskIntent(type="update_task", task_title="Задача", new_list_name="Личное"),
    )

    repo.move_to_list.assert_called_once_with(task, 2)
    assert "обновлена" in result.lower()


@pytest.mark.asyncio
async def test_update_task_not_found() -> None:
    session = AsyncMock()
    user = _make_user()

    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=[])

    service = TaskService(session, repo=repo)
    result = await service.update_task(
        user=user,  # type: ignore[arg-type]
        intent=UpdateTaskIntent(type="update_task", task_title="Несуществующая"),
    )

    assert "не найдена" in result.lower()


# ---------------------------------------------------------------------------
# create_default_lists
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_default_lists_already_has_lists_no_create_called() -> None:
    session = AsyncMock()
    existing_lists = [_make_list(1, "Работа")]

    repo = AsyncMock()
    repo.get_lists_by_user = AsyncMock(return_value=existing_lists)
    repo.create_list = AsyncMock()

    service = TaskService(session, repo=repo)
    await service.create_default_lists(user_id=42)

    repo.create_list.assert_not_called()


@pytest.mark.asyncio
async def test_create_default_lists_no_lists_creates_three() -> None:
    session = AsyncMock()

    repo = AsyncMock()
    repo.get_lists_by_user = AsyncMock(return_value=[])
    repo.create_list = AsyncMock()

    service = TaskService(session, repo=repo)
    await service.create_default_lists(user_id=42)

    assert repo.create_list.call_count == len(DEFAULT_LISTS)


# ---------------------------------------------------------------------------
# get_tasks_for_user — overdue and today filters
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_tasks_filter_overdue_returns_only_past_due() -> None:
    now = now_utc()
    session = AsyncMock()
    user = _make_user()
    overdue_task = _make_task(1, "Просроченная задача")
    overdue_task = SimpleNamespace(**{**overdue_task.__dict__, "due_date": now - timedelta(days=2)})
    future_task = _make_task(2, "Будущая задача")
    future_task = SimpleNamespace(**{**future_task.__dict__, "due_date": now + timedelta(days=2)})

    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=[overdue_task, future_task])

    service = TaskService(session, repo=repo)
    result = await service.get_tasks_for_user(
        user=user,  # type: ignore[arg-type]
        intent=ListTasksIntent(type="list_tasks", filter="overdue"),
    )

    assert "Просроченная задача" in result
    assert "Будущая задача" not in result


@pytest.mark.asyncio
async def test_get_tasks_filter_today_returns_only_today_tasks() -> None:
    now = now_utc()
    session = AsyncMock()
    user = _make_user()
    today_task = _make_task(1, "Сегодняшняя задача")
    today_task = SimpleNamespace(**{**today_task.__dict__, "due_date": now.replace(hour=14, minute=0, second=0)})
    tomorrow_task = _make_task(2, "Завтрашняя задача")
    tomorrow_task = SimpleNamespace(**{**tomorrow_task.__dict__, "due_date": now + timedelta(days=1)})

    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=[today_task, tomorrow_task])

    service = TaskService(session, repo=repo)
    result = await service.get_tasks_for_user(
        user=user,  # type: ignore[arg-type]
        intent=ListTasksIntent(type="list_tasks", filter="today"),
    )

    assert "Сегодняшняя задача" in result
    assert "Завтрашняя задача" not in result


# ---------------------------------------------------------------------------
# create_task_smart — list auto-classification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_task_smart_single_list_auto_assigned() -> None:
    """Single list → auto_assigned=True, low_confidence=False."""
    session = AsyncMock()
    user = _make_user()
    task_list = _make_list(1, "Работа")
    created_task = _make_task(10, "Новая задача")

    repo = AsyncMock()
    repo.get_lists_by_user = AsyncMock(return_value=[task_list])
    repo.create = AsyncMock(return_value=created_task)

    service = TaskService(session, repo=repo)
    result = await service.create_task_smart(
        user=user,  # type: ignore[arg-type]
        intent=CreateTaskIntent(type="create_task", title="Новая задача"),
    )

    from bot.services.tasks import TaskCreateResult
    assert isinstance(result, TaskCreateResult)
    assert result.auto_assigned is True
    assert result.low_confidence is False
    assert result.task.title == "Новая задача"


@pytest.mark.asyncio
async def test_create_task_smart_no_lists_returns_error_string() -> None:
    """No lists → returns error string."""
    session = AsyncMock()
    user = _make_user()

    repo = AsyncMock()
    repo.get_lists_by_user = AsyncMock(return_value=[])

    service = TaskService(session, repo=repo)
    result = await service.create_task_smart(
        user=user,  # type: ignore[arg-type]
        intent=CreateTaskIntent(type="create_task", title="Задача"),
    )

    assert isinstance(result, str)
    assert "нет списков" in result.lower()


@pytest.mark.asyncio
async def test_create_task_smart_high_confidence_uses_suggested_list() -> None:
    """High confidence + suggested_list_id → uses that list, auto_assigned=True."""
    session = AsyncMock()
    user = _make_user()
    lists = [_make_list(1, "Работа"), _make_list(2, "Дом")]
    created_task = _make_task(10, "Задача", list_id=2)

    repo = AsyncMock()
    repo.get_lists_by_user = AsyncMock(return_value=lists)
    repo.create = AsyncMock(return_value=created_task)

    service = TaskService(session, repo=repo)
    from bot.services.tasks import TaskCreateResult
    result = await service.create_task_smart(
        user=user,  # type: ignore[arg-type]
        intent=CreateTaskIntent(
            type="create_task",
            title="Задача",
            suggested_list_id=2,
            list_confidence=0.9,
        ),
    )

    assert isinstance(result, TaskCreateResult)
    assert result.auto_assigned is True
    assert result.low_confidence is False
    # Should have created in list 2
    create_kwargs = repo.create.call_args.kwargs
    assert create_kwargs["list_id"] == 2


@pytest.mark.asyncio
async def test_create_task_smart_low_confidence_multiple_lists() -> None:
    """Low confidence with multiple lists → low_confidence=True."""
    session = AsyncMock()
    user = _make_user()
    lists = [_make_list(1, "Работа"), _make_list(2, "Дом")]
    created_task = _make_task(10, "Задача", list_id=1)

    repo = AsyncMock()
    repo.get_lists_by_user = AsyncMock(return_value=lists)
    repo.create = AsyncMock(return_value=created_task)

    service = TaskService(session, repo=repo)
    from bot.services.tasks import TaskCreateResult
    result = await service.create_task_smart(
        user=user,  # type: ignore[arg-type]
        intent=CreateTaskIntent(
            type="create_task",
            title="Задача",
            suggested_list_id=1,
            list_confidence=0.5,  # below 0.8
        ),
    )

    assert isinstance(result, TaskCreateResult)
    assert result.low_confidence is True


@pytest.mark.asyncio
async def test_create_task_smart_no_suggestion_multiple_lists_low_confidence() -> None:
    """No suggested_list_id with multiple lists → low_confidence=True, uses first list."""
    session = AsyncMock()
    user = _make_user()
    lists = [_make_list(1, "Работа"), _make_list(2, "Дом")]
    created_task = _make_task(10, "Сделать кое-что")

    repo = AsyncMock()
    repo.get_lists_by_user = AsyncMock(return_value=lists)
    repo.create = AsyncMock(return_value=created_task)

    service = TaskService(session, repo=repo)
    from bot.services.tasks import TaskCreateResult
    result = await service.create_task_smart(
        user=user,  # type: ignore[arg-type]
        intent=CreateTaskIntent(type="create_task", title="Сделать кое-что"),
    )

    assert isinstance(result, TaskCreateResult)
    assert result.low_confidence is True


@pytest.mark.asyncio
async def test_create_task_smart_priority_preserved() -> None:
    """Priority from intent is passed to repo.create."""
    session = AsyncMock()
    user = _make_user()
    task_list = _make_list(1)
    created_task = _make_task(1, "Срочная задача", priority=Priority.HIGH)

    repo = AsyncMock()
    repo.get_lists_by_user = AsyncMock(return_value=[task_list])
    repo.create = AsyncMock(return_value=created_task)

    service = TaskService(session, repo=repo)
    await service.create_task_smart(
        user=user,  # type: ignore[arg-type]
        intent=CreateTaskIntent(type="create_task", title="Срочная задача", priority="high"),
    )

    create_kwargs = repo.create.call_args.kwargs
    assert create_kwargs["priority"] == "high"


@pytest.mark.asyncio
async def test_create_task_with_scheduled_at() -> None:
    """scheduled_at from intent is passed through to repo.create."""
    from datetime import timezone
    session = AsyncMock()
    user = _make_user()
    task_list = _make_list(1)
    scheduled = now_utc().replace(hour=15, minute=0, second=0, microsecond=0)
    created_task = _make_task(1, "Задача с расписанием")

    repo = AsyncMock()
    repo.get_lists_by_user = AsyncMock(return_value=[task_list])
    repo.create = AsyncMock(return_value=created_task)

    service = TaskService(session, repo=repo)
    await service.create_task_smart(
        user=user,  # type: ignore[arg-type]
        intent=CreateTaskIntent(
            type="create_task",
            title="Задача с расписанием",
            scheduled_at=scheduled,
        ),
    )

    create_kwargs = repo.create.call_args.kwargs
    assert create_kwargs["scheduled_at"] == scheduled
