"""
FastAPI application factory for the Real Estate Aggregation Platform API.

Provides ``create_app()`` which configures lifespan handlers, middleware,
and route registration.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.core.config import get_settings
from app.routers import health, properties
from app.services.cache_service import CacheService
from app.services.redis_client import RedisClient

logger = structlog.get_logger(__name__)


async def _periodic_health_check(redis_client: RedisClient) -> None:
    """Background task that periodically checks Redis health.

    Runs every ``REDIS_HEALTH_CHECK_INTERVAL`` seconds. Updates the
    ``healthy`` and ``failure_count`` state on the RedisClient.

    Args:
        redis_client: The ``RedisClient`` instance to check.

    """
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.REDIS_HEALTH_CHECK_INTERVAL)
        try:
            await redis_client.ping()
        except Exception:  # noqa: BLE001
            logger.warning("health_check_task_error", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown logic.

    On startup:
        - Initialise Redis connection pool.
        - Attach ``RedisClient`` and ``CacheService`` to ``app.state``.
        - Start a periodic health-check background task.
        - Log application startup with version info.
    On shutdown:
        - Cancel the health-check background task.
        - Close Redis connection pool.

    """
    settings = get_settings()

    # Initialise Redis client
    redis_client = RedisClient()
    await redis_client.connect()
    cache_service = CacheService(redis_client)

    app.state.redis_client = redis_client
    app.state.cache_service = cache_service

    # Start periodic health check
    health_task = asyncio.create_task(_periodic_health_check(redis_client))

    logger.info(
        "Application startup",
        version=app.version,
        api_prefix=settings.API_PREFIX,
        redis_healthy=redis_client.healthy,
    )

    yield

    # Shutdown: clean up resources
    health_task.cancel()
    try:
        await health_task
    except asyncio.CancelledError:
        pass
    await redis_client.disconnect()
    logger.info("Application shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        A fully configured ``FastAPI`` ASGI application instance.

    """
    settings = get_settings()

    app = FastAPI(
        title="Real Estate Aggregation API",
        description="REST API for searching and filtering real estate listings",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=f"{settings.API_PREFIX}/docs",
        openapi_url=f"{settings.API_PREFIX}/openapi.json",
    )

    # Register routers
    app.include_router(properties.router, prefix=settings.API_PREFIX)
    app.include_router(health.router)

    return app
