from bot.utils.dt import now_utc
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.db.models import AIModel, Priority
from bot.services.intent.models import (
    CompleteTaskIntent,
    CreateTaskIntent,
    DeleteTaskIntent,
    ListTasksIntent,
)
from bot.services.tasks import TaskService


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
        result = await service.create_task(
            user=user,  # type: ignore[arg-type]
            intent=CreateTaskIntent(type="create_task", title="Новая задача", list_name="Дом"),
        )

    # Verify it searched for "дом" in list names
    call_kwargs = repo_instance.create.call_args
    assert call_kwargs.kwargs["list_id"] == 2
