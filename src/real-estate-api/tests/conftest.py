"""
Shared test fixtures for real-estate-api unit tests.

Provides fakeredis-based fixtures for cache tests, a test FastAPI application
with overridden dependencies, and async HTTP test client via httpx.
"""

from collections.abc import AsyncGenerator

import fakeredis
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


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
async def app(fake_redis: fakeredis.FakeAsyncRedis) -> FastAPI:
    """Create a test FastAPI application with fakeredis overrides.

    Overrides the real Redis client with a fakeredis instance so tests
    do not require a running Redis server.

    Args:
        fake_redis: The fakeredis fixture.

    Returns:
        A ``FastAPI`` application configured for testing.
    """
    # Import here to avoid module-level side effects
    from app.main import create_app
    from app.services.cache_service import CacheService
    from app.services.redis_client import RedisClient

    test_app = create_app()

    # Override the real RedisClient with the fakeredis-backed one
    redis_client = RedisClient()
    redis_client._redis = fake_redis
    redis_client._pool = fake_redis.connection_pool
    redis_client.healthy = True

    cache_service = CacheService(redis_client)

    test_app.state.redis_client = redis_client
    test_app.state.cache_service = cache_service

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
