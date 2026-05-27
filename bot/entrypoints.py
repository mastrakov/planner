"""Console entry points for uv run dev / uv run service / uv run tests."""
import asyncio
import logging
import os
import subprocess
import sys


def _configure_logging(debug: bool) -> None:
    """Configure root logging BEFORE any library imports (alembic, sqlalchemy, etc.)
    that might add their own handlers and make basicConfig a no-op."""
    level = logging.DEBUG if debug else logging.INFO
    # Force=True removes any pre-existing handlers before applying our config.
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )
    # Keep noisy libs at INFO even in debug mode
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("aiohttp").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy").setLevel(logging.INFO)


def dev() -> None:
    """uv run dev — polling mode (local development)."""
    os.environ.setdefault("ENV", "local")
    _configure_logging(debug=True)

    from bot.db.base import run_migrations
    from bot.main import main
    run_migrations()
    asyncio.run(main())


def service() -> None:
    """uv run service — webhook mode (production)."""
    os.environ.setdefault("ENV", "production")
    _configure_logging(debug=False)

    from bot.db.base import run_migrations
    from bot.main import main
    run_migrations()
    asyncio.run(main())


def tests() -> None:
    """uv run tests — run pytest with any extra args."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *sys.argv[1:]],
        check=False,
    )
    sys.exit(result.returncode)
