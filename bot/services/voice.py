import asyncio
import io
import logging
import os
import tempfile

import aiofiles
from aiogram import Bot
from aiogram.types import Voice
from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)

_openai = AsyncOpenAI(api_key=settings.openai_api_key)


async def download_ogg_from_telegram(bot: Bot, voice: Voice) -> str:
    """Download voice message OGG from Telegram and return path to temp file."""
    file = await bot.get_file(voice.file_id)
    file_path = file.file_path
    if not file_path:
        raise ValueError("Cannot get file path from Telegram")

    suffix = ".ogg"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)

    await bot.download_file(file_path, tmp_path)
    if os.path.getsize(tmp_path) == 0:
        raise RuntimeError("Downloaded OGG file is empty (0 bytes)")
    return tmp_path


async def convert_to_mp3(ogg_path: str) -> str:
    """Convert OGG to MP3 via ffmpeg without blocking the event loop."""
    mp3_path = ogg_path.replace(".ogg", ".mp3")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", ogg_path, "-codec:a", "libmp3lame", mp3_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    if proc.returncode != 0:
        stderr_text = stderr.decode(errors="replace")
        logger.error("ffmpeg conversion failed (rc=%d):\n%s", proc.returncode, stderr_text)
        raise RuntimeError(f"ffmpeg failed (rc={proc.returncode}): {stderr_text[:500]}")
    return mp3_path


async def transcribe(mp3_path: str) -> str:
    """Transcribe MP3 via OpenAI gpt-4o-mini-transcribe."""
    async with aiofiles.open(mp3_path, "rb") as f:
        content = await f.read()

    audio_file = io.BytesIO(content)
    audio_file.name = "audio.mp3"

    response = await _openai.audio.transcriptions.create(
        model="gpt-4o-transcribe",
        file=audio_file,  # type: ignore[arg-type]
        language="ru",
        prompt="Транскрибируй на русском языке.",
    )
    return response.text


class VoiceService:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def voice_to_text(self, voice: Voice) -> str:
        ogg_path = await download_ogg_from_telegram(self._bot, voice)
        try:
            mp3_path = await convert_to_mp3(ogg_path)
            try:
                return await transcribe(mp3_path)
            finally:
                if os.path.exists(mp3_path):
                    os.unlink(mp3_path)
        finally:
            if os.path.exists(ogg_path):
                os.unlink(ogg_path)
