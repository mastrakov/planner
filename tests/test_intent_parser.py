import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.db.models import AIModel
from bot.services.intent.models import (
    AIChatIntent,
    CreateTaskIntent,
    ParsedResponse,
)
from bot.services.intent.parser import IntentParser


def _make_user(ai_model: str = AIModel.CLAUDE) -> SimpleNamespace:
    return SimpleNamespace(id=1, timezone="Europe/Moscow", ai_model=ai_model)


@pytest.mark.asyncio
async def test_parse_create_task_via_claude() -> None:
    task_repo = AsyncMock()
    task_repo.get_lists_by_user = AsyncMock(return_value=[])

    response_json = json.dumps({
        "intents": [{"type": "create_task", "title": "Купить молоко", "priority": "low"}],
        "confidence": 0.95,
        "clarification_needed": None,
    })

    with patch("bot.services.intent.parser._anthropic_client") as mock_client:
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=response_json)]
        mock_client.messages.create = AsyncMock(return_value=mock_msg)

        parser = IntentParser(task_repo)
        result = await parser.parse("Купить молоко", _make_user(AIModel.CLAUDE), [])  # type: ignore[arg-type]

    assert isinstance(result, ParsedResponse)
    assert len(result.intents) == 1
    intent = result.intents[0]
    assert isinstance(intent, CreateTaskIntent)
    assert intent.title == "Купить молоко"
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_parse_create_task_via_gpt4o() -> None:
    task_repo = AsyncMock()
    task_repo.get_lists_by_user = AsyncMock(return_value=[])

    response_json = json.dumps({
        "intents": [{"type": "create_task", "title": "Сдать отчёт", "priority": "high"}],
        "confidence": 0.9,
        "clarification_needed": None,
    })

    with patch("bot.services.intent.parser._openai_client") as mock_client:
        mock_choice = MagicMock()
        mock_choice.message.content = response_json
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        parser = IntentParser(task_repo)
        result = await parser.parse("Сдать отчёт", _make_user(AIModel.GPT4O), [])  # type: ignore[arg-type]

    assert isinstance(result, ParsedResponse)
    intent = result.intents[0]
    assert isinstance(intent, CreateTaskIntent)
    assert intent.priority == "high"


@pytest.mark.asyncio
async def test_parse_falls_back_to_ai_chat_on_error() -> None:
    task_repo = AsyncMock()
    task_repo.get_lists_by_user = AsyncMock(return_value=[])

    with patch("bot.services.intent.parser._anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))

        parser = IntentParser(task_repo)
        result = await parser.parse("Как дела?", _make_user(AIModel.CLAUDE), [])  # type: ignore[arg-type]

    assert isinstance(result, ParsedResponse)
    assert len(result.intents) == 1
    assert isinstance(result.intents[0], AIChatIntent)
    assert result.intents[0].message == "Как дела?"


@pytest.mark.asyncio
async def test_parse_invalid_json_falls_back_to_ai_chat() -> None:
    task_repo = AsyncMock()
    task_repo.get_lists_by_user = AsyncMock(return_value=[])

    with patch("bot.services.intent.parser._anthropic_client") as mock_client:
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="not valid json")]
        mock_client.messages.create = AsyncMock(return_value=mock_msg)

        parser = IntentParser(task_repo)
        result = await parser.parse("что-то", _make_user(AIModel.CLAUDE), [])  # type: ignore[arg-type]

    assert isinstance(result.intents[0], AIChatIntent)


@pytest.mark.asyncio
async def test_parse_clarification_needed() -> None:
    task_repo = AsyncMock()
    task_repo.get_lists_by_user = AsyncMock(return_value=[])

    response_json = json.dumps({
        "intents": [{"type": "create_task", "title": "Задача", "priority": "medium"}],
        "confidence": 0.6,
        "clarification_needed": "Уточните в какой список добавить задачу.",
    })

    with patch("bot.services.intent.parser._anthropic_client") as mock_client:
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=response_json)]
        mock_client.messages.create = AsyncMock(return_value=mock_msg)

        parser = IntentParser(task_repo)
        result = await parser.parse("Задача", _make_user(AIModel.CLAUDE), [])  # type: ignore[arg-type]

    assert result.confidence == 0.6
    assert result.clarification_needed == "Уточните в какой список добавить задачу."


@pytest.mark.asyncio
async def test_parse_system_prompt_includes_list_names() -> None:
    task_repo = AsyncMock()
    list_ns = SimpleNamespace(id=1, name="Работа", emoji="💼")
    task_repo.get_lists_by_user = AsyncMock(return_value=[list_ns])

    response_json = json.dumps({
        "intents": [{"type": "ai_chat", "message": "hi"}],
        "confidence": 1.0,
        "clarification_needed": None,
    })

    with patch("bot.services.intent.parser._anthropic_client") as mock_client:
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=response_json)]
        mock_client.messages.create = AsyncMock(return_value=mock_msg)

        parser = IntentParser(task_repo)
        await parser.parse("привет", _make_user(AIModel.CLAUDE), [])  # type: ignore[arg-type]

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "Работа" in call_kwargs["system"]
