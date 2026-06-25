"""
FastAPI application factory for the Real Estate Aggregation Platform API.

Provides ``create_app()`` which configures lifespan handlers, middleware,
and route registration.
"""

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.core.config import get_settings
from app.routers import cities, health, properties, readiness
from app.services.cache_service import CacheService
from app.services.redis_client import RedisClient

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown logic.

    On startup:
        - Record startup timestamp for readiness grace period.
        - Initialise Redis connection pool.
        - Attach ``RedisClient`` and ``CacheService`` to ``app.state``.
        - Log application startup with version info.
    On shutdown:
        - Close Redis connection pool (recovery worker is stopped inside
          ``disconnect()``).

    """
    settings = get_settings()

    app.state.started_at = time.time()

    # Use existing Redis client from app.state if already set (e.g. in tests)
    redis_client: RedisClient | None = getattr(app.state, "redis_client", None)
    cache_service: CacheService | None = getattr(app.state, "cache_service", None)

    if redis_client is None or cache_service is None:
        # Initialise Redis client from scratch
        redis_client = RedisClient()
        await redis_client.connect()
        cache_service = CacheService(redis_client)

        app.state.redis_client = redis_client
        app.state.cache_service = cache_service

    logger.info(
        "Application startup",
        version=app.version,
        api_prefix=settings.API_PREFIX,
        redis_healthy=redis_client.healthy,
        redis_enabled=settings.REDIS_ENABLED,
    )

    yield

    # Shutdown: clean up resources
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
    app.include_router(cities.router, prefix=settings.API_PREFIX)
    app.include_router(health.router)
    app.include_router(readiness.router)

    return app
