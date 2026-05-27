from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bot.db.models import AIModel
from bot.services.ai.clients import AIClients


def _make_user(ai_model: str) -> SimpleNamespace:
    return SimpleNamespace(ai_model=ai_model)


def test_get_for_user_returns_anthropic_for_claude_model() -> None:
    mock_anthropic = MagicMock()
    mock_openai = MagicMock()
    clients = AIClients(anthropic_client=mock_anthropic, openai_client=mock_openai)

    user = _make_user(AIModel.CLAUDE)
    result = clients.get_for_user(user)

    assert result is mock_anthropic


def test_get_for_user_returns_openai_for_gpt4o() -> None:
    mock_anthropic = MagicMock()
    mock_openai = MagicMock()
    clients = AIClients(anthropic_client=mock_anthropic, openai_client=mock_openai)

    user = _make_user(AIModel.GPT4O)
    result = clients.get_for_user(user)

    assert result is mock_openai


def test_lazy_init_anthropic() -> None:
    """Anthropic client is created only on first call to get_anthropic()."""
    clients = AIClients()

    mock_instance = MagicMock()
    with patch("anthropic.AsyncAnthropic", return_value=mock_instance) as mock_cls:
        # First call — should construct
        result1 = clients.get_anthropic()
        assert mock_cls.call_count == 1
        assert result1 is mock_instance

        # Second call — should reuse cached instance
        result2 = clients.get_anthropic()
        assert mock_cls.call_count == 1
        assert result2 is mock_instance


def test_lazy_init_openai() -> None:
    """OpenAI client is created only on first call to get_openai()."""
    clients = AIClients()

    mock_instance = MagicMock()
    with patch("openai.AsyncOpenAI", return_value=mock_instance) as mock_cls:
        # First call — should construct
        result1 = clients.get_openai()
        assert mock_cls.call_count == 1
        assert result1 is mock_instance

        # Second call — should reuse cached instance
        result2 = clients.get_openai()
        assert mock_cls.call_count == 1
        assert result2 is mock_instance
