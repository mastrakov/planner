import json
import logging
from datetime import datetime, timezone

import anthropic
import pytz
from openai import AsyncOpenAI

from bot.config import settings
from bot.db.models import AIModel, ChatHistory, User
from bot.db.repo.tasks import TaskRepo
from bot.services.intent.models import ParsedResponse
from bot.services.intent.prompts import build_system_prompt

logger = logging.getLogger(__name__)

_anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
_openai_client = AsyncOpenAI(api_key=settings.openai_api_key)


def _current_dt_for_user(tz_name: str) -> datetime:
    tz = pytz.timezone(tz_name)
    return datetime.now(tz=timezone.utc).astimezone(tz).replace(tzinfo=None)


def _history_to_messages(history: list[ChatHistory]) -> list[dict[str, str]]:
    return [{"role": h.role, "content": h.content} for h in history]


async def _parse_with_claude(system: str, messages: list[dict[str, str]], text: str) -> str:
    all_messages = messages + [{"role": "user", "content": text}]
    response = await _anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system,
        messages=all_messages,  # type: ignore[arg-type]
    )
    return response.content[0].text  # type: ignore[union-attr]


async def _parse_with_gpt4o(system: str, messages: list[dict[str, str]], text: str) -> str:
    all_messages = [{"role": "system", "content": system}] + messages + [{"role": "user", "content": text}]
    response = await _openai_client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        messages=all_messages,  # type: ignore[arg-type]
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content or "{}"


class IntentParser:
    def __init__(self, task_repo: TaskRepo) -> None:
        self._task_repo = task_repo

    async def parse(
        self,
        text: str,
        user: User,
        history: list[ChatHistory],
    ) -> ParsedResponse:
        task_lists = await self._task_repo.get_lists_by_user(user.id)
        list_names = [f"{tl.emoji} {tl.name}" for tl in task_lists]

        current_dt = _current_dt_for_user(user.timezone)
        system = build_system_prompt(current_dt, user.timezone, list_names)
        history_messages = _history_to_messages(history)

        try:
            if user.ai_model == AIModel.GPT4O:
                raw = await _parse_with_gpt4o(system, history_messages, text)
            else:
                raw = await _parse_with_claude(system, history_messages, text)

            data = json.loads(raw)
            return ParsedResponse.model_validate(data)
        except Exception:
            logger.exception("Intent parsing failed for text=%r", text)
            from bot.services.intent.models import AIChatIntent

            return ParsedResponse(
                intents=[AIChatIntent(type="ai_chat", message=text)],
                confidence=1.0,
                clarification_needed=None,
            )
