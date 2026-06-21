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

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown logic.

    On startup:
        - Log application startup with version info.
    On shutdown:
        - Clean up any global resources.

    """
    settings = get_settings()
    logger.info(
        "Application startup",
        version=app.version,
        api_prefix=settings.API_PREFIX,
    )
    yield
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
