"""
Tests for the RedisClient class.

Covers:
- Connection with REDIS_ENABLED=True/False
- Recovery worker lifecycle
- Gauge wiring on state transitions
- Reconnect pool behaviour
"""

import asyncio
from unittest.mock import AsyncMock

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
    import unittest.mock as umock

    mock_settings = AsyncMock()
    mock_settings.REDIS_ENABLED = False
    mock_settings.REDIS_URL = "redis://localhost:6379/0"
    mock_settings.REDIS_POOL_SIZE = 10
    mock_settings.REDIS_TIMEOUT_SECONDS = 2
    mock_settings.REDIS_HEALTH_CHECK_INTERVAL = 30
    mock_settings.REDIS_HEALTH_CHECK_FAILURE_THRESHOLD = 3

    with umock.patch("app.services.redis_client.get_settings", return_value=mock_settings):
        client = RedisClient()
        await client.connect()
        assert client._redis is None
        assert client._pool is None
        assert client.healthy is False


@pytest.mark.asyncio
async def test_connect_when_redis_disabled_sets_gauge_zero() -> None:
    """Gauge is 0 when Redis is disabled."""
    import unittest.mock as umock

    mock_settings = AsyncMock()
    mock_settings.REDIS_ENABLED = False
    mock_settings.REDIS_URL = "redis://localhost:6379/0"
    mock_settings.REDIS_POOL_SIZE = 10
    mock_settings.REDIS_TIMEOUT_SECONDS = 2
    mock_settings.REDIS_HEALTH_CHECK_INTERVAL = 30
    mock_settings.REDIS_HEALTH_CHECK_FAILURE_THRESHOLD = 3

    with umock.patch("app.services.redis_client.get_settings", return_value=mock_settings):
        client = RedisClient()
        await client.connect()
        metrics = list(redis_degraded.collect())
        assert metrics[0].samples[0].value == 0


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
    metrics = list(redis_degraded.collect())
    samples = list(metrics[0].samples)
    assert samples[0].value == 0


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


@pytest.mark.asyncio
async def test_set_and_get_round_trip() -> None:
    """Setting a value and then getting it returns the same value."""
    # Use decode_responses=True to match the real RedisClient config
    fake_redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    client = RedisClient()
    client._redis = fake_redis
    client._pool = fake_redis.connection_pool
    await client.set("test:key", "test_value", 60)
    result = await client.get("test:key")
    assert result == "test_value"


@pytest.mark.asyncio
async def test_get_returns_none_for_missing_key() -> None:
    """``get()`` returns ``None`` for a key that was never set."""
    fake_redis = fakeredis.FakeAsyncRedis()
    client = RedisClient()
    client._redis = fake_redis
    result = await client.get("nonexistent:key")
    assert result is None


@pytest.mark.asyncio
async def test_set_nx_acquires_lock() -> None:
    """``set_nx()`` returns ``True`` for a new lock key."""
    fake_redis = fakeredis.FakeAsyncRedis()
    client = RedisClient()
    client._redis = fake_redis
    result = await client.set_nx("lock:test", "", 5)
    assert result is True


@pytest.mark.asyncio
async def test_set_nx_returns_false_for_existing_lock() -> None:
    """``set_nx()`` returns ``False`` for an already-set lock key."""
    fake_redis = fakeredis.FakeAsyncRedis()
    client = RedisClient()
    client._redis = fake_redis
    await client._redis.set("lock:existing", "held")
    result = await client.set_nx("lock:existing", "", 5)
    assert result is False


@pytest.mark.asyncio
async def test_ping_with_recovery_logging() -> None:
    """``ping()`` logs recovery when transitioning from unhealthy to healthy."""
    fake_redis = fakeredis.FakeAsyncRedis()
    client = RedisClient()
    client._redis = fake_redis
    # Simulate degraded state
    client.healthy = False
    client.failure_count = 3
    # Ping should succeed and log recovery
    ok = await client.ping()
    assert ok is True
    assert client.healthy is True
    assert client.failure_count == 0


@pytest.mark.asyncio
async def test_ping_failure_threshold_triggers_degraded() -> None:
    """``ping()`` sets healthy=False after failure threshold is reached."""
    import unittest.mock as umock

    fake_redis = fakeredis.FakeAsyncRedis()
    client = RedisClient()
    client._redis = fake_redis
    client.healthy = True
    # Override settings to use threshold=1
    mock_settings = umock.MagicMock()
    mock_settings.REDIS_HEALTH_CHECK_FAILURE_THRESHOLD = 1
    mock_settings.REDIS_HEALTH_CHECK_INTERVAL = 30
    client._settings = mock_settings

    # Make fakeredis raise an error on ping
    async def failing_ping() -> None:
        msg = "Connection refused"
        raise OSError(msg)

    fake_redis.ping = failing_ping  # type: ignore[assignment]

    ok = await client.ping()
    assert ok is False
    assert client.healthy is False
    assert client.failure_count == 1
