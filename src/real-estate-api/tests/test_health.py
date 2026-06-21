"""
Tests for the health check endpoint.

Covers:
- Health endpoint returns expected fields
- Redis status reflects client health state
"""

import pytest


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
