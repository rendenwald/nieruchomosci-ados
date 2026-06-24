"""
Tests for the health and readiness endpoints.

Covers:
- GET /health returns expected fields for ok/degraded/disabled states
- GET /ready returns correct status codes for all Redis states and grace period
"""

import time
from unittest.mock import patch

import pytest

from app.core.config import Settings


@pytest.mark.asyncio
async def test_health_returns_ok(client) -> None:  # type: ignore[no-untyped-def]
    """GET /health returns 200 with status ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


@pytest.mark.asyncio
async def test_health_contains_redis_status(client) -> None:  # type: ignore[no-untyped-def]
    """Health response includes redis field."""
    response = await client.get("/health")
    body = response.json()
    assert "redis" in body


@pytest.mark.asyncio
async def test_health_redis_ok_when_healthy(client, app) -> None:  # type: ignore[no-untyped-def]
    """When Redis is healthy, health reports redis: ok."""
    app.state.redis_client.healthy = True
    response = await client.get("/health")
    body = response.json()
    assert body["redis"] == "ok"


@pytest.mark.asyncio
async def test_health_redis_degraded_when_unhealthy(client, app) -> None:  # type: ignore[no-untyped-def]
    """When Redis is unhealthy, health reports redis: degraded."""
    app.state.redis_client.healthy = False
    response = await client.get("/health")
    body = response.json()
    assert body["redis"] == "degraded"


@pytest.mark.asyncio
async def test_health_redis_disabled_when_disabled(  # type: ignore[no-untyped-def]
    client, app, monkeypatch
) -> None:
    """When REDIS_ENABLED=False, health reports redis: disabled."""
    disabled_settings = Settings(REDIS_ENABLED=False)
    monkeypatch.setattr("app.routers.health.get_settings", lambda: disabled_settings)
    app.state.redis_client.healthy = False
    response = await client.get("/health")
    body = response.json()
    assert body["redis"] == "disabled"


# --- Readiness endpoint tests ---


@pytest.mark.asyncio
async def test_ready_returns_200_when_healthy(client) -> None:  # type: ignore[no-untyped-def]
    """``healthy=True`` → 200, ready: true, redis: ok."""
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["redis"] == "ok"


@pytest.mark.asyncio
async def test_ready_returns_degraded_when_unhealthy(  # type: ignore[no-untyped-def]
    client, app
) -> None:
    """Degraded + within grace period → 200, ready: true, redis: degraded."""
    app.state.redis_client.healthy = False
    # Ensure we're within the grace period
    app.state.started_at = time.time()
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["redis"] == "degraded"


@pytest.mark.asyncio
async def test_ready_returns_503_after_grace_period(  # type: ignore[no-untyped-def]
    client, app
) -> None:
    """Degraded + past grace period → 503, ready: false, redis: degraded."""
    app.state.redis_client.healthy = False
    # Set started_at far in the past to exceed grace period
    app.state.started_at = time.time() - 60  # 60 seconds ago > 30s grace
    response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False
    assert body["redis"] == "degraded"


@pytest.mark.asyncio
async def test_ready_returns_503_with_zero_grace(  # type: ignore[no-untyped-def]
    client, app, monkeypatch
) -> None:
    """With ``REDIS_STARTUP_GRACE_PERIOD=0``, degraded returns 503 immediately."""
    # Patch the STARTUP GRACE PERIOD to 0
    zero_grace_settings = Settings(REDIS_STARTUP_GRACE_PERIOD=0)
    monkeypatch.setattr("app.routers.readiness.get_settings", lambda: zero_grace_settings)
    app.state.redis_client.healthy = False
    app.state.started_at = time.time()
    response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False
    assert body["redis"] == "degraded"


@pytest.mark.asyncio
async def test_ready_returns_disabled_when_redis_disabled(  # type: ignore[no-untyped-def]
    client, app, monkeypatch
) -> None:
    """``REDIS_ENABLED=False`` → 200, ready: true, redis: disabled."""
    disabled_settings = Settings(REDIS_ENABLED=False)
    monkeypatch.setattr("app.routers.readiness.get_settings", lambda: disabled_settings)
    app.state.redis_client.healthy = False
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["redis"] == "disabled"
