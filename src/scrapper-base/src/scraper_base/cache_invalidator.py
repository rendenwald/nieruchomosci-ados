"""
Cache invalidator — deletes affected Redis cache keys after a property upsert.

On insert: SCAN + DEL ``properties:list:v1:*`` keys + DEL ``cities:list``.
On update: DEL ``properties:detail:{id}`` only.

Graceful degradation: if ``REDIS_URL`` env var is absent or a Redis error
occurs, invalidation is silently skipped and the write path is unaffected.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from prometheus_client import Counter
from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.client import Pipeline
from redis.exceptions import RedisError

logger = structlog.get_logger(__name__)

# ── Prometheus metrics ─────────────────────────────────────────────────────

cache_invalidation_total: Counter = Counter(
    "cache_invalidation_total",
    "Total number of cache invalidation attempts",
    ["operation", "status"],
)

# ── Cache key patterns ────────────────────────────────────────────────────

LIST_KEY_PATTERN: str = "properties:list:v1:*"
CITIES_KEY: str = "cities:list"
DETAIL_KEY_TEMPLATE: str = "properties:detail:{id}"


class CacheInvalidator:
    """Invalidates Redis cache keys after a property upsert.

    The invalidator is a *fire-and-forget* helper — it never raises and never
    blocks the caller. If Redis is not configured or unreachable, invalidation
    is silently skipped.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        *,
        pool: ConnectionPool | None = None,
    ) -> None:
        """Initialise the invalidator.

        Args:
            redis_url: Redis connection URL. Falls back to ``REDIS_URL`` env
                var. If *both* are ``None``, invalidation is disabled.
            pool: An optional pre-existing ``ConnectionPool``. If given,
                ``redis_url`` is ignored.
        """
        self._pool: ConnectionPool | None = pool
        self._redis: Redis | None = None
        self._disabled: bool = False

        url = redis_url or os.environ.get("REDIS_URL")
        if url is None:
            self._disabled = True
            logger.info("cache_invalidator_disabled", reason="REDIS_URL not configured")
            return

        if self._pool is None:
            try:
                self._pool = ConnectionPool.from_url(
                    url,
                    max_connections=2,
                    timeout=2,
                )
            except Exception as exc:
                logger.warning("cache_invalidator_pool_creation_failed", error=str(exc))
                self._disabled = True
                return

        self._redis = Redis(connection_pool=self._pool)

    @property
    def is_disabled(self) -> bool:
        """Return ``True`` if the invalidator is not connected to Redis."""
        return self._disabled or self._redis is None

    async def invalidate(self, property_id: int, is_new: bool) -> None:
        """Invalidate cache keys after a property upsert.

        Args:
            property_id: The ``Property.id`` that was upserted.
            is_new: ``True`` for a new insert, ``False`` for an update.

        The method is fire-and-forget: exceptions are logged and suppressed.
        """
        if self._disabled or self._redis is None:
            cache_invalidation_total.labels(
                operation="insert" if is_new else "update",
                status="skipped",
            ).inc()
            return

        try:
            if is_new:
                await self._invalidate_list_caches()
            else:
                await self._invalidate_detail_cache(property_id)

            cache_invalidation_total.labels(
                operation="insert" if is_new else "update",
                status="success",
            ).inc()
        except RedisError:
            logger.exception(
                "cache_invalidation_failed",
                property_id=property_id,
                is_new=is_new,
            )
            cache_invalidation_total.labels(
                operation="insert" if is_new else "update",
                status="fail",
            ).inc()

    async def _invalidate_list_caches(self) -> None:
        """Scan and delete all ``properties:list:v1:*`` keys + ``cities:list``."""
        assert self._redis is not None  # guarded by caller

        cursor: int = 0
        deleted_list: int = 0

        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor,
                match=LIST_KEY_PATTERN,
                count=100,
            )
            if keys:
                await self._redis.delete(*keys)
                deleted_list += len(keys)
            if cursor == 0:
                break

        # Delete the aggregated cities key (no-op if absent)
        await self._redis.delete(CITIES_KEY)

        if deleted_list or True:  # always log at debug
            logger.debug(
                "cache_list_invalidated",
                list_keys_deleted=deleted_list,
                cities_key_deleted=True,
            )

    async def _invalidate_detail_cache(self, property_id: int) -> None:
        """Delete the detail cache key ``properties:detail:{id}``."""
        assert self._redis is not None  # guarded by caller

        key = DETAIL_KEY_TEMPLATE.format(id=property_id)
        await self._redis.delete(key)
        logger.debug("cache_detail_invalidated", key=key)

    async def close(self) -> None:
        """Close the underlying Redis connection pool, if owned."""
        if self._pool is not None:
            await self._pool.disconnect()
