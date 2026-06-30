"""
Shared test fixtures for real-estate-api unit tests.

Provides fakeredis-based fixtures for cache tests, a test FastAPI application
with overridden dependencies, async HTTP test client via httpx, and mock
MinIO client for photo serving tests.
"""

import time
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import fakeredis
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def fake_redis() -> AsyncGenerator[fakeredis.FakeAsyncRedis, None]:
    """Create a fakeredis async instance for testing.

    Returns:
        A ``fakeredis.FakeAsyncRedis`` instance (no real Redis needed).
    """
    redis = fakeredis.FakeAsyncRedis()
    yield redis
    await redis.aclose()


@pytest_asyncio.fixture
async def mock_db_session() -> AsyncMock:
    """Create a mock ``AsyncSession`` for dependency override.

    All methods are ``AsyncMock`` so they work with async calls.
    """
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest_asyncio.fixture
async def app(
    fake_redis: fakeredis.FakeAsyncRedis,
    mock_db_session: AsyncMock,
) -> FastAPI:
    """Create a test FastAPI application with fakeredis and DB overrides.

    Overrides the real Redis client with a fakeredis instance and the
    async database session with a mock so tests do not require running
    Redis or PostgreSQL servers.

    Args:
        fake_redis: The fakeredis fixture.
        mock_db_session: The mock database session fixture.

    Returns:
        A ``FastAPI`` application configured for testing.
    """
    # Import here to avoid module-level side effects
    from app.database import get_session
    from app.main import create_app
    from app.services.cache_service import CacheService
    from app.services.redis_client import RedisClient

    test_app = create_app()

    # Override the get_session dependency with a mock
    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db_session

    test_app.dependency_overrides[get_session] = _override_session

    # Override the real RedisClient with the fakeredis-backed one
    redis_client = RedisClient()
    redis_client._redis = fake_redis
    redis_client._pool = fake_redis.connection_pool
    redis_client.healthy = True

    cache_service = CacheService(redis_client)

    test_app.state.redis_client = redis_client
    test_app.state.cache_service = cache_service
    test_app.state.started_at = time.time()

    return test_app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing the API.

    Args:
        app: The test FastAPI application fixture.

    Yields:
        An ``httpx.AsyncClient`` connected to the test app via ASGI transport.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def app_with_minio(app: FastAPI) -> FastAPI:
    """Create a test app with a mocked MinIO client.

    Attaches a ``MagicMock`` MinIO client to ``app.state`` so photo endpoint
    tests can control responses.

    Usage::

        async def test_photo(client, app_with_minio):
            app_with_minio.state.minio_client.get_object.return_value.read.return_value = b"fake"
            response = await client.get("/api/v1/photos/abc...jpg")

    Returns:
        The ``FastAPI`` application with ``minio_client`` attached.
    """
    mock_minio = MagicMock()
    app.state.minio_client = mock_minio
    app.state.minio_bucket = "property-photos"
    return app


