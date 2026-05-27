import os
from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

# Set dummy env vars before any bot imports so pydantic-settings can construct Settings
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0:test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic")
os.environ.setdefault("OPENAI_API_KEY", "test-openai")
os.environ.setdefault("POSTGRES_DSN", "postgresql+asyncpg://user:pass@localhost/test")
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleQ==")

from bot.db.models import AIModel  # noqa: E402


@pytest.fixture
def mock_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=123456789,
        first_name="Test",
        username="testuser",
        timezone="Europe/Moscow",
        ai_model=AIModel.CLAUDE,
        briefing_time=time(8, 0),
        is_active=True,
    )


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def mock_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.get_file = AsyncMock()
    bot.download_file = AsyncMock()
    return bot
