"""
Readiness probe endpoint for Kubernetes readiness checks.

Provides ``GET /ready`` that returns HTTP 200 when all critical dependencies
are healthy and HTTP 503 when they are not (with a startup grace period).
"""

import time
from typing import cast

import structlog
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.services.redis_client import RedisClient

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["readiness"])


def _get_redis_client(request: Request) -> RedisClient:
    """Dependency: return the Redis client from app state."""
    return cast(RedisClient, request.app.state.redis_client)


@router.get("/ready")
async def readiness_check(request: Request) -> JSONResponse:
    """Readiness probe for Kubernetes.

    Returns HTTP 200 if all critical dependencies are healthy, HTTP 503
    if Redis is degraded past the startup grace period.

    The startup grace period (``REDIS_STARTUP_GRACE_PERIOD`` seconds)
    allows the application to start up before a degraded Redis causes
    the pod to be marked not-ready.
    """
    settings = get_settings()
    redis_client = _get_redis_client(request)
    now = time.time()
    elapsed = now - request.app.state.started_at

    if not settings.REDIS_ENABLED:
        return JSONResponse(
            status_code=200,
            content={"ready": True, "redis": "disabled"},
        )

    if redis_client.healthy:
        return JSONResponse(
            status_code=200,
            content={"ready": True, "redis": "ok"},
        )

    # Redis is degraded — check grace period
    if elapsed < settings.REDIS_STARTUP_GRACE_PERIOD:
        return JSONResponse(
            status_code=200,
            content={"ready": True, "redis": "degraded"},
        )

    # Past grace period — not ready
    return JSONResponse(
        status_code=503,
        content={"ready": False, "redis": "degraded"},
    )
