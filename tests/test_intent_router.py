"""Tests for IntentRouter — routing logic, _summarize, execute_confirmed."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.db.models import AIModel
from bot.services.intent.models import (
    AIChatIntent,
    CreateTaskIntent,
    DeleteTaskIntent,
    ListTasksIntent,
    ParsedResponse,
)
from bot.services.intent.router import IntentRouter
from bot.services.tasks import TaskCreateResult


def _make_task_create_result(title: str = "Купить молоко") -> TaskCreateResult:
    """Build a TaskCreateResult with a mock task for testing."""
    task = SimpleNamespace(id=1, title=title, due_date=None, list_id=1)
    task_list = SimpleNamespace(id=1, name="Работа", emoji="💼")
    return TaskCreateResult(
        task=task,  # type: ignore[arg-type]
        target_list=task_list,  # type: ignore[arg-type]
        auto_assigned=True,
        low_confidence=False,
    )


def _make_user(ai_model: str = AIModel.CLAUDE) -> SimpleNamespace:
    return SimpleNamespace(id=1, timezone="Europe/Moscow", ai_model=ai_model)


def _make_message() -> AsyncMock:
    msg = AsyncMock()
    msg.answer = AsyncMock()
    return msg


def _make_router() -> tuple[IntentRouter, dict[str, AsyncMock]]:
    """Build IntentRouter with all 5 services mocked."""
    mocks: dict[str, AsyncMock] = {
        "task_service": AsyncMock(),
        "calendar_service": AsyncMock(),
        "reminder_service": AsyncMock(),
        "briefing_service": AsyncMock(),
        "analytics_service": AsyncMock(),
    }
    # Inject dummy AI clients to avoid any real network calls
    anthropic_mock = AsyncMock()
    openai_mock = AsyncMock()

    router = IntentRouter(
        task_service=mocks["task_service"],  # type: ignore[arg-type]
        calendar_service=mocks["calendar_service"],  # type: ignore[arg-type]
        reminder_service=mocks["reminder_service"],  # type: ignore[arg-type]
        briefing_service=mocks["briefing_service"],  # type: ignore[arg-type]
        analytics_service=mocks["analytics_service"],  # type: ignore[arg-type]
        anthropic_client=anthropic_mock,  # type: ignore[arg-type]
        openai_client=openai_mock,  # type: ignore[arg-type]
    )
    return router, mocks


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_route_clarification_needed_answers_and_returns() -> None:
    """When clarification_needed is set, answer with the text and do NOT dispatch."""
    router, mocks = _make_router()
    user = _make_user()
    message = _make_message()

    parsed = ParsedResponse(
        intents=[CreateTaskIntent(type="create_task", title="Задача")],
        confidence=0.95,
        clarification_needed="Уточните список.",
    )
    await router.route(parsed, user, message)  # type: ignore[arg-type]

    message.answer.assert_called_once_with("Уточните список.")
    mocks["task_service"].create_task.assert_not_called()


@pytest.mark.asyncio
async def test_route_low_confidence_asks_confirmation_no_state() -> None:
    """Low confidence without FSM state → fallback message with summary."""
    router, mocks = _make_router()
    user = _make_user()
    message = _make_message()

    parsed = ParsedResponse(
        intents=[CreateTaskIntent(type="create_task", title="Новая задача")],
        confidence=0.5,
        clarification_needed=None,
    )
    await router.route(parsed, user, message, state=None)  # type: ignore[arg-type]

    message.answer.assert_called_once()
    call_text = message.answer.call_args[0][0]
    assert "Новая задача" in call_text
    mocks["task_service"].create_task.assert_not_called()


@pytest.mark.asyncio
async def test_route_destructive_asks_confirmation_no_state() -> None:
    """Destructive intent always asks confirmation regardless of confidence."""
    router, mocks = _make_router()
    user = _make_user()
    message = _make_message()

    parsed = ParsedResponse(
        intents=[DeleteTaskIntent(type="delete_task", task_title="Задача")],
        confidence=0.99,
        clarification_needed=None,
    )
    await router.route(parsed, user, message, state=None)  # type: ignore[arg-type]

    message.answer.assert_called_once()
    call_text = message.answer.call_args[0][0]
    assert "Задача" in call_text
    mocks["task_service"].delete_task.assert_not_called()


@pytest.mark.asyncio
async def test_route_high_confidence_nondestruct_dispatches_create_task() -> None:
    """High confidence, non-destructive → create_task_smart is called and success message sent."""
    router, mocks = _make_router()
    user = _make_user()
    message = _make_message()

    mocks["task_service"].create_task_smart = AsyncMock(
        return_value=_make_task_create_result("Купить молоко")
    )
    mocks["task_service"].get_lists = AsyncMock(return_value=[])

    parsed = ParsedResponse(
        intents=[CreateTaskIntent(type="create_task", title="Купить молоко")],
        confidence=0.95,
        clarification_needed=None,
    )
    await router.route(parsed, user, message)  # type: ignore[arg-type]

    mocks["task_service"].create_task_smart.assert_called_once()
    # A message was sent (either success or list selection)
    message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_route_multiple_intents_all_dispatched_in_order() -> None:
    """Multiple intents in one ParsedResponse → each service called in order."""
    router, mocks = _make_router()
    user = _make_user()
    message = _make_message()

    call_order: list[str] = []

    async def create_task_smart_side_effect(**_kwargs: object) -> TaskCreateResult:
        call_order.append("create_task")
        return _make_task_create_result("Задача 1")

    async def get_tasks_side_effect(**_kwargs: object) -> str:
        call_order.append("list_tasks")
        return "<b>Задачи:</b>"

    mocks["task_service"].create_task_smart = AsyncMock(side_effect=create_task_smart_side_effect)
    mocks["task_service"].get_lists = AsyncMock(return_value=[])
    mocks["task_service"].get_tasks_for_user = AsyncMock(side_effect=get_tasks_side_effect)

    parsed = ParsedResponse(
        intents=[
            CreateTaskIntent(type="create_task", title="Задача 1"),
            ListTasksIntent(type="list_tasks"),
        ],
        confidence=0.95,
        clarification_needed=None,
    )
    await router.route(parsed, user, message)  # type: ignore[arg-type]

    assert call_order == ["create_task", "list_tasks"]
    assert message.answer.call_count == 2


@pytest.mark.asyncio
async def test_route_with_state_calls_ask_confirmation() -> None:
    """Low confidence with state → ask_confirmation is called."""
    router, mocks = _make_router()
    user = _make_user()
    message = _make_message()
    state = AsyncMock()

    parsed = ParsedResponse(
        intents=[CreateTaskIntent(type="create_task", title="Что-то")],
        confidence=0.5,
        clarification_needed=None,
    )

    with patch("bot.handlers.confirm_intent.ask_confirmation", new=AsyncMock()) as mock_ask:
        await router.route(parsed, user, message, state=state)  # type: ignore[arg-type]
        mock_ask.assert_called_once()


# ---------------------------------------------------------------------------
# _summarize
# ---------------------------------------------------------------------------

def test_summarize_create_task_intent() -> None:
    router, _ = _make_router()
    parsed = ParsedResponse(
        intents=[CreateTaskIntent(type="create_task", title="Купить молоко")],
        confidence=0.9,
    )
    result = router._summarize(parsed)
    assert "Создать задачу" in result
    assert "Купить молоко" in result


def test_summarize_delete_task_intent() -> None:
    router, _ = _make_router()
    parsed = ParsedResponse(
        intents=[DeleteTaskIntent(type="delete_task", task_title="Задача")],
        confidence=0.9,
    )
    result = router._summarize(parsed)
    assert "Удалить задачу" in result
    assert "Задача" in result


def test_summarize_ai_chat_truncated_at_60_chars() -> None:
    router, _ = _make_router()
    long_msg = "А" * 80
    parsed = ParsedResponse(
        intents=[AIChatIntent(type="ai_chat", message=long_msg)],
        confidence=1.0,
    )
    result = router._summarize(parsed)
    assert "Диалог" in result
    # The message in the summary should be truncated (showing at most 60 chars of the message)
    assert long_msg not in result  # full 80 chars not in result
    assert "А" * 60 in result  # exactly 60 chars ARE in result


def test_summarize_mixed_intents_multiline() -> None:
    router, _ = _make_router()
    parsed = ParsedResponse(
        intents=[
            CreateTaskIntent(type="create_task", title="Задача 1"),
            DeleteTaskIntent(type="delete_task", task_title="Задача 2"),
        ],
        confidence=0.9,
    )
    result = router._summarize(parsed)
    lines = result.split("\n")
    assert len(lines) == 2
    assert any("Создать" in ln for ln in lines)
    assert any("Удалить" in ln for ln in lines)


# ---------------------------------------------------------------------------
# execute_confirmed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_confirmed_bypasses_confidence_check() -> None:
    """execute_confirmed dispatches directly even for low-confidence parsed."""
    router, mocks = _make_router()
    user = _make_user()
    message = _make_message()

    mocks["task_service"].create_task_smart = AsyncMock(
        return_value=_make_task_create_result("Задача")
    )
    mocks["task_service"].get_lists = AsyncMock(return_value=[])

    parsed = ParsedResponse(
        intents=[CreateTaskIntent(type="create_task", title="Задача")],
        confidence=0.1,  # would normally trigger confirmation
        clarification_needed=None,
    )
    await router.execute_confirmed(parsed, user, message)  # type: ignore[arg-type]

    mocks["task_service"].create_task_smart.assert_called_once()
    # A message was sent (task confirmation)
    message.answer.assert_called_once()
