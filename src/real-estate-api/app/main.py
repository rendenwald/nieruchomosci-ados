"""
FastAPI application factory for the Real Estate Aggregation Platform API.

Provides ``create_app()`` which configures lifespan handlers, middleware,
and route registration.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.core.config import get_settings
from app.services.cache_service import CacheService
from app.services.redis_client import RedisClient

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown logic.

    On startup:
        - Initialise Redis connection pool.
        - Attach ``RedisClient`` and ``CacheService`` to ``app.state``.
        - Log application startup with version info.
    On shutdown:
        - Close Redis connection pool.
        - Clean up any global resources.

    """
    settings = get_settings()

    # Initialise Redis client
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

    @app.get(f"{settings.API_PREFIX}/health")
    async def health_check() -> dict[str, str]:
        """Basic health check endpoint.

        Returns:
            A JSON object with ``status`` field.
        """
        return {"status": "ok"}

    return app
