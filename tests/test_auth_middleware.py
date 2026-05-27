"""Tests for AuthMiddleware."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.middlewares.auth import AuthMiddleware


def _make_handler() -> AsyncMock:
    handler = AsyncMock(return_value="OK")
    return handler


def _make_event() -> AsyncMock:
    """Return a mock TelegramObject (not a Message)."""
    event = AsyncMock()
    # Make isinstance(event, Message) return False
    event.__class__ = MagicMock()
    return event


def _make_message_event() -> AsyncMock:
    """Return a mock that passes isinstance(event, Message) checks."""
    from aiogram.types import Message
    event = AsyncMock(spec=Message)
    event.answer = AsyncMock()
    return event


def _make_data_with_user(user_id: int) -> dict[str, Any]:
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    return {"event_update": update}


def _make_data_no_user() -> dict[str, Any]:
    update = MagicMock()
    update.effective_user = None
    return {"event_update": update}


@pytest.mark.asyncio
async def test_no_whitelist_configured_allows_all() -> None:
    """When allowed_user_ids is empty, handler is called."""
    middleware = AuthMiddleware()
    handler = _make_handler()
    event = _make_event()
    data = _make_data_with_user(12345)

    with patch("bot.middlewares.auth.settings") as mock_settings:
        mock_settings.allowed_user_ids = []
        result = await middleware(handler, event, data)

    handler.assert_called_once_with(event, data)
    assert result == "OK"


@pytest.mark.asyncio
async def test_user_in_whitelist_handler_called() -> None:
    """User in whitelist → handler is called."""
    middleware = AuthMiddleware()
    handler = _make_handler()
    event = _make_event()
    data = _make_data_with_user(42)

    with patch("bot.middlewares.auth.settings") as mock_settings:
        mock_settings.allowed_user_ids = [42, 100]
        result = await middleware(handler, event, data)

    handler.assert_called_once_with(event, data)
    assert result == "OK"


@pytest.mark.asyncio
async def test_user_not_in_whitelist_handler_not_called() -> None:
    """User NOT in whitelist → handler NOT called, returns None."""
    middleware = AuthMiddleware()
    handler = _make_handler()
    event = _make_event()
    data = _make_data_with_user(999)

    with patch("bot.middlewares.auth.settings") as mock_settings:
        mock_settings.allowed_user_ids = [42, 100]
        result = await middleware(handler, event, data)

    handler.assert_not_called()
    assert result is None


@pytest.mark.asyncio
async def test_user_not_in_whitelist_message_event_answers_access_denied() -> None:
    """Blocked user with a Message event → event.answer called with denial text."""
    middleware = AuthMiddleware()
    handler = _make_handler()
    event = _make_message_event()
    data = _make_data_with_user(999)

    with patch("bot.middlewares.auth.settings") as mock_settings:
        mock_settings.allowed_user_ids = [42]
        await middleware(handler, event, data)

    event.answer.assert_called_once_with("У вас нет доступа к этому боту.")
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_no_user_in_update_handler_called_passthrough() -> None:
    """Non-user update (user_id is None) → handler called as pass-through."""
    middleware = AuthMiddleware()
    handler = _make_handler()
    event = _make_event()
    data = _make_data_no_user()

    with patch("bot.middlewares.auth.settings") as mock_settings:
        mock_settings.allowed_user_ids = [42]
        result = await middleware(handler, event, data)

    handler.assert_called_once_with(event, data)
    assert result == "OK"
