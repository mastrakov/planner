from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import anthropic
    from openai import AsyncOpenAI

    from bot.db.models import User


class AIClients:
    """Lazy-initialized pair of AI clients, shared across services."""

    def __init__(
        self,
        anthropic_client: anthropic.AsyncAnthropic | None = None,
        openai_client: AsyncOpenAI | None = None,
    ) -> None:
        self._anthropic_client = anthropic_client
        self._openai_client = openai_client

    def get_anthropic(self) -> anthropic.AsyncAnthropic:
        if self._anthropic_client is None:
            import anthropic as _anthropic

            from bot.config import settings

            self._anthropic_client = _anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._anthropic_client

    def get_openai(self) -> AsyncOpenAI:
        if self._openai_client is None:
            from openai import AsyncOpenAI

            from bot.config import settings

            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    def get_for_user(self, user: User) -> anthropic.AsyncAnthropic | AsyncOpenAI:
        """Return the correct client based on user.ai_model."""
        from bot.db.models import AIModel

        if user.ai_model == AIModel.GPT4O:
            return self.get_openai()
        return self.get_anthropic()
