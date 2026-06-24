"""
Tests for the cache service (``CacheService`` / ``RedisClient``).

Covers:
- Cache miss on first call, hit on second
- TTL expiry triggers miss
- Fallback on Redis exception
- Health check state management
- Concurrent request deduplication
"""

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.services.cache_key import make_cache_key
from app.services.cache_service import CacheService
from app.services.redis_client import RedisClient


def _decode(data: str | bytes | None) -> str | None:
    """Decode bytes to str if needed."""
    if isinstance(data, bytes):
        return data.decode("utf-8")
    return data


@pytest.mark.asyncio
async def test_get_or_compute_miss_on_first_call(fake_redis) -> None:  # type: ignore[no-untyped-def]
    """First call to get_or_compute returns miss status."""
    redis_client = RedisClient()
    redis_client._redis = fake_redis
    redis_client.healthy = True

    cache_service = CacheService(redis_client)
    key = make_cache_key("test:v1", {"city": "Gdańsk"})

    call_count = 0

    async def compute() -> str:
        nonlocal call_count
        call_count += 1
        return '{"data": "test"}'

    data, status = await cache_service.get_or_compute(key, compute)
    assert status == "miss"
    assert data == '{"data": "test"}'
    assert call_count == 1


@pytest.mark.asyncio
async def test_get_or_compute_hit_on_second_call(fake_redis) -> None:  # type: ignore[no-untyped-def]
    """Second call to get_or_compute returns hit status within TTL."""
    redis_client = RedisClient()
    redis_client._redis = fake_redis
    redis_client.healthy = True

    cache_service = CacheService(redis_client)
    key = make_cache_key("test:v1", {"city": "Gdańsk"})

    call_count = 0

    async def compute() -> str:
        nonlocal call_count
        call_count += 1
        return '{"data": "test"}'

    # First call: miss
    data1, status1 = await cache_service.get_or_compute(key, compute)
    assert status1 == "miss"
    assert call_count == 1

    # Second call: hit
    data2, status2 = await cache_service.get_or_compute(key, compute)
    assert status2 == "hit"
    assert call_count == 1  # compute was not called again
    assert _decode(data2) == '{"data": "test"}'


@pytest.mark.asyncio
async def test_ttl_expiry_triggers_miss(fake_redis) -> None:  # type: ignore[no-untyped-def]
    """After TTL expires, next call returns miss."""
    redis_client = RedisClient()
    redis_client._redis = fake_redis
    redis_client.healthy = True

    cache_service = CacheService(redis_client)
    key = make_cache_key("test:v1", {"city": "Gdańsk"})

    call_count = 0

    async def compute() -> str:
        nonlocal call_count
        call_count += 1
        return '{"data": "test"}'

    # First call: miss (stores with 1s TTL)
    _, status1 = await cache_service.get_or_compute(key, compute, ttl=1)
    assert status1 == "miss"

    # Wait for TTL to expire
    import asyncio
    await asyncio.sleep(1.1)

    # Third call: should be miss again (TTL expired)
    _, status3 = await cache_service.get_or_compute(key, compute)
    assert status3 == "miss"
    assert call_count == 2  # compute called again


@pytest.mark.asyncio
async def test_fallback_on_redis_exception(fake_redis) -> None:  # type: ignore[no-untyped-def]
    """When Redis raises an exception, fallback returns (data, 'miss (fallback)')."""
    redis_client = RedisClient()
    redis_client._redis = fake_redis
    redis_client.healthy = True

    # Make the redis.get method raise an exception
    async def broken_get(*args: object, **kwargs: object) -> str:
        msg = "Connection refused"
        raise RedisConnectionError(msg)

    fake_redis.get = broken_get

    cache_service = CacheService(redis_client)
    key = make_cache_key("test:v1", {"city": "Gdańsk"})

    call_count = 0

    async def compute() -> str:
        nonlocal call_count
        call_count += 1
        return '{"data": "fallback"}'

    data, status = await cache_service.get_or_compute(key, compute)
    assert status == "miss (fallback)"
    assert data == '{"data": "fallback"}'
    assert call_count == 1


@pytest.mark.asyncio
async def test_degraded_mode_skips_redis(fake_redis) -> None:  # type: ignore[no-untyped-def]
    """When Redis is unhealthy, get_or_compute skips Redis and goes to compute."""
    redis_client = RedisClient()
    redis_client._redis = fake_redis
    redis_client.healthy = False  # Degraded mode

    cache_service = CacheService(redis_client)
    key = make_cache_key("test:v1", {"city": "Gdańsk"})

    call_count = 0

    async def compute() -> str:
        nonlocal call_count
        call_count += 1
        return '{"data": "degraded"}'

    # Even if something is cached, degraded mode should skip Redis
    data, status = await cache_service.get_or_compute(key, compute)
    assert status == "miss (fallback)"
    assert call_count == 1


@pytest.mark.asyncio
async def test_concurrent_dedup_one_db_query(fake_redis) -> None:  # type: ignore[no-untyped-def]
    """Multiple concurrent requests for same key should do one DB query."""
    redis_client = RedisClient()
    redis_client._redis = fake_redis
    redis_client.healthy = True

    cache_service = CacheService(redis_client)
    key = make_cache_key("test:v1", {"city": "Gdańsk"})

    call_count = 0

    async def compute() -> str:
        nonlocal call_count
        call_count += 1
        import asyncio
        await asyncio.sleep(0.1)  # Simulate slow DB
        return '{"data": "slow"}'

    # Run two concurrent requests
    async def request() -> tuple[str, str]:
        return await cache_service.get_or_compute(key, compute)

    import asyncio
    results = await asyncio.gather(request(), request())

    # Both should get data
    for data, status in results:
        assert _decode(data) == '{"data": "slow"}'

    # Only one DB query should have occurred
    assert call_count == 1
