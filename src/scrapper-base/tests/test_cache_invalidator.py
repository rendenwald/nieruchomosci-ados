"""Tests for CacheInvalidator — Redis cache invalidation after property upsert."""

from __future__ import annotations

import os
from typing import Any

import pytest
from fakeredis.aioredis import FakeRedis

from scraper_base.cache_invalidator import CacheInvalidator


@pytest.fixture
def fake_redis() -> FakeRedis:
    """Return a fake Redis client for testing."""
    return FakeRedis()


@pytest.fixture
def cache_invalidator(fake_redis: FakeRedis) -> CacheInvalidator:
    """Return a CacheInvalidator backed by fake Redis.

    We create a minimal invalidator by injecting the fake Redis connection
    via a pre-built ConnectionPool.  Since CacheInvalidator's constructor
    creates its own Redis instance from a pool, we access the internal
    ``_redis`` attribute for testing.  This is acceptable for unit tests
    of a private implementation.
    """
    invalidator = CacheInvalidator(redis_url="redis://localhost:6379/0")
    # Replace the real Redis client with our fakeredis instance
    invalidator._redis = fake_redis  # noqa: SLF001
    invalidator._disabled = False
    return invalidator


# ── Fixtures: seed data ────────────────────────────────────────────────────


async def _seed_list_keys(fake_redis: FakeRedis, count: int = 5) -> list[str]:
    """Insert ``count`` fake list cache keys and return their names."""
    keys: list[str] = []
    for i in range(count):
        key = f"properties:list:v1:hash{i:04d}"
        await fake_redis.setex(key, 120, f'{{"data": {i}}}')
        keys.append(key)
    return keys


# ── Tests ──────────────────────────────────────────────────────────────────


class TestCacheInvalidator:
    """CacheInvalidator unit tests."""

    async def test_invalidate_list_on_insert(
        self,
        cache_invalidator: CacheInvalidator,
        fake_redis: FakeRedis,
    ) -> None:
        """On insert (is_new=True): all ``properties:list:v1:*`` keys are deleted."""
        keys = await _seed_list_keys(fake_redis, count=5)

        # Also seed a non-list key that should NOT be deleted
        await fake_redis.setex("other:key", 120, "keep_me")

        await cache_invalidator.invalidate(property_id=42, is_new=True)

        # All list keys should be gone
        for key in keys:
            exists = await fake_redis.exists(key)
            assert not exists, f"List key {key} should have been deleted"

        # Non-list key should still exist
        assert await fake_redis.exists("other:key")
        assert await fake_redis.get("other:key") == b"keep_me"

    async def test_invalidate_cities_on_insert(
        self,
        cache_invalidator: CacheInvalidator,
        fake_redis: FakeRedis,
    ) -> None:
        """On insert: ``cities:list`` key is deleted."""
        await fake_redis.setex("cities:list", 3600, '["Warszawa", "Kraków"]')

        await cache_invalidator.invalidate(property_id=42, is_new=True)

        assert not await fake_redis.exists("cities:list")

    async def test_invalidate_detail_on_update(
        self,
        cache_invalidator: CacheInvalidator,
        fake_redis: FakeRedis,
    ) -> None:
        """On update (is_new=False): ``properties:detail:{id}`` is deleted."""
        await fake_redis.setex("properties:detail:7", 300, '{"id": 7, "price": 500000}')

        await cache_invalidator.invalidate(property_id=7, is_new=False)

        assert not await fake_redis.exists("properties:detail:7")

    async def test_no_list_invalidation_on_update(
        self,
        cache_invalidator: CacheInvalidator,
        fake_redis: FakeRedis,
    ) -> None:
        """On update: list cache keys are NOT deleted."""
        keys = await _seed_list_keys(fake_redis, count=3)

        await cache_invalidator.invalidate(property_id=42, is_new=False)

        # All list keys should still exist
        for key in keys:
            exists = await fake_redis.exists(key)
            assert exists, f"List key {key} should NOT have been deleted on update"

    async def test_skip_when_no_redis_url(self) -> None:
        """When ``REDIS_URL`` is not set, invalidation is a no-op."""
        # Temporarily unset REDIS_URL
        old = os.environ.pop("REDIS_URL", None)
        try:
            invalidator = CacheInvalidator()
            assert invalidator.is_disabled

            # This should not raise
            await invalidator.invalidate(property_id=1, is_new=True)
        finally:
            if old is not None:
                os.environ["REDIS_URL"] = old

    async def test_graceful_on_redis_error(
        self,
        cache_invalidator: CacheInvalidator,
    ) -> None:
        """When Redis raises, invalidate() does not propagate the exception."""
        from redis.exceptions import RedisError  # noqa: PLC0415

        # Break the internal redis client
        async def _broken_delete(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            msg = "Connection refused"
            raise RedisError(msg)

        assert cache_invalidator._redis is not None  # noqa: SLF001
        original_delete = cache_invalidator._redis.delete  # noqa: SLF001
        cache_invalidator._redis.delete = _broken_delete  # type: ignore[method-assign]  # noqa: SLF001

        try:
            # This should not raise
            await cache_invalidator.invalidate(property_id=42, is_new=True)
        except Exception:  # noqa: BLE001
            pytest.fail("invalidate() raised an exception on Redis error")
        finally:
            cache_invalidator._redis.delete = original_delete  # noqa: SLF001

    async def test_invalidate_list_on_insert_many_keys(
        self,
        cache_invalidator: CacheInvalidator,
        fake_redis: FakeRedis,
    ) -> None:
        """Many list keys are all deleted on insert."""
        # fakeredis SCAN may not paginate identically to real Redis, but
        # at this scale all keys should be found and deleted.
        keys = await _seed_list_keys(fake_redis, count=50)

        await cache_invalidator.invalidate(property_id=42, is_new=True)

        for key in keys:
            exists = await fake_redis.exists(key)
            assert not exists, f"List key {key} should have been deleted"

    async def test_invalidate_detail_non_existent(
        self,
        cache_invalidator: CacheInvalidator,
        fake_redis: FakeRedis,
    ) -> None:
        """Deleting a non-existent detail key is a no-op (no error)."""
        # Key does not exist
        await cache_invalidator.invalidate(property_id=999, is_new=False)
        # No assertion needed — the test is that no exception is raised

    async def test_double_invalidate_harmless(
        self,
        cache_invalidator: CacheInvalidator,
        fake_redis: FakeRedis,
    ) -> None:
        """Invalidating the same property twice is harmless."""
        await fake_redis.setex("properties:detail:1", 300, "data")

        await cache_invalidator.invalidate(property_id=1, is_new=False)
        await cache_invalidator.invalidate(property_id=1, is_new=False)

        assert not await fake_redis.exists("properties:detail:1")

    async def test_cities_key_absent_on_insert(
        self,
        cache_invalidator: CacheInvalidator,
        fake_redis: FakeRedis,
    ) -> None:
        """Deleting ``cities:list`` when it does not exist is harmless."""
        await cache_invalidator.invalidate(property_id=42, is_new=True)
        # No assertion needed — no exception expected
