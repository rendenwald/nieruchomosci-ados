"""
Health check endpoint for the Real Estate Aggregation API.

Provides ``GET /health`` with status information about Redis connectivity
and other service dependencies.
"""

from typing import cast

import structlog
from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.services.redis_client import RedisClient

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])


def _get_redis_client(request: Request) -> RedisClient:
    """Dependency: return the Redis client from app state."""
    return cast(RedisClient, request.app.state.redis_client)


@router.get("/health")
async def health_check(request: Request) -> dict[str, str]:
    """Health check endpoint for service dependencies.

    Returns:
        A JSON object with:
        - ``status``: Overall service status (always ``"ok"`` if responding).
        - ``redis``: ``"ok"`` if Redis is reachable, ``"degraded"`` otherwise,
          or ``"disabled"`` if Redis is explicitly disabled via config.

    """
    settings = get_settings()
    redis_client = _get_redis_client(request)

    if not settings.REDIS_ENABLED:
        redis_status = "disabled"
    else:
        redis_status = "ok" if redis_client.healthy else "degraded"

    return {
        "status": "ok",
        "redis": redis_status,
    }
