"""
Async PostgreSQL database connectivity using SQLAlchemy 2.0 + asyncpg.

Provides engine creation, session factory, and a context-managed session
with retry logic on connection failure.
"""

import asyncio
import logging
import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.ext.asyncio import (
    create_async_engine as _create_async_engine,
)

logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/realestate"
MAX_RETRIES = 3
RETRY_BACKOFF = [1.0, 2.0, 4.0]  # seconds


def get_database_url() -> str:
    """Return the database URL from the DATABASE_URL env var, or the default."""
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def create_async_engine(
    database_url: str | None = None,
    pool_size: int = 5,
    **kwargs: object,
) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    Args:
        database_url: PostgreSQL connection string. Falls back to DATABASE_URL
                      env var, then the default local connection.
        pool_size: Number of connections in the pool (default 5).
        **kwargs: Additional arguments forwarded to ``create_async_engine``.

    Returns:
        A configured ``AsyncEngine`` instance.

    """
    url = database_url or get_database_url()
    logger.info("Creating async engine", extra={"pool_size": pool_size})
    return _create_async_engine(
        url,
        pool_size=pool_size,
        max_overflow=2,
        pool_pre_ping=True,
        echo=os.environ.get("SQL_ECHO", "0").lower() in ("1", "true", "yes"),
        **kwargs,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine.

    Args:
        engine: An ``AsyncEngine`` instance.

    Returns:
        A configured ``async_sessionmaker`` for ``AsyncSession``.

    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield an ``AsyncSession`` as an async context manager.

    Usage::

        async for session in get_db_session(session_factory):
            await session.execute(...)

    The session is automatically closed after the ``for`` block exits.

    """
    async with session_factory() as session:
        yield session


async def check_connection(engine: AsyncEngine) -> bool:
    """Perform a lightweight health check against the database.

    Args:
        engine: An ``AsyncEngine`` instance.

    Returns:
        ``True`` if the database responds, ``False`` otherwise.

    """
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database health check failed", extra={"error": str(exc)})
        return False


async def init_db(engine: AsyncEngine) -> None:
    """Create all tables defined on ``Base.metadata``.

    .. caution::

        This is a convenience for development/testing. Production should use
        Alembic migrations.

    """
    from scraper_base.models import Base  # noqa: PLC0415

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created via metadata.create_all")


async def wait_for_db(
    engine: AsyncEngine,
    max_retries: int = MAX_RETRIES,
    backoff: list[float] | None = None,
) -> None:
    """Wait for the database to become available with exponential backoff.

    Args:
        engine: An ``AsyncEngine`` instance.
        max_retries: Maximum number of connection attempts.
        backoff: List of sleep durations (seconds) between retries.

    Raises:
        ConnectionError: If all retries are exhausted.

    """
    delays = backoff or RETRY_BACKOFF
    for attempt in range(1, max_retries + 1):
        if await check_connection(engine):
            logger.info("Database connection established")
            return
        if attempt < max_retries:
            delay = delays[min(attempt - 1, len(delays) - 1)]
            logger.warning(
                "Database not ready, retrying",
                extra={"attempt": attempt, "max_retries": max_retries, "retry_delay_s": delay},
            )
            await asyncio.sleep(delay)
    msg = f"Database unreachable after {max_retries} retries"
    raise ConnectionError(msg)
