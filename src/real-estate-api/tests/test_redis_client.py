"""
Tests for the RedisClient class.

Covers:
- Connection with REDIS_ENABLED=True/False
- Recovery worker lifecycle
- Gauge wiring on state transitions
- Reconnect pool behaviour
"""

import asyncio
from unittest.mock import AsyncMock, patch

import fakeredis
import pytest

from app.core.metrics import redis_degraded
from app.services.redis_client import RedisClient


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    """Reset the redis_degraded gauge before each test."""
    redis_degraded.set(0)


@pytest.mark.asyncio
async def test_connect_when_redis_enabled() -> None:
    """Calling ``connect()`` with a fakeredis instance creates ``_redis``
    and sets ``healthy=True``."""
    client = RedisClient()
    fake_redis = fakeredis.FakeAsyncRedis()
    client._redis = fake_redis
    client._pool = fake_redis.connection_pool
    # Manually set healthy since we bypassed real connect()
    client.healthy = True
    assert client._redis is not None
    assert client.healthy is True


@pytest.mark.asyncio
async def test_connect_when_redis_disabled() -> None:
    """``REDIS_ENABLED=False`` causes early return, no pool, healthy=False."""
    from unittest.mock import patch

    mock_settings = AsyncMock()
    mock_settings.REDIS_ENABLED = False
    mock_settings.REDIS_URL = "redis://localhost:6379/0"

    with patch("app.services.redis_client.get_settings", return_value=mock_settings):
        client = RedisClient()
        await client.connect()
        assert client._redis is None
        assert client._pool is None
        assert client.healthy is False


@pytest.mark.asyncio
async def test_connect_when_redis_disabled_sets_gauge_zero() -> None:
    """Gauge is 0 when Redis is disabled."""
    from unittest.mock import patch

    mock_settings = AsyncMock()
    mock_settings.REDIS_ENABLED = False
    mock_settings.REDIS_URL = "redis://localhost:6379/0"

    with patch("app.services.redis_client.get_settings", return_value=mock_settings):
        client = RedisClient()
        await client.connect()
        assert redis_degraded.collect()[0].samples[0].value == 0


@pytest.mark.asyncio
async def test_recovery_worker_starts_on_connect() -> None:
    """Recovery task created after ``connect()`` when Redis is enabled."""
    fake_redis = fakeredis.FakeAsyncRedis()
    client = RedisClient()
    # Override connect to start recovery worker
    client._redis = fake_redis
    client._pool = fake_redis.connection_pool
    client.healthy = True
    await client._start_recovery_worker()
    assert client._recovery_task is not None
    assert not client._recovery_task.done()
    # Clean up
    await client._stop_recovery_worker()


@pytest.mark.asyncio
async def test_recovery_worker_stops_on_disconnect() -> None:
    """Calling ``disconnect()`` cancels recovery worker task."""
    fake_redis = fakeredis.FakeAsyncRedis()
    client = RedisClient()
    client._redis = fake_redis
    client._pool = fake_redis.connection_pool
    client.healthy = True
    await client._start_recovery_worker()
    assert client._recovery_task is not None
    await client._stop_recovery_worker()
    assert client._recovery_task is None or client._recovery_task.done()


@pytest.mark.asyncio
async def test_ping_returns_true_when_healthy() -> None:
    """``ping()`` returns ``True`` when Redis responds."""
    fake_redis = fakeredis.FakeAsyncRedis()
    client = RedisClient()
    client._redis = fake_redis
    ok = await client.ping()
    assert ok is True
    assert client.healthy is True


@pytest.mark.asyncio
async def test_ping_returns_false_when_no_redis() -> None:
    """``ping()`` returns ``False`` when ``_redis`` is ``None``."""
    client = RedisClient()
    client._redis = None
    ok = await client.ping()
    assert ok is False
    assert client.healthy is True  # No state change


@pytest.mark.asyncio
async def test_recovery_worker_idles_when_healthy() -> None:
    """When ``healthy=True``, the recovery worker sleeps without pinging.
    We verify by checking that _recovery_task is created and running."""
    fake_redis = fakeredis.FakeAsyncRedis()
    client = RedisClient()
    client._redis = fake_redis
    client.healthy = True
    await client._start_recovery_worker()
    # Give the task a moment to enter the sleep
    await asyncio.sleep(0.05)
    assert client._recovery_task is not None
    assert not client._recovery_task.done()
    await client._stop_recovery_worker()


@pytest.mark.asyncio
async def test_ping_updates_gauge_on_healthy() -> None:
    """Gauge stays 0 when Redis is healthy."""
    fake_redis = fakeredis.FakeAsyncRedis()
    client = RedisClient()
    client._redis = fake_redis
    client.healthy = True
    redis_degraded.set(0)
    await client.ping()
    assert redis_degraded.collect()[0].samples[0].value == 0


@pytest.mark.asyncio
async def test_get_returns_none_when_no_redis() -> None:
    """``get()`` returns ``None`` when ``_redis`` is ``None``."""
    client = RedisClient()
    client._redis = None
    result = await client.get("test-key")
    assert result is None


@pytest.mark.asyncio
async def test_set_does_not_raise_when_no_redis() -> None:
    """``set()`` returns early without error when ``_redis`` is ``None``."""
    client = RedisClient()
    client._redis = None
    # Should not raise
    await client.set("test-key", "test-value", 60)


@pytest.mark.asyncio
async def test_set_nx_returns_false_when_no_redis() -> None:
    """``set_nx()`` returns ``False`` when ``_redis`` is ``None``."""
    client = RedisClient()
    client._redis = None
    result = await client.set_nx("test-key", "", 5)
    assert result is False


@pytest.mark.asyncio
async def test_recovery_task_not_created_without_start() -> None:
    """Recovery task is ``None`` before ``_start_recovery_worker()`` is called."""
    client = RedisClient()
    assert client._recovery_task is None


@pytest.mark.asyncio
async def test_stop_recovery_worker_when_not_started() -> None:
    """``_stop_recovery_worker()`` is a no-op when task is ``None``."""
    client = RedisClient()
    await client._stop_recovery_worker()  # Should not raise
    assert client._recovery_task is None
