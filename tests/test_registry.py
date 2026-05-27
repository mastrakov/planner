"""Tests for IntegrationRegistry."""

import pytest

from bot.services.integrations.registry import IntegrationRegistry


def _make_provider() -> object:
    """Create a minimal mock CalendarProvider (duck typing, no ABC enforcement)."""
    from unittest.mock import AsyncMock
    provider = AsyncMock()
    return provider


def test_register_and_has_calendar() -> None:
    registry = IntegrationRegistry()
    provider = _make_provider()
    registry.register_calendar("google", provider)  # type: ignore[arg-type]
    assert registry.has_calendar("google") is True


def test_has_calendar_unregistered_returns_false() -> None:
    registry = IntegrationRegistry()
    assert registry.has_calendar("unknown") is False


def test_get_calendar_registered_returns_provider() -> None:
    registry = IntegrationRegistry()
    provider = _make_provider()
    registry.register_calendar("google", provider)  # type: ignore[arg-type]
    result = registry.get_calendar("google")
    assert result is provider


def test_get_calendar_unregistered_raises_key_error() -> None:
    registry = IntegrationRegistry()
    with pytest.raises(KeyError):
        registry.get_calendar("nonexistent")


def test_register_multiple_providers() -> None:
    registry = IntegrationRegistry()
    p1 = _make_provider()
    p2 = _make_provider()
    registry.register_calendar("google", p1)  # type: ignore[arg-type]
    registry.register_calendar("outlook", p2)  # type: ignore[arg-type]
    assert registry.has_calendar("google")
    assert registry.has_calendar("outlook")
    assert registry.get_calendar("google") is p1
    assert registry.get_calendar("outlook") is p2
