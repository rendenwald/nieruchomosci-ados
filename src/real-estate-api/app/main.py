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
from minio import Minio

from app.core.config import get_settings
from app.routers import cities, health, photos, properties, readiness
from app.services.cache_service import CacheService
from app.services.redis_client import RedisClient
from app.workers.alert_worker import AlertWorker

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown logic.

    On startup:
        - Record startup timestamp for readiness grace period.
        - Initialise Redis connection pool.
        - Attach ``RedisClient`` and ``CacheService`` to ``app.state``.
        - Start the AlertWorker background consumer.
        - Log application startup with version info.
    On shutdown:
        - Stop the AlertWorker background consumer.
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

    # Initialise MinIO client for photo serving
    try:
        minio_client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        app.state.minio_client = minio_client
        app.state.minio_bucket = settings.MINIO_BUCKET_PHOTOS
    except Exception as exc:  # noqa: BLE001
        logger.warning("MinIO client creation failed, photo serving unavailable", error=str(exc))
        app.state.minio_client = None

    # Start Alert Worker background consumer
    alert_worker = AlertWorker(redis_client)
    await alert_worker.start()
    app.state.alert_worker = alert_worker

    logger.info(
        "Application startup",
        version=app.version,
        api_prefix=settings.API_PREFIX,
        redis_healthy=redis_client.healthy,
        redis_enabled=settings.REDIS_ENABLED,
        alert_worker_started=alert_worker._running,  # noqa: SLF001
    )

    yield

    # Shutdown: stop workers first, then clean up resources
    await alert_worker.stop()
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
    app.include_router(photos.router, prefix=settings.API_PREFIX)
    app.include_router(cities.router, prefix=settings.API_PREFIX)
    app.include_router(health.router)
    app.include_router(readiness.router)

    return app


app = create_app()
