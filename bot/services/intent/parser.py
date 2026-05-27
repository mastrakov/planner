from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytz

from bot.config import settings
from bot.db.models import AIModel, ChatHistory, User
from bot.db.repo.tasks import TaskRepo
from bot.services.intent.models import ParsedResponse
from bot.services.intent.prompts import build_system_prompt

if TYPE_CHECKING:
    import anthropic
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


def _current_dt_for_user(tz_name: str) -> datetime:
    """Return current local time for the user, WITH tzinfo so the prompt includes the UTC offset."""
    tz = pytz.timezone(tz_name)
    return datetime.now(tz=UTC).astimezone(tz)


def _history_to_messages(history: list[ChatHistory]) -> list[dict[str, str]]:
    return [{"role": h.role, "content": h.content} for h in history]


async def _parse_with_claude(
    client: anthropic.AsyncAnthropic,
    system: str,
    messages: list[dict[str, str]],
    text: str,
) -> str:
    all_messages = messages + [{"role": "user", "content": text}]
    logger.debug("Claude request: history_len=%d text=%r", len(messages), text)
    response = await client.messages.create(
        model=settings.claude_model,
        max_tokens=1024,
        system=system,
        messages=all_messages,  # type: ignore[arg-type]
    )
    raw = response.content[0].text  # type: ignore[union-attr]
    logger.debug("Claude response: %s", raw)
    return raw


async def _parse_with_gpt4o(
    client: AsyncOpenAI,
    system: str,
    messages: list[dict[str, str]],
    text: str,
) -> str:
    all_messages = [{"role": "system", "content": system}] + messages + [{"role": "user", "content": text}]
    logger.debug("GPT-4o request: history_len=%d text=%r", len(messages), text)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        max_tokens=1024,
        messages=all_messages,  # type: ignore[arg-type]
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or "{}"
    logger.debug("GPT-4o response: %s", raw)
    return raw


class IntentParser:
    def __init__(
        self,
        task_repo: TaskRepo,
        anthropic_client: anthropic.AsyncAnthropic | None = None,
        openai_client: AsyncOpenAI | None = None,
    ) -> None:
        self._task_repo = task_repo
        self._anthropic_client = anthropic_client
        self._openai_client = openai_client

    def _get_anthropic_client(self) -> anthropic.AsyncAnthropic:
        if self._anthropic_client is None:
            import anthropic as _anthropic

            from bot.config import settings
            self._anthropic_client = _anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._anthropic_client

    def _get_openai_client(self) -> AsyncOpenAI:
        if self._openai_client is None:
            from openai import AsyncOpenAI

            from bot.config import settings
            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    async def parse(
        self,
        text: str,
        user: User,
        history: list[ChatHistory],
    ) -> ParsedResponse:
        task_lists = await self._task_repo.get_lists_by_user(user.id)
        list_names = [f"{tl.emoji} {tl.name}" for tl in task_lists]
        lists_with_ids = [(tl.id, tl.emoji, tl.name) for tl in task_lists]

        current_dt = _current_dt_for_user(user.timezone)
        system = build_system_prompt(
            current_dt, user.timezone, list_names, task_lists_with_ids=lists_with_ids
        )
        history_messages = _history_to_messages(history)

        logger.debug(
            "Parsing intent: user_id=%d model=%s history_len=%d text=%r",
            user.id, user.ai_model, len(history), text,
        )
        try:
            if user.ai_model == AIModel.GPT4O:
                raw = await _parse_with_gpt4o(self._get_openai_client(), system, history_messages, text)
            else:
                raw = await _parse_with_claude(self._get_anthropic_client(), system, history_messages, text)

            data = json.loads(raw)
            # Set user timezone context so Pydantic validators can correctly interpret
            # naive datetimes returned by the AI (without UTC offset) as local user time.
            from bot.services.intent.models import _user_tz_ctx
            token = _user_tz_ctx.set(user.timezone)
            try:
                parsed = ParsedResponse.model_validate(data)
            finally:
                _user_tz_ctx.reset(token)
            intent_types = [i.type for i in parsed.intents]
            logger.debug(
                "Parsed intents=%s confidence=%.2f clarification=%r",
                intent_types, parsed.confidence, parsed.clarification_needed,
            )
            return parsed
        except Exception:
            logger.exception("Intent parsing failed for text=%r", text)
            from bot.services.intent.models import AIChatIntent

            return ParsedResponse(
                intents=[AIChatIntent(type="ai_chat", message=text)],
                confidence=1.0,
                clarification_needed=None,
            )
