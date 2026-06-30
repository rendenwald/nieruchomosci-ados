"""
Async database session management for the real-estate-api.

Provides a shared engine, session factory, and FastAPI dependency
for obtaining an ``AsyncSession`` per request.

Uses ``scraper_base.database`` for engine creation and configuration.
"""

from collections.abc import AsyncGenerator

from scraper_base.database import (
    create_async_engine,
    create_session_factory,
    get_database_url,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

# Single engine instance (lazy-init pattern — call get_engine() to access)
_engine = create_async_engine(get_database_url())
_session_factory = create_session_factory(_engine)


def get_engine() -> AsyncEngine:
    """Return the shared async engine instance."""
    return _engine


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an ``AsyncSession``.

    Usage::

        from fastapi import Depends
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.database import get_session

        @router.post("/example")
        async def example(db: AsyncSession = Depends(get_session)): ...

    The session is closed (returned to pool) after the request completes.

    Yields:
        An ``AsyncSession`` bound to the shared engine.
    """
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
