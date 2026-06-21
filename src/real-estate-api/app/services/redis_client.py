"""
Async Redis client wrapper with connection pooling, health checks,
and graceful degradation.

Uses ``redis.asyncio`` (official ``redis-py`` v5+) — no deprecated
``aioredis`` library.
"""

import structlog
from redis.asyncio import Redis as AsyncRedis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import RedisError, TimeoutError

from app.core.config import get_settings
from app.core.metrics import cache_operation_duration_seconds

logger = structlog.get_logger(__name__)


class RedisClient:
    """Async Redis client with connection pooling and health tracking.

    Attributes:
        healthy: Current health status (True = available, False = degraded).
        failure_count: Consecutive health-check failures.
    """

    def __init__(self) -> None:
        self._redis: AsyncRedis | None = None
        self._pool: ConnectionPool | None = None
        self.healthy: bool = True
        self.failure_count: int = 0
        self._settings = get_settings()
        self._log = logger.bind(service="redis")

    async def connect(self) -> None:
        """Create the Redis connection pool and verify connectivity.

        Logs connection status on startup. Sets ``healthy`` based on
        the initial ping result.
        """
        try:
            self._pool = ConnectionPool.from_url(
                self._settings.REDIS_URL,
                max_connections=self._settings.REDIS_POOL_SIZE,
                socket_connect_timeout=self._settings.REDIS_TIMEOUT_SECONDS,
                socket_timeout=self._settings.REDIS_TIMEOUT_SECONDS,
                decode_responses=True,
            )
            self._redis = AsyncRedis(connection_pool=self._pool)
            await self.ping()
            self.healthy = True
            self.failure_count = 0
            self._log.info("redis_connected", healthy=True)
        except RedisError as exc:
            self.healthy = False
            self.failure_count += 1
            self._log.warning(
                "redis_connection_failed",
                error=str(exc),
                healthy=False,
            )

    async def disconnect(self) -> None:
        """Close the Redis connection pool gracefully."""
        if self._pool is not None:
            await self._pool.disconnect()
            self._log.info("redis_disconnected")

    async def ping(self) -> bool:
        """Health check with timeout.

        Returns:
            ``True`` if Redis responds, ``False`` otherwise.
        """
        if self._redis is None:
            return False
        try:
            result = await self._redis.ping()
            if result:
                if not self.healthy:
                    self._log.warning("redis_recovered", healthy=True)
                self.healthy = True
                self.failure_count = 0
                return True
            return False
        except (RedisError, TimeoutError, OSError) as exc:
            self.failure_count += 1
            if self.failure_count >= self._settings.REDIS_HEALTH_CHECK_FAILURE_THRESHOLD:
                if self.healthy:
                    self._log.warning(
                        "redis_degraded",
                        failure_count=self.failure_count,
                        error=str(exc),
                    )
                self.healthy = False
            return False

    async def get(self, key: str) -> str | None:
        """GET a value from Redis.

        Args:
            key: The cache key to retrieve.

        Returns:
            The string value, or ``None`` if not found.

        Raises:
            RedisError: On Redis communication failure (caller handles).
        """
        if self._redis is None:
            return None
        with cache_operation_duration_seconds.labels(
            endpoint="properties", operation="get",
        ).time():
            value: str | None = await self._redis.get(key)
            return value

    async def set(self, key: str, value: str, ttl: int) -> None:
        """SET a value in Redis with TTL (SETEX semantics).

        Args:
            key: The cache key.
            value: The string value to store.
            ttl: Time-to-live in seconds.

        Raises:
            RedisError: On Redis communication failure (caller handles).
        """
        if self._redis is None:
            return
        with cache_operation_duration_seconds.labels(
            endpoint="properties", operation="set",
        ).time():
            await self._redis.setex(key, ttl, value)

    async def set_nx(self, key: str, value: str, ttl: int) -> bool:
        """Set a key if it does not already exist (SET NX).

        Used for distributed locking to prevent thundering herd.

        Args:
            key: The lock key.
            value: The lock value (typically empty string).
            ttl: Lock TTL in seconds (short-lived, ~5s).

        Returns:
            ``True`` if the lock was acquired, ``False`` otherwise.

        Raises:
            RedisError: On Redis communication failure (caller handles).
        """
        if self._redis is None:
            return False
        result: bool = await self._redis.setnx(key, value)
        if result:
            await self._redis.expire(key, ttl)
        return result
