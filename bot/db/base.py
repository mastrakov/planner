from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings

engine = create_async_engine(settings.postgres_dsn, echo=settings.is_local)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


def run_migrations() -> None:
    """Apply all pending Alembic migrations. Called once at startup before the bot runs."""
    import logging
    from alembic import command
    from alembic.config import Config

    logger = logging.getLogger(__name__)
    logger.info("Running Alembic migrations...")

    # alembic.ini lives at the project root (one level above bot/)
    import os
    ini_path = os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini")
    alembic_cfg = Config(os.path.abspath(ini_path))
    command.upgrade(alembic_cfg, "head")

    logger.info("Migrations complete.")
