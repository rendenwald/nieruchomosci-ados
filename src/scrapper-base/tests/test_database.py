"""Tests for the database module."""

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncEngine

from scraper_base.database import (
    create_async_engine,
    create_session_factory,
    get_database_url,
)
from scraper_base.db_utils import check_connection


class TestCreateAsyncEngine:
    """Engine creation and configuration."""

    def test_default_database_url(self):
        """Database URL should have a sensible default."""
        url = get_database_url()
        assert "postgresql+asyncpg" in url
        assert "localhost" in url

    async def test_engine_creation_with_sqlite(self):
        """Engine can be created with any valid async URL."""
        engine = create_async_engine("sqlite+aiosqlite://", pool_size=5)
        assert isinstance(engine, AsyncEngine)
        await engine.dispose()

    async def test_session_factory_creates_session(self):
        """Session factory bound to an engine produces valid sessions."""
        engine = create_async_engine("sqlite+aiosqlite://", pool_size=5)
        factory = create_session_factory(engine)
        async with factory() as session:
            result = await session.execute(sa_text("SELECT 1 AS val"))
            assert result.scalar_one() == 1
        await engine.dispose()


class TestCheckConnection:
    """Health check function."""

    async def test_check_connection_success(self, db_engine):
        """Health check returns True when DB is reachable."""
        assert await check_connection(db_engine) is True
