"""
Cache-aside service with concurrent request deduplication.

Provides ``get_or_compute()`` which implements the standard cache-aside
pattern: check Redis → miss → lock → double-check → compute → store.
"""

from collections.abc import Callable
from typing import Any, TypeVar

import structlog
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.metrics import cache_errors_total, cache_hits_total, cache_misses_total
from app.services.redis_client import RedisClient

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CacheService:
    """Cache-aside service wrapping ``RedisClient``.

    Provides ``get_or_compute()`` with thundering-herd prevention via
    ``SET NX`` lock and double-check after lock acquisition.
    """

    def __init__(self, redis_client: RedisClient) -> None:
        self._redis = redis_client
        self._settings = get_settings()
        self._log = logger.bind(service="cache")
        self._endpoint = "properties"
        self._key_prefix = self._settings.CACHE_KEY_PREFIX

    async def get_or_compute(
        self,
        key: str,
        compute: Callable[[], Any],
        ttl: int | None = None,
    ) -> tuple[str, str]:
        """Cache-aside read: return cached value or compute and store.

        Steps:
            1. If Redis is in degraded mode, skip directly to ``compute``.
            2. Attempt ``redis.GET(key)``.
            3. On hit → return ``(json_data, "hit")``.
            4. On miss → acquire lock via ``SET NX key:lock "" EX 5``.
            5. Double-check cache after lock (another request may have stored it).
            6. If still missing, call ``compute()``.
            7. Store result with ``redis.SETEX(key, ttl, json_data)``.
            8. Release lock (let it expire naturally via TTL).
            9. Return ``(json_data, "miss")``.

        If Redis raises an exception at any point, fall back to
        ``compute()`` and return ``(json_data, "miss (fallback)")``
        without writing to the cache.

        Args:
            key: The cache key.
            compute: Async callable that returns the data to cache.
            ttl: Cache TTL in seconds. Defaults to ``CACHE_TTL_SECONDS``.

        Returns:
            A tuple of ``(json_data: str, cache_status: str)`` where
            ``cache_status`` is one of ``"hit"``, ``"miss"``, or
            ``"miss (fallback)"``.

        """
        effective_ttl = ttl or self._settings.CACHE_TTL_SECONDS

        # ── Degraded mode: skip Redis entirely ──────────────────────────
        if not self._redis.healthy:
            data = await compute()
            cache_misses_total.labels(
                endpoint=self._endpoint,
                cache_key_prefix=self._key_prefix,
            ).inc()
            return (data, "miss (fallback)")

        try:
            # ── Try cache hit ───────────────────────────────────────────
            cached = await self._redis.get(key)
            if cached is not None:
                cache_hits_total.labels(
                    endpoint=self._endpoint,
                    cache_key_prefix=self._key_prefix,
                ).inc()
                return (cached, "hit")

            # ── Cache miss: lock + double-check + compute ───────────────
            cache_misses_total.labels(
                endpoint=self._endpoint,
                cache_key_prefix=self._key_prefix,
            ).inc()

            lock_key = f"{key}:lock"
            acquired = await self._redis.set_nx(lock_key, "", 5)

            if acquired:
                # Double-check: another request may have stored it while we
                # were acquiring the lock
                cached_after_lock = await self._redis.get(key)
                if cached_after_lock is not None:
                    return (cached_after_lock, "hit")

                # Compute and store
                data = await compute()
                await self._redis.set(key, data, effective_ttl)
                return (data, "miss")
            else:
                # Lock not acquired — another request is computing.
                # Wait briefly then try reading again (up to 3 attempts).
                import asyncio  # noqa: PLC0415

                for attempt in range(3):
                    await asyncio.sleep(0.1 * (attempt + 1))
                    cached = await self._redis.get(key)
                    if cached is not None:
                        cache_hits_total.labels(
                            endpoint=self._endpoint,
                            cache_key_prefix=self._key_prefix,
                        ).inc()
                        return (cached, "hit")

                # Fallback: compute ourselves after waiting
                data = await compute()
                await self._redis.set(key, data, effective_ttl)
                return (data, "miss")

        except RedisError as exc:
            # ── Fallback: Redis error → DB query, no cache write ────────
            self._log.warning(
                "cache_fallback_due_to_redis_error",
                error=str(exc),
                key=key,
            )
            cache_errors_total.labels(
                endpoint=self._endpoint,
                operation="get_or_compute",
                error_type=type(exc).__name__,
            ).inc()

            data = await compute()
            return (data, "miss (fallback)")
