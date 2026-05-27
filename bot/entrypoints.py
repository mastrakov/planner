"""Console entry points for uv run dev / uv run service / uv run tests."""
import asyncio
import subprocess
import sys


def dev() -> None:
    """uv run dev — polling mode (local development)."""
    import os
    os.environ.setdefault("ENV", "local")
    from bot.db.base import run_migrations
    from bot.main import main
    run_migrations()
    asyncio.run(main())


def service() -> None:
    """uv run service — webhook mode (production)."""
    import os
    os.environ.setdefault("ENV", "production")
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
